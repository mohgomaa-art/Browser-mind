"""Persist WorkflowTemplate + WorkflowInstance (P1 — index + JSON blobs)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from browsermind_core.ontology.p1_schemas import WorkflowInstance, WorkflowTemplate
from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider


class WorkflowStore:
    NS_TEMPLATE = "workflow_template"
    NS_INSTANCE = "workflow_instance"
    IDX_TEMPLATE = "_workflow_template_index.json"
    IDX_INSTANCE = "_workflow_instance_index.json"

    def __init__(self, store_dir: str):
        self.store_dir = store_dir
        os.makedirs(store_dir, exist_ok=True)
        self.provider = LocalJSONPersistenceProvider(store_dir)

    def _idx_path(self, kind: str) -> str:
        name = self.IDX_TEMPLATE if kind == "template" else self.IDX_INSTANCE
        return os.path.join(self.store_dir, name)

    def _load_idx(self, kind: str) -> Dict[str, Any]:
        path = self._idx_path(kind)
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _save_idx(self, kind: str, idx: Dict[str, Any]):
        with open(self._idx_path(kind), "w", encoding="utf-8") as f:
            json.dump(idx, f, indent=2)

    def create_template(
        self,
        name: str,
        description: str = "",
        family_key: str = "",
        required_capabilities: Optional[List[UUID]] = None,
    ) -> WorkflowTemplate:
        idx = self._load_idx("template")
        if name in idx:
            raise ValueError(f"Template with name '{name}' already exists in store. Template names must be unique to prevent store pollution.")
        tpl = WorkflowTemplate(
            name=name,
            description=description or f"Template for {family_key or name}",
            required_capabilities=required_capabilities or [],
        )
        payload = tpl.model_dump(mode="json")
        payload["family_key"] = family_key
        self.provider.save(self.NS_TEMPLATE, str(tpl.id), payload)
        idx[name] = {"id": str(tpl.id), "family_key": family_key}
        self._save_idx("template", idx)
        return tpl

    def create_instance(
        self,
        name: str,
        persona_id: UUID,
        template_id: UUID,
        bound_resources: Optional[Dict[str, UUID]] = None,
        bound_identities: Optional[Dict[str, UUID]] = None,
        *,
        environment_family: str = "",
        environment_instance: str = "",
        profile_path: str = "",
    ) -> WorkflowInstance:
        inst = WorkflowInstance(
            persona_id=persona_id,
            template_id=template_id,
            bound_resources=bound_resources or {},
            bound_identities=bound_identities or {},
        )
        payload = inst.model_dump(mode="json")
        payload["environment_family"] = environment_family
        payload["environment_instance"] = environment_instance
        payload["profile_path"] = profile_path
        self.provider.save(self.NS_INSTANCE, str(inst.id), payload)
        idx = self._load_idx("instance")
        idx[name] = {
            "id": str(inst.id),
            "template_id": str(template_id),
            "persona_id": str(persona_id),
            "family_key": environment_family,
        }
        self._save_idx("instance", idx)
        return inst

    def list_templates(self) -> List[Dict[str, Any]]:
        idx = self._load_idx("template")
        return [{"name": k, **v} for k, v in idx.items()]

    def list_instances(self) -> List[Dict[str, Any]]:
        idx = self._load_idx("instance")
        return [{"name": k, **v} for k, v in idx.items()]

    def lookup_template(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        idx = self._load_idx("template")
        if name_or_id in idx:
            return idx[name_or_id]
        for entry in idx.values():
            if entry["id"].startswith(name_or_id):
                return entry
        return None

    def lookup_instance(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        idx = self._load_idx("instance")
        if name_or_id in idx:
            return idx[name_or_id]
        for entry in idx.values():
            if entry["id"].startswith(name_or_id):
                return entry
        return None

    def get_template(self, template_id: UUID) -> Optional[WorkflowTemplate]:
        data = self.provider.load(self.NS_TEMPLATE, str(template_id))
        if not data:
            return None
        family_key = data.pop("family_key", None)
        tpl = WorkflowTemplate.model_validate(data)
        if family_key:
            tpl.metadata = tpl.metadata or {}
            tpl.metadata.setdefault("family_key", family_key)
        return tpl

    def find_by_capability(
        self,
        capability_key: str,
        site_key: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the index entry for the first template whose family_key or
        name matches *capability_key*, optionally filtered by *site_key*.

        Matching rules (checked in order):
        1. template.family_key == capability_key
        2. capability_key in template.family_key  (substring — e.g. "auth" in "auth_login")
        3. capability_key in template.name

        If *site_key* is given, preference is given to templates whose name
        contains *site_key* (site-specific templates win over generic ones).
        Returns None if no match is found.
        """
        idx = self._load_idx("template")
        candidates = []
        ck = capability_key.lower()
        for name, entry in idx.items():
            fk = (entry.get("family_key") or "").lower()
            nm = name.lower()
            if fk == ck or ck in fk or ck in nm:
                candidates.append((name, entry))

        if not candidates:
            return None

        if site_key:
            sk = site_key.lower()
            site_specific = [
                (n, e) for n, e in candidates if sk in n.lower()
            ]
            if site_specific:
                return {"name": site_specific[0][0], **site_specific[0][1]}

        return {"name": candidates[0][0], **candidates[0][1]}

    def get_instance(self, instance_id: UUID) -> Optional[WorkflowInstance]:
        data = self.provider.load(self.NS_INSTANCE, str(instance_id))
        if not data:
            return None
        side = {k: data.pop(k, None) for k in ("environment_family", "environment_instance", "profile_path")}
        inst = WorkflowInstance.model_validate(data)
        for k, v in side.items():
            if v:
                setattr(inst, "_" + k, v)
        return inst
