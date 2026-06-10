from PySide6.QtCore import QObject, Signal
from browsermind_core.console.session import KernelSession, DEFAULT_STORE

class StateNotifier(QObject):
    """
    Qt Signal emitter. Bound to the Kernel EventBus.
    """
    entity_mutated = Signal(str, str)  # (entity_type, entity_id)

class AppContext:
    """
    Dependency Injection container for the OS.
    Holds the KernelSession and forwards events to the UI via StateNotifier.
    """
    def __init__(self, store_dir: str = DEFAULT_STORE):
        self.session = KernelSession(store_dir)
        self.notifier = StateNotifier()
        
        # Subscribe to Kernel events
        self.session.event_bus.subscribe("EntityMutated", self._on_kernel_mutation)

    def _on_kernel_mutation(self, payload: dict):
        # We bounce the event to Qt's event loop via the notifier
        entity_type = payload.get("entity_type", "")
        entity_id = payload.get("entity_id", "")
        self.notifier.entity_mutated.emit(entity_type, str(entity_id))

    def get_index(self, entity_type: str) -> dict:
        """Helper to get full named index"""
        return self.session._load_index(entity_type)
