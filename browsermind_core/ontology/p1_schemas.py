from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Literal
from datetime import datetime, timezone
from uuid import UUID, uuid4

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

# -----------------------------------------------------------------------------
# Base Entity
# -----------------------------------------------------------------------------
class BaseEntity(BaseModel):
    """Common fields for all BrowserMind ontology entities."""
    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

# =============================================================================
# 1. PRINCIPAL LEVEL (The External Owner)
# =============================================================================

class Principal(BaseEntity):
    """The external entity that owns the account and pays for the compute."""
    name: str = Field(..., description="Name of the user, team, or organization")
    principal_type: Literal["user", "organization", "team", "api_client"]
    billing_id: Optional[str] = None

# =============================================================================
# 2. SYSTEM LEVEL (The Global Engine)
# =============================================================================

class Environment(BaseEntity):
    """The target domain execution context (e.g., LinkedIn, Greenhouse)."""
    domain: str = Field(..., description="The base domain or app identifier")
    risk_level: Literal["low", "medium", "high", "extreme"]
    anti_bot_active: bool = False
    requires_auth: bool = False

class Capability(BaseEntity):
    """The immutable primitive (e.g., Upload, Checkout)."""
    name: str
    description: str

class WorkflowTemplate(BaseEntity):
    """The generic procedural abstraction (e.g., Apply to Greenhouse)."""
    name: str
    description: str
    required_capabilities: List[UUID] = Field(default_factory=list, description="IDs of required capabilities")
    steps: List[Dict[str, Any]] = Field(default_factory=list, description="Compiled semantic steps")
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ProceduralMemory(BaseEntity):
    """The System's shared knowledge graph of how things operate."""
    memory_type: Literal["environment", "capability", "workflow"]
    target_id: UUID = Field(..., description="References an Environment, Capability, or WorkflowTemplate")
    knowledge: str = Field(..., description="The procedural fact (e.g., 'Requires bypassing hidden inputs')")
    metadata: Dict[str, Any] = Field(default_factory=dict)

# =============================================================================
# 3. PERSONA LEVEL (The Context Boundary)
# =============================================================================

class Persona(BaseEntity):
    """The absolute sandboxed context. Nothing crosses this line during execution."""
    principal_id: UUID = Field(..., description="The Principal that owns this Persona")
    name: str = Field(..., description="e.g., 'AI Founder', 'Medical Student'")
    description: Optional[str] = None

class Identity(BaseEntity):
    """Authenticated states belonging to a Persona."""
    persona_id: UUID
    environment_id: UUID = Field(..., description="The Environment this identity applies to")
    identifier: str
    status: Literal["active", "expired", "revoked", "requires_2fa"] = "active"

class Secret(BaseEntity):
    """Ephemeral or persistent credentials for an Identity."""
    identity_id: UUID
    secret_type: Literal["password", "token", "cookie_jar", "oauth_state"]
    encrypted_value: str
    expires_at: Optional[datetime] = None

class Resource(BaseEntity):
    """Files, URLs, or Structured Data belonging to a Persona."""
    persona_id: UUID
    resource_type: Literal["file", "url", "structured_data"]
    name: str
    uri_or_content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Preference(BaseEntity):
    """Biases and weights specific to the Persona."""
    persona_id: UUID
    key: str
    value: Any
    weight: float = 1.0

class TrustPolicy(BaseEntity):
    """RBAC rules applied hierarchically for this Persona."""
    persona_id: UUID
    target_type: Literal["capability", "workflow_template"]
    target_id: UUID = Field(..., description="ID of the Capability or WorkflowTemplate")
    authority_level: Literal["auto", "ask", "never"]

class WorkflowInstance(BaseEntity):
    """The Persona's personalized, parameterized version of a global template."""
    persona_id: UUID
    template_id: UUID = Field(..., description="References a System WorkflowTemplate")
    bound_resources: Dict[str, UUID] = Field(description="e.g., {'resume': resource_id}")
    bound_identities: Dict[str, UUID] = Field(description="e.g., {'linkedin': identity_id}")

class Task(BaseEntity):
    """The concrete goals defined by the Persona."""
    persona_id: UUID
    goal: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"

class SemanticMemory(BaseEntity):
    """Deduced facts specific to the Persona."""
    persona_id: UUID
    fact: str = Field(..., description="e.g., 'Prefers remote jobs over onsite'")
    confidence: float = 1.0

# =============================================================================
# 4. EXECUTION LEVEL (The State Machine)
# =============================================================================

class ExecutionContext(BaseModel):
    """The frozen snapshot of all IDs required to resume a real Workflow."""
    persona_id: UUID
    task_id: UUID
    workflow_instance_id: UUID
    template_id: Optional[UUID] = None
    identity_id: Optional[UUID] = None
    environment_id: Optional[UUID] = None

class Execution(BaseEntity):
    """The active state machine running a Workflow Instance."""
    task_id: UUID
    workflow_instance_id: UUID
    status: Literal["running", "paused", "forked", "succeeded", "failed", "rollback"] = "running"
    approval_level: Literal["auto", "ask", "never"] = Field(
        ..., description="Resolved authority level based on Persona's Trust Policies"
    )
    failure_reason: Optional[str] = None
    retry_count: int = 0
    context: Optional[ExecutionContext] = None

class Snapshot(BaseEntity):
    """Git-like state captures allowing Pause, Resume, Fork, and Rollback."""
    execution_id: UUID
    snapshot_hash: str
    dom_state_uri: str
    browser_context_uri: str
    is_point_of_no_return: bool = False

class SnapshotRecord(BaseEntity):
    """
    P0.5: A persisted, sequenced checkpoint of Execution state.
    Used for Rollback, Diff, Audit, and Replay.
    """
    execution_id: UUID
    sequence: int = Field(..., description="Monotonically increasing sequence number")
    execution_state: Dict[str, Any] = Field(..., description="Full serialized Execution state at this checkpoint")
    is_valid: bool = True

class EpisodicMemory(BaseEntity):
    """The historical log of what happened during an Execution."""
    execution_id: UUID
    event_description: str
    timestamp: datetime = Field(default_factory=utc_now)
    outcome: Literal["success", "failure", "neutral"]

# =============================================================================
# 5. P4C — STATE VERIFICATION SCHEMAS
# =============================================================================

class StateEvidence(BaseModel):
    """
    Raw observable signals collected from the DOM after workflow execution.
    These are facts about what was visible — NOT opinions about what state was reached.
    The same evidence can be re-inferred later without re-running the replay.
    """
    signals: List[str] = Field(default_factory=list)  # e.g. ["logout_button_visible", "avatar_present"]
    url_pattern: str = ""                              # e.g. "/dashboard" or full URL
    page_title: str = ""
    observed_at: datetime = Field(default_factory=utc_now)


class StateInference(BaseModel):
    """
    The semantic state inferred from a StateEvidence observation.
    Separates the act of observing (Evidence) from the act of concluding (Inference).
    Rules may be updated without re-running replay — just re-infer from stored evidence.
    """
    inferred_state: str       # e.g. "authenticated", "checkout_complete"
    expected_state: str       # e.g. "authenticated" — what the workflow was supposed to achieve
    confidence: float = 1.0   # 0.0-1.0
    evidence: StateEvidence
    match: bool               # True if inferred_state == expected_state


class EnvironmentFingerprint(BaseModel):
    """
    A snapshot of the observable environment at replay time.
    Enables distinguishing between two failure causes:
      1. Workflow died   → resolution_rate dropped + fingerprint identical
      2. Environment changed → resolution_rate dropped + fingerprint changed
    """
    dom_hash: str = ""                               # hash of page.content()
    url_signature: str = ""                          # normalized URL (tokens stripped)
    role_distribution: Dict[str, int] = Field(default_factory=dict)  # {"button": 12, "textbox": 3}
    element_count: int = 0
    captured_at: datetime = Field(default_factory=utc_now)


# =============================================================================
# 6. P3.1 — REPLAYABILITY PREDICTION SYSTEM
# =============================================================================

class TargetDescriptor(BaseModel):
    """
    Immutable semantic facts extracted from the DOM at interaction time.
    Contains NO opinions, NO computed scores.
    """
    role: str = ""
    name: str = ""
    accessible_name: str = ""   # aria-label or computed accessible name
    text_content: str = ""      # visible innerText of the element
    placeholder: str = ""       # input placeholder attribute
    dom_path: str = ""          # tagName chain for structural context


class RecordingEvidence(BaseModel):
    """
    Transient DOM state captured at recording time.
    This is a snapshot of page conditions, NOT a property of the target itself.
    The same target may have candidate_count=1 today and 3 tomorrow.
    """
    candidate_count: int = 0    # How many elements matched role+name at recording time
    page_url: str = ""
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReplayabilityAssessment(BaseModel):
    """
    The Analyzer's prediction about whether a step can survive replay.
    This is an algorithmic opinion, not a fact. Scoring rules may change over time.
    Deliberately kept to simple deterministic rules until we have a real dataset.
    """
    tier: Literal["HIGH", "AMBIGUOUS", "UNREPLAYABLE"]
    score: float                # 0.0 to 1.0 — higher is more replayable
    reasons: List[str]          # machine-readable signals, e.g. ["missing_name", "generic_role"]


class FailureAttribution(BaseModel):
    """
    The comparison of a step's predicted replayability vs its actual outcome.
    This is the golden data: it teaches us when our predictions are wrong.

    Representation Ledger fields:
      resolved_by: what representation ultimately succeeded (set on every step that resolved)
      recovered_by: which fallback strategy was used AFTER an initial failure

    Together these answer: "When replay succeeds, what representation actually saved it?"
    """
    step_seq: int
    action_type: str
    role: str
    name: str
    predicted_tier: str         # The ReplayabilityAssessment tier at compile time
    predicted_score: float
    actual_outcome: Literal["SUCCESS", "FAILED", "TRANSITION_SUCCESS", "AMBIGUOUS_IDENTITY", "ASK", "BOT_DETECTED"]  # What actually happened during replay
    failure_reason: Optional[str] = None
    resolved_by: Optional[str] = None   # P4C Representation Ledger: how resolution succeeded
    recovered_by: Optional[str] = None  # which fallback was used after initial failure
    resolution_depth: Optional[int] = None  # 0=primary_semantic, 1=placeholder, 2=nearby_text, 3=structural_path
    
    # 4-Layer Execution Probes
    resolution_success: Optional[bool] = None
    execution_success: Optional[bool] = None
    effect_verified: Optional[bool] = None
    effect_type: Optional[str] = None
    effect_details: Optional[Dict[str, Any]] = None
    failure_layer: Optional[str] = None
    target_integrity: Optional[Dict[str, Any]] = None
    resolution_time_ms: Optional[int] = None
    resolution_candidate_scans: int = 0
    resolution_passes: int = 0
    resolution_latency_ms: Optional[int] = None
    vault_resolution_path: Optional[str] = None
    step_duration_ms: Optional[int] = None
    inter_step_delay_ms: Optional[int] = None
    quality_score: Optional[float] = None   # EffectVerdict.quality_score (0-1)

    # Semantic state before and after this step (SemanticState.to_dict())
    semantic_state_before: Optional[Dict[str, Any]] = None
    semantic_state_after: Optional[Dict[str, Any]] = None


class ReplayReport(BaseModel):
    """
    Full execution report with per-step attribution.
    The failure_attribution list is the primary output of P3.1.
    """
    workflow_id: UUID
    template_id: UUID
    status: Literal["SUCCESS", "FAILED", "INTERRUPTED", "BLOCKED"] = "SUCCESS"
    total_steps: int = 0
    resolved_steps: int = 0
    failed_steps: int = 0
    ambiguous_steps: int = 0          # P4E: steps that hit AMBIGUOUS_IDENTITY
    resolution_rate: float = 0.0
    ambiguity_rate: float = 0.0       # P4E: ambiguous_steps / total_steps
    resource_resolution_rate: float = 0.0
    recovery_rate: Optional[float] = None
    duration_seconds: float = 0.0
    failure_reason: Optional[str] = None
    missing_resource: Optional[str] = None
    provenance: Optional[Dict[str, Any]] = None
    # P3.1: Per-step attribution for prediction vs actual comparison
    failure_attribution: List[FailureAttribution] = Field(default_factory=list)

    # P4C: State Achievement Verification (Evidence → Inference → State)
    state_inference: Optional[StateInference] = None

    # Phase 1 Evidence Sprint: State Verification Audit
    verification_report: Optional[dict] = None
    # Captures verifier failures so the absence of `verification_report`
    # is distinguishable from a silent crash. Shape: {"type", "message", "traceback"}.
    verification_error: Optional[Dict[str, str]] = None

    # ContractVerifier: runtime "did the goal complete?" check.
    # Shape matches ContractVerifier.verify() return: goal_completed,
    # success_contract, contract_evidence, validator_result.
    contract_verification: Optional[Dict[str, Any]] = None

    # P4C: Environment Fingerprints (start + end of replay)
    env_fingerprint_start: Optional[EnvironmentFingerprint] = None
    env_fingerprint_end: Optional[EnvironmentFingerprint] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
