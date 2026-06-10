"""
Capability discoverability — signal/context matching from taxonomy JSON only.
No hardcoded per-capability if-statements; scales as taxonomy grows.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

from training.capability_taxonomy import (
    MIN_MATCH_STRENGTH,
    WORKFLOW_CAPABILITIES,
    _blocked_by_negative,
    _phrase_matches,
    _score_capability,
    get_discovery_spec,
    score_workflow_markers,
    workflow_capability_active,
)

_SEEDS_PATH = os.path.join(os.path.dirname(__file__), "capability_seeds.json")
_WORD_BOUNDARY_SHORT = 6

FUNNEL_CAPABILITIES = (
    "upload",
    "job_application",
    "content_creation",
    "settings",
    "checkout",
    "search",
    "auth_recovery",
    "filter",
    "account_creation",
    "multi_field_form",
    "navigation",
    "legal",
    "marketing",
    "data_extraction",
    "other",
)


@lru_cache(maxsize=1)
def load_capability_seeds() -> Dict[str, Any]:
    with open(_SEEDS_PATH, encoding="utf-8") as f:
        return json.load(f)


def seed_urls_for_capability(capability_id: str) -> List[str]:
    caps = load_capability_seeds().get("capabilities", {})
    entry = caps.get(capability_id, {})
    return list(entry.get("urls", []))


def all_seed_urls() -> List[Dict[str, str]]:
    """Flatten to [{url, primary_capability}, ...] — URL may appear under multiple caps."""
    out: List[Dict[str, str]] = []
    for cap_id, entry in load_capability_seeds().get("capabilities", {}).items():
        for url in entry.get("urls", []):
            out.append({"url": url, "seed_capability": cap_id})
    return out


def unique_seed_url_list() -> List[str]:
    seen: set = set()
    urls: List[str] = []
    for item in all_seed_urls():
        u = item["url"]
        if u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


def _signal_list_match(name: str, signals: List[str]) -> bool:
    name_l = name.lower().strip()
    for phrase in signals:
        p = phrase.lower().strip()
        if not p:
            continue
        if len(p) < _WORD_BOUNDARY_SHORT and " " not in p:
            if re.search(rf"\b{re.escape(p)}\b", name_l):
                return True
        elif p in name_l:
            return True
    return False


def discovery_signal_detected(
    capability_id: str,
    target: str,
    *,
    role: str = "",
    state_family: str = "",
) -> bool:
    """DISC-1: strict discovery — signals/workflow_markers only (not context-only)."""
    disc = get_discovery_spec(capability_id)
    name = target.lower().strip()

    if _blocked_by_negative(name, disc.get("negative_signals", [])):
        return False

    if _signal_list_match(name, disc.get("signals", [])):
        return True
    if _signal_list_match(name, disc.get("workflow_markers", [])):
        return True
    return False


def discovery_signal_match(
    capability_id: str,
    target: str,
    *,
    role: str = "",
    state_family: str = "",
) -> bool:
    """Broad discovery including required_context (used for candidate pool sizing)."""
    if discovery_signal_detected(
        capability_id, target, role=role, state_family=state_family
    ):
        return True

    disc = get_discovery_spec(capability_id)
    name = target.lower().strip()
    if _blocked_by_negative(name, disc.get("negative_signals", [])):
        return False

    ctx = disc.get("required_context", {})
    families = ctx.get("state_families", [])
    roles = ctx.get("roles", [])
    if families and state_family in families:
        if not roles or role in roles:
            if len(name) >= 3 and name not in ("link", "button", "submit", "menu"):
                return True
    return False


def boundary_passed(
    capability_id: str,
    target: str,
    *,
    role: str = "",
    state_family: str = "",
    opportunity_type: str = "interaction",
    heading_context: Optional[List[str]] = None,
    zone_texts: Optional[List[str]] = None,
) -> bool:
    """DISC-1: node or workflow-region passes capability boundary (excludes wayfinding-only)."""
    name = target.lower().strip()
    strength = _score_capability(
        capability_id,
        name,
        role=role,
        state_family=state_family,
        opportunity_type=opportunity_type,
        heading_context=heading_context,
    )
    if strength >= MIN_MATCH_STRENGTH:
        return True
    if zone_texts and capability_id in WORKFLOW_CAPABILITIES:
        wf_score, _ = score_workflow_markers(capability_id, zone_texts + [name])
        return wf_score >= MIN_MATCH_STRENGTH
    return False


def region_matches_capability(capability_id: str, zone_family: str) -> bool:
    disc = get_discovery_spec(capability_id)
    families = disc.get("required_context", {}).get("state_families", [])
    if not families:
        return False
    return zone_family in families


def capabilities_for_url(url: str) -> List[str]:
    """All seed capabilities that list this URL."""
    out = []
    for cap_id, entry in load_capability_seeds().get("capabilities", {}).items():
        if url in entry.get("urls", []):
            out.append(cap_id)
    return out
