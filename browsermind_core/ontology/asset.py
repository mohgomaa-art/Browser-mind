# browsermind_core/ontology/asset.py
"""Asset Ontology — Models asset types and their relationships in an Asset Graph."""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class StateClass(str, Enum):
    """
    Classifies a produces_state token by what it guarantees.

    OBSERVATION  — the state means "this place can be inspected".
                   The target resource may or may not exist there.
                   Example: email.opened  (email is open, but OTP may not be in it)

    AVAILABILITY — the state means "this resource exists and is accessible".
                   The target resource is guaranteed to be present.
                   Example: vault.otp_generated  (OTP was generated and is in the vault)
    """
    OBSERVATION  = "observation"
    AVAILABILITY = "availability"


class TrustTier(int, Enum):
    """
    Classifies the inherent trust level of an environment or data source.
    Higher values indicate greater determinism, privacy, and reliability.
    """
    LOW    = 10   # e.g., web search results, unauthenticated public pages
    MEDIUM = 50   # e.g., email inbox (can contain spam, delayed delivery)
    HIGH   = 100  # e.g., credential vault, hardware token (deterministic, secure)


class Persona(BaseModel):
    """User persona profile."""
    name: str
    description: Optional[str] = None


class AssetOwnership(BaseModel):
    """Explicit ownership mapping between Persona and AssetInstance."""
    persona_name: str
    asset_instance_name: str


class AssetType(BaseModel):
    """Abstract classification of resources (e.g. email_account, credential_asset)."""
    name: str  # e.g. "email_account", "payment_asset"
    description: Optional[str] = None


class AssetInstance(BaseModel):
    """Specific instance of an AssetType (e.g. gmail_primary, outlook_work)."""
    name: str
    asset_type: str  # Name of AssetType it represents
    environment: str  # Name/ID of the host Environment
    description: Optional[str] = None
    canonical_name: str = ""
    aliases: List[str] = []


class Environment(BaseModel):
    """Host environment for an asset (e.g. gmail, outlook, vault, stripe)."""
    id: str
    kind: str  # e.g. "email_client", "wallet", "secrets_manager", "portal"
    trust_tier: TrustTier = TrustTier.LOW
    url: Optional[str] = None
    description: Optional[str] = None
    aliases: List[str] = []


class Capability(BaseModel):
    """Represents an execution capability supported by an Environment."""
    name: str  # e.g., "read_email", "retrieve_credential"
    description: Optional[str] = None
    inputs: List[str]  # e.g. ["email_account"] (Asset instances required)
    outputs: List[str]  # e.g. ["email_content"] (Data artifacts produced)
    consumes_state: List[str] = [] # e.g. ["email.selected"] (Pre-condition execution states)
    produces_state: List[str] = [] # e.g. ["email.opened"] (Post-condition execution states)


class AssetGraph:
    """Directed Graph representing Goal -> Flows -> Requirements -> Asset Types."""

    def __init__(self):
        self.nodes: Dict[str, Dict[str, Any]] = {}  # name -> {type, metadata}
        self.edges: List[tuple[str, str, str]] = []  # (source, target, relation)

    def add_node(self, name: str, node_type: str, metadata: Optional[Dict[str, Any]] = None):
        self.nodes[name] = {
            "type": node_type,
            "metadata": metadata or {}
        }

    def add_edge(self, source: str, target: str, relation: str):
        self.edges.append((source, target, relation))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": self.nodes,
            "edges": [
                {"source": e[0], "target": e[1], "relation": e[2]}
                for e in self.edges
            ]
        }
