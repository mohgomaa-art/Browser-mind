"""
browsermind_core/console/cli.py
The BrowserMind Console — `bm` command.
"""
import click
import json
import sys
from uuid import uuid4
from browsermind_core.console.session import KernelSession

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


def _session(ctx) -> KernelSession:
    return ctx.ensure_object(KernelSession)


def _ok(msg: str):
    click.echo(click.style("[OK] ", fg="green") + msg)


def _err(msg: str):
    click.echo(click.style("[ERR] ", fg="red") + msg, err=True)
    sys.exit(1)


def _print_table(rows: list[dict], keys: list[str]):
    if not rows:
        click.echo(click.style("  (empty)", dim=True))
        return
    widths = {k: max(len(k), max(len(str(r.get(k, ""))) for r in rows)) for k in keys}
    header = "  ".join(k.upper().ljust(widths[k]) for k in keys)
    click.echo(click.style(header, bold=True))
    click.echo("-" * len(header))
    for row in rows:
        click.echo("  ".join(str(row.get(k, "")).ljust(widths[k]) for k in keys))


# =============================================================================
# Root
# =============================================================================

@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("--store", default=None, help="Override default store directory (~/.browsermind)")
@click.pass_context
def cli(ctx, store):
    """BrowserMind Kernel Console"""
    from browsermind_core.console.session import DEFAULT_STORE
    ctx.obj = KernelSession(store or DEFAULT_STORE)


# =============================================================================
# bm principal
# =============================================================================

@cli.group()
def principal():
    """Manage Principals (users, teams, API clients)"""


@principal.command("create")
@click.argument("name")
@click.option("--type", "principal_type", default="user",
              type=click.Choice(["user", "organization", "team", "api_client"]),
              show_default=True)
@click.pass_context
def principal_create(ctx, name, principal_type):
    """Create a new Principal."""
    s = _session(ctx)
    p = s.principal_manager.create_principal(name=name, principal_type=principal_type)
    s._register("principal", name, str(p.id))
    _ok(f"Principal '{name}' created  [{str(p.id)[:8]}…]")


@principal.command("ls")
@click.pass_context
def principal_ls(ctx):
    """List all Principals."""
    s = _session(ctx)
    idx = s._load_index("principal")
    rows = [{"name": k, "id": v["id"][:8] + "…"} for k, v in idx.items()]
    _print_table(rows, ["name", "id"])


# =============================================================================
# bm persona
# =============================================================================

@cli.group()
def persona():
    """Manage Personas (sandboxed contexts)"""


@persona.command("create")
@click.argument("name")
@click.option("--principal", "principal_name", required=True, help="Principal name or ID prefix")
@click.option("--desc", default="", help="Optional description")
@click.pass_context
def persona_create(ctx, name, principal_name, desc):
    """Create a new Persona for a Principal."""
    s = _session(ctx)
    entry = s._lookup("principal", principal_name)
    if not entry:
        _err(f"Principal '{principal_name}' not found. Run: bm principal create {principal_name}")
    from uuid import UUID
    p = s.persona_manager.create_persona(
        principal_id=UUID(entry["id"]), name=name
    )
    s._register("persona", name, str(p.id), {"principal": principal_name})
    _ok(f"Persona '{name}' created  [{str(p.id)[:8]}…]")


@persona.command("ls")
@click.pass_context
def persona_ls(ctx):
    """List all Personas."""
    s = _session(ctx)
    idx = s._load_index("persona")
    rows = [{"name": k, "principal": v.get("principal",""), "id": v["id"][:8] + "…"} for k, v in idx.items()]
    _print_table(rows, ["name", "principal", "id"])


# =============================================================================
# bm identity
# =============================================================================

@cli.group()
def identity():
    """Manage Identities and Secrets"""


@identity.command("create")
@click.argument("identifier")
@click.option("--persona", "persona_name", required=True)
@click.option("--env", "env_id", default=None, help="Environment ID (UUID). Defaults to a new UUID.")
@click.option("--secret", "raw_secret", required=True, prompt=True, hide_input=True,
              confirmation_prompt=True, help="Secret / password (input hidden)")
@click.pass_context
def identity_create(ctx, identifier, persona_name, env_id, raw_secret):
    """Provision an Identity and store its Secret in the Vault."""
    s = _session(ctx)
    entry = s._lookup("persona", persona_name)
    if not entry:
        _err(f"Persona '{persona_name}' not found.")
    from uuid import UUID
    env = UUID(env_id) if env_id else uuid4()
    ident = s.identity_service.provision_identity(
        persona_id=UUID(entry["id"]),
        environment_id=env,
        identifier=identifier,
        raw_secret=raw_secret,
    )
    s._register("identity", identifier, str(ident.id), {"persona": persona_name, "env": str(env)})
    _ok(f"Identity '{identifier}' created and Secret stored in Vault  [{str(ident.id)[:8]}…]")


@identity.command("ls")
@click.pass_context
def identity_ls(ctx):
    """List all Identities."""
    s = _session(ctx)
    idx = s._load_index("identity")
    rows = [{"identifier": k, "persona": v.get("persona",""), "env": v.get("env","")[:8]+"…", "id": v["id"][:8]+"…"} for k, v in idx.items()]
    _print_table(rows, ["identifier", "persona", "env", "id"])


# =============================================================================
# bm task
# =============================================================================

@cli.group()
def task():
    """Manage Tasks"""


@task.command("create")
@click.argument("goal")
@click.option("--persona", "persona_name", required=True)
@click.pass_context
def task_create(ctx, goal, persona_name):
    """Create a Task for a Persona."""
    s = _session(ctx)
    entry = s._lookup("persona", persona_name)
    if not entry:
        _err(f"Persona '{persona_name}' not found.")
    from uuid import UUID
    t = s.task_manager.create_task(persona_id=UUID(entry["id"]), goal=goal)
    task_name = goal[:30].replace(" ", "_").lower()
    s._register("task", task_name, str(t.id), {"persona": persona_name, "goal": goal})
    _ok(f"Task '{goal}' created  [{str(t.id)[:8]}…]")


@task.command("ls")
@click.pass_context
def task_ls(ctx):
    """List all Tasks."""
    s = _session(ctx)
    idx = s._load_index("task")
    rows = [{"name": k, "persona": v.get("persona",""), "goal": v.get("goal","")[:40], "id": v["id"][:8]+"…"} for k, v in idx.items()]
    _print_table(rows, ["name", "persona", "goal", "id"])


# =============================================================================
# bm record (P2A)
# =============================================================================

@cli.group()
def record():
    """P2A — record raw human demonstrations (not replay)"""


@record.command("start")
@click.option("--env", "env_key", default="saucedemo", show_default=True)
@click.option("--persona", "persona_name", default="pilot", show_default=True)
@click.option("--url", default=None, help="Override start URL")
@click.option("--headless", is_flag=True)
@click.pass_context
def record_start(ctx, env_key, persona_name, url, headless):
    """Open warmed profile; capture clicks/inputs until Enter."""
    import asyncio

    from browsermind_core.recorder.record_runner import run_recording_session

    s = _session(ctx)
    session = asyncio.run(
        run_recording_session(
            s.store_dir,
            env_key,
            persona_name,
            headless=headless,
            start_url=url,
        )
    )
    _ok(
        f"Demonstration saved  [{str(session.id)[:8]}…]  "
        f"actions={len(session.actions)}  family={session.environment_family}"
    )


@record.command("ls")
@click.option("--n", default=20, show_default=True)
@click.pass_context
def record_ls(ctx, n):
    """List saved demonstration sessions."""
    from browsermind_core.recorder.demonstration_repository import DemonstrationRepository

    s = _session(ctx)
    rows = DemonstrationRepository(s.store_dir).list_sessions(n)
    _print_table(
        [
            {
                "id": r["id"][:8] + "…",
                "family": r.get("family", ""),
                "persona": r.get("persona", ""),
                "actions": str(r.get("actions", 0)),
                "status": r.get("status", ""),
            }
            for r in rows
        ],
        ["id", "family", "persona", "actions", "status"],
    )


@record.command("show")
@click.argument("session_id")
@click.pass_context
def record_show(ctx, session_id):
    """Show actions for a demonstration session."""
    from uuid import UUID

    from browsermind_core.recorder.demonstration_repository import DemonstrationRepository

    s = _session(ctx)
    repo = DemonstrationRepository(s.store_dir)
    sid = None
    for row in repo.list_sessions(500):
        if row["id"].startswith(session_id):
            sid = UUID(row["id"])
            break
    if not sid:
        _err(f"Session '{session_id}' not found.")
    session = repo.load(sid)
    if not session:
        _err("Could not load session.")
    click.echo(click.style(f"\n  Session {session.id}\n", bold=True))
    click.echo(f"  family={session.environment_family}  actions={len(session.actions)}")
    for act in session.actions[:40]:
        hint = (act.target_selector or act.target_name or "")[:48]
        click.echo(
            f"  {act.seq:3d}  {act.action_type:<12}  {hint:<48}  {act.url[:40]}"
        )
    if len(session.actions) > 40:
        click.echo(click.style(f"  ... +{len(session.actions) - 40} more", dim=True))

@record.command("compile")
@click.argument("session_id")
@click.argument("template_name")
@click.pass_context
def record_compile(ctx, session_id, template_name):
    """Compile a demonstration session into a reusable WorkflowTemplate."""
    from uuid import UUID
    from browsermind_core.recorder.demonstration_repository import DemonstrationRepository
    from browsermind_core.recorder.demonstration_compiler import DemonstrationCompiler

    s = _session(ctx)
    repo = DemonstrationRepository(s.store_dir)
    sid = None
    for row in repo.list_sessions(500):
        if row["id"].startswith(session_id):
            sid = UUID(row["id"])
            break
    if not sid:
        _err(f"Session '{session_id}' not found.")
    session = repo.load(sid)
    if not session:
        _err("Could not load session.")
        
    compiler = DemonstrationCompiler(s)
    tpl = compiler.compile(session, template_name)
    _ok(f"Compiled template '{template_name}' from session [{str(session.id)[:8]}…] with {len(tpl.steps)} steps")


# =============================================================================
# bm workflow
# =============================================================================

@cli.group()
def workflow():
    """Manage WorkflowTemplate and WorkflowInstance (see WORKFLOW_CONTRACT.md)"""


@workflow.group("template")
def workflow_template():
    """System-level workflow templates"""


@workflow_template.command("create")
@click.argument("name")
@click.option("--family", "family_key", default="", help="Environment family key (e.g. saucedemo)")
@click.option("--desc", default="", help="Description")
@click.pass_context
def workflow_template_create(ctx, name, family_key, desc):
    """Create a WorkflowTemplate."""
    s = _session(ctx)
    tpl = s.workflow_store.create_template(
        name=name, description=desc, family_key=family_key
    )
    s.event_bus.emit(
        "EntityMutated",
        {
            "entity_type": "WorkflowTemplate",
            "entity_id": tpl.id,
            "new_value": tpl.model_dump(mode="json"),
            "actor": "cli",
        },
    )
    _ok(f"WorkflowTemplate '{name}'  [{str(tpl.id)[:8]}…]")


@workflow_template.command("ls")
@click.pass_context
def workflow_template_ls(ctx):
    """List WorkflowTemplates."""
    s = _session(ctx)
    rows = s.workflow_store.list_templates()
    _print_table(
        [{"name": r["name"], "family": r.get("family_key", ""), "id": r["id"][:8] + "…"} for r in rows],
        ["name", "family", "id"],
    )


@workflow.group("candidate")
def workflow_candidate():
    """Pending TemplateCandidate review surface."""


@workflow_candidate.command("ls")
@click.option("--status", default=None, help="Filter by status")
@click.pass_context
def workflow_candidate_ls(ctx, status):
    """List TemplateCandidates (optionally filtered by status)."""
    s = _session(ctx)
    rows = s.candidate_registry.list(status=status)
    _print_table(
        [
            {
                "id": str(c.id)[:8] + "…",
                "parent_id": str(c.parent_id)[:8] + "…",
                "status": c.status,
                "created_at": c.created_at.isoformat(),
                "mutations": len(c.mutations),
            }
            for c in rows
        ],
        ["id", "parent_id", "status", "created_at", "mutations"],
    )


@workflow_candidate.command("approve")
@click.argument("candidate_id")
@click.pass_context
def workflow_candidate_approve(ctx, candidate_id):
    """Approve a TemplateCandidate and commit its mutations."""
    s = _session(ctx)
    from uuid import UUID
    from datetime import datetime, timezone
    cand = s.candidate_registry.get(UUID(candidate_id))
    if cand is None:
        return _err(f"No candidate {candidate_id}")
    if cand.status != "pending":
        return _err(f"Candidate is {cand.status}, must be pending")
    tpl_data = s.workflow_store.provider.load(s.workflow_store.NS_TEMPLATE, str(cand.parent_id))
    if tpl_data is None:
        return _err("Parent template not found")
    for m in cand.mutations:
        if m["type"] == "tier_downgrade":
            idx = m["step_seq"]
            if 0 <= idx < len(tpl_data["steps"]):
                repl = dict(tpl_data["steps"][idx].get("replayability") or {})
                repl["tier"] = m["to_tier"]
                repl["committed_via"] = "approval"
                tpl_data["steps"][idx]["replayability"] = repl
    tpl_data.setdefault("metadata", {})
    tpl_data["metadata"]["committed_candidate_id"] = str(cand.id)
    s.workflow_store.provider.save(s.workflow_store.NS_TEMPLATE, str(cand.parent_id), tpl_data)
    s.candidate_registry.update_status(cand.id, "committed", committed_at=datetime.now(timezone.utc))
    _ok(f"Committed candidate {str(cand.id)[:8]}… on template {str(cand.parent_id)[:8]}…")


@workflow_candidate.command("reject")
@click.argument("candidate_id")
@click.pass_context
def workflow_candidate_reject(ctx, candidate_id):
    """Reject a pending TemplateCandidate."""
    s = _session(ctx)
    from uuid import UUID
    s.candidate_registry.update_status(UUID(candidate_id), "rejected")
    _ok(f"Rejected candidate {candidate_id[:8]}…")


@workflow_candidate.command("rollback")
@click.argument("candidate_id")
@click.pass_context
def workflow_candidate_rollback(ctx, candidate_id):
    """Restore parent template steps from candidate.previous_state."""
    s = _session(ctx)
    from uuid import UUID
    cand = s.candidate_registry.get(UUID(candidate_id))
    if cand is None:
        return _err(f"No candidate {candidate_id}")
    if cand.status != "committed":
        return _err(f"Only committed candidates can be rolled back; status={cand.status}")
    tpl_data = s.workflow_store.provider.load(s.workflow_store.NS_TEMPLATE, str(cand.parent_id))
    if tpl_data is None or cand.previous_state is None:
        return _err("Parent or previous_state missing")
    tpl_data["steps"] = cand.previous_state["steps"]
    tpl_data.setdefault("metadata", {})
    tpl_data["metadata"]["rolled_back_candidate_id"] = str(cand.id)
    s.workflow_store.provider.save(s.workflow_store.NS_TEMPLATE, str(cand.parent_id), tpl_data)
    s.candidate_registry.update_status(cand.id, "rolled_back")
    _ok(f"Rolled back candidate {str(cand.id)[:8]}…")


# =============================================================================
# bm recovery
# =============================================================================

@cli.group("recovery")
def recovery():
    """Mined recovery strategy lifecycle."""


@recovery.group("candidate")
def recovery_candidate():
    """RecoveryCandidate review surface."""


@recovery_candidate.command("ls")
@click.option("--status", default=None)
@click.pass_context
def recovery_candidate_ls(ctx, status):
    s = _session(ctx)
    rows = s.recovery_candidate_registry.list(status=status)
    _print_table(
        [{"id": str(r.id)[:8] + "…",
          "name": r.name[:32],
          "primitive": r.primitive,
          "status": r.status,
          "support": r.support,
          "lift": round(float(r.lift or 0.0), 3)}
         for r in rows],
        ["id", "name", "primitive", "status", "support", "lift"],
    )


@recovery_candidate.command("approve")
@click.argument("candidate_id")
@click.pass_context
def recovery_candidate_approve(ctx, candidate_id):
    """Approve a candidate and commit it to recovery_ladder.json."""
    from uuid import UUID
    from datetime import datetime, timezone
    from browsermind_core.runtime.recovery_registry import RecoveryStrategy
    s = _session(ctx)
    cand = s.recovery_candidate_registry.get(UUID(candidate_id))
    if cand is None:
        return _err(f"No recovery candidate {candidate_id}")
    if cand.status not in ("pending", "shadow", "ready"):
        return _err(f"Candidate is {cand.status}, must be pending/shadow/ready")
    # Snapshot ladder for rollback.
    snapshot = s.recovery_registry.snapshot()
    # Build a RecoveryStrategy and append.
    strat = RecoveryStrategy(
        name=cand.name,
        predicate=dict(cand.predicate or {}),
        primitive=cand.primitive,
        depth=5,                 # mined strategies sit at depth 5 (after R1-R5)
        source="mined",
        candidate_id=str(cand.id),
    )
    s.recovery_registry.append(strat)
    s.recovery_candidate_registry.update_status(
        cand.id, "committed",
        committed_at=datetime.now(timezone.utc),
        previous_state=snapshot,
    )
    _ok(f"Committed candidate {str(cand.id)[:8]}… as mined strategy '{cand.name}'")


@recovery_candidate.command("reject")
@click.argument("candidate_id")
@click.pass_context
def recovery_candidate_reject(ctx, candidate_id):
    from uuid import UUID
    s = _session(ctx)
    try:
        s.recovery_candidate_registry.update_status(UUID(candidate_id), "rejected")
    except KeyError:
        return _err(f"No recovery candidate {candidate_id}")
    _ok(f"Rejected candidate {candidate_id[:8]}…")


@recovery_candidate.command("rollback")
@click.argument("candidate_id")
@click.pass_context
def recovery_candidate_rollback(ctx, candidate_id):
    """Restore recovery_ladder.json from candidate.previous_state."""
    from uuid import UUID
    s = _session(ctx)
    cand = s.recovery_candidate_registry.get(UUID(candidate_id))
    if cand is None:
        return _err(f"No recovery candidate {candidate_id}")
    if cand.status != "committed":
        return _err(f"Only committed candidates can be rolled back; status={cand.status}")
    if not cand.previous_state:
        return _err("No previous_state snapshot available")
    s.recovery_registry.replace(cand.previous_state)
    s.recovery_candidate_registry.update_status(cand.id, "rolled_back")
    _ok(f"Rolled back candidate {str(cand.id)[:8]}…")


# -----------------------------------------------------------------------------
# bm recovery mine / sweep / monitor — the three taps that make the loop run
# -----------------------------------------------------------------------------


@recovery.command("mine")
@click.option("--failure-class", default="TARGET_CHANGED", show_default=True,
              help="Failure category to mine patterns from")
@click.option("--min-support", default=20, show_default=True, type=int)
@click.option("--min-lift", default=2.0, show_default=True, type=float)
@click.option("--max-conjunction-size", default=3, show_default=True, type=int)
@click.option("--dry-run", is_flag=True,
              help="Print discovered patterns without persisting candidates")
@click.pass_context
def recovery_mine(ctx, failure_class, min_support, min_lift,
                  max_conjunction_size, dry_run):
    """Mine recurring failure patterns from OutcomeLedger and emit RecoveryCandidates."""
    from browsermind_core.training.failure_pattern_miner import (
        mine_patterns, to_recovery_candidate,
    )
    from browsermind_core.runtime.primitive_library import get_primitive

    s = _session(ctx)
    records = list(s.outcome_ledger.records)
    if not records:
        return _err("OutcomeLedger has no records yet — run a few replays first.")

    patterns = mine_patterns(
        records,
        failure_class=failure_class,
        min_support=min_support,
        min_lift=min_lift,
        max_conjunction_size=max_conjunction_size,
    )

    if not patterns:
        click.echo(click.style(
            f"  (no patterns met support>={min_support} lift>={min_lift})",
            dim=True,
        ))
        return

    # Dedup against existing candidates: same (predicate, primitive) signature.
    existing = s.recovery_candidate_registry.list()
    existing_sigs = {
        (json.dumps(c.predicate, sort_keys=True), c.primitive)
        for c in existing
    }

    rows = []
    saved = 0
    skipped_dup = 0
    skipped_invalid = 0
    for p in patterns:
        sig = (json.dumps(p.predicate, sort_keys=True), p.suggested_primitive)
        is_dup = sig in existing_sigs
        is_invalid = get_primitive(p.suggested_primitive) is None
        rows.append({
            "predicate": json.dumps(p.predicate, sort_keys=True)[:48],
            "primitive": p.suggested_primitive,
            "support": p.support,
            "lift": round(p.lift, 2),
            "status": ("DUP" if is_dup else
                       "INVALID" if is_invalid else
                       ("DRY" if dry_run else "SAVED")),
        })
        if dry_run or is_dup or is_invalid:
            skipped_dup += int(is_dup)
            skipped_invalid += int(is_invalid)
            continue
        cand = to_recovery_candidate(p)
        s.recovery_candidate_registry.save(cand)
        existing_sigs.add(sig)
        saved += 1

    _print_table(rows, ["predicate", "primitive", "support", "lift", "status"])
    if dry_run:
        click.echo(click.style(
            f"  [dry-run] {len(patterns)} pattern(s) discovered; nothing persisted.",
            dim=True,
        ))
    else:
        click.echo(click.style(
            f"  Saved {saved} new candidate(s); skipped {skipped_dup} dup(s), "
            f"{skipped_invalid} invalid primitive(s).",
            dim=True,
        ))


@recovery.command("sweep")
@click.option("--shadow-min-samples", default=30, show_default=True, type=int)
@click.option("--min-lift", default=0.10, show_default=True, type=float)
@click.pass_context
def recovery_sweep(ctx, shadow_min_samples, min_lift):
    """Run the promotion gate: pending → shadow → ready based on shadow_results.jsonl."""
    from browsermind_core.runtime.recovery_promotion_gate import refresh_registry
    from browsermind_core.runtime.shadow_validator import ShadowValidator

    s = _session(ctx)
    validator = ShadowValidator(s.store_dir)
    results = refresh_registry(
        s.recovery_candidate_registry,
        validator=validator,
        shadow_min_samples=shadow_min_samples,
        min_lift=min_lift,
    )
    if not results:
        click.echo(click.style("  (no pending/shadow candidates)", dim=True))
        return

    rows = []
    promoted = 0
    for c, allow, reason in results:
        # Re-fetch to see the post-sweep status (refresh_registry mutates).
        fresh = s.recovery_candidate_registry.get(c.id)
        if fresh is not None and fresh.status == "ready" and c.status != "ready":
            promoted += 1
        rows.append({
            "id": str(c.id)[:8] + "…",
            "name": c.name[:32],
            "before": c.status,
            "after": (fresh.status if fresh else c.status),
            "reason": reason[:48],
        })
    _print_table(rows, ["id", "name", "before", "after", "reason"])
    click.echo(click.style(
        f"  Promoted {promoted} candidate(s) to 'ready'.", dim=True,
    ))


@recovery.command("monitor")
@click.option("--min-samples", default=20, show_default=True, type=int)
@click.option("--neg-lift", default=0.10, show_default=True, type=float,
              help="Quarantine when lift <= -abs(neg_lift)")
@click.pass_context
def recovery_monitor(ctx, min_samples, neg_lift):
    """Post-commit measurement: quarantine mined strategies whose real-traffic lift
    has gone negative."""
    from browsermind_core.runtime.recovery_post_commit_monitor import sweep

    s = _session(ctx)
    records = list(s.outcome_ledger.records)
    results = sweep(
        records,
        s.recovery_candidate_registry,
        s.recovery_registry,
        min_samples=min_samples,
        neg_lift_threshold=neg_lift,
    )
    if not results:
        click.echo(click.style("  (no committed candidates to monitor)", dim=True))
        return

    rows = []
    flagged_count = 0
    for cand, metrics, flagged in results:
        flagged_count += int(flagged)
        rows.append({
            "id": str(cand.id)[:8] + "…",
            "name": cand.name[:24],
            "n": metrics.get("n_after_commit", 0),
            "mined": metrics.get("mined_success_rate"),
            "baseline": metrics.get("baseline_success_rate"),
            "lift": metrics.get("lift"),
            "action": "QUARANTINED" if flagged else "ok",
        })
    _print_table(rows, ["id", "name", "n", "mined", "baseline", "lift", "action"])
    click.echo(click.style(
        f"  Quarantined {flagged_count} candidate(s); {len(results) - flagged_count} healthy.",
        dim=True,
    ))


@workflow.group("instance")
def workflow_instance():
    """Persona-bound workflow instances"""


@workflow_instance.command("create")
@click.argument("name")
@click.option("--persona", "persona_name", required=True)
@click.option("--template", "template_name", required=True)
@click.option("--family", "family_key", default="")
@click.option("--origin", default="", help="Environment instance origin URL")
@click.pass_context
def workflow_instance_create(ctx, name, persona_name, template_name, family_key, origin):
    """Create a WorkflowInstance bound to a template."""
    from uuid import UUID

    s = _session(ctx)
    pe = s._lookup("persona", persona_name)
    if not pe:
        _err(f"Persona '{persona_name}' not found.")
    te = s.workflow_store.lookup_template(template_name)
    if not te:
        _err(f"Template '{template_name}' not found.")
    profile = ""
    if family_key:
        from pathlib import Path
        from browsermind_core.runtime.environment_config import get_instance

        try:
            profile = str(get_instance(family_key).profile_dir(s.store_dir, persona_name=persona_name))
        except KeyError:
            safe_persona = persona_name.lower().replace(" ", "_")
            profile = str(Path(s.store_dir) / "profiles" / safe_persona / family_key)
    inst = s.workflow_store.create_instance(
        name=name,
        persona_id=UUID(pe["id"]),
        template_id=UUID(te["id"]),
        environment_family=family_key,
        environment_instance=origin,
        profile_path=profile,
    )
    s.event_bus.emit(
        "EntityMutated",
        {
            "entity_type": "WorkflowInstance",
            "entity_id": inst.id,
            "new_value": inst.model_dump(mode="json"),
            "actor": "cli",
        },
    )
    _ok(f"WorkflowInstance '{name}'  [{str(inst.id)[:8]}…]")


@workflow_instance.command("ls")
@click.pass_context
def workflow_instance_ls(ctx):
    """List WorkflowInstances."""
    s = _session(ctx)
    rows = s.workflow_store.list_instances()
    _print_table(
        [
            {
                "name": r["name"],
                "family": r.get("family_key", ""),
                "template": r.get("template_id", "")[:8] + "…",
                "id": r["id"][:8] + "…",
            }
            for r in rows
        ],
        ["name", "family", "template", "id"],
    )


# =============================================================================
# bm system — honesty surface
# =============================================================================


@cli.group()
def system():
    """Inspect what the learning loop has actually observed (vs. what it could)."""


@system.command("status")
@click.option("--json", "as_json", is_flag=True, help="Emit raw JSON instead of formatted text")
@click.pass_context
def system_status(ctx, as_json):
    """One-glance answer to 'is anything actually learning yet?'

    Distinguishes architectural readiness (plumbing, tests) from observed
    behavior (real replays, real candidates, real auto-commits, real
    quarantines). The bottom-line tag is either:

      LEARNING ACTUALIZED         — at least one mined strategy committed
                                    on real-traffic evidence
      PLUMBED BUT DRY             — every component imports and tests pass,
                                    but no real-traffic loop has closed
    """
    from browsermind_core.training.system_status import (
        compute_status, render_status_lines,
    )
    s = _session(ctx)
    status = compute_status(s)
    if as_json:
        click.echo(json.dumps(status, indent=2, default=str))
        return
    for line in render_status_lines(status):
        click.echo(line)


# =============================================================================
# bm execution
# =============================================================================

@cli.group()
def execution():
    """Manage Executions (start, pause, resume, inspect, replay)"""


@execution.command("start")
@click.option("--task", "task_name", required=True)
@click.option("--persona", "persona_name", required=True)
@click.option("--policy", default="auto",
              type=click.Choice(["auto", "ask", "never"]), show_default=True)
@click.pass_context
def execution_start(ctx, task_name, persona_name, policy):
    """Start an Execution for a Task."""
    s = _session(ctx)
    task_entry = s._lookup("task", task_name)
    if not task_entry:
        _err(f"Task '{task_name}' not found.")
    persona_entry = s._lookup("persona", persona_name)
    if not persona_entry:
        _err(f"Persona '{persona_name}' not found.")
    from uuid import UUID
    persona_id = UUID(persona_entry["id"])
    insts = s.workflow_store.list_instances()
    tpls = s.workflow_store.list_templates()
    workflow_instance_id = UUID(insts[0]["id"]) if insts else uuid4()
    template_id = UUID(tpls[0]["id"]) if tpls else uuid4()
    s.policy_engine.set_policy(persona_id, template_id, policy)
    exc = s.execution_engine.start_execution(
        task_id=UUID(task_entry["id"]),
        workflow_instance_id=workflow_instance_id,
        target_template_id=template_id,
        persona_id=persona_id,
    )
    s._register("execution", str(exc.id)[:8], str(exc.id),
                {"task": task_name, "persona": persona_name, "status": exc.status})
    _ok(f"Execution started  [{str(exc.id)[:8]}…]  status={exc.status}  policy={exc.approval_level}")


@execution.command("pause")
@click.argument("exec_id")
@click.pass_context
def execution_pause(ctx, exec_id):
    """Pause a running Execution (checkpoints state)."""
    s = _session(ctx)
    entry = s._lookup("execution", exec_id)
    if not entry:
        _err(f"Execution '{exec_id}' not found.")
    from uuid import UUID
    exc_uuid = UUID(entry["id"])
    exc = s.execution_engine.rehydrate_execution(exc_uuid)
    if not exc:
        _err("Could not rehydrate execution from store.")
    s.execution_engine.pause_execution(exc_uuid)
    _ok(f"Execution [{exec_id}…] paused and checkpointed.")


@execution.command("resume")
@click.argument("exec_id")
@click.pass_context
def execution_resume(ctx, exec_id):
    """Resume a paused Execution."""
    s = _session(ctx)
    entry = s._lookup("execution", exec_id)
    if not entry:
        _err(f"Execution '{exec_id}' not found.")
    from uuid import UUID
    exc_uuid = UUID(entry["id"])
    exc = s.execution_engine.rehydrate_execution(exc_uuid)
    if not exc:
        _err("Could not rehydrate execution from store.")
    s.execution_engine.resume_execution(exc_uuid)
    _ok(f"Execution [{exec_id}…] resumed.")


@execution.command("inspect")
@click.argument("exec_id")
@click.pass_context
def execution_inspect(ctx, exec_id):
    """Inspect all checkpoints (Snapshots) for an Execution."""
    s = _session(ctx)
    entry = s._lookup("execution", exec_id)
    if not entry:
        _err(f"Execution '{exec_id}' not found.")
    from uuid import UUID
    snaps = s.repo.load_all_snapshots(UUID(entry["id"]))
    if not snaps:
        click.echo(click.style("  No snapshots found.", dim=True))
        return
    click.echo(click.style(f"\n  Snapshots for Execution [{exec_id}…]\n", bold=True))
    rows = [
        {
            "seq": str(snap.sequence),
            "status": snap.execution_state.get("status", "?"),
            "retries": str(snap.execution_state.get("retry_count", 0)),
            "valid": "✓" if snap.is_valid else "✗",
            "id": str(snap.id)[:8] + "…",
        }
        for snap in snaps
    ]
    _print_table(rows, ["seq", "status", "retries", "valid", "id"])


@execution.command("ls")
@click.pass_context
def execution_ls(ctx):
    """List all Executions."""
    s = _session(ctx)
    idx = s._load_index("execution")
    rows = [{"id": k, "task": v.get("task",""), "persona": v.get("persona",""), "status": v.get("status","")} for k, v in idx.items()]
    _print_table(rows, ["id", "task", "persona", "status"])


# =============================================================================
# bm outcome
# =============================================================================

@cli.group()
def outcome():
    """Inspect the Outcome Ledger (did it work?)"""


@outcome.command("list")
@click.option("--execution", "exec_id", default=None, help="Filter by execution id prefix")
@click.option("--n", default=20, show_default=True)
@click.pass_context
def outcome_list(ctx, exec_id, n):
    """List recent Outcome records."""
    s = _session(ctx)
    records = s.outcome_repo.tail(n)
    if exec_id:
        from uuid import UUID
        entry = s._lookup("execution", exec_id)
        if entry:
            records = s.outcome_repo.get_by_execution(UUID(entry["id"]))
        else:
            records = [r for r in records if str(r.execution_id or "").startswith(exec_id)]
    total = s.outcome_repo.count()
    if not records:
        click.echo(click.style("  No outcome records.", dim=True))
        return
    click.echo(click.style(f"\n  Showing {len(records)} of {total} outcomes\n", bold=True))
    rows = [
        {
            "type": r.outcome_type[:24],
            "ok": "yes" if r.success else "no",
            "scope": r.scope[:10],
            "exec": str(r.execution_id or "")[:8] + "…",
            "evidence": (r.evidence or "")[:36],
        }
        for r in records
    ]
    _print_table(rows, ["type", "ok", "scope", "exec", "evidence"])


# =============================================================================
# bm ledger
# =============================================================================

@cli.group()
def ledger():
    """Inspect the Mutation Ledger"""


@ledger.command("tail")
@click.option("--n", default=10, show_default=True, help="Number of entries to show")
@click.pass_context
def ledger_tail(ctx, n):
    """Show the last N ledger entries (persisted across sessions)."""
    s = _session(ctx)
    history = s.ledger_repo.tail(n)
    total = s.ledger_repo.count()
    if not history:
        click.echo(click.style("  Ledger is empty.", dim=True))
        return
    click.echo(click.style(f"\n  Last {len(history)} of {total} total Ledger entries\n", bold=True))
    for entry in history:
        ts = entry.timestamp.strftime("%H:%M:%S")
        old = entry.old_value.get("status", "--") if entry.old_value else "--"
        new = entry.new_value.get("status", "--")
        actor = entry.actor or "system"
        click.echo(
            f"  {click.style(ts, dim=True)}  "
            f"{click.style(entry.entity_type, fg='cyan'):<14} "
            f"{str(entry.entity_id)[:8]}...  "
            f"{click.style(old, fg='yellow')} -> {click.style(new, fg='green')}  "
            f"[{actor}]"
        )

# =============================================================================
# bm replay (P3A)
# =============================================================================

@cli.group()
def replay():
    """P3A — Replay a compiled WorkflowTemplate using strict semantics"""


@replay.command("start")
@click.argument("template_name")
@click.option("--env", "env_key", default="huggingface", show_default=True)
@click.option("--persona", "persona_name", default="validator", show_default=True)
@click.option("--url", default=None, help="Override start URL")
@click.option("--headless", is_flag=True)
@click.option("--skip-failures", is_flag=True,
              help="Log unresolvable steps and continue instead of aborting at the first failure.")
@click.pass_context
def replay_start(ctx, template_name, env_key, persona_name, url, headless, skip_failures):
    """Replay a WorkflowTemplate deterministically."""
    import asyncio
    import json
    from uuid import uuid4
    from pathlib import Path
    from browsermind_core.runtime.environment_registry import resolve
    from browsermind_core.runtime.auth_session import AuthSession
    from browsermind_core.ontology.p1_schemas import WorkflowInstance
    from browsermind_core.runtime.replay_engine import ReplayEngine

    s = _session(ctx)
    te = s.workflow_store.lookup_template(template_name)
    if not te:
        _err(f"Template '{template_name}' not found.")
    print(f"  [replay] resolved '{template_name}' -> template_id={te['id']}")
        
    template = s.workflow_store.get_template(te["id"])
    
    entry = resolve(env_key)
    if not entry:
        _err(f"Environment '{env_key}' not found.")
    if url:
        entry.start_url = url
    
    # Create a dummy WorkflowInstance for P3A
    pe = s._lookup("persona", persona_name)
    if not pe:
        _err(
            f"Persona '{persona_name}' not found. "
            f"Create it first with: bm persona create {persona_name} --principal <principal-name>"
        )
        return
    from uuid import UUID as _UUID
    replay_persona_id = _UUID(pe["id"])

    instance = WorkflowInstance(
        persona_id=replay_persona_id,
        template_id=template.id,
        bound_resources={},
        bound_identities={}
    )
    
    session = AuthSession(
        entry=entry,
        persona_name=persona_name,
        store_dir=Path(s.store_dir),
        headless=headless
    )
    
    engine = ReplayEngine(
        session,
        outcome_ledger=s.outcome_ledger,
        lesson_reader=getattr(s, "lesson_reader", None),
        behavior_audit=getattr(s, "behavior_audit", None),
        recovery_registry=getattr(s, "recovery_registry", None),
        recovery_candidate_registry=getattr(s, "recovery_candidate_registry", None),
        auto_pilot=getattr(s, "auto_pilot", None),
        persona_id=replay_persona_id,
        environment_family=entry.family,
        environment_instance=entry.key,
        execution_engine=s.execution_engine,
        state_classifier=getattr(s, "state_classifier", None),
        sstg=getattr(s, "sstg", None),
        task_id=s.task_manager.create_task(
            persona_id=replay_persona_id,
            goal=f"replay:{template_name}",
        ).id,
        skip_failures=skip_failures,
    )
    report = asyncio.run(engine.replay(entry, template, instance))
    
    print("\n" + "="*50)
    print("REPLAY REPORT")
    print("="*50)
    print(json.dumps(report.model_dump(mode="json"), indent=2))
    print("="*50)
    
    if report.failed_steps == 0 and report.resolved_steps == report.total_steps:
        _ok(f"Replay Successful! Resolution Rate: {report.resolution_rate * 100:.1f}%")
    else:
        _err(f"Replay Failed. Reason: {report.failure_reason}")


# =============================================================================
# bm explore — run ExplorationHarness on a registered site
# =============================================================================

@cli.command("explore")
@click.option("--site", "site_key", required=True, help="Site key from the site registry (e.g. github, saucedemo).")
@click.option("--budget", default=50, show_default=True, type=int, help="Max exploration steps.")
@click.option("--headless", is_flag=True, help="Run browser headless.")
@click.option("--persona", "persona_name", default="validator", show_default=True)
@click.option("--env", "env_key", default=None, help="Override environment key (defaults to site_key).")
@click.pass_context
def explore(ctx, site_key, budget, headless, persona_name, env_key):
    """Discover capability hypotheses by exploring a site with ExplorationHarness."""
    import asyncio
    import json
    from pathlib import Path
    from browsermind_core.exploration.exploration_spec import ExplorationSpec
    from browsermind_core.exploration.exploration_harness import ExplorationHarness
    from browsermind_core.runtime.environment_registry import resolve
    from browsermind_core.runtime.auth_session import AuthSession
    from browsermind_core.runtime.replay_engine import ReplayEngine
    from browsermind_core.representation.fallback_ledger import FallbackLedger

    s = _session(ctx)

    resolved_env = env_key or site_key
    entry = resolve(resolved_env)
    if not entry:
        _err(
            f"Environment '{resolved_env}' not found. "
            f"Register it with: bm environment create {resolved_env}"
        )

    from uuid import UUID as _UUID
    pe = s._lookup("persona", persona_name)
    if not pe:
        all_personas = s.persona_manager.list_personas()
        if not all_personas:
            _err("No personas found. Create one with: bm persona create <name> --principal <principal>")
        fallback = all_personas[0]
        click.echo(f"  [explore] persona '{persona_name}' not found — using '{fallback.name}' ({fallback.id})")
        persona_id = fallback.id if isinstance(fallback.id, _UUID) else _UUID(str(fallback.id))
        persona_name = fallback.name
    else:
        persona_id = _UUID(pe["id"])

    # Wire FallbackLedger so every unrecognised interaction is recorded
    ledger = FallbackLedger()
    ledger_logger = ledger.as_logger(site_key=site_key)

    async def engine_factory(_site_key: str) -> ReplayEngine:
        session = AuthSession(
            entry=entry,
            persona_name=persona_name,
            store_dir=Path(s.store_dir),
            headless=headless,
        )
        return ReplayEngine(
            session,
            outcome_ledger=s.outcome_ledger,
            lesson_reader=getattr(s, "lesson_reader", None),
            behavior_audit=getattr(s, "behavior_audit", None),
            recovery_registry=getattr(s, "recovery_registry", None),
            recovery_candidate_registry=getattr(s, "recovery_candidate_registry", None),
            auto_pilot=getattr(s, "auto_pilot", None),
            persona_id=persona_id,
            environment_family=entry.family,
            environment_instance=entry.key,
            execution_engine=s.execution_engine,
            exploration_mode=True,
            state_classifier=getattr(s, "state_classifier", None),
            sstg=getattr(s, "sstg", None),
            task_id=s.task_manager.create_task(
                persona_id=persona_id,
                goal=f"explore:{site_key}",
            ).id,
        )

    harness = ExplorationHarness(
        hypothesis_store=getattr(s, "hypothesis_store", None),
        normalizer_logger=ledger_logger,
        on_result=lambda r: click.echo(
            f"  [explore] {r.status}  steps={r.steps_executed}"
            f"  experiences={len(r.experiences_discovered)}"
            f"  hypotheses={len(r.hypothesis_hashes)}"
        ),
    )

    spec = ExplorationSpec(site_key=site_key, budget=budget, label=f"cli_explore_{site_key}")

    click.echo(f"\n  Exploring '{site_key}' (budget={budget}, headless={headless}) ...")
    click.echo(f"  FallbackLedger: {ledger._path}")
    click.echo()

    from datetime import datetime, timezone
    started_at = datetime.now(timezone.utc).isoformat()
    result = asyncio.run(harness.run(spec, engine_factory))

    # Persist result for the sidecar /api/explore/runs endpoint
    runs_dir = Path.home() / ".browsermind" / "explore_runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"{site_key}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    run_record = {
        "site_key":               site_key,
        "budget":                 budget,
        "status":                 result.status,
        "steps_executed":         result.steps_executed,
        "experiences_discovered": result.experiences_discovered,
        "hypothesis_hashes":      result.hypothesis_hashes,
        "duration_seconds":       result.duration_seconds,
        "error":                  result.error,
        "started_at":             started_at,
    }
    (runs_dir / f"{run_id}.json").write_text(
        json.dumps(run_record, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    click.echo()
    click.echo("=" * 50)
    click.echo("EXPLORATION RESULT")
    click.echo("=" * 50)
    click.echo(f"  Status      : {result.status}")
    click.echo(f"  Steps       : {result.steps_executed}")
    click.echo(f"  Duration    : {result.duration_seconds:.1f}s")
    if result.experiences_discovered:
        click.echo(f"  Experiences : {', '.join(result.experiences_discovered)}")
    if result.hypothesis_hashes:
        click.echo(f"  Hypotheses  : {len(result.hypothesis_hashes)} new")
    if result.error:
        click.echo(f"  Error       : {result.error}")

    ledger_stats = ledger.stats()
    click.echo(f"\n  FallbackLedger: {ledger_stats['unique_fragments']} unique fragments,"
               f" {ledger_stats['total_observations']} observations")
    click.echo(f"  Run 'python scripts/vocab_review.py' to cluster and propose new vocab.\n")

    if result.error:
        _err(f"Exploration failed: {result.error}")
    _ok(f"Exploration complete: {result.status}")


# =============================================================================
# bm environment (P2A)
# =============================================================================

from browsermind_core.console.environment_commands import environment_group
cli.add_command(environment_group, name="environment")

# =============================================================================
# bm mission — autonomous exploration mission runtime
# =============================================================================

from browsermind_core.console.mission_commands import mission_group
cli.add_command(mission_group, name="mission")

from browsermind_core.console.session_commands import session_group
cli.add_command(session_group, name="session")


# =============================================================================
# bm dataset — extract OutcomeLedger episodes for BC training
# =============================================================================

@cli.group()
def dataset():
    """Export and inspect training datasets derived from the OutcomeLedger."""


@dataset.command("export")
@click.option("--output", default="training/dataset_v1.jsonl", show_default=True,
              help="Destination JSONL path.")
@click.option("--success-only/--all", default=True,
              help="Keep only successful step attempts (default).")
@click.option("--site", "sites", multiple=True,
              help="Filter by environment_instance. Repeatable.")
@click.option("--min-steps", default=0, show_default=True, type=int,
              help="Drop episodes whose execution has fewer than this many step rows.")
@click.pass_context
def dataset_export(ctx, output, success_only, sites, min_steps):
    """Flatten OutcomeLedger step records into a BC-ready JSONL dataset."""
    from browsermind_core.training.episode_extractor import (
        extract_bc_episodes, write_jsonl, summarize,
    )
    s = _session(ctx)
    episodes = extract_bc_episodes(
        s.outcome_ledger,
        success_only=success_only,
        sites=sites or None,
        min_steps=min_steps,
    )
    if not episodes:
        _err("No episodes found in OutcomeLedger. Run replays first.")
        return
    path = write_jsonl(episodes, output)
    summary = summarize(episodes)
    _ok(f"Wrote {summary['total']} episodes -> {path}")
    click.echo(json.dumps(summary, indent=2))


@dataset.command("summary")
@click.option("--success-only/--all", default=True)
@click.pass_context
def dataset_summary(ctx, success_only):
    """Print a histogram of OutcomeLedger episodes without writing a file."""
    from browsermind_core.training.episode_extractor import (
        extract_bc_episodes, summarize,
    )
    s = _session(ctx)
    episodes = extract_bc_episodes(s.outcome_ledger, success_only=success_only)
    click.echo(json.dumps(summarize(episodes), indent=2))


@dataset.command("status")
@click.pass_context
def dataset_status(ctx):
    """Show OutcomeLedger episode count + readiness banding for BC."""
    from browsermind_core.training.episode_extractor import extract_bc_episodes
    s = _session(ctx)
    all_eps = extract_bc_episodes(s.outcome_ledger, success_only=False)
    ok_eps = extract_bc_episodes(s.outcome_ledger, success_only=True)
    click.echo(f"Total step records   : {len(all_eps)}")
    click.echo(f"Successful (BC-ready): {len(ok_eps)}")
    click.echo(f"Production target    : 500+")
    if len(ok_eps) >= 500:
        click.echo("[READY] Sufficient data for BC training.")
    elif len(ok_eps) >= 50:
        click.echo(f"[PARTIAL] {500 - len(ok_eps)} more successful episodes for full training; can smoke-test now.")
    else:
        click.echo(f"[NOT READY] Need {max(0, 50 - len(ok_eps))} more successful episodes minimum.")


# =============================================================================
# bm benchmark — frozen evaluation suite
# =============================================================================

@cli.group()
def benchmark():
    """Run the frozen benchmark suite and compare runs."""


@benchmark.command("run")
@click.option("--runs", default=5, show_default=True, type=int)
@click.option("--headless", is_flag=True)
@click.option("--compare", default=None, help="Path to a prior benchmark JSON for diff.")
@click.pass_context
def benchmark_run(ctx, runs, headless, compare):
    """Execute the benchmark suite and write reports/benchmark/<timestamp>.json."""
    import subprocess, sys
    from pathlib import Path
    args = [sys.executable, str(Path("run_benchmark.py")),
            "--runs", str(runs)]
    if headless:
        args.append("--headless")
    if compare:
        args += ["--compare", compare]
    rc = subprocess.call(args)
    if rc != 0:
        _err(f"benchmark exited with code {rc}")


@benchmark.command("compare")
@click.argument("report_a")
@click.argument("report_b")
def benchmark_compare(report_a, report_b):
    """Compare two benchmark reports and print the delta."""
    from pathlib import Path
    a = json.loads(Path(report_a).read_text(encoding="utf-8"))
    b = json.loads(Path(report_b).read_text(encoding="utf-8"))
    a_rate = a.get("aggregate_success_rate", 0.0)
    b_rate = b.get("aggregate_success_rate", 0.0)
    delta = b_rate - a_rate
    verdict = "IMPROVED" if delta > 0 else "REGRESSED" if delta < 0 else "UNCHANGED"
    click.echo(f"A ({a.get('timestamp','?')}): {a_rate:.1%}")
    click.echo(f"B ({b.get('timestamp','?')}): {b_rate:.1%}")
    click.echo(f"Delta: {delta:+.1%}  [{verdict}]")


# =============================================================================
# bm self-train — closed-loop retraining
# =============================================================================

@cli.command("self-train")
@click.option("--min-episodes", default=100, show_default=True, type=int)
@click.option("--epochs", default=30, show_default=True, type=int)
@click.option("--output", default="bc_v2_checkpoint.pt", show_default=True)
@click.option("--dataset", default="training/dataset_autotrain.jsonl", show_default=True)
@click.option("--benchmark/--no-benchmark", "benchmark_after", default=True,
              help="Run the benchmark suite after training (default).")
@click.option("--benchmark-runs", default=3, show_default=True, type=int)
@click.option("--regression-threshold", default=0.05, show_default=True, type=float,
              help="Reject the candidate if new score drops more than this fraction.")
@click.option("--headless", is_flag=True)
@click.pass_context
def self_train(ctx, min_episodes, epochs, output, dataset,
               benchmark_after, benchmark_runs, regression_threshold, headless):
    """Extract -> train -> benchmark -> deploy. Rejects regressions on the way in."""
    import subprocess, sys, shutil
    from pathlib import Path
    from browsermind_core.training.episode_extractor import (
        extract_bc_episodes, write_jsonl, summarize,
    )

    s = _session(ctx)

    click.echo("[1/5] Counting episodes...")
    episodes = extract_bc_episodes(s.outcome_ledger, success_only=True, exclude_pre_stage1=True)
    click.echo(f"      {len(episodes)} successful episodes")
    if len(episodes) < min_episodes:
        _err(
            f"Only {len(episodes)} successful episodes available, "
            f"need >= {min_episodes}. Tip: --min-episodes {max(10, len(episodes))}."
        )
        return

    click.echo("[2/5] Exporting...")
    Path(dataset).parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(episodes, dataset)
    sm = summarize(episodes)
    click.echo(f"      {sm['total']} eps, {sm['sites_count']} sites, "
               f"{sm['templates_count']} templates")

    click.echo(f"[3/5] Training (epochs={epochs}) ...")
    candidate = output.replace(".pt", "_candidate.pt")
    rc = subprocess.call(
        [sys.executable, "train_bc_v2.py",
         "--data", dataset, "--epochs", str(epochs), "--output", candidate]
    )
    if rc != 0 or not Path(candidate).exists():
        _err(f"train_bc_v2 exited with code {rc} or produced no checkpoint")
        return

    if not benchmark_after:
        shutil.copy2(candidate, output)
        Path(candidate).unlink(missing_ok=True)
        _ok(f"self-train complete (benchmark skipped). Checkpoint: {output}")
        return

    bench_dir = Path("reports/benchmark")
    old_score = 0.0
    if bench_dir.exists():
        priors = sorted(bench_dir.glob("benchmark_*.json"), reverse=True)
        if priors:
            try:
                old_score = json.loads(priors[0].read_text(encoding="utf-8")).get(
                    "aggregate_success_rate", 0.0
                )
            except Exception:
                old_score = 0.0

    click.echo(f"[4/5] Benchmarking candidate (runs={benchmark_runs}) ...")
    bench_cmd = [sys.executable, "run_benchmark.py", "--runs", str(benchmark_runs)]
    if headless:
        bench_cmd.append("--headless")
    subprocess.call(bench_cmd)

    new_score = 0.0
    if bench_dir.exists():
        priors = sorted(bench_dir.glob("benchmark_*.json"), reverse=True)
        if priors:
            try:
                new_score = json.loads(priors[0].read_text(encoding="utf-8")).get(
                    "aggregate_success_rate", 0.0
                )
            except Exception:
                new_score = 0.0

    delta = new_score - old_score
    click.echo(f"[5/5] old={old_score:.1%}  new={new_score:.1%}  delta={delta:+.1%}")

    if old_score > 0 and new_score < old_score - regression_threshold:
        _err(
            f"REJECT: regression {-delta:.1%} > threshold {regression_threshold:.1%}. "
            f"Keeping prior {output}; candidate left at {candidate}."
        )
        return

    shutil.copy2(candidate, output)
    Path(candidate).unlink(missing_ok=True)
    _ok(f"DEPLOY: checkpoint updated to {output}  (score {new_score:.1%})")


# =============================================================================
# bm vault — Fernet-backed persona credential store
# =============================================================================

@cli.group()
def vault():
    """Manage encrypted secrets and resources per persona."""


@vault.command("set")
@click.option("--persona", required=True, help="Persona name (must exist).")
@click.option("--env", "env_key", required=True, help="Environment key, e.g. greenhouse.")
@click.option("--key", required=True, help="Secret name, e.g. password / email.")
@click.option("--value", required=True, help="Plaintext value; stored Fernet-encrypted.")
@click.pass_context
def vault_set(ctx, persona, env_key, key, value):
    """Encrypt and store a secret for (persona, env, key)."""
    from browsermind_core.runtime.vault_writer import VaultWriter
    s = _session(ctx)
    pe = s._lookup("persona", persona)
    if not pe:
        _err(f"Persona '{persona}' not found. Create it with: bm persona create {persona} --principal <name>")
        return
    VaultWriter(s.store_dir, persona).set_secret(env_key, key, value)
    _ok(f"Stored secret '{key}' for persona '{persona}' / env '{env_key}'")


@vault.command("get")
@click.option("--persona", required=True)
@click.option("--env", "env_key", required=True)
@click.option("--key", required=True)
@click.pass_context
def vault_get(ctx, persona, env_key, key):
    """Decrypt and print a secret. Prints (none) if missing."""
    from browsermind_core.runtime.vault_writer import VaultWriter
    s = _session(ctx)
    pe = s._lookup("persona", persona)
    if not pe:
        _err(f"Persona '{persona}' not found.")
        return
    data = VaultWriter(s.store_dir, persona).load()
    val = ((data.get("secrets") or {}).get(env_key) or {}).get(key)
    click.echo(val if val is not None else "(none)")


@vault.command("list")
@click.option("--persona", required=True)
@click.pass_context
def vault_list(ctx, persona):
    """Print every stored (env, key) pair for a persona. Values redacted."""
    from browsermind_core.runtime.vault_writer import VaultWriter
    s = _session(ctx)
    pe = s._lookup("persona", persona)
    if not pe:
        _err(f"Persona '{persona}' not found.")
        return
    data = VaultWriter(s.store_dir, persona).load()
    secrets = data.get("secrets") or {}
    resources = data.get("resources") or {}
    if not secrets and not resources:
        click.echo("(empty vault)")
        return
    if secrets:
        click.echo("Secrets:")
        for env, keys in secrets.items():
            for k in keys:
                click.echo(f"  {env:<24} {k}")
    if resources:
        click.echo("Resources:")
        for env, keys in resources.items():
            for k, v in keys.items():
                click.echo(f"  {env:<24} {k:<16} {v}")


@vault.command("set-resource")
@click.option("--persona", required=True)
@click.option("--env", "env_key", required=True)
@click.option("--key", required=True, help="Resource name, e.g. resume.")
@click.option("--value", required=True, help="Path or URL; stored in plaintext.")
@click.pass_context
def vault_set_resource(ctx, persona, env_key, key, value):
    """Store a non-secret resource (file path, URL, structured value)."""
    from browsermind_core.runtime.vault_writer import VaultWriter
    s = _session(ctx)
    pe = s._lookup("persona", persona)
    if not pe:
        _err(f"Persona '{persona}' not found.")
        return
    VaultWriter(s.store_dir, persona).set_resource(env_key, key, value)
    _ok(f"Stored resource '{key}' for persona '{persona}' / env '{env_key}'")


# =============================================================================
# bm status — readiness dashboard
# =============================================================================

@cli.command("status")
@click.pass_context
def bm_status(ctx):
    """Print system readiness across personas, templates, episodes, model, benchmark."""
    from pathlib import Path
    from browsermind_core.training.episode_extractor import extract_bc_episodes

    s = _session(ctx)

    click.echo("=" * 60)
    click.echo("  BrowserMind System Status")
    click.echo("=" * 60)

    # Personas
    personas_idx = s._load_index("persona")
    p_count = len(personas_idx)
    p_tag = "PASS" if p_count else "FAIL"
    click.echo(f"\n[{p_tag}] Personas: {p_count} configured")
    for name in list(personas_idx.keys())[:3]:
        click.echo(f"       {name}  ({personas_idx[name].get('id','?')[:8]}…)")

    # Templates
    try:
        templates = s.workflow_store.list_templates()
        t_count = len(templates)
    except Exception:
        t_count = 0
    t_tag = "PASS" if t_count >= 6 else "WARN" if t_count >= 1 else "FAIL"
    click.echo(f"\n[{t_tag}] Templates: {t_count} compiled (target: 6+)")

    # Episodes
    try:
        all_eps = extract_bc_episodes(s.outcome_ledger, success_only=False)
        ok_eps = extract_bc_episodes(s.outcome_ledger, success_only=True)
        ev_verified = [e for e in ok_eps if e.get("effect_verified") is True]
        ev_rate = (len(ev_verified) / len(ok_eps)) if ok_eps else 0.0
    except Exception:
        all_eps = ok_eps = ev_verified = []
        ev_rate = 0.0
    ep_tag = "PASS" if len(ok_eps) >= 500 else "WARN" if len(ok_eps) >= 50 else "FAIL"
    ev_tag = "PASS" if ev_rate >= 0.6 else "WARN"
    click.echo(f"\n[{ep_tag}] Episodes: {len(ok_eps)} successful / {len(all_eps)} total (target: 500+)")
    click.echo(f"[{ev_tag}] Evidence: {ev_rate:.0%} effect_verified=True (target: 60%+)")

    # Model
    ck = Path("bc_v2_checkpoint.pt")
    if ck.exists():
        try:
            import torch
            data = torch.load(str(ck), map_location="cpu", weights_only=False)
            acc = data.get("action_acc", 0.0)
            vl = data.get("val_loss", float("inf"))
            m_tag = "PASS" if acc >= 0.5 else "WARN"
            click.echo(f"\n[{m_tag}] Model: action_acc={acc:.3f}  val_loss={vl:.4f}")
        except Exception as e:
            click.echo(f"\n[WARN] Model checkpoint exists but cannot be loaded: {e}")
    else:
        click.echo("\n[FAIL] Model: no bc_v2_checkpoint.pt — run `bm self-train` or train_bc_v2.py")

    # Latest benchmark
    bd = Path("reports/benchmark")
    reports = sorted(bd.glob("benchmark_*.json"), reverse=True) if bd.exists() else []
    if reports:
        try:
            latest = json.loads(reports[0].read_text(encoding="utf-8"))
            agg = latest.get("aggregate_success_rate", 0.0)
            b_tag = "PASS" if agg >= 0.7 else "WARN" if agg >= 0.3 else "FAIL"
            click.echo(f"\n[{b_tag}] Benchmark: {agg:.1%} aggregate  ({reports[0].name})")
        except Exception:
            click.echo("\n[FAIL] Benchmark: cannot parse latest report")
    else:
        click.echo("\n[FAIL] Benchmark: no reports — run `bm benchmark run`")

    # BC policy layer status — does the trained model actually load?
    try:
        from browsermind_core.runtime.bc_policy import shared as _bc_shared
        bc = _bc_shared()
        if bc.ready:
            click.echo("\n[PASS] BC policy: bc_v2_checkpoint.pt loaded; closed-loop predictions logging")
        else:
            click.echo("\n[INFO] BC policy: no checkpoint yet — run `bm self-train` to close the loop")
    except Exception as exc:
        click.echo(f"\n[WARN] BC status probe failed: {exc}")

    # Field Registry — semantic identity layer (DOCS/FIELD_ONTOLOGY_SPEC.md).
    try:
        from browsermind_core.ontology.field_registry import get_registry as _get_field_reg
        _field_count = len(_get_field_reg().list_fields())
        _f_tag = "PASS" if _field_count >= 20 else "WARN" if _field_count >= 1 else "FAIL"
        click.echo(f"\n[{_f_tag}] Field Registry: {_field_count} fields (target: 20+)")
    except Exception as exc:
        click.echo(f"\n[WARN] Field Registry probe failed: {exc}")

    click.echo("\n" + "=" * 60)


# =============================================================================
# bm field — semantic Field Registry management
# =============================================================================

@cli.group("field")
def field_group():
    """Inspect and extend the semantic Field Registry."""


@field_group.command("ls")
def field_ls():
    """List every Field in the registry."""
    from browsermind_core.ontology.field_registry import get_registry
    fields = get_registry().list_fields()
    if not fields:
        click.echo("(empty registry)")
        return
    click.echo(f"{'ID':<24} {'KIND':<14} {'OPT':<11} ALIASES")
    click.echo("-" * 78)
    for f in fields:
        aliases = ", ".join(f.aliases[:3])
        if len(f.aliases) > 3:
            aliases += f", … (+{len(f.aliases) - 3})"
        click.echo(f"{f.id:<24} {f.kind.value:<14} {f.optionality.value:<11} {aliases}")


@field_group.command("show")
@click.argument("field_id")
def field_show(field_id):
    """Print one Field's full record."""
    from browsermind_core.ontology.field_registry import get_registry
    f = get_registry().get(field_id)
    if f is None:
        _err(f"Field '{field_id}' not found. Try: bm field ls")
        return
    click.echo(json.dumps(f.model_dump(mode="json"), indent=2, ensure_ascii=False))


@field_group.command("add-alias")
@click.option("--id", "field_id", required=True, help="Existing field id (e.g. country).")
@click.option("--alias", required=True, help="New alias to register.")
def field_add_alias(field_id, alias):
    """Add a new alias to an existing Field. Aliases must be globally unique."""
    from browsermind_core.ontology.field_registry import get_registry
    try:
        updated = get_registry().add_alias(field_id, alias)
    except (KeyError, ValueError) as exc:
        _err(str(exc))
        return
    _ok(f"alias '{alias}' added to '{field_id}'  (now {len(updated.aliases)} aliases)")


@field_group.command("unknown")
@click.option("--limit", default=20, show_default=True, type=int,
              help="Top N most-frequent unknown labels. 0 = all.")
def field_unknown(limit):
    """Show labels the resolver could not identify, ranked by frequency.

    These are the candidates an operator should turn into Field aliases via
    `bm field add-alias` so future replays resolve cleanly.
    """
    from collections import Counter
    from pathlib import Path
    queue = Path.home() / ".browsermind" / "unknown_fields.jsonl"
    if not queue.exists():
        click.echo("No unknown fields recorded yet.")
        return
    counts: Counter = Counter()
    contexts: dict = {}
    for raw in queue.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except Exception:
            continue
        label = row.get("target_name", "")
        if not label:
            continue
        counts[label] += 1
        contexts.setdefault(label, row.get("container_label") or "")
    if not counts:
        click.echo("No unknown labels in queue.")
        return
    items = counts.most_common(limit if limit > 0 else None)
    click.echo(f"{'COUNT':>5}  {'LABEL':<46}  CONTAINER")
    click.echo("-" * 78)
    for label, n in items:
        click.echo(f"{n:>5}  {label[:44]:<46}  {contexts.get(label, '')[:24]}")


# =============================================================================
# bm doctor  (#91, #95)
# =============================================================================

@cli.command("doctor")
@click.pass_context
def doctor(ctx):
    """Run pre-flight diagnostics: Python, Playwright, ports, store, registry."""
    from browsermind_core.console.session import DEFAULT_STORE
    from browsermind_core.console.doctor import run_doctor
    store_dir = Path(getattr(ctx.ensure_object(object), "store_dir", DEFAULT_STORE))
    sys.exit(run_doctor(store_dir))


# =============================================================================
# bm corpus  (#92, #94)
# =============================================================================

@cli.group("corpus")
def corpus_group():
    """Corpus analytics and export."""


@corpus_group.command("stats")
@click.pass_context
def corpus_stats(ctx):
    """Print corpus statistics: sites, steps, hypotheses, quality."""
    from browsermind_core.console.session import DEFAULT_STORE
    from browsermind_core.mission.corpus_stats import CorpusStats
    store_dir = Path(getattr(ctx.ensure_object(object), "store_dir", DEFAULT_STORE))
    cs = CorpusStats(store_dir)
    click.echo(cs.summary())


@corpus_group.command("export")
@click.option("--output", "-o", default="corpus.jsonl", show_default=True,
              help="Output JSONL file path.")
@click.pass_context
def corpus_export(ctx):
    """Export corpus to JSONL for training pipeline. (#75)"""
    from browsermind_core.console.session import DEFAULT_STORE
    from browsermind_core.mission.mission_queue import MissionQueue
    import json as _json
    store_dir = Path(getattr(ctx.ensure_object(object), "store_dir", DEFAULT_STORE))
    q = MissionQueue(store_dir)
    entries = q.list_entries()
    out = Path(ctx.params.get("output", "corpus.jsonl"))
    count = 0
    with open(out, "w", encoding="utf-8") as f:
        for e in entries:
            for run in (e.run_history or []):
                run["site_key"] = e.site_key
                run["persona"] = e.persona
                run["budget"] = e.budget
                f.write(_json.dumps(run, ensure_ascii=False) + "\n")
                count += 1
    click.echo(click.style("[OK] ", fg="green") + f"Exported {count} run records to {out}")


# =============================================================================
# bm site  (#95, #49, #52)
# =============================================================================

@cli.group("site")
def site_group():
    """Site registry commands."""


@site_group.command("validate")
@click.argument("site_key")
@click.option("--headless/--no-headless", default=True, show_default=True)
@click.option("--timeout", default=10, show_default=True, type=int, help="Page load timeout in seconds")
def site_validate(site_key, headless, timeout):
    """Pre-flight validation for a site: reachability, bot wall, affordances. (#95)"""
    from browsermind_core.console.doctor import validate_site
    validate_site(site_key, headless=headless, timeout=timeout)


@site_group.command("ls")
@click.option("--category", "-c", default=None, help="Filter by category")
@click.option("--max-difficulty", default=5, type=int, show_default=True)
@click.option("--limit", default=50, type=int, show_default=True)
def site_ls(category, max_difficulty, limit):
    """List sites in the registry. (#44)"""
    from browsermind_core.mission.site_registry import list_sites, SITE_CATEGORIES
    sites = list_sites(category=category, max_difficulty=max_difficulty)[:limit]

    if not sites:
        click.echo(click.style("  (no sites match filters)", dim=True))
        return

    click.echo()
    header = f"  {'KEY':<24}  {'CATEGORY':<14}  {'DIFF':<5}  {'LOGIN':<7}  DESCRIPTION"
    click.echo(click.style(header, bold=True))
    click.echo("  " + "-" * 72)
    for s in sites:
        click.echo(
            f"  {s.key:<24}  {s.category:<14}  {s.difficulty:<5}  "
            f"{'yes' if s.requires_login else 'no':<7}  "
            f"{s.description[:40]}"
        )
    click.echo()
    click.echo(f"  Showing {len(sites)} of {len(list_sites(category=category))} sites")
    if not category:
        click.echo(f"  Categories: {', '.join(SITE_CATEGORIES)}")
    click.echo()


@site_group.command("add-campaign")
@click.option("--category", "-c", "categories", multiple=True,
              help="Categories to include (repeatable). Default: all.")
@click.option("--max-difficulty", default=3, type=int, show_default=True)
@click.option("--limit", default=100, type=int, show_default=True)
@click.option("--budget", default=200, type=int, show_default=True)
@click.option("--persona", default="validator", show_default=True)
@click.pass_context
def site_add_campaign(ctx, categories, max_difficulty, limit, budget, persona):
    """Bulk-add sites from the registry for a campaign. (#49)"""
    from browsermind_core.console.session import DEFAULT_STORE
    from browsermind_core.mission.site_registry import site_keys_for_campaign
    from browsermind_core.mission.mission_queue import MissionQueue
    store_dir = Path(getattr(ctx.ensure_object(object), "store_dir", DEFAULT_STORE))

    keys = site_keys_for_campaign(
        categories=list(categories) if categories else None,
        max_difficulty=max_difficulty,
        limit=limit,
    )
    if not keys:
        click.echo(click.style("[WARN] ", fg="yellow") + "No sites match filters.")
        return

    q = MissionQueue(store_dir)
    added = q.add_bulk(keys, persona=persona, budget=budget)
    click.echo(
        click.style("[OK] ", fg="green")
        + f"Added {added}/{len(keys)} sites to mission queue"
    )


# =============================================================================
# bm goal
# =============================================================================

@cli.group()
def goal():
    """L14 Planning — goal-oriented execution (decompose + dispatch)"""


@goal.command("ls")
@click.pass_context
def goal_ls(ctx):
    """List all registered GoalSpecs."""
    s = _session(ctx)
    rows = [
        {
            "goal_id": g.goal_id,
            "description": g.description[:50],
            "target_state": g.target_state,
            "hints": ", ".join(g.capability_hints[:3]) or "(none)",
        }
        for g in s.goal_registry.all()
    ]
    _print_table(rows, ["goal_id", "description", "target_state", "hints"])


@goal.command("show")
@click.argument("goal_id")
@click.pass_context
def goal_show(ctx, goal_id):
    """Show details of a GoalSpec."""
    s = _session(ctx)
    try:
        g = s.goal_registry.require(goal_id)
    except KeyError as exc:
        _err(str(exc))
    click.echo(click.style(f"\n  GoalSpec: {g.goal_id}\n", bold=True))
    click.echo(f"  description:   {g.description}")
    click.echo(f"  target_state:  {g.target_state}")
    click.echo(f"  start_state:   {g.start_state or '(live)'}")
    click.echo(f"  site_key:      {g.site_key or '(any)'}")
    click.echo(f"  hints:         {', '.join(g.capability_hints) or '(none)'}")
    click.echo(f"  constraints:   {g.constraints or {}}")


@goal.command("decompose")
@click.argument("goal_id")
@click.option("--from-state", "start_state", default=None,
              help="Override start SSTG state (default: unauthenticated)")
@click.pass_context
def goal_decompose(ctx, goal_id, start_state):
    """Dry-run: show how GoalDecomposer would break down a goal."""
    s = _session(ctx)
    try:
        spec = s.goal_registry.require(goal_id)
    except KeyError as exc:
        _err(str(exc))

    result = s.goal_decomposer.decompose(spec, current_state=start_state)
    if not result.feasible:
        click.echo(click.style("[INFEASIBLE] ", fg="yellow") + result.reason)
        return

    click.echo(click.style(f"\n  Strategy: {result.strategy}\n", bold=True))
    for i, cap in enumerate(result.capability_sequence, 1):
        click.echo(f"  {i:2d}. {cap}")
    if result.plan:
        click.echo(f"\n  {result.plan.summary()}")
    else:
        click.echo(f"\n  Total steps: {len(result.capability_sequence)}")


@goal.command("start")
@click.argument("goal_id")
@click.option("--persona", "persona_name", required=True)
@click.option("--env", "env_key", default="", help="Site/environment key for template preference")
@click.option("--from-state", "start_state", default=None)
@click.option("--headless", is_flag=True, default=False)
@click.pass_context
def goal_start(ctx, goal_id, persona_name, env_key, start_state, headless):
    """Execute a goal end-to-end via GoalDecomposer + CapabilityDispatcher."""
    import asyncio
    from uuid import UUID

    s = _session(ctx)

    # Resolve goal spec
    try:
        spec = s.goal_registry.require(goal_id)
    except KeyError as exc:
        _err(str(exc))

    # Resolve persona
    entry = s._lookup("persona", persona_name)
    if not entry:
        _err(f"Persona '{persona_name}' not found.")

    # Override site_key and persona_id from CLI
    from dataclasses import replace
    spec = replace(
        spec,
        site_key=env_key or spec.site_key,
        persona_id=entry["id"],
    )

    # If no dispatcher is wired (no live Playwright session), dry-run decompose only
    if s.execution_coordinator._dispatcher is None:
        click.echo(
            click.style("[INFO] ", fg="cyan")
            + "No live Playwright session — running decomposition only."
        )
        result = s.goal_decomposer.decompose(spec, current_state=start_state)
        if not result.feasible:
            _err(result.reason)
        click.echo(
            click.style("[PLAN] ", fg="green")
            + result.summary()
        )
        click.echo("  To execute, launch via `bm replay run` for each capability step.")
        return

    async def _run():
        return await s.execution_coordinator.execute_goal(
            spec=spec,
            current_state=start_state,
        )

    result = asyncio.run(_run())
    if result.success:
        _ok(result.summary())
    else:
        click.echo(click.style("[FAIL] ", fg="red") + result.summary())


# Register new commands
from pathlib import Path  # noqa: E402

try:
    from browsermind_core.console.mission_commands import mission_group
    cli.add_command(mission_group, name="mission")
except Exception:
    pass

cli.add_command(corpus_group, name="corpus")
cli.add_command(site_group, name="site")


if __name__ == '__main__':
    cli()
