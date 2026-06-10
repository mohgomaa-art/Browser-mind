"""
P0.5 — PersistenceProvider
Generic persistence interface. Technology-agnostic.
All Repositories sit above this layer; nothing below it knows about Execution or Persona.
"""
import json
import os
import hashlib
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from uuid import UUID


class PersistenceProvider(ABC):
    """
    The generic storage contract.
    Knows nothing about BrowserMind entities.
    Can be backed by SQLite, Postgres, S3, or filesystem.
    """

    @abstractmethod
    def save(self, namespace: str, key: str, data: Dict[str, Any]):
        pass

    @abstractmethod
    def load(self, namespace: str, key: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def delete(self, namespace: str, key: str):
        pass

    @abstractmethod
    def list_keys(self, namespace: str) -> List[str]:
        pass


class LocalJSONPersistenceProvider(PersistenceProvider):
    """
    File-based JSON persistence for local development and testing.
    Each namespace maps to a subdirectory.
    """

    def __init__(self, storage_dir: str = ".browsermind_store"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    def _get_path(self, namespace: str, key: str) -> str:
        ns_dir = os.path.join(self.storage_dir, namespace)
        os.makedirs(ns_dir, exist_ok=True)
        return os.path.join(ns_dir, f"{key}.json")

    def _checksum(self, data: Dict[str, Any]) -> str:
        raw = json.dumps(data, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def save(self, namespace: str, key: str, data: Dict[str, Any]):
        payload = {
            "_checksum": self._checksum(data),
            "_data": data,
        }
        file_path = self._get_path(namespace, key)
        # Atomic write: write to temp file, then rename to avoid partial writes
        tmp_path = file_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        for attempt in range(5):
            try:
                os.replace(tmp_path, file_path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))

    def load(self, namespace: str, key: str) -> Optional[Dict[str, Any]]:
        file_path = self._get_path(namespace, key)
        if not os.path.exists(file_path):
            return None
        with open(file_path, "r") as f:
            payload = json.load(f)

        # Integrity check: reject corrupted files
        expected = payload.get("_checksum")
        actual = self._checksum(payload["_data"])
        if expected != actual:
            return None  # Corrupted — caller decides fallback strategy

        return payload["_data"]

    def delete(self, namespace: str, key: str):
        file_path = self._get_path(namespace, key)
        if os.path.exists(file_path):
            os.remove(file_path)

    def list_keys(self, namespace: str) -> List[str]:
        ns_dir = os.path.join(self.storage_dir, namespace)
        if not os.path.exists(ns_dir):
            return []
        return [f.replace(".json", "") for f in os.listdir(ns_dir) if f.endswith(".json")]
