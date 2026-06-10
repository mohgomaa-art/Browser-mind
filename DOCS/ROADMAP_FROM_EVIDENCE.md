# BrowserMind — Roadmap From Evidence

Date: 2026-06-06. Evidence-only. Each item cites the audit finding that justifies its placement.

The buckets are time-ordered: each later bucket is gated on completion of the prior one.

---

## Immediate (this week, unblocked, evidence-based)

These are one-line / one-day fixes that close credibility gaps and unblock measurement. They require no new architecture.

| # | Action | Justification cite | Estimated effort |
|---|---|---|---|
| I-1 | Fix the `text_content` privacy leak: add `isTextInput` guard at `semantic_recorder.py:95` | [DOCS/audit_evidence/03a_recorder_compiler.md] | 1 hour |
| I-2 | Wire `recording_evidence` from JS payload into `DemonstrationStep` at `record_runner.py:52-67`; add the field to the Pydantic model | [DOCS/audit_evidence/03a_recorder_compiler.md] | 2 hours |
| I-3 | Guard `demonstration_compiler.py:151-159` so 0-step templates do not emit `EntityMutated` with `status: "compiled"` | [DOCS/audit_evidence/03a_recorder_compiler.md] | 1 hour |
| I-4 | Fix `replay_engine.py:599-601` so locator-evaluate exceptions do not produce `effect_verified=True` | [DOCS/audit_evidence/03b_replay_engine.md] | 4 hours |
| I-5 | Reissue documentation numbers: Replay Dataset v1 → 205 steps / 41 runs (artifact-true), P8A → 9/9 with baseline-skipped, Recovery → 6/6 not 7/7 | [DOCS/audit_evidence/14_contradictions_missing.md] | 1 day |
| I-6 | Fix or remove `scripts/experiments/p8a_baseline_agent.py:28` — replace `gemini-3.5-flash` with a valid Gemini model id, OR remove the head-to-head from documentation as currently misleading | [DOCS/audit_evidence/06_replay_experiment.md] | 2 hours |
| I-7 | Add log + metric on checksum-mismatch path at `persistence.py:84-88` instead of silent `None` | [DOCS/audit_evidence/02_kernel_persistence.md] | 2 hours |
| I-8 | Delete or fence the four confirmed DEAD modules: `runtime/storage.py`, `runtime/enforcement.py`, `runtime/friction_observatory.py`, `training/step_recorder.py` | [DOCS/audit_evidence/04_dead_dup_fake.md] | 4 hours |

**Bucket exit criterion:** All eight items merged. Documentation matches artifacts. Measurement is no longer corrupted at source.

---

## Next (1-4 weeks, gated on Immediate)

This bucket closes the replay→ledger loop and ends the duplication crisis.

| # | Action | Justification cite | Effort |
|---|---|---|---|
| N-1 | Wire `ReplayEngine.replay` → `OutcomeLedger.record(OutcomeRecord)` per step + per run. Define the per-step schema explicitly. | `replay_engine.py` zero hits for `OutcomeRecord` [DOCS/audit_evidence/03b_replay_engine.md] | 1-2 days |
| N-2 | Wire `ReplayEngine.replay` → `ExecutionEngine.start_execution` / `complete_execution` so runs have durable episode rows | [DOCS/audit_evidence/03b_replay_engine.md] | 3-5 days |
| N-3 | Replace substring-match failure taxonomy at `failure_taxonomy.py:152-153` with typed-exception dispatch from a `ReplayException` hierarchy | [DOCS/audit_evidence/03b_replay_engine.md] | 2-3 days |
| N-4 | Replace `replay start` synthetic `persona_id=uuid4()` (`cli.py:678`) with real persona resolution | [DOCS/audit_evidence/02_kernel_persistence.md] | 1 day |
| N-5 | Make `cli.py:401` and `kernel_bridge.py:59` use the persona-aware `environment_registry.profile_dir` instead of persona-less `EnvironmentInstanceConfig.profile_dir` | [DOCS/audit_evidence/08_identity_policy_env.md] | 2-3 days |
| N-6 | Make recovery tests spawn a new process / fresh `ExecutionRepository` instead of reusing the in-memory object at `test_execution_recovery.py:55-59` | [DOCS/audit_evidence/09_tests_data_training.md] | 1-2 days |
| N-7 | Declare `core/*` and root-level `record_session.py` / `collect_*.py` / `studio_api.py` LEGACY-FROZEN. No new commits. Add a top-of-file banner. | [DOCS/audit_evidence/04_dead_dup_fake.md] | 1 day (governance) |
| N-8 | Migrate `train_bc.py` off `training/spec_sessions/` to a directory that exists; OR create `spec_sessions/` from current modern recorder output | [DOCS/audit_evidence/09_tests_data_training.md] | 2-3 days |
| N-9 | Add a `python -m pytest` CI job that runs `browsermind_core/tests/` on every PR with no skips | [DOCS/audit_evidence/09_tests_data_training.md] | 1 day |
| N-10 | Resolve duplicate `Environment` + `Persona` classes (`asset.py` vs `p1_schemas.py`) — pick one, deprecate the other | [DOCS/audit_evidence/02_kernel_persistence.md] | 2-3 days |

**Bucket exit criterion:** OutcomeLedger contains ≥500 step rows from real cross-site replay runs. CI green. Legacy stack frozen. Two-architecture problem stops growing.

---

## Later (1-3 months, gated on Next)

This bucket replaces the security stubs and starts BC.

| # | Action | Justification cite | Effort |
|---|---|---|---|
| L-1 | Replace `secret_vault.py:12` (SHA-256 mock) with `cryptography.Fernet`. Define key location (per-user OS keystore on Windows, secret-tool on Linux, Keychain on macOS). | [DOCS/audit_evidence/08_identity_policy_env.md] | 1-2 weeks |
| L-2 | Replace `vault_writer.py:63-65,87` plaintext write with the same Fernet path. Migrate any existing on-disk secrets. | [DOCS/audit_evidence/08_identity_policy_env.md] | 3-5 days |
| L-3 | Build a real ABAC evaluator. Replace `runtime/policy_engine.py` static dict. Define attribute schema (subject.persona_id, resource.environment_family, action.kind, env.network_zone). | [DOCS/audit_evidence/08_identity_policy_env.md] | 2-3 weeks |
| L-4 | Gate `ExecutionEngine.start_execution` on `policy_engine.evaluate(...)`. Make the line at `execution_engine.py:48` actually deny or pause when policy says so. | [DOCS/audit_evidence/08_identity_policy_env.md] | 3-5 days |
| L-5 | Promote `ContractVerifier` from `scripts/experiments/p8a_task_contracts.py` to a runtime component callable per step. Define a small contract DSL. | [DOCS/audit_evidence/06_replay_experiment.md] | 2 weeks |
| L-6 | Deduplicate the three `SessionRecorder` classes; pick one schema; migrate the trainers. | [DOCS/audit_evidence/04_dead_dup_fake.md] | 2-3 weeks |
| L-7 | Promote TARGET_CHANGED root-cause classification from `target_changed_dossier.py:114-215` (offline) to `ReplayEngine` (runtime), so navigation-state-mismatch and role-drift are detected as they happen | [DOCS/audit_evidence/06_replay_experiment.md] | 2 weeks |
| L-8 | Run a real cross-site replay experiment producing ≥500 ground-truth-verified outcome rows; publish numbers; gate first BC training run on this. | [DOCS/TRAINING_READINESS.md] | 3 weeks operator time |
| L-9 | Reissue `STATE_OF_PROJECT_*.md` quarterly with measured numbers from the OutcomeLedger, not prose claims. | [DOCS/audit_evidence/14_contradictions_missing.md] | recurring |

**Bucket exit criterion:** Real crypto, real policy enforcement, real persona isolation; ≥500 ground-truth-verified outcome rows; first BC run produces a checkpoint and a measured replay-resolution delta.

---

## Frozen (do not start until Later milestones are proven)

These items are valuable but cannot pay off until the loop above closes.

| # | Item | Why frozen | Cite |
|---|---|---|---|
| F-1 | RL training (`train_ppo.py`, DAgger expansion) | RL needs reward signal from a working OutcomeLedger producer + ContractVerifier at runtime + reliable `effect_verified`. None exists today. | [DOCS/TRAINING_READINESS.md] |
| F-2 | P7 Flow-Aware Agent productionization (`browsermind_core/agent/*` 11 modules) | No runtime path; consumed only by experiments. Adding more code here grows the EXPERIMENTAL surface without payoff. | [DOCS/audit_evidence/04_dead_dup_fake.md] |
| F-3 | P5/P6 Representation Gateway productionization (`browsermind_core/representation/*`) | Same as F-2. | [DOCS/audit_evidence/04_dead_dup_fake.md] |
| F-4 | New environment families beyond what's needed for the cross-site replay experiment | EnvironmentFamily/Instance is a string tag today; building more on top calcifies the gap. | [DOCS/audit_evidence/02_kernel_persistence.md] |
| F-5 | New PolicyRouter executor types (`ContextExecutor`, `AuthenticatedExecutor`, `VisualExecutor`) | All three currently `raise NotImplementedError`. Don't add more until the existing three are real. | `browsermind_core/agent/router.py:128, 134, 140` |
| F-6 | "Personal Web OS" public framing | Today's vault, ABAC, persona, intent lifecycle do not match the framing. Fix the implementation before re-using the framing in any user-facing copy. | [DOCS/audit_evidence/14_contradictions_missing.md] |
| F-7 | Adding new sites to the recorder/replay experiment surface | First make the existing 4 sites (saucedemo, demoqa, the-internet, aria_internet) produce ground-truth-verified rows. | [DOCS/audit_evidence/09_tests_data_training.md] |
| F-8 | New documentation that claims gates / metrics / training readiness | All such claims must be artifact-derived from the OutcomeLedger from now on. | [DOCS/audit_evidence/14_contradictions_missing.md] |

---

## Sequencing Diagram (text)

```
  Immediate (week 1)
    └──> Next (weeks 2-5)
          └──> Later (months 2-4)
                └──> BC training (months 4-6)
                      └──> RL training (month 6+)

  In parallel, frozen until Later exit:
    P5/P6/P7 productionization
    Personal-Web-OS public framing
    New sites / new environment families
```

End.
