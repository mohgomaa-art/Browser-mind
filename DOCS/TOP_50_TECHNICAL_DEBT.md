# BrowserMind — Top 50 Technical Debt

Date: 2026-06-06. Evidence-only.

Scoring (1=low, 10=high):
- **Impact**: blast radius if broken / value created if fixed.
- **Risk**: probability the bug bites a real user soon.
- **Difficulty**: estimated engineering effort.
- **Priority Score** = `(Impact × Risk) / Difficulty`. Higher = do first.

| Rank | Item | File | Impact | Risk | Difficulty | Priority | Notes |
|---:|---|---|---:|---:|---:|---:|---|
| 1 | ReplayEngine does not write `OutcomeRecord` to `OutcomeLedger` | browsermind_core/runtime/replay_engine.py | 10 | 10 | 3 | 33.3 | Zero `OutcomeRecord/outcome_ledger` hits in replay_engine.py; CLI prints to stdout (cli.py:697) and discards |
| 2 | Locator-evaluate exception → false-positive `effect_verified=True` | browsermind_core/runtime/replay_engine.py:599-601 | 10 | 9 | 2 | 45.0 | Corrupts every measurement that depends on effect verification — RL fatal |
| 3 | `secret_vault.py` uses SHA-256, mislabeled `ENC[AES256:...]` | browsermind_core/managers/identity/secret_vault.py:12 | 10 | 9 | 4 | 22.5 | One-way hash, never decryptable. Misrepresents security posture. |
| 4 | `vault_writer.py` writes plaintext to disk | browsermind_core/runtime/vault_writer.py:63-65,87 | 10 | 9 | 4 | 22.5 | No `cryptography`/`Fernet`/`nacl`/`Crypto` import in identity/vault/policy/runtime |
| 5 | `runtime/policy_engine.py` falls through to ALLOW for real persona UUIDs | browsermind_core/runtime/policy_engine.py | 10 | 9 | 5 | 18.0 | Hardcoded `"alpha"`/`"beta"` rules; enforcement is no-op |
| 6 | `execution_engine.py:48` evaluates approval but never gates | browsermind_core/runtime/execution_engine.py:48 | 9 | 8 | 3 | 24.0 | Execution always proceeds regardless of policy |
| 7 | Two parallel architectures (`core/*` vs `browsermind_core/*`) | core/executor.py (1,868 LOC), core/recorder.py, core/decision_engine.py | 9 | 8 | 8 | 9.0 | 13+ files still import legacy; trainers + studio_api on legacy schema |
| 8 | Three `SessionRecorder` classes coexist | core/recorder.py:32, collect_massive.py:155, collect_and_train.py:134 | 8 | 7 | 6 | 9.3 | Schema fork |
| 9 | `replay start` injects synthetic `persona_id=uuid4()` | browsermind_core/console/cli.py:678 | 9 | 8 | 2 | 36.0 | Defeats persona isolation entirely |
| 10 | CLI/pilot paths use persona-less `profile_dir` (Chrome cookie sharing) | browsermind_core/console/cli.py:401, kernel_bridge.py:59 | 9 | 8 | 3 | 24.0 | Cross-persona data leakage on these paths |
| 11 | `recording_evidence` dropped between JS and Python | browsermind_core/recorder/record_runner.py:52-67 | 7 | 9 | 1 | 63.0 | One-line copy fix; debugging blind spot |
| 12 | `text_content` lacks `isTextInput` guard — typed input leaks | browsermind_core/recorder/semantic_recorder.py:95 | 8 | 8 | 1 | 64.0 | Privacy + name-confusion |
| 13 | Compiler emits 0-step "compiled" template | browsermind_core/recorder/demonstration_compiler.py:151-159 | 7 | 7 | 1 | 49.0 | Add a guard before emit |
| 14 | English-only CAPTCHA filter | browsermind_core/recorder/demonstration_compiler.py:33-44 | 6 | 6 | 3 | 12.0 | Drops legit "Confirm" buttons; misses non-English CAPTCHAs |
| 15 | `WorkflowTemplate` family/instance/profile fields stripped on read | browsermind_core/ontology/workflow_store.py:125, 132-133 | 7 | 6 | 2 | 21.0 | Index copy survives but template body loses fields |
| 16 | `failure_taxonomy.py:152-153` substring-matches exception text | browsermind_core/experiments/failure_taxonomy.py:152-153 | 8 | 7 | 4 | 14.0 | Brittle string coupling; replace with typed exceptions |
| 17 | TARGET_CHANGED root causes are post-hoc-only | scripts/target_changed_dossier.py:114-215 | 7 | 7 | 6 | 8.2 | NAVIGATION_STATE_CHANGE / RECORDER_MISMATCH / ROLE_DRIFT not runtime-emitted |
| 18 | PolicyRouter declares 4 executors; 3 raise NotImplementedError | browsermind_core/agent/router.py:128, 134, 140, 147-150 | 8 | 5 | 4 | 10.0 | Any non-Accessibility route crashes |
| 19 | `ExecutionRehydrated` event has zero subscribers | browsermind_core/runtime/execution_engine.py:125 | 4 | 6 | 1 | 24.0 | Orphan publisher |
| 20 | EventBus exposes `subscribe`/`emit` only, no `publish` | browsermind_core/runtime/event_bus.py | 5 | 4 | 2 | 10.0 | Misleading docstring |
| 21 | `events/__init__.py` is empty; EventBus actually at `runtime/event_bus.py` | browsermind_core/events/__init__.py | 3 | 3 | 1 | 9.0 | Misleading package shell |
| 22 | DEAD: `runtime/storage.py` parallel to `persistence.py` | browsermind_core/runtime/storage.py | 5 | 5 | 1 | 25.0 | Same default dir; no checksum, no atomic write — risk of silent fork |
| 23 | DEAD: `runtime/enforcement.py` (duplicate `SecretVault`, `IdentityService`) | browsermind_core/runtime/enforcement.py | 4 | 4 | 1 | 16.0 | Zero importers |
| 24 | DEAD: `recorder/shadow_recorder.py` | browsermind_core/recorder/shadow_recorder.py:48 | 3 | 3 | 1 | 9.0 | Zero callers |
| 25 | DEAD: `runtime/friction_observatory.py` | browsermind_core/runtime/friction_observatory.py | 3 | 3 | 1 | 9.0 | Never instantiated |
| 26 | DEAD: `training/step_recorder.py` | training/step_recorder.py | 3 | 3 | 1 | 9.0 | Never instantiated |
| 27 | DEAD: `browsermind_core/execution/*` coordinator stack | execution_coordinator.py, playwright_executor.py, generic_executor.py, outcome_verifier.py | 6 | 6 | 2 | 18.0 | Hardcodes `base_url="http://127.0.0.1:8090"`; not called by ReplayEngine or CLI |
| 28 | EXPERIMENTAL: `browsermind_core/agent/*` (P7 Flow-Aware Agent, 11 modules) | browsermind_core/agent/router.py + 10 siblings | 7 | 5 | 9 | 3.9 | No runtime path despite heavy test coverage |
| 29 | EXPERIMENTAL: `browsermind_core/representation/*` (P5/P6) | browsermind_core/representation/* | 6 | 4 | 8 | 3.0 | No runtime path |
| 30 | P8A baseline agent uses invalid Gemini ID `"gemini-3.5-flash"` | scripts/experiments/p8a_baseline_agent.py:28 | 8 | 9 | 1 | 72.0 | Baseline never could have run; "0/9 vs 7/9" claim is false |
| 31 | Documentation claim "Replay Dataset v1: 45 steps, 14 runs" is wrong | DOCS/research/STATE_OF_PROJECT_JUNE_2026.md vs reports/forensic/combined_ledger_v2.md:3 (205/41) | 7 | 9 | 1 | 63.0 | Headline number is fabricated relative to artifact |
| 32 | Documentation claim "BrowserMind 7/9 P8A" contradicts JSON (9/9) | DOCS walkthrough vs reports/survivability/p8a_baseline_challenge.json | 7 | 9 | 1 | 63.0 | Self-inconsistent inside the same project |
| 33 | "Recovery 7/7" — pytest collects 6 tests | browsermind_core/tests/test_execution_recovery.py (4) + test_failure_recovery.py (2) | 6 | 8 | 1 | 48.0 | Off-by-one in headline |
| 34 | Recovery tests reuse same in-memory `ExecutionRepository` object | browsermind_core/tests/test_execution_recovery.py:55-59 | 7 | 8 | 2 | 28.0 | Don't actually test cross-process persistence |
| 35 | Zero real Playwright in `browsermind_core/tests/` | grep returns string-literal-only hits | 7 | 7 | 5 | 9.8 | Tests cannot prove browser behavior |
| 36 | Heavy mocking on critical paths | browsermind_core/tests/test_identity_runtime_consolidation.py:10 (27 mocks); test_boundary_awareness.py (13 hand-rolled mocks) | 6 | 6 | 4 | 9.0 | False confidence in covered surface |
| 37 | `train_bc.py` reads non-existent `training/spec_sessions/` | train_bc.py:196-268 | 7 | 7 | 2 | 24.5 | Pipeline blocks at startup; `--allow-unaudited` is a workaround |
| 38 | `training/gold/samples.json` empty (0/3,359) | training/gold/gold_report.json:7-9 | 7 | 6 | 5 | 8.4 | Meta-verifier rejects everything |
| 39 | `training/gold_v2/samples.json` is 10 synthetic seeds | training/gold_v2/dataset_report.json:24-26 | 6 | 6 | 3 | 12.0 | All `action_id=0`; not a useful BC dataset |
| 40 | `meta_verifier_report.json:30-35` `quality_gates.passes=false` | training/gold_v2/meta_verifier_report.json | 6 | 6 | 4 | 9.0 | `false_positive_rate_missing`, `human_agreement_missing` |
| 41 | Ground-truth size conflict (test expects 100, files 35-245) | browsermind_core/tests/test_replay_reliability_phase1.py:38-44 | 5 | 5 | 2 | 12.5 | Spec drift |
| 42 | `failure_ledger.jsonl` does not exist | find returns empty | 5 | 6 | 5 | 6.0 | Documented but absent |
| 43 | `R2D taxonomy` zero grep hits in `**/*.{py,md}` | grep | 4 | 4 | 6 | 2.7 | Documented but unimplemented; lower priority unless RL starts |
| 44 | `capability_taxonomy_v1.json` not imported by `browsermind_core/` | grep | 4 | 4 | 3 | 5.3 | Either retire or wire into runtime |
| 45 | Duplicate `Environment` + `Persona` classes (asset.py vs p1_schemas.py) | browsermind_core/ontology/asset.py:34-69 vs p1_schemas.py:32-67 | 6 | 6 | 3 | 12.0 | Divergent shapes — `id: str` vs UUID, `kind` vs `domain` |
| 46 | `Snapshot` (p1_schemas.py:149-155) is DEAD; only `SnapshotRecord` used | browsermind_core/ontology/p1_schemas.py:149-155 | 3 | 3 | 1 | 9.0 | Confusion risk |
| 47 | `_<kind>_index.json` writes bypass atomic + checksum | browsermind_core/console/session.py:82-84 | 5 | 5 | 2 | 12.5 | Hand-rolled `json.dump`; corruption-prone on crash mid-write |
| 48 | `LocalJSONPersistenceProvider` returns `None` on checksum mismatch silently | browsermind_core/runtime/persistence.py:84-88 | 5 | 5 | 1 | 25.0 | No log, no metric, no exception |
| 49 | `RequirementLedger` has no persistence and is not instantiated by KernelSession | browsermind_core/ledger/requirement_ledger.py:23 | 4 | 4 | 2 | 8.0 | In-memory list only |
| 50 | `AssetGraph` has no persistence | browsermind_core/ontology/asset.py:82-105 | 4 | 4 | 3 | 5.3 | Schema-only |

---

## Top-12 by Priority Score

The list ranks items by `(Impact × Risk) / Difficulty`. The actionable shortlist for the next two sprints:

1. **#30 — Stop the false P8A "7/9 vs 0/9" comparison** — fix model id or remove the comparison from documentation. (Priority 72.0)
2. **#12 — Add `isTextInput` guard to `text_content` path** — one-line fix, plugs typed-input leak. (64.0)
3. **#11 — Copy `recording_evidence` from JS to `DemonstrationStep`** — one-line fix. (63.0)
4. **#31 — Reissue Replay Dataset v1 numbers** — replace fabricated 45/14 with measured 205/41. (63.0)
5. **#32 — Reissue P8A 7/9 claim** — match the actual `success_rate.browsermind = 1.0`. (63.0)
6. **#13 — Guard against 0-step compiled templates** — add length check before emit. (49.0)
7. **#33 — Fix "7/7 recovery tests" claim or add the 7th test**. (48.0)
8. **#2 — Fix locator-evaluate false-positive `effect_verified=True`**. (45.0)
9. **#9 — Replace synthetic `persona_id=uuid4()` in `replay start`** with real persona resolution. (36.0)
10. **#1 — Wire ReplayEngine → OutcomeLedger**. (33.3)
11. **#34 — Make recovery tests use new process / fresh repository**. (28.0)
12. **#48 — Log + alert on checksum mismatch instead of silent `None`**. (25.0)

These twelve items are roughly two engineer-weeks combined and fix the largest credibility and measurement gaps.

End.
