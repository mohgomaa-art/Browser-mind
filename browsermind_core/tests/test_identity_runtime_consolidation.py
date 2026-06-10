"""Tier-1 identity-runtime tests: vault writer (M2),
identity-status precheck (M3), session continuity (M5+M6+M7)."""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from browsermind_core.experiments.harness import ReplayExperimentHarness  # noqa: F401
from browsermind_core.managers.identity.identity_service import IdentityService
from browsermind_core.managers.identity.secret_vault import SecretVault
from browsermind_core.ontology.p1_schemas import FailureAttribution, ReplayReport, WorkflowInstance, WorkflowTemplate
from browsermind_core.runtime.auth_session import AuthSession, AuthSessionManager
from browsermind_core.runtime.environment_registry import EnvironmentEntry
from browsermind_core.runtime.replay_engine import ReplayEngine
from browsermind_core.runtime.vault_writer import VaultWriter, write_secret


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def store_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def env_entry() -> EnvironmentEntry:
    return EnvironmentEntry(
        key="testsite",
        start_url="https://example.test/",
        family="test",
    )


# ── M2 — Canonical Vault Writer ──────────────────────────────────────────────

def test_vault_writer_creates_skeleton_when_missing(store_dir: Path):
    w = VaultWriter(store_dir, "alice")
    assert w.load() == {"secrets": {}, "resources": {}}
    # No file written yet — load() doesn't persist.
    vault_path = store_dir / "persona_vault" / "alice.json"
    assert not vault_path.exists()


def test_vault_writer_set_secret_persists_through_provider(store_dir: Path):
    w = VaultWriter(store_dir, "alice")
    w.set_secret(env_key="github", key="password", value="hunter2")
    # VaultWriter.load() decrypts transparently for callers.
    data = w.load()
    assert data["secrets"]["github"]["password"] == "hunter2"
    # On-disk envelope exists with checksum; raw value is Fernet-encrypted, not plaintext.
    raw = json.loads((store_dir / "persona_vault" / "alice.json").read_text())
    assert "_data" in raw and "_checksum" in raw
    on_disk = raw["_data"]["secrets"]["github"]["password"]
    assert on_disk != "hunter2"
    assert "hunter2" not in on_disk
    assert on_disk.startswith("FRN1:")


def test_vault_writer_preserves_existing_buckets(store_dir: Path):
    w = VaultWriter(store_dir, "alice")
    w.set_secret("github", "password", "p1")
    w.set_secret("github", "totp", "p2")
    w.set_resource("github", "username", "alice")
    w.set_secret("gitlab", "password", "p3")
    data = w.load()
    assert data["secrets"]["github"] == {"password": "p1", "totp": "p2"}
    assert data["secrets"]["gitlab"] == {"password": "p3"}
    assert data["resources"]["github"] == {"username": "alice"}


def test_vault_writer_delete_secret(store_dir: Path):
    w = VaultWriter(store_dir, "alice")
    w.set_secret("github", "password", "p1")
    assert w.delete_secret("github", "password") is True
    assert w.delete_secret("github", "password") is False  # idempotent
    assert "github" not in w.load()["secrets"]


def test_vault_writer_one_shot_helper(store_dir: Path):
    write_secret(store_dir, "alice", "github", "password", "p1")
    assert VaultWriter(store_dir, "alice").load()["secrets"]["github"]["password"] == "p1"


def test_vault_writer_runtime_resolver_can_read_what_writer_wrote(store_dir: Path):
    """End-to-end: writer -> runtime read path matches.

    On-disk values are Fernet-encrypted; `VaultWriter.load()` (and therefore
    `AuthSession.get_credentials`) decrypts them transparently.
    """
    write_secret(store_dir, "alice", "github", "password", "hunter2")

    # Raw provider read returns the encrypted token.
    from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider
    provider = LocalJSONPersistenceProvider(str(store_dir))
    raw = provider.load("persona_vault", "alice")
    assert raw["secrets"]["github"]["password"].startswith("FRN1:")

    # The runtime read path (mirroring AuthSession.get_credentials) decrypts.
    decrypted = VaultWriter(store_dir, "alice").load()
    assert decrypted["secrets"]["github"]["password"] == "hunter2"


def test_identity_service_provision_writes_through_to_runtime_vault(store_dir: Path):
    """M2 + IdentityService integration: when store_dir+persona_name+env_key are
    supplied, provisioned credentials reach the runtime vault."""
    svc = IdentityService(SecretVault())
    persona_id = uuid4()
    env_id = uuid4()
    svc.provision_identity(
        persona_id=persona_id,
        environment_id=env_id,
        identifier="alice@github",
        raw_secret="hunter2",
        store_dir=str(store_dir),
        persona_name="alice",
        env_key="github",
    )
    data = VaultWriter(store_dir, "alice").load()
    assert data["secrets"]["github"]["password"] == "hunter2"


def test_identity_service_backward_compatible_without_runtime_args():
    """Legacy callers (no store_dir/persona_name/env_key) still work."""
    svc = IdentityService(SecretVault())
    identity = svc.provision_identity(
        persona_id=uuid4(),
        environment_id=uuid4(),
        identifier="alice@github",
        raw_secret="hunter2",
    )
    assert identity.id is not None
    assert identity.identifier == "alice@github"


# ── M3 — Identity Status Enforcement ─────────────────────────────────────────

def _seed_identity_index(store_dir: Path, persona: str, env_key: str, status: str):
    idx = {
        f"{persona}@{env_key}": {
            "id": str(uuid4()),
            "persona": persona,
            "env": env_key,
            "status": status,
        }
    }
    (store_dir / "_identity_index.json").write_text(json.dumps(idx), encoding="utf-8")


def test_resolve_identity_status_returns_none_when_no_index(store_dir: Path, env_entry):
    sess = AuthSession(env_entry, "alice", store_dir)
    assert sess.resolve_identity_status(env_entry.key) is None


def test_resolve_identity_status_reads_index(store_dir: Path, env_entry):
    _seed_identity_index(store_dir, "alice", env_entry.key, "expired")
    sess = AuthSession(env_entry, "alice", store_dir)
    assert sess.resolve_identity_status(env_entry.key) == "expired"


def test_resolve_identity_status_skips_other_personas(store_dir: Path, env_entry):
    _seed_identity_index(store_dir, "bob", env_entry.key, "expired")
    sess = AuthSession(env_entry, "alice", store_dir)
    assert sess.resolve_identity_status(env_entry.key) is None


def _make_engine(status_value):
    """Build a ReplayEngine with a stub AuthSession that returns the given status."""
    auth = MagicMock()
    auth.persona_name = "alice"
    auth.store_dir = Path("/tmp/store")
    auth.resolve_identity_status = MagicMock(return_value=status_value)
    auth.open = AsyncMock()
    auth.close = AsyncMock()
    return ReplayEngine(auth, owns_session=True), auth


def _make_template():
    return WorkflowTemplate(
        name="t",
        description="t",
        steps=[
            {"seq": 1, "action_type": "click", "target_role": "button",
             "target_name": "Go", "target_selector": "#go"}
        ],
        metadata={},
    )


def _make_empty_template():
    """Template with zero steps. Skips the engine's post-finally
    resource-resolution-rate block, which references a local that is only
    bound inside the try (pre-existing engine code, out of Tier-1 scope)."""
    return WorkflowTemplate(
        name="t-empty",
        description="t",
        steps=[],
        metadata={},
    )


def _make_instance(template: WorkflowTemplate):
    return WorkflowInstance(
        id=uuid4(),
        persona_id=uuid4(),
        template_id=template.id,
        bound_resources={},
        bound_identities={},
    )


def _site():
    return SimpleNamespace(key="testsite", label="Test")


@pytest.mark.parametrize("status", ["expired", "requires_2fa", "revoked"])
def test_replay_blocks_on_nonactive_identity(status):
    engine, auth = _make_engine(status)
    template = _make_template()
    report = asyncio.run(engine.replay(_site(), template, _make_instance(template)))
    assert report.status == "BLOCKED"
    assert report.failure_reason and f"IDENTITY_{status.upper()}" in report.failure_reason
    auth.open.assert_not_called()  # browser never opened


def test_replay_proceeds_on_active_identity():
    engine, auth = _make_engine("active")
    auth.open = AsyncMock(side_effect=RuntimeError("simulated launch failure"))
    template = _make_empty_template()
    report = asyncio.run(engine.replay(_site(), template, _make_instance(template)))
    # The simulated open() raised inside the try block; status should not be BLOCKED.
    assert report.status != "BLOCKED"
    auth.open.assert_called()


def test_replay_proceeds_on_no_identity_record():
    engine, _ = _make_engine(None)
    auth = engine.auth_session
    auth.open = AsyncMock(side_effect=RuntimeError("simulated"))
    template = _make_empty_template()
    report = asyncio.run(engine.replay(_site(), template, _make_instance(template)))
    assert report.status != "BLOCKED"


# ── M5+M6+M7 — Session Continuity ────────────────────────────────────────────

def test_replay_engine_owns_session_default():
    auth = MagicMock()
    engine = ReplayEngine(auth)
    assert engine.owns_session is True


def test_replay_engine_owns_session_false_skips_close():
    auth = MagicMock()
    auth.persona_name = "alice"
    auth.store_dir = Path("/tmp")
    auth.resolve_identity_status = MagicMock(return_value=None)
    # open() raises so we exit through the finally block fast.
    auth.open = AsyncMock(side_effect=RuntimeError("simulated"))
    auth.close = AsyncMock()

    engine = ReplayEngine(auth, owns_session=False)
    template = _make_empty_template()
    asyncio.run(engine.replay(_site(), template, _make_instance(template)))
    auth.close.assert_not_called()


def test_replay_engine_owns_session_true_closes():
    """When owns_session=True, the engine closes the session in its finally
    block. We make open() return a fake page so the `if page:` guard inside
    finally is satisfied, then ensure close() was called once."""
    auth = MagicMock()
    auth.persona_name = "alice"
    auth.store_dir = Path("/tmp")
    auth.resolve_identity_status = MagicMock(return_value=None)
    fake_page = MagicMock()
    fake_page.context = MagicMock()
    auth.open = AsyncMock(return_value=fake_page)
    auth.close = AsyncMock()

    engine = ReplayEngine(auth, owns_session=True)
    template = _make_empty_template()
    asyncio.run(engine.replay(_site(), template, _make_instance(template)))
    auth.close.assert_called_once()


def test_replay_engine_owns_session_false_skips_close_after_open():
    """Mirror of above with owns_session=False — close() must not be called
    even when the browser opened cleanly."""
    auth = MagicMock()
    auth.persona_name = "alice"
    auth.store_dir = Path("/tmp")
    auth.resolve_identity_status = MagicMock(return_value=None)
    fake_page = MagicMock()
    fake_page.context = MagicMock()
    auth.open = AsyncMock(return_value=fake_page)
    auth.close = AsyncMock()

    engine = ReplayEngine(auth, owns_session=False)
    template = _make_empty_template()
    asyncio.run(engine.replay(_site(), template, _make_instance(template)))
    auth.close.assert_not_called()


def test_auth_session_manager_close_session_evicts_cache(tmp_path: Path, env_entry):
    mgr = AuthSessionManager(tmp_path)
    sess = mgr.get_or_create(env_entry, "alice")
    sess.close = AsyncMock()  # type: ignore
    assert ("alice", env_entry.key) in mgr._active

    closed = asyncio.run(mgr.close_session("alice", env_entry.key))
    assert closed is True
    assert ("alice", env_entry.key) not in mgr._active
    sess.close.assert_called_once()


def test_auth_session_manager_close_session_returns_false_for_unknown(tmp_path: Path):
    mgr = AuthSessionManager(tmp_path)
    closed = asyncio.run(mgr.close_session("nobody", "nowhere"))
    assert closed is False


def test_auth_session_manager_close_all(tmp_path: Path):
    mgr = AuthSessionManager(tmp_path)
    e1 = EnvironmentEntry(key="a", start_url="https://a", family="t")
    e2 = EnvironmentEntry(key="b", start_url="https://b", family="t")
    s1 = mgr.get_or_create(e1, "alice")
    s2 = mgr.get_or_create(e2, "alice")
    s1.close = AsyncMock()  # type: ignore
    s2.close = AsyncMock()  # type: ignore

    closed = asyncio.run(mgr.close_all())
    assert closed == 2
    assert mgr._active == {}
    s1.close.assert_called_once()
    s2.close.assert_called_once()


def test_auth_session_manager_get_or_create_dedups():
    mgr = AuthSessionManager(Path("/tmp/x"))
    entry = EnvironmentEntry(key="a", start_url="https://a", family="t")
    s1 = mgr.get_or_create(entry, "alice")
    s2 = mgr.get_or_create(entry, "alice")
    assert s1 is s2
