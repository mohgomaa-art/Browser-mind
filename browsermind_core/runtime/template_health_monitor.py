"""
template_health_monitor.py — Schema drift detection for compiled WorkflowTemplates.

The problem: WorkflowTemplates are compiled against a site at a specific point in
time. The site redesigns. LinkedIn moves the Apply button. The template silently
fails. The SSTG records a failed transition. OutcomeLedger records quality=0.
BCPolicyV2 trains on garbage. The model gets worse. Compounding degradation.

Without a liveness invariant, at 500 sites with 5% weekly UI change rate you
accumulate 25 stale templates per week. After 6 months: 600+ stale templates
poisoning the data.

This monitor is that invariant. It navigates to a template's landing page, extracts
the live structural hash, and computes drift against the affordance vector stored
in template.metadata["compile_time_affordances"] at compile time.

Drift thresholds:
  < 0.3  → healthy (minor styling changes; affordances intact)
  0.3–0.7 → stale  (significant restructure; re-record before next campaign run)
  > 0.7  → corrupt (completely different page or redirect; immediate re-record needed)

Template metadata keys written by the compiler (stamp_template()):
  compile_time_affordances: List[str]   — sorted affordance vector
  compile_time_hash:        str         — SHA256[:16] of the vector
  compile_time_url:         str         — URL navigated to during compilation
  compile_time_iso:         str         — ISO timestamp of compilation

Template metadata keys written by the monitor:
  health_status:      "healthy" | "stale" | "corrupted" | "unknown"
  health_drift_score: float (Jaccard distance)
  health_checked_iso: str   (ISO timestamp of last check)
  health_live_hash:   str   (hash observed during check)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from playwright.async_api import Page

# Module-level import so tests can patch it via the standard path.
from browsermind_core.runtime.page_state_extractor import PageStateExtractor

log = logging.getLogger(__name__)


def _utc_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class TemplateHealthResult:
    status: str                         # "healthy" | "stale" | "corrupted" | "unknown"
    drift_score: Optional[float]        # None if check could not run
    live_hash: Optional[str]
    recorded_hash: Optional[str]
    checked_iso: str = field(default_factory=_utc_iso)
    error: Optional[str] = None

    @property
    def is_healthy(self) -> bool:
        return self.status == "healthy"

    @property
    def needs_rerecord(self) -> bool:
        return self.status in ("stale", "corrupted")


# ---------------------------------------------------------------------------
# Compile-time stamp helper (called by the template compiler, not the monitor)
# ---------------------------------------------------------------------------

def stamp_template(template: Any, compile_url: str, signals: Any) -> None:
    """
    Write affordance fingerprint data into template.metadata at compile time.

    Call this from the template compiler immediately after navigating to the
    landing page so future health checks have a baseline to compare against.

    Args:
        template:     WorkflowTemplate instance (must have a .metadata dict).
        compile_url:  The URL that was navigated to during compilation.
        signals:      PageStateSignals captured at compile time.
    """
    from browsermind_core.runtime.structural_fingerprint import (
        affordance_vector,
        vector_to_hash,
    )
    vec = affordance_vector(signals)
    template.metadata["compile_time_affordances"] = vec
    template.metadata["compile_time_hash"]        = vector_to_hash(vec)
    template.metadata["compile_time_url"]         = compile_url
    template.metadata["compile_time_iso"]         = _utc_iso()


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

class TemplateHealthMonitor:
    """
    Checks whether a compiled WorkflowTemplate is still valid against its
    live site.

    Usage:
        monitor = TemplateHealthMonitor()
        result  = await monitor.check(template, page)
        if result.needs_rerecord:
            await trigger_rerecord_workflow(template)
    """

    STALE_THRESHOLD   = 0.30   # drift ≥ this → stale
    CORRUPT_THRESHOLD = 0.70   # drift ≥ this → corrupted

    def __init__(self, nav_timeout_ms: int = 15_000) -> None:
        self._nav_timeout_ms = nav_timeout_ms

    async def check(
        self,
        template: Any,
        page: "Page",
    ) -> TemplateHealthResult:
        """
        Navigate to the template's compile-time URL and compare the live
        affordance vector against the recorded one.

        The page is left at the landing URL after the check.
        """
        recorded_vec: Optional[List[str]] = template.metadata.get("compile_time_affordances")
        recorded_hash: Optional[str]      = template.metadata.get("compile_time_hash")
        compile_url: Optional[str]        = template.metadata.get("compile_time_url")

        if not recorded_vec and not compile_url:
            # Template was compiled before stamping was added — cannot check.
            return TemplateHealthResult(
                status="unknown",
                drift_score=None,
                live_hash=None,
                recorded_hash=recorded_hash,
                error="no compile_time_affordances in template metadata",
            )

        # If we have a URL but no vector, try to find the navigate step.
        if not compile_url:
            compile_url = self._find_nav_url(template)
        if not compile_url:
            return TemplateHealthResult(
                status="unknown",
                drift_score=None,
                live_hash=None,
                recorded_hash=recorded_hash,
                error="could not determine landing URL from template steps",
            )

        # Navigate
        try:
            await page.goto(compile_url, timeout=self._nav_timeout_ms, wait_until="domcontentloaded")
        except Exception as exc:
            return TemplateHealthResult(
                status="unknown",
                drift_score=None,
                live_hash=None,
                recorded_hash=recorded_hash,
                error=f"navigation failed: {exc}",
            )

        # Extract live fingerprint
        try:
            from browsermind_core.runtime.structural_fingerprint import (
                affordance_vector,
                vector_distance,
                vector_to_hash,
            )
            signals = await PageStateExtractor().extract(page)
            live_vec  = affordance_vector(signals)
            live_hash = vector_to_hash(live_vec)
        except Exception as exc:
            return TemplateHealthResult(
                status="unknown",
                drift_score=None,
                live_hash=None,
                recorded_hash=recorded_hash,
                error=f"signal extraction failed: {exc}",
            )

        # If only the hash was stored (older templates), we can't do vector comparison.
        if not recorded_vec:
            # Fall back to binary match/no-match on hash.
            drift = 0.0 if live_hash == recorded_hash else 0.5
        else:
            drift = vector_distance(recorded_vec, live_vec)

        if drift >= self.CORRUPT_THRESHOLD:
            status = "corrupted"
        elif drift >= self.STALE_THRESHOLD:
            status = "stale"
        else:
            status = "healthy"

        result = TemplateHealthResult(
            status=status,
            drift_score=drift,
            live_hash=live_hash,
            recorded_hash=recorded_hash,
        )

        # Write result back into template.metadata so the ledger can query it.
        template.metadata["health_status"]      = status
        template.metadata["health_drift_score"] = drift
        template.metadata["health_checked_iso"] = result.checked_iso
        template.metadata["health_live_hash"]   = live_hash

        log.info(
            "TemplateHealthMonitor: template=%s status=%s drift=%.3f url=%s",
            getattr(template, "id", "?"),
            status,
            drift,
            compile_url,
        )
        return result

    def _find_nav_url(self, template: Any) -> Optional[str]:
        """Extract the URL from the first navigate step in template.steps."""
        for step in getattr(template, "steps", []):
            if isinstance(step, dict) and step.get("action_type") == "navigate":
                return step.get("url") or step.get("value")
        return None

    async def check_batch(
        self,
        templates: List[Any],
        page: "Page",
    ) -> Dict[str, TemplateHealthResult]:
        """
        Check a list of templates sequentially (one page instance, multiple navs).
        Returns {template_id_str: TemplateHealthResult}.
        """
        results: Dict[str, TemplateHealthResult] = {}
        for tpl in templates:
            tid = str(getattr(tpl, "id", id(tpl)))
            try:
                results[tid] = await self.check(tpl, page)
            except Exception as exc:
                results[tid] = TemplateHealthResult(
                    status="unknown",
                    drift_score=None,
                    live_hash=None,
                    recorded_hash=None,
                    error=str(exc),
                )
        return results
