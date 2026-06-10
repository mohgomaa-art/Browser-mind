"""
Integration test: Recorder<->Vault contract.

Verifies:
  1. VaultProvider resolves b_key="password" -> correct credential value.
  2. VaultProvider returns None for b_key="pending_vault_extraction" (old dead key).

Run from project root:
    python scripts/test_vault_contract.py
"""
import sys
import asyncio
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider
from browsermind_core.runtime.acquisition_runtime import VaultProvider, ResourceRequest
from browsermind_core.ontology.resource_ontology import ResourceClass


# ---------------------------------------------------------------------------
# Minimal stub matching the interface VaultProvider.acquire expects
# ---------------------------------------------------------------------------

@dataclass
class _FakeEntry:
    key: str

class _FakeAuthSession:
    def __init__(self, store_dir: str, persona_name: str, site_key: str):
        self.store_dir = Path(store_dir)
        self.persona_name = persona_name
        self.entry = _FakeEntry(key=site_key)

# VaultProvider.acquire(req, resolver) where resolver is a ResourceResolver.
# ResourceResolver exposes: resolver._get_vault_data() and resolver.auth_session.entry.key
# We need a stub that looks like ResourceResolver to VaultProvider.
class _FakeResolver:
    def __init__(self, store_dir: str, persona_name: str, site_key: str):
        self.auth_session = _FakeAuthSession(store_dir, persona_name, site_key)
        self._vault_data = None

    def _get_vault_data(self) -> dict:
        if self._vault_data is None:
            provider = LocalJSONPersistenceProvider(str(self.auth_session.store_dir))
            data = provider.load("persona_vault", self.auth_session.persona_name)
            if not data:
                data = provider.load("persona_vault", self.auth_session.persona_name.lower())
            self._vault_data = data or {}
        return self._vault_data


async def run_tests():
    store_dir = str(Path.home() / ".browsermind")
    failures = []

    for site_key, expected_password in [
        ("saucedemo",    "secret_sauce"),
        ("aria_internet", "SuperSecretPassword!"),
    ]:
        resolver = _FakeResolver(store_dir, "pilot", site_key)
        provider = VaultProvider()
        req = ResourceRequest(resource_key="password", resource_class=ResourceClass.SECRET)

        result = await provider.acquire(req, resolver)
        if result != expected_password:
            failures.append(
                f"FAIL [{site_key}] b_key='password': expected={expected_password!r} got={result!r}"
            )
        else:
            print(f"PASS [{site_key}] b_key='password' -> {result!r}")

        # Confirm old dead key returns None
        req_old = ResourceRequest(resource_key="pending_vault_extraction", resource_class=ResourceClass.SECRET)
        result_old = await provider.acquire(req_old, resolver)
        if result_old is not None:
            failures.append(
                f"FAIL [{site_key}] b_key='pending_vault_extraction': expected=None got={result_old!r}"
            )
        else:
            print(f"PASS [{site_key}] b_key='pending_vault_extraction' -> None (dead key confirmed)")

    if failures:
        for f in failures:
            print(f)
        sys.exit(1)
    else:
        print("\nAll vault contract assertions passed.")


if __name__ == "__main__":
    asyncio.run(run_tests())
