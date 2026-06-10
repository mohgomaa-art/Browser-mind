"""ContractVerifier — runtime verification of task completion against declared contracts.

Promoted from `scripts/experiments/p8a_task_contracts.py` to the runtime so every
replay run produces a binary "did the goal complete?" answer that can flow into
the OutcomeLedger as a `contract_verification` record.

Three sources of contracts are checked, in priority order:
  1. A contract registered programmatically via `register_contract(...)`.
  2. A YAML file at <root>/browsermind_core/runtime/contracts/<key>.yaml.
  3. The legacy P8A contracts in scripts/experiments/p8a_task_contracts.CONTRACTS.

Lookup keys tried per replay (first match wins):
  - the WorkflowTemplate name
  - the WorkflowTemplate.metadata['contract_id'] if set
  - the environment_instance key

Conditions supported (matches the P8A schema so nothing is lost):
  - url_contains:       target=substring
  - element_visible:    target=CSS/XPath selector
  - element_text_contains: target=selector, value=text (case-insensitive)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SuccessCondition:
    kind: str
    target: str
    value: str = ""
    label: str = ""


@dataclass
class TaskSuccessContract:
    task_id: str
    description: str
    rationale: str
    conditions: List[SuccessCondition] = field(default_factory=list)


_RUNTIME_REGISTRY: Dict[str, TaskSuccessContract] = {}


def register_contract(contract: TaskSuccessContract) -> None:
    """Register a contract in-memory (highest priority)."""
    _RUNTIME_REGISTRY[contract.task_id] = contract


def _load_yaml_contract(key: str, root: Path) -> Optional[TaskSuccessContract]:
    yaml_path = root / "browsermind_core" / "runtime" / "contracts" / f"{key}.yaml"
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
        SuccessCondition(
            kind=c.get("kind", ""),
            target=c.get("target", ""),
            value=c.get("value", ""),
            label=c.get("label", ""),
        )
        for c in (data.get("conditions") or [])
    ]
    return TaskSuccessContract(
        task_id=data.get("task_id", key),
        description=data.get("description", ""),
        rationale=data.get("rationale", ""),
        conditions=conditions,
    )


def _load_legacy_p8a_contract(key: str) -> Optional[TaskSuccessContract]:
    try:
        from scripts.experiments.p8a_task_contracts import CONTRACTS as _LEGACY  # type: ignore
    except Exception:
        return None
    legacy = _LEGACY.get(key)
    if legacy is None:
        return None
    conditions = [
        SuccessCondition(kind=c.kind, target=c.target, value=c.value, label=c.label)
        for c in legacy.conditions
    ]
    return TaskSuccessContract(
        task_id=legacy.task_id,
        description=legacy.description,
        rationale=legacy.rationale,
        conditions=conditions,
    )


def lookup_contract(*keys: str, root: Optional[Path] = None) -> Optional[TaskSuccessContract]:
    """Try each key against runtime registry, then YAML, then legacy P8A."""
    root = root or Path(__file__).resolve().parents[2]
    for key in keys:
        if not key:
            continue
        if key in _RUNTIME_REGISTRY:
            return _RUNTIME_REGISTRY[key]
        c = _load_yaml_contract(key, root)
        if c is not None:
            return c
        c = _load_legacy_p8a_contract(key)
        if c is not None:
            return c
    return None


class ContractVerifier:
    """Evaluates a task's declared contract against the live browser state."""

    async def verify(
        self,
        page,
        contract: Optional[TaskSuccessContract] = None,
        *,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if contract is None and task_id is not None:
            contract = lookup_contract(task_id)
        if contract is None:
            return {
                "goal_completed": False,
                "success_contract": None,
                "contract_evidence": {"error": "no contract registered"},
                "validator_result": False,
            }

        try:
            current_url = page.url
        except Exception:
            current_url = ""

        evidence_conditions: Dict[str, Any] = {}
        all_satisfied = bool(contract.conditions)
        for cond in contract.conditions:
            satisfied = await self._evaluate(page, cond, current_url)
            evidence_conditions[cond.label or f"{cond.kind}:{cond.target}"] = {
                "kind": cond.kind,
                "target": cond.target,
                "satisfied": satisfied,
            }
            if not satisfied:
                all_satisfied = False

        return {
            "goal_completed": all_satisfied,
            "success_contract": {
                "task_id": contract.task_id,
                "description": contract.description,
                "rationale": contract.rationale,
                "conditions": [
                    {"kind": c.kind, "target": c.target, "label": c.label}
                    for c in contract.conditions
                ],
            },
            "contract_evidence": {
                "url_at_verification": current_url,
                "conditions": evidence_conditions,
            },
            "validator_result": all_satisfied,
        }

    async def _evaluate(self, page, cond: SuccessCondition, current_url: str) -> bool:
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
