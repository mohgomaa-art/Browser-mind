"""Tests for the Fernet-backed SecretVault."""
from __future__ import annotations

import os
import sys
from uuid import uuid4

import pytest

from browsermind_core.managers.identity.secret_vault import SecretVault


_ENV_VAR = "BROWSERMIND_VAULT_KEY"


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Ensure the env-var key does not leak between tests."""
    monkeypatch.delenv(_ENV_VAR, raising=False)
    yield


def test_encrypt_decrypt_roundtrip(tmp_path):
    vault = SecretVault(store_dir=tmp_path)
    identity_id = uuid4()
    raw = "s3cret-pa55w0rd!"
    secret = vault.encrypt_and_store(identity_id, raw, "password")

    assert secret.identity_id == identity_id
    assert secret.encrypted_value
    assert vault.decrypt(secret) == raw


def test_encrypted_value_is_not_plaintext(tmp_path):
    vault = SecretVault(store_dir=tmp_path)
    identity_id = uuid4()
    raw = "hunter2-correct-horse-battery-staple"
    secret = vault.encrypt_and_store(identity_id, raw, "password")

    assert raw not in secret.encrypted_value
    # And the encoded token should not contain a substring of the plaintext either.
    assert "hunter2" not in secret.encrypted_value


def test_key_persisted_across_instances(tmp_path):
    vault_a = SecretVault(store_dir=tmp_path)
    identity_id = uuid4()
    raw = "rotating-token-xyz"
    secret_a = vault_a.encrypt_and_store(identity_id, raw, "token")

    vault_b = SecretVault(store_dir=tmp_path)
    # vault_b must derive the same key from .vault_key on disk.
    assert vault_b.decrypt(secret_a) == raw


def test_env_var_key_wins(tmp_path, monkeypatch):
    # Pre-create a different on-disk key.
    seed_vault = SecretVault(store_dir=tmp_path)
    on_disk_key = seed_vault._key  # noqa: SLF001 (test introspection)

    # Choose a distinct key and put it in the env var.
    from cryptography.fernet import Fernet
    env_key = Fernet.generate_key()
    assert env_key != on_disk_key
    monkeypatch.setenv(_ENV_VAR, env_key.decode("ascii"))

    vault = SecretVault(store_dir=tmp_path)
    assert vault._key == env_key  # noqa: SLF001

    # And a secret encrypted with the env key cannot be decrypted with the on-disk key.
    identity_id = uuid4()
    raw = "env-wins"
    secret = vault.encrypt_and_store(identity_id, raw, "password")
    assert vault.decrypt(secret) == raw

    # Switch back to file-key vault: it should fail to decrypt the env-key secret.
    monkeypatch.delenv(_ENV_VAR, raising=False)
    file_vault = SecretVault(store_dir=tmp_path)
    from cryptography.fernet import InvalidToken
    with pytest.raises(InvalidToken):
        file_vault.decrypt(secret)


def test_secrets_persisted_across_instances(tmp_path):
    vault_a = SecretVault(store_dir=tmp_path)
    identity_id = uuid4()
    raw = "persisted-secret-123"
    vault_a.encrypt_and_store(identity_id, raw, "password")

    vault_b = SecretVault(store_dir=tmp_path)
    fetched = vault_b.get_secret_for_identity(identity_id)
    assert fetched is not None
    assert fetched.identity_id == identity_id
    assert vault_b.decrypt(fetched) == raw


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX-only chmod check")
def test_key_file_mode_is_0600_on_posix(tmp_path):
    SecretVault(store_dir=tmp_path)
    key_path = tmp_path / ".vault_key"
    assert key_path.exists()
    mode = key_path.stat().st_mode & 0o777
    assert mode == 0o600
