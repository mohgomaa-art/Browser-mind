"""CapabilityHypothesis — a candidate capability pattern awaiting validation.

This is the landing zone for all unknown patterns encountered during exploration.
It sits between raw execution noise and a promoted CapabilityRecord:

  Raw Unknown Pattern (InvariantGraph with no CapabilityRecord)
        ↓
  CapabilityHypothesis (HYPOTHESIS)
        ↓  frequency ≥ 2, multiple contexts
  RECURRING
        ↓  frequency ≥ 5 OR environments ≥ 3
  EMERGING
        ↓  environments ≥ 3 AND frequency ≥ 10 (or manual promotion)
  CANDIDATE
        ↓  write CapabilityRecord, link back
  PROMOTED
        OR
  REFUTED  (evidence contradicts a genuine capability)

Key invariant
─────────────
A hypothesis is keyed by invariant_hash — the same content-addressed identity
used by CapabilityRecord. If a hypothesis is promoted, its invariant_hash
becomes the key of the resulting CapabilityRecord. There is a 1:1 relationship
between a promoted hypothesis and its CapabilityRecord.

Self-directed exploration loop
───────────────────────────────
The store exposes query(status=RECURRING | EMERGING) so ExplorationHarness can
retrieve "things worth revisiting" and feed them back as capability_targets in
ExplorationSpec. This closes the loop:

  Unknown pattern → Hypothesis → Recurring → Exploration Target →
  More evidence → Emerging → Candidate → CapabilityRecord
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ── Status constants ──────────────────────────────────────────────────────────

class HypothesisStatus:
    HYPOTHESIS = "HYPOTHESIS"   # first observation, single context
    RECURRING  = "RECURRING"    # seen ≥2 times in different contexts
    EMERGING   = "EMERGING"     # seen across ≥3 environments or ≥5 times
    CANDIDATE  = "CANDIDATE"    # ready for CapabilityRecord promotion
    PROMOTED   = "PROMOTED"     # CapabilityRecord written; hypothesis retired
    REFUTED    = "REFUTED"      # evidence disproves it as a genuine capability

# Ordered for tier comparison (higher index = more mature)
_STATUS_ORDER = [
    HypothesisStatus.HYPOTHESIS,
    HypothesisStatus.RECURRING,
    HypothesisStatus.EMERGING,
    HypothesisStatus.CANDIDATE,
    HypothesisStatus.PROMOTED,
    HypothesisStatus.REFUTED,   # terminal; separate branch
]

# Graduation thresholds
RECURRING_MIN_FREQUENCY = 2        # must be seen ≥2 times
EMERGING_MIN_FREQUENCY  = 5        # OR ≥5 total observations
EMERGING_MIN_ENVS       = 3        # OR ≥3 distinct environments
CANDIDATE_MIN_FREQUENCY = 10       # AND ≥10 observations
CANDIDATE_MIN_ENVS      = 3        # AND ≥3 distinct environments


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Invariant keywords that indicate low-value noise patterns (consent banners, modals)
_LOW_VALUE_PATTERNS = frozenset({
    "accept", "decline", "cookie", "consent", "banner", "modal",
    "dismiss", "close", "captcha", "popup", "overlay",
})


# ── EvidenceEntry ─────────────────────────────────────────────────────────────

@dataclass
class EvidenceEntry:
    """One piece of evidence for a hypothesis observation."""
    env_key: str
    source: str              # "exploration", "replay", "compilation", etc.
    timestamp: datetime = field(default_factory=_utc_now)
    context_hint: str = ""   # e.g. template name, step label, site category
    outcome: str = ""        # "success", "failure", "partial"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "EvidenceEntry":
        d = dict(d)
        if isinstance(d.get("timestamp"), str):
            d["timestamp"] = datetime.fromisoformat(d["timestamp"])
        d.setdefault("context_hint", "")
        d.setdefault("outcome", "")
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})  # type: ignore[attr-defined]


# ── CapabilityHypothesis ──────────────────────────────────────────────────────

@dataclass
class CapabilityHypothesis:
    """A capability pattern awaiting promotion to CapabilityRecord.

    Fields
    ──────
    hypothesis_id       UUID string. Stable identity for this hypothesis object.
    invariant_hash      16-char hex of SHA-256(sorted invariants). Shared key with
                        CapabilityRecord when promoted. Content-addressed.
    invariants          Sorted list of invariant intent strings (same as InvariantGraph).
    status              Current lifecycle status (see HypothesisStatus).
    first_seen          UTC timestamp of first observation.
    last_seen           UTC timestamp of most recent observation.
    frequency           Total number of times this pattern was observed.
    environments        Distinct environment keys where it was observed.
    evidence            Last N EvidenceEntry records (capped at 50 to bound storage).
    transfer_attempts   Number of times attempted on an environment not in training set.
    transfer_successes  Number of successful transfers.
    source              Where this hypothesis originated: "exploration", "replay", etc.
    promoted_capability_id  If PROMOTED, the invariant_hash of the resulting CapabilityRecord.
    refuted_reason      If REFUTED, a short explanation string.
    human_hint          Optional human-assigned label (annotation only, not identity).
    site_category       Category from SiteRegistry.category (populated when available).
    """
    hypothesis_id: str
    invariant_hash: str
    invariants: List[str]
    status: str = HypothesisStatus.HYPOTHESIS
    first_seen: datetime = field(default_factory=_utc_now)
    last_seen: datetime = field(default_factory=_utc_now)
    frequency: int = 1
    environments: List[str] = field(default_factory=list)
    evidence: List[EvidenceEntry] = field(default_factory=list)
    transfer_attempts: int = 0
    transfer_successes: int = 0
    source: str = "exploration"
    promoted_capability_id: Optional[str] = None
    refuted_reason: Optional[str] = None
    human_hint: Optional[str] = None
    site_category: Optional[str] = None
    importance_score: float = 1.0   # weighted rank; updated by compute_importance()

    # ── Importance scoring ────────────────────────────────────────────────────

    def compute_importance(self) -> float:
        """Compute and cache importance_score (0.1–2.0).

        Higher = more likely to be a genuine transferable capability.
        Lower  = cookie banners, modals, and other noise patterns.
        """
        inv_lower = [i.lower() for i in self.invariants]
        noise_count = sum(
            1 for inv in inv_lower
            if any(kw in inv for kw in _LOW_VALUE_PATTERNS)
        )
        noise_ratio = noise_count / max(len(inv_lower), 1)

        transfer_diversity = len(self.environments) / max(self.frequency, 1)
        transfer_bonus = 0.5 if self.transfer_successes > 0 else 0.0

        score = (1.0 * (1 - 0.7 * noise_ratio) * (0.5 + 1.5 * transfer_diversity)
                 + transfer_bonus)
        self.importance_score = max(0.1, min(2.0, round(score, 3)))
        return self.importance_score

    # ── Observation recording ─────────────────────────────────────────────────

    def observe(
        self,
        env_key: str,
        source: str = "exploration",
        context_hint: str = "",
        outcome: str = "",
    ) -> None:
        """Record one new observation of this hypothesis.

        Increments frequency, updates environments, appends evidence,
        then calls _try_graduate() to check if thresholds are met.
        """
        if self.status in (HypothesisStatus.PROMOTED, HypothesisStatus.REFUTED):
            return  # terminal states accept no further observations

        self.frequency += 1
        self.last_seen = _utc_now()

        if env_key and env_key not in self.environments:
            self.environments.append(env_key)

        entry = EvidenceEntry(
            env_key=env_key,
            source=source,
            context_hint=context_hint,
            outcome=outcome,
        )
        self.evidence.append(entry)
        # Cap evidence list at 50 entries (keep most recent)
        if len(self.evidence) > 50:
            self.evidence = self.evidence[-50:]

        self._try_graduate()

    def record_transfer_attempt(self, success: bool) -> None:
        """Record a cross-environment transfer attempt."""
        self.transfer_attempts += 1
        if success:
            self.transfer_successes += 1
        self.last_seen = _utc_now()

    # ── Lifecycle transitions ─────────────────────────────────────────────────

    def _try_graduate(self) -> None:
        """Auto-advance status based on thresholds. Never downgrades."""
        if self.status in (HypothesisStatus.PROMOTED, HypothesisStatus.REFUTED):
            return

        n_envs = len(self.environments)
        freq   = self.frequency

        if self.status == HypothesisStatus.HYPOTHESIS:
            if freq >= RECURRING_MIN_FREQUENCY:
                self.status = HypothesisStatus.RECURRING

        if self.status == HypothesisStatus.RECURRING:
            if freq >= EMERGING_MIN_FREQUENCY or n_envs >= EMERGING_MIN_ENVS:
                self.status = HypothesisStatus.EMERGING

        if self.status == HypothesisStatus.EMERGING:
            if freq >= CANDIDATE_MIN_FREQUENCY and n_envs >= CANDIDATE_MIN_ENVS:
                self.status = HypothesisStatus.CANDIDATE

    def promote(self, capability_id: Optional[str] = None) -> None:
        """Mark as PROMOTED (CapabilityRecord written). Idempotent."""
        if self.status == HypothesisStatus.REFUTED:
            return
        self.status = HypothesisStatus.PROMOTED
        self.promoted_capability_id = capability_id or self.invariant_hash
        self.last_seen = _utc_now()

    def refute(self, reason: str = "") -> None:
        """Mark as REFUTED. Idempotent; a refuted hypothesis stays refuted."""
        if self.status == HypothesisStatus.PROMOTED:
            return
        self.status = HypothesisStatus.REFUTED
        self.refuted_reason = reason or "manually refuted"
        self.last_seen = _utc_now()

    def force_advance(self, target_status: str) -> None:
        """Manually advance status (for Human Intervention Loop).

        Only advances, never retreats. Useful when a human confirms a pattern
        is meaningful before automated thresholds are reached.
        Allowed transitions: HYPOTHESIS→RECURRING→EMERGING→CANDIDATE
        """
        allowed = [
            HypothesisStatus.HYPOTHESIS,
            HypothesisStatus.RECURRING,
            HypothesisStatus.EMERGING,
            HypothesisStatus.CANDIDATE,
        ]
        if target_status not in allowed:
            return
        if self.status in (HypothesisStatus.PROMOTED, HypothesisStatus.REFUTED):
            return
        current_rank = allowed.index(self.status) if self.status in allowed else 0
        target_rank  = allowed.index(target_status)
        if target_rank > current_rank:
            self.status = target_status
            self.last_seen = _utc_now()

    # ── Transfer rate ─────────────────────────────────────────────────────────

    @property
    def transfer_rate(self) -> Optional[float]:
        """Fraction of transfer attempts that succeeded. None if no attempts."""
        if self.transfer_attempts == 0:
            return None
        return round(self.transfer_successes / self.transfer_attempts, 4)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "hypothesis_id":          self.hypothesis_id,
            "invariant_hash":         self.invariant_hash,
            "invariants":             list(self.invariants),
            "status":                 self.status,
            "first_seen":             self.first_seen.isoformat(),
            "last_seen":              self.last_seen.isoformat(),
            "frequency":              self.frequency,
            "environments":           list(self.environments),
            "evidence":               [e.to_dict() for e in self.evidence],
            "transfer_attempts":      self.transfer_attempts,
            "transfer_successes":     self.transfer_successes,
            "source":                 self.source,
            "promoted_capability_id": self.promoted_capability_id,
            "refuted_reason":         self.refuted_reason,
            "human_hint":             self.human_hint,
            "site_category":          self.site_category,
            "importance_score":       self.importance_score,
        }
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "CapabilityHypothesis":
        d = dict(d)
        for ts_field in ("first_seen", "last_seen"):
            if isinstance(d.get(ts_field), str):
                d[ts_field] = datetime.fromisoformat(d[ts_field])
        raw_evidence = d.pop("evidence", [])
        d.setdefault("transfer_attempts", 0)
        d.setdefault("transfer_successes", 0)
        d.setdefault("source", "exploration")
        d.setdefault("promoted_capability_id", None)
        d.setdefault("refuted_reason", None)
        d.setdefault("human_hint", None)
        d.setdefault("site_category", None)
        d.setdefault("importance_score", 1.0)
        known = {
            "hypothesis_id", "invariant_hash", "invariants", "status",
            "first_seen", "last_seen", "frequency", "environments",
            "transfer_attempts", "transfer_successes", "source",
            "promoted_capability_id", "refuted_reason", "human_hint",
            "site_category", "importance_score",
        }
        obj = cls(**{k: v for k, v in d.items() if k in known})
        obj.evidence = [EvidenceEntry.from_dict(e) for e in raw_evidence]
        return obj


# ── Factory ───────────────────────────────────────────────────────────────────

def make_hypothesis(
    invariants: List[str],
    env_key: str = "",
    source: str = "exploration",
    context_hint: str = "",
    outcome: str = "",
    site_category: Optional[str] = None,
) -> "CapabilityHypothesis":
    """Create a new CapabilityHypothesis from a set of invariant intents.

    Computes invariant_hash from the canonical sorted join (same algorithm as
    InvariantGraph.invariant_hash) so hypotheses and records share the same key.
    """
    canonical = "|".join(sorted(invariants))
    inv_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    hyp = CapabilityHypothesis(
        hypothesis_id=str(uuid.uuid4()),
        invariant_hash=inv_hash,
        invariants=sorted(invariants),
        source=source,
        site_category=site_category,
        environments=[env_key] if env_key else [],
    )
    if env_key or context_hint or outcome:
        entry = EvidenceEntry(
            env_key=env_key,
            source=source,
            context_hint=context_hint,
            outcome=outcome,
        )
        hyp.evidence = [entry]
    return hyp
