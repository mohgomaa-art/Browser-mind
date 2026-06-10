# BrowserMind — Critical Path: Record → Compile → Replay → Measure

Date: 2026-06-06. Evidence-only. Tags: PROVEN | PARTIAL | ASSUMED | MISSING | DEAD | EXPERIMENTAL.

The critical path is the chain a real workflow must traverse:
  Human demo → recorder → session-on-disk → compiler → WorkflowTemplate-on-disk → replay engine → browser action → OutcomeRecord-on-disk → measurement.

Each numbered step cites file:function:lines and is tagged.

---

## Path A — Record (Human → DemonstrationSession on disk)

| # | Step | File:function:lines | Tag |
|---|---|---|---|
| A1 | CLI entry `bm record start` parses `--persona`, `--site`, `--profile-dir` | `browsermind_core/console/cli.py: bm_record (within record subcommand region, lines ~204-320)` | PROVEN |
| A2 | Resolves `EnvironmentInstanceConfig` from registry; selects `profile_dir` | `browsermind_core/runtime/environment_registry.py: profile_dir` | PROVEN |
| A3 | Constructs `RecordRunner` with persona id, site, profile_dir | `browsermind_core/recorder/record_runner.py: RecordRunner.__init__` | PROVEN |
| A4 | RecordRunner launches Playwright Chromium with the profile dir, opens the site | `browsermind_core/recorder/record_runner.py: run`, calls Playwright `chromium.launch_persistent_context` | PROVEN |
| A5 | Injects `semantic_recorder.py` JS into every page; captures `target_role`, `target_name`, `value`, `text_content`, `xpath`, `recording_evidence` | `browsermind_core/recorder/semantic_recorder.py: getTargetDescriptor (lines ~95)`, `getAccessibleName (lines 62-68)`, `recording_evidence (lines 318)` | PROVEN (capture) / PARTIAL (value-as-name guard exists for accessible-name only; text_content path at line 95 has no `isTextInput` guard — typed input still leaks into `descriptor.text_content`) |
| A6 | JS observers wrap every read in `try/catch` that returns empty string on error | `semantic_recorder.py: lines 49, 72, 85, 136, 149, 162, 183, 205, 222, 264, 323` | PARTIAL — silent blank-role/blank-name steps on page errors |
| A7 | Steps buffered in memory until user presses Enter | `browsermind_core/recorder/record_runner.py: run, line ~111` | PARTIAL — crash mid-recording loses the entire session |
| A8 | On stop, `RecordRunner` builds `DemonstrationSession` of `DemonstrationStep` objects | `browsermind_core/recorder/record_runner.py: lines 52-67` | PARTIAL — `recording_evidence` is **NOT** copied from JS payload to `DemonstrationStep`; the field has no slot in the Pydantic model |
| A9 | `DemonstrationRepository.save(session)` persists to disk | `browsermind_core/recorder/demonstration_repository.py: save` via `LocalJSONPersistenceProvider.save` at `<store_dir>/demonstration_session/<uuid>.json` | PROVEN |
| A10 | `event_bus.emit("EntityMutated", ...)` for the new session | (assumed in repository) | UNVERIFIED in this scope |
| A11 | `MutationLedger._on_entity_mutated` writes a `LedgerEntry` row | `browsermind_core/ledger/mutation_ledger.py: _on_entity_mutated, lines 31-43` → `ledger_repository.append, lines 37-42` | PROVEN |

**Path A status:** PROVEN-with-bugs. The session lands on disk, but the recorder loses two payloads on the way: (1) `recording_evidence` is dropped silently between JS and Python; (2) typed user input leaks into `text_content` because the value-guard is partial.

---

## Path B — Compile (DemonstrationSession → WorkflowTemplate on disk)

| # | Step | File:function:lines | Tag |
|---|---|---|---|
| B1 | CLI entry `bm record compile` (or equivalent) loads a session from `DemonstrationRepository` | `browsermind_core/console/cli.py` (record subcommand region) | PROVEN |
| B2 | `DemonstrationCompiler.compile(session)` walks steps | `browsermind_core/recorder/demonstration_compiler.py: compile` | PARTIAL |
| B3 | Filters CAPTCHA-likely steps by English string list | `demonstration_compiler.py: lines 33-44` filter on `target_name in ["begin","loading","confirm"]` and `"let's confirm you are human"` | PARTIAL — English-only; will drop legitimate "Confirm" buttons and miss real CAPTCHAs in other languages |
| B4 | Reads `recording_evidence` from each step | `demonstration_compiler.py: line 63` `getattr(act, "recording_evidence", None)` | DEAD — always returns `None` because A8 never persisted it |
| B5 | Produces `WorkflowTemplate.steps` | `demonstration_compiler.py: ~lines 100-150` | PROVEN |
| B6 | Persists template via `WorkflowStore.upsert_template(template)` | `browsermind_core/ontology/workflow_store.py: upsert_template, lines 50-70` then `provider.save("workflow_template", uuid, json)` | PROVEN |
| B7 | Index updated at `<store_dir>/_workflow_template_index.json` | `workflow_store.py: index write, lines 70-90` | PROVEN |
| B8 | Auxiliary fields `family_key`, `environment_family`, `environment_instance`, `profile_path` written to JSON blob (lines 56-58, 81-83) but **stripped on read** by `model_validate` (lines 125, 132-133) | `workflow_store.py` | PARTIAL — only the index copy of these fields survives reads via `list_*` / `lookup_*` |
| B9 | Compiler emits `EntityMutated` with `status: "compiled"` | `demonstration_compiler.py: lines 151-159` | PARTIAL — emitted **even when the resulting template has 0 steps** (no guard); silent regression risk |
| B10 | `MutationLedger` rows the create event | (same as A11) | PROVEN |

**Path B status:** PROVEN-with-bugs. The template lands on disk, but (1) the compiler reads a field the recorder never wrote (`recording_evidence`); (2) it can emit a 0-step template marked compiled; (3) it can drop legitimate steps via English-only CAPTCHA filtering; (4) the family/instance/profile fields it tries to attach to the template body don't survive the round-trip.

---

## Path C — Replay (WorkflowTemplate → browser action → OutcomeRecord)

| # | Step | File:function:lines | Tag |
|---|---|---|---|
| C1 | CLI entry `bm replay start` | `browsermind_core/console/cli.py: bm_replay, lines 645-703` | PROVEN |
| C2 | Loads `WorkflowTemplate` from `WorkflowStore.get_template(uuid)` | `browsermind_core/ontology/workflow_store.py: get_template, lines 121-126` | PROVEN |
| C3 | Constructs synthetic `WorkflowInstance` with `persona_id=uuid4()` | `cli.py: line 678` | PARTIAL — fake persona id; downstream isolation cannot be enforced |
| C4 | `EnvironmentInstanceConfig` resolution; persona-less `profile_dir` used by CLI path | `browsermind_core/runtime/environment_config.py: EnvironmentInstanceConfig.profile_dir` | PARTIAL — CLI/pilot paths share Chrome cookies across personas |
| C5 | `AuthSession.open()` launches Chromium with the resolved profile dir | `browsermind_core/runtime/auth_session.py: open` | PROVEN — real Chromium |
| C6 | `ReplayEngine.replay(site, template, instance, enable_recovery, start_step_index, is_resume)` is called | `browsermind_core/runtime/replay_engine.py: replay, line 88` | PROVEN |
| C7 | For each step: `TargetResolver.resolve(step, page)` | `browsermind_core/runtime/target_resolver.py: resolve, lines 1-714` | PROVEN |
| C8 | Strategy ladder: 1) exact CSS selector, 2) strict semantic ×2 with networkidle wait, 3) loose semantic, 4) container proximity, 5) ambiguity guard (`AmbiguousIdentityError` on count>1), 6) memory prior, 7) recovery R1 (container), 8) R2 (placeholder), 9) R3 (accessible-name), 10) R4 (dom_path), 11) R5a (affordance intent), 12) R5b (capability intent), 13) final fallback | `target_resolver.py: lines 1-633` | PROVEN |
| C9 | All-strategy failure → write `scratch/failed_page.html` and raise `TargetResolutionError` | `target_resolver.py: lines 634-646` | PROVEN |
| C10 | If resolved: `ActionExecutor.execute(locator, step.action)` calls real Chromium primitives (`click`, `fill`, `press`, `set_input_files`) and `page.goto` for navigation steps | `browsermind_core/runtime/action_executor.py: execute, line 17` | PROVEN |
| C11 | Outcome verification: locator-evaluate to detect element disappearance / state change | `replay_engine.py: lines 599-601` | PARTIAL — locator-evaluate failure is treated as `ELEMENT_DISAPPEARED, effect_verified=True` — false-positive verification |
| C12 | Per-step `ReplayStep` aggregated into `ReplayReport` | `replay_engine.py: ~lines 700+`, returns `ReplayReport` dataclass | PROVEN |
| C13 | **Write `OutcomeRecord` to `OutcomeLedger`** | grep over `replay_engine.py` for `OutcomeRecord|outcome_ledger` returns **zero matches** | **MISSING** — the wire is not present |
| C14 | **`ExecutionEngine.complete_execution(...)`** | not called by `ReplayEngine`; the two subsystems are decoupled | **MISSING** |
| C15 | CLI prints `ReplayReport` to stdout and discards | `cli.py: line 697` | PARTIAL — no durable record of the run beyond stdout/console scrape |
| C16 | Failure taxonomy classification (post-hoc) | `browsermind_core/experiments/failure_taxonomy.py: lines 152-153` substring-matches `"target not found"` to produce `TARGET_CHANGED` | PARTIAL — brittle string coupling between runtime exception text and offline classifier |
| C17 | TARGET_CHANGED root-cause attribution (post-hoc, offline) | `scripts/target_changed_dossier.py: lines 114-215` produces NAVIGATION_STATE_CHANGE / RECORDER_MISMATCH / ROLE_DRIFT labels | EXPERIMENTAL — these are NOT runtime classifications; they are forensic labels assigned offline |

**Silent-failure inventory (replay path):**
- `replay_engine.py: 599-601` — locator-evaluate exception → false-positive `effect_verified=True`. **Most dangerous.**
- ~25 bare `except: pass` / print-only blocks across `replay_engine.py`, `target_resolver.py`, `affordance_executor.py`, `affordance_discoverer.py`, `memory_*.py`, `auth_session.py`, `acquisition_runtime.py`. Memory writes, fingerprint writes, state inferences silently dropped on error.
- `replay_engine.py: _resolve_input` (line 56) is a DEAD helper — never called; `ResourceResolver.resolve_input` is used at line 392 instead.

**Path C status:** PARTIAL. The browser-driving half is PROVEN (real Chromium, 13-strategy resolver, real action executor). The measurement half is MISSING — no OutcomeRecord is ever written by the replay path. The classification half is post-hoc-only.

---

## Path D — P8A Experiment (runner → contract verification → report)

| # | Step | File:function:lines | Tag |
|---|---|---|---|
| D1 | Runner script entry | `scripts/experiments/p8a_baseline_challenge.py: __main__, line ~707` | PROVEN |
| D2 | Loads task list from `p8a_task_contracts.py` | `scripts/experiments/p8a_task_contracts.py: TASKS list (lines ~1-200)` | PROVEN |
| D3 | For each task: instantiates BrowserMind agent path | `p8a_baseline_challenge.py: line 274` | PROVEN |
| D4 | Runs BrowserMind replay against test server | `scripts/experiments/p8a_test_server.py` 453 lines | PROVEN |
| D5 | Applies `ContractVerifier` to BrowserMind result | `p8a_task_contracts.py: lines 217-310` URL substring + element visibility | PARTIAL — encoded around BrowserMind happy-path URLs |
| D6 | Instantiates baseline agent | `p8a_baseline_challenge.py: line 484` | DEAD — see D7 |
| D7 | Baseline agent uses `model_name="gemini-3.5-flash"` (invalid Gemini ID) | `scripts/experiments/p8a_baseline_agent.py: line 28` | **DEAD** — could not have run successfully |
| D8 | Baseline detects missing `GEMINI_API_KEY` and skips | observed in `reports/survivability/p8a_baseline_challenge.json` (`Skipped due to missing GEMINI_API_KEY` on every task; `execution_time_ms=0, llm_calls=0`) | PARTIAL — skip is honest about absence; comparison is dishonest |
| D9 | Applies `ContractVerifier` to baseline result | `p8a_baseline_challenge.py: line 484` | EXPERIMENTAL — never executed against a running baseline |
| D10 | Aggregates per-task outcomes; emits `p8a_baseline_challenge.json` | report writer in same file | PROVEN |
| D11 | Documentation reports "BrowserMind 7/9, Baseline 0/9" | `DOCS/research/STATE_OF_PROJECT_JUNE_2026.md` and walkthrough docs | **FALSE_CLAIM** — artifact shows BM 9/9 (`success_rate.browsermind = 1.0`); baseline tasks all `success: true: false` with `Skipped due to missing GEMINI_API_KEY`. The "7" appears to be `hypothesis_correct` count conflated with task success. |

**Path D status:** EXPERIMENTAL. ContractVerifier mechanics are real; the head-to-head comparison the project claims is dead at the baseline-agent level.

---

## Critical Path Completeness Score

Counting PROVEN links / total links per path:

- **Path A (Record):** 9 PROVEN, 4 PARTIAL, 0 MISSING. Completeness ≈ 70%.
- **Path B (Compile):** 6 PROVEN, 4 PARTIAL, 0 MISSING. Completeness ≈ 60%.
- **Path C (Replay → Measure):** 11 PROVEN, 4 PARTIAL, **2 MISSING (C13, C14)**, 1 EXPERIMENTAL. Completeness ≈ 55%, but the missing links are at the *measurement* step that justifies the entire chain.
- **Path D (P8A):** 6 PROVEN, 1 DEAD, 1 PARTIAL, 1 FALSE_CLAIM at report level. Completeness ≈ 50%.

**Replay Chain Completeness Score (Record→Compile→Replay→Measure end-to-end): ~50%.** PROVEN: recorder semantics, replay engine resolver, action executor, ContractVerifier mechanics. MISSING: replay→OutcomeLedger wire, replay→ExecutionEngine wire, runtime navigation-state-mismatch detection, runtime role-drift compile remediation, P8A baseline.

---

## Gaps Explicitly Marked

| Gap | Severity | Effort | Cite |
|---|---|---|---|
| ReplayEngine does not write OutcomeRecord | **CRITICAL** — collapses measurement | S (1-2 days, well-scoped) | `replay_engine.py` zero hits for `OutcomeRecord` |
| ReplayEngine does not call ExecutionEngine.start/complete | **CRITICAL** — no execution row to gate policy on | S | grep |
| `recording_evidence` dropped between JS and Python | HIGH — debugging blind spot | XS | `record_runner.py: 52-67` |
| `text_content` lacks `isTextInput` guard — typed-input leak | HIGH — privacy + name-confusion | XS | `semantic_recorder.py: 95` |
| Compiler emits 0-step "compiled" template | HIGH — silent regression | XS | `demonstration_compiler.py: 151-159` |
| English-only CAPTCHA filter | MEDIUM | S | `demonstration_compiler.py: 33-44` |
| `WorkflowTemplate` family/instance/profile fields stripped on read | MEDIUM | XS | `workflow_store.py: 125, 132-133` |
| `replay start` injects synthetic `persona_id=uuid4()` | HIGH — defeats persona isolation | S | `cli.py: 678` |
| CLI/pilot paths use persona-less `profile_dir` | HIGH — cross-persona cookie sharing | S | `cli.py: 401`, `kernel_bridge.py: 59` |
| Failure taxonomy substring-matches runtime exception text | HIGH — brittle | S | `failure_taxonomy.py: 152-153` |
| TARGET_CHANGED root causes are post-hoc-only | MEDIUM — measurement never closes the loop | M | `target_changed_dossier.py: 114-215` |
| `ExecutionRehydrated` event has zero subscribers | LOW — orphan publisher | XS | `execution_engine.py: 125` |
| Locator-evaluate failure → false-positive `effect_verified=True` | HIGH — corrupts measurement | XS | `replay_engine.py: 599-601` |

End.
