"""
structural_fingerprint.py — Affordance-based structural fingerprint for SSTG identity.

The fingerprint is computed from what a page INVITES (its affordances), not how it
looks. Amazon can redesign its header 50 times — if the cart badge, product listing,
and checkout button remain, the fingerprint is identical.

Two representations are provided:
  - Affordance vector: sorted list of "key:value" strings — stored in template
    metadata at compile time, used for drift comparison via Jaccard distance.
  - Hash: SHA256[:16] of the joined vector — used as a compact SSTG node ID.

Drift is computed as Jaccard distance between two affordance vectors, NOT between
hashes. SHA256 has the avalanche effect: a 1-bit change in the hash means nothing
about semantic similarity. Vector comparison does.

Usage:
    signals = await PageStateExtractor().extract(page)
    vec   = affordance_vector(signals)    # store in template.metadata
    hsh   = vector_to_hash(vec)           # use as SSTG node key
    drift = vector_distance(vec_a, vec_b) # 0.0=identical, 1.0=maximally different
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from browsermind_core.runtime.page_state_extractor import PageStateSignals


# ---------------------------------------------------------------------------
# Affordance vector
# ---------------------------------------------------------------------------

def affordance_vector(signals: "PageStateSignals") -> List[str]:
    """
    Return a sorted list of "key:value" strings representing the affordance
    profile of a page. Values are boolean or small integer buckets — never
    raw counts or URL fragments — to keep the vector stable across minor
    page variations.
    """
    form_bucket = min(int(getattr(signals, "form_count", 0)), 3)

    snippet  = (getattr(signals, "content_snippet", "") or "").lower()
    headings = " ".join(getattr(signals, "heading_texts", []) or []).lower()
    combined = snippet + " " + headings
    cart_present = any(t in combined for t in ("cart", "basket", "bag", "checkout"))

    entries = [
        f"login:{bool(getattr(signals, 'has_login_form', False))}",
        f"logout:{bool(getattr(signals, 'has_logout_link', False))}",
        f"avatar:{bool(getattr(signals, 'has_user_avatar', False))}",
        f"cart:{cart_present}",
        f"stepper:{bool(getattr(signals, 'has_stepper', False))}",
        f"modal:{bool(getattr(signals, 'has_visible_modal', False) or getattr(signals, 'has_visible_dialog', False))}",
        f"forms:{form_bucket}",
        f"price:{bool(getattr(signals, 'has_pricing_tiers', False))}",
        f"upload:{bool(getattr(signals, 'has_dropzone', False) or getattr(signals, 'has_file_input', False))}",
        f"confirm:{bool(getattr(signals, 'has_confirmation_heading', False))}",
        f"captcha:{bool(getattr(signals, 'has_captcha', False))}",
        f"paywall:{bool(getattr(signals, 'has_paywall', False))}",
        f"onboard:{bool(getattr(signals, 'has_onboarding_cue', False))}",
        f"error_alert:{bool(getattr(signals, 'error_alert_count', 0) > 0)}",
        f"success_alert:{bool(getattr(signals, 'success_alert_count', 0) > 0)}",
    ]
    return sorted(entries)


def vector_to_hash(vector: List[str]) -> str:
    """Return a 16-char hex hash of an affordance vector. Used as SSTG node ID."""
    return hashlib.sha256("|".join(vector).encode()).hexdigest()[:16]


def compute_structural_hash(signals: "PageStateSignals") -> str:
    """Convenience: affordance_vector → vector_to_hash in one call."""
    return vector_to_hash(affordance_vector(signals))


# ---------------------------------------------------------------------------
# Drift measurement
# ---------------------------------------------------------------------------

def vector_distance(a: List[str], b: List[str]) -> float:
    """
    Jaccard distance between two affordance vectors.

    Returns 0.0 (identical) to 1.0 (maximally different).
    This is meaningful for affordance comparison — unlike Hamming distance on
    SHA256 hashes, which is noise due to the avalanche effect.
    """
    if not a and not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    if union == 0:
        return 0.0
    return 1.0 - intersection / union


# ---------------------------------------------------------------------------
# Async helper
# ---------------------------------------------------------------------------

async def hash_live_page(page: object) -> Optional[str]:
    """
    Run PageStateExtractor against a live Playwright page and return the
    structural hash. Returns None on extraction failure.
    """
    try:
        from browsermind_core.runtime.page_state_extractor import PageStateExtractor
        signals = await PageStateExtractor().extract(page)
        if not signals.snapshot_ok:
            return None
        return compute_structural_hash(signals)
    except Exception:
        return None


async def vector_from_live_page(page: object) -> Optional[List[str]]:
    """
    Run PageStateExtractor and return the affordance vector (for drift comparison).
    Returns None on extraction failure.
    """
    try:
        from browsermind_core.runtime.page_state_extractor import PageStateExtractor
        signals = await PageStateExtractor().extract(page)
        if not signals.snapshot_ok:
            return None
        return affordance_vector(signals)
    except Exception:
        return None
