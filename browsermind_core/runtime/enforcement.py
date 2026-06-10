from typing import TypeVar, Generic, Type, Any
from uuid import UUID
from core.ontology.p1_schemas import BaseEntity, Persona, Identity, Secret, WorkflowInstance, Environment

T = TypeVar('T', bound=BaseEntity)

class UnauthorizedMutationError(Exception):
    """Raised when a Manager attempts to mutate an entity it does not own."""
    pass

class BaseManager(Generic[T]):
    """
    The BaseManager mathematically enforces the BrowserMind Ownership Matrix. 
    A manager is ONLY allowed to mutate the specific entity type it owns.
    Cross-boundary writes will raise a strict runtime error.
    """
    __owned_entity__: Type[T]

    def __init__(self):
        if not hasattr(self, '__owned_entity__'):
            raise NotImplementedError("Manager must define __owned_entity__ to enforce ownership constraints.")

    def _verify_ownership(self, entity: Any):
        if not isinstance(entity, self.__owned_entity__):
            raise UnauthorizedMutationError(
                f"SECURITY VIOLATION: {self.__class__.__name__} is forbidden from mutating {type(entity).__name__}. "
                f"It strictly owns {self.__owned_entity__.__name__}."
            )

    def save(self, entity: T) -> T:
        self._verify_ownership(entity)
        # Mock database persistence
        print(f"[{self.__class__.__name__}] Safely persisted {type(entity).__name__} ({entity.id})")
        return entity

    def delete(self, entity: T) -> None:
        self._verify_ownership(entity)
        print(f"[{self.__class__.__name__}] Deleted {type(entity).__name__} ({entity.id})")


# =============================================================================
# 1. Secret Vault Isolation
# =============================================================================

class SecretVault(BaseManager[Secret]):
    __owned_entity__ = Secret

    def encrypt_and_store(self, identity_id: UUID, raw_secret: str, secret_type: str) -> Secret:
        """Only the Vault is allowed to encrypt and persist actual credentials."""
        secret = Secret(
            identity_id=identity_id,
            secret_type=secret_type,  # type: ignore
            encrypted_value=f"ENC[AES256_GCM:{raw_secret}]" # Mock encryption
        )
        return self.save(secret)


# =============================================================================
# 2. Identity Service
# =============================================================================

class IdentityService(BaseManager[Identity]):
    __owned_entity__ = Identity

    def __init__(self, vault: SecretVault):
        super().__init__()
        # IdentityService interacts with the Vault via contract, 
        # but cannot manipulate Secret objects directly.
        self.vault = vault

    def provision_identity(self, persona_id: UUID, environment_id: UUID, identifier: str, raw_secret: str) -> Identity:
        # Create Identity
        identity = Identity(
            persona_id=persona_id,
            environment_id=environment_id,
            identifier=identifier
        )
        self.save(identity)
        
        # Delegate Secret creation to the Vault (Enforcing Lifecycle Boundary)
        self.vault.encrypt_and_store(identity.id, raw_secret, secret_type="password")
        return identity


# =============================================================================
# 3. Persona Manager
# =============================================================================

class PersonaManager(BaseManager[Persona]):
    __owned_entity__ = Persona


# =============================================================================
# 4. Workflow Manager
# =============================================================================

class WorkflowManager(BaseManager[WorkflowInstance]):
    __owned_entity__ = WorkflowInstance

    def provision_workflow(self, persona_id: UUID, template_id: UUID, identity: Identity) -> WorkflowInstance:
        """
        WorkflowManager can READ the Identity object (to extract its ID), 
        but if it attempts to call self.save(identity), it will trigger 
        an UnauthorizedMutationError, preventing Manager Explosion.
        """
        instance = WorkflowInstance(
            persona_id=persona_id,
            template_id=template_id,
            bound_identities={"default_login": identity.id},
            bound_resources={}
        )
        return self.save(instance)

# Example of prevention:
# mgr = WorkflowManager()
# mgr.save(Identity(...)) -> Raises UnauthorizedMutationError!
