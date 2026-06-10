"""
P4C Environment Fingerprinter

Captures an observable snapshot of the environment at a point in time.
Used to distinguish between two failure causes in Temporal Replay:

  1. Workflow died       → resolution_rate dropped + fingerprint identical
  2. Environment changed → resolution_rate dropped + fingerprint changed

This is the difference between a fragile workflow and a changed website.
"""
import hashlib
import re
from datetime import datetime, timezone
from typing import Dict

from browsermind_core.ontology.p1_schemas import EnvironmentFingerprint

# ARIA roles we track in the distribution
_TRACKED_ROLES = [
    "button", "textbox", "link", "checkbox", "radio", "combobox",
    "listitem", "menuitem", "tab", "img", "heading",
]


async def fingerprint_environment(page) -> EnvironmentFingerprint:
    """
    Capture a reproducible fingerprint of the current page environment.

    dom_hash:          SHA-256 of the raw HTML content (changes if DOM changes)
    url_signature:     URL normalized by stripping tokens, UUIDs, session IDs
    role_distribution: count of each ARIA role found on the page
    element_count:     total count of interactive elements (inputs, buttons, links)
    """
    dom_hash = ""
    url_signature = ""
    role_distribution: Dict[str, int] = {}
    element_count = 0

    try:
        content = await page.content()
        dom_hash = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:16]

        raw_url = page.url
        url_signature = _normalize_url(raw_url)

        for role in _TRACKED_ROLES:
            try:
                count = await page.get_by_role(role).count()
                if count > 0:
                    role_distribution[role] = count
            except Exception:
                pass

        try:
            inputs  = await page.locator("input, textarea, select").count()
            buttons = await page.locator("button, [role=button]").count()
            links   = await page.locator("a[href]").count()
            element_count = inputs + buttons + links
        except Exception:
            pass

    except Exception:
        pass

    return EnvironmentFingerprint(
        dom_hash=dom_hash,
        url_signature=url_signature,
        role_distribution=role_distribution,
        element_count=element_count,
        captured_at=datetime.now(timezone.utc),
    )


def _normalize_url(url: str) -> str:
    """
    Strip dynamic tokens from a URL so that two visits to the same page
    produce the same signature even if session tokens differ.

    Strips: UUIDs, numeric IDs in path segments, query strings.
    """
    # Remove query string
    url = url.split("?")[0].split("#")[0]
    # Replace UUIDs
    url = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<uuid>", url)
    # Replace long numeric IDs in path segments (>= 5 digits)
    url = re.sub(r"/\d{5,}", "/<id>", url)
    return url


def compare_fingerprints(fp1: EnvironmentFingerprint, fp2: EnvironmentFingerprint) -> dict:
    """
    Compare two fingerprints and return a delta summary.
    Used by temporal_replay.py to classify whether environment changed.
    """
    dom_changed = fp1.dom_hash != fp2.dom_hash
    url_changed = fp1.url_signature != fp2.url_signature
    element_delta = fp2.element_count - fp1.element_count

    role_deltas = {}
    all_roles = set(fp1.role_distribution) | set(fp2.role_distribution)
    for role in all_roles:
        delta = fp2.role_distribution.get(role, 0) - fp1.role_distribution.get(role, 0)
        if delta != 0:
            role_deltas[role] = delta

    environment_changed = dom_changed or url_changed or bool(role_deltas)

    return {
        "dom_changed": dom_changed,
        "url_changed": url_changed,
        "element_delta": element_delta,
        "role_deltas": role_deltas,
        "environment_changed": environment_changed,
    }
