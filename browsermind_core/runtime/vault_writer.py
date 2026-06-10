"""Canonical writer for the persona vault.

The runtime reads persona credentials from `persona_vault/<persona>.json`
through `LocalJSONPersistenceProvider` (see `auth_session.AuthSession.get_credentials`
and `resource_resolver.ResourceResolver._resolve_from_vault`). Until now, no
writer existed in the repo for that file — operators edited it by hand.

This module is the single, canonical write path. All credential mutation
flows through `VaultWriter`, which preserves the existing top-level shape:

    {
      "secrets":   { "<env_key>": { "<key>": "<value>" }, ... },
      "resources": { "<env_key>": { "<key>": "<value>" }, ... }
    }

Thread-safety: the underlying provider performs atomic temp-file rename and
SHA-256 checksumming, so concurrent writers on the same persona are safe at
the file level. In-process call ordering is the caller's responsibility.

Backward compatibility: existing files are read-modify-write without
restructuring. Files that pre-date this module remain valid.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider
from browsermind_core.managers.identity.secret_vault import SecretVault


_NS = "persona_vault"
_ENC_PREFIX = "FRN1:"  # Marker for Fernet-encrypted secret values.


def _decrypt_value(value: Any, vault: SecretVault) -> Any:
    """Decrypt a stored value if marked with the Fernet prefix; otherwise return as-is.

    Legacy plaintext entries written before encryption was introduced are
    returned unchanged so existing persona vaults remain readable.
    """
    if isinstance(value, str) and value.startswith(_ENC_PREFIX):
        try:
            return vault.decrypt_value(value[len(_ENC_PREFIX):])
        except Exception:
            return value
    return value


def _encrypt_value(value: str, vault: SecretVault) -> str:
    return _ENC_PREFIX + vault.encrypt_value(value)


class VaultWriter:
    """Read-modify-write surface for `persona_vault/<persona>.json`.

    Construct one per `(store_dir, persona_name)`. Persona names are
    case-preserved on write but lookups also try the lowercase form to
    match `auth_session.get_credentials` fallback behavior.
    """

    def __init__(self, store_dir: str | Path, persona_name: str, vault: Optional[SecretVault] = None):
        self.store_dir = str(store_dir)
        self.persona_name = persona_name
        self._provider = LocalJSONPersistenceProvider(self.store_dir)
        self._vault = vault if vault is not None else SecretVault(store_dir=self.store_dir)

    # ── Read helpers ────────────────────────────────────────────────────

    def load(self) -> Dict[str, Any]:
        """Return the current vault contents with secrets decrypted (or an empty skeleton)."""
        data = self._provider.load(_NS, self.persona_name)
        if data is None and self.persona_name != self.persona_name.lower():
            data = self._provider.load(_NS, self.persona_name.lower())
        if not data:
            return {"secrets": {}, "resources": {}}
        # Defensive: ensure the two top-level buckets always exist.
        data.setdefault("secrets", {})
        data.setdefault("resources", {})
        # Decrypt secret values transparently for callers.
        decrypted_secrets: Dict[str, Dict[str, Any]] = {}
        for env_key, bucket in data.get("secrets", {}).items():
            if isinstance(bucket, dict):
                decrypted_secrets[env_key] = {
                    k: _decrypt_value(v, self._vault) for k, v in bucket.items()
                }
            else:
                decrypted_secrets[env_key] = bucket
        data["secrets"] = decrypted_secrets
        return data

    # ── Write surface ───────────────────────────────────────────────────

    def set_secret(self, env_key: str, key: str, value: str) -> None:
        """Set a secret credential for one (env, key). Stored Fernet-encrypted."""
        self._mutate("secrets", env_key, key, _encrypt_value(value, self._vault))

    def set_resource(self, env_key: str, key: str, value: Any) -> None:
        """Set a non-secret resource (path, URL, structured value) for one (env, key)."""
        self._mutate("resources", env_key, key, value)

    def delete_secret(self, env_key: str, key: str) -> bool:
        """Remove a secret. Returns True if it existed."""
        return self._delete("secrets", env_key, key)

    def delete_resource(self, env_key: str, key: str) -> bool:
        """Remove a resource. Returns True if it existed."""
        return self._delete("resources", env_key, key)

    # ── Internals ───────────────────────────────────────────────────────

    def _load_raw(self) -> Dict[str, Any]:
        """Load the on-disk vault without decrypting secrets. For write paths."""
        data = self._provider.load(_NS, self.persona_name)
        if data is None and self.persona_name != self.persona_name.lower():
            data = self._provider.load(_NS, self.persona_name.lower())
        if not data:
            return {"secrets": {}, "resources": {}}
        data.setdefault("secrets", {})
        data.setdefault("resources", {})
        return data

    def _mutate(self, bucket: str, env_key: str, key: str, value: Any) -> None:
        if not env_key or not key:
            raise ValueError("env_key and key must be non-empty")
        data = self._load_raw()
        env_bucket = data[bucket].setdefault(env_key, {})
        env_bucket[key] = value
        self._provider.save(_NS, self.persona_name, data)

    def _delete(self, bucket: str, env_key: str, key: str) -> bool:
        data = self._load_raw()
        env_bucket = data[bucket].get(env_key) or {}
        if key not in env_bucket:
            return False
        del env_bucket[key]
        if not env_bucket:
            data[bucket].pop(env_key, None)
        self._provider.save(_NS, self.persona_name, data)
        return True


def write_secret(store_dir: str | Path, persona_name: str, env_key: str, key: str, value: str) -> None:
    """One-shot helper for callers that don't need to keep a writer instance."""
    VaultWriter(store_dir, persona_name).set_secret(env_key, key, value)


def write_resource(store_dir: str | Path, persona_name: str, env_key: str, key: str, value: Any) -> None:
    """One-shot helper for non-secret resources."""
    VaultWriter(store_dir, persona_name).set_resource(env_key, key, value)
