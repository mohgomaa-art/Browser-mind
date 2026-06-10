from typing import Optional
from uuid import UUID
from browsermind_core.ontology.p1_schemas import Principal
from browsermind_core.runtime.event_bus import EventBus

class PrincipalManager:
    def __init__(self, event_bus: Optional[EventBus] = None):
        self.event_bus = event_bus

    def create_principal(self, name: str, principal_type: str) -> Principal:
        principal = Principal(name=name, principal_type=principal_type) # type: ignore
        
        if self.event_bus:
            self.event_bus.emit("EntityMutated", {
                "entity_type": "Principal",
                "entity_id": principal.id,
                "new_value": principal.model_dump(mode="json"),
                "actor": "system_admin"
            })
            
        return principal
