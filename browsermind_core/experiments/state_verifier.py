"""
P4C State Verifier — Evidence/Inference Architecture

Separation of concerns:
  collect_evidence(site_key, page) -> StateEvidence
      Site-specific DOM probing. Returns raw observable signals.
      These are FACTS about what was visible — not conclusions.

  infer_state(site_key, evidence) -> StateInference
      Generic rule-based inference. Maps evidence signals to named states.
      Can be re-run on stored evidence without re-running replay.

The key insight: Evidence collection is fragile and site-specific.
Inference rules are stable and site-general.
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional

from browsermind_core.ontology.p1_schemas import StateEvidence, StateInference


# ---------------------------------------------------------------------------
# Evidence Collection (site-specific DOM probing)
# ---------------------------------------------------------------------------

async def collect_evidence(site_key: str, page) -> StateEvidence:
    """
    Collect observable DOM signals for a given site after workflow execution.
    Returns raw facts — no interpretation, no state conclusions.
    """
    signals = []
    url_pattern = ""
    page_title = ""

    try:
        await page.wait_for_timeout(800)
        url_pattern = page.url
        page_title = await page.title()

        if site_key == "static_baseline":
            if await page.locator(".mw-search-results").count() > 0:
                signals.append("search_results_visible")
            if await page.locator("#firstHeading").count() > 0:
                signals.append("article_heading_visible")

        elif site_key == "saucedemo":
            if await page.locator(".complete-header").count() > 0:
                signals.append("checkout_complete_header_visible")
            if await page.locator(".error-message-container").count() > 0:
                signals.append("error_banner_visible")
            if await page.locator(".inventory_item").count() > 0:
                signals.append("inventory_page_visible")
            if "/checkout-complete" in url_pattern:
                signals.append("url_checkout_complete")

        elif site_key == "demoqa":
            if await page.locator("#example-modal-sizes-title-lg").count() > 0:
                signals.append("success_modal_visible")
            if await page.locator(".modal-content").count() > 0:
                signals.append("modal_present")

        elif site_key == "aria_internet":
            if await page.locator(".flash.success").count() > 0:
                signals.append("success_flash_visible")
            if await page.locator(".flash.error").count() > 0:
                signals.append("error_flash_visible")
            if "secure" in url_pattern:
                signals.append("url_secure_area")

        elif site_key == "github":
            if "/issues" in url_pattern:
                signals.append("url_issues_page")
            if "/stargazers" in url_pattern:
                signals.append("url_stargazers_page")
            if await page.locator(".issues-listing").count() > 0:
                signals.append("issues_listing_visible")

        elif site_key == "huggingface":
            if "models" in url_pattern or "search" in url_pattern:
                signals.append("url_models_or_search")
            if await page.locator("div.grid-cols-1").count() > 0:
                signals.append("model_grid_visible")
            if "login" in url_pattern:
                signals.append("url_login_page")

        elif site_key == "controlled_drift":
            page_content = await page.content()
            if "Welcome" in page_content:
                signals.append("welcome_text_visible")
            if "/dashboard" in url_pattern:
                signals.append("url_dashboard")
            if await page.locator("form").count() > 0:
                signals.append("login_form_present")

    except Exception as e:
        signals.append(f"evidence_collection_error:{str(e)[:80]}")

    return StateEvidence(
        signals=signals,
        url_pattern=url_pattern,
        page_title=page_title,
        observed_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# State Inference Rules (site-aware, but generic mapping logic)
# ---------------------------------------------------------------------------

# Each site defines: { signal -> inferred_state, ... }
# The first matching signal wins. Order matters — most specific first.
_INFERENCE_RULES: dict = {
    "static_baseline": {
        "article_heading_visible":   ("results_available", 1.0),
        "search_results_visible":    ("results_available", 0.9),
    },
    "saucedemo": {
        "checkout_complete_header_visible": ("checkout_complete", 1.0),
        "url_checkout_complete":            ("checkout_complete", 0.9),
        "error_banner_visible":             ("error_displayed", 1.0),
        "inventory_page_visible":           ("browsing_inventory", 0.8),
    },
    "demoqa": {
        "success_modal_visible": ("form_submitted", 1.0),
        "modal_present":         ("form_submitted", 0.8),
    },
    "aria_internet": {
        "success_flash_visible": ("logged_in", 1.0),
        "url_secure_area":       ("logged_in", 0.9),
        "error_flash_visible":   ("login_failed", 1.0),
    },
    "github": {
        "url_issues_page":      ("issues_opened", 1.0),
        "issues_listing_visible": ("issues_opened", 0.9),
        "url_stargazers_page":  ("stargazers_opened", 1.0),
    },
    "huggingface": {
        "model_grid_visible":    ("model_search_completed", 1.0),
        "url_models_or_search":  ("model_search_completed", 0.9),
        "url_login_page":        ("logged_out", 1.0),
    },
    "controlled_drift": {
        "welcome_text_visible": ("logged_in", 1.0),
        "url_dashboard":        ("logged_in", 0.9),
        "login_form_present":   ("logged_out", 0.8),
    },
}

_EXPECTED_STATES: dict = {
    "static_baseline":  "results_available",
    "saucedemo":        "checkout_complete",
    "demoqa":           "form_submitted",
    "aria_internet":    "logged_in",
    "github":           "issues_opened",
    "huggingface":      "model_search_completed",
    "controlled_drift": "logged_in",
}


def infer_state(site_key: str, evidence: StateEvidence) -> StateInference:
    """
    Infer the terminal semantic state from collected evidence.
    Returns a StateInference with inferred_state, confidence, and match.
    """
    expected = _EXPECTED_STATES.get(site_key, "terminal_state")
    rules = _INFERENCE_RULES.get(site_key, {})

    inferred = "unknown_state"
    confidence = 0.0

    for signal in evidence.signals:
        if signal in rules:
            inferred, confidence = rules[signal]
            break

    # If we have URL-based signals in evidence but no signal matched rules,
    # try a URL heuristic as a last-resort inference
    if inferred == "unknown_state" and evidence.url_pattern:
        if site_key == "aria_internet" and "secure" in evidence.url_pattern:
            inferred, confidence = "logged_in", 0.7
        elif site_key == "github" and "/issues" in evidence.url_pattern:
            inferred, confidence = "issues_opened", 0.7

    match = (inferred == expected)

    return StateInference(
        inferred_state=inferred,
        expected_state=expected,
        confidence=confidence,
        evidence=evidence,
        match=match,
    )
