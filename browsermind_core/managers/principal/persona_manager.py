from typing import Dict, List, Optional
from uuid import UUID
from pathlib import Path

from browsermind_core.ontology.p1_schemas import Persona
from browsermind_core.runtime.event_bus import EventBus
from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider


_NS = "persona"


class DuplicatePersonaError(ValueError):
    """Raised when a persona with the same name + principal_id already exists."""
    pass


class PersonaManager:
    """Manages Personas with on-disk persistence.

    When constructed without a store_dir, behaves as an in-memory manager
    (preserves existing test/UI call sites). When constructed with a
    store_dir, every create_persona() write hits disk under the "persona"
    namespace and subsequent process starts rehydrate from there.
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        store_dir: Optional[str] = None,
    ):
        self.event_bus = event_bus
        self._provider: Optional[LocalJSONPersistenceProvider] = (
            LocalJSONPersistenceProvider(str(store_dir)) if store_dir else None
        )
        self._personas: Dict[str, Persona] = {}
        if self._provider is not None:
            self._hydrate()

    def _hydrate(self) -> None:
        assert self._provider is not None
        for key in self._provider.list_keys(_NS):
            data = self._provider.load(_NS, key)
            if not data:
                continue
            try:
                persona = Persona(**data)
            except Exception:
                continue
            self._personas[str(persona.id)] = persona

    def create_persona(self, principal_id: UUID, name: str) -> Persona:
        for existing in self._personas.values():
            if existing.name == name and existing.principal_id == principal_id:
                raise DuplicatePersonaError(
                    f"Persona '{name}' already exists for principal {principal_id} "
                    f"(id={existing.id}). Use get_persona() or lookup_by_name()."
                )
        persona = Persona(principal_id=principal_id, name=name)
        self._personas[str(persona.id)] = persona
        if self._provider is not None:
            self._provider.save(_NS, str(persona.id), persona.model_dump(mode="json"))
        if self.event_bus:
            self.event_bus.emit("EntityMutated", {
                "entity_type": "Persona",
                "entity_id": persona.id,
                "new_value": persona.model_dump(mode="json"),
                "actor": str(principal_id),
            })
        return persona

    def get_persona(self, persona_id: UUID) -> Optional[Persona]:
        cached = self._personas.get(str(persona_id))
        if cached is not None:
            return cached
        if self._provider is None:
            return None
        data = self._provider.load(_NS, str(persona_id))
        if not data:
            return None
        try:
            persona = Persona(**data)
        except Exception:
            return None
        self._personas[str(persona.id)] = persona
        return persona

    def list_personas(self) -> List[Persona]:
        return list(self._personas.values())

    def lookup_by_name(self, name: str) -> Optional[Persona]:
        for p in self._personas.values():
            if p.name == name:
                return p
        return None
