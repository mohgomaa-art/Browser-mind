import pytest
from uuid import uuid4

# We will implement these managers shortly to make the test pass
from browsermind_core.runtime.event_bus import EventBus
from browsermind_core.ledger.mutation_ledger import MutationLedger
from browsermind_core.managers.principal.principal_manager import PrincipalManager
from browsermind_core.managers.principal.persona_manager import PersonaManager
from browsermind_core.managers.identity.secret_vault import SecretVault
from browsermind_core.managers.identity.identity_service import IdentityService
from browsermind_core.managers.policy.policy_engine import PolicyEngine
from browsermind_core.runtime.task_manager import TaskManager
from browsermind_core.runtime.execution_engine import ExecutionEngine

def test_full_core_lifecycle():
    """
    Core Acceptance Test.
    This test verifies that the unbroken chain from Principal to Policy Check
    works securely without any cross-boundary mutations or shortcuts.
    """
    # 1. Initialize the Runtime Kernel
    event_bus = EventBus()
    ledger = MutationLedger(event_bus)
    
    # 2. Initialize the Managers (Dependency Injection to preserve boundaries)
    vault = SecretVault()
    identity_service = IdentityService(vault)
    principal_manager = PrincipalManager(event_bus)
    persona_manager = PersonaManager(event_bus)
    policy_engine = PolicyEngine()
    
    task_manager = TaskManager(event_bus)
    execution_engine = ExecutionEngine(event_bus, policy_engine)

    # 3. Create Principal & Persona
    principal = principal_manager.create_principal(name="John Doe", principal_type="user")
    assert principal.id is not None
    
    persona = persona_manager.create_persona(principal_id=principal.id, name="AI Founder")
    assert persona.id is not None

    # 4. Create Identity & Secret
    env_id = uuid4()
    identity = identity_service.provision_identity(
        persona_id=persona.id, 
        environment_id=env_id, 
        identifier="johndoe_github", 
        raw_secret="super_secret_password"
    )
    assert identity.id is not None
    
    # Verify Vault stored it without leaking plaintext.
    # SecretVault is real Fernet now — tokens start with "gAAAA" (Fernet v0x80 prefix, base64-urlsafe).
    secret = vault.get_secret_for_identity(identity.id)
    assert secret is not None
    assert "super_secret_password" not in secret.encrypted_value
    assert vault.decrypt(secret) == "super_secret_password"

    # 5. Policy setup
    workflow_template_id = uuid4()
    policy_engine.set_policy(persona_id=persona.id, target_id=workflow_template_id, authority_level="auto")

    # 6. Task & Execution
    task = task_manager.create_task(persona_id=persona.id, goal="Apply to Greenhouse")
    
    # The Execution Engine attempts to start. It asks the PolicyEngine for permission.
    workflow_instance_id = uuid4()  # Mocking workflow instance binding for now
    execution = execution_engine.start_execution(
        task_id=task.id, 
        workflow_instance_id=workflow_instance_id,
        target_template_id=workflow_template_id,
        persona_id=persona.id
    )
    
    # Verify Policy allowed it
    assert execution.approval_level == "auto"
    assert execution.status == "running"

    # 7. Complete execution & Verify Event + Ledger
    initial_ledger_count = len(ledger.get_history())
    
    execution_engine.complete_execution(execution.id, outcome="success")
    
    # The EventBus should have triggered the MutationLedger asynchronously or synchronously
    history = ledger.get_history()
    assert len(history) > initial_ledger_count
    
    # Verify the specific ledger entry for the execution completion
    last_entry = history[-1]
    assert last_entry.entity_type == "Execution"
    assert last_entry.entity_id == execution.id
    assert last_entry.new_value["status"] == "succeeded"

    print("✅ Core Lifecycle Test Passed Successfully!")


def test_semantic_state_classifier_smoke():
    """Verify SemanticStateClassifier produces correct auth/context labels on a login URL."""
    from unittest.mock import MagicMock
    from browsermind_core.runtime.state_classifier import SemanticStateClassifier

    snapshot = MagicMock()
    snapshot.content_snippet = ""
    snapshot.title = ""
    snapshot.error_alert_count = 0
    snapshot.success_alert_count = 0
    snapshot.form_count = 1
    snapshot.validation_count = 0
    snapshot.result_count = 0
    snapshot.list_item_count = 0
    snapshot.alert_count = 0
    snapshot.element_count = 100

    classifier = SemanticStateClassifier()
    state = classifier.classify(snapshot, url="https://example.com/login")

    assert state.auth_level == "unauthenticated"
    assert state.page_context == "form_active"
    assert state.fingerprint == "unauthenticated:form_active"
    assert state.confidence > 0.0
    assert state.classified_at is not None


def test_sstg_add_and_persist(tmp_path):
    """Verify SSTG records observations and round-trips through JSON."""
    from browsermind_core.learning.state_transition_graph import SemanticStateTransitionGraph
    from browsermind_core.ontology.semantic_state import SemanticState
    from datetime import timezone, datetime

    sstg_path = str(tmp_path / "sstg.json")
    g = SemanticStateTransitionGraph.load(sstg_path)

    pre = SemanticState(auth_level="unauthenticated", page_context="landing",
                        classified_at=datetime.now(tz=timezone.utc))
    post = SemanticState(auth_level="authenticated", page_context="dashboard",
                         classified_at=datetime.now(tz=timezone.utc))

    g.add_observation(pre, post, capability_hash="abc123", env_key="github")
    g.save()

    g2 = SemanticStateTransitionGraph.load(sstg_path)
    assert g2.node_count() == 2
    assert g2.edge_count() == 1
    edge = g2.edges[0]
    assert edge.from_state == "unauthenticated:landing"
    assert edge.to_state == "authenticated:dashboard"
    assert edge.observation_count == 1
    assert "github" in edge.env_keys
