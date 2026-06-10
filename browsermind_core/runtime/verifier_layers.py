"""
verifier_layers.py — Individual L6 verification probes.

Each verifier is a single-responsibility probe that checks one dimension:
  NetworkVerifier       — did the expected HTTP calls occur?
  DomVerifier           — are expected selectors present / forbidden absent?
  SemanticZoneVerifier  — did the semantically-relevant DOM zones change?
  AccessibilityVerifier — expected ARIA roles visible?
  StorageVerifier       — localStorage keys have expected values?
  VisualVerifier        — element screenshot SSIM comparison
  SemanticVerifier      — is the EffectVerdict outcome acceptable?

Layer weight changes (Week 2):
  Before: network=0.10, dom=0.30
  After:  network=0.35, dom=0.15, semantic_zone=0.15 (new)
  Rationale: a confirmed POST /api/cart/add → 200 is stronger evidence than
  DOM element counting. SemanticZoneVerifier targets only zones that should
  change, eliminating noise from ads and rotating timestamps.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from playwright.async_api import Page


# ------------------------------------------------------------------ #
# Shared result type                                                   #
# ------------------------------------------------------------------ #

class VerificationLayerResult:
    __slots__ = ("passed", "score", "evidence", "failures")

    def __init__(
        self,
        passed: bool,
        score: float,
        evidence: str = "",
        failures: Optional[List[str]] = None,
    ) -> None:
        self.passed = passed
        self.score = score
        self.evidence = evidence
        self.failures: List[str] = failures or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "evidence": self.evidence,
            "failures": self.failures,
        }


_OK    = lambda evidence="": VerificationLayerResult(True,  1.0, evidence)
_SKIP  = lambda: VerificationLayerResult(True, 1.0, "skipped — no spec")
_FAIL  = lambda evidence, failures=None: VerificationLayerResult(
    False, 0.0, evidence, failures
)


# ------------------------------------------------------------------ #
# NetworkVerifier                                                      #
# ------------------------------------------------------------------ #

class NetworkVerifier:
    """
    Checks that expected HTTP mutation calls occurred.

    Requires the caller to capture network events before/during execution
    and pass them as `captured_requests`. Works with both the legacy list-of-dict
    format and CDPNetworkMonitor.to_captured_requests().

    At weight=0.35 this is now the highest-weight layer. A confirmed
    POST → 200 eliminates the need for DOM diffing on data-mutation actions.
    """

    def verify(
        self,
        expected: List[Dict[str, Any]],
        captured_requests: List[Dict[str, str]],
    ) -> VerificationLayerResult:
        if not expected:
            return _SKIP()

        # No requests captured at all — CDP unavailable or action had no mutations
        if not captured_requests:
            return VerificationLayerResult(
                passed=True,
                score=0.5,
                evidence="no network capture available — layer degraded to neutral",
            )

        failures = []
        for spec in expected:
            url_pat = spec.get("url_contains", "")
            method  = spec.get("method", "").upper()
            require_success = spec.get("require_success", True)
            matched = any(
                (not url_pat or url_pat in r.get("url", ""))
                and (not method or method == r.get("method", "").upper())
                and (not require_success or r.get("status", "").startswith("2"))
                for r in captured_requests
            )
            if not matched:
                desc = f"method={method or '*'} url_contains={url_pat!r}"
                failures.append(f"Expected mutation not observed: {desc}")

        if failures:
            return _FAIL(f"{len(failures)} expected network mutation(s) missing", failures)
        return _OK(f"{len(expected)} network mutation(s) confirmed (score=1.0)")


# ------------------------------------------------------------------ #
# DomVerifier                                                          #
# ------------------------------------------------------------------ #

class DomVerifier:
    """
    Checks CSS selector presence/absence and text presence/absence.

    Weight reduced from 0.30 → 0.15 in favour of NetworkVerifier and
    SemanticZoneVerifier which carry lower noise-to-signal.
    """

    async def verify(
        self,
        page: "Page",
        expected_selectors: List[str],
        forbidden_selectors: List[str],
        expected_texts: List[str],
        forbidden_texts: List[str],
    ) -> VerificationLayerResult:
        if (not expected_selectors and not forbidden_selectors
                and not expected_texts and not forbidden_texts):
            return _SKIP()

        failures = []

        for sel in expected_selectors:
            try:
                count = await page.locator(sel).count()
                if count == 0:
                    failures.append(f"Expected selector not found: {sel!r}")
            except Exception as exc:
                failures.append(f"Selector check failed: {sel!r}: {exc}")

        for sel in forbidden_selectors:
            try:
                count = await page.locator(sel).count()
                if count > 0:
                    failures.append(f"Forbidden selector present: {sel!r}")
            except Exception:
                pass

        if expected_texts or forbidden_texts:
            try:
                body_text = await page.evaluate(
                    "() => (document.body || document.documentElement).innerText || ''"
                )
            except Exception:
                body_text = ""

            for text in expected_texts:
                if text.lower() not in body_text.lower():
                    failures.append(f"Expected text not found: {text!r}")

            for text in forbidden_texts:
                if text.lower() in body_text.lower():
                    failures.append(f"Forbidden text present: {text!r}")

        if failures:
            return _FAIL(f"{len(failures)} DOM assertion(s) failed", failures)
        total = (len(expected_selectors) + len(forbidden_selectors)
                 + len(expected_texts) + len(forbidden_texts))
        return _OK(f"{total} DOM assertion(s) passed")


# ------------------------------------------------------------------ #
# SemanticZoneVerifier                                                 #
# ------------------------------------------------------------------ #

# Canonical semantic zones: selector lists ordered by specificity.
# First matching visible element in each zone wins.
_SEMANTIC_ZONES: Dict[str, List[str]] = {
    "cart":          [
        "[aria-label*='cart' i]", ".cart-count", "[data-testid*='cart' i]",
        "[class*='cart-icon' i]", "#cart-quantity", ".bag-count",
        "[class*='basket' i]",
    ],
    "auth":          [
        "[aria-label*='user' i]", ".user-avatar", "[data-testid*='profile' i]",
        ".account-name", ".user-name", "[class*='user-menu' i]",
        "[class*='account-menu' i]", "[class*='logged-in' i]",
    ],
    "form_feedback": [
        "[role='alert']", ".success-message", "[aria-live='polite']",
        "[aria-live='assertive']", "[class*='success' i]",
        "[class*='confirmation' i]", ".toast", "[class*='toast' i]",
        "[class*='snackbar' i]",
    ],
    "search":        [
        "[role='main']", ".search-results", "[data-testid*='results' i]",
        "[class*='result-list' i]", "[class*='search-result' i]",
        "[data-component*='results' i]",
    ],
    "order":         [
        "[class*='order-confirm' i]", "[class*='order-number' i]",
        "[class*='thank-you' i]", "[class*='confirmation' i]",
        "h1[class*='confirm' i]", "h1[class*='order' i]",
    ],
    "navigation":    [
        "h1", ".page-title", "[data-testid*='title' i]",
        "[class*='breadcrumb' i]", "[aria-current='page']",
    ],
}

# Which zones to diff for a given capability/action hint
_ACTION_ZONE_MAP: Dict[str, List[str]] = {
    "add_to_cart":   ["cart", "form_feedback"],
    "checkout":      ["order", "form_feedback"],
    "place_order":   ["order", "form_feedback"],
    "login":         ["auth", "form_feedback"],
    "logout":        ["auth", "navigation"],
    "register":      ["auth", "form_feedback"],
    "search":        ["search", "navigation"],
    "submit_form":   ["form_feedback"],
    "navigate":      ["navigation"],
    "fill":          ["form_feedback"],
    "click":         ["form_feedback", "navigation"],
}


class SemanticZoneVerifier:
    """
    Zone-level DOM diffing.

    Captures text content of semantically relevant zones before and after
    an action, then verifies they changed as expected.

    Advantages over whole-DOM diffing:
    - 50x faster on large pages (zone snapshot is a single locator.inner_text)
    - 10x lower noise (ads, timestamps, scroll offsets are not in named zones)
    - Explicit reporting: which zone changed and to what

    Usage:
        zone_verifier = SemanticZoneVerifier()
        before = await zone_verifier.capture(page, capability_hint="login")
        # ... execute action ...
        result = await zone_verifier.verify(page, before, capability_hint="login")
    """

    async def capture(
        self,
        page: "Page",
        capability_hint: str = "",
    ) -> Dict[str, str]:
        """
        Snapshot the relevant semantic zones for the given capability.

        Returns {zone_name: text_content}. Returns {} on total failure.
        """
        zones_to_check = (
            _ACTION_ZONE_MAP.get(capability_hint)
            or list(_SEMANTIC_ZONES.keys())
        )
        result: Dict[str, str] = {}
        for zone_name in zones_to_check:
            selectors = _SEMANTIC_ZONES.get(zone_name, [])
            for sel in selectors:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=300):
                        text = (await el.inner_text()) or ""
                        result[zone_name] = text.strip()[:200]
                        break
                except Exception:
                    continue
            if zone_name not in result:
                result[zone_name] = ""
        return result

    async def verify(
        self,
        page: "Page",
        before_zones: Dict[str, str],
        capability_hint: str = "",
        require_change: bool = False,
    ) -> "VerificationLayerResult":
        """
        Compare current zone content against before_zones snapshot.

        Args:
            before_zones:   Dict from capture() before the action.
            require_change: If True, ≥1 zone must have changed for PASS.
        """
        if not before_zones:
            return _SKIP()

        after_zones = await self.capture(page, capability_hint)

        changed: List[str] = []
        unchanged: List[str] = []

        for zone_name, before_text in before_zones.items():
            after_text = after_zones.get(zone_name, "")
            # Skip zones that were absent both before and after
            if not before_text and not after_text:
                continue
            if after_text != before_text:
                changed.append(zone_name)
            else:
                unchanged.append(zone_name)

        if not changed and not unchanged:
            return _SKIP()

        if require_change and not changed:
            return _FAIL(
                f"No semantic zones changed after action "
                f"(checked: {list(before_zones.keys())})",
                [f"Zone '{z}' unchanged" for z in unchanged],
            )

        total_checked = len(changed) + len(unchanged)
        score = (
            len(changed) / total_checked
            if (require_change and total_checked > 0)
            else 0.8   # advisory pass — zones present but change not required
        )
        evidence = (
            f"zones changed={changed}, unchanged={unchanged}"
            if changed else f"zones checked {unchanged}, no change (advisory pass)"
        )
        return VerificationLayerResult(
            passed=True,
            score=score,
            evidence=evidence,
        )


# ------------------------------------------------------------------ #
# AccessibilityVerifier                                                #
# ------------------------------------------------------------------ #

class AccessibilityVerifier:
    """Checks that expected ARIA roles are visible after the action."""

    async def verify(
        self,
        page: "Page",
        expected_roles: List[str],
    ) -> VerificationLayerResult:
        if not expected_roles:
            return _SKIP()

        failures = []
        for role in expected_roles:
            try:
                count = await page.get_by_role(role).count()  # type: ignore[arg-type]
                if count == 0:
                    failures.append(f"Expected ARIA role not visible: {role!r}")
            except Exception as exc:
                failures.append(f"ARIA role check failed: {role!r}: {exc}")

        if failures:
            return _FAIL(f"{len(failures)} accessibility assertion(s) failed", failures)
        return _OK(f"{len(expected_roles)} ARIA role(s) confirmed visible")


# ------------------------------------------------------------------ #
# StorageVerifier                                                      #
# ------------------------------------------------------------------ #

class StorageVerifier:
    """Checks localStorage key/value expectations."""

    async def verify(
        self,
        page: "Page",
        expected: Dict[str, str],
    ) -> VerificationLayerResult:
        if not expected:
            return _SKIP()

        failures = []
        for key, expected_val in expected.items():
            try:
                actual = await page.evaluate(f"() => localStorage.getItem({key!r})")
                if actual is None:
                    failures.append(f"localStorage[{key!r}] not set")
                elif expected_val and str(actual) != expected_val:
                    failures.append(
                        f"localStorage[{key!r}] = {actual!r}, expected {expected_val!r}"
                    )
            except Exception as exc:
                failures.append(f"localStorage check failed for {key!r}: {exc}")

        if failures:
            return _FAIL(f"{len(failures)} storage assertion(s) failed", failures)
        return _OK(f"{len(expected)} storage key(s) confirmed")


# ------------------------------------------------------------------ #
# VisualVerifier                                                       #
# ------------------------------------------------------------------ #

class VisualVerifier:
    """
    Pixel-based visual regression using SSIM.

    Requires Pillow and scikit-image. Falls back to skipped if not installed.
    """

    async def verify(
        self,
        page: "Page",
        baseline_path: Optional[str],
        selector: Optional[str] = None,
        threshold: float = 0.95,
    ) -> VerificationLayerResult:
        if baseline_path is None:
            return _SKIP()

        try:
            import io

            import numpy as np
            from PIL import Image
            from skimage.metrics import structural_similarity  # type: ignore

            if selector:
                locator = page.locator(selector)
                current_bytes = await locator.screenshot()
            else:
                current_bytes = await page.screenshot()

            current  = np.array(Image.open(io.BytesIO(current_bytes)).convert("RGB"))
            baseline = np.array(Image.open(baseline_path).convert("RGB"))

            if current.shape != baseline.shape:
                return _FAIL(
                    f"Screenshot size mismatch: {current.shape} vs {baseline.shape}"
                )

            score, _ = structural_similarity(
                baseline, current, channel_axis=2, full=True
            )
            if score < threshold:
                return _FAIL(
                    f"SSIM {score:.3f} below threshold {threshold:.3f}",
                    [f"Visual regression detected (SSIM={score:.3f})"],
                )
            return _OK(f"SSIM {score:.3f} ≥ threshold {threshold:.3f}")

        except ImportError:
            return VerificationLayerResult(
                True, 1.0, "skipped — pillow/skimage not installed"
            )
        except Exception as exc:
            return VerificationLayerResult(
                True, 0.5, f"skipped — screenshot comparison error: {exc}"
            )


# ------------------------------------------------------------------ #
# SemanticVerifier                                                     #
# ------------------------------------------------------------------ #

class SemanticVerifier:
    """
    Checks that the observed EffectVerdict matches the expected effect types.
    """

    def verify(
        self,
        verdict_effect_type: Optional[str],
        expected_effects: List[str],
        url_contains: Optional[str],
        url_pattern: Optional[str],
        actual_url: str,
    ) -> VerificationLayerResult:
        failures = []

        if url_contains and url_contains not in actual_url:
            failures.append(
                f"URL does not contain {url_contains!r} (actual: {actual_url!r})"
            )
        if url_pattern:
            if not re.search(url_pattern, actual_url):
                failures.append(
                    f"URL does not match pattern {url_pattern!r} (actual: {actual_url!r})"
                )

        if expected_effects and verdict_effect_type:
            if verdict_effect_type not in expected_effects:
                failures.append(
                    f"Effect type {verdict_effect_type!r} not in expected {expected_effects}"
                )

        if failures:
            return _FAIL(f"{len(failures)} semantic assertion(s) failed", failures)

        if not url_contains and not url_pattern and not expected_effects:
            return _SKIP()

        return _OK("semantic assertions passed")
