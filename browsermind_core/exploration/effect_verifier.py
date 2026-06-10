"""
EffectVerifier — distinguishes "action executed" from "goal achieved".

Enhanced with:
  - Semantic success vs error alert classification (#11)
  - Form validation failure classification (#13)
  - Navigation loop detection (#14)
  - Visual text-regression confidence (#15)
  - Quality scoring for evidence weighting (#77)

effect_type taxonomy (priority order, first match wins):
  url_transition       — URL changed to a NEW page (base URL differs)
  hash_navigation      — Only the fragment changed (anchor jump, page unchanged)
  return_to_origin     — URL changed back to where we started (loop)
  form_validation_fail — Validation errors appeared after submit
  alert_success        — Success toast/notification appeared
  alert_error          — Error toast/notification appeared
  dom_mutation         — Significant DOM change on same URL
  content_change       — Text content hash changed
  no_signal            — Nothing measurable changed

outcome_label mapping:
  url_transition       → TRANSITION_SUCCESS
  hash_navigation      → FAILED (anchor jump, not real navigation)
  return_to_origin     → FAILED (nav loop)
  form_validation_fail → FAILED (form rejected input)
  alert_success        → SUCCESS
  alert_error          → FAILED (explicit error)
  dom_mutation         → SUCCESS
  content_change       → SUCCESS
  no_signal            → FAILED
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from playwright.async_api import Page


@dataclass
class EffectSnapshot:
    """DOM state snapshot taken before or after an action."""
    url: str = ""
    title: str = ""

    # Structural signals
    element_count: int = 0
    list_item_count: int = 0
    result_count: int = 0
    alert_count: int = 0
    success_alert_count: int = 0     # alerts with success/confirm semantics
    error_alert_count: int = 0       # alerts with error/warning semantics
    validation_count: int = 0
    heading_count: int = 0
    form_count: int = 0              # number of visible forms

    # Content fingerprint
    content_hash: str = ""
    content_snippet: str = ""        # first 200 chars of visible text

    # Evidence quality metadata
    snapshot_ok: bool = True         # False if JS evaluation failed

    @property
    def is_empty(self) -> bool:
        return not self.snapshot_ok or (self.url == "" and self.element_count == 0)


@dataclass
class EffectVerdict:
    """
    Result of comparing two EffectSnapshots.

    Attributes:
        effect_type: semantic classification (see module docstring)
        quality_score: 0.0-1.0 evidence quality for corpus weighting
    """
    has_effect: bool
    effect_type: str
    confidence: float
    evidence: str
    delta: Dict[str, int] = field(default_factory=dict)
    quality_score: float = 0.5       # corpus evidence quality weight

    @property
    def outcome_label(self) -> str:
        if self.effect_type == "url_transition":
            return "TRANSITION_SUCCESS"
        if self.effect_type == "hash_navigation":
            return "FAILED"
        if self.effect_type == "alert_success":
            return "SUCCESS"
        if self.effect_type == "dom_mutation":
            return "SUCCESS"
        if self.effect_type == "content_change":
            return "SUCCESS"
        return "FAILED"

    @property
    def failure_reason(self) -> Optional[str]:
        if self.effect_type == "no_signal":
            return "NO_VISIBLE_SIGNAL"
        if self.effect_type == "return_to_origin":
            return "NAVIGATION_LOOP"
        if self.effect_type == "hash_navigation":
            return "HASH_NAVIGATION"
        if self.effect_type == "form_validation_fail":
            return "FORM_VALIDATION_REJECTED"
        if self.effect_type == "alert_error":
            return "EXPLICIT_ERROR_RESPONSE"
        return None


class EffectVerifier:
    """
    Takes DOM snapshots and diffs them to verify action effects.

    Usage:
        verifier = EffectVerifier()
        before = await verifier.snapshot(page)
        # ... execute action ...
        after  = await verifier.snapshot(page)
        verdict = verifier.diff(before, after)
    """

    def __init__(self, start_url: str = "") -> None:
        # Tracking the session start URL enables navigation-loop detection (#14)
        self._start_url = start_url

    def set_start_url(self, url: str) -> None:
        self._start_url = url

    async def snapshot(self, page: "Page") -> EffectSnapshot:
        """Capture current page state. Best-effort — returns degraded snapshot on error."""
        snap = EffectSnapshot()
        try:
            snap.url   = page.url or ""
            snap.title = await page.title() or ""

            counts = await page.evaluate("""() => {
                const vis = (el) => {
                    try {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    } catch { return false; }
                };
                const q = (sel) => Array.from(document.querySelectorAll(sel)).filter(vis).length;
                const text = (document.body || document.documentElement).innerText || '';

                // Semantic alert classification
                const alertEls = Array.from(document.querySelectorAll(
                    '[role="alert"], .alert, .notification, .message, .toast, ' +
                    '[class*="toast" i], [class*="snackbar" i], [class*="banner" i]'
                )).filter(vis);
                const successKeywords = /success|confirm|complete|done|thank|submitted|saved/i;
                const errorKeywords   = /error|fail|invalid|wrong|incorrect|denied|reject/i;
                const successAlerts = alertEls.filter(el =>
                    successKeywords.test(el.textContent || '') ||
                    successKeywords.test(el.className || '') ||
                    el.getAttribute('role') === 'status'
                ).length;
                const errorAlerts = alertEls.filter(el =>
                    errorKeywords.test(el.textContent || '') ||
                    errorKeywords.test(el.className || '')
                ).length;

                return {
                    total:          q('*'),
                    list_items:     q('li, article, [role="listitem"]'),
                    results:        q('[class*="result" i], .result, .search-result'),
                    alerts:         alertEls.length,
                    success_alerts: successAlerts,
                    error_alerts:   errorAlerts,
                    validation:     q(':invalid, [class*="invalid" i], [class*="error" i], ' +
                                      '[class*="field-error" i], .form-error'),
                    headings:       q('h1, h2, h3, h4'),
                    forms:          q('form'),
                    content:        text.slice(0, 200),
                    content_full:   text.slice(0, 3000),
                };
            }""")

            snap.element_count      = int(counts.get("total", 0))
            snap.list_item_count    = int(counts.get("list_items", 0))
            snap.result_count       = int(counts.get("results", 0))
            snap.alert_count        = int(counts.get("alerts", 0))
            snap.success_alert_count = int(counts.get("success_alerts", 0))
            snap.error_alert_count  = int(counts.get("error_alerts", 0))
            snap.validation_count   = int(counts.get("validation", 0))
            snap.heading_count      = int(counts.get("headings", 0))
            snap.form_count         = int(counts.get("forms", 0))
            snap.content_snippet    = counts.get("content", "")
            snap.content_hash       = hashlib.md5(
                counts.get("content_full", "").encode("utf-8", errors="replace")
            ).hexdigest()
            snap.snapshot_ok = True

        except Exception:
            snap.snapshot_ok = False

        return snap

    def diff(self, before: EffectSnapshot, after: EffectSnapshot) -> EffectVerdict:
        """
        Compare two snapshots and return a verdict.

        Priority order (first match wins):
          1. URL changed to new page        → url_transition      (quality=1.0)
          2. URL changed back to start      → return_to_origin    (quality=0.3)
          3. Validation errors appeared     → form_validation_fail(quality=0.7)
          4. Error alert appeared           → alert_error         (quality=0.8)
          5. Results/list items appeared    → dom_mutation        (quality=0.9)
          6. Success alert appeared         → alert_success       (quality=0.9)
          7. >5% element count change       → dom_mutation        (quality=0.65)
          8. Content hash changed           → content_change      (quality=0.5)
          9. Nothing changed                → no_signal           (quality=0.1)
        """
        if before.is_empty or after.is_empty:
            return EffectVerdict(
                has_effect=False,
                effect_type="no_signal",
                confidence=0.5,
                evidence="snapshot unavailable",
                quality_score=0.0,
            )

        delta = {
            "list_items":     after.list_item_count    - before.list_item_count,
            "results":        after.result_count       - before.result_count,
            "alerts":         after.alert_count        - before.alert_count,
            "success_alerts": after.success_alert_count - before.success_alert_count,
            "error_alerts":   after.error_alert_count  - before.error_alert_count,
            "validation":     after.validation_count   - before.validation_count,
            "elements":       after.element_count      - before.element_count,
            "headings":       after.heading_count      - before.heading_count,
        }

        # 1. URL transition — strongest signal
        if after.url != before.url:
            # Sub-case: only fragment changed → anchor jump, page content unchanged
            before_base = before.url.split('#')[0]
            after_base  = after.url.split('#')[0]
            if before_base == after_base:
                return EffectVerdict(
                    has_effect=False,
                    effect_type="hash_navigation",
                    confidence=1.0,
                    evidence=f"anchor jump: {before.url!r} → {after.url!r}",
                    delta=delta,
                    quality_score=0.05,
                )
            # Sub-case: navigation loop (returned to where we started)
            if self._start_url and after.url.rstrip("/") == self._start_url.rstrip("/"):
                return EffectVerdict(
                    has_effect=False,
                    effect_type="return_to_origin",
                    confidence=0.95,
                    evidence=f"navigation loop: returned to start URL {after.url!r}",
                    delta=delta,
                    quality_score=0.3,
                )
            return EffectVerdict(
                has_effect=True,
                effect_type="url_transition",
                confidence=1.0,
                evidence=f"URL: {before.url!r} → {after.url!r}",
                delta=delta,
                quality_score=1.0,
            )

        # 2. Validation errors appeared after submission → form rejected input
        if delta["validation"] > 0 and (before.form_count > 0 or after.form_count > 0):
            return EffectVerdict(
                has_effect=False,
                effect_type="form_validation_fail",
                confidence=0.85,
                evidence=f"+{delta['validation']} validation error(s) — form rejected probe input",
                delta=delta,
                quality_score=0.7,
            )

        # 3. Error alert appeared
        if delta["error_alerts"] > 0:
            return EffectVerdict(
                has_effect=False,
                effect_type="alert_error",
                confidence=0.85,
                evidence=f"+{delta['error_alerts']} error notification(s) appeared",
                delta=delta,
                quality_score=0.8,
            )

        # 4. New results / list items appeared
        if delta["results"] > 0 or delta["list_items"] > 2:
            label = "results" if delta["results"] > 0 else "list items"
            count = delta["results"] or delta["list_items"]
            return EffectVerdict(
                has_effect=True,
                effect_type="dom_mutation",
                confidence=0.9,
                evidence=f"+{count} {label} appeared",
                delta=delta,
                quality_score=0.9,
            )

        # 5. Success alert appeared
        if delta["success_alerts"] > 0:
            return EffectVerdict(
                has_effect=True,
                effect_type="alert_success",
                confidence=0.9,
                evidence=f"+{delta['success_alerts']} success notification(s) appeared",
                delta=delta,
                quality_score=0.9,
            )

        # 6. Generic alert (unclassified)
        if delta["alerts"] > 0:
            return EffectVerdict(
                has_effect=True,
                effect_type="dom_mutation",
                confidence=0.8,
                evidence=f"+{delta['alerts']} notification(s) appeared",
                delta=delta,
                quality_score=0.75,
            )

        # 7. Significant element count change (>5% of before)
        if before.element_count > 0:
            pct_change = abs(delta["elements"]) / before.element_count
            if pct_change > 0.05:
                return EffectVerdict(
                    has_effect=True,
                    effect_type="dom_mutation",
                    confidence=0.65,
                    evidence=(
                        f"element count {before.element_count} → {after.element_count}"
                        f" ({pct_change:.0%} change)"
                    ),
                    delta=delta,
                    quality_score=0.65,
                )

        # 8. Content hash changed
        if after.content_hash != before.content_hash:
            return EffectVerdict(
                has_effect=True,
                effect_type="content_change",
                confidence=0.50,
                evidence="visible text content changed",
                delta=delta,
                quality_score=0.5,
            )

        # 9. No observable signal
        return EffectVerdict(
            has_effect=False,
            effect_type="no_signal",
            confidence=1.0,
            evidence="no URL, DOM, or content change detected",
            delta=delta,
            quality_score=0.1,
        )
