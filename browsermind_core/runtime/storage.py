import json
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from uuid import UUID

class StorageProvider(ABC):
    @abstractmethod
    def save_checkpoint(self, entity_id: UUID, entity_type: str, state: Dict[str, Any]):
        pass

    @abstractmethod
    def load_checkpoint(self, entity_id: UUID, entity_type: str) -> Optional[Dict[str, Any]]:
        pass


class LocalJSONStorageProvider(StorageProvider):
    """
    A simple JSON-based storage provider for local persistence.
    Used for P0.5 - P0.8 to prove the Execution Engine can survive a crash.
    """
    def __init__(self, storage_dir: str = ".browsermind_store"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    def _get_file_path(self, entity_id: UUID, entity_type: str) -> str:
        return os.path.join(self.storage_dir, f"{entity_type}_{entity_id}.json")

    def save_checkpoint(self, entity_id: UUID, entity_type: str, state: Dict[str, Any]):
        file_path = self._get_file_path(entity_id, entity_type)
        with open(file_path, "w") as f:
            json.dump(state, f)

    def load_checkpoint(self, entity_id: UUID, entity_type: str) -> Optional[Dict[str, Any]]:
        file_path = self._get_file_path(entity_id, entity_type)
        if not os.path.exists(file_path):
            return None
        with open(file_path, "r") as f:
            return json.load(f)
