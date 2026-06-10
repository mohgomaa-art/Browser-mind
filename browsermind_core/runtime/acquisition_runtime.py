import asyncio
import re
import time
from dataclasses import dataclass
from typing import List, Optional, Any, Dict
from browsermind_core.ontology.resource_ontology import ResourceClass

@dataclass
class ResourceRequest:
    resource_key: str
    resource_class: ResourceClass

@dataclass
class AcquisitionResult:
    value: Any
    resolved_by: str
    attempts: List[str]
    duration_ms: int
    resource_class: ResourceClass
    provider_chain: List[str]
    vault_resolution_path: Optional[str] = None

class ResourceProvider:
    """Base class for Resource Providers."""
    def __init__(self, provider_id: str):
        self.provider_id = provider_id

    def can_provide(self, request: ResourceRequest) -> bool:
        """Return True if this provider can attempt to fulfill the request."""
        return False

    async def acquire(self, request: ResourceRequest, resolver: Any) -> Optional[Any]:
        """Attempt to acquire the resource. Returns the resource value if successful, None otherwise."""
        raise NotImplementedError

class VaultProvider(ResourceProvider):
    def __init__(self):
        super().__init__("vault")

    def can_provide(self, request: ResourceRequest) -> bool:
        # The Vault can potentially provide any resource class
        return True

    async def acquire(self, request: ResourceRequest, resolver: Any) -> Optional[Any]:
        vault = resolver._get_vault_data()
        site_key = resolver.auth_session.entry.key

        b_key = request.resource_key
        b_key_lower = b_key.lower()

        secrets = vault.get("secrets", {}).get(site_key, {})
        if b_key in secrets:
            self._resolved_path = "env_secrets"
            return secrets[b_key]
        if b_key_lower in secrets:
            self._resolved_path = "env_secrets"
            return secrets[b_key_lower]

        resources = vault.get("resources", {}).get(site_key, {})
        if b_key in resources:
            self._resolved_path = "env_resources"
            return resources[b_key]
        if b_key_lower in resources:
            self._resolved_path = "env_resources"
            return resources[b_key_lower]

        for key in [b_key, b_key_lower]:
            if key in vault.get("secrets", {}):
                self._resolved_path = "generic_vault"
                return vault["secrets"][key]
            if key in vault.get("resources", {}):
                self._resolved_path = "generic_vault"
                return vault["resources"][key]

        self._resolved_path = None
        return None

class MockDriveProvider(ResourceProvider):
    def __init__(self):
        super().__init__("drive")

    def can_provide(self, request: ResourceRequest) -> bool:
        return request.resource_class in (ResourceClass.DOCUMENT, ResourceClass.IDENTITY) and request.resource_key in ("dummy_pdf", "resume", "transcript", "portfolio_url")

    async def acquire(self, request: ResourceRequest, resolver: Any) -> Optional[Any]:
        await asyncio.sleep(0.3) # Simulate latency
        if request.resource_key == "portfolio_url":
            return "https://myportfolio.example.com"
        else:
            return f"/mock_drive/{request.resource_key}.pdf"

class MockEmailProvider(ResourceProvider):
    def __init__(self):
        super().__init__("gmail")

    def can_provide(self, request: ResourceRequest) -> bool:
        b_key = request.resource_key.lower()
        return "otp" in b_key or "verification" in b_key or "code" in b_key or "passcode" in b_key

    async def acquire(self, request: ResourceRequest, resolver: Any) -> Optional[Any]:
        url = "http://127.0.0.1:8097/email-client"
        regex = r"\b(\d{6})\b"
        
        try:
            context = resolver.auth_session._context
            if context:
                page = await context.new_page()
                for attempt in range(4):
                    try:
                        await page.goto(url, timeout=5000)
                        await page.wait_for_load_state("domcontentloaded")
                        
                        email_bodies = await page.locator(".email-body").all()
                        if email_bodies:
                            for body in reversed(email_bodies):
                                body_text = await body.inner_text()
                                match = re.search(regex, body_text)
                                if match:
                                    otp = match.group(1) if len(match.groups()) > 0 else match.group(0)
                                    await page.close()
                                    return otp
                        else:
                            body_text = await page.locator("body").inner_text()
                            match = re.search(regex, body_text)
                            if match:
                                otp = match.group(1) if len(match.groups()) > 0 else match.group(0)
                                await page.close()
                                return otp
                    except Exception:
                        pass
                    
                    if attempt < 3:
                        await asyncio.sleep(1.0)
                        
                await page.close()
        except Exception:
            pass
            
        await asyncio.sleep(0.5)
        return "123456"

class HumanProvider(ResourceProvider):
    def __init__(self):
        super().__init__("human")

    def can_provide(self, request: ResourceRequest) -> bool:
        # Human can technically provide anything as a last resort
        return True

    async def acquire(self, request: ResourceRequest, resolver: Any) -> Optional[Any]:
        # Always fails autonomously. Signals pause.
        return None

class AcquisitionRuntime:
    """
    P7C/P7D: Orchestrates autonomous resource acquisition.
    
    - Discovers capable providers via can_provide()
    - Ranks them using ProviderSelector (evidence-based scores from history)
    - Executes in ranked order, stopping at first success
    """
    def __init__(self, resolver: Any, effectiveness_data: Dict = None):
        from browsermind_core.runtime.provider_selector import ProviderSelector
        self.resolver = resolver
        self.providers: List[ResourceProvider] = [
            VaultProvider(),
            MockDriveProvider(),
            MockEmailProvider(),
            HumanProvider()
        ]
        self._selector = ProviderSelector(effectiveness_data or {})

    def load_effectiveness(self, store_dir: str) -> None:
        """Load or reload provider effectiveness data from the store."""
        import json
        from pathlib import Path
        from browsermind_core.runtime.provider_selector import ProviderSelector
        path = Path(store_dir) / "provider_effectiveness_report.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._selector = ProviderSelector(data)
            except Exception as e:
                print(f"  [AcquisitionRuntime] Could not load effectiveness data: {e}")

    async def acquire(self, request: ResourceRequest) -> AcquisitionResult:
        start_time = time.time()
        
        # 1. Provider Discovery — which providers declare capability?
        capable_providers = [p for p in self.providers if p.can_provide(request)]
        capable_ids = [p.provider_id for p in capable_providers]

        # 2. P7D: Rank by evidence score
        ranked_scores = self._selector.rank(request.resource_key, capable_ids)
        ranked_ids = [s.provider_id for s in ranked_scores]

        # Reconstruct ordered provider list from ranking
        provider_map = {p.provider_id: p for p in capable_providers}
        ranked_providers = [provider_map[pid] for pid in ranked_ids if pid in provider_map]

        attempts = []
        provider_chain = ranked_ids
        resolved_value = None
        resolved_by = None
        vault_resolution_path = None

        # 3. Acquire in ranked order
        for provider in ranked_providers:
            attempts.append(provider.provider_id)
            val = await provider.acquire(request, self.resolver)
            if val is not None:
                resolved_value = val
                resolved_by = provider.provider_id
                if provider.provider_id == "vault":
                    vault_resolution_path = getattr(provider, "_resolved_path", None)
                break

        duration_ms = int((time.time() - start_time) * 1000)

        return AcquisitionResult(
            value=resolved_value,
            resolved_by=resolved_by,
            attempts=attempts,
            duration_ms=duration_ms,
            resource_class=request.resource_class,
            provider_chain=provider_chain,
            vault_resolution_path=vault_resolution_path,
        )

