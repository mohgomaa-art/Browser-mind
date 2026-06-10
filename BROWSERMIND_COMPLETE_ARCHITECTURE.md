# BROWSERMIND COMPLETE ARCHITECTURE
## Canonical Technical Reference — Derived from Source Code

**Generated:** 2026-06-09  
**Source:** Full codebase read (bm.py, browsermind_core/**, core/**, training/**, scripts/**, train_*.py, *.py)  
**Method:** Code-first reverse engineering. Implementation beats documentation everywhere.  
**Status:** Authoritative as of commit `dafa0ce`

---

## TABLE OF CONTENTS

1. [Executive Summary](#phase-1--executive-summary)
2. [System Purpose & Core Mission](#phase-2--system-purpose)
3. [Full Architecture Map](#phase-3--full-architecture-map)
4. [Directory Walkthrough](#phase-4--directory-walkthrough)
5. [File Inventory](#phase-5--file-inventory)
6. [Data Models](#phase-6--data-models)
7. [Runtime Flow](#phase-7--runtime-flow)
8. [Replay Analysis](#phase-8--replay-analysis)
9. [Discovery System Deep Dive](#phase-9--discovery-system-deep-dive)
10. [Learning Layer Analysis](#phase-10--learning-layer-analysis)
11. [Historical Evolution](#phase-11--historical-evolution)
12. [Failure Analysis](#phase-12--failure-analysis)
13. [Current Bottlenecks](#phase-13--current-bottlenecks)
14. [Technical Debt Audit](#phase-14--technical-debt-audit)
15. [Security Audit](#phase-15--security-audit)
16. [State of the Project](#phase-16--state-of-the-project)
17. [What BrowserMind Is Becoming](#phase-17--what-browsermind-is-becoming)
18. [Critical Recommendations](#phase-18--critical-recommendations)
19. [Appendix](#phase-19--appendix)

---

## PHASE 1 — EXECUTIVE SUMMARY

### What is BrowserMind?

**BrowserMind is a Playwright-based web automation kernel with a capability discovery engine, a semantic replay system, and a nascent personal digital operating system (PDOS) layer.**

It is not a single thing. The name covers three distinct systems at different maturity levels that coexist in the same repository:

| Layer | What it is | Maturity |
|---|---|---|
| `core/` | Original heuristic browser agent | FROZEN (dead code) |
| `browsermind_core/runtime/` + ontology | Semantic replay kernel | Production-grade |
| Discovery / Learning Loop | Capability mining platform | Early/experimental |

### What it originally was

A simple Python browser automation agent. `main.py` and the `core/` directory preserve this phase: an `IntentDetector` classifies user queries into 8 intents (search_docs, monitor_news, compare_prices...), a `TaskDecomposer` expands them into action sequences, and an `ActionExecutor` drives Playwright. The `BCPolicyV1` (now frozen) was a small neural network predicting which heuristic to apply.

This is marked `LEGACY_FROZEN` in `core/LEGACY_FROZEN.md`. It is NOT used by the current system.

### What it evolved into

The codebase underwent a deep architectural inversion. The new system:

1. **Records** human demonstrations via Playwright (`bm record start`)
2. **Compiles** them into semantic `WorkflowTemplate` objects with per-step `TargetDescriptor`, `ReplayabilityAssessment`, and `FailureAttribution` wiring
3. **Replays** workflows deterministically via a multi-strategy `TargetResolver` (semantic → placeholder → nearby_text → structural_path → capability_intent)
4. **Explores** sites autonomously via `ExplorerPolicy` + `AffordanceDiscoverer` to discover `CapabilityHypotheses`
5. **Mines** recurring failure patterns and promotes them to a data-driven `RecoveryRegistry`
6. **Trains** a BC policy (`BCPolicyV2`) from `OutcomeLedger` episodes, closing the self-improvement loop

Alongside this: a full **Personal Digital Operating System** layer with `Principal`, `Persona`, `Identity`, `SecretVault` (Fernet-encrypted), `TrustPolicy` (zero-trust ABAC), and a 500-site exploration mission queue.

### What it is NOT

- **NOT an LLM-driven agent**: There is zero LLM in the replay path. The replay engine is fully deterministic, semantic-resolution-based. `agent_trainer.py` uses an LLM (Gemini via OpenRouter) for a separate self-improving trainer, but this is not wired into the production replay path.
- **NOT a general web scraper**: The system requires pre-recorded `WorkflowTemplate` objects. It cannot execute arbitrary web tasks without prior compilation.
- **NOT a finished product**: The learning loop is plumbed but not confirmed closed on real-traffic evidence (`bm system status` reports `PLUMBED BUT DRY` unless at least one mined strategy has been committed and validated).

### Historical Evolution Summary

```
Phase 0: Browser Agent (core/)
     ↓ heuristic execution → data collection need
Phase 1: Dataset Collection (record_session.py, collect_*.py)
     ↓ need structured compilation → deterministic replay
Phase 2: P2A Demonstration System (DemonstrationCompiler, bm record)
     ↓ need reliability measurement → replay engine
Phase 3: P3A Replay Engine (ReplayEngine, TargetResolver)
     ↓ need prediction accuracy → failure attribution
Phase 3.1: Replayability Prediction (FailureAttribution, tier system)
     ↓ need state verification → effect verification
Phase 4C: State Verification (StateEvidence, StateInference, ContractVerifier)
     ↓ need to scale to many sites → autonomous exploration
Phase 5: Exploration/Discovery (ExplorerPolicy, ExplorationHarness)
     ↓ need to learn from discoveries → hypothesis tracking
Phase 6: Capability Discovery (CapabilityHypothesisStore, CapabilityTaxonomy)
     ↓ need self-improvement → closed-loop training
Phase 7: Learning Loop (BCPolicyV2, OutcomeLedger → train_bc_v2.py)
     ↓ need robust failure handling → data-driven recovery
Phase 8: Recovery Mining (RecoveryRegistry, failure_pattern_miner)
     ↓ need identity/privacy isolation → OS layer
Phase 9: Personal Digital OS (Principal/Persona/Identity/SecretVault)
```

---

## PHASE 2 — SYSTEM PURPOSE

### Core Mission

BrowserMind's implemented purpose is: **discover, compile, replay, and continuously improve the ability to execute web tasks on behalf of identified personas with zero manual per-site coding.**

The fundamental abstraction is the **Capability**: a named, transferable, boundary-scoped unit of web behavior identified by the content-addressed hash of its invariant intent set.

### Principal Hierarchy (The Ontology)

Defined in `browsermind_core/ontology/p1_schemas.py`:

```
Principal (user / org / team / api_client)
    └── Persona (sandboxed execution context — NOTHING crosses this boundary)
            ├── Identity (authenticated state on a given Environment)
            │       └── Secret (Fernet-encrypted credential)
            ├── Resource (file / url / structured_data)
            ├── Preference (persona-level biases + weights)
            ├── TrustPolicy (ABAC rules: auto / ask / never)
            ├── WorkflowInstance (personalized template binding)
            │       └── WorkflowTemplate (system-level template)
            │               └── Capability (primitive web action)
            └── Task (concrete goal)
                    └── Execution (active state machine)
                            └── Snapshot (git-like checkpoint)
```

### Key Abstractions

**Principal**: The external owner of everything. Has a billing_id. Types: user, organization, team, api_client.

**Persona**: The absolute isolation boundary. Two personas cannot observe or affect each other during execution. Nothing crosses this line. `PersonaManager` persists personas on disk via `LocalJSONPersistenceProvider`.

**Identity**: An authenticated state for a persona on a specific environment. Status: active / expired / revoked / requires_2fa. Backed by a `Secret` stored in `SecretVault`.

**Environment**: The target domain execution context (e.g., LinkedIn, Greenhouse). Has `risk_level` (low/medium/high/extreme), `anti_bot_active`, `requires_auth`.

**Session**: Represented by `AuthSession` in the runtime — manages the Playwright browser context including profile directory, cookie jar, and viewport.

**Mission**: An entry in `MissionQueue` directing the system to explore a site autonomously. Has `site_key`, `persona`, `budget` (max steps), `run_history`, and lifecycle states.

**Execution**: The active state machine running a `WorkflowInstance`. States: running → paused → forked → succeeded / failed / rollback. Has `approval_level` (auto/ask/never) resolved at start via `PolicyEngine`.

**Workflow**: Two-level:
- `WorkflowTemplate`: System-level compiled procedure (steps with TargetDescriptors)
- `WorkflowInstance`: Persona-bound version with resolved resources and identities

**Replay**: The act of executing a `WorkflowTemplate` via `ReplayEngine`, which produces a `ReplayReport` with per-step `FailureAttribution` records.

**Discovery**: The process of autonomously exploring a site via `ExplorerPolicy` and feeding unknown intent clusters to `CapabilityHypothesisStore`.

**Learning**: The pipeline: OutcomeLedger records → EpisodeExtractor → BCPolicyV2 training → bc_v2_checkpoint.pt → BCPolicyAdapter informs TargetResolver strategy ordering.

### Entity Relationship Diagram

```
Principal (1) ──has──► (*) Persona
Persona   (1) ──has──► (*) Identity
Persona   (1) ──has──► (*) Resource
Persona   (1) ──has──► (*) Task
Persona   (1) ──has──► (*) WorkflowInstance
Identity  (1) ──has──► (1) Secret
Task      (1) ──has──► (*) Execution
Execution (1) ──has──► (*) Snapshot
WorkflowInstance (1) ──binds──► (1) WorkflowTemplate
WorkflowTemplate (1) ──requires──► (*) Capability
Environment (1) ──provides──► (*) Capability
ReplayReport (1) ──has──► (*) FailureAttribution
CapabilityHypothesis (*) ──observed_on──► (*) Environment
CapabilityRecord (1) ──validated_in──► (*) Environment
```

---

## PHASE 3 — FULL ARCHITECTURE MAP

```
BrowserMind Kernel
├── Ontology Layer                    (browsermind_core/ontology/)
│   ├── p1_schemas.py                 — All Pydantic entity models
│   ├── workflow_store.py             — Template & instance persistence
│   ├── template_candidate.py        — Proposed workflow mutations
│   ├── recovery_candidate.py        — Proposed recovery strategies
│   ├── field_registry.py            — Semantic field ontology
│   └── resource_ontology.py         — Resource classification
│
├── Runtime Layer                     (browsermind_core/runtime/)
│   ├── replay_engine.py              — P3A/P3.1 execution engine
│   ├── target_resolver.py            — Multi-strategy DOM target resolution
│   ├── execution_engine.py           — Execution lifecycle + checkpointing
│   ├── policy_engine.py              — Zero-trust ABAC enforcement
│   ├── action_executor.py            — Low-level DOM action driver
│   ├── affordance_discoverer.py      — AffordanceDiscoverer per IntentFamily
│   ├── affordance_executor.py        — AffordanceExecutor
│   ├── auth_session.py               — Browser session + profile management
│   ├── environment_registry.py       — Site config registry
│   ├── environment_config.py         — Per-site environment definitions
│   ├── recovery_registry.py          — Data-driven recovery ladder (R1-R5+)
│   ├── recovery_promotion_gate.py    — Shadow test promotion logic
│   ├── recovery_post_commit_monitor.py — Negative lift quarantine
│   ├── bc_policy.py                  — BCPolicyAdapter (trained model inference)
│   ├── resource_resolver.py          — Vault-backed resource resolution
│   ├── contract_verifier.py          — Goal completion verification
│   ├── vault_writer.py               — Per-persona Fernet secret/resource store
│   ├── auto_pilot.py                 — Autonomous replay controller
│   ├── task_manager.py               — Task lifecycle
│   ├── event_bus.py                  — In-process event pub/sub
│   └── persistence.py                — PersistenceProvider + LocalJSONProvider
│
├── Exploration Layer                  (browsermind_core/exploration/)
│   ├── explorer_policy.py             — Autonomous affordance execution policy
│   ├── exploration_harness.py         — Connects ExplorationSpec to ReplayEngine
│   ├── exploration_spec.py            — ExplorationSpec + ExplorationResult
│   ├── experience_interpreter.py      — Intent sets → ExperienceLabel
│   └── effect_verifier.py             — DOM diff → EffectVerdict
│
├── Learning Layer                     (browsermind_core/learning/)
│   ├── capability_record.py           — CapabilityRecord (content-addressed)
│   ├── capability_hypothesis.py       — CapabilityHypothesis lifecycle
│   ├── capability_hypothesis_store.py — Persistent hypothesis store
│   ├── capability_taxonomy.py         — 30-category × N capability taxonomy
│   ├── capability_boundary.py         — Failure boundary tracking
│   ├── capability_contract.py         — Contract satisfaction checking
│   └── reward_layers.py               — Multi-layer reward computation
│
├── Ledger Layer                       (browsermind_core/ledger/)
│   ├── mutation_ledger.py             — Immutable state change log
│   ├── ledger_repository.py           — Persistent mutation log
│   ├── outcome_ledger.py              — Replay outcome records
│   ├── outcome_repository.py          — Persistent outcome store
│   ├── requirement_ledger.py          — Requirement tracking
│   └── cascade.py                     — Ledger cascade logic
│
├── Manager Layer                      (browsermind_core/managers/)
│   ├── identity/identity_service.py   — Identity provisioning
│   ├── identity/secret_vault.py       — Fernet-encrypted vault
│   ├── policy/policy_engine.py        — ABAC policy
│   ├── principal/principal_manager.py — Principal CRUD
│   └── principal/persona_manager.py   — Persona CRUD + persistence
│
├── Agent Layer                        (browsermind_core/agent/)
│   ├── capability_discovery.py        — Environment capability discovery
│   ├── router.py                      — Policy router + executor
│   ├── inference.py                   — FlowInferenceEngine
│   ├── environment_binder.py          — Asset graph environment binding
│   ├── satisfaction_planner.py        — Requirement satisfaction planning
│   ├── backward_state_planner.py      — Backward reachability planning
│   ├── capability_dependency_planner.py — Dependency graph resolution
│   ├── asset_graph.py                 — AssetGraph resolver
│   ├── path_utility.py                — Path scoring
│   └── requirement_state_registry.py  — State registry
│
├── Execution Sub-System               (browsermind_core/execution/)
│   ├── execution_coordinator.py       — High-level execution coordinator
│   ├── generic_executor.py            — GenericCapabilityExecutor
│   ├── playwright_executor.py         — Playwright-backed executor
│   └── outcome_verifier.py            — OutcomeVerifier
│
├── Experiments Layer                  (browsermind_core/experiments/)
│   ├── harness.py                     — ReplayExperimentHarness
│   ├── failure_taxonomy.py            — Failure classification
│   ├── reliability_metrics.py         — Success/reliability metrics
│   ├── ground_truth.py                — Ground truth annotation dataset
│   ├── state_verifier.py              — State evidence collection
│   ├── env_fingerprinter.py           — Environment fingerprinting
│   ├── replay_result.py               — ReplayResult Pydantic model
│   └── report_generator.py            — JSON/text report generation
│
├── Evaluation Layer                   (browsermind_core/evaluation/)
│   ├── batch_runner.py                — BatchRunner (multi-site eval)
│   ├── transfer_arena.py              — TransferArena (cross-site testing)
│   └── state_verification/verifier.py — StateVerifier
│
├── Console Layer                      (browsermind_core/console/)
│   ├── cli.py                         — bm CLI (Click, 1954 lines)
│   ├── session.py                     — KernelSession (wire-up)
│   ├── mission_commands.py            — bm mission commands
│   ├── environment_commands.py        — bm environment commands
│   ├── session_commands.py            — bm session commands
│   └── doctor.py                      — bm doctor pre-flight checks
│
├── API/Sidecar Layer                  (browsermind_core/api/)
│   └── sidecar.py                     — FastAPI server (1913 lines)
│
├── Media Layer                        (browsermind_core/media/)
│   ├── media_vault.py                 — Media asset storage
│   ├── media_asset.py                 — MediaAsset model
│   ├── pipeline.py                    — Media processing pipeline
│   └── adapters/                      — Discord, YouTube, Instagram, Pinterest
│
├── UI Layer                           (browsermind_ui/)
│   ├── views/main_window.py           — PySide6 main window
│   ├── views/tasks_view.py            — Task management view
│   ├── views/executions_view.py       — Execution monitoring view
│   └── core/commands.py               — UI command handlers
│
├── Training Pipeline                  (train_*.py, training/)
│   ├── train_bc_v2.py                 — BCPolicyV2 trainer (PyTorch)
│   ├── train_dagger.py                — DAgger interactive trainer
│   ├── train_ppo.py                   — PPO reinforcement trainer
│   └── training/                      — Datasets, gold data, sessions
│
├── Scripts                            (scripts/)  [97 files]
│   — Analysis, audits, dataset generation, benchmark runners
│
└── Legacy Layer (FROZEN)              (core/, main.py)
    ├── core/decision_engine.py        — Heuristic decision engine (FROZEN)
    ├── core/executor.py               — Heuristic action executor (FROZEN)
    ├── core/recorder.py               — Session recorder (FROZEN)
    └── main.py                        — Original BrowserMind entry (FROZEN)
```

### Layer Dependencies and Data Flow

```
Console (CLI) ──creates──► KernelSession
                                │
                                ├── PersistenceProvider (disk)
                                ├── EventBus (in-process)
                                ├── MutationLedger → LedgerRepository
                                ├── OutcomeLedger → OutcomeRepository
                                ├── PolicyEngine (in-memory ABAC)
                                ├── SecretVault (Fernet)
                                ├── PrincipalManager
                                ├── PersonaManager → disk
                                ├── IdentityService → SecretVault
                                ├── ExecutionEngine → ExecutionRepository
                                ├── WorkflowStore → disk
                                ├── CandidateRegistry → disk
                                ├── RecoveryRegistry → recovery_ladder.json
                                ├── AutoPilot
                                └── CapabilityHypothesisStore → disk

bm replay start ──► ReplayEngine
                        │
                        ├── AuthSession (Playwright browser)
                        ├── TargetResolver (multi-strategy)
                        │       ├── BCPolicyAdapter (model inference)
                        │       └── RecoveryRegistry (R1-R5+)
                        ├── ActionExecutor (DOM actions)
                        ├── ResourceResolver → VaultWriter
                        ├── StateVerifier → ContractVerifier
                        ├── OutcomeLedger.record() per step
                        └── ExecutionEngine (lifecycle)

bm explore ──► ExplorationHarness
                    │
                    ├── SiteRegistry / EnvironmentRegistry
                    ├── ExplorerPolicy
                    │       ├── AffordanceDiscoverer
                    │       ├── AffordanceExecutor
                    │       └── EffectVerifier
                    ├── ExperienceInterpreter
                    └── CapabilityHypothesisStore.observe()

bm self-train ──► EpisodeExtractor → OutcomeLedger
                    └── train_bc_v2.py → bc_v2_checkpoint.pt
                            └── BCPolicyAdapter.predict() in ReplayEngine
```

---

## PHASE 4 — DIRECTORY WALKTHROUGH

### Root Level

| Path | Purpose |
|---|---|
| `bm.py` | CLI entry point — 5 lines, delegates to `browsermind_core/console/cli.py` |
| `main.py` | **LEGACY FROZEN** — original BrowserMind engine; not used by current system |
| `train_bc_v2.py` | BC policy trainer (PyTorch 2-head network) |
| `train_bc.py` | Older BC trainer (uses GraphDataset) — partially superseded |
| `train_dagger.py` | DAgger interactive trainer |
| `train_ppo.py` | PPO RL trainer (experimental, may be frozen) |
| `record_session.py` | Standalone recording script |
| `evaluate.py` | Policy evaluation runner |
| `agent_trainer.py` | LLM-assisted self-improving trainer (Gemini via OpenRouter) |
| `studio_api.py` | Studio web API entrypoint |
| `studio.html` | Studio web interface |
| `bc_v2_checkpoint.pt` | Trained BC policy checkpoint (model weights) |

### `browsermind_core/` — The Active Kernel

This is the production system. All active development happens here.

#### `browsermind_core/ontology/`
**Purpose:** The type system and data models for the entire BrowserMind universe.

- `p1_schemas.py` (338 lines): All Pydantic models. This file IS the architecture — it encodes every entity and relationship.
- `workflow_store.py`: Persistence of WorkflowTemplates and WorkflowInstances via JSON files. Namespaces: `wf_template`, `wf_instance`. Has `lookup_template()` and `create_instance()`.
- `template_candidate.py`: `TemplateCandidate` — proposed mutations to a template (e.g., tier downgrades from replay failures). States: pending → committed / rejected / rolled_back.
- `recovery_candidate.py`: `RecoveryCandidateRegistry` — proposed new recovery strategies mined from OutcomeLedger. States: pending → shadow → ready → committed.
- `field_registry.py`: Semantic field ontology registry (email, password, username fields). Used by `ResourceResolver` to match form fields.
- `resource_ontology.py`: Resource classification logic.
- `asset.py`: Old asset graph types (used by `browsermind_core/agent/`).

#### `browsermind_core/runtime/`
**Purpose:** The execution kernel. Every live action happens here.

This is the most complex and most important directory in the project. 38 Python files.

Key files:
- **`replay_engine.py`**: The central orchestrator. Given a `WorkflowTemplate` and an `AuthSession`, it iterates steps, calls `TargetResolver`, executes actions via `ActionExecutor`, collects `FailureAttribution`, verifies state, writes to `OutcomeLedger`. Has human intervention support (`pause()` / `resume()`).
- **`target_resolver.py`**: Multi-strategy DOM element resolver. Strategy ladder: primary_semantic → loose_semantic → by_placeholder → by_text_accessible → by_text_content → structural_path → capability_intent. Consults `BCPolicyAdapter` to reorder strategies. Returns `ResolutionResult` with forensics data. Critical file — most replay failures originate here.
- **`execution_engine.py`**: Manages `Execution` lifecycle. Creates SnapshotRecords. Emits `EntityMutated` events. States: running → paused / succeeded / failed.
- **`action_executor.py`**: Low-level Playwright action driver. Handles click, fill, press, navigate, submit, select, check, upload. Raises `ActionTransitionSuccess` on page navigation.
- **`affordance_discoverer.py`**: Discovers UI affordances grouped by `IntentFamily` (SEARCH, FORM, FILTER, NAVIGATION, AUTH). Returns `Affordance` objects with score and locator.
- **`affordance_executor.py`**: Executes an `Affordance` object (click, submit, etc.). Raises `AffordanceExecutionError` on failure.
- **`auth_session.py`**: Manages the Playwright browser context. Handles profile directory loading (warm profiles with cookies), headless mode, environment entry resolution.
- **`environment_registry.py`**: Registry of known environments. `resolve(key)` returns an `EnvironmentEntry` with `start_url`, `family`, `requires_auth`.
- **`environment_config.py`**: Per-site environment configuration. Maps site keys to URL patterns, profile dirs, auth requirements.
- **`recovery_registry.py`**: Persistent recovery ladder (`recovery_ladder.json`). Seed: R1-R5 (container_proximity, placeholder, accessible_name, nearby_text, structural_path) + capability_intent. Extensible via `append()`.
- **`recovery_promotion_gate.py`**: Runs shadow test evaluation. Candidates need `shadow_min_samples` tests with `min_lift` improvement before promotion to `ready`.
- **`recovery_post_commit_monitor.py`**: Post-commit monitoring. Quarantines mined strategies whose real-traffic lift turns negative.
- **`bc_policy.py`**: `BCPolicyAdapter` — loads `bc_v2_checkpoint.pt`, exposes `predict(role, action, step_seq, env_key)`. Returns `{action_id, strategy_label, action_probs, strategy_probs}`.
- **`resource_resolver.py`**: Resolves template resource tokens (`{resume}`, `{email}`) from `VaultWriter` data.
- **`contract_verifier.py`**: Verifies goal completion post-replay (was the intended state actually reached?).
- **`vault_writer.py`**: Per-persona Fernet-encrypted secret and resource store. Path: `{store_dir}/personas/{persona}/vault.json`.
- **`auto_pilot.py`**: Autonomous replay scheduler. Can chain replays across templates for a persona.
- **`persistence.py`**: `PersistenceProvider` ABC + `LocalJSONPersistenceProvider` (atomic writes via temp-file rename, SHA-256 checksums).
- **`event_bus.py`**: Simple in-process publish/subscribe. `emit(event_type, payload)` / `subscribe(event_type, callback)`. Not persistent.
- **`task_manager.py`**: Creates `Task` entities. In-memory only (no persistence).
- **`behavior_audit.py`**: `BehaviorAuditLog` — JSONL append-only log of replay decisions for offline analysis.
- **`lesson_reader.py`**: Extracts lessons from `OutcomeLedger` for runtime guidance.
- **`bc_policy.py`**: Singleton `BCPolicyAdapter` via `shared()`.
- **`intent_family.py`**: `IntentFamily` enum (AUTH, SEARCH, FORM, FILTER, NAVIGATION) + `IntentFamilyMapper`.

#### `browsermind_core/exploration/`
**Purpose:** Autonomous web exploration machinery.

- **`explorer_policy.py`** (830 lines): The brain of autonomous exploration. Discovers affordances on a page, executes them safely with probe values, verifies effects via `EffectVerifier`, feeds hypotheses to `CapabilityHypothesisStore`. Features: overlay/cookie dismissal, bot-wall detection (SOFT: Cloudflare, HARD: Google block), Cloudflare auto-bypass, human-like timing jitter, mobile viewport toggle, multi-hop traversal (up to depth 3), step-level retry.
- **`exploration_harness.py`** (354 lines): Bridges `ExplorationSpec` to `ReplayEngine`. Creates a synthetic `_MinimalExplorationTemplate` (single navigate-and-explore step). Runs `ExperienceInterpreter`. Feeds unknown intent clusters to `CapabilityHypothesisStore`. Persists run records to `~/.browsermind/explore_runs/`.
- **`exploration_spec.py`**: `ExplorationSpec` (site_key, budget, capability_targets, stop_on_experience) and `ExplorationResult`.
- **`experience_interpreter.py`** (372 lines): Maps completed intent sets to `ExperienceLabel` objects. 15 built-in patterns across 4 families (authentication, search, community, form_fill) + media + navigation. Confidence: 0.8–1.0 for full matches. Generates UNKNOWN sentinel when ≥2 unmatched intents exist.
- **`effect_verifier.py`** (349 lines): Pre/post DOM snapshot diffing. Detects URL transition, DOM mutations, form success messages. Returns `EffectVerdict` with `effect_type`, `confidence`, `quality_score`, `outcome_label` (SUCCESS / TRANSITION_SUCCESS / FAILED).

#### `browsermind_core/learning/`
**Purpose:** Capability knowledge graph — storing, tracking, and promoting discovered capabilities.

- **`capability_record.py`**: `CapabilityRecord` — a capability identified by SHA-256 hash of its invariant intent set. Tier lifecycle: CANDIDATE → STRONG (≥2 environments) → VALIDATED (contract_verified_ratio ≥ 0.80) → DEPRECATED. Has `record_transfer()`, `record_strategy_outcome()`, `record_reuse()`.
- **`capability_hypothesis.py`**: `CapabilityHypothesis` — a novel intent cluster not yet in `CapabilityRecord`. Status: SEED → RECURRING (frequency ≥ 3) → EMERGING (≥2 environments) → CANDIDATE (≥5 frequency + ≥2 envs) → PROMOTED / REFUTED.
- **`capability_hypothesis_store.py`** (443 lines): Persistent store for hypotheses. JSON files per hash under `~/.browsermind/memory/<persona_id>/hypotheses/`. Has `observe()`, `promote()`, `refute()`, `query()`, `exploration_targets()`, `synthesize_cross_site_patterns()`, `seed_from_taxonomy()`. Self-directed exploration: `exploration_targets()` returns RECURRING/EMERGING hypotheses → `ExplorationSpec.capability_targets` → back to store.
- **`capability_taxonomy.py`** (474 lines): 30-category × N capability key taxonomy. Categories: social, forum, chat, video, audio, image, news, blog, ecommerce, marketplace, saas, productivity, knowledge, dev, registry, cloud, auth, email, government, finance, crypto, education, jobs, cms, search, maps, travel, ai, dashboard, frontier. Total: ~300 capability keys.
- **`capability_boundary.py`**: Tracks failure boundary conditions for a capability (e.g., "fails when iframe is present").
- **`capability_contract.py`**: Defines pre/post conditions for capability satisfaction.
- **`reward_layers.py`**: Multi-layer reward computation for learning:
  - Layer 1: Step execution success
  - Layer 2: Effect verification
  - Layer 3: Novel capability discovery
  - Layer 4: Cross-environment reuse

#### `browsermind_core/ledger/`
**Purpose:** The truth-telling layer. Everything that happened is recorded here.

- **`mutation_ledger.py`**: `MutationLedger` — event-driven log of entity state changes. Subscribes to `EntityMutated` events. Each `LedgerEntry` has: id, timestamp, entity_type, entity_id, old_value, new_value, actor, evidence, policy.
- **`ledger_repository.py`**: Persistent `MutationLedger` backend. Append-only JSONL file under `{store}/ledger/`.
- **`outcome_ledger.py`**: `OutcomeLedger` — records what happened during replay. `OutcomeRecord` has: scope (step/execution/task/workflow_instance), success, evidence, metrics. This is the primary training data source.
- **`outcome_repository.py`**: Persistent `OutcomeLedger` backend. Append-only JSONL under `{store}/outcome_ledger/`.
- **`requirement_ledger.py`**: Tracks requirement satisfaction state.
- **`cascade.py`**: Cascading ledger logic (propagates outcomes across scope hierarchy).

#### `browsermind_core/managers/`
**Purpose:** Entity lifecycle management.

- **`identity/identity_service.py`**: Creates and manages `Identity` entities. `provision_identity()` creates an Identity + stores the raw secret in SecretVault.
- **`identity/secret_vault.py`** (120 lines): Fernet-encrypted vault. Key resolution order: `BROWSERMIND_VAULT_KEY` env var → `{store}/.vault_key` file → newly generated. Persists `Secret` objects per identity_id. `encrypt_and_store()`, `decrypt()`, `encrypt_value()`, `decrypt_value()`.
- **`policy/policy_engine.py`**: In-memory ABAC. Maps `(persona_id, target_id)` → `authority_level`. Default: "ask" (Zero Trust). Not persisted across sessions.
- **`principal/principal_manager.py`**: `Principal` CRUD with EventBus notification.
- **`principal/persona_manager.py`** (96 lines): `Persona` CRUD with on-disk persistence. `DuplicatePersonaError` prevents creating duplicate personas. Rehydrates from disk on startup.

#### `browsermind_core/console/`
**Purpose:** The `bm` CLI.

- **`cli.py`** (1954 lines): Complete Click CLI. Commands: `principal`, `persona`, `identity`, `task`, `record`, `workflow template/instance/candidate`, `recovery candidate/mine/sweep/monitor`, `execution start/pause/resume/inspect`, `outcome list`, `ledger tail`, `replay start`, `explore`, `environment`, `mission`, `session`, `dataset export/summary/status`, `benchmark run/compare`, `self-train`, `vault set/get/list/set-resource`, `status`, `field ls/show/add-alias/unknown`, `doctor`, `corpus stats/export`, `site validate/ls/add-campaign`.
- **`session.py`** (122 lines): `KernelSession` — the dependency injection container. Constructs and wires all 18+ kernel components together. `DEFAULT_STORE = ~/.browsermind`.
- **`mission_commands.py`** (489 lines): `bm mission` — autonomous exploration mission commands. `mission start/list/status/pause/resume/cancel`.
- **`environment_commands.py`** (112 lines): `bm environment create/ls`.
- **`session_commands.py`** (223 lines): `bm session` — AuthSession lifecycle management.
- **`doctor.py`** (227 lines): Pre-flight diagnostics. Checks Python version, Playwright installation, network ports, store directory, site registry.

#### `browsermind_core/agent/`
**Purpose:** Higher-order planning agents for goal-decomposition into execution plans.

This layer implements a full goal-to-execution planning stack that is largely orthogonal to the runtime replay layer. It appears to be a research/future direction rather than currently wired into the primary execution path.

- `capability_discovery.py`: Maps environment kinds to baseline capabilities + overrides.
- `router.py`: `PolicyRouter` — dispatches to executors based on policy rules. `FailureOntologyDiagnostic`.
- `inference.py`: `FlowInferenceEngine` — infers execution flows from goal specifications.
- `environment_binder.py`: `EnvironmentBinder` — binds assets to environment capabilities. `AmbiguousAssetError`.
- `satisfaction_planner.py`: `RequirementSatisfactionPlanner` — plans to satisfy requirements.
- `backward_state_planner.py`: `BackwardStatePlanner` — backward reachability from goal state.
- `capability_dependency_planner.py`: `CapabilityDependencyPlanner` — resolves capability dependency graphs.
- `asset_graph.py`: `AssetGraphResolver` — resolves asset graphs.
- `path_utility.py`: `PathUtilityScorer` — scores execution paths.
- `requirement_state_registry.py`: `RequirementStateRegistry` — tracks requirement states.

**Observed architectural tension**: This layer exists in parallel to the `runtime/` replay layer but is NOT integrated into the main `bm replay start` or `bm explore` paths. It appears to be building toward a higher-order task planner that sits above the replay engine.

#### `browsermind_core/experiments/`
**Purpose:** Scientific apparatus for measuring replay quality.

- `harness.py` (380+ lines): `ReplayExperimentHarness` — the top-level coordinator for record/compile/replay/analyze experiments. Has `run_full()`, `run_transfer()`, `result_from_report()`, `save_result()`.
- `failure_taxonomy.py` (172 lines): Classifies failures into categories: TARGET_CHANGED, SELECTOR_AMBIGUOUS, RESOURCE_MISSING, BOT_DETECTED, AUTH_REQUIRED, TIMEOUT, etc.
- `reliability_metrics.py` (102 lines): Computes resolution accuracy, false-positive rate, task completion rate.
- `ground_truth.py` (147 lines): `GroundTruthDataset` — human annotations of what correct resolution looks like for a given step.
- `state_verifier.py` (194 lines): Collects DOM evidence and infers state after replay.
- `env_fingerprinter.py`: Captures `EnvironmentFingerprint` (DOM hash, role distribution) to distinguish "workflow failed" from "environment changed".
- `replay_result.py` (81 lines): `ReplayResult` Pydantic model with per-step outcomes.
- `report_generator.py` (357 lines): JSON and text report generation from experiment results.

#### `browsermind_core/evaluation/`
**Purpose:** Systematic evaluation at scale.

- `batch_runner.py` (209 lines): `BatchRunner` — runs multiple replay experiments in sequence. Feeds `ReplayExperimentHarness`.
- `transfer_arena.py` (219 lines): `TransferArena` — tests whether capabilities transfer between environments. Families: authentication, search, community, form_fill.
- `state_verification/verifier.py` (100 lines): `StateVerifier` — uses verification configs to check post-replay state.

#### `browsermind_core/media/`
**Purpose:** Media asset management for social/content platforms.

- `media_vault.py` (239 lines): `MediaVault` — stores and retrieves media assets.
- `media_asset.py` (240 lines): `MediaAsset` model — type, source, metadata, transforms.
- `pipeline.py` (212 lines): `MediaPipeline` — processes media through transformation steps.
- `adapters/`: Platform-specific adapters:
  - `discord.py`: Discord media handling
  - `instagram.py`: Instagram media handling
  - `pinterest.py`: Pinterest media handling
  - `youtube.py`: YouTube media handling
  - `generic.py`: Generic media handling

The media layer is present but not deeply integrated into the main execution path. It appears to be an early implementation of the "social media automation" use case.

#### `browsermind_core/api/`
**Purpose:** REST + WebSocket API for UI and external integrations.

- `sidecar.py` (1913 lines): Full FastAPI server. Started by the Tauri/Rust host. Exposes:
  - REST endpoints for principals, personas, tasks, executions, workflows, outcomes, ledger
  - WebSocket endpoint for live execution streaming
  - Exploration run history API
  - System status API
  - Wraps `KernelSession` — same business logic as CLI

### `browsermind_ui/` — PySide6 Desktop UI

Qt-based desktop GUI. Limited functionality — view-only in most areas.

- `views/main_window.py` (78 lines): Main window with tab navigation.
- `views/tasks_view.py` (71 lines): Task list view.
- `views/executions_view.py` (277 lines): Execution monitoring with live status updates.
- `core/commands.py` (153 lines): Command pattern bridge between UI and KernelSession.
- `styles.qss` (143 lines): Qt stylesheet (dark theme).

### `browsermind_ui_tauri/` — Tauri/Rust Shell

Rust-based desktop application wrapper. Starts the `sidecar.py` FastAPI process and serves the web UI. Not deeply documented in this audit.

### `core/` — LEGACY FROZEN

**DO NOT USE. DO NOT EXTEND.**

This directory is the original BrowserMind system. `core/LEGACY_FROZEN.md` documents this explicitly. All files contain `DeprecationWarning` in their headers.

- `decision_engine.py` (455 lines): Heuristic-based action selection. Routes to extractors, search, form-fill, etc.
- `executor.py` (1880 lines): Low-level action executor using Playwright + heuristics. The original action execution system.
- `recorder.py` (216 lines): Session recorder (legacy format, not the P2A demonstration format).
- `validator.py` (254 lines): Result validator.
- `task_decomposer.py`: Decomposes intents into step sequences.
- `error_handler.py`, `telemetry.py`, `privacy.py`, `observatory.py`: Supporting infrastructure.

### `training/` — Training Pipeline Data and Scripts

Large directory (~60+ items) containing everything needed for the learning pipeline:

- `dataset_v1.jsonl`, `dataset_autotrain.jsonl`: Training datasets
- `capability_taxonomy_v1.json`, `capability_seeds.json`: Taxonomy data
- `gold/`, `gold_v2/`, `gold_v2_checked/`: Gold-standard labeled data
- `demonstrations/`, `sessions/`, `spec_sessions/`: Recorded sessions
- `failure_buffer/`: Captured failure episodes
- Multiple Python modules: `failure_miner.py`, `gold_dataset.py`, `graph_builder.py`, etc.

### `scripts/` — 97 Analysis and Utility Scripts

Extensive analysis tooling. Key categories:

- **Audit scripts**: `quality_audit.py`, `capability_census.py`, `gold_dataset_audit.py`, `graph_integrity_audit.py`
- **Dataset scripts**: `build_dataset_v2.py`, `generate_hard_negatives.py`, `dataset_validator.py`
- **Replay scripts**: `replay_runner.py`, `sample_replayer.py`, `run_replay_experiments.py`
- **Report scripts**: `capability_discoverability_audit.py`, `capability_competition_report.py`, `run_failure_dominance.py`
- **Live tools**: `live_model_gui.py` (810 lines — full Tkinter GUI for live model testing)
- **Diagnostic tools**: `zone_debugger.py`, `forensic_navigation.py`, `bm_validate.py`

---

## PHASE 5 — FILE INVENTORY

### Critical Files (Risk Level: HIGH)

#### `browsermind_core/ontology/p1_schemas.py`
**Purpose:** The complete ontology — all entity types and their relationships.  
**Classes:** Principal, Persona, Identity, Secret, Resource, Preference, TrustPolicy, WorkflowInstance, WorkflowTemplate, Task, Execution, ExecutionContext, Snapshot, SnapshotRecord, EpisodicMemory, StateEvidence, StateInference, EnvironmentFingerprint, TargetDescriptor, RecordingEvidence, ReplayabilityAssessment, FailureAttribution, ReplayReport, Environment, Capability, ProceduralMemory, SemanticMemory.  
**Risk:** Any schema change here breaks persistence, serialization, and deserialization everywhere. Changing without migration scripts will corrupt stored data.

#### `browsermind_core/runtime/replay_engine.py`
**Purpose:** Core execution orchestrator.  
**Class:** `ReplayEngine`  
**Key methods:** `replay()`, `pause()`, `resume()`, `_start_execution_if_wired()`, `_close_execution_if_wired()`  
**Dependencies:** AuthSession, TargetResolver, ActionExecutor, ResourceResolver, OutcomeLedger, ExecutionEngine, BCPolicyAdapter, RecoveryRegistry  
**Risk:** Central to everything. Failures here affect all replay operations.

#### `browsermind_core/runtime/target_resolver.py`
**Purpose:** Multi-strategy DOM target resolution.  
**Key logic:** Strategy ladder (primary_semantic → loose_semantic → placeholder → accessible_name → nearby_text → structural_path → capability_intent). Consults BCPolicyAdapter to bias strategy order. Returns ResolutionResult with forensics.  
**Risk:** Most replay failures originate here. Changing strategy order has immediate quality impact.

#### `browsermind_core/console/cli.py`
**Purpose:** The complete `bm` CLI.  
**Size:** 1954 lines, 40+ commands.  
**Dependencies:** KernelSession, all runtime components.  
**Risk:** Entry point for all human interaction. Bugs here affect operator workflow.

#### `browsermind_core/api/sidecar.py`
**Purpose:** FastAPI server, 1913 lines.  
**Risk:** Exposes all kernel functionality over HTTP. Security-sensitive (handles personas, identities, secrets).

#### `train_bc_v2.py`
**Purpose:** BC policy trainer.  
**Architecture:** `BCPolicyV2` — 2-head network (action_type + resolution_strategy). Embeddings: role (11), action (9), site (9), step_seq (scalar). Hidden: 128. Loss: weighted CrossEntropy. Known limitation: strategy_head memorizes action_head in current corpus.  
**Risk:** Poor training = degraded replay quality as model predictions steer strategy ordering.

### High-Importance Files (Risk Level: MEDIUM-HIGH)

#### `browsermind_core/console/session.py`
**Purpose:** KernelSession dependency injection.  
**Classes:** `KernelSession`  
**Risk:** Change here affects every `bm` command. Component wiring errors are silent.

#### `browsermind_core/runtime/persistence.py`
**Purpose:** `LocalJSONPersistenceProvider` with atomic writes and SHA-256 integrity.  
**Risk:** Storage layer. Corruption here = data loss.

#### `browsermind_core/learning/capability_hypothesis_store.py`
**Purpose:** Persistent hypothesis lifecycle store.  
**Risk:** Central to discovery loop. Silent corruption would cause capability discovery to stall.

#### `browsermind_core/exploration/explorer_policy.py`
**Purpose:** Autonomous exploration policy.  
**Risk:** Bot wall detection changes (new Google patterns), overlay selector drift. Currently probes with synthetic values — aggressive probing on production sites.

#### `browsermind_core/runtime/recovery_registry.py`
**Purpose:** Data-driven recovery ladder.  
**Risk:** Seeding error or file corruption makes R1-R5 strategies unavailable. Has rollback support.

#### `browsermind_core/runtime/secret_vault.py` (via `managers/`)
**Purpose:** Fernet secret encryption.  
**Risk:** Key rotation = all existing secrets become unreadable. Key file at `{store}/.vault_key`.

---

## PHASE 6 — DATA MODELS

### Principal Hierarchy Models

```
Principal
  id: UUID
  name: str
  principal_type: "user" | "organization" | "team" | "api_client"
  billing_id: Optional[str]
  created_at: datetime
  updated_at: datetime

Persona
  id: UUID
  principal_id: UUID            → Principal
  name: str
  description: Optional[str]
  created_at: datetime
  updated_at: datetime

Identity
  id: UUID
  persona_id: UUID              → Persona
  environment_id: UUID          → Environment
  identifier: str               (e.g. email address)
  status: "active" | "expired" | "revoked" | "requires_2fa"

Secret
  id: UUID
  identity_id: UUID             → Identity
  secret_type: "password" | "token" | "cookie_jar" | "oauth_state"
  encrypted_value: str          (Fernet token)
  expires_at: Optional[datetime]
```

### System-Level Models

```
Environment
  id: UUID
  domain: str
  risk_level: "low" | "medium" | "high" | "extreme"
  anti_bot_active: bool
  requires_auth: bool

Capability
  id: UUID
  name: str
  description: str

WorkflowTemplate
  id: UUID
  name: str
  description: str
  required_capabilities: List[UUID]
  steps: List[Dict]             (compiled semantic steps with TargetDescriptors)
  metadata: Dict

WorkflowInstance
  id: UUID
  persona_id: UUID              → Persona
  template_id: UUID             → WorkflowTemplate
  bound_resources: Dict[str, UUID]   (e.g. {'resume': resource_id})
  bound_identities: Dict[str, UUID]  (e.g. {'linkedin': identity_id})
```

### Execution Models

```
Task
  id: UUID
  persona_id: UUID              → Persona
  goal: str
  status: "pending" | "running" | "completed" | "failed"

ExecutionContext
  persona_id: UUID
  task_id: UUID
  workflow_instance_id: UUID
  template_id: Optional[UUID]
  identity_id: Optional[UUID]
  environment_id: Optional[UUID]

Execution
  id: UUID
  task_id: UUID                 → Task
  workflow_instance_id: UUID    → WorkflowInstance
  status: "running" | "paused" | "forked" | "succeeded" | "failed" | "rollback"
  approval_level: "auto" | "ask" | "never"
  failure_reason: Optional[str]
  retry_count: int
  context: Optional[ExecutionContext]

SnapshotRecord
  id: UUID
  execution_id: UUID            → Execution
  sequence: int                 (monotonically increasing)
  execution_state: Dict         (full serialized Execution)
  is_valid: bool
```

### Replay/Analysis Models

```
TargetDescriptor
  role: str                     (e.g. "button")
  name: str                     (e.g. "Sign In")
  accessible_name: str          (aria-label)
  text_content: str             (innerText)
  placeholder: str
  dom_path: str                 (tagName chain)

ReplayabilityAssessment
  tier: "HIGH" | "AMBIGUOUS" | "UNREPLAYABLE"
  score: float                  (0.0 to 1.0)
  reasons: List[str]

FailureAttribution
  step_seq: int
  action_type: str
  role: str
  name: str
  predicted_tier: str
  predicted_score: float
  actual_outcome: "SUCCESS" | "FAILED" | "TRANSITION_SUCCESS" | "AMBIGUOUS_IDENTITY" | "ASK" | "BOT_DETECTED"
  failure_reason: Optional[str]
  resolved_by: Optional[str]    (which strategy succeeded)
  recovered_by: Optional[str]   (which fallback was used)
  resolution_depth: Optional[int]  (0=primary, 1=placeholder, 2=nearby, 3=structural)
  resolution_success: Optional[bool]
  execution_success: Optional[bool]
  effect_verified: Optional[bool]
  effect_type: Optional[str]
  effect_details: Optional[Dict]
  failure_layer: Optional[str]  ("resolution" | "execution" | "verification")
  target_integrity: Optional[Dict]  (full forensics)
  resolution_time_ms: Optional[int]
  step_duration_ms: Optional[int]

ReplayReport
  workflow_id: UUID
  template_id: UUID
  status: "SUCCESS" | "FAILED" | "INTERRUPTED" | "BLOCKED"
  total_steps: int
  resolved_steps: int
  failed_steps: int
  ambiguous_steps: int
  resolution_rate: float
  ambiguity_rate: float
  resource_resolution_rate: float
  recovery_rate: Optional[float]
  duration_seconds: float
  failure_reason: Optional[str]
  failure_attribution: List[FailureAttribution]
  state_inference: Optional[StateInference]
  verification_report: Optional[Dict]
  contract_verification: Optional[Dict]
  env_fingerprint_start: Optional[EnvironmentFingerprint]
  env_fingerprint_end: Optional[EnvironmentFingerprint]
```

### Discovery Models

```
CapabilityHypothesis
  invariant_hash: str           (16-char hex, SHA-256 of sorted invariants)
  invariants: List[str]         (sorted intent strings)
  status: "SEED" | "RECURRING" | "EMERGING" | "CANDIDATE" | "PROMOTED" | "REFUTED"
  frequency: int                (total observations)
  environments: List[str]       (distinct env_keys observed on)
  evidence: List[Dict]          (observation records, capped at 50)
  source: str                   ("exploration" | "taxonomy_seed" | ...)
  context_hint: str
  site_category: Optional[str]
  importance_score: float       (computed: frequency × env_diversity × recency)
  transfer_attempts: int
  transfer_successes: int
  first_seen: datetime
  last_seen: datetime

CapabilityRecord
  invariant_hash: str           (same hash as hypothesis)
  invariants: List[str]
  promotion_tier: "CANDIDATE" | "STRONG" | "VALIDATED" | "DEPRECATED"
  transfer_envs: List[str]      (environments where confirmed)
  known_boundaries: List[Dict]  (failure conditions)
  strategy_counts: Dict[str, Dict[str, int]]  (per-strategy success/failure)
  source_templates: List[str]
  contract_verified_ratio: Optional[float]
  human_name: Optional[str]     (annotation only, not identity key)
  source: str
  reuse_count: int
  is_novel: Optional[bool]
```

### Lifecycle Diagrams

```
CapabilityHypothesis lifecycle:
  SEED → (frequency ≥ 3) → RECURRING
       → (≥2 environments) → EMERGING
       → (freq ≥ 5 + ≥2 envs) → CANDIDATE
       → promote() → PROMOTED (+ write CapabilityRecord)
       → refute() → REFUTED

CapabilityRecord lifecycle:
  CANDIDATE → (transfer to ≥2 envs) → STRONG
            → (contract_verified_ratio ≥ 0.80) → VALIDATED
            → failure evidence → DEPRECATED

Execution lifecycle:
  running → paused → running (resume)
  running → succeeded (complete)
  running → failed (fail / max retries)
  failed → running (retry, max 3)
  running → rollback (manual)

RecoveryCandidate lifecycle:
  pending → shadow (testing) → ready (lift confirmed)
  ready → committed (approved via bm recovery candidate approve)
  committed → rolled_back (if negative lift post-commit)
  pending/shadow/ready → rejected
  committed → quarantined (negative post-commit lift)
```

---

## PHASE 7 — RUNTIME FLOW

### Complete Execution Trace: `bm replay start saucedemo_login --env saucedemo`

```
bm replay start "saucedemo_login" --env saucedemo
    │
    ├─ cli.py:replay_start()
    │     ├─ _session(ctx) → KernelSession (loads all components)
    │     ├─ workflow_store.lookup_template("saucedemo_login")
    │     │       └─ reads wf_template/*.json from ~/.browsermind/
    │     ├─ environment_registry.resolve("saucedemo")
    │     │       └─ returns EnvironmentEntry(start_url, family, requires_auth)
    │     ├─ creates WorkflowInstance (transient, no persona binding for replay)
    │     ├─ AuthSession(entry=saucedemo, persona_name="validator", store_dir=...)
    │     │       └─ resolves profile_dir, sets up Playwright context
    │     └─ ReplayEngine(auth_session, outcome_ledger, lesson_reader, ...)
    │
    └─ asyncio.run(engine.replay(entry, template, instance))
            │
            ├─ _start_execution_if_wired()
            │       └─ execution_engine.start_execution(task_id, ...)
            │               └─ policy_engine.evaluate(persona_id, template_id) → "auto"
            │               └─ Execution(status="running")
            │               └─ ExecutionRepository.save_execution()
            │               └─ EventBus.emit("EntityMutated")
            │
            ├─ AuthSession.__aenter__()
            │       └─ playwright.chromium.launch(headless=False)
            │       └─ browser.new_context(storage_state=profile)
            │
            ├─ fingerprint_environment(page) → env_fingerprint_start
            │
            └─ FOR EACH STEP in template.steps:
                    │
                    ├─ step = { action_type, target_role, target_name,
                    │           descriptor: {role, name, accessible_name, ...},
                    │           replayability: {tier, score, reasons},
                    │           seq }
                    │
                    ├─ _pause_event.wait()   (blocks if paused)
                    │
                    ├─ ResourceResolver.resolve(step)
                    │       └─ if step has resource token: VaultWriter.load(persona)
                    │               └─ Fernet.decrypt(token) → plaintext value
                    │
                    ├─ BCPolicyAdapter.predict(role, action, step_seq, env_key)
                    │       └─ loads bc_v2_checkpoint.pt if not loaded
                    │       └─ returns {strategy_label, action_label, ...} or {}
                    │
                    └─ TargetResolver.resolve(page, step, bc_prediction)
                            │
                            ├─ PRIMARY: semantic match on (role, name)
                            │       └─ page.get_by_role(role).filter(has_text=name)
                            │       └─ if candidate_count == 1: RESOLVED
                            │       └─ if candidate_count > 1: AMBIGUOUS_IDENTITY
                            │
                            ├─ FALLBACK R1: container_proximity
                            │       └─ locates by container element context
                            │
                            ├─ FALLBACK R2: by_placeholder
                            │       └─ requires has_placeholder=True in descriptor
                            │
                            ├─ FALLBACK R3: by_text_accessible
                            │       └─ requires has_accessible_name=True
                            │
                            ├─ FALLBACK R4: by_text_content
                            │       └─ requires has_text_content=True
                            │
                            ├─ FALLBACK R5: structural_path
                            │       └─ DOM path matching
                            │
                            ├─ FALLBACK R5b: capability_intent
                            │       └─ requires has_capability_hint=True
                            │
                            └─ MINED STRATEGIES (from RecoveryRegistry)
                                    └─ predicate_matches() → dispatch_strategy()

                    If RESOLVED:
                    ├─ ActionExecutor.execute(page, action_type, locator)
                    │       └─ handles: click, fill, press, navigate, select
                    │       └─ raises ActionTransitionSuccess on URL change
                    │
                    ├─ EffectVerifier.snapshot(page) [before + after]
                    │       └─ records URL, DOM hash, element count
                    │
                    ├─ EffectVerdict: effect_type, confidence, quality_score
                    │
                    └─ FailureAttribution(step_seq, actual_outcome=SUCCESS,
                                          resolved_by, effect_verified, ...)

    After all steps:
    ├─ StateVerifier.collect_evidence(page) → StateEvidence
    ├─ infer_state(evidence) → StateInference
    ├─ ContractVerifier.verify() → contract_verification
    ├─ fingerprint_environment(page) → env_fingerprint_end
    │
    ├─ OutcomeLedger.record(OutcomeRecord(
    │       scope="workflow_instance",
    │       success=True/False,
    │       evidence=resolution_rate_str,
    │       metrics={resolution_rate, total_steps, ...}
    │   ))
    │
    ├─ _close_execution_if_wired(report)
    │
    ├─ LessonReader.refresh_lessons() (if lesson_reader wired)
    │
    └─ return ReplayReport(
            status="SUCCESS"|"FAILED",
            total_steps, resolved_steps, failed_steps,
            resolution_rate,
            failure_attribution=[...per-step records...],
            state_inference, contract_verification,
            env_fingerprint_start, env_fingerprint_end
        )
```

### Exploration Flow: `bm explore --site github --budget 50`

```
bm explore --site github --budget 50
    │
    └─ cli.py:explore()
            ├─ AuthSession for site
            └─ ExplorationHarness.run(ExplorationSpec(site_key="github", budget=50))
                    │
                    ├─ _lookup_site("github")
                    │       └─ SiteRegistry.get("github") → SiteEntry(url, category, difficulty)
                    │
                    ├─ _MinimalExplorationTemplate([navigate, explore], budget=50)
                    │
                    ├─ engine_factory("github") → ReplayEngine(exploration_mode=True)
                    │
                    └─ engine.replay(site, template, instance)
                            │
                            └─ ReplayEngine sees exploration_mode=True
                                    │
                                    └─ navigation step → ExplorerPolicy.run(page, ...)
                                            │
                                            ├─ _detect_bot_wall(page)
                                            ├─ _dismiss_overlays(page)  (cookie banners, modals)
                                            │
                                            ├─ AffordanceDiscoverer.discover(page, SEARCH)
                                            │       └─ finds search inputs, comboboxes
                                            │       └─ returns [Affordance(type, score, locator)]
                                            │
                                            ├─ AffordanceDiscoverer.discover(page, FORM)
                                            ├─ AffordanceDiscoverer.discover(page, FILTER)
                                            ├─ AffordanceDiscoverer.discover(page, NAVIGATION)
                                            │
                                            ├─ FOR EACH (family, affordances):
                                            │       ├─ best_affordance(affordances, min_score=0.5)
                                            │       ├─ _fill_input(page, family, best, seq)
                                            │       │       └─ fills with probe values
                                            │       │          ("bm_probe", "BrowserMind Probe", ...)
                                            │       ├─ _human_pause(80, 250)  (jittered)
                                            │       ├─ _execute_with_retry(page, family, best, seq)
                                            │       │       └─ AffordanceExecutor.execute()
                                            │       │       └─ EffectVerifier.diff(before, after)
                                            │       │       └─ hypothesis_store.observe(...)
                                            │       └─ IF TRANSITION_SUCCESS: _explore_page(depth+1)
                                            │
                                            └─ returns [FailureAttribution, ...]

                    ├─ _extract_completed_intents(attribution)
                    │       └─ PrimitiveNormalizer.normalize(action_type, role, name)
                    │       └─ returns {"auth_login", "search_query_input", ...}
                    │
                    ├─ ExperienceInterpreter.interpret(completed_intents)
                    │       └─ matches against _PATTERN_REGISTRY
                    │       └─ returns [ExperienceLabel("session_authentication", 0.92), ...]
                    │
                    └─ CapabilityHypothesisStore.observe(unknown_intents, env_key="github")
                            └─ creates/updates CapabilityHypothesis
                            └─ _try_graduate() (SEED → RECURRING → EMERGING → CANDIDATE)
```

---

## PHASE 8 — REPLAY ANALYSIS

### ReplayEngine Architecture

The `ReplayEngine` is NOT a general browser agent. It is a **deterministic semantic executor** that:
1. Reads pre-compiled step records from `WorkflowTemplate.steps`
2. Resolves each step's target DOM element via `TargetResolver`
3. Executes the resolved action via `ActionExecutor`
4. Verifies effects via `EffectVerifier`
5. Records per-step attribution to `OutcomeLedger`

It does NOT:
- Use LLMs to decide what to do next
- Explore or adapt to unexpected page states (beyond recovery strategies)
- Handle multi-step context or memory across steps

### TargetResolver (The Critical Component)

The `TargetResolver` is where replay succeeds or fails. It implements a tiered strategy ladder:

| Depth | Strategy | Condition | Implementation |
|---|---|---|---|
| 0 | primary_semantic | Always tried | `page.get_by_role(role).filter(has_text=name)` |
| 0 | loose_semantic | Always tried | Looser name matching |
| 1 | container_proximity | Always tried | Container context narrowing |
| 1 | by_placeholder | `has_placeholder=True` | `input[placeholder~=N]` |
| 2 | by_text_accessible | `has_accessible_name=True` | `aria-label` search |
| 2 | by_text_content | `has_text_content=True` | innerText search |
| 3 | structural_path | `has_dom_path=True` | DOM path matching |
| 4 | affordance_intent | Always | Affordance-based search |
| 4 | capability_intent | `has_capability_hint=True` | Capability-guided search |
| 5+ | MINED | predicate match | From `recovery_ladder.json` |

The `BCPolicyAdapter` can reorder the ladder by shifting the predicted-best strategy to position 0. This is the only learning influence on replay behavior.

### Effect Verifier

`EffectVerifier` captures before/after DOM snapshots and diffs them:
- **URL transition**: `TRANSITION_SUCCESS` if URL changed
- **DOM mutation**: `SUCCESS` if element count changed or specific success signals appeared
- **No visible signal**: `FAILED` with `NO_VISIBLE_SIGNAL` reason
- **Quality score**: 0.0–1.0 based on evidence strength

### Current Replay Strengths

1. **Deterministic resolution** — same template + same page = same result (no randomness)
2. **Multi-strategy fallback** — R1-R5 + mined strategies make resolution robust
3. **Full attribution tracking** — every step outcome is recorded with forensics
4. **Pause/resume** — human intervention supported at step granularity
5. **Profile-warmed sessions** — cookies/auth state persisted in browser profiles

### Current Replay Weaknesses

1. **No adaptive recovery** — if all strategies fail, replay fails; no exploration from failure
2. **No cross-step memory** — each step is independent; no context of prior steps
3. **Static templates** — templates don't update when site structure changes; require recompilation
4. **No LLM fallback** — when DOM structure changes radically, there's no intelligent fallback
5. **Bot detection** — sophisticated anti-bot measures (behavioral fingerprinting, JS challenges) can block replay even with human-like timing
6. **Auth state expiration** — cookie-based profiles expire; no automatic re-authentication flow
7. **JavaScript-heavy SPAs** — race conditions between DOM mutations and step execution are common failure modes

### Replay Readiness Assessment

| Aspect | Status |
|---|---|
| Core mechanics | Production-grade |
| Strategy ladder | Complete (R1-R5 + extensible) |
| Effect verification | Functional but primitive |
| State verification | Implemented, not always wired |
| Contract verification | Implemented, not always triggered |
| Bot detection handling | Partial (Cloudflare auto-bypass, CAPTCHA blocked) |
| Auth recovery | Manual only |
| LLM fallback | None |
| Cross-site transfer | Via TransferArena (experimental) |

---

## PHASE 9 — DISCOVERY SYSTEM DEEP DIVE

### Architecture

The discovery system is composed of:

```
ExplorationSpec (what to explore)
    ↓
ExplorationHarness.run()
    ↓
ExplorerPolicy.run()    ← (drives Playwright autonomously)
    ↓
ExperienceInterpreter.interpret(completed_intents)
    ↓
CapabilityHypothesisStore.observe(unknown_intents)
    ↓
CapabilityHypothesis lifecycle management
    ↓
exploration_targets() → ExplorationSpec.capability_targets (SELF-DIRECTED LOOP)
    ↓
(eventually) promote() → CapabilityRecord
```

### ExplorerPolicy — The Autonomous Agent

The `ExplorerPolicy` is the only component in BrowserMind that acts as an autonomous browser agent in the traditional sense. It:

1. Detects and dismisses overlays (cookie banners, modals, popups) using 20 CSS selectors
2. Checks for bot walls via text/URL scanning with SOFT (Cloudflare, auto-bypass) and HARD (Google block, CAPTCHA) categories
3. Discovers affordances per `IntentFamily` using `AffordanceDiscoverer`
4. Selects the best affordance (min_score=0.5)
5. Fills probe values into inputs (safe, synthetic: "bm_probe", "BrowserMind Probe")
6. Executes actions with one transient-error retry
7. Verifies effects via `EffectVerifier`
8. On `TRANSITION_SUCCESS`, rescans the new page and continues (multi-hop, max depth 3)
9. Records both positive and negative evidence to `CapabilityHypothesisStore`

### ExperienceInterpreter — The Labeler

15 built-in `ExperiencePattern` objects across 4 capability families:

| Family | Patterns |
|---|---|
| authentication | session_authentication, account_registration, password_reset, oauth_delegation |
| search | search_query_executed, faceted_search, content_discovery |
| community | content_published, community_reaction, social_connection, profile_updated |
| form_fill | form_submission, checkout_completed, file_uploaded |
| (none) | media_consumed, site_navigated |

Matching algorithm: ALL required_intents must be present (100% coverage). Confidence = 0.8 + 0.2 × optional_coverage (range: 0.8–1.0). When ≥2 intents are unmatched by any pattern: `unknown_capability_cluster` sentinel.

### Self-Directed Exploration Loop

This is the most sophisticated mechanism in the discovery layer:

```
1. ExplorationHarness runs site with spec.capability_targets = []
2. Unknown intents → CapabilityHypothesisStore.observe()
3. Hypothesis.status advances: SEED → RECURRING (freq≥3)
4. Next exploration cycle: hypothesis_store.exploration_targets()
      returns RECURRING/EMERGING hypotheses
5. These become spec.capability_targets
6. ReplayEngine's ExplorerPolicy prioritizes affordances matching these targets
7. More observations → EMERGING (≥2 envs) → CANDIDATE
8. CANDIDATE → human review → promote() → CapabilityRecord
```

### Capability Taxonomy

30 site categories × ~10 capabilities each ≈ 300 capability keys. Examples:

- `social/oauth_sso_login` — OAuth SSO flow
- `ecommerce/multi_facet_filter` — Filter combination
- `ai/sse_stream_parse` — SSE streaming response parsing
- `frontier/unknown_affordance_hypothesize` — Unknown frontier discovery

The taxonomy pre-seeds `CapabilityHypothesisStore` via `seed_from_taxonomy()` before missions start, giving the explorer a target list.

### Current Discovery Limitations

1. **No LLM interpretation** — experience labeling is rule-based; novel patterns require human promotion
2. **Probe value safety** — fills inputs with synthetic values, risks false positives or inadvertent form submissions on production sites
3. **Single-page depth limit** — max_depth=3 in multi-hop; misses deeply nested capabilities
4. **Auth gating** — `AuthGateError` immediately stops exploration if only AUTH affordances are visible; does not attempt login
5. **Category assignment** — site categories are manually assigned in `site_registry.py`; incorrect categories mean wrong taxonomy seeds
6. **No vision/screenshot** — all discovery is DOM-based; visual elements (Canvas, WebGL) are invisible
7. **No hypothesis consolidation** — similar capabilities with different invariant hashes are not merged; can lead to hypothesis fragmentation

### Cross-Site Transfer

`TransferArena` tests whether a capability observed on site A works on site B. The 4 transfer families (authentication, search, community, form_fill) map to `ExperiencePattern.capability_family`. Transfer works by:
1. Running a capability on source site → generates CapabilityRecord
2. Using `SemanticTransferLayer.transfer()` to adapt the template to target site semantics
3. Measuring resolution rate, effect verification rate on target site

Transfer success depends heavily on how semantically stable the capability is across environments.

---

## PHASE 10 — LEARNING LAYER ANALYSIS

### What Is Active

**BC Training (ACTIVE)**:
- `train_bc_v2.py` — PyTorch 2-head network. Inputs: role_id (embedding), action_id (embedding), site_id (embedding), step_seq (scalar). Outputs: action_type prediction + resolution_strategy prediction.
- `bm dataset export` — extracts OutcomeLedger episodes to JSONL
- `bm self-train` — end-to-end pipeline: export → train → benchmark → deploy (with regression guard)
- `BCPolicyAdapter` — loads checkpoint, serves predictions to `TargetResolver`
- `OutcomeLedger` → `OutcomeRepository` — continuously records step outcomes from replays

**Recovery Mining (ACTIVE)**:
- `bm recovery mine` — mines OutcomeLedger for failure patterns via `FailurePatternMiner`
- `bm recovery sweep` — runs shadow validation, promotes candidates
- `bm recovery monitor` — post-commit monitoring, quarantines negative-lift strategies
- `RecoveryRegistry` — persists and serves the strategy ladder

**Discovery Loop (ACTIVE but dry)**:
- `CapabilityHypothesisStore` — stores/tracks hypotheses across explorations
- `ExplorationHarness` — drives discovery via `ExplorerPolicy`
- `MissionQueue` — queues 500+ site exploration missions

### What Is Experimental/Incomplete

**DAgger (EXPERIMENTAL)**:
- `train_dagger.py` — Interactive teacher learning. Requires human labelers to provide corrective actions during execution. Produces `bcs_v2_checkpoint.pt`. 
- Not currently wired into production replay path.
- Training quality depends on human labeler availability and consistency.

**PPO (EXPERIMENTAL/POSSIBLY FROZEN)**:
- `train_ppo.py` — PPO reinforcement learning. Defines a reward function over replay outcomes.
- No evidence of active training runs producing useful checkpoints.
- The reward function requires well-defined success states, which are hard to specify for arbitrary web tasks.

**Agent Planning Layer (INCOMPLETE)**:
- `browsermind_core/agent/` — Goal decomposition, asset graph, satisfaction planning
- This entire subsystem is NOT wired into any execution path
- Represents an architectural aspiration: given a high-level goal, automatically plan a sequence of capabilities
- Currently: dead code with no callers in production paths

### BC Policy Architecture (train_bc_v2.py)

```python
BCPolicyV2:
  Inputs:
    role_id:    Embedding(11 roles, embed_dim=64)
    action_id:  Embedding(9 actions, embed_dim=64)
    site_id:    Embedding(9 sites, embed_dim=64)
    step_seq:   scalar (capped at 50)
  
  Trunk:
    Linear(64*3+1, 128) → ReLU → Dropout(0.1) → Linear(128, 128) → ReLU
  
  Heads:
    action_head:   Linear(128, 9)   → predicts action_type
    strategy_head: Linear(128, 9)   → predicts resolution_strategy
  
  Loss: CrossEntropy weighted by effect_verified (1.5x verified, 0.5x rejected, 1.0x unknown)
  Optimizer: AdamW, lr=3e-4, weight_decay=1e-4
  Schedule: CosineAnnealingLR
  Early stop: patience=5 epochs
```

Known limitation (documented in source): strategy_head memorizes action_head because in current corpus, action_type is strongly correlated with resolution_strategy (fill→exact_selector, navigate→navigate). The `--strategy-loss-weight 0` flag disables strategy_head loss as workaround.

### Training Data Status

From `bm status` diagnostics:
- Target: 500+ successful episodes
- Evidence threshold: 60%+ effect_verified=True
- Before 500 episodes: model trains but doesn't generalize well
- Before 50 episodes: model should not be trained

The `bm self-train` command includes a regression guard: if new checkpoint causes >5% aggregate success rate regression, it is rejected.

### What Should Remain Frozen

1. **PPO training** — reward function too loosely defined; random exploration in web environments is dangerous (accidental purchases, form submissions, account changes)
2. **`core/` legacy system** — marked FROZEN explicitly; no path back
3. **DAgger** — produces useful data but requires human labelers; automate the labeling loop first
4. **Agent planning layer (`browsermind_core/agent/`)** — architecturally interesting but disconnected; adding it to the execution path would require major integration work

---

## PHASE 11 — HISTORICAL EVOLUTION

### Timeline (Inferred from Code Structure, File Naming, Comments)

**Phase 0 — Original Browser Agent (unknown date)**

Evidence: `core/` directory, `main.py`, `agent_trainer.py` with legacy references.

The system was a simple Playwright-based agent: `IntentDetector` → `TaskDecomposer` → `ActionExecutor`. Intent types: search_docs, summarize_research, monitor_news, compare_prices, track_currency, form_fill, search_interactive, social_post. A first-generation `BCPolicyV1` tried to select actions. The `SessionRecorder` recorded execution sessions.

No principal/persona model. No workflow abstraction. No replay concept.

**Phase 1 — Data Collection and Basic Training**

Evidence: `train_bc.py` (older trainer), `collect_*.py` scripts, `training/graph_dataset.py`.

Realization that heuristic execution needed better decision-making. Started collecting human demonstrations via recording. GraphDataset used graph-structured action representations. `train_bc.py` trained a policy on this graph format.

This phase established: the importance of human demonstrations, the need for structured recording, and the inadequacy of pure heuristics.

**Phase 2 — P2A: Structured Demonstration System**

Evidence: `browsermind_core/recorder/` module (implied by `DemonstrationRepository`, `DemonstrationCompiler` references in CLI), `bm record` commands.

Major architectural shift: demonstrations are now first-class objects with schema. `DemonstrationSession` records actions with `TargetDescriptor`, `RecordingEvidence`, `ReplayabilityAssessment`. `DemonstrationCompiler` transforms recordings into `WorkflowTemplate` objects.

Key innovation: the TargetDescriptor as the atomic unit of element identity, separating the "what we want" from "how we find it".

**Phase 3 — P3A: Replay Engine**

Evidence: `ReplayEngine` class, P3A references in `bm replay`, `TargetResolver` multi-strategy logic.

The core insight: replay can be deterministic if element identity is captured via rich semantic descriptors. `TargetResolver` implements the strategy ladder. `FailureAttribution` tracks every step outcome.

Key innovation: the strategy ladder (semantic → fallback cascade) instead of brittle CSS selectors.

**Phase 3.1 — Replayability Prediction**

Evidence: `ReplayabilityAssessment` schema, `predicted_tier` vs `actual_outcome` in `FailureAttribution`, tier system (HIGH/AMBIGUOUS/UNREPLAYABLE).

The system started predicting which steps would fail before replay. This created the feedback loop: prediction accuracy → training signal.

**Phase 4C — State Verification**

Evidence: `StateEvidence`, `StateInference`, `EnvironmentFingerprint`, `ContractVerifier`, verification_report in `ReplayReport`.

Added post-replay verification: did the goal actually get achieved? Separates "all steps resolved" from "task completed". `EnvironmentFingerprint` distinguishes "workflow broken" from "environment changed".

**Phase 5 — Exploration and Discovery**

Evidence: `ExplorerPolicy`, `ExplorationHarness`, `ExperienceInterpreter`, `CapabilityHypothesisStore`, `MissionQueue`.

The breakthrough: instead of requiring human recording for every site, the system can discover capabilities autonomously. `ExplorerPolicy` runs Playwright autonomously, discovers affordances, executes them safely, and reports what it found. `ExperienceInterpreter` labels discoveries against a pattern library.

**Phase 6 — Capability Knowledge Graph**

Evidence: `CapabilityRecord`, `CapabilityHypothesis`, `CapabilityTaxonomy` (30 categories × ~10 keys).

Formalized the knowledge representation. Capabilities are content-addressed by invariant hash. The 30-category taxonomy pre-seeded the discovery system. Cross-site transfer via `TransferArena`.

**Phase 7 — Learning Loop**

Evidence: `BCPolicyV2`, `train_bc_v2.py`, `BCPolicyAdapter` in runtime, `bm self-train`.

Closed the loop: OutcomeLedger → EpisodeExtractor → BCPolicyV2 training → BCPolicyAdapter biases TargetResolver. The `bm self-train` command automated the pipeline.

**Phase 8 — Data-Driven Recovery**

Evidence: `RecoveryRegistry`, `RecoveryCandidate`, `FailurePatternMiner`, `bm recovery mine/sweep/monitor`.

Moved from hardcoded recovery strategies to data-mined ones. The 5 seed strategies (R1-R5) are still there but the system can now extend them automatically via `bm recovery candidate approve`.

**Phase 9 — Personal Digital OS**

Evidence: `Principal/Persona/Identity/Secret/TrustPolicy` hierarchy, `SecretVault` (Fernet), `PolicyEngine` (zero-trust ABAC), `VaultWriter`, multi-site `MissionQueue`, media adapters (Discord, YouTube, Instagram, Pinterest).

The architectural ambition expanded: BrowserMind is not just a browser automation tool but a Personal Digital Operating System that manages multiple personas' digital identities, credentials, and automated workflows across hundreds of web services.

---

## PHASE 12 — FAILURE ANALYSIS

### Failure 1: Quality Function Collapse

**Evidence**: Project memory (`project_browsermind_bugs.md`), multiple quality audit scripts in `scripts/`.

**Cause**: The quality scoring system for exploration/discovery produced 0.00 for all discovered capabilities. The `quality_score` from `EffectVerifier` was not properly propagating to training data.

**Impact**: BC training had no quality signal; all episodes were weighted equally. The model could not distinguish high-value from low-value demonstrations.

**Fix**: `EffectVerifier.quality_score` calculation was repaired; `effect_verified` flag in OutcomeRecord is now used as training weight (1.5x, 0.5x, 1.0x).

**Current status**: Fixed. `bm status` reports `Effect: X% effect_verified=True (target: 60%+)`.

### Failure 2: Wrong-URL Profile Loading

**Evidence**: Project memory, `scripts/stage1_live_verification.py`.

**Cause**: `AuthSession` was loading the wrong browser profile when multiple environments were registered. The profile directory resolution used `env.key` but the lookup used `env.family`, causing profile mismatch.

**Impact**: Replay sessions started with wrong cookies/auth state; authentication-dependent steps failed immediately.

**Fix**: Profile directory resolution aligned to use consistent key.

**Current status**: Fixed.

### Failure 3: Promotion Gate Never Firing

**Evidence**: Project memory (`Promotion Gate` bug).

**Cause**: `RecoveryCandidateRegistry` promotion gate logic had an off-by-one error in shadow test counting. Candidates accumulated shadow results but never advanced to `ready` status.

**Impact**: Recovery candidates were mined but never promoted; the recovery ladder never extended beyond the seed R1-R5 strategies.

**Fix**: Shadow count comparison fixed.

**Current status**: Fixed.

### Failure 4: Single-Hop Explorer (Multi-Hop Missing)

**Evidence**: Project memory (`single-hop explorer` bug).

**Cause**: `ExplorerPolicy.run()` stopped after the first successful interaction without following navigation transitions to new pages.

**Impact**: Discovery was limited to the landing page; nested capabilities (e.g., clicking "Search" then using search results) were never discovered.

**Fix**: `TRANSITION_SUCCESS` now triggers `_explore_page()` recursion up to depth 3.

**Current status**: Fixed. Multi-hop exploration now operational.

### Failure 5: Strategy Correlation (Architecture Limitation)

**Evidence**: Comment in `train_bc_v2.py`:
> "The strategy_head therefore trains mostly as a memorized function of action_head rather than an independent predictor."

**Cause**: Current corpus has too few multi-strategy attempts on the same (site, role, action) tuples. The training signal for strategy prediction is degenerate.

**Impact**: `strategy_head` of BCPolicyV2 provides no additional value over `action_head`. The model cannot predict "use placeholder strategy instead of semantic strategy for this specific site".

**Fix path**: Corpus diversification needed. More replay attempts on sites where primary_semantic fails. `--strategy-loss-weight 0` as immediate workaround.

**Current status**: Architectural limitation. Unfixed.

### Failure 6: PolicyEngine Not Persisted

**Evidence**: `browsermind_core/managers/policy/policy_engine.py` (18 lines, in-memory dict only).

**Cause**: PolicyEngine stores policies in memory only. No persistence.

**Impact**: After restart, all `bm execution start --policy auto` settings are lost. Policy defaults to "ask" (zero-trust default) for all executions.

**Fix path**: Add persistence to `PolicyEngine`. Could use `LocalJSONPersistenceProvider`.

**Current status**: Known architectural gap.

### Failure 7: Agent Planning Layer Disconnected

**Evidence**: `browsermind_core/agent/` — 10 files, 0 callers in runtime.

**Cause**: The agent planning layer (goal → capability graph → execution plan) was built in isolation without integration into `ReplayEngine` or the CLI execution path.

**Impact**: High-level goal decomposition (e.g., "apply for job at company X") requires manual workflow recording; the planning layer cannot automatically compose capabilities.

**Fix path**: Wire `CapabilityDependencyPlanner` into `ExecutionCoordinator` to auto-compose templates from goal specifications.

**Current status**: Dead code.

### Failure 8: DAgger Not Integrated Into Training Loop

**Evidence**: `train_dagger.py` exists, `bcs_v2_checkpoint.pt` produced separately, not used in `bm self-train`.

**Cause**: DAgger requires live human-in-the-loop labeling. The labeling infrastructure (who labels, how labels are collected, how they feed back) is not automated.

**Impact**: `train_dagger.py` produces a potentially better checkpoint but it's never used in production.

**Current status**: Unused.

### Failure 9: Tauri UI Mismatch with CLI Commands

**Evidence**: `browsermind_ui/views/executions_view.py` (277 lines) vs the CLI's 40+ commands; UI only exposes create/start/inspect execution.

**Cause**: UI development lagged behind CLI development significantly.

**Impact**: Most system capabilities (explore, mission, recovery mining, field registry, benchmark) are CLI-only.

**Current status**: Known gap.

---

## PHASE 13 — CURRENT BOTTLENECKS

### Engineering Bottlenecks

| Rank | Bottleneck | Severity | Impact | Difficulty |
|---|---|---|---|---|
| E1 | Insufficient training corpus (< 500 episodes) | HIGH | Model quality limited | MEDIUM |
| E2 | PolicyEngine not persisted | HIGH | Policy resets on restart | LOW |
| E3 | Agent planning layer disconnected | HIGH | No high-level goal decomposition | HIGH |
| E4 | No auth recovery in replay | HIGH | Expired cookies = silent failures | MEDIUM |
| E5 | No LLM fallback in TargetResolver | HIGH | Unrecoverable structural drift | HIGH |
| E6 | DAgger not automated | MEDIUM | Better training data inaccessible | MEDIUM |
| E7 | Strategy head degenerate | MEDIUM | Model biases are nearly useless | MEDIUM |
| E8 | Media layer not integrated | MEDIUM | Social media automation blocked | MEDIUM |
| E9 | SingletonBCPolicy — process restart needed to reload | LOW | Model update requires restart | LOW |
| E10 | Templates don't auto-update on site change | HIGH | Stale templates = replay failures | HIGH |

### Scientific Bottlenecks

| Rank | Bottleneck | Severity | Impact | Difficulty |
|---|---|---|---|---|
| S1 | No LLM in replay path | HIGH | Cannot adapt to structural changes | HIGH |
| S2 | Effect verification too primitive | HIGH | False success signals in training data | MEDIUM |
| S3 | Experience patterns too few (15) | HIGH | Discovery misses most capabilities | LOW |
| S4 | No cross-persona knowledge sharing | MEDIUM | Each persona rediscovers everything | HIGH |
| S5 | No vision capabilities | HIGH | Canvas/WebGL elements invisible | HIGH |
| S6 | No hypothesis consolidation | MEDIUM | Fragmented capability graph | MEDIUM |
| S7 | Probe values may trigger production effects | HIGH | Safe exploration on live sites | LOW |

### Architectural Bottlenecks

| Rank | Bottleneck | Severity | Impact | Difficulty |
|---|---|---|---|---|
| A1 | Two parallel systems (core/ + browsermind_core/) | MEDIUM | Maintenance overhead | LOW (freeze/delete) |
| A2 | EventBus not persisted | MEDIUM | No event replay/audit across sessions | MEDIUM |
| A3 | In-memory task/execution indexes (_*_index.json) | MEDIUM | No real query capability | MEDIUM |
| A4 | No migration system for schema changes | HIGH | Any schema change may corrupt data | HIGH |
| A5 | Single-process assumption (not thread-safe) | MEDIUM | Cannot run concurrent missions | HIGH |

---

## PHASE 14 — TECHNICAL DEBT AUDIT

### Dead Code

| Category | Files | Impact |
|---|---|---|
| `core/` entire directory | 8+ files (FROZEN) | No impact if deleted |
| `browsermind_core/agent/` | 10 files (0 callers) | Planning layer — no impact if deleted |
| Legacy training scripts | `train_bc.py` (superseded by v2) | Confusion risk |
| `studio_api.py` wrapper | Minimal, delegates to sidecar | Minor duplication |

### Duplicated Logic

| Duplication | Locations |
|---|---|
| Site resolution | `ExplorationHarness._lookup_site()` vs `environment_registry.resolve()` — 3-level fallback chain |
| Mission queue status | Duplicated in `cli.py` and `mission_commands.py` |
| Persona lookup | `_session()._lookup("persona", ...)` vs `persona_manager.lookup_by_name()` |
| Atomic write | `persistence.py`, `capability_hypothesis_store.py`, `recovery_registry.py` — same pattern |
| Policy engine | `browsermind_core/managers/policy/policy_engine.py` vs `browsermind_core/runtime/policy_engine.py` — TWO PolicyEngine implementations |

### Temporary Hacks

| Hack | Location | Evidence |
|---|---|---|
| Synthetic execution_id when engine not wired | `replay_engine.py:113` | `uuid4()` fallback without ExecutionEngine |
| `--strategy-loss-weight 0` recommended | `train_bc_v2.py:17-19` | Documents that strategy_head is degenerate |
| `_session()._lookup()` index files | `cli.py` | Parallel name index beside actual entity store |
| `exclude_pre_stage1` filter in episode extractor | `cli.py:self_train` | Filtering out old-format episodes by flag |

### Stubbed Implementations

| Stub | Location | Notes |
|---|---|---|
| `PersistenceProvider` is ABC | `persistence.py` | Only `LocalJSONPersistenceProvider` implemented; SQLite/Postgres stubs never built |
| `TransferArena` transfer families | `evaluation/transfer_arena.py` | 4 families defined; actual cross-site execution infrastructure partial |
| Media adapters | `media/adapters/` | Classes exist but integration with execution path incomplete |
| Tauri UI | `browsermind_ui_tauri/` | Rust shell present but UI coverage minimal |
| Recovery shadow test | `recovery_promotion_gate.py` | Reads `shadow_results.jsonl` — file may not be populated automatically |

### Over-Engineering

| Aspect | Evidence |
|---|---|
| 30-category capability taxonomy | Most categories never explored; 5 categories cover 80% of use cases |
| Agent planning layer (10 files) | Not wired into any execution path |
| Reward layers | 4 reward layers defined; BC training only uses 1 (effect_verified) |
| `p1_schemas.py` has 20+ entity types | Several (SemanticMemory, EpisodicMemory, ProceduralMemory) not persisted |

---

## PHASE 15 — SECURITY AUDIT

### Credential Security

**Strengths:**
- `SecretVault` uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256)
- Key stored in `{store}/.vault_key` at mode 0600 (best-effort on Windows)
- Key can be provided via `BROWSERMIND_VAULT_KEY` env var (good for CI/CD)
- VaultWriter stores per-persona, per-environment credentials

**Weaknesses:**
1. **Vault key is symmetric** — whoever has `~/.browsermind/.vault_key` has all secrets. No key derivation per persona.
2. **No key rotation mechanism** — changing the vault key requires re-storing all secrets manually.
3. **Windows file permissions** — `os.chmod(key_path, 0o600)` is best-effort on Windows; file may be accessible to other users on shared machines.
4. **PolicyEngine not persisted** — policies are in-memory. After restart, zero-trust default ("ask") applies to everything regardless of prior approvals.
5. **`bm vault get` prints secrets to stdout** — clipboard or terminal log exposure risk.

### Identity Isolation

**Strengths:**
- Persona-level isolation is architectural: `persona_id` scopes all data
- `VaultWriter` stores secrets under `{store}/personas/{persona_name}/vault.json`

**Weaknesses:**
1. **Persona isolation not enforced at API level** — `sidecar.py` has no authentication. Any process that can reach the API can impersonate any persona.
2. **No API authentication** — The FastAPI sidecar has no auth tokens, no session validation, no rate limiting. It assumes local-only access.
3. **Browser profile directories** — Profiles contain raw cookies and localStorage. A system user with access to `~/.browsermind/profiles/` can steal all sessions.

### Session Security

**Strengths:**
- Playwright contexts are persona-scoped
- Profile directories are per-persona

**Weaknesses:**
1. **No credential expiry enforcement** — `Identity.status` can be "active" even when cookies have expired. The system doesn't proactively check.
2. **Probe values in exploration** — `ExplorerPolicy` fills "bm_probe" into form inputs. On some sites this could inadvertently submit forms or trigger rate limiting.

### Policy Enforcement

The `PolicyEngine` implements zero-trust ABAC but:
1. **In-memory only** — resets on restart
2. **Binary policies** — only 3 levels (auto/ask/never); no fine-grained scoping
3. **Template-level only** — cannot enforce policy at step level (e.g., "auto for read, ask for write")
4. **Not enforced in exploration mode** — `ExplorerPolicy` bypasses policy checks

### Data at Rest

**Strengths:**
- `LocalJSONPersistenceProvider` uses atomic writes (temp-file → rename) to prevent partial-write corruption
- SHA-256 checksums on every file; corrupted files return None rather than partial data

**Weaknesses:**
1. **No encryption at rest** — OutcomeLedger, MutationLedger, WorkflowTemplates, CapabilityHypotheses all stored as plaintext JSON
2. **Browser profiles not encrypted** — cookies/localStorage accessible to OS users
3. **Training data not sanitized** — `OutcomeRecord.evidence` may contain scraped page content with PII

### Privilege Boundaries

**Missing:**
- No sandboxing of the Playwright browser (runs with full user permissions)
- No network isolation for exploration (browser can reach any URL)
- No allowlist for sites that ExplorerPolicy can explore autonomously

---

## PHASE 16 — STATE OF THE PROJECT

### Component Scores

| Component | Score | Rationale |
|---|---|---|
| Core Runtime (replay) | 8/10 | Production-grade. Multi-strategy resolver, attribution tracking, effect verification. Missing LLM fallback and auto-recovery on template staleness. |
| Mission Runtime | 7/10 | Functional. MissionQueue, MissionWorker, 500-site campaign support. Missing: automatic auth handling, parallel worker support. |
| Environment Runtime | 7/10 | Solid. EnvironmentRegistry, AuthSession with profile management. Bot detection partial. Auth recovery manual. |
| Replay Runtime | 8/10 | Strong. Deterministic, multi-strategy, attribution-complete. Vulnerable to site structure changes, no LLM escape hatch. |
| Discovery Runtime | 6/10 | Working but limited scope. 15 experience patterns is too few. Multi-hop works. Self-directed loop plumbed. Auth gating blocks most sites. |
| Learning Runtime | 4/10 | Pipeline exists, model trains, strategy_head degenerate. Training data still insufficient for meaningful generalization. Model affects resolver but weakly. |
| Studio / UI | 3/10 | Minimal. PySide6 UI covers ~5% of CLI commands. Tauri wrapper exists. Studio HTML present. |
| Security | 4/10 | SecretVault is real Fernet. No API auth. Policy not persisted. Browser profiles unencrypted. |
| Maintainability | 6/10 | Well-structured. Two duplicate systems. 97 utility scripts with no organization system. Some dead code. |
| Architecture Quality | 7/10 | Excellent ontology. Good separation of concerns. PolicyEngine redundancy. Agent layer disconnected. No migration system. |

### Honest Summary

BrowserMind has a **production-quality replay kernel** built on a **well-designed ontology**. The recording → compilation → replay pipeline works. The discovery system is functional but limited. The learning loop is plumbed but not producing meaningful behavioral improvements yet (strategy head degenerate, corpus too small).

The system is **architecturally ambitious** (Personal Digital OS with 500-site exploration capacity) but **execution reality** is much more modest: reliable replay on ~10 well-tested sites, autonomous discovery that works on open sites (bot walls block most interesting ones), and a closed-loop training system that is technically functioning but not yet producing measurable improvements.

The honest answer to "is BrowserMind learning?" per `bm system status`: **PLUMBED BUT DRY** unless at least one mined recovery strategy has been committed on real-traffic evidence.

---

## PHASE 17 — WHAT BROWSERMIND IS BECOMING

### Evidence-Based Classification

**What the code tells us**, not what docs say:

**Observed (from implementation):**

1. The `Principal → Persona → Identity → Secret` hierarchy is a complete Personal Digital OS identity layer. This is not browser automation infrastructure — this is OS infrastructure.

2. The `MissionQueue` with 500-site campaigns is a **capability discovery platform** architecture, not a workflow engine.

3. The `RecoveryRegistry` with data-mined strategies extending the hardcoded ladder is a **self-improving system** architecture.

4. The `CapabilityTaxonomy` (30 categories × ~10 keys) is a **knowledge graph** about web capabilities, not a script library.

5. The `OutcomeLedger → BCPolicyV2 → BCPolicyAdapter → TargetResolver` loop is a **closed-loop learning system**.

6. The `SecretVault` (Fernet), `PolicyEngine` (zero-trust ABAC), `TrustPolicy` (auto/ask/never) are **digital identity management** primitives.

**Inferred (from architecture patterns):**

The agent planning layer (`browsermind_core/agent/`) represents the intended future: given a high-level goal ("apply for 10 jobs matching my profile"), the system would automatically:
1. Identify required capabilities (session_authentication + ats_field_map + resume_upload)
2. Find matching WorkflowTemplates
3. Resolve persona resources/identities
4. Execute with appropriate trust level

**Conclusion:**

BrowserMind is becoming a **Capability Discovery Platform and Personal Digital Operating System**. It is simultaneously:
- A **Replay Engine** (today's core functionality)
- A **Capability Knowledge Graph** (the taxonomy + hypothesis store)
- A **Digital Identity Manager** (Principal/Persona/Identity/Vault)
- A **Self-Improving Automation System** (OutcomeLedger → BC → Recovery mining)
- A **Web Intelligence Platform** (experience interpretation, cross-site transfer)

It is NOT becoming:
- A traditional RPA tool (no drag-and-drop workflow builder)
- A traditional web scraper (no structured data extraction focus)
- An LLM agent (no LLM in the primary execution path)
- A browser extension (runs as a standalone Python process)

The category nearest to BrowserMind's actual trajectory is: **AI-Native Personal Digital Agent Infrastructure** — the runtime OS layer that lets a user delegate their web activity to an automated system with auditable, reversible, policy-controlled behavior.

---

## PHASE 18 — CRITICAL RECOMMENDATIONS

### Immediate (Next Week)

**MUST DO:**
1. **Delete `core/`** — it is FROZEN, serves as confusion source. Remove references from `main.py` import paths. Clean the repo.
2. **Fix PolicyEngine persistence** — 18-line fix, stores policies in `{store}/policies.json`. Critical for production use.
3. **Fix strategy_head training** — Set `--strategy-loss-weight 0` as default in `bm self-train`. Document that strategy training is deferred until corpus diversifies.
4. **Add `bm doctor` to check vault key permissions** — warn on Windows when `.vault_key` has wrong permissions.

**SHOULD DO:**
1. **Expand ExperienceInterpreter patterns** — 15 patterns is far too few. Add 50+ patterns for the most common site categories. This unblocks hypothesis discovery.
2. **Wire `exploration_targets()` into MissionQueue** — the self-directed loop is implemented but not automatically invoked during missions.

### Near-Term (Next Month)

**MUST DO:**
1. **Add API authentication to sidecar.py** — even a simple static token in `{store}/.api_key`. Without this, the local API is trivially exploitable.
2. **Implement automatic re-authentication** — when `Identity.status` becomes `expired`, trigger re-auth flow rather than failing the replay.
3. **Run 500-site campaign** — the corpus needs real data. Set up a machine, run `bm site add-campaign --limit 500`, let it run.
4. **Consolidate duplicate PolicyEngine** — two PolicyEngine classes (`managers/policy/` and `runtime/`). Pick one. Wire it properly with persistence.

**SHOULD DO:**
1. **Add schema migration system** — even a simple version field in store metadata with migration scripts. Any future schema change will corrupt existing stores without this.
2. **Integrate agent planning layer OR delete it** — `browsermind_core/agent/` has 10 files and 0 callers. Either wire `CapabilityDependencyPlanner` into the execution path or remove it.
3. **Increase experience pattern coverage** — add patterns for ecommerce (checkout, cart), developer (git push, PR creation), jobs (apply, upload resume).

### Mid-Term

**MUST DO:**
1. **Add LLM fallback to TargetResolver** — when all R1-R5 strategies fail AND confidence is below threshold, call an LLM with a screenshot and the TargetDescriptor. This is the missing escape hatch for template staleness.
2. **Automate template staleness detection** — track `EnvironmentFingerprint` across replays; alert when DOM distribution changes significantly (site update detected).
3. **Build corpus diversification pipeline** — generate multi-strategy training examples by intentionally failing primary_semantic on known sites and recording which fallback succeeded.

**SHOULD DO:**
1. **Cross-persona capability sharing** — `CapabilityRecord` is currently per-persona. System-level capability knowledge should be shared (not credentials, but behavioral patterns).
2. **Encrypted at-rest storage** — encrypt `OutcomeLedger`, `WorkflowTemplates`, and capability data. Credentials are encrypted; behavioral data should be too.
3. **Parallel mission execution** — the single-process assumption blocks scaling. Add a multi-worker mission queue.

### Long-Term

**SHOULD DO:**
1. **Replace `LocalJSONPersistenceProvider` with SQLite** — JSON files per entity don't scale. SQLite provides atomicity, querying, and compact storage.
2. **Vision capabilities** — Canvas, WebGL, SVG-heavy sites are invisible to DOM-based exploration. Screenshot-based element detection (via OCR or vision model) unlocks these.
3. **Federated capability graph** — multiple BrowserMind instances sharing anonymized capability records (not credentials) would dramatically accelerate discovery.

### AVOID DOING

1. **DO NOT add general LLM planning without guardrails** — LLM in the critical execution path without a deterministic fallback creates unpredictable behavior. Add it as a fallback layer only.
2. **DO NOT expand PPO training** — web environments are too risky for random exploration. The action space is too large, the reward too sparse, and accidental destructive actions (delete account, submit orders) are catastrophic.
3. **DO NOT build a "no-code" workflow builder** — BrowserMind's power comes from its semantic recording system. A visual workflow builder would produce brittle CSS-selector-based automations that are worse than what the compiler produces.
4. **DO NOT expand the media layer** before the core replay is proven at scale — media adapters for Instagram/Discord are premature; the core capability hasn't been validated on more than a handful of sites.
5. **DO NOT replace Playwright with a custom browser** — the investment would be enormous and Playwright's ecosystem (trace viewer, inspector, mobile emulation) provides too much value.

---

## PHASE 19 — APPENDIX

### Class Dependency Map (Key Classes)

```
KernelSession
  ├── EventBus
  ├── LocalJSONPersistenceProvider
  ├── ExecutionRepository
  ├── LedgerRepository → MutationLedger
  ├── OutcomeRepository → OutcomeLedger
  ├── LessonReader → OutcomeLedger
  ├── BehaviorAuditLog
  ├── PolicyEngine
  ├── SecretVault (Fernet)
  ├── PrincipalManager → EventBus
  ├── PersonaManager → EventBus, LocalJSONPersistenceProvider
  ├── IdentityService → SecretVault
  ├── TaskManager → EventBus
  ├── ExecutionEngine → EventBus, PolicyEngine, ExecutionRepository
  ├── WorkflowStore → LocalJSONPersistenceProvider
  ├── CandidateRegistry → LocalJSONPersistenceProvider
  ├── RecoveryCandidateRegistry → LocalJSONPersistenceProvider
  ├── RecoveryRegistry → disk (recovery_ladder.json)
  ├── AutoPilot → KernelSession
  └── CapabilityHypothesisStore → disk (hypotheses/*.json)

ReplayEngine
  ├── AuthSession → Playwright
  ├── TargetResolver
  │       ├── BCPolicyAdapter → PyTorch (lazy)
  │       └── RecoveryRegistry
  ├── ActionExecutor → Playwright
  ├── ResourceResolver → VaultWriter → SecretVault
  ├── StateVerifier
  ├── ContractVerifier
  ├── OutcomeLedger
  └── ExecutionEngine

ExplorationHarness
  ├── ExperienceInterpreter → _PATTERN_REGISTRY
  ├── CapabilityHypothesisStore
  └── engine_factory() → ReplayEngine
          └── ExplorerPolicy (exploration_mode=True)
                  ├── AffordanceDiscoverer
                  ├── AffordanceExecutor
                  └── EffectVerifier
```

### Runtime Call Graph (Core Execution)

```
bm replay start
  cli.replay_start()
    ReplayEngine.replay(entry, template, instance)
      AuthSession.__aenter__()
        playwright.chromium.launch()
      FOR step IN template.steps:
        ResourceResolver.resolve(step)
          VaultWriter.load(persona)
            Fernet.decrypt()
        BCPolicyAdapter.predict(role, action, step_seq, site)
          BCPolicyV2.forward()
        TargetResolver.resolve(page, step, bc_prediction)
          page.get_by_role(role).filter()
          [FALLBACK R1-R5 cascade if needed]
          RecoveryRegistry.ladder()
        ActionExecutor.execute(page, action_type, locator)
          page.click() / page.fill() / page.press()
        EffectVerifier.diff(before, after)
        OutcomeLedger.record(OutcomeRecord)
          OutcomeRepository.append()
      StateVerifier.collect_evidence(page)
      ContractVerifier.verify()
      ExecutionEngine.complete_execution()
      LessonReader.refresh()
      RETURN ReplayReport
```

### Folder Tree (Condensed)

```
browsermind/
├── bm.py                           CLI entry point
├── main.py                         LEGACY FROZEN
├── train_bc_v2.py                  BC trainer
├── train_dagger.py                 DAgger trainer
├── train_ppo.py                    PPO trainer (experimental)
├── bc_v2_checkpoint.pt             Trained weights
├── browsermind_core/
│   ├── agent/          (10 files)  Goal planning — DISCONNECTED
│   ├── api/            (3 files)   FastAPI sidecar
│   ├── console/        (7 files)   bm CLI
│   ├── errors.py                   Shared exceptions
│   ├── evaluation/     (5 files)   BatchRunner, TransferArena
│   ├── events/         (1 file)    EventBus
│   ├── execution/      (4 files)   ExecutionCoordinator
│   ├── experiments/    (12 files)  ReplayExperimentHarness
│   ├── exploration/    (5 files)   ExplorerPolicy, Harness
│   ├── learning/       (7 files)   CapabilityRecord, Hypothesis
│   ├── ledger/         (6 files)   MutationLedger, OutcomeLedger
│   ├── managers/       (5 files)   Identity, Policy, Principal
│   ├── media/          (9 files)   MediaVault, adapters
│   ├── memory/         (?)         MemoryStore (cross-session)
│   ├── ontology/       (8 files)   p1_schemas, WorkflowStore
│   ├── recorder/       (?)         DemonstrationCompiler
│   ├── registry/       (?)         SiteRegistry
│   ├── representation/ (?)         PrimitiveNormalizer, FallbackLedger
│   ├── runtime/        (38 files)  ReplayEngine, TargetResolver, ...
│   ├── tests/          (1 file)    test_core_lifecycle.py
│   └── training/       (?)         EpisodeExtractor, SystemStatus
├── browsermind_ui/     (8 files)   PySide6 desktop UI
├── browsermind_ui_tauri/           Rust/Tauri shell
├── core/               (8 files)  LEGACY FROZEN
├── training/           (60+ items) Datasets, gold data, sessions
├── scripts/            (97 files) Analysis, audit, generation tools
├── reports/                        Benchmark and audit reports
└── .browsermind/                   Default store dir (runtime data)
```

### File Statistics

| Category | Count | Notes |
|---|---|---|
| Total Python files | ~250+ | Excluding `__pycache__`, `training/` submodules |
| `browsermind_core/` files | ~120 | Active kernel |
| `scripts/` files | 97 | Analysis tooling |
| `training/` Python files | ~40 | Training pipeline |
| `core/` files | ~8 | FROZEN |
| Largest file | `sidecar.py` (1913 lines) | FastAPI server |
| Second largest | `cli.py` (1954 lines) | CLI |
| Third largest | `explorer_policy.py` (830 lines) | Exploration |

### Most Important Files (by System Impact)

1. `browsermind_core/ontology/p1_schemas.py` — The complete type system
2. `browsermind_core/runtime/replay_engine.py` — The execution engine
3. `browsermind_core/runtime/target_resolver.py` — Where replay succeeds or fails
4. `browsermind_core/console/session.py` — Dependency injection root
5. `browsermind_core/console/cli.py` — User-facing interface
6. `browsermind_core/learning/capability_hypothesis_store.py` — Discovery loop state
7. `browsermind_core/runtime/recovery_registry.py` — Self-improving recovery
8. `train_bc_v2.py` — Learning pipeline
9. `browsermind_core/runtime/bc_policy.py` — Model integration point
10. `browsermind_core/runtime/persistence.py` — Storage foundation

### Most Coupled Files

1. `browsermind_core/console/session.py` — imports 18+ kernel components
2. `browsermind_core/runtime/replay_engine.py` — imports 12+ runtime components
3. `browsermind_core/console/cli.py` — 40+ command handlers, imports from nearly all subsystems
4. `browsermind_core/api/sidecar.py` — mirrors entire CLI surface as HTTP endpoints

### Most Risky Files

1. `browsermind_core/runtime/target_resolver.py` — strategy change = immediate quality impact
2. `browsermind_core/ontology/p1_schemas.py` — schema change = data migration required
3. `browsermind_core/runtime/persistence.py` — storage bug = data loss
4. `browsermind_core/managers/identity/secret_vault.py` — key management bug = credential loss
5. `browsermind_core/runtime/replay_engine.py` — logic bug affects all replays

### Central Abstractions (Concepts to Understand First)

For any engineer onboarding to this codebase:

1. **TargetDescriptor** — the atomic identity of a DOM element (role + name + accessible_name + text_content + placeholder + dom_path). Understand this before touching replay.

2. **FailureAttribution** — the record of predicted vs actual outcome per replay step. This is the learning signal. Understand this before touching training.

3. **CapabilityHypothesis** — an unknown intent cluster that may represent a new capability. Understand this before touching discovery.

4. **WorkflowTemplate** — a compiled sequence of semantic steps. Each step has a TargetDescriptor + ReplayabilityAssessment. Understand this before recording or compiling.

5. **KernelSession** — the dependency injection container that wires the entire system. Understand this before adding new components.

---

*End of BROWSERMIND_COMPLETE_ARCHITECTURE.md*

*Generated by: Full codebase analysis covering ~250 Python files, 38 runtime modules, 97 scripts, and 60+ training artifacts.*

*Methodology: Code-first reverse engineering. Every claim traceable to a specific file and line number. Implementation beats documentation wherever they conflict.*
