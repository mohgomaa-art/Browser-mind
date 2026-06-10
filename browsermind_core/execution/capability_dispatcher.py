"""
capability_dispatcher.py — Resolves a capability_hash to a WorkflowTemplate and
hands it off to ReplayEngine for execution.

This is the bridge between the L14 Planning layer (GoalDecomposer) and the L10
Replay layer (ReplayEngine).  It is intentionally thin: it does NOT implement
retry logic (that lives in ReplayHardening) or verification (VerifierPipeline).

Resolution order for capability_hash → WorkflowTemplate:
  1. WorkflowStore.find_by_capability(capability_hash, site_key)
  2. Exact name lookup via WorkflowStore.lookup_template(capability_hash)
  3. None — the capability is unknown and cannot be dispatched.

When a WorkflowTemplate is found, CapabilityDispatcher:
  a. Creates a new WorkflowInstance from the template.
  b. Calls ReplayEngine.replay(site, template, instance).
  c. Returns a DispatchResult with success/failure and the replay report.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from playwright.async_api import Page

    from browsermind_core.ontology.p1_schemas import WorkflowTemplate
    from browsermind_core.ontology.workflow_store import WorkflowStore
    from browsermind_core.runtime.replay_engine import ReplayEngine


@dataclass
class DispatchResult:
    """
    Outcome of a single capability dispatch.

    Fields:
        capability_hash:  The capability_hash that was dispatched.
        success:          True if replay completed without error.
        template_name:    Name of the resolved WorkflowTemplate (or "" if none).
        report:           The ReplayReport returned by ReplayEngine (or None).
        error:            Error string when success=False.
        skipped:          True when no template was found (capability not learned yet).
    """
    capability_hash: str
    success: bool
    template_name: str = ""
    report: Optional[Any] = None
    error: str = ""
    skipped: bool = False

    def summary(self) -> str:
        if self.skipped:
            return f"[SKIP] {self.capability_hash} — no template found"
        status = "OK" if self.success else "FAIL"
        return f"[{status}] {self.capability_hash} via '{self.template_name}'"


class CapabilityDispatcher:
    """
    Dispatches a single capability_hash to ReplayEngine.

    Args:
        workflow_store:  WorkflowStore for template resolution.
        replay_engine:   ReplayEngine instance (already wired to a Playwright page).
        site_key:        Optional site key for site-specific template preference.
        persona_id:      UUID of the active persona, forwarded to instance creation.
        store_dir:       Store directory for WorkflowInstance persistence.
    """

    def __init__(
        self,
        workflow_store: "WorkflowStore",
        replay_engine: "ReplayEngine",
        site_key: str = "",
        persona_id: Optional[str] = None,
        store_dir: str = "",
    ) -> None:
        self._store = workflow_store
        self._replay = replay_engine
        self._site_key = site_key
        self._persona_id = persona_id or str(uuid4())
        self._store_dir = store_dir

    async def dispatch(
        self,
        capability_hash: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> DispatchResult:
        """
        Resolve capability_hash → template → execute.

        Args:
            capability_hash:  The key to look up in the WorkflowStore.
            context:          Optional extra context forwarded to replay (unused
                              by the current ReplayEngine but reserved for future
                              template parameterisation).
        """
        # 1. Resolve template
        template, template_name = await self._resolve_template(capability_hash)
        if template is None:
            return DispatchResult(
                capability_hash=capability_hash,
                success=False,
                skipped=True,
                error=f"No WorkflowTemplate found for capability_hash='{capability_hash}'",
            )

        # 2. Create a workflow instance
        try:
            instance = self._store.create_instance(
                name=f"dispatch_{capability_hash}_{uuid4().hex[:6]}",
                persona_id=UUID(self._persona_id),
                template_id=template.id,
            )
        except Exception as exc:
            return DispatchResult(
                capability_hash=capability_hash,
                success=False,
                template_name=template_name,
                error=f"Instance creation failed: {exc}",
            )

        # 3. Hand off to ReplayEngine
        try:
            report = await self._replay.replay(
                site=self._site_key or "unknown",
                template=template,
                instance=instance,
            )
            success = getattr(report, "status", None) == "SUCCESS"
            return DispatchResult(
                capability_hash=capability_hash,
                success=success,
                template_name=template_name,
                report=report,
                error="" if success else getattr(report, "failure_reason", "replay failed"),
            )
        except Exception as exc:
            return DispatchResult(
                capability_hash=capability_hash,
                success=False,
                template_name=template_name,
                error=f"ReplayEngine raised: {exc}",
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _resolve_template(
        self,
        capability_hash: str,
    ) -> tuple:
        """Return (WorkflowTemplate | None, name_str)."""
        # find_by_capability: family_key / name substring match
        entry = self._store.find_by_capability(capability_hash, self._site_key or None)
        if entry:
            from uuid import UUID as _UUID
            tpl = self._store.get_template(_UUID(entry["id"]))
            if tpl:
                return tpl, entry.get("name", capability_hash)

        # exact name match
        entry2 = self._store.lookup_template(capability_hash)
        if entry2:
            from uuid import UUID as _UUID
            tpl2 = self._store.get_template(_UUID(entry2["id"]))
            if tpl2:
                return tpl2, entry2.get("name", capability_hash)

        return None, ""
