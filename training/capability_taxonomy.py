"""
BrowserMind — Capability Taxonomy v1.25
Boundary-aware classification: positive_signals + negative_signals + context inference.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

_WORD_BOUNDARY_SHORT = 6  # tokens shorter than this require \\b match

WORKFLOW_CAPABILITIES = frozenset(
    {"upload", "job_application", "checkout", "content_creation"}
)
DEFAULT_WORKFLOW_MARKER_WEIGHT = 0.2
DEFAULT_WORKFLOW_THRESHOLD = 0.55

_TAXONOMY_PATH = os.path.join(os.path.dirname(__file__), "capability_taxonomy_v1.json")

MIN_MATCH_STRENGTH = 0.20
AMBIGUITY_RATIO = 0.72

_NAV_FAMILIES = frozenset({"navigation_hub", "landing_page", "article_page", "content_feed"})
_FORM_FAMILIES = frozenset({"multi_field_form", "dialog_form", "checkout_form", "signup_form", "login_form"})
_WAYFINDING_SFS = _NAV_FAMILIES | frozenset(
    {"search_interface", "action_toolbar", "generic_interactive"}
)
_EXPLICIT_CAPS = (
    "marketing", "legal", "auth_recovery", "account_creation", "upload",
    "search", "filter", "content_creation", "job_application", "checkout", "settings",
)


def _has_explicit_capability(
    name: str,
    min_score: float = 0.55,
    *,
    zone_texts: Optional[List[str]] = None,
) -> bool:
    for cap in _EXPLICIT_CAPS:
        if _score_positive(name, get_boundary(cap).get("positive_signals", [])) >= min_score:
            return True
    if zone_texts:
        for cap in WORKFLOW_CAPABILITIES:
            if workflow_capability_active(cap, zone_texts):
                return True
    return False


def _workflow_blocks_wayfinding(zone_texts: Optional[List[str]]) -> bool:
    if not zone_texts:
        return False
    return any(workflow_capability_active(cap, zone_texts) for cap in WORKFLOW_CAPABILITIES)


def _infer_wayfinding(
    name: str,
    role: str,
    state_family: str,
    *,
    zone_texts: Optional[List[str]] = None,
) -> Optional[Tuple[str, float]]:
    """Default bucket for chrome links/buttons without task-specific language."""
    if role not in ("link", "button", "menuitem"):
        return None
    if state_family not in _WAYFINDING_SFS:
        return None
    if _workflow_blocks_wayfinding(zone_texts):
        return None
    if _has_explicit_capability(name, zone_texts=zone_texts):
        return None
    if state_family == "search_interface":
        if _score_positive(name, get_boundary("filter").get("positive_signals", [])) >= 0.55:
            return ("filter", 0.5)
        if _score_positive(name, get_boundary("search").get("positive_signals", [])) >= 0.55:
            return ("search", 0.5)
    if state_family == "action_toolbar":
        if _score_positive(name, get_boundary("filter").get("positive_signals", [])) >= 0.5:
            return ("filter", 0.48)
    return ("navigation", 0.36)


@lru_cache(maxsize=1)
def load_taxonomy() -> Dict[str, Any]:
    with open(_TAXONOMY_PATH, encoding="utf-8") as f:
        return json.load(f)


def capability_ids() -> List[str]:
    return [c for c in load_taxonomy()["capabilities"] if c != "other"]


def capability_prior(capability_id: str) -> float:
    spec = load_taxonomy()["capabilities"].get(capability_id) or load_taxonomy()["capabilities"]["other"]
    return float(spec.get("capability_prior", 0.4))


def curriculum_core() -> List[str]:
    return list(load_taxonomy().get("curriculum_phases", {}).get("v1_core", []))


def get_boundary(capability_id: str) -> Dict[str, Any]:
    spec = load_taxonomy()["capabilities"].get(capability_id, {})
    return spec.get("boundary", {})


def get_discovery_spec(capability_id: str) -> Dict[str, Any]:
    spec = load_taxonomy()["capabilities"].get(capability_id, {})
    disc = spec.get("discovery")
    if disc:
        return disc
    boundary = spec.get("boundary", {})
    return {
        "signals": list(boundary.get("positive_signals", [])),
        "negative_signals": list(boundary.get("negative_signals", [])),
        "required_context": {
            "state_families": list(spec.get("typical_state_families", [])),
            "roles": list(spec.get("semantic_signals", {}).get("role_affinity", [])),
        },
        "workflow_markers": list(boundary.get("positive_signals", [])),
    }


def score_workflow_markers(capability_id: str, texts: List[str]) -> Tuple[float, List[str]]:
    """DISC-2: aggregate workflow evidence across a form/region (not single-node)."""
    disc = get_discovery_spec(capability_id)
    weight = float(disc.get("workflow_marker_weight", DEFAULT_WORKFLOW_MARKER_WEIGHT))
    matched: List[str] = []
    seen: set = set()

    for raw in texts:
        name = (raw or "").lower().strip()
        if not name:
            continue
        if _blocked_by_negative(name, disc.get("negative_signals", [])):
            continue
        for phrase in disc.get("workflow_markers", []) + disc.get("signals", []):
            p = phrase.lower().strip()
            if not p or p in seen:
                continue
            if _phrase_matches(name, p):
                seen.add(p)
                matched.append(p)

    return round(min(len(matched) * weight, 1.0), 4), matched


def workflow_capability_active(capability_id: str, texts: List[str]) -> bool:
    disc = get_discovery_spec(capability_id)
    threshold = float(disc.get("workflow_score_threshold", DEFAULT_WORKFLOW_THRESHOLD))
    score, _ = score_workflow_markers(capability_id, texts)
    return score >= threshold


def _phrase_matches(name: str, phrase: str) -> bool:
    if len(phrase) < _WORD_BOUNDARY_SHORT and " " not in phrase:
        return re.search(rf"\b{re.escape(phrase)}\b", name) is not None
    return phrase in name


def _score_positive(name: str, positives: List[str]) -> float:
    best = 0.0
    for phrase in positives:
        p = phrase.lower().strip()
        if not p:
            continue
        if _phrase_matches(name, p):
            words = len(p.split())
            best = max(best, 0.55 + 0.12 * min(words, 4))
    return min(best, 1.0)


def _blocked_by_negative(name: str, negatives: List[str]) -> bool:
    return any(n.lower() in name for n in negatives if n)


def _score_capability(
    cap_id: str,
    name: str,
    *,
    role: str,
    state_family: str,
    opportunity_type: str,
    heading_context: Optional[List[str]],
) -> float:
    spec = load_taxonomy()["capabilities"].get(cap_id, {})
    boundary = spec.get("boundary", {})
    positives = boundary.get("positive_signals", [])
    negatives = boundary.get("negative_signals", [])

    if _blocked_by_negative(name, negatives):
        return 0.0

    strength = _score_positive(name, positives)

    signals = spec.get("semantic_signals", {})
    if state_family in signals.get("state_family_match", []):
        strength = max(strength, 0.62)

    if opportunity_type == "extraction" and cap_id == "data_extraction":
        if role in signals.get("role_affinity", []):
            strength = max(strength, 0.78)

    if role in signals.get("role_affinity", []):
        strength = min(strength + 0.08, 1.0)

    if heading_context:
        for h in heading_context:
            hl = h.lower()
            for kw in signals.get("heading_keywords", []):
                if kw in hl:
                    strength = max(strength, 0.72)

    return strength


def _context_infer(
    name: str,
    role: str,
    state_family: str,
    opportunity_type: str,
    *,
    zone_texts: Optional[List[str]] = None,
) -> Optional[Tuple[str, float]]:
    """Returns (capability_id, strength) when boundary match is weak but context is strong."""
    if opportunity_type == "extraction":
        return ("data_extraction", 0.75)

    if state_family == "search_interface" and role in ("searchbox", "combobox", "textbox"):
        if "filter" not in name and "sort" not in name:
            return ("search", 0.52)

    if state_family in _FORM_FAMILIES:
        if zone_texts:
            for cap_id in WORKFLOW_CAPABILITIES:
                if workflow_capability_active(cap_id, zone_texts):
                    wf_score, _ = score_workflow_markers(cap_id, zone_texts + [name])
                    if wf_score >= MIN_MATCH_STRENGTH:
                        return (cap_id, wf_score)
        if role in ("textbox", "combobox", "checkbox", "button"):
            if "password" in name or "username" in name:
                return ("auth_recovery", 0.48)
            if state_family == "signup_form":
                return ("account_creation", 0.48)
            if state_family == "checkout_form":
                return ("checkout", 0.48)
            return ("multi_field_form", 0.45)

    wayfinding = _infer_wayfinding(name, role, state_family, zone_texts=zone_texts)
    if wayfinding:
        return wayfinding

    if state_family == "login_form":
        if role in ("link", "button", "menuitem"):
            if _phrase_matches(name, "terms") or _phrase_matches(name, "privacy") or "docs" in name:
                return ("legal", 0.5)
            if _has_explicit_capability(name, zone_texts=zone_texts):
                return None
            return ("navigation", 0.36)
        if role in ("button", "textbox") and not _has_explicit_capability(
            name, zone_texts=zone_texts
        ):
            return ("auth_recovery", 0.42)

    tax = load_taxonomy()
    for rule in tax.get("context_inference", {}).get("rules", []):
        sf = rule.get("if_state_family")
        if sf and state_family != sf:
            continue
        roles = rule.get("if_role_in")
        if roles and role not in roles:
            continue
        if rule.get("if_role") and role != rule["if_role"]:
            continue
        contains = rule.get("if_name_contains", [])
        if contains and not any(c in name for c in contains):
            continue
        return (rule["then"], 0.42)

    if state_family == "post_composer":
        return ("content_creation", 0.45)

    return None


def competition_scores(
    target: str,
    *,
    role: str = "",
    state_family: str = "",
    opportunity_type: str = "interaction",
    heading_context: Optional[List[str]] = None,
    zone_texts: Optional[List[str]] = None,
) -> Dict[str, float]:
    """
    DISC-2.5: raw per-capability scores (no wayfinding / context-inference override).
    Workflow caps combine node boundary score + zone workflow marker score via max().
    """
    name = target.lower().strip()
    tax = load_taxonomy()
    out: Dict[str, float] = {}

    for cap_id in tax.get("classification_order", []):
        if cap_id == "other":
            continue
        s = _score_capability(
            cap_id,
            name,
            role=role,
            state_family=state_family,
            opportunity_type=opportunity_type,
            heading_context=heading_context,
        )
        if zone_texts and cap_id in WORKFLOW_CAPABILITIES:
            wf_score, _ = score_workflow_markers(cap_id, zone_texts + [name])
            s = max(s, wf_score)
        if s > 0:
            out[cap_id] = round(s, 4)

    return out


def competition_winner(scores: Dict[str, float]) -> Tuple[str, float]:
    if not scores:
        return ("other", 0.0)
    cap_id, strength = max(scores.items(), key=lambda x: x[1])
    if strength < MIN_MATCH_STRENGTH:
        return ("other", strength)
    return (cap_id, strength)


def zone_competition_scores(
    *,
    zone_texts: List[str],
    state_family: str,
    nodes: List[Dict[str, Any]],
    heading_context: Optional[List[str]] = None,
) -> Dict[str, float]:
    """Aggregate zone-level competition: max(node scores, zone workflow scores) per capability."""
    tax = load_taxonomy()
    merged: Dict[str, float] = {}

    for cap_id in tax.get("classification_order", []):
        if cap_id == "other":
            continue
        best = 0.0
        if cap_id in WORKFLOW_CAPABILITIES and zone_texts:
            wf_score, _ = score_workflow_markers(cap_id, zone_texts)
            best = max(best, wf_score)
        for node in nodes:
            name = (node.get("name") or "").strip()
            role = (node.get("role") or "").lower()
            if not name:
                continue
            opp_type = (
                "interaction"
                if role
                in ("button", "link", "textbox", "checkbox", "searchbox", "combobox", "menuitem")
                else "extraction"
            )
            cs = competition_scores(
                name,
                role=role,
                state_family=state_family,
                opportunity_type=opp_type,
                heading_context=heading_context,
                zone_texts=zone_texts,
            )
            best = max(best, cs.get(cap_id, 0.0))
        if best > 0:
            merged[cap_id] = round(best, 4)

    return merged


def build_zone_text_map(
    ax_graph: Dict[str, Any],
    zones: List[Dict[str, Any]],
) -> Dict[int, List[str]]:
    """Map node idx → all AX names in the same interaction zone (workflow context)."""
    idx_to_texts: Dict[int, List[str]] = {}
    nodes_by_idx = {
        n["idx"]: n.get("name", "").strip()
        for n in ax_graph.get("nodes", [])
        if n.get("idx") is not None and n.get("name", "").strip()
    }
    for zone in zones:
        texts = [
            nodes_by_idx[i]
            for i in zone.get("node_idxs", [])
            if i in nodes_by_idx
        ]
        for i in zone.get("node_idxs", []):
            idx_to_texts[i] = texts
    return idx_to_texts


def rank_capabilities(
    target: str,
    *,
    role: str = "",
    state_family: str = "",
    opportunity_type: str = "interaction",
    heading_context: Optional[List[str]] = None,
    zone_texts: Optional[List[str]] = None,
) -> List[Tuple[str, float, float]]:
    name = target.lower().strip()
    tax = load_taxonomy()
    scores: Dict[str, float] = {}

    for cap_id in tax.get("classification_order", []):
        if cap_id == "other":
            continue
        s = _score_capability(
            cap_id, name, role=role, state_family=state_family,
            opportunity_type=opportunity_type, heading_context=heading_context,
        )
        if zone_texts and cap_id in WORKFLOW_CAPABILITIES:
            wf_score, _ = score_workflow_markers(cap_id, zone_texts + [name])
            s = max(s, wf_score)
        if s > 0:
            scores[cap_id] = s

    ranked = sorted(scores.items(), key=lambda x: -x[1])

    if not ranked or ranked[0][1] < MIN_MATCH_STRENGTH:
        inferred = _context_infer(
            name, role, state_family, opportunity_type, zone_texts=zone_texts
        )
        if inferred:
            cap_id, inf_strength = inferred
            return [(cap_id, inf_strength, 0.5)]
        return [("other", 0.0, 0.25)]

    # Boost with context when boundary match is marginal
    if ranked[0][1] < 0.45:
        inferred = _context_infer(
            name, role, state_family, opportunity_type, zone_texts=zone_texts
        )
        if inferred:
            cap_id, inf_strength = inferred
            if inf_strength > ranked[0][1]:
                ranked = [(cap_id, inf_strength)] + ranked

    # DISC-2: workflow-active region wins over navigation when node signal is weak
    if zone_texts and ranked[0][1] < 0.55:
        for cap_id in WORKFLOW_CAPABILITIES:
            if workflow_capability_active(cap_id, zone_texts):
                wf_score, _ = score_workflow_markers(cap_id, zone_texts + [name])
                if wf_score > ranked[0][1]:
                    ranked = [(cap_id, wf_score)] + [
                        (c, s) for c, s in ranked if c != cap_id
                    ]

    best_id, best_strength = ranked[0]
    second_strength = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = (best_strength - second_strength) / best_strength if best_strength > 0 else 0.0
    confidence = round(min(0.4 + 0.6 * margin, 0.99), 4)

    if second_strength >= best_strength * AMBIGUITY_RATIO:
        confidence = round(confidence * 0.65, 4)

    out = [(best_id, best_strength, confidence)]
    for cap_id, strength in ranked[1:6]:
        if strength >= MIN_MATCH_STRENGTH * 0.85:
            out.append((cap_id, strength, round(confidence * 0.5, 4)))
    return out


def classify_capability(
    target: str,
    *,
    role: str = "",
    state_family: str = "",
    opportunity_type: str = "interaction",
    heading_context: Optional[List[str]] = None,
) -> str:
    return rank_capabilities(
        target, role=role, state_family=state_family,
        opportunity_type=opportunity_type, heading_context=heading_context,
    )[0][0]


def classify_with_metadata(
    target: str,
    *,
    role: str = "",
    state_family: str = "",
    opportunity_type: str = "interaction",
) -> Dict[str, Any]:
    ranked = rank_capabilities(target, role=role, state_family=state_family, opportunity_type=opportunity_type)
    cap_id = ranked[0][0]
    spec = load_taxonomy()["capabilities"][cap_id]
    return {
        "capability": cap_id,
        "label": spec.get("label", cap_id),
        "capability_prior": spec.get("capability_prior", 0.4),
        "capability_confidence": ranked[0][2],
        "cross_site": spec.get("cross_site", False),
    }


def export_boundary_audit_table() -> Dict[str, Any]:
    """Static boundary spec for V1.25 audit report."""
    tax = load_taxonomy()
    table = {}
    for cap_id, spec in tax["capabilities"].items():
        if cap_id == "other":
            continue
        b = spec.get("boundary", {})
        table[cap_id] = {
            "capability": cap_id,
            "label": spec.get("label", cap_id),
            "positive_signals": list(b.get("positive_signals", [])),
            "negative_signals": list(b.get("negative_signals", [])),
            "confusions_with": list(b.get("confusions_with", [])),
        }
    return table
