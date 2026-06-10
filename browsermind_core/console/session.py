"""
console/session.py
Wires up the BrowserMind Kernel for the Console client.
All state is persisted in ~/.browsermind/ by default.
"""
import os
import json
from pathlib import Path
from typing import Optional
from uuid import UUID

from browsermind_core.runtime.event_bus import EventBus
from browsermind_core.ledger.mutation_ledger import MutationLedger
from browsermind_core.ledger.ledger_repository import LedgerRepository
from browsermind_core.ledger.outcome_ledger import OutcomeLedger
from browsermind_core.ledger.outcome_repository import OutcomeRepository
from browsermind_core.runtime.persistence import LocalJSONPersistenceProvider
from browsermind_core.runtime.lesson_reader import LessonReader
from browsermind_core.runtime.behavior_audit import BehaviorAuditLog
from browsermind_core.runtime.execution_repository import ExecutionRepository
from browsermind_core.runtime.execution_engine import ExecutionEngine
from browsermind_core.managers.policy.policy_engine import PolicyEngine
from browsermind_core.managers.principal.principal_manager import PrincipalManager
from browsermind_core.managers.principal.persona_manager import PersonaManager
from browsermind_core.managers.identity.secret_vault import SecretVault
from browsermind_core.managers.identity.identity_service import IdentityService
from browsermind_core.runtime.task_manager import TaskManager
from browsermind_core.ontology.workflow_store import WorkflowStore
from browsermind_core.ontology.template_candidate import CandidateRegistry
from browsermind_core.ontology.recovery_candidate import RecoveryCandidateRegistry
from browsermind_core.runtime.recovery_registry import RecoveryRegistry
from browsermind_core.runtime.auto_pilot import AutoPilot
from browsermind_core.learning.capability_hypothesis_store import CapabilityHypothesisStore
from browsermind_core.runtime.state_classifier import SemanticStateClassifier
from browsermind_core.runtime.semantic_state_classifier_v2 import SemanticStateClassifierV2
from browsermind_core.runtime.page_state_extractor import PageStateExtractor
from browsermind_core.learning.state_transition_graph import SemanticStateTransitionGraph
from browsermind_core.learning.sstg_planner import SSTGPlanner
from browsermind_core.learning.sstg_gap_analyzer import SSTGGapAnalyzer
from browsermind_core.execution.goal_spec import GoalSpec
from browsermind_core.execution.goal_registry import GoalRegistry
from browsermind_core.execution.goal_decomposer import GoalDecomposer
from browsermind_core.execution.execution_coordinator import ExecutionCoordinator


DEFAULT_STORE = str(Path.home() / ".browsermind")


class KernelSession:
    """
    The single entry point for the Console.
    Constructs and holds all Kernel components wired together.
    """

    def __init__(self, store_dir: str = DEFAULT_STORE):
        self.store_dir = store_dir
        os.makedirs(store_dir, exist_ok=True)

        self.event_bus = EventBus()

        provider = LocalJSONPersistenceProvider(store_dir)
        self.repo = ExecutionRepository(provider)
        self.provider = provider

        ledger_repo = LedgerRepository(provider)
        self.ledger = MutationLedger(self.event_bus, repository=ledger_repo)
        self.ledger_repo = ledger_repo

        outcome_repo = OutcomeRepository(provider)
        self.outcome_ledger = OutcomeLedger(repository=outcome_repo)
        self.outcome_repo = outcome_repo
        self.lesson_reader = LessonReader(outcome_ledger=self.outcome_ledger)
        self.behavior_audit = BehaviorAuditLog(
            path=Path(store_dir) / "audit" / "behavior_audit.jsonl"
        )

        self.policy_engine = PolicyEngine(store_path=Path(store_dir))
        self.vault = SecretVault()

        self.principal_manager = PrincipalManager(self.event_bus)
        self.persona_manager = PersonaManager(self.event_bus, store_dir=store_dir)
        self.identity_service = IdentityService(self.vault)
        self.task_manager = TaskManager(self.event_bus)
        self.execution_engine = ExecutionEngine(
            self.event_bus, self.policy_engine, self.repo
        )
        self.workflow_store = WorkflowStore(store_dir)
        self.candidate_registry = CandidateRegistry(store_dir)
        self.recovery_candidate_registry = RecoveryCandidateRegistry(store_dir)
        self.recovery_registry = RecoveryRegistry(store_dir)
        self.auto_pilot = AutoPilot(self)
        # Exploration: hypothesis store receives unknown capability patterns from
        # ExplorationHarness.run() and feeds them back as exploration targets.
        # persona_id="default" at session level; persona-scoped stores are a follow-on.
        self.hypothesis_store = CapabilityHypothesisStore(
            root=Path(store_dir) / "memory" / "default",
            persona_id="default",
        )

        # Semantic intelligence layer
        self.state_classifier    = SemanticStateClassifier()       # v1 — EffectSnapshot-based
        self.state_classifier_v2 = SemanticStateClassifierV2()     # v2 — PageStateSignals-based
        self.page_state_extractor = PageStateExtractor()
        self.sstg = SemanticStateTransitionGraph.load(
            path=str(Path(store_dir) / "sstg.json")
        )
        self.sstg_planner = SSTGPlanner(self.sstg)
        self.sstg_gap_analyzer = SSTGGapAnalyzer(self.sstg)

        # L14 Planning layer
        self.goal_registry = GoalRegistry()
        self.goal_decomposer = GoalDecomposer(self.sstg_planner)
        self.execution_coordinator = ExecutionCoordinator(
            goal_decomposer=self.goal_decomposer,
        )

    # -------------------------------------------------------------------------
    # Index helpers (simple key-value lookup files)
    # -------------------------------------------------------------------------

    def _index_path(self, kind: str) -> str:
        return os.path.join(self.store_dir, f"_{kind}_index.json")

    def _load_index(self, kind: str) -> dict:
        path = self._index_path(kind)
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def _save_index(self, kind: str, index: dict):
        with open(self._index_path(kind), "w") as f:
            json.dump(index, f, indent=2)

    def _register(self, kind: str, name: str, entity_id: str, extra: dict = {}):
        idx = self._load_index(kind)
        idx[name] = {"id": entity_id, **extra}
        self._save_index(kind, idx)

    def _lookup(self, kind: str, name_or_id: str) -> Optional[dict]:
        idx = self._load_index(kind)
        if name_or_id in idx:
            return idx[name_or_id]
        # Try lookup by partial ID
        for entry in idx.values():
            if entry["id"].startswith(name_or_id):
                return entry
        return None
