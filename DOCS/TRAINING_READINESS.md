# BrowserMind — Training Readiness

Date: 2026-06-06. Evidence-only. Tags: PROVEN | PARTIAL | ASSUMED | MISSING.

Source evidence: `DOCS/audit_evidence/09_tests_data_training.md`, `DOCS/audit_evidence/06_replay_experiment.md`, `DOCS/audit_evidence/14_contradictions_missing.md`.

---

## Behavioral Cloning (BC) — Precondition Checklist

| # | Precondition | Tag | Score (1-10) | Evidence |
|---|---|---|---|---|
| 1 | Replay success rate measurable end-to-end | PARTIAL | 5 | Per-step `ReplayStep` exists in `ReplayReport`; CLI prints to stdout but does not write to ledger. Aggregation at `browsermind_core/experiments/reliability_metrics.py` exists but consumes ad-hoc artifacts in `reports/replay_experiments/`, not a runtime ledger. [file: browsermind_core/runtime/replay_engine.py, function: replay, line: 88]; [file: browsermind_core/console/cli.py, line: 697]. |
| 2 | False positive rate measurable | PARTIAL | 3 | `report_generator.py` computes resolution thresholds; FPR-specific code is absent. Effect-verification is itself unreliable: `replay_engine.py:599-601` reports `effect_verified=True` on locator-evaluate exception. The measurement is corrupted at source. |
| 3 | Step-level outcome data exists at row scale | PARTIAL | 3 | `reports/replay_experiments/` contains 276 step outcomes across 54 runs, but they are derived ad-hoc per experiment, not produced by the runtime path. The runtime `OutcomeLedger` has no producer in console scope (zero `record()` callers). [file: browsermind_core/ledger/outcome_ledger.py, function: record, lines: 38-42]. |
| 4 | Ground truth labels exist at scale | PARTIAL/MISSING | 3 | `ground_truth/` contains 4 sites: `saucedemo.json` (245 rows), `demoqa.json` (77), `static_baseline.json` (35), `aria_internet.json` (91) — total 448. But `browsermind_core/tests/test_replay_reliability_phase1.py:38-44` constructs `GroundTruthDataset` requiring "exactly 100" annotations, which conflicts with the actual file sizes. The labels are not used by the trainers. |
| 5 | Data contamination is prevented | PARTIAL | 5 | `train_bc.py:196-268` gates on `gold_report.json` + `meta_verifier_report.json`; `gold_v2/meta_verifier_report.json:30-35` reports `quality_gates.passes=false` (`false_positive_rate_missing`, `human_agreement_missing`). Practical use requires `--allow-unaudited` (`train_bc.py:454-457`). The gate exists but is failing today. |
| 6 | Training pipeline runs on real demonstration data | PARTIAL/BLOCKED | 5 | `train_bc.py` reads `training/spec_sessions/` — directory does not exist. `training/sessions/` has 3 files. `train_dagger.py` and `train_ppo.py` consume legacy `core/*` recorder schemas, not `browsermind_core/recorder/*` schemas. Schema mismatch blocks the modern recorder from feeding BC. |

**BC Training Readiness Score = (5+3+3+3+5+5) / 60 = 24/60 ≈ 4.0/10.**

(Lower than the data-audit score of 4.5/10; this revision applies the corrupted-effect-verification finding from the replay audit to precondition #2.)

---

## Reinforcement Learning (RL) — Precondition Checklist

| # | Precondition | Tag | Evidence |
|---|---|---|---|
| 1 | Reward signal flows from replay to trainer | MISSING | Replay engine does not write `OutcomeRecord`. No reward channel exists today. |
| 2 | Outcome verification is correct (not false-positive) | MISSING | `replay_engine.py:599-601` corrupts `effect_verified=True` on locator-evaluate exception. RL would optimize toward false positives. |
| 3 | ContractVerifier or equivalent is callable at runtime | MISSING | `scripts/experiments/p8a_task_contracts.py` is offline-only; not invoked from `ReplayEngine` or `ActionExecutor`. |
| 4 | Policy can stop unsafe actions | MISSING | `runtime/policy_engine.py` falls through to ALLOW for real persona UUIDs. `execution_engine.py:48` evaluates approval but never gates. |
| 5 | Episode boundaries are durable | MISSING | `ExecutionEngine.start_execution`/`complete_execution` not wired into `ReplayEngine`. No episode rows. |
| 6 | Action space is stable across schemas | MISSING | Two parallel architectures (`core/*` vs `browsermind_core/*`) — `train_ppo.py` consumes legacy schema; the modern recorder produces a different one. |

**RL Training Readiness Score: 0/10.** The plumbing for RL does not exist. Every precondition is MISSING.

---

## What Must Be Built Before BC Can Begin

(Ordered by dependency.)

1. **ReplayEngine writes OutcomeRecord per step + per run** to `OutcomeLedger`. Define the schema explicitly: `step_id`, `step_index`, `target_resolution_strategy`, `resolved`, `failure_class`, `effect_verified` (correct), `evidence_path`, `latency_ms`. Effort: 1-2 days. [file: browsermind_core/runtime/replay_engine.py]; [file: browsermind_core/ledger/outcome_ledger.py].
2. **Fix `replay_engine.py:599-601`** so locator-evaluate exceptions do not produce `effect_verified=True`. Effort: <1 day.
3. **Replace failure taxonomy substring match** with typed-exception dispatch from a single `ReplayException` hierarchy. Effort: 2-3 days. [file: browsermind_core/experiments/failure_taxonomy.py:152-153].
4. **Migrate `train_bc.py`, `train_dagger.py`, `train_ppo.py` off legacy `core/*` schema** onto `browsermind_core/recorder/*` schemas, OR explicitly freeze `train_dagger.py` and `train_ppo.py`. Effort: 1-2 weeks. [file: train_bc.py]; [file: train_dagger.py]; [file: train_ppo.py].
5. **Produce a clean cross-site replay dataset** by running the modern recorder + replay loop against a curated site list with the OutcomeLedger producing rows. Target: ≥500 step rows, ≥30 runs, ≥3 sites, all RESOLVED outcomes ground-truth-verified by ContractVerifier-equivalent at runtime. Effort: 2-3 weeks of operator time after items 1-3 land.
6. **Annotate failure rows.** Build a small annotation tool that reads `failure_class` from the ledger and lets a human attach the correct root cause. Effort: 1 week.

**Realistic BC start date if items 1-6 begin today: ~6-8 weeks.**

---

## What Must Be Built Before RL Can Begin

Everything above for BC, **plus**:

7. **Real policy enforcement.** Replace the dict-lookup `runtime/policy_engine.py` with an actual ABAC evaluator that gates `ExecutionEngine.start_execution`. Effort: 2-3 weeks. [file: browsermind_core/runtime/policy_engine.py]; [file: browsermind_core/runtime/execution_engine.py:48].
8. **Real persona isolation.** Replace persona-less `EnvironmentInstanceConfig.profile_dir` usage at `cli.py:401` and `kernel_bridge.py:59` with persona-aware paths. Effort: 1 week. [file: browsermind_core/runtime/environment_config.py]; [file: browsermind_core/runtime/auth_session.py].
9. **Real vault.** Replace `secret_vault.py` (SHA-256 mock) and `vault_writer.py` (plaintext on disk) with `cryptography.Fernet` or NaCl. Effort: 1-2 weeks including key management. [file: browsermind_core/managers/identity/secret_vault.py:12]; [file: browsermind_core/runtime/vault_writer.py:63-65,87].
10. **Episode lifecycle.** Wire `ExecutionEngine.start_execution(...)` and `complete_execution(...)` into `ReplayEngine.replay`. Effort: 3-5 days.
11. **Runtime contract verification.** Promote `ContractVerifier` from `scripts/experiments/p8a_task_contracts.py` to a runtime component callable per step. Effort: 2 weeks (requires defining contract DSL).
12. **A reward shaping spec.** What constitutes a positive reward? `effect_verified` alone is not enough. Define per-task contract satisfaction. Effort: 2-3 weeks of design + small implementation.

**Realistic RL start date: ≥6 months from today, contingent on BC closing the data loop first.**

---

## Data Gaps to Close

| Gap | Cite | Required action |
|---|---|---|
| `training/spec_sessions/` does not exist | `train_bc.py: 196-268` | Either create it from modern recorder or change the path |
| `training/gold/samples.json` empty (0 accepted of 3,359 rejected) | `training/gold/gold_report.json:7-9` | Diagnose why everything was rejected; rewrite the meta-verifier or relax thresholds |
| `training/gold_v2/samples.json` is 10 synthetic seeds (all `action_id=0`) | `training/gold_v2/dataset_report.json:24-26` | Replace with real demonstrations |
| `meta_verifier_report.json: quality_gates.passes=false` | `training/gold_v2/meta_verifier_report.json:30-35` | Fill in `false_positive_rate` and `human_agreement` measurements |
| Ground-truth size conflict (test expects 100, files have 35-245) | `browsermind_core/tests/test_replay_reliability_phase1.py:38-44` | Either fix the test or expand the labels |
| `failure_ledger.jsonl` does not exist | `find . -name "failure_ledger*"` empty | Build it as a side-effect of the OutcomeLedger producer |
| `R2D taxonomy` zero hits in code | grep over `**/*.{py,md}` | Either implement or remove from documentation |
| `capability_taxonomy_v1.json` not imported by `browsermind_core/` | `training/capability_taxonomy.py:21`, `scripts/value_audit.py:135` only | Decide: retire or wire into runtime |
| Two parallel recorder schemas (legacy `core/*` vs `browsermind_core/*`) | three `SessionRecorder` classes | Pick one, freeze the other |

---

## Bottom Line

BC is not training-ready today. Realistic path is ~6-8 weeks if items 1-6 start now. RL is not training-ready and will not be for at least 6 months. The blocker is not algorithmic — the blocker is that the runtime does not produce a ledger of outcomes the trainer can read.

End.
