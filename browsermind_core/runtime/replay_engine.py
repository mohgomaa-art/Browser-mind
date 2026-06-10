"""ReplayEngine — P3A/P3.1: Executes a WorkflowTemplate and records FailureAttribution."""
import asyncio
import time
from typing import Dict, Any

from browsermind_core.ontology.p1_schemas import (
    WorkflowTemplate, WorkflowInstance, ReplayReport, FailureAttribution
)
from browsermind_core.runtime.auth_session import AuthSession
from browsermind_core.runtime.target_resolver import TargetResolver, TargetResolutionError, AmbiguousIdentityError
from browsermind_core.runtime.policy_engine import PolicyEngine, PolicyRejectionError, PolicyInterventionRequired
from browsermind_core.runtime.resource_resolver import ResourceResolver, ResourceMissingError
from browsermind_core.runtime.action_executor import ActionExecutor, ActionExecutionError, ActionTransitionSuccess
from browsermind_core.runtime.affordance_executor import AffordanceExecutor, AffordanceExecutionError
from browsermind_core.experiments.state_verifier import collect_evidence, infer_state
from browsermind_core.experiments.env_fingerprinter import fingerprint_environment
from browsermind_core.evaluation.state_verification import StateVerifier, load_verification_config
from browsermind_core.memory.memory_writer import MemoryWriter
from browsermind_core.runtime.intent_family import IntentFamilyMapper
from browsermind_core.runtime.r0_logger import R0Logger
from browsermind_core.ontology.resource_ontology import ResourceClassifier
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

class ReplayEngine:
    """
    P3A/P3.1 Replay Engine.

    For every step:
      1. Read the predicted ReplayabilityAssessment (attached by Compiler).
      2. Attempt to resolve and execute.
      3. Record a FailureAttribution: predicted_tier vs actual_outcome.

    The ReplayReport.failure_attribution list is the primary output of P3.1.
    It answers: "When do our predictions match reality?"
    """

    def __init__(self, auth_session: AuthSession, on_before_resolve = None, *, owns_session: bool = True, outcome_ledger=None, persona_id=None, environment_family: str = "", environment_instance: str = "", execution_engine=None, task_id=None, ground_truth_dataset=None, lesson_reader=None, behavior_audit=None, recovery_registry=None, recovery_candidate_registry=None, auto_pilot=None, skip_failures: bool = False, exploration_mode: bool = False, state_classifier=None, sstg=None):
        """
        Args:
            auth_session: The session that drives this replay.
            on_before_resolve: Optional pre-resolve hook.
            owns_session: When True (default), the engine closes the
                AuthSession in its finally block — preserving existing
                single-shot replay semantics. When False, the caller is
                responsible for the session lifecycle (e.g. running
                multiple replays back-to-back against the same browser
                process). M5+M6+M7 — session continuity.
            outcome_ledger: Optional OutcomeLedger. When provided, every
                replay run writes one OutcomeRecord (scope="workflow_instance")
                with the report's headline metrics. None disables ledger writes.
            persona_id: Optional UUID identifying the persona. Required when
                outcome_ledger is supplied; the OutcomeRecord schema mandates it.
            environment_family / environment_instance: Recorded on the
                OutcomeRecord so cross-run aggregation can group by site.
            execution_engine: Optional ExecutionEngine. When provided alongside
                a task_id, the replay run becomes a durable Execution row
                (start_execution at run start, complete_execution at end,
                fail_execution on early-BLOCKED). None disables episode wiring.
            task_id: Optional UUID. Required to use execution_engine; without
                a task we cannot create an Execution.
            lesson_reader: Optional LessonReader. Notified after each replay's
                step OutcomeRecords land so it can lazily refresh lessons.jsonl.
        """
        self.auth_session = auth_session
        self.on_before_resolve = on_before_resolve
        self.owns_session = owns_session
        self.outcome_ledger = outcome_ledger
        self.persona_id = persona_id
        self.environment_family = environment_family
        self.environment_instance = environment_instance
        self.execution_engine = execution_engine
        self.task_id = task_id
        self._active_execution_id = None
        self.ground_truth_dataset = ground_truth_dataset
        self.lesson_reader = lesson_reader
        self._behavior_audit = behavior_audit
        self._recovery_registry = recovery_registry
        self._recovery_candidate_registry = recovery_candidate_registry
        self.auto_pilot = auto_pilot
        self.skip_failures = bool(skip_failures)
        self.exploration_mode = bool(exploration_mode)
        self._state_classifier = state_classifier
        self._sstg = sstg

        # Phase 3: hardening stack — initialised lazily per replay() call
        # because we need instance.id and page (not available at __init__ time)
        self._hardening = None

        # Human Intervention Runtime — asyncio.Event SET = running, CLEAR = paused
        self._pause_event: asyncio.Event = asyncio.Event()
        self._pause_event.set()
        self._pause_reason: str = ""

    # ── Human Intervention API ────────────────────────────────────────────────

    def pause(self, reason: str = "") -> None:
        """Pause execution after the current step completes."""
        self._pause_reason = reason
        self._pause_event.clear()

    def resume(self) -> None:
        """Resume a paused execution."""
        self._pause_reason = ""
        self._pause_event.set()

    @property
    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    def _start_execution_if_wired(self, template, instance):
        """Open an Execution row at replay start. No-op if engine/task not wired."""
        if self.execution_engine is None or self.task_id is None or self.persona_id is None:
            # When there is no ExecutionEngine at all, assign a synthetic
            # execution_id so OutcomeRecord step rows from this replay share
            # a trajectory even without a full execution lifecycle.
            if self.execution_engine is None and self._active_execution_id is None:
                from uuid import uuid4
                self._active_execution_id = uuid4()
            return
        try:
            execution = self.execution_engine.start_execution(
                task_id=self.task_id,
                workflow_instance_id=instance.id,
                target_template_id=template.id,
                persona_id=self.persona_id,
            )
            self._active_execution_id = execution.id
        except Exception as e:
            print(f"  [ReplayEngine] start_execution failed: {e}")

    def _close_execution_if_wired(self, report):
        """Close the Execution row using the report's terminal status. No-op if not wired."""
        if self.execution_engine is None or self._active_execution_id is None:
            # UI Phase 1 — even if the execution engine isn't wired, clear the
            # live-state file so the Live Workspace shows "idle" once a replay
            # ends. Best-effort; never raises.
            try:
                self._clear_live_state()
            except Exception:
                pass
            return
        exec_id = self._active_execution_id
        try:
            if report.status == "SUCCESS":
                self.execution_engine.complete_execution(exec_id, "success")
            elif report.status in ("BLOCKED", "INTERRUPTED"):
                self.execution_engine.fail_execution(
                    exec_id, report.failure_reason or report.status
                )
            else:  # FAILED
                self.execution_engine.complete_execution(exec_id, "failed")
        except Exception as e:
            print(f"  [ReplayEngine] close_execution failed: {e}")
        finally:
            self._active_execution_id = None
            # UI Phase 1 — clear the live-state file. The Live Workspace will
            # then show "idle" rather than continuing to display the last
            # step of a finished run. Best-effort; never raises.
            try:
                self._clear_live_state()
            except Exception:
                pass

    # ── UI Phase 1 — Live Workspace state writer (read by /live page) ──
    #
    # The Live Workspace polls ~/.browsermind/_live_state.json. We update
    # it at every step boundary with a small JSON snapshot. Atomic write
    # (tmp + replace) so a partial read can never see a torn file.
    # Best-effort: never raises.

    def _live_state_path(self):
        from pathlib import Path
        store = getattr(self.auth_session, "store_dir", None)
        if store is None:
            store = Path.home() / ".browsermind"
        return Path(store) / "_live_state.json"

    def _write_live_state(self, instance, template, seq, action_type, role,
                          name, report, strategy=None,
                          is_paused: bool = False, pause_reason: str = ""):
        import json as _json
        from datetime import datetime, timezone
        path = self._live_state_path()
        try:
            persona_name = getattr(self.auth_session, "persona_name", "")
        except Exception:
            persona_name = ""
        state = {
            "execution_id": str(getattr(self, "_active_execution_id", "") or ""),
            "persona_id": str(getattr(self, "persona_id", "") or ""),
            "persona_name": persona_name,
            "environment_instance": getattr(self, "environment_instance", ""),
            "environment_family": getattr(self, "environment_family", ""),
            "template_name": getattr(template, "name", ""),
            "template_id": str(getattr(template, "id", "") or ""),
            "current_step_seq": seq,
            "current_action": action_type,
            "current_target_role": role,
            "current_target_name": name,
            "current_strategy": strategy,
            "step_count_so_far": (
                getattr(report, "resolved_steps", 0)
                + getattr(report, "failed_steps", 0)
            ),
            "successful_so_far": getattr(report, "resolved_steps", 0),
            "failed_so_far": getattr(report, "failed_steps", 0),
            "total_steps": getattr(report, "total_steps", 0)
                or len(getattr(template, "steps", []) or []),
            "is_paused": is_paused,
            "pause_reason": pause_reason,
            "last_update_ts": datetime.now(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            ),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(_json.dumps(state, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except Exception:
            # Live-state write must never break a replay.
            pass

    def _clear_live_state(self):
        """Remove the live-state file so the Live Workspace shows 'idle'."""
        try:
            p = self._live_state_path()
            if p.exists():
                p.unlink()
        except Exception:
            pass

    def _record_replay_outcome(self, report, template, instance):
        """Write a single workflow-instance OutcomeRecord summarising the run.

        Best-effort: a failure to record must not corrupt the report. The
        replay path returns the report regardless; this hook only adds a
        durable trace alongside it.
        """
        if self.outcome_ledger is None or self.persona_id is None:
            return
        try:
            from browsermind_core.ledger.outcome_ledger import OutcomeRecord
            success = (report.status == "SUCCESS")
            evidence = (
                report.failure_reason
                or f"status={report.status} resolved={report.resolved_steps}/{report.total_steps}"
            )
            metrics = {
                "status": report.status,
                "total_steps": report.total_steps,
                "resolved_steps": report.resolved_steps,
                "failed_steps": report.failed_steps,
                "ambiguous_steps": getattr(report, "ambiguous_steps", 0),
                "resolution_rate": report.resolution_rate,
                "ambiguity_rate": getattr(report, "ambiguity_rate", 0.0),
                "recovery_rate": getattr(report, "recovery_rate", 0.0),
                "duration_seconds": report.duration_seconds,
                "template_id": str(template.id),
                "template_name": getattr(template, "name", ""),
                # ContractGate — outcome verification result.
                # None = no contract registered; True/False = verified result.
                "contract_goal_completed": getattr(self, "_last_contract_result", None),
                "contract_id": getattr(self, "_last_contract_id", None),
            }
            # Investigation A — per-binding-key telemetry. Forward the
            # missing-resource key into the OutcomeLedger so cross-dyad
            # comparison can see *which* binding failed, not just that
            # one failed. Pure forwarding — the runtime already captures
            # this in report.missing_resource.
            missing = getattr(report, "missing_resource", None)
            if missing:
                metrics["failed_binding_key"] = str(missing)
            # Stage 2.1 — Cascade annotation (telemetry only).
            from browsermind_core.ledger.cascade import annotate as _cascade_annotate
            _cascade_annotate(
                metrics,
                scope="workflow_instance",
                template_name=getattr(template, "name", ""),
                environment_instance=self.environment_instance,
            )
            self.outcome_ledger.record(
                OutcomeRecord(
                    scope="workflow_instance",
                    scope_id=instance.id,
                    persona_id=self.persona_id,
                    environment_family=self.environment_family,
                    environment_instance=self.environment_instance,
                    outcome_type="replay_run",
                    success=success,
                    evidence=evidence,
                    metrics=metrics,
                    execution_id=self._active_execution_id,
                )
            )
        except Exception as e:
            print(f"  [ReplayEngine] OutcomeLedger write failed: {e}")

    def _record_replay_accuracy(self, report, template, instance, env_key):
        """Judge each FailureAttribution row against the ground-truth dataset and write
        a second OutcomeRecord summarising correctness (FPR + accuracy).

        Best-effort: ledger write or judging errors must not break the replay return path.
        No-op when no dataset or ledger is wired.
        """
        if self.outcome_ledger is None or self.persona_id is None or self.ground_truth_dataset is None:
            return
        try:
            from browsermind_core.experiments.ground_truth_judge import (
                annotation_summary,
                judge_step_outcomes,
            )
            from browsermind_core.experiments.reliability_metrics import (
                compute_replay_reliability_metrics,
            )
            from browsermind_core.ledger.outcome_ledger import OutcomeRecord
            from browsermind_core.ledger.cascade import annotate as _cascade_annotate

            rows = judge_step_outcomes(
                report,
                self.ground_truth_dataset,
                site=env_key,
                template_name=getattr(template, "name", None),
                workflow_id=instance.id,
            )
            metrics = compute_replay_reliability_metrics(rows)
            counts = annotation_summary(rows)
            success = (
                metrics.get("false_positive_resolution_rate") == 0.0
                and metrics.get("resolution_accuracy") == 1.0
            )
            evidence = (
                f"accuracy={metrics.get('resolution_accuracy')} "
                f"fpr={metrics.get('false_positive_resolution_rate')} "
                f"correct={counts.get('RESOLVED_CORRECT', 0)} "
                f"incorrect={counts.get('RESOLVED_INCORRECT', 0)} "
                f"unjudged={counts.get('RESOLVED_UNJUDGED', 0)}"
            )
            self.outcome_ledger.record(
                OutcomeRecord(
                    scope="workflow_instance",
                    scope_id=instance.id,
                    persona_id=self.persona_id,
                    environment_family=self.environment_family,
                    environment_instance=self.environment_instance,
                    outcome_type="replay_accuracy",
                    success=success,
                    evidence=evidence,
                    metrics=_cascade_annotate(
                        {**metrics, "ground_truth_counts": counts, "template_name": getattr(template, "name", "")},
                        scope="workflow_instance",
                        template_name=getattr(template, "name", ""),
                        environment_instance=self.environment_instance,
                    ),
                    execution_id=self._active_execution_id,
                )
            )
        except Exception as e:
            print(f"  [ReplayEngine] accuracy ledger write failed: {e}")

    def _record_step_outcomes(self, report, template, instance, env_key):
        """Promote every FailureAttribution row to a durable OutcomeRecord(scope='step').

        Per Phase 1 of the BC-readiness plan. Each record carries:
          step_id          deterministic hash of (instance, seq, action) so cross-run
                           aggregation works without a stable runtime id;
          action           action_type (click/fill/press/...);
          success          actual_outcome in {SUCCESS, TRANSITION_SUCCESS};
          failure_class    FailureCategory.value via classify_failure(); None on success;
          root_cause       normalized human-readable failure reason; None on success;
          effect_verified  passed through unchanged (Phase 2 already removed
                           the false-positive paths in the probe block).

        The remainder of FailureAttribution lands in `metrics` so adapters and
        lesson extractors don't need to touch ReplayReport directly.

        Best-effort: ledger errors must not corrupt the replay return path.
        No-op when ledger or persona is not wired.
        """
        if self.outcome_ledger is None or self.persona_id is None:
            return
        if not getattr(report, "failure_attribution", None):
            return
        try:
            import hashlib
            from browsermind_core.ledger.outcome_ledger import OutcomeRecord
            from browsermind_core.experiments.failure_taxonomy import classify_failure

            template_steps = list(getattr(template, "steps", []) or [])
            template_id_str = str(template.id)
            template_name = getattr(template, "name", "")

            for attr in report.failure_attribution:
                success = attr.actual_outcome in ("SUCCESS", "TRANSITION_SUCCESS")

                # Locate the source step from the template; tolerate seq off-by-one.
                template_step = None
                idx0 = attr.step_seq - 1
                if 0 <= idx0 < len(template_steps):
                    template_step = template_steps[idx0]
                elif 0 <= attr.step_seq < len(template_steps):
                    template_step = template_steps[attr.step_seq]

                # Build the classifier input from the FailureAttribution (the
                # runtime source of truth) overlaid on the template step. This
                # ensures role/name reach classify_failure even when the
                # template body lacks them.
                failed_step: Dict[str, Any] = dict(template_step or {})
                if attr.role and not failed_step.get("target_role"):
                    failed_step["target_role"] = attr.role
                if attr.name and not failed_step.get("target_name"):
                    failed_step["target_name"] = attr.name

                if success:
                    failure_class = None
                    root_cause = None
                else:
                    cat, normalized = classify_failure(
                        failure_reason=attr.failure_reason,
                        failed_step=failed_step,
                    )
                    failure_class = cat.value
                    root_cause = normalized

                step_id_seed = f"{instance.id}:{attr.step_seq}:{attr.action_type}"
                step_id_hash = hashlib.sha256(step_id_seed.encode("utf-8")).hexdigest()[:32]

                evidence = (
                    attr.failure_reason
                    or f"{attr.action_type} {attr.actual_outcome} via {attr.resolved_by or 'n/a'}"
                )

                metrics = {
                    "step_id": step_id_hash,
                    "step_seq": attr.step_seq,
                    "action": attr.action_type,
                    "role": attr.role,
                    "name": attr.name,
                    "field_optionality": (template_step or {}).get("optionality"),
                    "predicted_tier": attr.predicted_tier,
                    "predicted_score": attr.predicted_score,
                    "actual_outcome": attr.actual_outcome,
                    "resolved_by": attr.resolved_by,
                    "recovered_by": attr.recovered_by,
                    "resolution_depth": attr.resolution_depth,
                    "resolution_success": attr.resolution_success,
                    "execution_success": attr.execution_success,
                    "effect_type": attr.effect_type,
                    "effect_verified": attr.effect_verified,
                    "quality_score": attr.quality_score,
                    "failure_layer": attr.failure_layer,
                    "failure_class": failure_class,
                    "root_cause": root_cause,
                    "resolution_time_ms": attr.resolution_time_ms,
                    "environment_key": env_key,
                    "template_id": template_id_str,
                    "template_name": template_name,
                    "vault_resolution_path": attr.vault_resolution_path,
                    "step_duration_ms": attr.step_duration_ms,
                    "inter_step_delay_ms": attr.inter_step_delay_ms,
                }
                # Stage 2.1 — Cascade annotation (telemetry only; no
                # execution logic). Adds cascade_layer, cascade_workflow_class,
                # cascade_proxy_for. See browsermind_core/ledger/cascade.py.
                from browsermind_core.ledger.cascade import annotate as _cascade_annotate
                _cascade_annotate(
                    metrics,
                    scope="step",
                    template_name=template_name,
                    environment_instance=env_key,
                )
                # Closed-loop BC: record what the policy WOULD have predicted
                # so future training measures the gap between deterministic
                # outcomes and learned preferences.
                try:
                    from browsermind_core.runtime.bc_policy import shared as _bc_shared
                    _bc = _bc_shared()
                    if _bc.ready:
                        pred = _bc.predict(attr.role, attr.action_type, attr.step_seq, env_key=env_key or "")
                        if pred:
                            metrics["bc_action_pred"] = pred.get("action_label")
                            metrics["bc_strategy_pred"] = pred.get("strategy_label")
                            metrics["bc_action_correct"] = (
                                pred.get("action_label") == (attr.action_type or "").lower()
                            )
                            metrics["bc_strategy_correct"] = (
                                pred.get("strategy_label") == (attr.resolved_by or "").lower()
                            )
                except Exception:
                    pass

                self.outcome_ledger.record(
                    OutcomeRecord(
                        scope="step",
                        scope_id=instance.id,
                        persona_id=self.persona_id,
                        environment_family=self.environment_family,
                        environment_instance=self.environment_instance,
                        outcome_type="step_attempt",
                        success=success,
                        evidence=evidence,
                        metrics=metrics,
                        execution_id=self._active_execution_id,
                    )
                )
            if self.lesson_reader is not None:
                try:
                    self.lesson_reader.notify_steps_recorded(len(report.failure_attribution))
                except Exception:
                    pass
            if self.auto_pilot is not None:
                try:
                    self.auto_pilot.notify_steps_recorded(len(report.failure_attribution))
                except Exception:
                    pass
        except Exception as e:
            print(f"  [ReplayEngine] step OutcomeLedger write failed: {e}")

    # ── Contract Gate ─────────────────────────────────────────────────────────
    # Outcome verification via ContractVerifier.
    # Called between _record_replay_accuracy() and _record_replay_outcome() so
    # the contract result is available for embedding in OutcomeRecord.metrics.
    # Result stored in self._last_contract_result for _record_replay_outcome to
    # consume.  Best-effort: never raises into replay().

    def _verify_contract_outcome(self, page, template, env_key: str) -> None:
        """Run ContractVerifier against the live page and store the result.

        Stores the result in self._last_contract_result (Optional[bool]) and
        self._last_contract_id (Optional[str]) so _record_replay_outcome() can
        embed both into OutcomeRecord.metrics as contract_goal_completed and
        contract_id.

        No contract found → _last_contract_result = None (unverified, not failed).
        Logging prefix: [ContractGate]
        """
        self._last_contract_result = None
        self._last_contract_id = None

        if page is None:
            return
        try:
            from browsermind_core.runtime.contract_verifier import (
                ContractVerifier,
                lookup_contract,
            )
            import asyncio

            template_name = getattr(template, "name", "") or ""
            contract_id_meta = ""
            try:
                contract_id_meta = str((template.metadata or {}).get("contract_id", ""))
            except Exception:
                pass

            contract = lookup_contract(template_name, contract_id_meta, env_key)
            if contract is None:
                print(
                    f"  [ContractGate] No contract for template={template_name!r} env={env_key}; "
                    f"contract_goal_completed=None"
                )
                return

            verifier = ContractVerifier()
            # verify() is a coroutine — run it from synchronous context if needed.
            loop = None
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                pass

            if loop and loop.is_running():
                # We are inside an async context; schedule and await is handled
                # by the caller.  Store a sentinel so _record_replay_outcome
                # knows to call the async variant instead.
                # This path is covered by _verify_contract_outcome_async().
                return

            result = asyncio.run(verifier.verify(page, contract))
            goal_completed = result.get("goal_completed")
            self._last_contract_result = bool(goal_completed) if goal_completed is not None else None
            self._last_contract_id = contract.task_id
            print(
                f"  [ContractGate] template={template_name!r} env={env_key} "
                f"contract={contract.task_id!r} goal_completed={self._last_contract_result}"
            )
        except Exception as exc:
            print(f"  [ContractGate] ERROR (non-fatal): {exc}")

    async def _verify_contract_outcome_async(self, page, template, env_key: str) -> None:
        """Async variant of _verify_contract_outcome for use inside replay().

        replay() is an async method. ContractVerifier.verify() is a coroutine.
        This method must be awaited directly from the replay() async context.
        """
        self._last_contract_result = None
        self._last_contract_id = None

        if page is None:
            return
        try:
            from browsermind_core.runtime.contract_verifier import (
                ContractVerifier,
                lookup_contract,
            )

            template_name = getattr(template, "name", "") or ""
            contract_id_meta = ""
            try:
                contract_id_meta = str((template.metadata or {}).get("contract_id", ""))
            except Exception:
                pass

            contract = lookup_contract(template_name, contract_id_meta, env_key)
            if contract is None:
                print(
                    f"  [ContractGate] No contract for template={template_name!r} env={env_key}; "
                    f"contract_goal_completed=None"
                )
                return

            verifier = ContractVerifier()
            result = await verifier.verify(page, contract)
            goal_completed = result.get("goal_completed")
            self._last_contract_result = bool(goal_completed) if goal_completed is not None else None
            self._last_contract_id = contract.task_id
            print(
                f"  [ContractGate] template={template_name!r} env={env_key} "
                f"contract={contract.task_id!r} goal_completed={self._last_contract_result}"
            )
        except Exception as exc:
            print(f"  [ContractGate] ERROR (non-fatal): {exc}")

    # ── Capability Loop: Addition 1 ───────────────────────────────────────────
    # Post-execution failure pattern mining.
    # Called after _record_step_outcomes() when the execution is terminal.
    # Best-effort: never raises into replay().

    def _mine_step_outcomes(self, execution_id, env_key: str) -> None:
        """Mine failure patterns from this execution's step OutcomeRecords.

        Calls FailurePatternMiner over the step records just written to the
        OutcomeLedger. Any PatternCandidate that clears the miner's lift gate
        is converted to a RecoveryCandidate and registered. This closes the
        first link of the Execution → Experience chain.

        Logging prefix: [CapLoop/Mine]
        """
        if self.outcome_ledger is None or execution_id is None:
            return
        try:
            from browsermind_core.training.failure_pattern_miner import (
                mine_patterns,
                to_recovery_candidate,
            )

            all_step_records = [
                r for r in self.outcome_ledger.list_for_execution(execution_id)
                if getattr(r, "scope", None) == "step"
            ]
            if not all_step_records:
                print(f"  [CapLoop/Mine] No step records for execution={execution_id}; skipping.")
                return

            # OutcomeGate: prefer effect_verified=True records when flag is enabled.
            from browsermind_core.verification.outcome_gate import filter_for_mining
            records, mine_label = filter_for_mining(all_step_records)
            print(f"  [CapLoop/Mine] record_pool={mine_label}")

            # Collect distinct failure classes present in this execution
            failure_classes = {
                str(r.metrics.get("failure_class") or "")
                for r in records
                if not r.success and r.metrics.get("failure_class")
            }
            if not failure_classes:
                print(f"  [CapLoop/Mine] No failures in execution={execution_id}; skipping.")
                return

            candidates_emitted = 0
            for fc in failure_classes:
                # min_support=1 so single-execution runs always mine;
                # min_lift uses the miner's default (2.0).
                patterns = mine_patterns(records, failure_class=fc, min_support=1, min_lift=2.0)
                for pat in patterns:
                    rc = to_recovery_candidate(
                        pat,
                        name_hint=f"exec:{str(execution_id)[:8]}:{fc}",
                    )
                    if self._recovery_candidate_registry is not None:
                        self._recovery_candidate_registry.save(rc)
                        candidates_emitted += 1

            print(
                f"  [CapLoop/Mine] execution={str(execution_id)[:8]} env={env_key} "
                f"failure_classes={sorted(failure_classes)} "
                f"candidates_emitted={candidates_emitted}"
            )

            # Boundary Law: extract capability boundaries from all failure records
            # and persist them onto ProceduralRecord.known_boundaries.
            # This closes the gap: failures now narrow the scope of capability hypotheses.
            try:
                from browsermind_core.learning.capability_boundary import (
                    extract_boundaries_from_failures,
                    merge_boundaries,
                )
                from browsermind_core.memory.memory_store import MemoryStore
                from browsermind_core.memory.procedural import ProceduralRecord

                failure_records = [r for r in all_step_records if not r.success]
                boundaries = extract_boundaries_from_failures(
                    failure_records, environment_instance=env_key
                )
                if boundaries:
                    mem_store = MemoryStore(persona_id=str(self.persona_id or "default"))
                    # Group boundaries by capability_hint and write/update ProceduralRecords
                    from collections import defaultdict
                    by_hint = defaultdict(list)
                    for b in boundaries:
                        by_hint[b.capability_hint].append(b)

                    boundaries_written = 0
                    for cap_hint, cap_boundaries in by_hint.items():
                        # Create a minimal ProceduralRecord to carry the boundaries.
                        # Step action and intent_family are inferred from the failure records.
                        sample_rec = next(
                            (r for r in failure_records
                             if str(r.metrics.get("name") or r.metrics.get("role") or "") == cap_hint),
                            None
                        )
                        action = str((sample_rec.metrics.get("action") if sample_rec else None) or "")
                        intent_fam = str((sample_rec.metrics.get("role") if sample_rec else None) or "UNKNOWN")
                        if not action:
                            continue
                        proc = ProceduralRecord(
                            environment_key=env_key,
                            intent_family=intent_fam,
                            capability_hint=cap_hint,
                            step_action=action,
                            strategy_counts={},
                            known_boundaries=[b.to_dict() for b in cap_boundaries],
                        )
                        mem_store.update_procedural(proc)
                        boundaries_written += len(cap_boundaries)

                    print(
                        f"  [CapLoop/Mine] Boundary Law: {len(boundaries)} boundaries "
                        f"across {len(by_hint)} capability hints written (env={env_key})"
                    )
            except Exception as boundary_exc:
                print(f"  [CapLoop/Mine] Boundary extraction ERROR (non-fatal): {boundary_exc}")

        except Exception as exc:
            print(f"  [CapLoop/Mine] ERROR (non-fatal): {exc}")

    # ── Capability Loop: Additions 2 + 3 ─────────────────────────────────────
    # InvariantCompiler + PromotionRules arbiter.
    # Runs after mining. Reconstructs pseudo-templates from this execution's
    # successful step records, strips identity signals, compiles an
    # InvariantGraph, evaluates promotion gates, and writes a ProceduralRecord
    # if the template clears CANDIDATE tier.
    # Best-effort: never raises into replay().

    def _compile_and_promote(self, template: WorkflowTemplate, env_key: str) -> None:
        """Compile an InvariantGraph from this execution and evaluate promotion.

        Data flow:
          OutcomeRecord(scope=step, success=True)
            → SemanticTransferLayer.transfer()    [strip identity signals]
            → InvariantCompiler.compile_from_templates()
            → evaluate_candidate()                [promotion gates]
            → MemoryStore.update_procedural()     [if CANDIDATE or above]

        This closes Execution → Capability → Reuse (Additions 2 + 3).

        Logging prefix: [CapLoop/Compile]
        """
        if self.outcome_ledger is None or self._active_execution_id is None:
            return
        try:
            from browsermind_core.representation.invariant_compiler import InvariantCompiler
            from browsermind_core.runtime.semantic_transfer import SemanticTransferLayer
            from browsermind_core.representation.promotion_rules import evaluate_candidate, PromotionTier
            from browsermind_core.memory.memory_store import MemoryStore
            from browsermind_core.memory.procedural import ProceduralRecord

            template_id_str = str(template.id)

            # Collect successful step records for this execution
            all_success_records = [
                r for r in self.outcome_ledger.list_for_execution(self._active_execution_id)
                if getattr(r, "scope", None) == "step" and r.success
            ]
            if not all_success_records:
                print(f"  [CapLoop/Compile] No successful steps for template={template_id_str[:8]}; skipping.")
                return

            # OutcomeGate: filter to verified records for compilation when flag enabled.
            from browsermind_core.verification.outcome_gate import (
                filter_for_compilation,
                resolve_stress_test,
            )
            from browsermind_core.runtime.contract_verifier import lookup_contract

            success_records, compile_label, compiled_from_verified = filter_for_compilation(all_success_records)
            print(f"  [CapLoop/Compile] compile_pool={compile_label}")

            # Build one pseudo-template per execution from the step records.
            # Group records by execution_id to produce distinct demonstrations.
            from collections import defaultdict
            by_exec = defaultdict(list)
            for r in success_records:
                by_exec[str(r.execution_id)].append(r)

            # Reconstruct WorkflowTemplate-like objects from step record metrics.
            # InvariantCompiler only reads step["action_type"], step["target_role"],
            # step["target_name"], and step["seq"] — so minimal reconstruction is safe.
            from browsermind_core.ontology.p1_schemas import WorkflowTemplate as WFTemplate
            import uuid as _uuid

            pseudo_templates = []
            for _exec_id, recs in by_exec.items():
                recs_sorted = sorted(recs, key=lambda r: r.metrics.get("step_seq", 0))
                steps = [
                    {
                        "action_type": r.metrics.get("action", ""),
                        "target_role": r.metrics.get("role", ""),
                        "target_name": r.metrics.get("name", ""),
                        "seq": r.metrics.get("step_seq", 0),
                    }
                    for r in recs_sorted
                ]
                pseudo_templates.append(
                    WFTemplate(
                        id=_uuid.UUID(str(_exec_id)) if _exec_id and len(_exec_id) == 36 else _uuid.uuid4(),
                        name=template.name,
                        description="",
                        steps=steps,
                    )
                )

            if not pseudo_templates:
                return

            # Strip identity signals from every pseudo-template
            stripped = []
            for pt in pseudo_templates:
                try:
                    stripped.append(
                        SemanticTransferLayer.transfer(pt, target_start_url="", strict_intent_forcing=True)
                    )
                except Exception:
                    stripped.append(pt)  # fall back to un-stripped if transfer fails

            # Compile InvariantGraph
            compiler = InvariantCompiler(variant_threshold=0.5, collapse_level=1)
            graph = compiler.compile_from_templates(goal_id=template_id_str, templates=stripped)

            print(
                f"  [CapLoop/Compile] template={template_id_str[:8]} env={env_key} "
                f"demos={graph.demonstrations_count} "
                f"invariants={len(graph.invariants)} variants={len(graph.variants)} noise={len(graph.noise)}"
            )

            if not graph.invariants and not graph.variants:
                print(f"  [CapLoop/Compile] Empty graph; skipping promotion.")
                return

            # Evaluate promotion gates.
            # With a single execution: rediscovery=1, cohesion=1.0, diversity=1.
            # stress_test is stubbed True — this is logged explicitly.
            rediscovery = len(by_exec)
            source_diversity = len({
                r.environment_instance
                for r in success_records
                if r.environment_instance
            }) or 1

            # Boost counts using the persisted CapabilityRecord's historical
            # transfer_envs — each distinct environment that has seen this hash
            # already counts as a prior rediscovery.
            try:
                _hist_mem = MemoryStore(persona_id=str(self.persona_id or "default"))
                _existing_cap = _hist_mem.get_capability_by_hash(graph.invariant_hash)
                if _existing_cap is not None:
                    hist_envs = set(_existing_cap.transfer_envs or [])
                    if env_key:
                        hist_envs.add(env_key)
                    rediscovery = max(rediscovery, len(hist_envs))
                    source_diversity = max(source_diversity, len(hist_envs))
            except Exception:
                pass

            # ContractGate: resolve stress_test_passed from contract verification ratio.
            # When OUTCOME_GATE_PROMOTION env flag is off: returns (True, "STUBBED").
            # When on: returns (True, "ratio=X.XX") iff contract_verified_ratio >= 0.80,
            #          else (False, "no_contract") or (False, "ratio=X.XX below threshold").
            _execution_scope_records = [
                r for r in self.outcome_ledger.list_for_execution(self._active_execution_id)
                if getattr(r, "scope", None) == "workflow_instance"
            ]
            _has_contract = lookup_contract(
                getattr(template, "name", ""),
                str((template.metadata or {}).get("contract_id", "")),
                env_key,
            ) is not None
            stress_test_passed, stress_reason = resolve_stress_test(
                template_name=getattr(template, "name", ""),
                env_key=env_key,
                execution_records=_execution_scope_records,
                has_contract=_has_contract,
            )
            print(
                f"  [CapLoop/Compile] stress_test={stress_test_passed} reason={stress_reason!r} "
                f"(rediscovery={rediscovery}, source_diversity={source_diversity})"
            )

            gate = evaluate_candidate(
                candidate=template_id_str,
                rediscovery_count=rediscovery,
                semantic_cohesion=1.0,
                source_diversity=source_diversity,
                stress_test_passed=stress_test_passed,
            )

            print(
                f"  [CapLoop/Compile] Promotion gate: tier={gate.current_tier.value} "
                f"missing_strong={gate.missing_for_strong} missing_review={gate.missing_for_review}"
            )

            # Write ProceduralRecords for all invariant intents when gate >= CANDIDATE.
            # CANDIDATE is the entry tier (rediscovery >= 1), which any single execution
            # satisfies. This means every successful execution seeds a ProceduralRecord.
            if gate.current_tier in (
                PromotionTier.CANDIDATE,
                PromotionTier.STRONG_CANDIDATE,
                PromotionTier.ELIGIBLE_FOR_REVIEW,
            ):
                mem_store = MemoryStore(persona_id=str(self.persona_id or "default"))
                written = 0
                for r in success_records:
                    strat = r.metrics.get("resolved_by") or r.metrics.get("resolution_strategy") or ""
                    action = r.metrics.get("action", "")
                    cap_hint = r.metrics.get("name", "") or ""
                    intent_fam = r.metrics.get("role", "") or "UNKNOWN"
                    if not strat or not action:
                        continue
                    proc = ProceduralRecord(
                        environment_key=env_key,
                        intent_family=intent_fam,
                        capability_hint=cap_hint,
                        step_action=action,
                        strategy_counts={
                            strat: {"success": 1, "failure": 0}
                        },
                    )
                    mem_store.update_procedural(proc)
                    written += 1

                print(
                    f"  [CapLoop/Compile] ProceduralRecords written: {written} "
                    f"(env={env_key}, tier={gate.current_tier.value})"
                )

                # CapabilityRecord: write the capability as a first-class object
                # keyed by structural hash.  This inverts the prior architecture:
                # the unit being promoted is the capability, not the workflow template.
                try:
                    from browsermind_core.learning.capability_record import CapabilityRecord

                    _tier_map = {
                        PromotionTier.CANDIDATE: "CANDIDATE",
                        PromotionTier.STRONG_CANDIDATE: "STRONG",
                        PromotionTier.ELIGIBLE_FOR_REVIEW: "VALIDATED",
                    }
                    cap_tier = _tier_map.get(gate.current_tier, "CANDIDATE")
                    cap_record = CapabilityRecord(
                        invariant_hash=graph.invariant_hash,
                        invariants=list(graph.invariants),
                        promotion_tier=cap_tier,
                        transfer_envs=[env_key] if env_key else [],
                        source_templates=[template_id_str],
                        source="compilation",
                    )
                    # Attach latest contract ratio when available
                    if compiled_from_verified:
                        from browsermind_core.verification.outcome_gate import contract_verified_ratio
                        _ratio = contract_verified_ratio(_execution_scope_records)
                        if _ratio is not None:
                            cap_record.contract_verified_ratio = _ratio
                    mem_store.update_capability(cap_record)
                    print(
                        f"  [CapLoop/Compile] CapabilityRecord written: "
                        f"hash={graph.invariant_hash} tier={cap_tier} "
                        f"invariants={len(graph.invariants)} (env={env_key})"
                    )
                except Exception as cap_exc:
                    print(f"  [CapLoop/Compile] CapabilityRecord write ERROR (non-fatal): {cap_exc}")

        except Exception as exc:
            print(f"  [CapLoop/Compile] ERROR (non-fatal): {exc}")

    # ── Capability Loop: Addition 5 ───────────────────────────────────────────
    # Capability-level validation — mid-execution state transition check.
    # Called after _record_step_outcomes() so the step record set is complete.
    # For each known CapabilityRecord whose invariant set is a subset of the
    # completed step intents in this execution, run CapabilityVerifier.
    # Best-effort: never raises into replay().

    async def _verify_capabilities_in_execution(
        self, page, env_key: str, completed_intent_set: set
    ) -> None:
        """Check capability-level contracts for all capabilities exercised this run.

        A capability is considered "exercised" when its full invariant set is a
        subset of the intent tokens produced by the steps completed in this
        execution. For each such capability, look up a CapabilityContract keyed
        by invariant_hash and run CapabilityVerifier.

        Results are logged but not (yet) written to the OutcomeLedger — the
        data model extension for capability-scope records is a follow-on task.

        Logging prefix: [CapLoop/CapVerify]
        """
        if page is None or not env_key or self.persona_id is None:
            return
        try:
            from browsermind_core.memory.memory_store import MemoryStore
            from browsermind_core.learning.capability_contract import (
                lookup_capability_contract,
                CapabilityVerifier,
            )

            mem_store = MemoryStore(persona_id=str(self.persona_id or "default"))
            capabilities = mem_store.load_capabilities()
            if not capabilities:
                return

            verifier = CapabilityVerifier()
            verified_count = 0
            checked_count = 0

            for inv_hash, cap_record in capabilities.items():
                cap_invariants = set(cap_record.invariants)
                if not cap_invariants:
                    continue
                # Only check capabilities whose full invariant set was exercised
                if not cap_invariants.issubset(completed_intent_set):
                    continue

                contract = lookup_capability_contract(inv_hash)
                if contract is None:
                    continue

                checked_count += 1
                try:
                    result = await verifier.verify(page, contract)
                    transition_verified = result.get("transition_verified", False)
                    if transition_verified:
                        verified_count += 1
                        # Reward Layer 4: increment reuse_count and update transfer_envs
                        cap_record.record_reuse(env_key)
                        # Reward Layer 3: mark novelty once if not yet set
                        if cap_record.is_novel is None:
                            try:
                                from browsermind_core.learning.reward_layers import is_novel_capability
                                cap_record.is_novel = is_novel_capability(
                                    cap_record.human_name or ""
                                )
                            except Exception:
                                pass
                        mem_store.update_capability(cap_record)
                    print(
                        f"  [CapLoop/CapVerify] hash={inv_hash} "
                        f"transition_verified={transition_verified} "
                        f"reuse_count={cap_record.reuse_count} "
                        f"env={env_key}"
                    )
                except Exception as verify_exc:
                    print(
                        f"  [CapLoop/CapVerify] verify ERROR hash={inv_hash} "
                        f"(non-fatal): {verify_exc}"
                    )

            if checked_count:
                print(
                    f"  [CapLoop/CapVerify] checked={checked_count} "
                    f"verified={verified_count} env={env_key}"
                )
        except Exception as exc:
            print(f"  [CapLoop/CapVerify] ERROR (non-fatal): {exc}")

    # ── Bot Wall Detection ─────────────────────────────────────────────────────
    # Checks for Cloudflare challenge / CAPTCHA pages immediately after initial
    # navigation. Returns True if a bot wall is detected; caller must bail out.

    @staticmethod
    async def _check_bot_wall(page) -> bool:
        """Return True if the current page is a Cloudflare or CAPTCHA challenge wall."""
        try:
            url = page.url or ""
            if "challenges.cloudflare.com" in url or "/cdn-cgi/challenge-platform" in url:
                return True
            title = (await page.title()).lower()
            if "just a moment" in title or "attention required" in title or "ddos-guard" in title:
                return True
            # Structural check: Cloudflare injects a challenge form or specific meta tag
            cf_elem = await page.query_selector("#challenge-form, [data-cf-settings], .cf-browser-verification")
            if cf_elem is not None:
                return True
        except Exception:
            pass
        return False

    # ── Capability Loop: Addition 4 ───────────────────────────────────────────
    # Novelty trigger — runs at the START of replay(), after fingerprint capture.
    # Uses MemoryStore as the novelty proxy: empty procedural store = novel env.
    # Triggers AffordanceDiscoverer for the 4 implemented IntentFamilies.
    # Best-effort: never raises into replay().

    async def _discover_on_novelty(self, page, env_key: str, budget: int = 10) -> list:
        """Trigger affordance discovery when the environment has no procedural memory.

        MemoryStore is the novelty proxy: if load_procedural(env_key) returns an
        empty dict, no prior execution has ever written strategy priors for this
        environment — treat it as novel and run discovery across the 4 implemented
        IntentFamilies (SEARCH, AUTH, FORM, FILTER).

        After seeding ProceduralRecords, runs ExplorerPolicy to actually execute
        the discovered affordances. Returns FailureAttribution records from the
        exploration run so replay() can inject them into report.failure_attribution.

        Returns an empty list for known environments or when discovery finds nothing.

        Logging prefix: [CapLoop/Novelty]
        """
        if page is None or not env_key or env_key == "unknown":
            return []
        try:
            from browsermind_core.memory.memory_store import MemoryStore
            from browsermind_core.runtime.affordance_discoverer import AffordanceDiscoverer
            from browsermind_core.runtime.intent_family import IntentFamily

            mem_store = MemoryStore(persona_id=str(self.persona_id or "default"))
            existing = mem_store.load_procedural(env_key)

            implemented_families = [
                IntentFamily.SEARCH,
                IntentFamily.AUTH,
                IntentFamily.FORM,
                IntentFamily.FILTER,
                IntentFamily.NAVIGATION,
            ]
            all_discovered = []  # (family, affordances) pairs — populated below

            if existing:
                if not self.exploration_mode:
                    print(f"  [CapLoop/Novelty] Known environment env={env_key} ({len(existing)} procedural records); skipping discovery.")
                    return []

                # exploration_mode=True: re-run discovery to get fresh locators.
                # Skip seeding (records already exist); run ExplorerPolicy only.
                print(
                    f"  [CapLoop/Novelty] Known environment env={env_key}"
                    f" ({len(existing)} procedural records); refreshing affordances for exploration."
                )
                discoverer = AffordanceDiscoverer()
                for family in implemented_families:
                    try:
                        affordances = await discoverer.discover(page, family)
                        if affordances:
                            all_discovered.append((family, affordances))
                            print(
                                f"  [CapLoop/Novelty]   {family.value}: {len(affordances)} affordance(s) refreshed"
                                " — " + ", ".join(
                                    f"{a.type}(score={a.score:.2f})" for a in affordances[:3]
                                )
                            )
                    except Exception:
                        pass

                # If refresh returned nothing, treat as novel so we don't silently skip
                if not all_discovered:
                    print(
                        f"  [CapLoop/Novelty] Known env refresh returned 0 affordances"
                        f" (env={env_key}) — falling back to novel discovery."
                    )
                    existing = {}  # clear so code below takes the novel path
                    return await self._discover_on_novelty(page, env_key, budget)

                # Jump straight to ExplorerPolicy (no seeding for known envs)
                exploration_steps = []
                try:
                    from browsermind_core.exploration.explorer_policy import ExplorerPolicy
                    policy = ExplorerPolicy()
                    exploration_steps = await policy.run(
                        page=page,
                        all_discovered=all_discovered,
                        budget=budget,
                        env_key=env_key,
                        state_classifier=self._state_classifier,
                    )
                    if exploration_steps:
                        print(
                            f"  [CapLoop/Novelty] ExplorerPolicy: {len(exploration_steps)} step(s) executed "
                            f"env={env_key}"
                        )
                        # Feed SSTG from ExplorerPolicy semantic state observations
                        if self._sstg is not None:
                            _sstg_env = env_key or self.environment_instance or self.environment_family or ""
                            _recorded = 0
                            for _step in exploration_steps:
                                _sb = getattr(_step, "semantic_state_before", None)
                                _sa = getattr(_step, "semantic_state_after", None)
                                if _sb and _sa and getattr(_step, "execution_success", False):
                                    try:
                                        from browsermind_core.ontology.semantic_state import SemanticState
                                        _pre = SemanticState.from_dict(_sb)
                                        _post = SemanticState.from_dict(_sa)
                                        if _pre.fingerprint != _post.fingerprint:
                                            _cap = getattr(_step, "action_type", None) or "explore"
                                            self._sstg.add_observation(_pre, _post, _cap, _sstg_env)
                                            _recorded += 1
                                    except Exception:
                                        pass
                            if _recorded:
                                try:
                                    self._sstg.save()
                                    print(f"  [SSTG] Recorded {_recorded} transition(s) from ExplorerPolicy (env={env_key})")
                                except Exception:
                                    pass
                except Exception as policy_exc:
                    print(f"  [CapLoop/Novelty] ExplorerPolicy ERROR (non-fatal): {policy_exc}")
                return exploration_steps

            print(f"  [CapLoop/Novelty] NOVEL environment detected: env={env_key} — running affordance discovery.")

            discoverer = AffordanceDiscoverer()
            total_found = 0
            for family in implemented_families:
                try:
                    affordances = await discoverer.discover(page, family)
                    print(
                        f"  [CapLoop/Novelty]   {family.value}: {len(affordances)} affordance(s) discovered"
                        + (
                            " — " + ", ".join(
                                f"{a.type}(score={a.score:.2f})" for a in affordances[:3]
                            ) if affordances else ""
                        )
                    )
                    total_found += len(affordances)
                    if affordances:
                        all_discovered.append((family, affordances))
                except Exception as family_exc:
                    print(f"  [CapLoop/Novelty]   {family.value}: discovery error (non-fatal): {family_exc}")

            print(f"  [CapLoop/Novelty] Discovery complete: env={env_key} total_affordances={total_found}")

            # Discovery Law → Hypothesis Law: seed CANDIDATE-tier ProceduralRecords
            # from discovered affordances. Each affordance that scored above threshold
            # becomes a capability hypothesis (source='affordance_discovery').
            # These are CANDIDATE tier only — they have no execution evidence yet.
            # They exist to seed the strategy priors lookup for future executions
            # on this environment.
            if all_discovered:
                try:
                    from browsermind_core.memory.memory_store import MemoryStore
                    from browsermind_core.memory.procedural import ProceduralRecord
                    _AFFORDANCE_SCORE_THRESHOLD = 0.5

                    mem_store_discovery = MemoryStore(persona_id=str(self.persona_id or "default"))
                    seeded = 0
                    for family, affordances in all_discovered:
                        for aff in affordances:
                            score = getattr(aff, "score", 0.0)
                            if score < _AFFORDANCE_SCORE_THRESHOLD:
                                continue
                            aff_type = str(getattr(aff, "type", "") or family.value)
                            # Affordance action is typically the interaction type
                            # (click, fill, etc.) inferred from the affordance type.
                            aff_action = "click"
                            aff_type_lower = aff_type.lower()
                            if "input" in aff_type_lower or "form" in aff_type_lower or "fill" in aff_type_lower:
                                aff_action = "fill"
                            elif "search" in aff_type_lower:
                                aff_action = "fill"

                            proc = ProceduralRecord(
                                environment_key=env_key,
                                intent_family=family.value,
                                capability_hint=aff_type,
                                step_action=aff_action,
                                strategy_counts={},
                                known_boundaries=[],
                                source="affordance_discovery",
                            )
                            mem_store_discovery.update_procedural(proc)
                            seeded += 1

                    print(
                        f"  [CapLoop/Novelty] Discovery → Candidate: {seeded} ProceduralRecord(s) "
                        f"seeded from affordances (env={env_key}, source=affordance_discovery)"
                    )
                except Exception as seed_exc:
                    print(f"  [CapLoop/Novelty] Candidate seeding ERROR (non-fatal): {seed_exc}")

            # Explorer Policy — execute the top affordance per family so the system
            # actually *uses* what it discovered, not merely records it.
            # Best-effort: policy errors must not break the replay path.
            exploration_steps = []
            try:
                from browsermind_core.exploration.explorer_policy import ExplorerPolicy
                policy = ExplorerPolicy()
                exploration_steps = await policy.run(
                    page=page,
                    all_discovered=all_discovered,
                    budget=budget,
                    env_key=env_key,
                    state_classifier=self._state_classifier,
                )
                if exploration_steps:
                    print(
                        f"  [CapLoop/Novelty] ExplorerPolicy: {len(exploration_steps)} step(s) executed "
                        f"env={env_key}"
                    )
                    # Feed SSTG from ExplorerPolicy semantic state observations
                    if self._sstg is not None:
                        _sstg_env = env_key or self.environment_instance or self.environment_family or ""
                        _recorded = 0
                        for _step in exploration_steps:
                            _sb = getattr(_step, "semantic_state_before", None)
                            _sa = getattr(_step, "semantic_state_after", None)
                            if _sb and _sa and getattr(_step, "execution_success", False):
                                try:
                                    from browsermind_core.ontology.semantic_state import SemanticState
                                    _pre = SemanticState.from_dict(_sb)
                                    _post = SemanticState.from_dict(_sa)
                                    if _pre.fingerprint != _post.fingerprint:
                                        _cap = getattr(_step, "action_type", None) or "explore"
                                        self._sstg.add_observation(_pre, _post, _cap, _sstg_env)
                                        _recorded += 1
                                except Exception:
                                    pass
                        if _recorded:
                            try:
                                self._sstg.save()
                                print(f"  [SSTG] Recorded {_recorded} transition(s) from ExplorerPolicy (env={env_key})")
                            except Exception:
                                pass
            except Exception as policy_exc:
                print(f"  [CapLoop/Novelty] ExplorerPolicy ERROR (non-fatal): {policy_exc}")

            return exploration_steps

        except Exception as exc:
            print(f"  [CapLoop/Novelty] ERROR (non-fatal): {exc}")
        return []

    def _resolve_input(self, step: Dict[str, Any], instance: WorkflowInstance):
        val = step.get("default_value")
        binding = step.get("input_binding")
        if binding:
            b_type = binding.get("type")
            b_key  = binding.get("key", "")
            if b_type == "vault":
                creds = {}
                if hasattr(self.auth_session, "get_credentials"):
                    creds = self.auth_session.get_credentials()
                
                name_lower = (step.get("target_name") or "").lower()
                b_key_lower = b_key.lower()
                
                vault_val = None
                if name_lower in creds:
                    vault_val = creds[name_lower]
                elif b_key_lower in creds:
                    vault_val = creds[b_key_lower]
                elif "password" in name_lower and "password" in creds:
                    vault_val = creds["password"]
                
                if not vault_val:
                    import os
                    vault_val = os.environ.get(
                        f"BM_VAULT_{b_key.upper()}",
                        os.environ.get("BM_VAULT_SECRET")
                    )
                if vault_val:
                    val = vault_val
        return val

    async def replay(self, site: Any, template: WorkflowTemplate, instance: WorkflowInstance, enable_recovery: bool = True, start_step_index: int = 0, is_resume: bool = False) -> ReplayReport:
        start_time = time.time()

        report = ReplayReport(
            workflow_id=instance.id,
            template_id=template.id,
            total_steps=len(template.steps),
            provenance={
                "template_uuid": str(template.id),
                "compiled_from": template.metadata.get("compiled_from", "unknown") if template.metadata else "unknown",
                "compiler_version": template.metadata.get("compiler_version", "1.0.0") if template.metadata else "1.0.0",
                "recording_version": template.metadata.get("recording_version", "1.0.0") if template.metadata else "1.0.0",
            }
        )

        # A-3: open Execution episode at run start (no-op if not wired)
        self._start_execution_if_wired(template, instance)

        # M3: Identity status precheck.
        # Block before opening the browser if the persisted Identity for
        # this (persona, env) pair is non-active. Status==None means
        # "no identity provisioned" and is treated as a soft pass — many
        # benchmark workflows perform their own login as their first step.
        if site is not None and hasattr(self.auth_session, "resolve_identity_status"):
            try:
                status = self.auth_session.resolve_identity_status(site.key)
            except Exception:
                status = None
            if status in ("expired", "requires_2fa", "revoked"):
                report.status = "BLOCKED"
                report.failure_reason = (
                    f"IDENTITY_{status.upper()}: identity for "
                    f"persona={self.auth_session.persona_name!r} "
                    f"env={site.key!r} is {status}. "
                    f"Re-authenticate before retrying."
                )
                report.duration_seconds = time.time() - start_time
                R0Logger.log_event(
                    self.auth_session.store_dir,
                    "replay_blocked",
                    workflow=template.name,
                    environment=site.key,
                    reason=report.failure_reason,
                    status="BLOCKED",
                )
                _env_key_blocked = site.key if site is not None else "unknown"
                self._record_replay_accuracy(report, template, instance, _env_key_blocked)
                # ContractGate: verify goal completion before writing OutcomeRecord.
                # Page is None on the BLOCKED path (never opened); _verify handles None.
                await self._verify_contract_outcome_async(None, template, _env_key_blocked)
                self._record_replay_outcome(report, template, instance)
                self._record_step_outcomes(report, template, instance, _env_key_blocked)
                self._close_execution_if_wired(report)
                return report

        if is_resume:
            env_key = site.key if site else "unknown"
            R0Logger.log_event(
                self.auth_session.store_dir,
                "workflow_resume",
                workflow=template.name,
                environment=env_key,
                step_index=start_step_index,
                status="IN_PROGRESS"
            )

        page = None
        try:
            page = await self.auth_session.open()
            env_key = site.key if site else "unknown"

            # Bot wall check: detect Cloudflare / CAPTCHA challenge pages immediately
            # after the initial navigation. Bail early with BOT_DETECTED so the site
            # is not silently counted as a failed workflow.
            if await self._check_bot_wall(page):
                report.status = "BLOCKED"
                report.failure_reason = "BOT_DETECTED:cloudflare_or_captcha"
                R0Logger.log_event(
                    self.auth_session.store_dir,
                    "replay_blocked",
                    workflow=template.name,
                    environment=env_key,
                    reason=report.failure_reason,
                    status="BLOCKED",
                )
                report.duration_seconds = time.time() - start_time
                self._record_replay_outcome(report, template, instance)
                self._close_execution_if_wired(report)
                return report

            persona_id = self.auth_session.persona_name
            resolver = TargetResolver(page, env_key=env_key, persona_id=persona_id, lesson_reader=self.lesson_reader, behavior_audit=getattr(self, "_behavior_audit", None), recovery_registry=getattr(self, "_recovery_registry", None))
            resource_resolver = ResourceResolver(self.auth_session)
            executor = ActionExecutor(page)
            affordance_executor = AffordanceExecutor()
            memory_writer = MemoryWriter(persona_id=persona_id)  # P4: Memory Runtime
            policy_engine = PolicyEngine()  # P5B: Policy Engine

            # P4C: Capture environment fingerprint at start of replay
            try:
                report.env_fingerprint_start = await fingerprint_environment(page)
            except Exception:
                pass

            # Capability Loop — Addition 4: novelty trigger + Explorer Policy.
            # _discover_on_novelty now returns FailureAttribution records from
            # ExplorerPolicy so the exploration harness can see what was executed.
            # Extract exploration_budget from the navigation step (set by
            # _MinimalExplorationTemplate from ExplorationSpec.budget).
            _explore_budget = 10  # default when not running via explore command
            for _ts in getattr(template, "steps", []) or []:
                if _ts.get("action_type") == "navigate" and "exploration_budget" in _ts:
                    try:
                        _explore_budget = max(1, int(_ts["exploration_budget"]))
                    except (TypeError, ValueError):
                        pass
                    break
            exploration_steps = await self._discover_on_novelty(page, env_key, budget=_explore_budget)
            if exploration_steps:
                for _es in exploration_steps:
                    report.failure_attribution.append(_es)
                    if getattr(_es, "actual_outcome", "") in ("SUCCESS", "TRANSITION_SUCCESS"):
                        report.resolved_steps += 1
                    else:
                        report.failed_steps += 1
                report.total_steps += len(exploration_steps)

            _prev_step_end_time = None
            _prior_belief = None  # StepBelief from previous step; None on first step

            # Phase 3: Initialise hardening stack for this replay run.
            try:
                from browsermind_core.runtime.replay_hardening import ReplayHardening
                self._hardening = ReplayHardening(
                    page=page,
                    store_dir=self.auth_session.store_dir,
                    workflow_id=str(instance.id),
                    template_name=template.name,
                )
            except Exception:
                self._hardening = None

            # Phase 4 (Interrupt Controller): launch background interrupt watcher.
            # Detects cookie banners, marketing modals, session expiry, chat widgets
            # that appear between steps and would otherwise cause false TargetResolver failures.
            _interrupt_queue: asyncio.Queue = asyncio.Queue()
            _interrupt_ctrl = None
            _interrupt_watcher = None
            try:
                from browsermind_core.runtime.page_interrupt_controller import (
                    PageInterruptController,
                    drain_interrupts,
                )
                _interrupt_ctrl = PageInterruptController()
                _interrupt_watcher = asyncio.create_task(
                    _interrupt_ctrl.watch(page, _interrupt_queue)
                )
            except Exception:
                pass

            for idx, step in enumerate(template.steps):
                if idx < start_step_index:
                    report.resolved_steps += 1
                    continue

                step_start_time = time.time()
                inter_step_delay_ms = int((_prev_step_end_time and (step_start_time - _prev_step_end_time) * 1000) or 0) or None
                seq         = step.get("seq", 0)
                action_type = step.get("action_type", "")
                role        = step.get("target_role", "")
                name        = step.get("target_name", "")
                selector    = step.get("target_selector", "")
                url         = step.get("url", "")

                # UI Phase 1 — Live Workspace state. Atomic write of a small
                # state file at every step boundary so the read-side viewer
                # at /live can poll it. Best-effort; failures here must
                # never raise into the replay loop.
                try:
                    self._write_live_state(
                        instance=instance,
                        template=template,
                        seq=seq,
                        action_type=action_type,
                        role=role,
                        name=name,
                        report=report,
                        strategy=None,
                    )
                except Exception:
                    pass

                # Human Intervention: in-process pause (asyncio.Event)
                if not self._pause_event.is_set():
                    try:
                        self._write_live_state(
                            instance=instance, template=template, seq=seq,
                            action_type=action_type, role=role, name=name,
                            report=report, strategy=None,
                            is_paused=True, pause_reason=self._pause_reason,
                        )
                    except Exception:
                        pass
                    await self._pause_event.wait()

                # Human Intervention: cross-process pause (BrowserMind.bat / live_watch.py)
                _sentinel = Path(self.auth_session.store_dir) / "_pause_requested" if hasattr(self.auth_session, "store_dir") else None
                if _sentinel is not None and _sentinel.exists():
                    R0Logger.log_event(self.auth_session.store_dir, "workflow_pause",
                                       reason="user_requested", step=seq)
                    try:
                        self._write_live_state(
                            instance=instance, template=template, seq=seq,
                            action_type=action_type, role=role, name=name,
                            report=report, strategy=None,
                            is_paused=True, pause_reason="sentinel_file",
                        )
                    except Exception:
                        pass
                    while _sentinel.exists():
                        await asyncio.sleep(0.5)
                    R0Logger.log_event(self.auth_session.store_dir, "workflow_resume",
                                       reason="sentinel_cleared", step=seq)

                # Phase 3: Pre-step bot-wall check. If a bot-wall is detected
                # before we even try to resolve, write a checkpoint and pause.
                if self._hardening is not None and action_type != "navigate":
                    try:
                        _pre_check = await self._hardening.pre_step_check()
                        if _pre_check is not None:
                            self._hardening._write_checkpoint(
                                step_seq=seq,
                                completed_steps=report.resolved_steps,
                                attribution_so_far=report.failure_attribution,
                                environment_key=env_key,
                                reason="bot_wall_pre_step",
                            )
                            report.status = "BLOCKED"
                            report.failure_reason = f"BOT_WALL at step {seq}: {_pre_check.bot_wall_signal}"
                            break
                    except Exception:
                        pass

                # Phase 4 (Interrupt Controller): drain any queued page-level
                # interrupts (cookie banners, modals, chat widgets) before attempting
                # to resolve the target.  Failures here are non-fatal.
                if _interrupt_ctrl is not None and action_type != "navigate":
                    try:
                        from browsermind_core.runtime.page_interrupt_controller import drain_interrupts
                        _drain_results = await drain_interrupts(
                            page, _interrupt_queue, _interrupt_ctrl
                        )
                        if _drain_results:
                            resolved_names = [r.rule_name for r in _drain_results if r.resolved]
                            if resolved_names:
                                print(f"  [Interrupt] Step {seq}: handled {resolved_names}")
                    except Exception:
                        pass

                # Navigate steps (synthetic exploration template) — no UI resolution needed.
                # auth_session.open() already navigated; this step is a positioning marker.
                # NOT added to failure_attribution: the navigate fallback intent is
                # non-semantic and would create ghost hypotheses in the hypothesis store.
                if action_type == "navigate":
                    if url:
                        try:
                            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                        except Exception:
                            pass  # Best-effort; page may already be at the correct URL
                    # Stamp affordance fingerprint on first navigate if not yet stored.
                    # TemplateHealthMonitor uses this vector for future drift detection.
                    if template is not None and template.metadata is not None and not template.metadata.get("compile_time_affordances"):
                        try:
                            from browsermind_core.runtime.template_health_monitor import stamp_template
                            from browsermind_core.runtime.page_state_extractor import PageStateExtractor
                            _signals = await PageStateExtractor().extract(page)
                            stamp_template(template, page.url, _signals)
                        except Exception:
                            pass
                    report.resolved_steps += 1
                    _prev_step_end_time = time.time()
                    continue

                # Read prediction attached by Compiler (P3.1)
                assessment      = step.get("replayability") or {}
                predicted_tier  = assessment.get("tier", "UNKNOWN")
                predicted_score = float(assessment.get("score", 0.0))

                # --- Resolve ---
                actual_outcome   = "SUCCESS"
                failure_reason   = None
                loc              = None
                recovered_by     = None
                resolved_by      = None
                resolution_depth = None
                candidate_count  = 0
                candidates_info  = []
                vault_resolution_path = None

                res_result = None
                policy_rejected = False
                
                # --- P5B-lite Policy Enforcement ---
                try:
                    cap_hint = (step.get("descriptor") or {}).get("capability_hint", "")
                    binding = step.get("input_binding")
                    b_key = binding.get("key") if binding else None
                    if is_resume and idx == start_step_index:
                        # Human approved resumption on this step, bypass policy evaluation
                        pass
                    else:
                        policy_engine.enforce(persona_id, cap_hint)
                    # If allowed but is a challenge capability, log it
                    is_challenge = any(kw in (cap_hint or "").lower() for kw in ("captcha", "verification", "otp", "terms", "age", "conflict"))
                    if is_challenge:
                        r_class = ResourceClassifier.classify(
                            resource_key=b_key,
                            resource_binding=binding,
                            capability_hint=cap_hint,
                            workflow_role=role
                        ).value
                        R0Logger.log_event(
                            self.auth_session.store_dir,
                            "authority_challenge",
                            challenge_type=cap_hint,
                            workflow=template.name,
                            environment=env_key,
                            step_index=seq,
                            decision="ALLOW",
                            resource_class=r_class
                        )
                except PolicyRejectionError as e:
                    print(f"  [Policy] {e}")
                    actual_outcome = "FAILED"
                    failure_reason = "POLICY_DENY"
                    report.status = "BLOCKED"
                    policy_rejected = True
                    r_class = ResourceClassifier.classify(
                        resource_key=b_key,
                        resource_binding=binding,
                        capability_hint=cap_hint,
                        workflow_role=role
                    ).value
                    R0Logger.log_event(
                        self.auth_session.store_dir,
                        "authority_challenge",
                        challenge_type=cap_hint or "policy_deny",
                        workflow=template.name,
                        environment=env_key,
                        step_index=seq,
                        decision="DENY",
                        resource_class=r_class
                    )
                except PolicyInterventionRequired as e:
                    print(f"  [Policy] {e}")
                    actual_outcome = "ASK" 
                    failure_reason = "POLICY_ASK"
                    report.status = "INTERRUPTED"
                    policy_rejected = True
                    r_class = ResourceClassifier.classify(
                        resource_key=b_key,
                        resource_binding=binding,
                        capability_hint=cap_hint,
                        workflow_role=role
                    ).value
                    R0Logger.log_event(
                        self.auth_session.store_dir,
                        "authority_challenge",
                        challenge_type=cap_hint or "policy_ask",
                        workflow=template.name,
                        environment=env_key,
                        step_index=seq,
                        decision="ASK",
                        resource_class=r_class
                    )
                    R0Logger.log_event(
                        self.auth_session.store_dir,
                        "workflow_pause",
                        reason="policy_ask",
                        workflow=template.name,
                        environment=env_key,
                        step_index=seq,
                        acquisition_required=False,
                        resource_class=r_class
                    )

                if self.on_before_resolve:
                    try:
                        await self.on_before_resolve(page, step)
                    except Exception as e:
                        print(f"  [ReplayEngine] on_before_resolve hook failed: {e}")

                res_start_time = time.time()
                
                if not policy_rejected:
                    try:
                        res_result = await resolver.resolve(
                            role, name, selector,
                            descriptor=step.get("descriptor"),
                            enable_recovery=enable_recovery,
                            step=step,
                            prior_belief=_prior_belief,
                        )
                        res_time_ms = int((time.time() - res_start_time) * 1000)
                        report.resolved_steps += 1
                        loc = res_result.locator
                        recovered_by = res_result.recovered_by
                        resolved_by = res_result.resolved_by
                        resolution_depth = res_result.depth
                        candidate_count = res_result.candidate_count

                    except AmbiguousIdentityError as e:
                        res_time_ms = int((time.time() - res_start_time) * 1000)
                        actual_outcome  = "AMBIGUOUS_IDENTITY"
                        failure_reason  = str(e)
                        candidate_count = e.candidate_count
                        candidates_info = e.candidates_info
                        report.status = "FAILED"
                        report.failed_steps += 1
                        report.failure_reason = (
                            f"Step {seq}: {action_type} - role='{role}', name='{name}' -> {failure_reason}"
                        )
                        report.ambiguous_steps = getattr(report, 'ambiguous_steps', 0) + 1
                        resolved_by      = None
                        recovered_by     = None
                        resolution_depth = None

                    except TargetResolutionError as e:
                        res_time_ms = int((time.time() - res_start_time) * 1000)
                        actual_outcome = "FAILED"
                        failure_reason = f"TargetNotFound: role='{role}', name='{name}'"
                        report.failed_steps += 1
                        report.failure_reason = (
                            f"Step {seq}: {action_type} - role='{role}', name='{name}' -> TargetNotFound"
                        )
                        recovered_by     = None
                        resolved_by      = None
                        resolution_depth = None
                        # Teacher queue: when a step has a real semantic name
                        # but no Field resolves for it, append to the unknown
                        # queue so the operator can curate it via `bm field
                        # add-alias`. Best-effort; never raises into replay.
                        try:
                            self._record_unknown_field(step, role, name, instance, template)
                        except Exception:
                            pass
                else:
                    # Policy rejected: bypass resolution, preserve actual_outcome (FAILED or ASK) and failure_reason
                    res_time_ms = int((time.time() - res_start_time) * 1000)
                    recovered_by     = None
                    resolved_by      = None
                    resolution_depth = None
                    report.failed_steps += 1
                    report.failure_reason = failure_reason

                resolution_success = actual_outcome not in ("FAILED", "AMBIGUOUS_IDENTITY", "ASK")
                
                # --- Live Resolver Ambiguity & Strategy Logger ---
                if not policy_rejected:
                    strategy_str = f"via {resolved_by}" if resolution_success else f"failed: {failure_reason}"
                    print(f"  [Resolver] Step {seq:2d}: {action_type:<8} - role='{role}', name='{name}' -> {actual_outcome} {strategy_str} (Candidates = {candidate_count})")

                execution_success = None
                effect_verified = None
                effect_type = None
                effect_details = None
                quality_score = None
                failure_layer = (
                    "identity"    if actual_outcome == "AMBIGUOUS_IDENTITY" else
                    "resolution"  if actual_outcome == "FAILED" else
                    None
                )

                # --- Identity Ledger (Task 4) ---
                confidence_map = {
                    "primary_semantic":   1.0,
                    "loose_semantic":     0.8,
                    "semantic+container": 0.85,
                    "placeholder":        0.7,
                    "nearby_text":        0.5,
                    "structural_path":    0.1,
                }
                identity_confidence = (
                    0.0 if actual_outcome == "AMBIGUOUS_IDENTITY" else
                    confidence_map.get(resolved_by, 0.0)
                )
                
                # --- Selection Forensics (Task 3B) ---
                desc = step.get("descriptor") or {}
                selection_forensics = {
                    "container_label": desc.get("container_label"),
                    "container_data_test": desc.get("container_data_test"),
                    "price": desc.get("price"),
                    "list_size": desc.get("list_size"),
                }

                target_integrity = {
                    "expected_role": role,
                    "expected_name": name,
                    "resolved_tag": None,
                    "resolved_text": None,
                    "url_before": None,
                    "url_after": None,
                    "dom_hash_before": None,
                    "dom_hash_after": None,
                    # Identity Ledger
                    "candidate_count": candidate_count,
                    "resolution_strategy": resolved_by,
                    "identity_confidence": identity_confidence,
                    "candidates_info": candidates_info,
                    "selection_forensics": selection_forensics,
                }

                if resolution_success:
                    try:
                        val = await resource_resolver.resolve_input(step, instance)
                        binding = step.get("input_binding")
                        if binding:
                            b_key = binding.get("key", "")
                            r_class = ResourceClassifier.classify(
                                resource_key=b_key,
                                resource_binding=binding,
                                capability_hint=cap_hint,
                                workflow_role=role
                            ).value
                            # P7C: Log Acquisition trail
                            acq_res = resource_resolver.last_acquisition_result
                            if acq_res:
                                vault_resolution_path = acq_res.vault_resolution_path
                                R0Logger.log_event(
                                    self.auth_session.store_dir,
                                    "resource_acquisition",
                                    resource=b_key,
                                    attempts=acq_res.attempts,
                                    resolved_by=acq_res.resolved_by,
                                    duration_ms=acq_res.duration_ms,
                                    resource_class=r_class,
                                    provider_chain=acq_res.provider_chain
                                )

                            # Log identity usage if it is an identity
                            if b_key in ("github_profile", "linkedin_profile", "email_address", "username", "phone_number", "portfolio_url", "transcript", "resume"):
                                R0Logger.log_event(
                                    self.auth_session.store_dir,
                                    "identity_usage",
                                    identity=b_key,
                                    workflow=template.name,
                                    environment=env_key,
                                    step_index=seq,
                                    resource_class=r_class
                                )
                            R0Logger.log_event(
                                self.auth_session.store_dir,
                                "resource_demand",
                                resource=b_key,
                                resource_class=r_class,
                                workflow=template.name,
                                environment=env_key,
                                step_index=seq,
                                required_for=(step.get("descriptor") or {}).get("capability_hint") or action_type,
                                available=True,
                                source=acq_res.resolved_by if acq_res else "vault"
                            )
                    except ResourceMissingError as e:
                        actual_outcome = "ASK"
                        failure_reason = f"RESOURCE_MISSING"
                        report.status = "INTERRUPTED"
                        report.failure_reason = failure_reason
                        report.missing_resource = e.resource_key
                        report.failed_steps += 1
                        
                        r_class = ResourceClassifier.classify(
                            resource_key=e.resource_key,
                            resource_binding=binding,
                            capability_hint=cap_hint,
                            workflow_role=role
                        ).value
                        
                        # P7C: Log Acquisition trail
                        acq_res = resource_resolver.last_acquisition_result
                        if acq_res:
                            R0Logger.log_event(
                                self.auth_session.store_dir,
                                "resource_acquisition",
                                resource=e.resource_key,
                                attempts=acq_res.attempts,
                                resolved_by=acq_res.resolved_by,
                                duration_ms=acq_res.duration_ms,
                                resource_class=r_class,
                                provider_chain=acq_res.provider_chain
                            )

                        # Log resource demand as unavailable
                        R0Logger.log_event(
                            self.auth_session.store_dir,
                            "resource_demand",
                            resource=e.resource_key,
                            resource_class=r_class,
                            workflow=template.name,
                            environment=env_key,
                            step_index=seq,
                            required_for=step.get("descriptor", {}).get("capability_hint") or action_type,
                            available=False,
                            acquisition_required=True
                        )
                        # Write to R0 Evidence Ledger using R0Logger
                        R0Logger.log_event(
                            self.auth_session.store_dir,
                            "resource_missing",
                            resource=e.resource_key,
                            resource_class=r_class,
                            workflow=template.name,
                            environment=env_key,
                            step_index=seq,
                            required_for=(step.get("descriptor") or {}).get("capability_hint") or action_type
                        )
                        # Log workflow pause
                        R0Logger.log_event(
                            self.auth_session.store_dir,
                            "workflow_pause",
                            reason="resource_missing",
                            resource=e.resource_key,
                            resource_class=r_class,
                            workflow=template.name,
                            environment=env_key,
                            step_index=seq,
                            acquisition_required=True
                        )
                        break
                    
                    url_before = page.url if page else None
                    target_integrity["url_before"] = url_before
                    val_before = None
                    
                    try:
                        # Pre-action probe (target integrity metadata)
                        if page:
                            try:
                                target_integrity["dom_hash_before"] = await page.evaluate("() => document.body.innerHTML.length")
                            except Exception:
                                pass

                        if loc:
                            try:
                                target_integrity["resolved_tag"] = await loc.evaluate("el => el.tagName.toLowerCase()")
                                target_integrity["resolved_text"] = await loc.evaluate("el => (el.innerText || el.textContent || '').substring(0, 50)")
                            except Exception:
                                pass

                        if res_result and res_result.mode == "affordance":
                            await affordance_executor.execute(page, res_result.affordance)
                            execution_success = True
                            effect_type = "DOM_CHANGED"
                            effect_verified = True
                            quality_score = 0.9
                        else:
                            # --- L5 Executor v2: FREV pipeline ---
                            from browsermind_core.runtime.execution_engine_v2 import (
                                WebExecutionEngine, ExecutionRequest,
                            )
                            _exec_v2 = WebExecutionEngine(page, start_url=url_before or "")
                            _exec_req = ExecutionRequest(
                                action_type=action_type,
                                page=page,
                                locator=loc,
                                value=val,
                                url=url,
                                skip_reach=True,  # ReplayEngine already verified resolution
                            )
                            _exec_result = await _exec_v2.execute(_exec_req)
                            if not _exec_result.success:
                                # Classify the failure before surfacing it.
                                # ELEMENT_NOT_FOUND is a targeting failure — do NOT produce
                                # a quality=0 verdict. Let TargetResolver retry.
                                from browsermind_core.runtime.execution_exception import (
                                    ExecutionExceptionClass as _EEC,
                                )
                                _exc_cls = _exec_result.exc_class
                                if _exc_cls == _EEC.ELEMENT_NOT_FOUND:
                                    raise ActionExecutionError(
                                        f"ELEMENT_NOT_FOUND: {_exec_result.error}"
                                    )
                                elif _exc_cls == _EEC.PAGE_CRASH:
                                    # Hard escalate — bypass normal failure handler
                                    raise ActionExecutionError(
                                        f"PAGE_CRASH: {_exec_result.error}"
                                    )
                                else:
                                    # For TIMEOUT/EXECUTION_ERROR the engine may have produced
                                    # a post-failure verdict — preserve it before raising.
                                    if _exec_result.effect_verdict is not None:
                                        _verdict = _exec_result.effect_verdict
                                        _outcome_label = _verdict.outcome_label
                                        effect_type = _verdict.effect_type.upper()
                                        effect_verified = (
                                            True  if _outcome_label in ("SUCCESS", "TRANSITION_SUCCESS") else
                                            False if _outcome_label == "FAILED" else
                                            None
                                        )
                                        quality_score = _verdict.quality_score
                                    raise ActionExecutionError(_exec_result.error or "ExecutionEngineV2 failed")
                            execution_success = True

                            # Map EffectVerdict → legacy effect_type / effect_verified / quality_score
                            _verdict = _exec_result.effect_verdict
                            if _verdict is not None:
                                _outcome_label = _verdict.outcome_label
                                effect_type = _verdict.effect_type.upper()
                                effect_verified = (
                                    True  if _outcome_label in ("SUCCESS", "TRANSITION_SUCCESS") else
                                    False if _outcome_label == "FAILED" else
                                    None
                                )
                                quality_score = _verdict.quality_score
                                if _verdict.effect_type == "url_transition":
                                    effect_details = {"url_before": url_before, "url_after": page.url}
                                elif _verdict.evidence:
                                    effect_details = {"evidence": _verdict.evidence}
                            else:
                                effect_type = "UNKNOWN"
                                effect_verified = None
                                quality_score = None

                        url_after = page.url if page else None
                        target_integrity["url_after"] = url_after

                        if page:
                            try:
                                target_integrity["dom_hash_after"] = await page.evaluate("() => document.body.innerHTML.length")
                            except Exception:
                                pass

                        # P4A/P4B: Write episode + update procedural priors
                        try:
                            desc = step.get("descriptor") or {}
                            cap_hint = desc.get("capability_hint") or ""
                            intent_fam = IntentFamilyMapper.map(desc).value
                            strat = resolved_by or "unknown"
                            memory_writer.write_step_outcome(
                                environment_key=env_key,
                                step_action=action_type,
                                capability_hint=cap_hint,
                                intent_family=intent_fam,
                                resolution_strategy=strat,
                                outcome="success",
                            )
                            # P4C: Infer semantic facts from this step
                            memory_writer.infer_semantic_facts_from_step(
                                environment_key=env_key,
                                step_action=action_type,
                                capability_hint=cap_hint,
                                resolution_strategy=strat,
                                descriptor=desc,
                            )
                        except Exception:
                            pass  # memory write must never crash replay

                    except ActionTransitionSuccess as e:
                        # The DOM tore down due to success (e.g. Navigation via Submit)
                        actual_outcome = "TRANSITION_SUCCESS"
                        execution_success = True
                        effect_type = "DOM_CHANGED"
                        effect_verified = True
                        quality_score = 0.95
                    except (ActionExecutionError, AffordanceExecutionError) as e:
                        actual_outcome = "FAILED"
                        execution_success = False
                        failure_layer = "execution"
                        failure_reason = f"ExecutionError: {str(e)}"
                        report.failed_steps += 1   # resolved but failed to execute
                        report.failure_reason = (
                            f"Step {seq}: {action_type} - role='{role}', name='{name}' -> {failure_reason}"
                        )
                        # If this is an ELEMENT_NOT_FOUND or TIMEOUT, an interrupt may
                        # have obscured the target.  Drain + handle now so the NEXT step
                        # attempt succeeds.
                        if _interrupt_ctrl is not None and "ELEMENT_NOT_FOUND" in str(e):
                            try:
                                from browsermind_core.runtime.page_interrupt_controller import drain_interrupts
                                await drain_interrupts(page, _interrupt_queue, _interrupt_ctrl)
                            except Exception:
                                pass
                        
                    if execution_success and effect_verified is False:
                        # Diagnostic failure only, we do not fail the workflow here
                        failure_layer = "effect"

                # --- Record FailureAttribution for this step (always) ---
                _step_end_time = time.time()
                step_duration_ms = int((_step_end_time - step_start_time) * 1000)
                _prev_step_end_time = _step_end_time

                # --- Semantic State Classification (best-effort, never crashes replay) ---
                # V2 classifier uses live page signals when the page is available.
                # Falls back to URL-only v1 classification if page is gone or JS fails.
                _sem_before_dict = None
                _sem_after_dict  = None
                _sem_before_obj  = None
                _sem_after_obj   = None
                if self._state_classifier is not None:
                    try:
                        from browsermind_core.runtime.page_state_extractor import PageStateExtractor as _PSE
                        from browsermind_core.runtime.semantic_state_classifier_v2 import SemanticStateClassifierV2 as _SCV2
                        _clf_v2 = _SCV2()
                        _extractor = _PSE()

                        # Before-state: use captured url_before (page may have navigated)
                        from browsermind_core.exploration.effect_verifier import EffectSnapshot as _ES
                        _snap_before = _ES(url=target_integrity.get("url_before") or "")
                        _sem_before_obj = _clf_v2.classify_snapshot(
                            _snap_before, url=target_integrity.get("url_before") or ""
                        )

                        # After-state: if page is alive, extract rich live signals
                        if page and execution_success:
                            try:
                                _live_signals = await _extractor.extract(page)
                                if _live_signals.snapshot_ok:
                                    _sem_after_obj = _clf_v2.classify(_live_signals)
                                else:
                                    raise ValueError("snapshot_ok=False")
                            except Exception:
                                _snap_after = _ES(url=target_integrity.get("url_after") or "")
                                _sem_after_obj = _clf_v2.classify_snapshot(
                                    _snap_after, url=target_integrity.get("url_after") or ""
                                )
                        else:
                            _snap_after = _ES(url=target_integrity.get("url_after") or "")
                            _sem_after_obj = _clf_v2.classify_snapshot(
                                _snap_after, url=target_integrity.get("url_after") or ""
                            )

                        _sem_before_dict = _sem_before_obj.to_dict()
                        _sem_after_dict  = _sem_after_obj.to_dict()
                    except Exception:
                        pass

                report.failure_attribution.append(
                    FailureAttribution(
                        step_seq=seq,
                        action_type=action_type,
                        role=role,
                        name=name,
                        predicted_tier=predicted_tier,
                        predicted_score=predicted_score,
                        actual_outcome=actual_outcome,
                        failure_reason=failure_reason,
                        resolved_by=resolved_by,
                        recovered_by=recovered_by,
                        resolution_depth=resolution_depth,
                        resolution_success=resolution_success,
                        execution_success=execution_success,
                        effect_verified=effect_verified,
                        effect_type=effect_type,
                        effect_details=effect_details,
                        quality_score=quality_score,
                        failure_layer=failure_layer,
                        target_integrity=target_integrity,
                        resolution_time_ms=res_time_ms,
                        vault_resolution_path=vault_resolution_path,
                        step_duration_ms=step_duration_ms,
                        inter_step_delay_ms=inter_step_delay_ms,
                        semantic_state_before=_sem_before_dict,
                        semantic_state_after=_sem_after_dict,
                    )
                )

                # --- SSTG update (best-effort, never crashes replay) ---
                if (self._sstg is not None
                        and _sem_before_obj is not None
                        and _sem_after_obj is not None
                        and execution_success):
                    try:
                        _edge_label = cap_hint or f"{action_type}:{role}"
                        self._sstg.add_observation(
                            _sem_before_obj,
                            _sem_after_obj,
                            _edge_label,
                            self.environment_instance or self.environment_family,
                        )
                        self._sstg.save()
                    except Exception:
                        pass

                # Inter-step belief: build StepBelief from this step for the next iteration.
                try:
                    from browsermind_core.runtime.execution_belief import belief_from_attribution
                    _prior_belief = belief_from_attribution(report.failure_attribution[-1])
                except Exception:
                    _prior_belief = None

                # --- R6 Phase 5: shadow-validate pending/shadow candidates ---
                # Best-effort. NEVER raises into replay. Read-only: the primitive
                # is invoked but only .count() is read on the returned Locator;
                # no click, no mutation.
                if self._recovery_candidate_registry is not None:
                    try:
                        from browsermind_core.runtime.shadow_validator import ShadowValidator
                        from browsermind_core.runtime.recovery_registry import predicate_matches
                        from browsermind_core.training.descriptor_features import features as _shadow_features
                        _shadow_validator = ShadowValidator(self.auth_session.store_dir)
                        _shadow_desc = step.get("descriptor") or {}
                        _shadow_fv = _shadow_features(_shadow_desc, integrity=target_integrity)
                        _shadow_live_ok = actual_outcome in ("SUCCESS", "TRANSITION_SUCCESS")
                        _shadow_candidates = (
                            self._recovery_candidate_registry.list(status="pending")
                            + self._recovery_candidate_registry.list(status="shadow")
                        )
                        for _shadow_cand in _shadow_candidates:
                            if not predicate_matches(_shadow_cand.predicate, _shadow_fv):
                                continue
                            await _shadow_validator.shadow_trial(
                                candidate=_shadow_cand,
                                page=page,
                                descriptor=_shadow_desc,
                                feature_vector=_shadow_fv,
                                step_id=str(seq),
                                persona=persona_id or "",
                                env=env_key,
                                live_resolver_succeeded=_shadow_live_ok,
                            )
                    except Exception:
                        pass  # Shadow validation must never raise into replay.

                # Stop execution pipeline on unresolved identity failures.
                # Continuing after ambiguity would advance workflow state without
                # having executed the intended step. With skip_failures=True the
                # engine logs the failed step and continues; useful for collecting
                # partial-success training data on noisy templates.
                if actual_outcome in ("FAILED", "ASK", "AMBIGUOUS_IDENTITY"):
                    step_optionality = (step.get("optionality") or "required").lower()
                    if step_optionality == "optional":
                        print(f"  [Resolver] Step {seq:2d}: optional step failed ({actual_outcome}), continuing")
                        if report.status != "FAILED":
                            report.status = "PARTIAL"
                        continue
                    if self.skip_failures:
                        print(f"  [Resolver] Step {seq:2d}: skip_failures=True, continuing past {actual_outcome}")
                        report.status = "PARTIAL"
                        continue
                    break

        except Exception as e:
            import traceback
            traceback.print_exc()
            report.failure_reason = f"System Error: {str(e)}"
        finally:
            if page:
                # P4C: Environment Fingerprint at end of replay
                try:
                    report.env_fingerprint_end = await fingerprint_environment(page)
                except Exception:
                    pass

                # P4C: State Achievement Verification (Evidence -> Inference -> State)
                site_key = site.key if site else "unknown"

                try:
                    evidence = await collect_evidence(site_key, page)
                    report.state_inference = infer_state(site_key, evidence)
                except Exception:
                    pass

                # Phase 1: State Verification Audit
                try:
                    yaml_path = ROOT_DIR / "browsermind_core" / "evaluation" / "state_verification" / "rules" / f"{site_key}.yaml"
                    if yaml_path.exists():
                        config = load_verification_config(str(yaml_path))
                        verifier = StateVerifier(page)
                        verification_report = await verifier.verify(config)
                        report.verification_report = verification_report.model_dump()
                except Exception as exc:
                    import traceback as _tb
                    report.verification_error = {
                        "type": type(exc).__name__,
                        "message": str(exc),
                        "traceback": _tb.format_exc(),
                    }
                    print(
                        f"  [ReplayEngine] StateVerifier failed: "
                        f"{type(exc).__name__}: {exc}"
                    )

                # ContractVerifier — runtime "did the goal complete?" check.
                # Tries template name, then env instance key. Records one
                # OutcomeRecord(outcome_type='contract_verification') and
                # attaches the result to the report. Best-effort.
                try:
                    from browsermind_core.runtime.contract_verifier import (
                        ContractVerifier as _CV,
                        lookup_contract as _lookup_contract,
                    )
                    contract = _lookup_contract(
                        template.name,
                        (template.metadata or {}).get("contract_id", "") if template.metadata else "",
                        site_key,
                    )
                    if contract is not None:
                        cv_report = await _CV().verify(page, contract)
                        report.contract_verification = cv_report
                        if self.outcome_ledger is not None and self.persona_id is not None:
                            from browsermind_core.ledger.outcome_ledger import OutcomeRecord
                            self.outcome_ledger.record(OutcomeRecord(
                                scope="task" if self.task_id else "workflow_instance",
                                scope_id=self.task_id or instance.id,
                                persona_id=self.persona_id,
                                environment_family=self.environment_family or "",
                                environment_instance=self.environment_instance or site_key,
                                outcome_type="contract_verification",
                                success=bool(cv_report.get("goal_completed")),
                                evidence=(
                                    f"contract={contract.task_id} "
                                    f"goal_completed={cv_report.get('goal_completed')} "
                                    f"url={cv_report.get('contract_evidence', {}).get('url_at_verification', '')}"
                                ),
                                execution_id=self._active_execution_id,
                                task_id=self.task_id,
                                metrics={
                                    "contract_id": contract.task_id,
                                    "conditions_total": len(contract.conditions),
                                    "conditions_satisfied": sum(
                                        1 for c in cv_report.get("contract_evidence", {}).get("conditions", {}).values()
                                        if c.get("satisfied")
                                    ),
                                },
                            ))
                except Exception as exc:
                    print(f"  [ReplayEngine] ContractVerifier failed: {type(exc).__name__}: {exc}")

                # M5+M6+M7: Session continuity. Only close when this engine
                # owns the session lifecycle. When the caller manages the
                # AuthSession across multiple replays, leave the browser
                # process and persistent context alive.
                if self.owns_session:
                    await self.auth_session.close()

        report.duration_seconds = time.time() - start_time
        if report.total_steps > 0:
            report.resolution_rate = report.resolved_steps / report.total_steps
            ambiguous = getattr(report, 'ambiguous_steps', 0)
            report.ambiguity_rate = round(ambiguous / report.total_steps, 4)
            report.resource_resolution_rate = resource_resolver.get_resolution_rate()
            
            # Calculate recovery_rate
            drifted_steps = 0
            recovered_steps = 0
            for attr in report.failure_attribution:
                if attr.actual_outcome == "SKIPPED":
                    continue
                if attr.resolved_by not in ("exact_selector", "primary_semantic"):
                    drifted_steps += 1
                    if attr.resolution_success:
                        recovered_steps += 1
            report.recovery_rate = round((recovered_steps / drifted_steps) * 100.0, 2) if drifted_steps > 0 else None

        if is_resume:
            env_key = site.key if site else "unknown"
            R0Logger.log_event(
                self.auth_session.store_dir,
                "workflow_resume",
                workflow=template.name,
                environment=env_key,
                step_index=start_step_index,
                status=report.status
            )

        # P7B: Compile dependency order from the executed steps of the template
        if report.status in ("SUCCESS", "INTERRUPTED", "BLOCKED"):
            observed_dependencies = []
            for step_idx in range(report.resolved_steps):
                if step_idx < len(template.steps):
                    step = template.steps[step_idx]
                    binding = step.get("input_binding")
                    if binding:
                        b_key = binding.get("key")
                        if b_key and b_key not in observed_dependencies:
                            observed_dependencies.append(b_key)
                    else:
                        cap_hint = step.get("descriptor", {}).get("capability_hint", "")
                        # Include verification or submission gates
                        if cap_hint and any(kw in cap_hint.lower() for kw in ("submit", "captcha", "verification", "terms", "age", "gate")):
                            if cap_hint not in observed_dependencies:
                                observed_dependencies.append(cap_hint)
            
            if observed_dependencies:
                import json
                import datetime
                dep_entry = {
                    "workflow": template.name,
                    "observed_sequence": observed_dependencies,
                    "timestamp": datetime.datetime.now().isoformat()
                }
                dep_path = os.path.join(self.auth_session.store_dir, "dependency_ledger.jsonl")
                try:
                    with open(dep_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(dep_entry) + "\n")
                except Exception as e:
                    print(f"  [ReplayEngine] Failed to write to dependency ledger: {e}")
                
                # Also log to R0 evidence ledger under workflow_dependency event
                R0Logger.log_event(
                    self.auth_session.store_dir,
                    "workflow_dependency",
                    workflow=template.name,
                    observed_sequence=observed_dependencies
                )

        _env_key_final = site.key if site is not None else "unknown"
        self._record_replay_accuracy(report, template, instance, _env_key_final)
        # ContractGate: verify goal completion against live page before writing OutcomeRecord.
        await self._verify_contract_outcome_async(page, template, _env_key_final)
        self._record_replay_outcome(report, template, instance)
        self._record_step_outcomes(report, template, instance, _env_key_final)

        # Capability Loop — Addition 1: post-execution failure pattern mining
        self._mine_step_outcomes(self._active_execution_id, _env_key_final)

        # Capability Loop — Additions 2 + 3: invariant compilation + promotion
        self._compile_and_promote(template, _env_key_final)

        # Capability Loop — Addition 5: capability-level state transition validation.
        # Build the set of intent tokens completed this run from FailureAttribution,
        # then check all known CapabilityRecord contracts whose invariants are covered.
        try:
            from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer
            _normalizer = PrimitiveNormalizer(collapse_level=1)
            _completed_intents: set = set()
            for _attr in report.failure_attribution:
                if _attr.actual_outcome in ("SUCCESS", "TRANSITION_SUCCESS"):
                    _intent = _normalizer.normalize(
                        action_type=_attr.action_type or "",
                        target_role=_attr.role or "",
                        target_name=_attr.name or "",
                    )
                    _completed_intents.add(_intent)
        except Exception:
            _completed_intents = set()
        await self._verify_capabilities_in_execution(page, _env_key_final, _completed_intents)

        # Phase 3: delete checkpoint on successful run so resume doesn't re-run
        if report.status == "SUCCESS" and self._hardening is not None:
            try:
                self._hardening.delete_checkpoint()
            except Exception:
                pass

        # Phase 4: cancel the interrupt watcher background task
        if _interrupt_watcher is not None:
            try:
                _interrupt_watcher.cancel()
                # Await cancellation to prevent "task was destroyed but pending" warnings
                try:
                    await asyncio.wait_for(_interrupt_watcher, timeout=0.5)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            except Exception:
                pass

        self._close_execution_if_wired(report)
        return report
