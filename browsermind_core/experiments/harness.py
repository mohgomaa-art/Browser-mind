"""ReplayExperimentHarness — record, compile, replay, collect metrics."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional
from uuid import UUID, uuid4

from browsermind_core.console.session import DEFAULT_STORE, KernelSession
from browsermind_core.experiments.descriptor_entropy import descriptor_entropy
from browsermind_core.experiments.failure_taxonomy import classify_failure
from browsermind_core.experiments.ground_truth import GroundTruthDataset
from browsermind_core.experiments.reliability_metrics import (
    RESOLVED_CORRECT,
    RESOLVED_INCORRECT,
    RESOLVED_UNJUDGED,
    compute_replay_reliability_metrics,
)
from browsermind_core.experiments.replay_result import ReplayResult
from browsermind_core.experiments.sites import ExperimentSite, get_site
from browsermind_core.ontology.p1_schemas import ReplayReport, WorkflowInstance, WorkflowTemplate
from browsermind_core.recorder.demonstration_compiler import DemonstrationCompiler
from browsermind_core.recorder.demonstration_repository import DemonstrationRepository
from browsermind_core.recorder.demonstration_session import DemonstrationSession
from browsermind_core.recorder.record_runner import run_recording_session
from browsermind_core.runtime.auth_session import AuthSession
from browsermind_core.runtime.environment_registry import resolve
from browsermind_core.runtime.replay_engine import ReplayEngine
from browsermind_core.runtime.semantic_transfer import SemanticTransferLayer


class ReplayExperimentHarness:
    """
    Orchestrates one replay validation experiment.

    Uses existing Recorder, Compiler, and ReplayEngine — no new abstractions.
    """

    def __init__(self, store_dir: str = DEFAULT_STORE, *, headless: bool = False, persona_id: str = "default"):
        self.store_dir = store_dir
        self.headless = headless
        self.persona_id = persona_id
        self.kernel = KernelSession(store_dir)
        self.demo_repo = DemonstrationRepository(store_dir)
        from browsermind_core.runtime.auth_session import AuthSessionManager
        self.auth_manager = AuthSessionManager(Path(store_dir))

    async def aclose(self) -> None:
        """End-of-batch cleanup. Closes every AuthSession owned by this harness.

        M5+M6+M7: ReplayEngine instances are constructed with
        owns_session=False so the underlying browser process survives
        across consecutive replays of the same (persona, env). Callers
        must invoke aclose() once they are done driving replays.
        """
        try:
            await self.auth_manager.close_all()
        except Exception:
            pass

    async def record(self, site: ExperimentSite) -> DemonstrationSession:

        print(f"\n--- RECORD: {site.label} ({site.key}) ---")
        print(f"Hint: {site.operator_hint}")
        return await run_recording_session(
            self.store_dir,
            site.key,
            self.persona_id,
            headless=self.headless,
        )

    def compile(self, session: DemonstrationSession, template_name: str) -> WorkflowTemplate:
        print(f"\n--- COMPILE: {template_name} ---")
        compiler = DemonstrationCompiler(self.kernel)
        return compiler.compile(session, template_name)

    def load_template(self, template_name: str) -> WorkflowTemplate:
        entry = self.kernel.workflow_store.lookup_template(template_name)
        if not entry:
            raise ValueError(f"Template '{template_name}' not found in store.")
        return self.kernel.workflow_store.get_template(entry["id"])

    async def replay(
        self,
        site: ExperimentSite,
        template: WorkflowTemplate,
        instance: Optional[WorkflowInstance] = None,
        enable_recovery: bool = True,
        on_before_resolve: Optional[Any] = None,
        start_step_index: int = 0,
        is_resume: bool = False
    ) -> ReplayReport:
        print(f"\n--- REPLAY: {site.label} / {template.name} ---")
        
        from browsermind_core.runtime.environment_registry import resolve
        entry = resolve(site.key)
        if not entry:
            raise ValueError(f"Environment '{site.key}' is not registered.")
            
        if not instance:
            instance = WorkflowInstance(
                id=uuid4(),
                persona_id=uuid4(),
                template_id=template.id,
                bound_resources={},
                bound_identities={},
            )
        auth_session = self.auth_manager.get_or_create(
            entry=entry,
            persona_name=self.persona_id,
            headless=self.headless
        )
        engine = ReplayEngine(auth_session, on_before_resolve=on_before_resolve, owns_session=False)
        return await engine.replay(site, template, instance, enable_recovery=enable_recovery, start_step_index=start_step_index, is_resume=is_resume)

    def result_from_report(
        self,
        *,
        site: ExperimentSite,
        template: WorkflowTemplate,
        report: ReplayReport,
        demonstration_id: Optional[UUID] = None,
        ground_truth: Optional[GroundTruthDataset] = None,
    ) -> ReplayResult:
        failed_step_seq, failed_step_def = self._failed_step_info(template, report)
        category, normalized_reason = classify_failure(
            failure_reason=report.failure_reason,
            failed_step=failed_step_def,
        )

        total = report.total_steps
        resolved = report.resolved_steps
        failed = report.failed_steps
        rate = report.resolution_rate if total else 0.0
        workflow_failed = not self._replay_success(report, total)
        replay_success = not workflow_failed

        # Build per-step outcome vector from failure_attribution.
        # Steps the engine ran: SUCCESS -> correctness-split resolution outcome,
        # FAILED -> taxonomy category. Steps the engine never reached are SKIPPED.
        step_outcomes = []
        ran_seqs = {attr.step_seq for attr in report.failure_attribution}
        for attr in report.failure_attribution:
            if attr.actual_outcome == "SUCCESS":
                outcome_str = self._resolution_outcome_from_ground_truth(
                    site=site,
                    template=template,
                    report=report,
                    attr=attr,
                    ground_truth=ground_truth,
                )
            elif attr.actual_outcome == "TRANSITION_SUCCESS":
                outcome_str = self._resolution_outcome_from_ground_truth(
                    site=site,
                    template=template,
                    report=report,
                    attr=attr,
                    ground_truth=ground_truth,
                )
            elif attr.actual_outcome == "AMBIGUOUS_IDENTITY":
                outcome_str = "AMBIGUOUS_IDENTITY"
            else:
                step_def = next(
                    (s for s in template.steps if s.get("seq") == attr.step_seq), None
                )
                cat, _ = classify_failure(
                    failure_reason=attr.failure_reason,
                    failed_step=step_def,
                )
                outcome_str = cat.value

            ti = getattr(attr, "target_integrity", None) or {}
            step_def = next((s for s in template.steps if s.get("seq") == attr.step_seq), {})
            desc = step_def.get("descriptor") or {}
            entropy = descriptor_entropy(
                {
                    **desc,
                    "role": attr.role,
                    "name": attr.name,
                    "container_label": (ti.get("selection_forensics") or {}).get("container_label")
                    or desc.get("container_label"),
                }
            )
            latency_ms = getattr(attr, "resolution_latency_ms", None)
            if latency_ms is None:
                latency_ms = getattr(attr, "resolution_time_ms", None)
            candidate_scans = getattr(attr, "resolution_candidate_scans", None)
            if candidate_scans is None:
                candidate_scans = ti.get("resolution_candidate_scans", ti.get("candidate_count", 0))
            resolution_passes = getattr(attr, "resolution_passes", None)
            if resolution_passes is None:
                depth = getattr(attr, "resolution_depth", None)
                resolution_passes = 0 if depth is None else int(depth) + 1
            step_outcomes.append({
                "seq": attr.step_seq,
                "action_type": attr.action_type,
                "role": attr.role,
                "name": attr.name,
                "outcome": outcome_str,
                "resolved_by": getattr(attr, "resolved_by", None),
                "resolution_depth": getattr(attr, "resolution_depth", None),
                "resolution_time_ms": getattr(attr, "resolution_time_ms", None),
                "resolution_candidate_scans": candidate_scans,
                "resolution_passes": resolution_passes,
                "resolution_latency_ms": latency_ms,
                "recovered_by": getattr(attr, "recovered_by", None),
                # Identity Ledger (Task 4)
                "candidate_count": ti.get("candidate_count", 0),
                "identity_confidence": ti.get("identity_confidence", None),
                "resolution_strategy": ti.get("resolution_strategy", None),
                "candidates_info": ti.get("candidates_info", []),
                "descriptor_entropy": entropy,
                "target_integrity": ti,
                # 4-Layer Execution Probes — preserved for downstream analysis.
                # Not consumed by reliability metrics; never overrides outcome.
                "resolution_success": getattr(attr, "resolution_success", None),
                "execution_success": getattr(attr, "execution_success", None),
                "effect_verified": getattr(attr, "effect_verified", None),
                "effect_type": getattr(attr, "effect_type", None),
                "effect_details": getattr(attr, "effect_details", None),
                "failure_layer": getattr(attr, "failure_layer", None),
            })
        # Mark steps the engine never reached
        for step in template.steps:
            seq = step.get("seq", 0)
            if seq not in ran_seqs:
                step_outcomes.append({
                    "seq": seq,
                    "action_type": step.get("action_type", ""),
                    "role": step.get("target_role", ""),
                    "name": step.get("target_name", ""),
                    "outcome": "SKIPPED",
                })
        step_outcomes.sort(key=lambda x: x["seq"])

        # Derive final status
        if report.status in ("INTERRUPTED", "BLOCKED"):
            result_status = report.status
            normalized_reason = report.failure_reason
            category = None
        else:
            result_status = "FAILED" if workflow_failed else "SUCCESS"

        task_completed = self._task_completed(report)
        reliability_metrics = compute_replay_reliability_metrics(
            step_outcomes,
            task_completed=task_completed,
        )

        return ReplayResult(
            workflow_id=report.workflow_id,
            site=site.key,
            status=result_status,
            total_steps=total,
            resolved_steps=resolved,
            failed_steps=failed,
            resolution_rate=round(rate, 4),
            ambiguous_steps=report.ambiguous_steps,
            ambiguity_rate=report.ambiguity_rate,
            resource_resolution_rate=getattr(report, 'resource_resolution_rate', 0.0),
            recovery_rate=getattr(report, 'recovery_rate', None),
            false_positive_resolution_rate=reliability_metrics["false_positive_resolution_rate"],
            resolution_accuracy=reliability_metrics["resolution_accuracy"],
            task_completion_rate=reliability_metrics["task_completion_rate"],
            task_completed=task_completed,
            reliability_metrics=reliability_metrics,
            workflow_failed=workflow_failed,
            replay_success=replay_success,
            failure_reason=normalized_reason if (workflow_failed or result_status in ("INTERRUPTED", "BLOCKED")) else None,
            failure_category=None if (replay_success or result_status in ("INTERRUPTED", "BLOCKED")) else category,
            failed_step=failed_step_seq,
            template_name=template.name,
            demonstration_id=demonstration_id,
            state_inference=report.state_inference.model_dump(mode="json") if report.state_inference else None,
            verification_report=report.verification_report,
            verification_error=report.verification_error,
            step_outcomes=step_outcomes,
        )

    async def run_full(
        self,
        site_key: str,
        *,
        template_name: Optional[str] = None,
        skip_record: bool = False,
        demonstration_id: Optional[str] = None,
        enable_recovery: bool = True,
        on_before_resolve = None,
        ground_truth: Optional[GroundTruthDataset] = None,
    ) -> ReplayResult:
        site = get_site(site_key)
        tpl_name = template_name or site.suggested_workflow

        if skip_record:
            template = self.load_template(tpl_name)
            demo_id = None
        else:
            if demonstration_id:
                session = self.demo_repo.load(UUID(demonstration_id))
                if not session:
                    raise ValueError(f"Demonstration '{demonstration_id}' not found.")
            else:
                session = await self.record(site)
            template = self.compile(session, tpl_name)
            demo_id = session.id

        report = await self.replay(site, template, enable_recovery=enable_recovery, on_before_resolve=on_before_resolve)
        return self.result_from_report(
            site=site,
            template=template,
            report=report,
            demonstration_id=demo_id,
            ground_truth=ground_truth,
        )

    async def run_transfer(
        self,
        template_name: str,
        target_site_key: str,
        intra_site: bool = False,
        enable_recovery: bool = True,
        on_before_resolve = None,
        ground_truth: Optional[GroundTruthDataset] = None,
    ) -> ReplayResult:
        """
        Executes a Semantic Transfer evaluation (WR-X).
        """
        site = get_site(target_site_key)
        template = self.load_template(template_name)
        
        from browsermind_core.runtime.environment_registry import resolve
        entry = resolve(site.key)
        
        # Intra-site means we keep the same target_start_url, but still apply strict forcing
        target_url = entry.start_url if not intra_site else None
        
        template = SemanticTransferLayer.transfer(
            template=template,
            target_start_url=target_url,
            strict_intent_forcing=True
        )

        report = await self.replay(site, template, enable_recovery=enable_recovery, on_before_resolve=on_before_resolve)
        return self.result_from_report(
            site=site,
            template=template,
            report=report,
            demonstration_id=None,
            ground_truth=ground_truth,
        )

    def save_result(self, result: ReplayResult, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{result.site}_{result.timestamp.strftime('%Y%m%dT%H%M%S')}.json"
        path.write_text(json.dumps(result.model_dump(mode="json"), indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _failed_step_info(
        template: WorkflowTemplate,
        report: ReplayReport,
    ) -> tuple[Optional[int], Optional[dict]]:
        for attr in report.failure_attribution:
            if attr.actual_outcome not in ("FAILED", "AMBIGUOUS_IDENTITY"):
                continue
            step_def = next((s for s in template.steps if s.get("seq") == attr.step_seq), None)
            return attr.step_seq, step_def

        if report.failure_reason:
            return None, None
        return None, None

    @staticmethod
    def _verification_verdict(report: ReplayReport) -> Optional[bool]:
        """Read a boolean verification verdict from `report.verification_report`.

        Prefers canonical keys (`state_match`, `verifier_result`) but accepts
        legacy keys (`success`, `passed`, `overall_success`) for backward
        compatibility. Returns None when no usable boolean is present.
        """
        verification = getattr(report, "verification_report", None)
        if not verification:
            return None
        for key in ("state_match", "verifier_result", "success", "passed", "overall_success"):
            if key in verification and verification[key] is not None:
                return bool(verification[key])
        return None

    @staticmethod
    def _replay_success(report: ReplayReport, total: int) -> bool:
        # Verification failure is a hard veto, even when every step is SUCCESS.
        verdict = ReplayExperimentHarness._verification_verdict(report)
        if verdict is False:
            return False
        if total == 0:
            return True
        if report.failure_reason:
            return False
        if len(report.failure_attribution) < total:
            return False
        return all(
            item.actual_outcome in ("SUCCESS", "TRANSITION_SUCCESS")
            for item in report.failure_attribution
        )

    @staticmethod
    def _task_completed(report: ReplayReport) -> Optional[bool]:
        verdict = ReplayExperimentHarness._verification_verdict(report)
        if verdict is not None:
            return verdict
        state = getattr(report, "state_inference", None)
        if state is not None:
            return bool(getattr(state, "match", False))
        return None

    @staticmethod
    def _resolution_outcome_from_ground_truth(
        *,
        site: ExperimentSite,
        template: WorkflowTemplate,
        report: ReplayReport,
        attr: Any,
        ground_truth: Optional[GroundTruthDataset],
    ) -> str:
        if not ground_truth:
            return RESOLVED_UNJUDGED

        annotation = ground_truth.find(
            site=site.key,
            step_seq=attr.step_seq,
            workflow_id=report.workflow_id,
            template_name=template.name,
        )
        if not annotation:
            return RESOLVED_UNJUDGED

        ti = getattr(attr, "target_integrity", None) or {}
        selection_forensics = ti.get("selection_forensics") or {}
        actual = {
            "role": attr.role,
            "name": attr.name,
            "container": selection_forensics.get("container_label") or ti.get("container_label"),
            # Target-identity fallback chain. The runtime populates different
            # fields depending on the step kind:
            #   - DOM elements with text:    resolved_text
            #   - Navigate steps:            url_after / url_before
            #   - Input fills (no innerText): role+name is the only stable identity
            "target": (
                ti.get("resolved_target")
                or ti.get("target_selector")
                or ti.get("resolved_text")
                or ti.get("url_after")
                or ti.get("url_before")
                or f"{attr.role}:{attr.name}"
            ),
        }
        return RESOLVED_CORRECT if annotation.matches_resolution(actual) else RESOLVED_INCORRECT

    @staticmethod
    def load_results(output_dir: Path) -> List[ReplayResult]:
        results: List[ReplayResult] = []
        if not output_dir.exists():
            return results
        for path in sorted(output_dir.glob("*.json")):
            if path.name == "summary.json":
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            if "workflow_id" in payload and "site" in payload:
                results.append(ReplayResult.model_validate(payload))
        return results
