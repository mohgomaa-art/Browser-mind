"""
Command Layer for BrowserMind UI.
UI Views should only call these commands, passing the AppContext.
"""
from uuid import UUID, uuid4
from browsermind_ui.core.app_context import AppContext

def create_persona_command(ctx: AppContext, name: str, principal_name: str) -> bool:
    sess = ctx.session
    entry = sess._lookup("principal", principal_name)
    if not entry:
        # Auto-create principal for UI ease
        idx = sess._load_index("principal")
        if not idx:
            p = sess.principal_manager.create_principal(name="Default User", principal_type="user")
            sess._register("principal", "Default User", str(p.id))
            entry = {"id": str(p.id)}
        else:
            return False
            
    p = sess.persona_manager.create_persona(principal_id=UUID(entry["id"]), name=name)
    sess._register("persona", name, str(p.id), {"principal": principal_name or "Default User"})
    return True

def ensure_persona(ctx: AppContext, persona_name: str, principal_name: str = "Default User") -> bool:
    """Create principal + persona if missing (UI bootstrap)."""
    sess = ctx.session
    if sess._lookup("persona", persona_name):
        return True
    if not sess._lookup("principal", principal_name):
        p = sess.principal_manager.create_principal(
            name=principal_name, principal_type="user"
        )
        sess._register("principal", principal_name, str(p.id))
    return create_persona_command(ctx, persona_name, principal_name)


def create_task_command(ctx: AppContext, goal: str, persona_name: str) -> bool:
    sess = ctx.session
    if not ensure_persona(ctx, persona_name):
        return False
    entry = sess._lookup("persona", persona_name)
    if not entry:
        return False
        
    t = sess.task_manager.create_task(persona_id=UUID(entry["id"]), goal=goal)
    task_name = goal[:30].replace(" ", "_").lower()
    sess._register("task", task_name, str(t.id), {"persona": persona_name, "goal": goal})
    return True

def create_identity_command(ctx: AppContext, identifier: str, persona_name: str, secret: str) -> bool:
    sess = ctx.session
    entry = sess._lookup("persona", persona_name)
    if not entry:
        return False
        
    env_id = uuid4()
    ident = sess.identity_service.provision_identity(
        persona_id=UUID(entry["id"]),
        environment_id=env_id,
        identifier=identifier,
        raw_secret=secret,
    )
    sess._register("identity", identifier, str(ident.id), {"persona": persona_name, "env": str(env_id)})
    return True

def start_execution_command(ctx: AppContext, task_name: str, persona_name: str) -> bool:
    sess = ctx.session
    task_entry = sess._lookup("task", task_name)
    persona_entry = sess._lookup("persona", persona_name)
    if not task_entry or not persona_entry:
        return False
        
    persona_id = UUID(persona_entry["id"])
    insts = sess.workflow_store.list_instances()
    tpls = sess.workflow_store.list_templates()
    workflow_instance_id = UUID(insts[0]["id"]) if insts else uuid4()
    template_id = UUID(tpls[0]["id"]) if tpls else uuid4()
    sess.policy_engine.set_policy(persona_id, template_id, "auto")

    exc = sess.execution_engine.start_execution(
        task_id=UUID(task_entry["id"]),
        workflow_instance_id=workflow_instance_id,
        target_template_id=template_id,
        persona_id=persona_id,
    )
    sess._register(
        "execution",
        str(exc.id)[:8],
        str(exc.id),
        {"task": task_name, "persona": persona_name, "status": exc.status},
    )
    ctx.session.event_bus.emit(
        "EntityMutated",
        {
            "entity_type": "Execution",
            "entity_id": exc.id,
            "new_value": exc.model_dump(mode="json"),
            "actor": "ui",
        },
    )
    return True

def pause_execution_command(ctx: AppContext, exec_id: str):
    sess = ctx.session
    entry = sess._lookup("execution", exec_id)
    if entry:
        uuid_val = UUID(entry["id"])
        sess.execution_engine.rehydrate_execution(uuid_val)
        sess.execution_engine.pause_execution(uuid_val)
        _update_exec_status(ctx, exec_id, "paused")

def resume_execution_command(ctx: AppContext, exec_id: str):
    sess = ctx.session
    entry = sess._lookup("execution", exec_id)
    if entry:
        uuid_val = UUID(entry["id"])
        sess.execution_engine.rehydrate_execution(uuid_val)
        sess.execution_engine.resume_execution(uuid_val)
        _update_exec_status(ctx, exec_id, "running")

def fail_execution_command(ctx: AppContext, exec_id: str, reason: str = "Manual failure"):
    sess = ctx.session
    entry = sess._lookup("execution", exec_id)
    if entry:
        uuid_val = UUID(entry["id"])
        sess.execution_engine.rehydrate_execution(uuid_val)
        sess.execution_engine.fail_execution(uuid_val, reason=reason)
        _update_exec_status(ctx, exec_id, "failed")

def retry_execution_command(ctx: AppContext, exec_id: str) -> str:
    """Returns error message if fails, else empty string"""
    sess = ctx.session
    entry = sess._lookup("execution", exec_id)
    if entry:
        uuid_val = UUID(entry["id"])
        sess.execution_engine.rehydrate_execution(uuid_val)
        try:
            sess.execution_engine.retry_execution(uuid_val)
            _update_exec_status(ctx, exec_id, "running")
            return ""
        except RuntimeError as e:
            return str(e)
    return "Execution not found"

def _update_exec_status(ctx: AppContext, exec_id: str, status: str):
    idx = ctx.session._load_index("execution")
    if exec_id in idx:
        idx[exec_id]["status"] = status
        ctx.session._save_index("execution", idx)
        # Manually trigger a UI refresh for the index update
        ctx.notifier.entity_mutated.emit("execution_index", exec_id)
