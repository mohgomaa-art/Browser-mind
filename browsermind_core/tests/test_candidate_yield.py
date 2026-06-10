"""Tests for candidate_yield aggregator using synthetic OutcomeRecords."""
from uuid import uuid4

from browsermind_core.ledger.outcome_ledger import OutcomeRecord, OutcomeLedger
from browsermind_core.training.candidate_yield import aggregate


def _ledger():
    return OutcomeLedger()


def _add_run(ledger, env="saucedemo", template="saucedemo_checkout_v1", success=True, persona=None, exec_id=None):
    persona = persona or uuid4()
    exec_id = exec_id or uuid4()
    instance_id = uuid4()
    task_id = uuid4()
    ledger.record(OutcomeRecord(
        scope="workflow_instance", scope_id=instance_id, persona_id=persona,
        environment_family=env, environment_instance=env,
        outcome_type="replay_completed", success=success,
        evidence="run", execution_id=exec_id, task_id=task_id,
        metrics={"template_name": template, "status": "SUCCESS" if success else "FAILED"},
    ))
    ledger.record(OutcomeRecord(
        scope="task" if task_id else "workflow_instance",
        scope_id=task_id, persona_id=persona,
        environment_family=env, environment_instance=env,
        outcome_type="contract_verification", success=success,
        evidence=f"goal_completed={success}",
        execution_id=exec_id, task_id=task_id,
        metrics={"contract_id": template, "template_name": template},
    ))
    return persona, exec_id


def test_no_data_insufficient():
    rep = aggregate(_ledger().records)
    assert rep["decision"]["verdict"] == "INSUFFICIENT_DATA"


def test_all_success_promote():
    L = _ledger()
    for _ in range(5):
        _add_run(L, success=True)
    rep = aggregate(L.records)
    assert rep["totals"]["applications_attempted"] == 5
    assert rep["totals"]["applications_submitted"] == 5
    assert rep["totals"]["submission_rate"] == 1.0
    assert rep["decision"]["verdict"] == "PROMOTE"


def test_low_yield_debug():
    L = _ledger()
    for _ in range(8):
        _add_run(L, success=False)
    for _ in range(2):
        _add_run(L, success=True)
    rep = aggregate(L.records)
    assert rep["totals"]["submission_rate"] == 0.2
    assert rep["decision"]["verdict"] == "ITERATE"


def test_per_env_breakdown():
    L = _ledger()
    _add_run(L, env="saucedemo", success=True)
    _add_run(L, env="saucedemo", success=False)
    _add_run(L, env="greenhouse", success=True)
    rep = aggregate(L.records)
    assert rep["by_environment_instance"]["saucedemo"] == {"attempted": 2, "submitted": 1}
    assert rep["by_environment_instance"]["greenhouse"] == {"attempted": 1, "submitted": 1}


def test_step_fpr_in_failed_runs():
    L = _ledger()
    persona, exec_id = _add_run(L, success=False)
    L.record(OutcomeRecord(
        scope="step", scope_id=uuid4(), persona_id=persona,
        environment_family="saucedemo", environment_instance="saucedemo",
        outcome_type="step_attempt", success=True,
        evidence="resolved", execution_id=exec_id,
        metrics={"effect_verified": True, "failure_class": None},
    ))
    L.record(OutcomeRecord(
        scope="step", scope_id=uuid4(), persona_id=persona,
        environment_family="saucedemo", environment_instance="saucedemo",
        outcome_type="step_attempt", success=False,
        evidence="failed", execution_id=exec_id,
        metrics={"effect_verified": False, "failure_class": "TARGET_CHANGED"},
    ))
    rep = aggregate(L.records)
    assert rep["totals"]["step_false_positive_rate_in_failed_runs"] == 0.5
    assert rep["step_failure_classes"]["TARGET_CHANGED"] == 1
