from uuid import UUID
from typing import Optional
from browsermind_core.ontology.p1_schemas import Task
from browsermind_core.runtime.event_bus import EventBus

class TaskManager:
    def __init__(self, event_bus: Optional[EventBus] = None):
        self.event_bus = event_bus

    def create_task(self, persona_id: UUID, goal: str) -> Task:
        task = Task(persona_id=persona_id, goal=goal)
        
        if self.event_bus:
            self.event_bus.emit("EntityMutated", {
                "entity_type": "Task",
                "entity_id": task.id,
                "new_value": task.model_dump(mode="json"),
                "actor": str(persona_id)
            })
            
        return task
