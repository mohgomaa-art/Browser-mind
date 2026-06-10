from typing import Callable, Dict, List, Any

class EventBus:
    """
    The central Pub/Sub bus for BrowserMind.
    Enforces decoupled communication between Managers, Ledgers, and Services.
    """
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type: str, callback: Callable):
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)

    def emit(self, event_type: str, payload: Any):
        if event_type in self.subscribers:
            for callback in self.subscribers[event_type]:
                callback(payload)
