"""
Phase V1.2 — Task Value Estimation
task_value = capability_prior × workflow_potential × cross_site_value × completion_probability

Not role-weighted. Capability prior is a prior only — modulated by executability signals.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from training.capability_taxonomy import load_taxonomy, rank_capabilities

GENERIC_FAMILIES = frozenset(
    {"generic_interactive", "generic_page", "empty_page", "root_fallback"}
)
VAGUE_NAMES = frozenset(
    {"link", "click here", "button", "submit", "more", "menu", "item", ""}
)


def learning_stage(capability_id: str) -> str:
    tax = load_taxonomy()
    phases = tax.get("curriculum_phases", {})
    if capability_id in phases.get("v1_core", []):
        return "core"
    if capability_id in phases.get("v1_extended", []):
        return "extended"
    if capability_id in phases.get("deprioritized", []):
        return "skip"
    if capability_id == "other":
        return "skip"
    return "extended"


def _workflow_potential(
    capability_id: str,
    spec: Dict[str, Any],
    *,
    role: str,
    state_family: str,
    name: str,
    match_strength: float,
) -> float:
    score = 0.45 + 0.35 * min(match_strength, 1.0)

    typical = spec.get("typical_state_families", [])
    if state_family in typical:
        score += 0.25
    elif state_family in GENERIC_FAMILIES:
        score -= 0.25

    signals = spec.get("semantic_signals", {})
    if role in signals.get("role_affinity", []):
        score += 0.15

    name_l = name.lower().strip()
    if name_l in VAGUE_NAMES or len(name_l) < 3:
        score -= 0.2

    # Capability/state mismatch penalties
    if capability_id == "upload" and state_family in ("navigation_hub", "article_page", "legal"):
        score -= 0.35
    if capability_id in ("auth_recovery", "account_creation") and state_family == "landing_page":
        if "password" not in name_l and role != "textbox":
            score -= 0.2

    return max(0.1, min(round(score, 4), 1.0))


def _cross_site_value(capability_id: str, spec: Dict[str, Any]) -> float:
    if not spec.get("cross_site", False):
        return 0.5
    if capability_id in ("legal", "marketing"):
        return 0.1
    if capability_id == "other":
        return 0.4
    prior = float(spec.get("capability_prior", 0.5))
    return round(0.85 + 0.1 * prior, 4) if prior >= 0.8 else round(0.7 + 0.2 * prior, 4)


def _completion_probability(
    capability_id: str,
    *,
    role: str,
    name: str,
    state_family: str,
    node: Optional[Dict[str, Any]],
    ax_graph: Optional[Dict[str, Any]],
) -> float:
    score = 0.85

    if node is not None:
        if node.get("disabled"):
            score -= 0.5
        if node.get("visible") is False:
            score -= 0.4

    name_l = name.lower().strip()
    if name_l in VAGUE_NAMES:
        score -= 0.25

    if state_family in GENERIC_FAMILIES:
        score -= 0.35

    # Auth without password field in graph → low completion for auth capabilities
    if capability_id in ("auth_recovery", "account_creation") and ax_graph:
        has_pw = any(
            "password" in n.get("name", "").lower()
            for n in ax_graph.get("nodes", [])
            if n.get("role") in ("textbox", "combobox")
        )
        if not has_pw and role != "textbox":
            score -= 0.4

    if capability_id == "upload" and role == "link":
        score -= 0.15  # hidden file inputs often exposed via button

    return max(0.1, min(round(score, 4), 1.0))


def estimate_task_value(
    target: str,
    *,
    role: str = "",
    state_family: str = "",
    opportunity_type: str = "interaction",
    node: Optional[Dict[str, Any]] = None,
    ax_graph: Optional[Dict[str, Any]] = None,
    heading_context: Optional[List[str]] = None,
    capability_id: Optional[str] = None,
    zone_texts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Returns capability assignment, task_value, factor breakdown, learning_stage.
    """
    ranked = rank_capabilities(
        target,
        role=role,
        state_family=state_family,
        opportunity_type=opportunity_type,
        heading_context=heading_context,
        zone_texts=zone_texts,
    )
    best_id, best_strength, cap_confidence = ranked[0]
    cap_id = capability_id or best_id

    tax = load_taxonomy()
    spec = tax["capabilities"].get(cap_id, tax["capabilities"]["other"])
    prior = float(spec.get("capability_prior", 0.4))

    wf = _workflow_potential(
        cap_id, spec, role=role, state_family=state_family, name=target, match_strength=best_strength
    )
    csv = _cross_site_value(cap_id, spec)
    cp = _completion_probability(
        cap_id,
        role=role,
        name=target,
        state_family=state_family,
        node=node,
        ax_graph=ax_graph,
    )

    task_value = round(prior * wf * csv * cp, 4)

    return {
        "capability": cap_id,
        "capability_confidence": round(cap_confidence, 4),
        "capability_runner_up": ranked[1][0] if len(ranked) > 1 else None,
        "capability_match_strength": round(best_strength, 4),
        "learning_stage": learning_stage(cap_id),
        "task_value": task_value,
        "task_value_factors": {
            "capability_prior": prior,
            "workflow_potential": wf,
            "cross_site_value": csv,
            "completion_probability": cp,
        },
        "capability_ranking_top3": [
            {"capability": c, "match_strength": round(s, 4)} for c, s, _ in ranked[:3]
        ],
    }


def compose_quality_score(
    task_value: float,
    *,
    actionability: float,
    confidence: float,
    rarity: float,
) -> float:
    """V1.2 quality — no role learnability."""
    return task_value * actionability * confidence * rarity
