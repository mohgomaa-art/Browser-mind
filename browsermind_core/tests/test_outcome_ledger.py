"""P1.5: Outcome ledger persistence."""
from uuid import uuid4

from browsermind_core.ledger.outcome_ledger import OutcomeLedger, OutcomeRecord
from browsermind_core.ledger.outcome_repository import OutcomeRepository
from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider


def test_outcome_persists_across_ledger_instances(tmp_path):
    provider = LocalJSONPersistenceProvider(str(tmp_path / "bm"))
    repo = OutcomeRepository(provider)
    persona_id = uuid4()
    execution_id = uuid4()

    ledger1 = OutcomeLedger(repository=repo)
    ledger1.record(
        OutcomeRecord(
            scope="execution",
            scope_id=execution_id,
            persona_id=persona_id,
            execution_id=execution_id,
            outcome_type="login_succeeded",
            success=True,
            evidence="Dashboard visible",
            environment_family="saucedemo",
            environment_instance="https://www.saucedemo.com/",
        )
    )

    ledger2 = OutcomeLedger(repository=repo)
    assert len(ledger2.records) == 1
    assert ledger2.records[0].success is True
    assert ledger2.list_for_execution(execution_id)[0].outcome_type == "login_succeeded"
