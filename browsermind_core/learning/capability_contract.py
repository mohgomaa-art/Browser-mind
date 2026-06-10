"""CapabilityContract + CapabilityVerifier — capability-level state transition validation.

Difference from TaskSuccessContract / ContractVerifier:
  - TaskSuccessContract validates the WORKFLOW terminal state (did the whole goal complete?).
  - CapabilityContract validates a MID-EXECUTION state transition: after a specific
    capability pattern ran, did the expected page state change occur?

Keying
──────
Contracts are keyed by invariant_hash (16-char hex), not by workflow template name.
This means the same contract applies whenever the same capability pattern fires,
regardless of which workflow or environment produced it.

Storage
───────
YAML files at: <root>/browsermind_core/learning/capability_contracts/<hash16>.yaml
In-memory registry: register_capability_contract().

YAML schema (all fields optional except invariant_hash):
  invariant_hash: <16-char hex>
  description: "After auth capability: session cookie set"
  conditions:
    - kind: url_contains
      target: /dashboard
      label: redirected_to_dashboard
    - kind: element_visible
      target: "[data-testid='user-avatar']"
      label: user_avatar_present
    - kind: element_text_contains
      target: ".welcome-message"
      value: "Welcome"
      label: welcome_visible

Condition kinds (same as ContractVerifier):
  url_contains, element_visible, element_text_contains
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class CapabilityCondition:
    kind: str
    target: str
    value: str = ""
    label: str = ""


@dataclass
class CapabilityContract:
    """State transition contract for a capability keyed by invariant_hash."""
    invariant_hash: str
    description: str = ""
    conditions: List[CapabilityCondition] = field(default_factory=list)


_CAPABILITY_CONTRACT_REGISTRY: Dict[str, CapabilityContract] = {}


def register_capability_contract(contract: CapabilityContract) -> None:
    """Register a CapabilityContract in-memory (highest priority)."""
    _CAPABILITY_CONTRACT_REGISTRY[contract.invariant_hash] = contract


def _load_yaml_capability_contract(
    invariant_hash: str, root: Path
) -> Optional[CapabilityContract]:
    yaml_path = (
        root
        / "browsermind_core"
        / "learning"
        / "capability_contracts"
        / f"{invariant_hash}.yaml"
    )
    if not yaml_path.exists():
        return None
    try:
        import yaml  # type: ignore
    except ImportError:
        return None
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    conditions = [
        CapabilityCondition(
            kind=c.get("kind", ""),
            target=c.get("target", ""),
            value=c.get("value", ""),
            label=c.get("label", ""),
        )
        for c in (data.get("conditions") or [])
    ]
    return CapabilityContract(
        invariant_hash=data.get("invariant_hash", invariant_hash),
        description=data.get("description", ""),
        conditions=conditions,
    )


def lookup_capability_contract(
    invariant_hash: str, *, root: Optional[Path] = None
) -> Optional[CapabilityContract]:
    """Look up a CapabilityContract for the given invariant_hash.

    Search order: in-memory registry → YAML file.
    Returns None if no contract is registered for this hash.
    """
    if not invariant_hash:
        return None
    if invariant_hash in _CAPABILITY_CONTRACT_REGISTRY:
        return _CAPABILITY_CONTRACT_REGISTRY[invariant_hash]
    root = root or Path(__file__).resolve().parents[2]
    return _load_yaml_capability_contract(invariant_hash, root)


class CapabilityVerifier:
    """Evaluates a CapabilityContract against the live browser page.

    Called mid-execution, after the steps whose invariant set matches the
    CapabilityRecord's invariants have all completed. The page is expected to
    be in the post-capability state (not necessarily the terminal workflow state).

    Returns a dict with:
      capability_hash     The invariant_hash being tested.
      transition_verified bool — True iff all conditions satisfied.
      evidence            Per-condition results.
      url_at_check        URL at time of verification.
    """

    async def verify(
        self, page, contract: CapabilityContract
    ) -> Dict[str, Any]:
        try:
            current_url = page.url if page is not None else ""
        except Exception:
            current_url = ""

        evidence: Dict[str, Any] = {}
        all_satisfied = bool(contract.conditions)

        for cond in contract.conditions:
            satisfied = await self._evaluate(page, cond, current_url)
            label = cond.label or f"{cond.kind}:{cond.target}"
            evidence[label] = {
                "kind": cond.kind,
                "target": cond.target,
                "satisfied": satisfied,
            }
            if not satisfied:
                all_satisfied = False

        return {
            "capability_hash": contract.invariant_hash,
            "transition_verified": all_satisfied,
            "evidence": evidence,
            "url_at_check": current_url,
        }

    async def _evaluate(
        self, page, cond: CapabilityCondition, current_url: str
    ) -> bool:
        if page is None:
            return False
        try:
            if cond.kind == "url_contains":
                return cond.target in current_url
            if cond.kind == "element_visible":
                el = page.locator(cond.target).first
                return await el.is_visible(timeout=2000)
            if cond.kind == "element_text_contains":
                el = page.locator(cond.target).first
                if not await el.is_visible(timeout=2000):
                    return False
                text = await el.inner_text()
                return cond.value.lower() in text.lower()
        except Exception:
            return False
        return False
