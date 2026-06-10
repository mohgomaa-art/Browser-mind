"""Self-Learning v1 — TemplateCandidate + CandidateRegistry + CLI tests."""
from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from click.testing import CliRunner

from browsermind_core.console import cli as cli_module
from browsermind_core.console.session import KernelSession
from browsermind_core.ontology.template_candidate import (
    CandidateRegistry,
    TemplateCandidate,
)


def _make_evidence(step_seq=0, observations=4):
    return {
        "step_seq": step_seq,
        "previous_tier": "HIGH",
        "candidate_tier": "AMBIGUOUS",
        "reason": "lesson_evidence:repeated_target_changed",
        "observations": observations,
        "requires_human_approval": True,
        "action": "click",
        "role": "button",
        "name": "Submit",
    }


def _make_candidate(parent_id, *, evidence=None, mutations=None):
    rows = [evidence or _make_evidence()]
    muts = mutations or [{
        "type": "tier_downgrade",
        "step_seq": rows[0]["step_seq"],
        "from_tier": "HIGH",
        "to_tier": "AMBIGUOUS",
        "reason": rows[0]["reason"],
    }]
    return TemplateCandidate(
        parent_id=parent_id,
        parent_version="2.0.0",
        mutations=muts,
        lesson_evidence=rows,
        previous_state={"steps": [{
            "action": "click",
            "target_role": "button",
            "target_name": "Submit",
            "target_selector": "button.submit",
            "replayability": {"tier": "HIGH"},
        }]},
    )


# --- registry round-trip -----------------------------------------------------


def test_registry_save_get_list_round_trip(tmp_path):
    reg = CandidateRegistry(str(tmp_path))
    parent_id = uuid4()
    cand = _make_candidate(parent_id)
    reg.save(cand)

    fetched = reg.get(cand.id)
    assert fetched is not None
    assert fetched.parent_id == parent_id
    assert fetched.status == "pending"
    assert fetched.mutations[0]["type"] == "tier_downgrade"

    listed = reg.list(status="pending")
    assert any(c.id == cand.id for c in listed)
    assert reg.list(status="committed") == []


def test_registry_update_status_persists(tmp_path):
    reg = CandidateRegistry(str(tmp_path))
    cand = _make_candidate(uuid4())
    reg.save(cand)
    reg.update_status(cand.id, "committed")
    again = CandidateRegistry(str(tmp_path)).get(cand.id)
    assert again.status == "committed"


# --- CLI approve / reject / rollback ----------------------------------------


def _seed_template_with_candidate(store_dir):
    """Persist a template then a pending candidate that downgrades step 0."""
    ks = KernelSession(store_dir=store_dir)
    tpl = ks.workflow_store.create_template(
        name="t-self-learn", family_key="saucedemo", description="seed"
    )
    # Inject one step with HIGH replayability into the persisted template body.
    payload = ks.workflow_store.provider.load(
        ks.workflow_store.NS_TEMPLATE, str(tpl.id)
    )
    payload["steps"] = [{
        "action": "click",
        "target_role": "button",
        "target_name": "Submit",
        "target_selector": "button.submit",
        "replayability": {"tier": "HIGH"},
    }]
    ks.workflow_store.provider.save(
        ks.workflow_store.NS_TEMPLATE, str(tpl.id), payload
    )
    cand = _make_candidate(tpl.id)
    ks.candidate_registry.save(cand)
    return tpl.id, cand.id


def test_cli_candidate_ls_lists_pending(tmp_path):
    parent_id, cand_id = _seed_template_with_candidate(str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli, ["--store", str(tmp_path), "workflow", "candidate", "ls"]
    )
    assert result.exit_code == 0, result.output
    assert str(cand_id)[:8] in result.output


def test_cli_candidate_approve_commits_mutation(tmp_path):
    parent_id, cand_id = _seed_template_with_candidate(str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "workflow", "candidate", "approve", str(cand_id)],
    )
    assert result.exit_code == 0, result.output

    # Re-open to verify durable state.
    ks = KernelSession(store_dir=str(tmp_path))
    payload = ks.workflow_store.provider.load(
        ks.workflow_store.NS_TEMPLATE, str(parent_id)
    )
    assert payload["steps"][0]["replayability"]["tier"] == "AMBIGUOUS"
    assert payload["steps"][0]["replayability"]["committed_via"] == "approval"
    assert payload["metadata"]["committed_candidate_id"] == str(cand_id)
    assert ks.candidate_registry.get(cand_id).status == "committed"


def test_cli_candidate_reject_marks_rejected(tmp_path):
    _, cand_id = _seed_template_with_candidate(str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "workflow", "candidate", "reject", str(cand_id)],
    )
    assert result.exit_code == 0, result.output
    ks = KernelSession(store_dir=str(tmp_path))
    assert ks.candidate_registry.get(cand_id).status == "rejected"


def test_cli_candidate_rollback_restores_previous_state(tmp_path):
    parent_id, cand_id = _seed_template_with_candidate(str(tmp_path))
    runner = CliRunner()

    # Approve first to get into committed state.
    runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "workflow", "candidate", "approve", str(cand_id)],
    )

    # Rollback should restore the original HIGH tier.
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "workflow", "candidate", "rollback", str(cand_id)],
    )
    assert result.exit_code == 0, result.output

    ks = KernelSession(store_dir=str(tmp_path))
    payload = ks.workflow_store.provider.load(
        ks.workflow_store.NS_TEMPLATE, str(parent_id)
    )
    assert payload["steps"][0]["replayability"]["tier"] == "HIGH"
    assert payload["metadata"].get("rolled_back_candidate_id") == str(cand_id)
    assert ks.candidate_registry.get(cand_id).status == "rolled_back"


def test_cli_candidate_rollback_refuses_non_committed(tmp_path):
    _, cand_id = _seed_template_with_candidate(str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["--store", str(tmp_path), "workflow", "candidate", "rollback", str(cand_id)],
    )
    # Rollback on pending must NOT alter the candidate.
    assert "must" in result.output.lower() or "committed" in result.output.lower()
    ks = KernelSession(store_dir=str(tmp_path))
    assert ks.candidate_registry.get(cand_id).status == "pending"
