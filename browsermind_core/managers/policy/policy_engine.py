import json
from pathlib import Path
from typing import Dict, Optional, Tuple
from uuid import UUID


class PolicyEngine:
    """
    Runtime ABAC Engine with persistent storage.

    Policies survive process restarts. Zero-trust default ("ask") still applies
    to any (persona_id, target_id) pair that has not been explicitly configured.
    """

    def __init__(self, store_path: Optional[Path] = None):
        # In-memory store: (str(persona_id), str(target_id)) -> authority_level
        self._policies: Dict[Tuple[str, str], str] = {}
        self._path: Optional[Path] = (
            Path(store_path) / "policies.json" if store_path else None
        )
        self._load()

    # ------------------------------------------------------------------ I/O --

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._policies = {
                (entry["persona_id"], entry["target_id"]): entry["authority_level"]
                for entry in data
            }
        except Exception:
            # Corrupt file — start fresh; do not crash startup
            self._policies = {}

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {"persona_id": pid, "target_id": tid, "authority_level": level}
            for (pid, tid), level in self._policies.items()
        ]
        self._path.write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    # --------------------------------------------------------------- Public --

    def set_policy(
        self, persona_id: UUID, target_id: UUID, authority_level: str
    ) -> None:
        self._policies[(str(persona_id), str(target_id))] = authority_level
        self._save()

    def evaluate(self, persona_id: UUID, target_id: UUID) -> str:
        return self._policies.get(
            (str(persona_id), str(target_id)), "ask"
        )

    def remove_policy(self, persona_id: UUID, target_id: UUID) -> None:
        self._policies.pop((str(persona_id), str(target_id)), None)
        self._save()

    def list_policies(self) -> list:
        return [
            {"persona_id": pid, "target_id": tid, "authority_level": lvl}
            for (pid, tid), lvl in self._policies.items()
        ]
