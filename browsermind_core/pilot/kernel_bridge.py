"""Wire Playwright pilot steps to KernelSession (ledger + execution + outcome)."""
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from browsermind_core.console.session import KernelSession
from browsermind_core.ledger.outcome_ledger import OutcomeRecord
from browsermind_core.runtime.environment_config import EnvironmentInstanceConfig
from browsermind_core.runtime.event_bus import EventBus


class PilotKernelBridge:
    """Bootstrap kernel entities and emit Mutation + Outcome for a pilot run."""

    def __init__(self, session: KernelSession, env: EnvironmentInstanceConfig):
        self.session = session
        self.env = env
        self.bus: EventBus = session.event_bus
        self.template_id: Optional[UUID] = None
        self.instance_id: Optional[UUID] = None
        self.persona_id: Optional[UUID] = None
        self.task_id: Optional[UUID] = None
        self.execution_id: Optional[UUID] = None
        self._step_seq = 0

    def bootstrap_persona(self, persona_name: str, principal_name: str = "pilot") -> UUID:
        from uuid import UUID as _UUID

        p_entry = self.session._lookup("principal", principal_name)
        if not p_entry:
            p = self.session.principal_manager.create_principal(
                name=principal_name, principal_type="user"
            )
            self.session._register("principal", principal_name, str(p.id))
            principal_id = p.id
        else:
            principal_id = _UUID(p_entry["id"])

        pe = self.session._lookup("persona", persona_name)
        if not pe:
            persona = self.session.persona_manager.create_persona(
                principal_id=principal_id, name=persona_name
            )
            self.session._register(
                "persona", persona_name, str(persona.id), {"principal": principal_name}
            )
            self.persona_id = persona.id
        else:
            self.persona_id = _UUID(pe["id"])
        return self.persona_id

    def register_workflow_binding(
        self,
        template_name: str | None = None,
        instance_name: str | None = None,
    ):
        assert self.persona_id
        tpl_name = template_name or f"{self.env.family_key}_login"
        inst_name = instance_name or f"{self.env.family_key}_pilot"
        persona_entry = None
        for name, entry in self.session._load_index("persona").items():
            if entry.get("id") == str(self.persona_id):
                persona_entry = name
                break
        profile = str(self.env.profile_dir(self.session.store_dir, persona_name=persona_entry or str(self.persona_id)))

        tpl_entry = self.session.workflow_store.lookup_template(tpl_name)
        if tpl_entry:
            tpl = self.session.workflow_store.get_template(UUID(tpl_entry["id"]))
        else:
            tpl = self.session.workflow_store.create_template(
                name=tpl_name,
                description="P1 smoke: login flow",
                family_key=self.env.family_key,
            )
        inst = self.session.workflow_store.create_instance(
            name=inst_name,
            persona_id=self.persona_id,
            template_id=tpl.id,
            environment_family=self.env.family_key,
            environment_instance=self.env.origin,
            profile_path=profile,
        )
        self.template_id = tpl.id
        self.instance_id = inst.id

        self._emit(
            "WorkflowTemplate",
            tpl.id,
            None,
            {
                "name": tpl_name,
                "family_key": self.env.family_key,
                "description": tpl.description,
            },
        )
        self._emit(
            "WorkflowInstance",
            inst.id,
            None,
            {
                "template_id": str(tpl.id),
                "persona_id": str(self.persona_id),
                "environment_family": self.env.family_key,
                "environment_instance": self.env.origin,
                "profile_path": profile,
            },
        )

    def create_task(self, goal: str, task_index_name: str, persona_name: str = "pilot") -> UUID:
        assert self.persona_id
        task = self.session.task_manager.create_task(persona_id=self.persona_id, goal=goal)
        self.task_id = task.id
        self.session._register(
            "task",
            task_index_name,
            str(task.id),
            {"persona": persona_name, "goal": goal},
        )
        return task.id

    def start_execution(self, policy: str = "auto", task_index_name: str = "pilot_login", persona_name: str = "pilot"):
        assert self.persona_id and self.task_id and self.instance_id and self.template_id
        from browsermind_core.managers.policy.policy_engine import PolicyEngine

        pe: PolicyEngine = self.session.policy_engine
        pe.set_policy(self.persona_id, self.template_id, policy)
        exc = self.session.execution_engine.start_execution(
            task_id=self.task_id,
            workflow_instance_id=self.instance_id,
            target_template_id=self.template_id,
            persona_id=self.persona_id,
            environment_id=uuid4(),
        )
        self.execution_id = exc.id
        self.session._register(
            "execution",
            str(exc.id)[:8],
            str(exc.id),
            {"task": task_index_name, "persona": persona_name, "status": exc.status},
        )
        return exc

    def checkpoint_pause_resume(self):
        """Optional P1 proof: pause + resume emits extra mutations."""
        assert self.execution_id
        eid = self.execution_id
        self.session.execution_engine.pause_execution(eid)
        self.pilot_step("kernel_pause")
        self.session.execution_engine.resume_execution(eid)
        self.pilot_step("kernel_resume")

    def pilot_step(self, name: str, detail: Optional[Dict[str, Any]] = None):
        assert self.execution_id
        self._step_seq += 1
        prev = self._step_seq - 1
        self._emit(
            "PilotStep",
            self.execution_id,
            {"seq": prev, "name": name} if prev else None,
            {"seq": self._step_seq, "name": name, **(detail or {})},
            evidence=name,
        )

    def complete_execution(
        self,
        success: bool,
        task_index_name: str = "pilot_login",
        persona_name: str = "pilot",
    ):
        assert self.execution_id
        self.session.execution_engine.complete_execution(
            self.execution_id, outcome="success" if success else "failure"
        )
        exc = self.session.execution_engine.get_execution(self.execution_id)
        status = exc.status if exc else ("succeeded" if success else "failed")
        self.session._register(
            "execution",
            str(self.execution_id)[:8],
            str(self.execution_id),
            {"task": task_index_name, "persona": persona_name, "status": status},
        )

    def record_outcome(self, success: bool, evidence: str, outcome_type: str = "login_succeeded"):
        assert self.persona_id and self.execution_id
        record = OutcomeRecord(
            scope="execution",
            scope_id=self.execution_id,
            persona_id=self.persona_id,
            environment_family=self.env.family_key,
            environment_instance=self.env.origin,
            outcome_type=outcome_type,
            success=success,
            evidence=evidence,
            execution_id=self.execution_id,
            task_id=self.task_id,
        )
        self.session.outcome_ledger.record(record)
        return record

    def mutation_count(self) -> int:
        return self.session.ledger_repo.count()

    def _emit(
        self,
        entity_type: str,
        entity_id: UUID,
        old_value: Optional[Dict[str, Any]],
        new_value: Dict[str, Any],
        evidence: Optional[str] = None,
    ):
        self.bus.emit(
            "EntityMutated",
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "old_value": old_value,
                "new_value": new_value,
                "actor": "run_workflow_pilot",
                "evidence": evidence,
            },
        )
