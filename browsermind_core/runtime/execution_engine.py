from uuid import UUID
from typing import Optional, Dict
from browsermind_core.ontology.p1_schemas import Execution, ExecutionContext
from browsermind_core.runtime.event_bus import EventBus
from browsermind_core.managers.policy.policy_engine import PolicyEngine
from browsermind_core.runtime.execution_repository import ExecutionRepository


class ExecutionEngine:
    def __init__(
        self,
        event_bus: EventBus,
        policy_engine: PolicyEngine,
        repository: Optional[ExecutionRepository] = None,
        max_retries: int = 3,
    ):
        self.event_bus = event_bus
        self.policy_engine = policy_engine
        self.repository = repository
        self.max_retries = max_retries
        self._executions: Dict[UUID, Execution] = {}

    def _checkpoint(self, execution: Execution):
        if self.repository:
            self.repository.save_execution(execution)
            self.repository.save_snapshot(execution)

    def _emit_mutation(self, execution: Execution, old_status: str, actor: str = "ExecutionEngine", **extra):
        payload = {
            "entity_type": "Execution",
            "entity_id": execution.id,
            "old_value": {"status": old_status},
            "new_value": execution.model_dump(mode="json"),
            "actor": actor,
            **extra,
        }
        self.event_bus.emit("EntityMutated", payload)

    def start_execution(
        self,
        task_id: UUID,
        workflow_instance_id: UUID,
        target_template_id: UUID,
        persona_id: UUID,
        identity_id: Optional[UUID] = None,
        environment_id: Optional[UUID] = None,
    ) -> Execution:
        approval_level = self.policy_engine.evaluate(persona_id, target_template_id)

        ctx = ExecutionContext(
            persona_id=persona_id,
            task_id=task_id,
            workflow_instance_id=workflow_instance_id,
            template_id=target_template_id,
            identity_id=identity_id,
            environment_id=environment_id,
        )

        execution = Execution(
            task_id=task_id,
            workflow_instance_id=workflow_instance_id,
            approval_level=approval_level,  # type: ignore
            status="running",
            context=ctx,
        )
        self._executions[execution.id] = execution
        self._checkpoint(execution)
        self._emit_mutation(execution, old_status="none", policy=approval_level)
        return execution

    def pause_execution(self, execution_id: UUID):
        execution = self._get_or_raise(execution_id)
        assert execution.status == "running", f"Cannot pause from status={execution.status}"
        old = execution.status
        execution.status = "paused"
        self._checkpoint(execution)
        self._emit_mutation(execution, old_status=old)

    def resume_execution(self, execution_id: UUID):
        execution = self._get_or_raise(execution_id)
        assert execution.status == "paused", f"Cannot resume from status={execution.status}"
        old = execution.status
        execution.status = "running"
        self._checkpoint(execution)
        self._emit_mutation(execution, old_status=old)

    def fail_execution(self, execution_id: UUID, reason: str):
        execution = self._get_or_raise(execution_id)
        old = execution.status
        execution.status = "failed"
        execution.failure_reason = reason
        self._checkpoint(execution)
        self._emit_mutation(execution, old_status=old, evidence=reason)

    def retry_execution(self, execution_id: UUID):
        execution = self._get_or_raise(execution_id)
        assert execution.status == "failed", f"Cannot retry from status={execution.status}"
        if execution.retry_count >= self.max_retries:
            raise RuntimeError(
                f"Max retries exhausted for execution {execution_id} "
                f"(max={self.max_retries})"
            )
        old = execution.status
        execution.status = "running"
        execution.retry_count += 1
        execution.failure_reason = None
        self._checkpoint(execution)
        self._emit_mutation(execution, old_status=old)

    def complete_execution(self, execution_id: UUID, outcome: str):
        execution = self._get_or_raise(execution_id)
        old = execution.status
        execution.status = "succeeded" if outcome == "success" else "failed"
        self._checkpoint(execution)
        self._emit_mutation(execution, old_status=old, evidence=outcome)

    def rehydrate_execution(self, execution_id: UUID) -> Optional[Execution]:
        if not self.repository:
            return None
        snap = self.repository.load_latest_valid_snapshot(execution_id)
        if snap is None:
            return None
        execution = Execution.model_validate(snap.execution_state)
        self._executions[execution.id] = execution
        self.event_bus.emit("ExecutionRehydrated", {
            "entity_id": str(execution.id),
            "status": execution.status,
            "from_snapshot_seq": snap.sequence,
        })
        return execution

    def get_execution(self, execution_id: UUID) -> Optional[Execution]:
        return self._executions.get(execution_id)

    def _get_or_raise(self, execution_id: UUID) -> Execution:
        execution = self._executions.get(execution_id)
        if execution is None:
            raise KeyError(f"Execution {execution_id} not found in memory. Rehydrate first.")
        return execution
