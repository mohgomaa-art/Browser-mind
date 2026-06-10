"""VocabInductor — clusters fallback patterns and proposes new vocabulary items.

Two-stage process
─────────────────
  1. cluster_fallbacks(entries)
       Groups similar name_fragments using combined trigram + word Jaccard
       similarity. Greedy single-linkage: sorted by frequency descending so
       high-signal patterns anchor clusters.

  2. propose_vocab_expansions(clusters, min_sites, min_freq)
       Emits a VocabProposal for every cluster that crosses the evidence
       thresholds. Each proposal carries an auto-generated UPPER_SNAKE name,
       an inferred L1 category, and the name_patterns to add to the runtime
       normalizer.

Confirmed proposals
───────────────────
  VocabProposalStore.confirm(proposal_id)
      → updates status to CONFIRMED
      → rewrites ~/.browsermind/vocab_extensions.json
      → PrimitiveNormalizer.load_vocab_extensions() picks up the new patterns

The complete loop:
  ExplorationHarness (fixed) → FallbackLedger → VocabInductor
      → VocabProposalStore → vocab_review.py (human or auto-confirm)
      → vocab_extensions.json → PrimitiveNormalizer._RUNTIME_PATTERNS
      → fallback rate drops → better hypothesis graduation
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from browsermind_core.representation.fallback_ledger import FallbackEntry


# ── Similarity ────────────────────────────────────────────────────────────────

def _trigrams(s: str) -> Set[str]:
    s = re.sub(r"[\s_]+", " ", s.lower()).strip()
    return {s[i:i+3] for i in range(max(0, len(s) - 2))}


def _word_tokens(s: str) -> Set[str]:
    return set(w for w in re.split(r"[\s_]+", s.lower()) if w)


def similarity(a: str, b: str) -> float:
    """Combined trigram + word Jaccard similarity in [0, 1]."""
    ta, tb = _trigrams(a), _trigrams(b)
    wa, wb = _word_tokens(a), _word_tokens(b)

    tri = len(ta & tb) / max(len(ta | tb), 1)
    wrd = len(wa & wb) / max(len(wa | wb), 1)

    return round(0.5 * tri + 0.5 * wrd, 4)


# ── Stop words ─────────────────────────────────────────────────────────────────

_STOPWORDS = frozenset({
    "a", "an", "the", "to", "of", "in", "on", "at", "by", "for",
    "and", "or", "but", "this", "that", "my", "your", "its",
    "all", "now", "here", "item", "button", "link", "me",
})


# ── L1 category inference ──────────────────────────────────────────────────────

_L1_HINTS: List[tuple] = [
    ("AUTHENTICATE",    frozenset({"sign", "login", "password", "account", "auth", "credential", "register"})),
    ("LOCATE",          frozenset({"search", "find", "query", "look", "browse", "explore", "discover"})),
    ("CONSENT",         frozenset({"accept", "decline", "cookie", "consent", "agree", "reject", "privacy", "gdpr", "banner"})),
    ("TRANSACT",        frozenset({"buy", "cart", "checkout", "order", "pay", "coupon", "purchase",
                                    "delete", "remove", "save", "edit", "update", "create", "submit",
                                    "upload", "download", "export", "import"})),
    ("INTERACT_OBJECT", frozenset({"play", "pause", "mute", "like", "share", "follow",
                                    "subscribe", "bookmark", "wishlist", "favourite", "favorite",
                                    "watch", "star", "react", "upvote", "heart", "clap"})),
    ("SELECT",          frozenset({"next", "previous", "prev", "page", "filter", "sort",
                                    "load", "show", "view", "select", "choose", "pick",
                                    "navigate", "open", "go"})),
]


def infer_l1_category(words: Set[str]) -> str:
    best, best_score = "INTERACT_OBJECT", 0
    for l1, hint_words in _L1_HINTS:
        score = len(words & hint_words)
        if score > best_score:
            best, best_score = l1, score
    return best


# ── Name generation ────────────────────────────────────────────────────────────

def generate_proposed_name(fragments: List[str]) -> str:
    """Generate an UPPER_SNAKE_CASE name from a list of similar fragments.

    Picks the top 2 non-stopword words by frequency across fragments,
    preserving a natural verb-object order where possible.
    """
    word_freq: Dict[str, int] = {}
    for frag in fragments:
        for w in re.split(r"[\s_]+", frag.lower()):
            if w and w not in _STOPWORDS and len(w) >= 3:
                word_freq[w] = word_freq.get(w, 0) + 1

    if not word_freq:
        return "UNKNOWN_INTERACTION"

    # Top words by (frequency DESC, length DESC) for determinism
    top = sorted(word_freq, key=lambda w: (-word_freq[w], -len(w)))

    if len(top) == 1:
        return top[0].upper()

    # Heuristic: try to keep verb first
    verbs = {"add", "open", "submit", "send", "edit", "delete", "save",
             "upload", "download", "play", "pause", "mute", "follow",
             "share", "like", "buy", "checkout", "apply", "accept",
             "decline", "close", "confirm", "create", "remove", "search"}
    name_words = top[:2]
    if top[0] not in verbs and top[1] in verbs:
        name_words = [top[1], top[0]]

    return "_".join(w.upper() for w in name_words)


# ── FallbackCluster ────────────────────────────────────────────────────────────

@dataclass
class FallbackCluster:
    """A group of semantically similar fallback fragments."""
    cluster_id:      str
    members:         List[str]    # name_fragments
    sites:           List[str]    # distinct site keys
    total_frequency: int
    proposed_name:   str          # e.g. "ADD_WISHLIST"
    l1_category:     str          # e.g. "INTERACT_OBJECT"
    cohesion:        float        # avg pairwise similarity in [0, 1]
    example_names:   List[str]    # raw target_name strings for human review

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id":      self.cluster_id,
            "members":         self.members,
            "sites":           self.sites,
            "total_frequency": self.total_frequency,
            "proposed_name":   self.proposed_name,
            "l1_category":     self.l1_category,
            "cohesion":        self.cohesion,
            "example_names":   self.example_names,
        }


# ── VocabProposal ──────────────────────────────────────────────────────────────

@dataclass
class VocabProposal:
    """A proposed new vocabulary item derived from a FallbackCluster.

    Lifecycle: PROPOSED → CONFIRMED (human reviewed) → INTEGRATED (added to source)
               PROPOSED → REJECTED
    """
    proposal_id:     str
    proposed_name:   str
    l1_category:     str
    name_patterns:   List[str]    # substrings that match this intent at runtime
    cluster_id:      str
    cluster_members: List[str]
    cluster_sites:   List[str]
    total_frequency: int
    example_names:   List[str] = field(default_factory=list)
    status:          str = "PROPOSED"
    created_at:      str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    confirmed_at:    Optional[str] = None
    rejected_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id":     self.proposal_id,
            "proposed_name":   self.proposed_name,
            "l1_category":     self.l1_category,
            "name_patterns":   self.name_patterns,
            "cluster_id":      self.cluster_id,
            "cluster_members": self.cluster_members,
            "cluster_sites":   self.cluster_sites,
            "total_frequency": self.total_frequency,
            "example_names":   self.example_names,
            "status":          self.status,
            "created_at":      self.created_at,
            "confirmed_at":    self.confirmed_at,
            "rejected_reason": self.rejected_reason,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VocabProposal":
        d2 = dict(d)
        d2.setdefault("confirmed_at", None)
        d2.setdefault("rejected_reason", None)
        d2.setdefault("example_names", [])
        known = {
            "proposal_id", "proposed_name", "l1_category", "name_patterns",
            "cluster_id", "cluster_members", "cluster_sites", "total_frequency",
            "example_names", "status", "created_at", "confirmed_at", "rejected_reason",
        }
        return cls(**{k: v for k, v in d2.items() if k in known})


# ── VocabProposalStore ─────────────────────────────────────────────────────────

class VocabProposalStore:
    """Persistent store for VocabProposals.

    On confirm(), rewrites vocab_extensions.json in the format that
    PrimitiveNormalizer.load_vocab_extensions() expects so the new patterns
    are immediately available on the next normalizer instantiation.
    """

    DEFAULT_PROPOSALS_PATH  = Path.home() / ".browsermind" / "vocab_proposals.json"
    DEFAULT_EXTENSIONS_PATH = Path.home() / ".browsermind" / "vocab_extensions.json"

    def __init__(
        self,
        proposals_path:  Optional[Path] = None,
        extensions_path: Optional[Path] = None,
    ) -> None:
        self._pp = Path(proposals_path)  if proposals_path  else self.DEFAULT_PROPOSALS_PATH
        self._ep = Path(extensions_path) if extensions_path else self.DEFAULT_EXTENSIONS_PATH

    def save(self, proposal: VocabProposal) -> None:
        proposals = self._load()
        proposals[proposal.proposal_id] = proposal
        self._write_proposals(proposals)

    def save_many(self, proposals: List[VocabProposal]) -> None:
        existing = self._load()
        for p in proposals:
            existing[p.proposal_id] = p
        self._write_proposals(existing)

    def all(self) -> List[VocabProposal]:
        return list(self._load().values())

    def pending(self) -> List[VocabProposal]:
        return [p for p in self.all() if p.status == "PROPOSED"]

    def confirmed(self) -> List[VocabProposal]:
        return [p for p in self.all() if p.status in ("CONFIRMED", "INTEGRATED")]

    def get(self, proposal_id: str) -> Optional[VocabProposal]:
        return self._load().get(proposal_id)

    def confirm(self, proposal_id: str) -> Optional[VocabProposal]:
        proposals = self._load()
        p = proposals.get(proposal_id)
        if p is None:
            return None
        p.status = "CONFIRMED"
        p.confirmed_at = datetime.now(timezone.utc).isoformat()
        proposals[proposal_id] = p
        self._write_proposals(proposals)
        self._rebuild_extensions(proposals)
        return p

    def reject(self, proposal_id: str, reason: str = "") -> Optional[VocabProposal]:
        proposals = self._load()
        p = proposals.get(proposal_id)
        if p is None:
            return None
        p.status = "REJECTED"
        p.rejected_reason = reason or "manually rejected"
        proposals[proposal_id] = p
        self._write_proposals(proposals)
        return p

    def integrate(self, proposal_id: str) -> Optional[VocabProposal]:
        """Mark INTEGRATED once the pattern is added to source primitive_normalizer.py."""
        proposals = self._load()
        p = proposals.get(proposal_id)
        if p is None:
            return None
        p.status = "INTEGRATED"
        proposals[proposal_id] = p
        self._write_proposals(proposals)
        return p

    def stats(self) -> Dict[str, Any]:
        all_p = self.all()
        counts: Dict[str, int] = {}
        for p in all_p:
            counts[p.status] = counts.get(p.status, 0) + 1
        return {"total": len(all_p), "by_status": counts}

    # ── I/O ──────────────────────────────────────────────────────────────────

    def _load(self) -> Dict[str, VocabProposal]:
        if not self._pp.exists():
            return {}
        try:
            raw = json.loads(self._pp.read_text(encoding="utf-8"))
            return {k: VocabProposal.from_dict(v) for k, v in raw.items()}
        except Exception:
            return {}

    def _write_proposals(self, proposals: Dict[str, VocabProposal]) -> None:
        _atomic_write_json(self._pp, {k: v.to_dict() for k, v in proposals.items()})

    def _rebuild_extensions(self, proposals: Dict[str, VocabProposal]) -> None:
        """Rewrite vocab_extensions.json from all confirmed + integrated proposals."""
        confirmed = [
            p for p in proposals.values()
            if p.status in ("CONFIRMED", "INTEGRATED")
        ]
        extensions = [
            {
                "l0_name":     p.proposed_name,
                "l1_name":     p.l1_category,
                "patterns":    p.name_patterns,
                "proposal_id": p.proposal_id,
            }
            for p in confirmed
        ]
        _atomic_write_json(self._ep, extensions)


# ── Clustering ─────────────────────────────────────────────────────────────────

def cluster_fallbacks(
    entries: Dict[str, FallbackEntry],
    similarity_threshold: float = 0.35,
) -> List[FallbackCluster]:
    """Group similar fallback fragments using greedy single-linkage clustering.

    Processes entries sorted by frequency descending so the most-seen patterns
    anchor clusters. Two fragments are merged if their combined trigram + word
    Jaccard similarity exceeds `similarity_threshold`.

    Returns clusters sorted by total_frequency descending.
    """
    if not entries:
        return []

    sorted_entries = sorted(entries.values(), key=lambda e: -e.frequency)
    # clusters[i] = list of name_fragments in that cluster
    clusters: List[List[str]] = []

    for entry in sorted_entries:
        frag = entry.name_fragment
        best_idx, best_sim = -1, similarity_threshold

        for i, members in enumerate(clusters):
            sim = max(similarity(frag, m) for m in members)
            if sim > best_sim:
                best_sim = sim
                best_idx = i

        if best_idx >= 0:
            clusters[best_idx].append(frag)
        else:
            clusters.append([frag])

    result: List[FallbackCluster] = []
    for members in clusters:
        member_entries = [entries[m] for m in members if m in entries]
        all_sites      = sorted({s for e in member_entries for s in e.sites})
        total_freq     = sum(e.frequency for e in member_entries)
        all_examples   = list(dict.fromkeys(
            ex["name"] for e in member_entries for ex in e.examples
        ))[:8]

        # Cohesion: mean pairwise similarity
        pairs = [
            (members[i], members[j])
            for i in range(len(members))
            for j in range(i + 1, len(members))
        ]
        cohesion = (
            sum(similarity(a, b) for a, b in pairs) / len(pairs)
            if pairs else 1.0
        )

        proposed_name = generate_proposed_name(members)
        l1_cat        = infer_l1_category(_word_tokens(" ".join(members)))
        cluster_id    = hashlib.sha256(
            "|".join(sorted(members)).encode()
        ).hexdigest()[:12]

        result.append(FallbackCluster(
            cluster_id      = cluster_id,
            members         = members,
            sites           = all_sites,
            total_frequency = total_freq,
            proposed_name   = proposed_name,
            l1_category     = l1_cat,
            cohesion        = round(cohesion, 3),
            example_names   = all_examples,
        ))

    result.sort(key=lambda c: -c.total_frequency)
    return result


# ── Proposal generation ────────────────────────────────────────────────────────

def propose_vocab_expansions(
    clusters: List[FallbackCluster],
    min_sites: int = 2,
    min_freq:  int = 5,
) -> List[VocabProposal]:
    """Generate VocabProposals for clusters that meet evidence thresholds.

    Args:
        min_sites: cluster must span ≥ this many distinct sites (transfer signal)
        min_freq:  cluster total_frequency must be ≥ this value (noise filter)

    Returns proposals sorted by total_frequency descending.
    """
    proposals: List[VocabProposal] = []

    for cluster in clusters:
        if len(cluster.sites) < min_sites:
            continue
        if cluster.total_frequency < min_freq:
            continue

        proposal_id = hashlib.sha256(
            cluster.proposed_name.encode()
        ).hexdigest()[:16]

        proposals.append(VocabProposal(
            proposal_id     = proposal_id,
            proposed_name   = cluster.proposed_name,
            l1_category     = cluster.l1_category,
            name_patterns   = list(cluster.members),  # all fragments as match patterns
            cluster_id      = cluster.cluster_id,
            cluster_members = list(cluster.members),
            cluster_sites   = list(cluster.sites),
            total_frequency = cluster.total_frequency,
            example_names   = list(cluster.example_names),
        ))

    return proposals


# ── Utility ────────────────────────────────────────────────────────────────────

def _word_tokens(s: str) -> Set[str]:
    return {w for w in re.split(r"[\s_]+", s.lower()) if w}


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise
