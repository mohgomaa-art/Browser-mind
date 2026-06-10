"""P0 — Mutation Ledger survives process restart when repository is wired."""
import pytest
from uuid import uuid4

from browsermind_core.ledger.ledger_repository import LedgerRepository
from browsermind_core.ledger.mutation_ledger import MutationLedger
from browsermind_core.runtime.event_bus import EventBus
from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider


def _emit_mutation(bus: EventBus, entity_id=None):
    bus.emit(
        "EntityMutated",
        {
            "entity_type": "Execution",
            "entity_id": entity_id or uuid4(),
            "old_value": {"status": "running"},
            "new_value": {"status": "succeeded"},
            "actor": "test",
            "evidence": "unit_test",
        },
    )


def test_ledger_hydrates_from_repository_on_new_session(tmp_path):
    store = str(tmp_path / "bm")
    provider = LocalJSONPersistenceProvider(store)
    repo = LedgerRepository(provider)

    bus1 = EventBus()
    ledger1 = MutationLedger(bus1, repository=repo)
    _emit_mutation(bus1)
    _emit_mutation(bus1)
    assert len(ledger1.get_history()) == 2
    assert repo.count() == 2

    bus2 = EventBus()
    ledger2 = MutationLedger(bus2, repository=repo)
    assert len(ledger2.get_history()) == 2
    assert ledger2.get_history()[0].entity_type == "Execution"

    _emit_mutation(bus2)
    assert len(ledger2.get_history()) == 3
    assert repo.count() == 3

    bus3 = EventBus()
    ledger3 = MutationLedger(bus3, repository=repo)
    assert len(ledger3.get_history()) == 3
