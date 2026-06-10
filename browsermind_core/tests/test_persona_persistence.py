"""Persona persistence: PersonaManager must rehydrate from disk across processes."""
from __future__ import annotations

import tempfile
from uuid import uuid4

from browsermind_core.managers.principal.persona_manager import PersonaManager


def test_create_then_rehydrate_in_new_manager():
    with tempfile.TemporaryDirectory() as d:
        principal = uuid4()
        pm = PersonaManager(store_dir=d)
        p = pm.create_persona(principal_id=principal, name="alice")

        pm2 = PersonaManager(store_dir=d)
        rehydrated = pm2.get_persona(p.id)

        assert rehydrated is not None
        assert rehydrated.name == "alice"
        assert rehydrated.principal_id == principal


def test_lookup_by_name_after_rehydrate():
    with tempfile.TemporaryDirectory() as d:
        pm = PersonaManager(store_dir=d)
        pm.create_persona(principal_id=uuid4(), name="bob")

        pm2 = PersonaManager(store_dir=d)
        found = pm2.lookup_by_name("bob")

        assert found is not None
        assert found.name == "bob"


def test_list_personas_returns_all_persisted():
    with tempfile.TemporaryDirectory() as d:
        pm = PersonaManager(store_dir=d)
        principal = uuid4()
        pm.create_persona(principal_id=principal, name="alpha")
        pm.create_persona(principal_id=principal, name="beta")

        pm2 = PersonaManager(store_dir=d)
        names = sorted(p.name for p in pm2.list_personas())
        assert names == ["alpha", "beta"]


def test_in_memory_only_when_no_store_dir():
    """No store_dir => no disk writes, no rehydration. Backwards compatible."""
    pm = PersonaManager()
    pm.create_persona(principal_id=uuid4(), name="ephemeral")
    assert len(pm.list_personas()) == 1
