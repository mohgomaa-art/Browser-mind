from __future__ import annotations

import json
import os
import tempfile
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from browsermind_core.ontology.semantic_state import SemanticState


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Edge
# ---------------------------------------------------------------------------

@dataclass
class StateTransitionEdge:
    """
    A directed edge in the SSTG.

    from_state / to_state are SemanticState.fingerprint strings
    (e.g. "unauthenticated:landing").

    capability_hash is either a CapabilityRecord.invariant_hash or a
    synthetic key like "click:button" used before a full CapabilityRecord
    exists.
    """
    from_state: str
    to_state: str
    capability_hash: str
    env_keys: List[str] = field(default_factory=list)
    observation_count: int = 0
    confidence: float = 0.0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_state": self.from_state,
            "to_state": self.to_state,
            "capability_hash": self.capability_hash,
            "env_keys": list(self.env_keys),
            "observation_count": self.observation_count,
            "confidence": self.confidence,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StateTransitionEdge":
        e = cls(
            from_state=d["from_state"],
            to_state=d["to_state"],
            capability_hash=d["capability_hash"],
            env_keys=d.get("env_keys", []),
            observation_count=d.get("observation_count", 0),
            confidence=d.get("confidence", 0.0),
        )
        for ts in ("first_seen", "last_seen"):
            v = d.get(ts)
            if isinstance(v, str):
                try:
                    setattr(e, ts, datetime.fromisoformat(v))
                except (ValueError, TypeError):
                    pass
        return e


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

@dataclass
class SemanticStateTransitionGraph:
    """
    System-wide directed graph of semantic state transitions.

    Nodes  — SemanticState fingerprints (e.g. "authenticated:search_results")
    Edges  — StateTransitionEdge objects linking (from, to) via a capability

    Persisted at: {store_dir}/sstg.json  (single system-wide file)
    """

    nodes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    edges: List[StateTransitionEdge] = field(default_factory=list)
    _path: Optional[str] = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_observation(
        self,
        pre: SemanticState,
        post: SemanticState,
        capability_hash: str,
        env_key: str = "",
    ) -> None:
        """Record that capability_hash transitions pre→post on env_key."""
        # Skip identity transitions (state didn't change)
        if pre.fingerprint == post.fingerprint:
            return

        # Upsert nodes
        if pre.fingerprint not in self.nodes:
            self.nodes[pre.fingerprint] = pre.to_dict()
        if post.fingerprint not in self.nodes:
            self.nodes[post.fingerprint] = post.to_dict()

        # Upsert edge
        edge = self._find_edge(pre.fingerprint, post.fingerprint, capability_hash)
        if edge is None:
            edge = StateTransitionEdge(
                from_state=pre.fingerprint,
                to_state=post.fingerprint,
                capability_hash=capability_hash,
                first_seen=_utc_now(),
            )
            self.edges.append(edge)

        if env_key and env_key not in edge.env_keys:
            edge.env_keys.append(env_key)

        edge.observation_count += 1
        # Confidence saturates at 1.0 after 5 corroborating observations
        edge.confidence = min(1.0, edge.observation_count / 5.0)
        edge.last_seen = _utc_now()

    def _find_edge(
        self,
        from_state: str,
        to_state: str,
        capability_hash: str,
    ) -> Optional[StateTransitionEdge]:
        for e in self.edges:
            if (
                e.from_state == from_state
                and e.to_state == to_state
                and e.capability_hash == capability_hash
            ):
                return e
        return None

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def paths_to(
        self,
        target: str,
        max_depth: int = 5,
    ) -> List[List[StateTransitionEdge]]:
        """BFS: return all edge-paths (as lists of edges) that lead to target.

        Useful for planning: "what sequence of capabilities gets me to
        authenticated:dashboard from unauthenticated:landing?"
        """
        if target not in self.nodes:
            return []

        # Build reverse adjacency for BFS toward the target
        reverse: Dict[str, List[StateTransitionEdge]] = {}
        for e in self.edges:
            reverse.setdefault(e.to_state, []).append(e)

        # BFS from target backward
        found: List[List[StateTransitionEdge]] = []
        queue: deque = deque()  # (current_state, path_so_far)
        queue.append((target, []))
        visited_with_depth: Dict[str, int] = {target: 0}

        while queue:
            current, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            for edge in reverse.get(current, []):
                src = edge.from_state
                new_path = [edge] + path
                if src == target:
                    continue  # skip trivial loops
                found.append(new_path)
                depth = len(new_path)
                if depth < max_depth and visited_with_depth.get(src, max_depth + 1) > depth:
                    visited_with_depth[src] = depth
                    queue.append((src, new_path))

        return found

    def gaps(self) -> List[str]:
        """Return node fingerprints with no outgoing edges (exploration dead-ends)."""
        has_outgoing = {e.from_state for e in self.edges}
        return [fp for fp in self.nodes if fp not in has_outgoing]

    def node_count(self) -> int:
        return len(self.nodes)

    def edge_count(self) -> int:
        return len(self.edges)

    # ------------------------------------------------------------------
    # Persistence — atomic write, matches LocalJSONPersistenceProvider pattern
    # ------------------------------------------------------------------

    def save(self, path: Optional[str] = None) -> None:
        target = path or self._path
        if not target:
            return
        os.makedirs(os.path.dirname(target), exist_ok=True)
        payload = {
            "nodes": self.nodes,
            "edges": [e.to_dict() for e in self.edges],
        }
        data = json.dumps(payload, ensure_ascii=False, indent=2)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(target), suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp_path, target)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @classmethod
    def load(cls, path: str) -> "SemanticStateTransitionGraph":
        """Load from disk or return an empty graph if the file doesn't exist."""
        if not os.path.exists(path):
            g = cls()
            g._path = path
            return g
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
            g = cls(
                nodes=payload.get("nodes", {}),
                edges=[
                    StateTransitionEdge.from_dict(e)
                    for e in payload.get("edges", [])
                ],
            )
            g._path = path
            return g
        except Exception:
            # Corrupted file: return empty graph rather than crashing
            g = cls()
            g._path = path
            return g
