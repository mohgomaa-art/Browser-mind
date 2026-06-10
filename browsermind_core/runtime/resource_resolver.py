import json
import re
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider
from browsermind_core.runtime.auth_session import AuthSession
from browsermind_core.ontology.p1_schemas import WorkflowInstance

class RuntimeInterrupt(Exception):
    """Base class for runtime interruptions that are neither execution failures nor policy denials."""
    pass

from browsermind_core.runtime.acquisition_runtime import AcquisitionRuntime, ResourceRequest
from browsermind_core.ontology.resource_ontology import ResourceClassifier

class ResourceMissingError(RuntimeInterrupt):
    """Raised when an explicit resource binding cannot be resolved."""
    def __init__(self, resource_key: str):
        super().__init__(f"Missing required resource: {resource_key}")
        self.resource_key = resource_key

class ResourceResolver:
    """
    WR-1 Resource Resolution.
    Resolves workflow parameters, credentials, and OTP tokens dynamically.
    Fulfills resource isolation by querying the Persona-specific vault inside the persistence layer.
    """
    def __init__(self, auth_session: AuthSession):
        self.auth_session = auth_session
        self.total_resources_required = 0
        self.total_resources_resolved = 0
        self._vault_data = None
        self.acquisition_runtime = AcquisitionRuntime(self)
        self.acquisition_runtime.load_effectiveness(str(self.auth_session.store_dir))
        self.last_acquisition_result = None

    def _get_vault_data(self) -> dict:
        if self._vault_data is None:
            try:
                provider = LocalJSONPersistenceProvider(str(self.auth_session.store_dir))
                # 1. Load by exact persona name
                data = provider.load("persona_vault", self.auth_session.persona_name)
                if not data:
                    # 2. Load by lowercase persona name
                    data = provider.load("persona_vault", self.auth_session.persona_name.lower())
                self._vault_data = data or {}
            except Exception as e:
                print(f"  [ResourceResolver] Failed to load persona vault: {e}")
                self._vault_data = {}
        return self._vault_data

    async def resolve_input(self, step: Dict[str, Any], instance: WorkflowInstance) -> Any:
        val = step.get("default_value")
        binding = step.get("input_binding")
        
        # Determine if a resource is required
        action_type = step.get("action_type", "")
        # Usually input fields are filled with "fill" or "type" or "press" (if passing a key)
        # But we only count it as a required resource if there is an input_binding or if it fills an input
        is_resource_req = (binding is not None) or (action_type in ("fill", "type"))
        
        if is_resource_req:
            self.total_resources_required += 1

        resolved_val = None
        self.last_acquisition_result = None

        if binding:
            b_key = binding.get("key", "")
            
            # P7C: Use AcquisitionRuntime
            cap_hint = step.get("descriptor", {}).get("capability_hint", "")
            role = step.get("target_role", "")
            r_class = ResourceClassifier.classify(
                resource_key=b_key,
                resource_binding=binding,
                capability_hint=cap_hint,
                workflow_role=role
            )
            
            req = ResourceRequest(resource_key=b_key, resource_class=r_class)
            result = await self.acquisition_runtime.acquire(req)
            self.last_acquisition_result = result
            resolved_val = result.value

        # Fallback to default_value if not resolved by binding
        if resolved_val is None:
            resolved_val = val
            
        # If binding was provided and we still have no value, it is missing
        if binding and resolved_val is None:
            raise ResourceMissingError(b_key)

        if is_resource_req:
            if resolved_val is not None:
                self.total_resources_resolved += 1
            else:
                # Try to see if default value can count as resolved
                if val is not None:
                    self.total_resources_resolved += 1
                    resolved_val = val

        return resolved_val

    def _resolve_from_vault(self, b_key: str, name_lower: str) -> Optional[Any]:
        vault = self._get_vault_data()
        site_key = self.auth_session.entry.key
        
        # 1. Search under environment-specific secrets
        secrets = vault.get("secrets", {}).get(site_key, {})
        if b_key in secrets:
            return secrets[b_key]
        if b_key.lower() in secrets:
            return secrets[b_key.lower()]
        if name_lower in secrets:
            return secrets[name_lower]
            
        # 2. Search under environment-specific resources
        resources = vault.get("resources", {}).get(site_key, {})
        if b_key in resources:
            return resources[b_key]
        if b_key.lower() in resources:
            return resources[b_key.lower()]
        if name_lower in resources:
            return resources[name_lower]

        # 3. Fallback to generic vault mapping
        for key in [b_key, b_key.lower(), name_lower]:
            if key in vault.get("secrets", {}):
                return vault["secrets"][key]
            if key in vault.get("resources", {}):
                return vault["resources"][key]
                
        # 4. Fallback to general password check
        if "password" in name_lower or "password" in b_key.lower():
            # If there's a password in environment secrets
            for key, val in secrets.items():
                if "password" in key.lower():
                    return val
            # If there's a password in top-level secrets
            for key, val in vault.get("secrets", {}).items():
                if "password" in key.lower():
                    return val
                    
        return None

    def get_resolution_rate(self) -> float:
        if self.total_resources_required == 0:
            return 100.0
        return round((self.total_resources_resolved / self.total_resources_required) * 100.0, 2)
