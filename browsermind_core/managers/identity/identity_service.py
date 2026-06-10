from uuid import UUID
from typing import Optional
from browsermind_core.ontology.p1_schemas import Identity
from browsermind_core.managers.identity.secret_vault import SecretVault

class IdentityService:
    def __init__(self, vault: SecretVault):
        self.vault = vault

    def provision_identity(
        self,
        persona_id: UUID,
        environment_id: UUID,
        identifier: str,
        raw_secret: str,
        *,
        store_dir: Optional[str] = None,
        persona_name: Optional[str] = None,
        env_key: Optional[str] = None,
        secret_field: str = "password",
    ) -> Identity:
        identity = Identity(
            persona_id=persona_id,
            environment_id=environment_id,
            identifier=identifier
        )

        self.vault.encrypt_and_store(identity.id, raw_secret, "password")

        # Optional runtime-vault write. The in-memory SecretVault preserves
        # original semantics for unit tests; when callers supply
        # store_dir + persona_name + env_key, the credential also lands in
        # persona_vault/<persona>.json so the runtime resolver can read it
        # at replay time. This is the only canonical writer for that file.
        if store_dir and persona_name and env_key:
            from browsermind_core.runtime.vault_writer import VaultWriter
            VaultWriter(store_dir, persona_name).set_secret(
                env_key=env_key,
                key=secret_field,
                value=raw_secret,
            )

        return identity
