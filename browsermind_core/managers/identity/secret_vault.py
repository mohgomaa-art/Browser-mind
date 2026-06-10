"""Real Fernet-backed SecretVault.

Replaces the prior SHA-256 mock. Key resolution order at construction:
  1. BROWSERMIND_VAULT_KEY env var (base64-encoded Fernet key)
  2. <store_dir>/.vault_key file (mode 0600 best-effort)
  3. Newly generated Fernet key, persisted to (2)

Secrets are persisted via LocalJSONPersistenceProvider under the "secret"
namespace, keyed by identity_id, and mirrored in an in-memory cache that
is hydrated from disk at construction.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional, Union
from uuid import UUID

from cryptography.fernet import Fernet

from browsermind_core.ontology.p1_schemas import Secret
from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider


_NS = "secret"
_KEY_FILENAME = ".vault_key"
_ENV_VAR = "BROWSERMIND_VAULT_KEY"
_DEFAULT_STORE_DIR = Path.home() / ".browsermind"


class SecretVault:
    """Fernet-encrypted secret store with on-disk persistence."""

    def __init__(
        self,
        store_dir: Optional[Union[str, Path]] = None,
        key: Optional[bytes] = None,
    ):
        self.store_dir = Path(store_dir) if store_dir is not None else _DEFAULT_STORE_DIR
        self.store_dir.mkdir(parents=True, exist_ok=True)

        self._key = key if key is not None else self._resolve_key(self.store_dir)
        self._fernet = Fernet(self._key)
        self._provider = LocalJSONPersistenceProvider(str(self.store_dir))
        self._secrets: Dict[UUID, Secret] = {}
        self._hydrate()

    # ── Key resolution ──────────────────────────────────────────────────

    @staticmethod
    def _resolve_key(store_dir: Path) -> bytes:
        env_val = os.environ.get(_ENV_VAR)
        if env_val:
            return env_val.encode() if isinstance(env_val, str) else env_val

        key_path = store_dir / _KEY_FILENAME
        if key_path.exists():
            return key_path.read_bytes().strip()

        new_key = Fernet.generate_key()
        key_path.write_bytes(new_key)
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass  # Windows / non-POSIX: best-effort
        return new_key

    # ── Hydration ──────────────────────────────────────────────────────

    def _hydrate(self) -> None:
        for key in self._provider.list_keys(_NS):
            data = self._provider.load(_NS, key)
            if not data:
                continue
            try:
                secret = Secret(**data)
            except Exception:
                continue
            self._secrets[secret.identity_id] = secret

    # ── Public API ─────────────────────────────────────────────────────

    def encrypt_and_store(
        self, identity_id: UUID, raw_secret: str, secret_type: str
    ) -> Secret:
        token = self._fernet.encrypt(raw_secret.encode("utf-8")).decode("ascii")
        secret = Secret(
            identity_id=identity_id,
            secret_type=secret_type,  # type: ignore[arg-type]
            encrypted_value=token,
        )
        self._secrets[identity_id] = secret
        self._provider.save(_NS, str(identity_id), secret.model_dump(mode="json"))
        return secret

    def get_secret_for_identity(self, identity_id: UUID) -> Optional[Secret]:
        cached = self._secrets.get(identity_id)
        if cached is not None:
            return cached
        data = self._provider.load(_NS, str(identity_id))
        if not data:
            return None
        try:
            secret = Secret(**data)
        except Exception:
            return None
        self._secrets[identity_id] = secret
        return secret

    def decrypt(self, secret: Secret) -> str:
        return self._fernet.decrypt(secret.encrypted_value.encode("ascii")).decode("utf-8")

    def encrypt_value(self, raw: str) -> str:
        """Encrypt an arbitrary string with the vault key (for VaultWriter use)."""
        return self._fernet.encrypt(raw.encode("utf-8")).decode("ascii")

    def decrypt_value(self, token: str) -> str:
        """Decrypt a token produced by encrypt_value."""
        return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
