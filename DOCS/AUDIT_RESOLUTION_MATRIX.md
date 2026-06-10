# BrowserMind — Audit Resolution Matrix

Date: 2026-06-06. No code changes. Classification + planning only.

This consolidates every finding from `DOCS/audit_evidence/{02,03a,03b,04,06,08,09,14}.md` and assigns each a disposition.

---

## Classification Definitions

| Tag | Meaning | When to use |
|---|---|---|
| **FIX NOW** | Schedule into the next 1-2 sprints. High impact × risk; effort low-to-medium. | Bug fixes, critical wires, security mislabeling. |
| **FREEZE** | Stop new work on this. Code stays in place; no new commits, no removal yet. | Experimental stacks with no runtime path; legacy-but-still-used architectures. |
| **DELETE** | Confirmed dead, no callers, no migration cost. Remove from repo. | Files with verified zero importers and no replacement plan. |
| **DOCUMENT** | The bug is a documentation claim, not a code defect. Fix in the doc, not in code. | False headlines, inflated counts, mislabeled subsystems. |
| **DEFER** | Real issue but blocked by, or lower-priority than, FIX NOW items. Revisit after they land. | Hardening, new system construction, performance work, far-roadmap items. |

Scoring: `Impact (1-10) × Risk (1-10) / Effort (1-10) = Priority`. Higher = sooner.

---

## A. Replay Measurement Loop

| ID | Finding | Cite | Impact | Risk | Effort | Class | Recommended Action |
|---|---|---|---:|---:|---:|---|---|
| A-1 | ReplayEngine writes no `OutcomeRecord`; `cli.py:bm_replay` prints `ReplayReport` to stdout and discards | `browsermind_core/runtime/replay_engine.py` (zero `OutcomeRecord` hits); `browsermind_core/console/cli.py:697` | 10 | 10 | 3 | **FIX NOW** | First sprint. Define the per-step / per-run `OutcomeRecord` schema; insert a single producer call inside the replay loop. Single largest unblocker in the repo. |
| A-2 | `replay_engine.py:599-601` treats locator-evaluate exception as `ELEMENT_DISAPPEARED, effect_verified=True` | `browsermind_core/runtime/replay_engine.py:599-601` | 10 | 9 | 2 | **FIX NOW** | Same sprint as A-1. Until this is fixed, every measurement that depends on `effect_verified` is poisoned. |
| A-3 | ReplayEngine does not call `ExecutionEngine.start_execution`/`complete_execution`; no episode rows | `browsermind_core/runtime/execution_engine.py`; replay path | 9 | 8 | 4 | **FIX NOW** | Sprint 2 of measurement work. Episode rows are the unit of audit, of policy, and (later) of RL. |
| A-4 | Failure taxonomy substring-matches runtime exception text to produce `TARGET_CHANGED` | `browsermind_core/experiments/failure_taxonomy.py:152-153` | 8 | 7 | 4 | **FIX NOW** | Replace with typed-exception dispatch from a `ReplayException` hierarchy. Couples to A-1 for clean classification at write time. |
| A-5 | TARGET_CHANGED root-cause attribution (NAVIGATION_STATE_CHANGE / RECORDER_MISMATCH / ROLE_DRIFT) is post-hoc, offline-only | `scripts/target_changed_dossier.py:114-215` | 7 | 7 | 6 | **DEFER** | After A-1 / A-4 land, promote runtime classification. Don't bring it forward earlier — it's only useful once the ledger is producing rows. |
| A-6 | `replay_engine.py:_resolve_input` (line 56) is a DEAD helper; `ResourceResolver.resolve_input` is used instead at line 392 | `browsermind_core/runtime/replay_engine.py:56` | 2 | 2 | 1 | **DELETE** | Remove the dead helper to reduce surface area. |
| A-7 | ~25 bare `except: pass` / print-only blocks across replay path swallow errors silently | `replay_engine.py`, `target_resolver.py`, `affordance_executor.py`, `affordance_discoverer.py`, `memory_*.py`, `auth_session.py`, `acquisition_runtime.py` | 7 | 7 | 7 | **DEFER** | Audit + tighten as a follow-up to A-1. Doing this before the ledger exists is premature; you'd be funneling errors into a sink. |
| A-8 | `browsermind_core/execution/*` coordinator stack (`execution_coordinator.py`, `playwright_executor.py`, `generic_executor.py`, `outcome_verifier.py`) hardcodes `base_url="http://127.0.0.1:8090"`; never called by ReplayEngine or CLI | `browsermind_core/execution/*` | 6 | 6 | 2 | **FREEZE** | No new code here. Decision after Roadmap Next bucket: delete or reintegrate. |

---

## B. Recorder & Compiler

| ID | Finding | Cite | Impact | Risk | Effort | Class | Recommended Action |
|---|---|---|---:|---:|---:|---|---|
| B-1 | `recording_evidence` emitted by JS observer never copied into `DemonstrationStep`; compiler always reads `None` | `browsermind_core/recorder/semantic_recorder.py:318` (emit), `record_runner.py:52-67` (drop), `demonstration_compiler.py:63` (read) | 7 | 9 | 1 | **FIX NOW** | Add the field to the Pydantic model and copy it through. ~10 lines. |
| B-2 | `isTextInput` guard exists for accessible-name path but `getTargetDescriptor` reads `el.innerText` for `text_content` with no guard — typed user input leaks | `browsermind_core/recorder/semantic_recorder.py:62-68` (guarded), `:95` (unguarded) | 8 | 8 | 1 | **FIX NOW** | Privacy + name-confusion. One-line guard. |
| B-3 | `DemonstrationCompiler` filters CAPTCHA by hardcoded English string list; will drop legit "Confirm" buttons and miss non-English CAPTCHAs | `browsermind_core/recorder/demonstration_compiler.py:33-44` | 6 | 6 | 3 | **DEFER** | Address after B-1/B-2/B-4. Less common than the silent leak. |
| B-4 | Compiler can emit a 0-step `WorkflowTemplate` and still emits `EntityMutated` with `status: "compiled"` | `browsermind_core/recorder/demonstration_compiler.py:151-159` | 7 | 7 | 1 | **FIX NOW** | Add a length check before emit. Silent regression if left. |
| B-5 | All recording JS handlers wrap reads in `try/catch` that returns empty string on error; page errors silently produce blank-role/blank-name steps | `semantic_recorder.py: 49, 72, 85, 136, 149, 162, 183, 205, 222, 264, 323` | 6 | 6 | 4 | **DEFER** | Replace blanket-catch with structured error reporting after B-1 lands (so errors have a place to go). |
| B-6 | `RecordRunner` buffers all steps in memory until user presses Enter; crash mid-recording loses entire session | `browsermind_core/recorder/record_runner.py:111` | 5 | 5 | 4 | **DEFER** | Add incremental flush after B-1 / B-2 land. Lower priority — recordings are short. |
| B-7 | `WorkflowTemplate` `family_key`, `environment_family`, `environment_instance`, `profile_path` written to JSON blob but stripped on `model_validate` | `browsermind_core/ontology/workflow_store.py:55-58, 81-83 (write), 125, 132-133 (strip)` | 7 | 6 | 2 | **FIX NOW** | Two options: extend the Pydantic model, or stop writing the fields. Fields are silently lost today. |
| B-8 | `ShadowRecorder` class (`browsermind_core/recorder/shadow_recorder.py:48`) has zero external callers | `shadow_recorder.py` | 3 | 3 | 1 | **DELETE** | Remove the file. |

---

## C. Security & Identity

| ID | Finding | Cite | Impact | Risk | Effort | Class | Recommended Action |
|---|---|---|---:|---:|---:|---|---|
| C-1 | `SecretVault` uses `hashlib.sha256(...)` wrapped in `f"ENC[AES256:{...}]"` string. SHA-256 is one-way; never decryptable. | `browsermind_core/managers/identity/secret_vault.py:12` | 10 | 9 | 4 | **FIX NOW** | Either replace with real `cryptography.Fernet` (Roadmap Later L-1) **or** remove all "encrypted vault" claims from documentation **and** label the surface "no encryption — research only" until L-1 ships. Cannot stay as-is — code lies about what it does. |
| C-2 | `VaultWriter.set_secret` writes plaintext via `_provider.save` | `browsermind_core/runtime/vault_writer.py:63-65, 87` | 10 | 9 | 4 | **FIX NOW** | Same disposition as C-1 — fix or de-claim. Inconsistent with C-1 (in-memory hashes, on-disk plaintext). |
| C-3 | `runtime/policy_engine.py` hardcodes `"alpha"`/`"beta"` rules; falls through to ALLOW for real persona UUIDs | `browsermind_core/runtime/policy_engine.py` | 10 | 9 | 5 | **FIX NOW** | Disable the runtime policy engine and route everything through `managers/policy/policy_engine.py`, OR build a real ABAC evaluator. The current state is silent ALLOW — worse than no engine. |
| C-4 | `ExecutionEngine.start_execution` evaluates `approval_level` at line 48 but no `if` denies / pauses / prompts; execution always proceeds | `browsermind_core/runtime/execution_engine.py:48` | 9 | 8 | 3 | **FIX NOW** | Smallest change with the largest effect: gate the call. Even a hard-deny on a single sentinel rule proves the wire works. |
| C-5 | `runtime/enforcement.py` defines duplicate `SecretVault`, `IdentityService`, "Ownership Matrix" `BaseManager`; zero importers | `browsermind_core/runtime/enforcement.py` | 4 | 4 | 1 | **DELETE** | Remove the file. Confusing fork. |
| C-6 | `PersonaManager` only emits an event; durable persona storage is a UI sidecar at `browsermind_ui/core/commands.py:22` | `browsermind_core/managers/principal/persona_manager.py:10-21` | 6 | 8 | 2 | **FIX NOW** | Move persistence into the manager. UI sidecar should not be the source of truth for backend state. |
| C-7 | `replay start` injects synthetic `persona_id=uuid4()` | `browsermind_core/console/cli.py:678` | 9 | 8 | 2 | **FIX NOW** | Replace with real persona resolution from the registered persona index. |
| C-8 | CLI/pilot paths use persona-less `EnvironmentInstanceConfig.profile_dir` (Chrome cookies shared across personas); persona-aware path exists in `environment_registry.profile_dir` | `browsermind_core/console/cli.py:401`, `browsermind_core/pilot/kernel_bridge.py:59`, `run_workflow_pilot.py` | 9 | 8 | 3 | **FIX NOW** | Switch CLI/pilot paths to the persona-aware accessor. |
| C-9 | No authorization check on `persona_id` argument; vault file isolation is only as strong as the caller-supplied string | identity/policy chain | 8 | 7 | 4 | **DEFER** | Closes after C-3 + C-4 land. Without policy enforcement, this gate is moot. |
| C-10 | Two PolicyEngine implementations (`managers/policy/policy_engine.py` UUID-keyed dict + `runtime/policy_engine.py` hardcoded rules) | both files | 7 | 7 | 5 | **FREEZE** runtime engine, **FIX NOW** managers engine | Disable runtime engine in wiring (C-3); evolve managers engine into the real ABAC. |
| C-11 | `ExecutionEngine.start_execution` accepts arbitrary `persona_id` with no membership check | `browsermind_core/runtime/execution_engine.py` | 7 | 7 | 3 | **FIX NOW** | Add a simple "persona exists in `_persona_index.json`" guard. Pre-cursor to C-9. |
| C-12 | `Family / Instance` is a free-form `family: str` tag; no Family class, no inheritance, no shared capability set | `browsermind_core/runtime/environment_registry.py`, `environment_config.py` | 5 | 4 | 7 | **DEFER** | Build only when a second site needs to share a family. Premature today. |
| C-13 | No hardcoded production credentials in repo | grep | — | — | — | **DOCUMENT** | Note this as a clean finding; the test-site fixtures (saucedemo / the-internet) are correctly in test scope. |

---

## D. Documentation Contradictions

These findings are not code defects. The code is what it is; the documentation describes something else. Fix in documentation, not code.

| ID | Finding | Cite | Impact | Risk | Effort | Class | Recommended Action |
|---|---|---|---:|---:|---:|---|---|
| D-1 | "BrowserMind P8A 7/9 vs Baseline 0/9" — artifact shows BM 9/9 (`success_rate.browsermind=1.0`) and baseline `Skipped due to missing GEMINI_API_KEY` on every task with `execution_time_ms=0, llm_calls=0` | `reports/survivability/p8a_baseline_challenge.json` vs `DOCS/research/STATE_OF_PROJECT_JUNE_2026.md` | 7 | 9 | 1 | **DOCUMENT** | Reissue the headline. Either (a) baseline never ran, comparison void, or (b) re-run with valid credentials. |
| D-2 | "Replay Dataset v1: 45 steps, 14 runs" — actual `reports/forensic/combined_ledger_v2.md:3` shows 205 steps / 41 runs / RESOLVED 150; `reports/replay_experiments/` shows 54 runs / 276 steps. Three mutually-inconsistent numbers. | as cited | 7 | 9 | 1 | **DOCUMENT** | Reissue with the artifact-true numbers. Pick one source of truth. |
| D-3 | "7/7 recovery tests pass" — pytest collects 6 tests (4 in `test_execution_recovery.py` + 2 in `test_failure_recovery.py`) | `browsermind_core/tests/test_execution_recovery.py`, `test_failure_recovery.py` | 6 | 8 | 1 | **DOCUMENT** | Correct to "6/6". |
| D-4 | "Resolution rate improved 0.14 → 0.57" — true historically (`reports/replay_experiments_v2/`) but stale; current `reports/replay_experiments/` shows demoqa = 1.0 | as cited | 5 | 6 | 1 | **DOCUMENT** | Either remove the headline as stale or reissue with the latest measurement. |
| D-5 | "Gate 1 passed (2/2)" — passed via operator y/n self-attestation in `run_p2b_validation.py:46-49` | `environment_validation_report.json` | 5 | 6 | 1 | **DOCUMENT** | Add a footnote: "Gate 1 result is operator self-attested; not a unit-test pass." |
| D-6 | "Gate 3 passed (similarity 1.0)" — function exists at `run_p2b_validation.py:109` but no committed JSON artifact | grep | 4 | 5 | 1 | **DOCUMENT** | Mark as UNVERIFIED until a committed artifact lands. |
| D-7 | "BC training is ready" — `train_bc.py` reads `training/spec_sessions/` which doesn't exist; only `gold_v2/` is populated (10 synthetic action_id=0 samples; meta-verifier gate fails) | `train_bc.py:196-268`; `training/gold_v2/meta_verifier_report.json:30-35` | 7 | 7 | 1 | **DOCUMENT** | Reframe as "BC infrastructure exists; data preconditions not met." Use TRAINING_READINESS.md as the source. |
| D-8 | "RL is the next phase" — inconsistent with the locked decision "No BC before G7" in the same plan, and the never-met 80% replay gate | `DOCS/BrowserMind_Implementation_Plan.md:690` | 6 | 6 | 1 | **DOCUMENT** | Resolve the internal contradiction explicitly in the plan. |
| D-9 | "Personal Web OS — encrypted vault, ABAC, persona isolation, intent lifecycle" framing in roadmap docs | multiple docs | 8 | 8 | 2 | **DOCUMENT** | Either ship the conditions in C-1, C-2, C-3, C-4 or remove the framing from product surface until they ship. Cannot keep the framing while the code is stubs. |
| D-10 | `STATE_OF_PROJECT_JUNE_2026.md` cites Replay Dataset row counts that match no committed file | as cited | 7 | 9 | 1 | **DOCUMENT** | Replace with auto-generated section from the (future) `OutcomeLedger`. Stop hand-writing numbers. |

---

## E. Confirmed Dead Code

Zero callers, no migration cost. Safe to remove after a final grep pass on the day of removal.

| ID | File | Cite | Class | Recommended Action |
|---|---|---|---|---|
| E-1 | `browsermind_core/runtime/storage.py` (`StorageProvider`, `LocalJSONStorageProvider`) — fully superseded by `persistence.py`; same default dir | `04_dead_dup_fake.md` | **DELETE** | Remove file. |
| E-2 | `browsermind_core/runtime/friction_observatory.py` — never instantiated | `04_dead_dup_fake.md` | **DELETE** | Remove file. |
| E-3 | `browsermind_core/runtime/enforcement.py` — duplicate stubs, zero importers | `08_identity_policy_env.md` | **DELETE** | Remove file. |
| E-4 | `browsermind_core/recorder/shadow_recorder.py` — `ShadowRecorder` zero external callers | `04_dead_dup_fake.md` | **DELETE** | Remove file. |
| E-5 | `training/step_recorder.py` — `StepRecorder` never instantiated | `04_dead_dup_fake.md` | **DELETE** | Remove file. |
| E-6 | `browsermind_core/runtime/replay_engine.py:56` `_resolve_input` — dead helper | A-6 above | **DELETE** | Remove the helper (surgical change). |
| E-7 | `browsermind_core/ontology/p1_schemas.py:149-155` `Snapshot` class — only `SnapshotRecord` is used | `02_kernel_persistence.md` | **DELETE** | Remove class; sweep imports. |
| E-8 | `browsermind_core/events/__init__.py` (1-line empty file; EventBus actually at `runtime/event_bus.py`) | `02_kernel_persistence.md` | **DELETE** | Remove the misleading empty package shell, or repurpose as a re-export. |
| E-9 | `browsermind_core/agent/router.py:128, 134, 140` `ContextExecutor`, `AuthenticatedExecutor`, `VisualExecutor` — all `raise NotImplementedError` | `04_dead_dup_fake.md` | **DELETE** | Remove the three stubs and the constructor calls at `:147-150`. Leave `AccessibilityExecutor` (the only real one). |
| E-10 | `ExecutionRehydrated` event publisher at `browsermind_core/runtime/execution_engine.py:125` — zero subscribers | `04_dead_dup_fake.md` | **DELETE** or **DEFER** | Either remove the publisher or add a real subscriber when persistence-recovery telemetry exists. Default: DELETE in cleanup pass. |

---

## F. Experimental / Frozen Stacks

These stacks have no runtime path today. They are tested but not consumed by `cli.py:bm_replay` or any product surface. Continuing to invest here without first closing the measurement loop is anti-leverage.

| ID | Stack | Cite | Class | Recommended Action |
|---|---|---|---|---|
| F-1 | `browsermind_core/agent/*` (P7 Flow-Aware Agent, 11 modules: `flow_inference`, `asset_graph`, `environment_binder`, `capability_discovery`, `backward_state_planner`, `path_utility`, `satisfaction_planner`, `capability_dependency_planner`, `policy_router`, `requirement_state_registry`) — consumed only by `scripts/experiments/*` and tests | `04_dead_dup_fake.md` | **FREEZE** | No new commits. Existing tests stay green. After A-1/A-2/A-3 land and the ledger is real, re-evaluate which modules earn integration. |
| F-2 | `browsermind_core/representation/*` (P5/P6 Representation Gateway: `InvariantCompiler`, `EvidenceLedger`, `RepresentationGateway`, adapters/*) — no runtime path | `04_dead_dup_fake.md` | **FREEZE** | Same disposition as F-1. |
| F-3 | `browsermind_core/execution/*` (`execution_coordinator`, `playwright_executor`, `generic_executor`, `outcome_verifier`) — hardcoded `127.0.0.1:8090` mock app, never called from ReplayEngine or CLI | `03b_replay_engine.md` | **FREEZE** | Decide after Roadmap Next: delete or reintegrate. |
| F-4 | Two parallel architectures (`core/*` vs `browsermind_core/*`); legacy `core/*` still imported by `main.py`, `agent_trainer.py`, `train_dagger.py`, `train_ppo.py`, `pipeline/*`, `studio_api.py`, 13+ files | `04_dead_dup_fake.md` | **FREEZE** legacy `core/*`; **FIX NOW** governance | No new commits to `core/*`. Banner top-of-file. Trainers migrated in Roadmap Later L-6. |
| F-5 | Three `SessionRecorder` classes (`core/recorder.py:32`, `collect_massive.py:155`, `collect_and_train.py:134`) | `04_dead_dup_fake.md` | **FREEZE** | Pick one (modern), freeze the other two. Migration in Roadmap Later. |
| F-6 | Two `ActionExecutor` classes (`core/executor.py:387` legacy, `browsermind_core/runtime/action_executor.py:17` modern) | `04_dead_dup_fake.md` | **FREEZE** legacy | Modern is the production path. |
| F-7 | `runtime/policy_engine.py` (hardcoded alpha/beta) — disable in wiring, leave file in place pending C-3 | C-3 / C-10 above | **FREEZE** | Stop calling it; route through managers engine. Delete only after C-3 lands. |
| F-8 | `core/executor.py` (1,868 LOC), `core/decision_engine.py`, `core/recorder.py`, `core/validator.py` — entire legacy fork | `04_dead_dup_fake.md` | **FREEZE** | Frozen as a stack until trainer migration is done. |

---

## G. Tests

| ID | Finding | Cite | Impact | Risk | Effort | Class | Recommended Action |
|---|---|---|---:|---:|---:|---|---|
| G-1 | "7/7 recovery tests" — only 6 collected; none spawn a new process; all reuse same in-memory `ExecutionRepository` object | `test_execution_recovery.py:55-59` | 7 | 8 | 2 | **DOCUMENT** + **FIX NOW** | Document the count (D-3), then make at least one test actually fork a subprocess and reload from disk. |
| G-2 | Zero real Playwright in `browsermind_core/tests/` | grep | 7 | 7 | 5 | **DEFER** | Real Playwright tests pay off after A-1. Without a ledger, browser tests prove call-site behavior, not measurement. |
| G-3 | Heavy mocking on critical paths (`test_identity_runtime_consolidation.py:10` 27 mocks; `test_boundary_awareness.py` 13 hand-rolled) | as cited | 6 | 6 | 4 | **DEFER** | Replace with integration tests after A-1/A-3. Today's mocks at least exercise call topology. |
| G-4 | Ground-truth size conflict: `test_replay_reliability_phase1.py:38-44` requires "exactly 100" annotations; actual files are 35 / 77 / 91 / 245 | as cited | 5 | 5 | 2 | **FIX NOW** | Either fix the test or expand labels. The test is currently impossible to satisfy. |
| G-5 | No CI job runs `browsermind_core/tests/` automatically | repo | 6 | 7 | 1 | **FIX NOW** | Add a basic GitHub Actions workflow. Even a smoke run prevents future drift. |
| G-6 | `test_replay_experiments.py` and `test_verification_pipeline_fixes.py` construct `ReplayReport` dataclasses by hand | `09_tests_data_training.md` | 4 | 4 | 4 | **DEFER** | Replace with real-replay fixtures after A-1. |

---

## H. Data & Training

| ID | Finding | Cite | Impact | Risk | Effort | Class | Recommended Action |
|---|---|---|---:|---:|---:|---|---|
| H-1 | `train_bc.py` reads `training/spec_sessions/` which doesn't exist | `train_bc.py:196-268` | 7 | 7 | 2 | **FIX NOW** | Either re-point `train_bc.py` at an existing directory, or generate `spec_sessions/` from current modern recorder output. |
| H-2 | `training/gold/samples.json` empty (0 accepted of 3,359 rejected) | `training/gold/gold_report.json:7-9` | 7 | 6 | 5 | **DEFER** | Diagnose why everything was rejected after A-1. Premature today — the meta-verifier should be regenerating from a working ledger. |
| H-3 | `training/gold_v2/samples.json` is 10 synthetic seeds (all `action_id=0`) | `training/gold_v2/dataset_report.json:24-26` | 6 | 6 | 3 | **DEFER** | Replace with real demonstrations after A-1. |
| H-4 | `meta_verifier_report.json: quality_gates.passes=false` | `training/gold_v2/meta_verifier_report.json:30-35` | 6 | 6 | 4 | **DEFER** | After H-1/H-3. |
| H-5 | `failure_ledger.jsonl` does not exist | grep | 5 | 6 | 5 | **DEFER** | Build as a side-effect of A-1's OutcomeLedger producer. |
| H-6 | R2D taxonomy zero hits in `**/*.{py,md}` | grep | 4 | 4 | 6 | **DOCUMENT** | Either remove from documentation or commit a placeholder spec. |
| H-7 | `capability_taxonomy_v1.json` referenced only by `training/capability_taxonomy.py:21` and `scripts/value_audit.py:135`; zero hits in `browsermind_core/` | grep | 4 | 4 | 3 | **DEFER** | Decide retire-or-wire after A-1. |

---

## I. Persistence & Kernel Hardening

| ID | Finding | Cite | Impact | Risk | Effort | Class | Recommended Action |
|---|---|---|---:|---:|---:|---|---|
| I-1 | `LocalJSONPersistenceProvider` returns `None` on checksum mismatch silently — no log, metric, exception | `browsermind_core/runtime/persistence.py:84-88` | 5 | 5 | 1 | **FIX NOW** | Add a `logging.error` + raise-or-quarantine path. Cheap. |
| I-2 | `_<kind>_index.json` writes use direct `json.dump` — bypass atomic-rename + checksum | `browsermind_core/console/session.py:82-84` | 5 | 5 | 2 | **FIX NOW** | Route through `PersistenceProvider`. |
| I-3 | `RequirementLedger` has no persistence; not instantiated by `KernelSession` | `browsermind_core/ledger/requirement_ledger.py:23` | 4 | 4 | 2 | **DEFER** | Either delete (DELETE-candidate) or wire — decide when a real consumer exists. Currently no consumer. |
| I-4 | `AssetGraph` has no persistence | `browsermind_core/ontology/asset.py:82-105` | 4 | 4 | 3 | **DEFER** | Same as I-3 — no consumer. |
| I-5 | Duplicate `Environment` + `Persona` classes (`asset.py:34-69` vs `p1_schemas.py:32-67`) with divergent shapes | as cited | 6 | 6 | 3 | **FIX NOW** | Pick one (`p1_schemas` is the wider Pydantic surface), deprecate the other, sweep imports. |
| I-6 | Two `LocalJSONPersistenceProvider` instances point at the same dir (`KernelSession` + inside `WorkflowStore`) | `02_kernel_persistence.md` | 4 | 4 | 2 | **DEFER** | Inject the single provider. After I-1 lands. |
| I-7 | No env var for store root (only `--store` flag and `~/.browsermind` default); no `BROWSERMIND_HOME` / `XDG_DATA_HOME` | `session.py:29` | 3 | 3 | 1 | **DEFER** | Add when a packaged release is on the table. |
| I-8 | `LedgerRepository.get_by_entity` walks every key and re-reads each JSON file (O(N) per call) | `browsermind_core/ledger/ledger_repository.py:54-61` | 4 | 5 | 4 | **DEFER** | Index by entity_id when N becomes painful. Today's N is small. |
| I-9 | `ExecutionRepository.load_all_snapshots` lists ALL keys then prefix-filters | `browsermind_core/runtime/execution_repository.py:53` | 4 | 4 | 3 | **DEFER** | Same as I-8. |
| I-10 | CLI `execution start` fabricates `workflow_instance_id = uuid4()` and `template_id = uuid4()` when no instances exist | `browsermind_core/console/cli.py:472-473` | 7 | 7 | 2 | **FIX NOW** | Replace with hard error: "create a template first". |
| I-11 | `bm environment add` warns "Custom environments are session-only" — no persistence | `browsermind_core/console/environment_commands.py:48` | 4 | 4 | 2 | **DEFER** | Cheap to add but no caller pressure today. |
| I-12 | `events/__init__.py`, `ontology/__init__.py`, `ledger/__init__.py` are 1-line empty files; misleading | `02_kernel_persistence.md` | 3 | 3 | 1 | **DELETE** or **FIX NOW** | Either remove or repurpose as re-export modules. Cosmetic but confusing. |

---

## J. Missing Systems (Build Decisions)

| ID | System | Cite | Impact | Risk | Effort | Class | Recommended Action |
|---|---|---|---:|---:|---:|---|---|
| J-1 | Real Secret Vault (`cryptography.Fernet` or NaCl) | C-1, C-2 | 9 | 9 | 8 | **DEFER** (action: scheduled in Roadmap Later L-1/L-2) | Build only after A-1, A-2, A-3 land. Until then, document is the disposition (D-9). |
| J-2 | Real ABAC evaluator | C-3 | 9 | 9 | 9 | **DEFER** (Roadmap Later L-3) | Same gating as J-1. |
| J-3 | Runtime ContractVerifier (vs offline-only) | A-5 / Replay audit | 9 | 7 | 9 | **DEFER** (Roadmap Later L-5) | After A-1. |
| J-4 | PersonaShareGrant / IsolationLevel / CrossPersonaPolicy | `14_contradictions_missing.md` | 7 | 6 | 8 | **DEFER** | After J-2. |
| J-5 | IntentTimeline / IntentValidator | `14_contradictions_missing.md` | 6 | 5 | 8 | **DEFER** | After J-2. |
| J-6 | Decision Ledger | `14_contradictions_missing.md` | 6 | 6 | 6 | **DEFER** | After A-1. |
| J-7 | SelectorFingerprint multi-strategy resolver class | `14_contradictions_missing.md` | 4 | 4 | 4 | **DEFER** | Functionality already in `target_resolver.py`; abstraction is cosmetic. |
| J-8 | InterruptProtocol (AWAITING_HUMAN) | `14_contradictions_missing.md` | 6 | 5 | 6 | **DEFER** | After A-3 episodes exist. |
| J-9 | ObservationAdapter | `14_contradictions_missing.md` | 7 | 5 | 7 | **DEFER** | Required for real BC; build alongside H-1 unblock. |
| J-10 | SemanticStateScorer | `14_contradictions_missing.md` | 5 | 4 | 7 | **DEFER** | Far roadmap. |
| J-11 | AmbiguityClassifier / AmbiguityResolver | `14_contradictions_missing.md` | 6 | 5 | 6 | **DEFER** | After A-1; extends recovery R-paths. |
| J-12 | Memory tier wiring (episodic / procedural / semantic into ReplayEngine) | `04_dead_dup_fake.md` | 5 | 4 | 7 | **DEFER** | Far roadmap. |
| J-13 | ExecutionStateMachine | A-3 / `14` | 8 | 6 | 5 | **DEFER** (action: A-3 implements the minimum) | A-3 covers start/complete; full state machine after that. |
| J-14 | Cross-process recovery test (real subprocess) | G-1 | 7 | 8 | 3 | **FIX NOW** | One real test that forks a process and re-reads the ledger. Earns the "persistence survives restart" claim. |
| J-15 | Env-var support for store root (`BROWSERMIND_HOME` / `XDG_DATA_HOME`) | I-7 | 3 | 3 | 1 | **DEFER** | Pre-release. |

---

## K. Counts by Disposition

| Disposition | Count |
|---|---:|
| FIX NOW | 26 |
| FREEZE | 8 |
| DELETE | 11 |
| DOCUMENT | 11 |
| DEFER | 25 |

**26 FIX NOW items** are the next 4-6 weeks of work, ordered by `(Impact × Risk) / Effort`:

1. A-1 — Wire ReplayEngine → OutcomeLedger (priority 33)
2. A-2 — Fix `effect_verified=True` false positive (priority 45)
3. B-2 — `text_content` `isTextInput` guard (priority 64)
4. B-1 — Copy `recording_evidence` JS→Python (priority 63)
5. B-4 — Guard 0-step compiled templates (priority 49)
6. C-7 — Replace synthetic `persona_id=uuid4()` (priority 36)
7. C-8 — Persona-aware `profile_dir` on CLI/pilot paths (priority 24)
8. C-4 — Gate `ExecutionEngine` on policy (priority 24)
9. A-3 — Wire ExecutionEngine episodes (priority 18)
10. A-4 — Typed-exception failure taxonomy (priority 14)
11. C-1, C-2 — Vault decision (encrypt or de-claim) (priority 22.5 each)
12. C-3 — Disable runtime PolicyEngine (priority 18)
13. C-6 — Move PersonaManager persistence (priority 24)
14. C-11 — Persona membership guard (priority 16)
15. B-7 — Workflow template field round-trip (priority 21)
16. I-1 — Log on checksum mismatch (priority 25)
17. I-2 — Atomic index writes (priority 12.5)
18. I-5 — Resolve duplicate `Environment`/`Persona` (priority 12)
19. I-10 — Hard-error on missing template/instance in `execution start` (priority 24.5)
20. G-1, G-4, G-5 — Test corrections + CI smoke job
21. J-14 — Real cross-process recovery test
22. H-1 — Re-point `train_bc.py` to a real directory

**11 DELETE items** are a one-day cleanup pass (E-1 through E-10, plus I-12 candidate).

**11 DOCUMENT items** are a half-day documentation reset (D-1 through D-10, plus C-13 acknowledgement).

**8 FREEZE decisions** are governance commitments — banners and a no-new-commits policy on `core/*`, `browsermind_core/agent/*`, `browsermind_core/representation/*`, `browsermind_core/execution/*`, `runtime/policy_engine.py`, the duplicate Recorder/Executor classes.

**25 DEFER items** are blocked on the FIX NOW bucket. Revisit after A-1/A-2/A-3 land and the OutcomeLedger has ≥500 step rows.

---

## L. Sequencing Summary

```
Week 1 (DOCUMENT + DELETE + cheap FIX NOW):
  D-1..D-10          documentation reset (half day)
  E-1..E-10, I-12    delete confirmed dead files (one day)
  B-1, B-2, B-4      recorder/compiler one-line fixes (one day)
  I-1, I-10          persistence + CLI hard-fail (one day)
  G-5                CI smoke job (half day)

Weeks 2-3 (replay measurement loop):
  A-1                ReplayEngine → OutcomeLedger
  A-2                effect_verified false-positive fix
  A-3                ExecutionEngine episode wire
  A-4                typed-exception failure taxonomy
  G-1, J-14          real cross-process recovery test

Weeks 3-4 (security & identity):
  C-1, C-2           vault decision (encrypt or de-claim)
  C-3, C-10          PolicyEngine cleanup
  C-4, C-11          execution gate + persona membership guard
  C-6                PersonaManager persistence
  C-7, C-8           persona resolution + persona-aware profile_dir

Weeks 4-6 (tests, training plumbing):
  B-7                workflow template field round-trip
  G-4                ground-truth size conflict
  H-1                re-point train_bc.py
  I-2, I-5           atomic index + duplicate class cleanup

After Week 6 (DEFER bucket reopens):
  Reassess every DEFER item against the new state of the OutcomeLedger
  Decide F-3, F-7 (delete vs reintegrate)
  Plan J-1, J-2, J-3 build (Roadmap Later)
```

End.
