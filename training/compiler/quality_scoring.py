"""
Quality score decomposition (mirrors opportunity_graph_generator formulas).
Used by Quality Audit — single source of truth for factor breakdown.
"""
from __future__ import annotations

from typing import Any, Dict

from training.compiler.opportunity_graph_generator import (
    _LOW_VALUE_EXTRACTION_TERMS,
    _LOW_VALUE_INTERACTION_TERMS,
    MIN_QUALITY_SCORE,
)

HIGH_VALUE_TERMS = frozenset(
    {
        "search",
        "upload",
        "filter",
        "resume",
        "checkout",
        "settings",
        "subscribe",
        "password",
        "email",
        "sign in",
        "log in",
        "register",
        "apply",
        "submit",
        "save",
        "download",
    }
)
LOW_VALUE_NAV_TERMS = frozenset(
    {
        "privacy",
        "terms",
        "legal",
        "cookie",
        "footer",
        "copyright",
        "contact us",
        "help center",
        "skip to",
    }
)


def score_interaction(
    role: str,
    name: str,
    state_family: str,
    confidence: float,
    scarcity: float,
) -> Dict[str, Any]:
    name_lower = name.lower()
    penalties: list[str] = []

    task_relevance = 1.0
    if any(term in name_lower for term in _LOW_VALUE_INTERACTION_TERMS):
        task_relevance = 0.35
        penalties.append("low_value_interaction_term")
    if state_family == "landing_page" and role == "link":
        task_relevance *= 0.5
        penalties.append("landing_page_link")
    if state_family in ("navigation_hub", "article_page") and role == "link":
        task_relevance *= 0.6
        penalties.append("nav_or_article_link")

    if role in ("textbox", "combobox", "searchbox", "checkbox"):
        learnability = 0.9
    elif role == "button" and state_family in (
        "login_form",
        "signup_form",
        "search_interface",
        "newsletter_signup",
    ):
        learnability = 0.72
    else:
        learnability = 0.55
        if role not in ("textbox", "combobox", "searchbox", "checkbox", "button"):
            penalties.append("low_learnability_role")

    actionability = 0.9 if len(name) < 40 else 0.25
    if len(name) >= 40:
        penalties.append("long_label_actionability")

    rarity = min(1.0, 0.35 + scarcity * 0.65)
    quality = task_relevance * learnability * actionability * rarity * confidence

    semantic = _semantic_tags(name_lower, role)

    return {
        "quality_score": round(quality, 4),
        "factors": {
            "task_relevance": round(task_relevance, 4),
            "learnability": round(learnability, 4),
            "actionability": round(actionability, 4),
            "rarity": round(rarity, 4),
            "family_confidence": round(confidence, 4),
        },
        "penalties": penalties,
        "semantic_tags": semantic,
        "passes_threshold": quality >= MIN_QUALITY_SCORE,
    }


def score_extraction(
    role: str,
    name: str,
    state_family: str,
    confidence: float,
    scarcity: float,
) -> Dict[str, Any]:
    name_lower = name.lower()
    penalties: list[str] = []

    task_relevance = 0.85
    if any(term in name_lower for term in _LOW_VALUE_EXTRACTION_TERMS):
        task_relevance = 0.2
        penalties.append("low_value_extraction_term")
    if role == "heading" and state_family in (
        "landing_page",
        "navigation_hub",
        "login_form",
    ):
        task_relevance *= 0.4
        penalties.append("heading_on_non_content_family")

    learnability = 0.75 if role in ("table", "article", "list", "main") else 0.45
    actionability = 0.85 if len(name) < 60 else 0.35
    if len(name) >= 60:
        penalties.append("long_label_actionability")

    rarity = min(1.0, 0.35 + scarcity * 0.65)
    quality = task_relevance * learnability * actionability * rarity * confidence
    semantic = _semantic_tags(name_lower, role)

    return {
        "quality_score": round(quality, 4),
        "factors": {
            "task_relevance": round(task_relevance, 4),
            "learnability": round(learnability, 4),
            "actionability": round(actionability, 4),
            "rarity": round(rarity, 4),
            "family_confidence": round(confidence, 4),
        },
        "penalties": penalties,
        "semantic_tags": semantic,
        "passes_threshold": quality >= MIN_QUALITY_SCORE,
    }


def _semantic_tags(name_lower: str, role: str) -> Dict[str, bool]:
    return {
        "high_value_keyword": any(t in name_lower for t in HIGH_VALUE_TERMS),
        "low_value_nav_keyword": any(t in name_lower for t in LOW_VALUE_NAV_TERMS),
        "is_link": role == "link",
        "is_textbox": role in ("textbox", "searchbox", "combobox"),
        "is_button": role == "button",
    }
