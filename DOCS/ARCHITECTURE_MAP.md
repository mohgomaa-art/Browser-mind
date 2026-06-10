# BrowserMind — Architecture Reality Map

Date: 2026-06-06. Evidence-only. Tags: PROVEN | PARTIAL | ASSUMED | MISSING | DEAD | EXPERIMENTAL.

Cross-references: see `DOCS/audit_evidence/02_kernel_persistence.md`, `03a_recorder_compiler.md`, `03b_replay_engine.md`, `04_dead_dup_fake.md`, `06_replay_experiment.md`, `08_identity_policy_env.md`, `09_tests_data_training.md`, `14_contradictions_missing.md`.

---

## Component Status Matrix

| # | Component | Status | Evidence | Integration with adjacent systems |
|---|---|---|---|---|
| 1 | Kernel session wiring | PROVEN | `browsermind_core/console/session.py:38-66` constructs single `LocalJSONPersistenceProvider`, shares to ledgers, hydrates `MutationLedger` + `OutcomeLedger` on construct | Wires ledgers, workflow store, vault. Does NOT instantiate `RequirementLedger`. PARTIAL on completeness. |
| 2 | Persistence provider | PROVEN | `browsermind_core/runtime/persistence.py:45-75` JSON + sha256 + atomic temp-rename + Win retries | Used by every ledger and the workflow store. Silent `None` return on checksum mismatch (lines 84-88) — PARTIAL observability. |
| 3 | Storage provider (alt) | DEAD | `browsermind_core/runtime/storage.py:1-40` `LocalJSONStorageProvider` defaults to same `.browsermind_store` dir but no checksum, no atomic write, no caller | Zero importers. Risk of silent fork. |
| 4 | Mutation ledger | PROVEN | `browsermind_core/ledger/mutation_ledger.py:23-29` subscribes `EntityMutated`, hydrates from `LedgerRepository.load_all()` | Confirmed emitters: `cli.py:348-356, 412-420` for workflow create. Manager-level emissions (Persona/Identity/Task) UNVERIFIED in scope. |
| 5 | Outcome ledger | PARTIAL | `browsermind_core/ledger/outcome_ledger.py:32-42` write surface + hydration both exist | **No producer in console scope.** Replay engine does not call `record()`. Only `pilot/kernel_bridge.py:180-192` writes `OutcomeRecord`. |
| 6 | Outcome repository | PROVEN | `browsermind_core/ledger/outcome_repository.py:9-44` JSON-backed with index | Survives restart iff someone calls `record()`. |
| 7 | Requirement ledger | MISSING (persistence) | `browsermind_core/ledger/requirement_ledger.py:23` in-memory list only | Not even instantiated by `KernelSession`. |
| 8 | Workflow store | PROVEN | `browsermind_core/ontology/workflow_store.py:20-23, 121-134` JSON via own provider instance | Two providers point at same dir (workflow_store builds its own). Fields `family_key`, `profile_path` written to JSON but stripped on `model_validate` reads (lines 125, 132-133). PARTIAL. |
| 9 | Execution repository | PROVEN | `browsermind_core/runtime/execution_repository.py:12-78` snapshots + executions persist | `load_all_snapshots` is O(N) on every call (line 53). PARTIAL on perf. |
| 10 | Asset graph | MISSING (persistence) | `browsermind_core/ontology/asset.py:82-105` `AssetGraph` is a dict + `to_dict()` with no I/O | Never imported by ledger/persistence. |
| 11 | P1 schemas | PROVEN (as schema) | `browsermind_core/ontology/p1_schemas.py:1-330` | `Snapshot` (lines 149-155) DEAD — only `SnapshotRecord` is constructed. Duplicate `Environment`/`Persona` shapes vs `asset.py` (CONFLICT). |
| 12 | Resource ontology | PROVEN | `browsermind_core/ontology/resource_ontology.py:1-87` stateless classifier | Falls back to `IDENTITY` (line 86) — silent misclassification risk. |
| 13 | Event bus | PARTIAL | `browsermind_core/runtime/event_bus.py` exposes `subscribe` + `emit` only, no `publish` despite Pub/Sub claim | `EntityMutated` PROVEN wired (5+ publishers → MutationLedger + Qt context). `ExecutionRehydrated` PROVEN orphan (publisher at `execution_engine.py:125`, zero subscribers). |
| 14 | Event package | MISSING | `browsermind_core/events/__init__.py` is a 1-line empty file; the actual EventBus lives at `runtime/event_bus.py` | Misleading package shell. |
| 15 | Semantic recorder (JS) | PARTIAL | `browsermind_core/recorder/semantic_recorder.py:35` h1-h6→heading, `:62-68` value≠name guard for accessible-name path | `getTargetDescriptor:95` reads `el.innerText` for `text_content` with NO `isTextInput` guard — typed input still leaks into `descriptor.text_content`. Value-as-name fix is INCOMPLETE. |
| 16 | Recording evidence flow | DEAD | JS emits `recording_evidence` at `semantic_recorder.py:318`; compiler reads at `demonstration_compiler.py:63` | `record_runner.py:52-67` never copies it to `DemonstrationStep`; compiler always sees `None`. PROVEN dead path. |
| 17 | Demonstration compiler | PARTIAL | `browsermind_core/recorder/demonstration_compiler.py` produces `WorkflowTemplate` from session | English-only CAPTCHA filter `["begin","loading","confirm"]` lines 33-44; can emit 0-step templates with status `compiled` (lines 151-159) — silent regression. |
| 18 | Demonstration session | PROVEN | `browsermind_core/recorder/demonstration_session.py` Pydantic model + repo write | Buffer-only; no incremental flush; crash mid-recording loses everything. |
| 19 | Demonstration repository | PROVEN | `browsermind_core/recorder/demonstration_repository.py` JSON via provider | Tested by `tests/test_demonstration_repository.py`. |
| 20 | Shadow recorder | DEAD | `browsermind_core/recorder/shadow_recorder.py:48` zero external callers | Confirmed by grep. |
| 21 | Replay engine | PROVEN (as resolver) / PARTIAL (as outcome producer) | `browsermind_core/runtime/replay_engine.py:88` async `replay(...)` 13 strategies | Returns `ReplayReport`; CLI prints to stdout (`cli.py:697`). NO write to `OutcomeLedger`. |
| 22 | Target resolver | PROVEN | `browsermind_core/runtime/target_resolver.py:1-714` 13 strategies + R1-R5 recovery + dump-page fallback at 634-646 | The strongest single component. |
| 23 | Action executor (modern) | PROVEN | `browsermind_core/runtime/action_executor.py:17` real Chromium calls | Used by ReplayEngine. No mock mode. |
| 24 | Action executor (legacy) | EXPERIMENTAL | `core/executor.py:387` legacy `ActionExecutor`, 1,868 LOC monolith | Still imported by `main.py`, trainers, `studio_api.py`. Parallel architecture. |
| 25 | Execution coordinator | DEAD | `browsermind_core/execution/execution_coordinator.py` + `playwright_executor.py` + `generic_executor.py` + `outcome_verifier.py` hardcode `base_url="http://127.0.0.1:8090"` test app | Never called by `ReplayEngine` or `cli.py:bm_replay`. |
| 26 | Failure taxonomy | PARTIAL | `browsermind_core/experiments/failure_taxonomy.py:152-153` substring-matches `"target not found"` to produce `TARGET_CHANGED` | Brittle. Couples runtime exception messages to offline analyzer. |
| 27 | TARGET_CHANGED root causes | EXPERIMENTAL | `scripts/target_changed_dossier.py:114-215` post-hoc forensic labeler offline | NAVIGATION_STATE_CHANGE / RECORDER_MISMATCH / ROLE_DRIFT are NOT runtime classifications. |
| 28 | Identity service | PARTIAL | `browsermind_core/managers/identity/identity_service.py` emits events for create | Persistence by event flow. Manager-level persistence not wired in `KernelSession`. |
| 29 | Persona manager | PARTIAL | `browsermind_core/managers/principal/persona_manager.py:10-21` only emits event, never writes | Durable persona storage actually happens as a UI sidecar at `browsermind_ui/core/commands.py:22`. |
| 30 | Principal manager | PARTIAL | 22-line CRUD class, no identity fields beyond name | Not the documented identity model. |
| 31 | Secret vault (memory) | MISSING (security) | `browsermind_core/managers/identity/secret_vault.py:12` `hashlib.sha256(...)` wrapped in `f"ENC[AES256:{...}]"` string | SHA-256 is not encryption. One-way; never decryptable. Mislabeled. |
| 32 | Vault writer (disk) | MISSING (security) | `browsermind_core/runtime/vault_writer.py:63-65,87` writes plaintext via `_provider.save` | No `cryptography`/`Fernet`/`nacl`/`Crypto` import in identity/vault/policy/runtime. |
| 33 | Policy engine (managers) | PARTIAL | `browsermind_core/managers/policy/policy_engine.py` UUID-keyed dict | Static lookup, not ABAC. Wired into Session. |
| 34 | Policy engine (runtime) | PARTIAL/EXPERIMENTAL | `browsermind_core/runtime/policy_engine.py` hardcoded `"alpha"`/`"beta"` rules | Falls through to ALLOW for real persona UUIDs. Enforcement is no-op. |
| 35 | Enforcement | DEAD | `browsermind_core/runtime/enforcement.py` duplicate `SecretVault`, `IdentityService`, "Ownership Matrix" `BaseManager` | Zero importers. |
| 36 | Execution policy gate | MISSING | `browsermind_core/runtime/execution_engine.py:48` evaluates `approval_level` but no `if` denies/pauses/prompts | Execution always proceeds. No enforcement. |
| 37 | Auth session | PARTIAL | `browsermind_core/runtime/auth_session.py` uses `environment_registry.profile_dir` (persona-aware) | But `cli.py:401`, `kernel_bridge.py:59`, `run_workflow_pilot.py` use the persona-less `environment_config.EnvironmentInstanceConfig.profile_dir`. Cross-persona Chrome cookie sharing on these paths. |
| 38 | Environment registry | PARTIAL | `browsermind_core/runtime/environment_registry.py` persona-aware profile_dir | `family` is a free-form string, no Family class, no inheritance. |
| 39 | Environment config | PARTIAL | `browsermind_core/runtime/environment_config.py` `EnvironmentInstanceConfig.profile_dir` | Persona-less; bypasses isolation. |
| 40 | Environment commands CLI | PARTIAL | `browsermind_core/console/environment_commands.py:48` `env_add` warns "Custom environments are session-only" | No persistence path for custom envs. |
| 41 | P7 Flow-Aware Agent | EXPERIMENTAL | `browsermind_core/agent/*` 11 modules: `flow_inference`, `asset_graph`, `environment_binder`, `capability_discovery`, `backward_state_planner`, `path_utility`, `satisfaction_planner`, `capability_dependency_planner`, `router`, `requirement_state_registry` | Consumed only by `scripts/experiments/*` and tests. No runtime path through `cli.py:replay` or `bm replay`. |
| 42 | PolicyRouter executors | DEAD (3 of 4) | `browsermind_core/agent/router.py:147-150` instantiates four executors | `ContextExecutor:128`, `AuthenticatedExecutor:134`, `VisualExecutor:140` are all `raise NotImplementedError`. Only `AccessibilityExecutor` has real bodies. |
| 43 | P5/P6 Representation Gateway | EXPERIMENTAL | `browsermind_core/representation/*` `InvariantCompiler`, `EvidenceLedger`, `RepresentationGateway`, adapters/* | No runtime path. |
| 44 | Memory subsystems | MISSING | `browsermind_core/memory/episode.py`, `procedural.py`, `semantic.py`, `memory_reader.py`, `memory_writer.py` | Not wired into ReplayEngine; no producer/consumer trace from replay path. |
| 45 | Friction observatory | DEAD | `browsermind_core/runtime/friction_observatory.py` `FrictionObservatory` never instantiated | Zero callers. |
| 46 | R0 logger | UNVERIFIED | `browsermind_core/runtime/r0_logger.py` | Not traced; treat as DEAD candidate pending grep. |
| 47 | Affordance modules | UNVERIFIED | `browsermind_core/runtime/affordance.py`, `affordance_discoverer.py`, `affordance_executor.py` | Recovery R5 references "affordance intent"; trace incomplete. |
| 48 | Acquisition runtime | UNVERIFIED | `browsermind_core/runtime/acquisition_runtime.py` | Not traced; DEAD candidate. |
| 49 | Intent family | UNVERIFIED | `browsermind_core/runtime/intent_family.py` | Recovery R5 references it; trace incomplete. |
| 50 | Semantic transfer | UNVERIFIED | `browsermind_core/runtime/semantic_transfer.py` | Not traced; DEAD candidate. |
| 51 | ContractVerifier | PARTIAL | `scripts/experiments/p8a_task_contracts.py:217-310` URL substring + element visibility | Applied to both BrowserMind (`p8a_baseline_challenge.py:274`) AND baseline (`:484`); however contracts are encoded around BrowserMind happy-path URLs. |
| 52 | P8A baseline agent | DEAD | `scripts/experiments/p8a_baseline_agent.py:28` hardcodes `model_name="gemini-3.5-flash"` (invalid id) | Could not have run successfully even with a key. |
| 53 | P8A test server | PROVEN | `scripts/experiments/p8a_test_server.py` 453 lines | Used by experiment harness. |
| 54 | Recovery tests | PARTIAL | `browsermind_core/tests/test_execution_recovery.py` (4 fns) + `test_failure_recovery.py` (2 fns) = 6 tests, not 7 | None spawn a new process; reuse same in-memory `ExecutionRepository` (`test_execution_recovery.py:55-59`). FALSE persistence test. |
| 55 | Browser tests | MISSING | Zero real Playwright in `browsermind_core/tests/` | Only string-literal mentions. Heavy mocking (`test_identity_runtime_consolidation.py:10` 27 mock uses; `test_boundary_awareness.py` 13 hand-rolled mocks). |
| 56 | Gold dataset | MISSING (training-ready) | `training/gold/samples.json` empty (`gold_report.json:7-9` `accepted=0, rejected=3359`) | Pipeline produced zero accepted samples. |
| 57 | Gold v2 dataset | PARTIAL | `training/gold_v2/samples.json` 10 samples all `action_id=0` (navigate) | `meta_verifier_report.json:30-35` `quality_gates.passes=false`. Synthetic seeds, not demos. |
| 58 | Capability taxonomy | EXPERIMENTAL | `training/capability_taxonomy_v1.json` referenced only by `training/capability_taxonomy.py:21` and `scripts/value_audit.py:135` | Zero hits in `browsermind_core/`. Runtime does not use it. |
| 59 | R2D taxonomy | MISSING | grep `R2D|reality.*taxonomy` returns zero hits in `**/*.{py,md}` (excluding node_modules) | Documented but not implemented. |
| 60 | Failure ledger | MISSING | `find . -name "failure_ledger*"` returns nothing | Not present. |
| 61 | BC trainer | PARTIAL | `train_bc.py:196-268` real PyTorch | Reads from `training/spec_sessions/` which does not exist. Practical use requires `--allow-unaudited` (`train_bc.py:454-457`). |
| 62 | DAgger trainer | PARTIAL | `train_dagger.py:269` imports `playwright.async_api` | Real Playwright loop. Consumes legacy `core/*` recorder schemas. |
| 63 | PPO trainer | PARTIAL | `train_ppo.py:25-26` real Playwright | Same legacy schema dependency. |
| 64 | CLI (`bm`) | PROVEN | `browsermind_core/console/cli.py:1-714` Click app | 714-line monolith. Some commands fabricate UUIDs for missing entities (cli.py:472-473, 678). |
| 65 | Qt UI | PROVEN (as UI shell) | `browsermind_ui/main.py`, `views/*`, `core/commands.py` | UI sidecar persists Persona at `commands.py:22` (workaround for missing manager-level persistence). |

---

## Integration Status Across Adjacent Boundaries

| Producer → Consumer | Schemas match? | Status | Evidence |
|---|---|---|---|
| Recorder (JS) → DemonstrationStep | NO | PARTIAL | `recording_evidence` emitted by JS, never copied by `record_runner.py:52-67`; compiler always reads `None`. |
| DemonstrationSession → DemonstrationCompiler | YES (Pydantic) | PROVEN | Round-trip via `model_dump`/`model_validate`. |
| DemonstrationCompiler → WorkflowTemplate | YES | PROVEN | But can emit 0-step template with status `compiled`. |
| WorkflowTemplate → ReplayEngine | YES | PROVEN | `replay(template, ...)` consumes it directly. |
| ReplayEngine → OutcomeLedger | NO WIRE | MISSING | `grep` over `replay_engine.py` for `OutcomeRecord|outcome_ledger` returns zero. |
| ReplayEngine → ExecutionEngine | NO WIRE | MISSING | `start_execution`/`complete_execution` never called by ReplayEngine. |
| ReplayEngine → FailureTaxonomy | YES (string-coupled) | PARTIAL | Substring match on exception text. |
| ContractVerifier → Report | YES | PROVEN | But P8A baseline is DEAD (invalid model id). |
| TargetChangedClassifier → ReplayEngine | NO (offline only) | EXPERIMENTAL | `scripts/target_changed_dossier.py` is post-hoc; runtime emits only typed exceptions. |
| Two parallel architectures (`core/*` vs `browsermind_core/*`) | NO | DUPLICATION | Three `SessionRecorder` classes (core/recorder.py:32, collect_massive.py:155, collect_and_train.py:134); two `ActionExecutor` classes (core/executor.py:387, browsermind_core/runtime/action_executor.py:17). |

---

## Subsystem Verdict Summary

- **PROVEN core**: persistence, mutation ledger, workflow store, target resolver (13 strategies), action executor, semantic recorder (partial), CLI shell.
- **PARTIAL/STUBBED**: outcome ledger (no producer), policy engine (no enforcement), persona/principal (no manager persistence), vault (no crypto), environment family (string tag only), failure taxonomy (substring match), recovery tests (6 not 7, no process restart).
- **DEAD**: storage.py, shadow_recorder.py, friction_observatory.py, training/step_recorder.py, enforcement.py, three of four PolicyRouter executors, the entire `browsermind_core/execution/*` coordinator stack, P8A baseline agent.
- **EXPERIMENTAL**: P7 agent stack (`browsermind_core/agent/*`), P5/P6 representation stack (`browsermind_core/representation/*`), capability taxonomy.
- **MISSING**: replay→ledger wire, R2D taxonomy, failure_ledger, real ABAC, real encryption, persona browser-profile isolation on CLI/pilot paths, PersonaShareGrant/IsolationLevel/CrossPersonaPolicy, IntentTimeline/IntentValidator, SelectorFingerprint multi-strategy resolver class, ExecutionStateMachine, AmbiguityClassifier/Resolver.

End.
