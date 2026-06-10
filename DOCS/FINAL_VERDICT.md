# BrowserMind — Final Verdict

Date: 2026-06-06. Adversarial audit. Evidence-only. Every claim cites file:line.

---

## 1. What BrowserMind actually is today

A single-developer research repository with a working browser-recorder + Playwright-replay loop on a small set of public test sites (DemoQA, the-internet, saucedemo) and an unfinished kernel skeleton (Pydantic schemas, JSON-on-disk store, mutation/outcome ledgers, an event bus) bolted onto two parallel architectures that were never reconciled — the modern `browsermind_core/*` stack used by the CLI and Qt UI, and the legacy `core/*` + root-level `collect_*.py` / `record_session.py` stack still consumed by every trainer (`agent_trainer.py`, `train_dagger.py`, `train_ppo.py`, `main.py`, `pipeline/*`, `studio_api.py`). The replay engine resolves targets through 13 strategies and produces a `ReplayReport` that is printed to stdout and discarded — there is no wiring from replay to the `OutcomeLedger` it claims to populate. The "Personal Web OS" architecture documented in `DOCS/research/STATE_OF_PROJECT_JUNE_2026.md` (encrypted vault, ABAC, persona isolation, environment family/instance, intent lifecycle, decision ledger) is not implemented in code. [file: browsermind_core/runtime/replay_engine.py, function: replay, lines: 88]; [file: browsermind_core/managers/identity/secret_vault.py, lines: 12]; [file: browsermind_core/runtime/vault_writer.py, function: set_secret, lines: 63-65]; [file: DOCS/audit_evidence/04_dead_dup_fake.md].

---

## 2. Biggest misconception in existing documentation

That BrowserMind is at gate G6/G7 of a Personal Web OS roadmap with measured production readiness. The actual artifacts contradict the headline claims. [file: DOCS/research/STATE_OF_PROJECT_JUNE_2026.md] reports "Replay Dataset v1: 45 steps, 14 runs"; the only committed ledger artifact `reports/forensic/combined_ledger_v2.md:3` reports 205 steps / 41 runs / RESOLVED 150, and a separate scan of `reports/replay_experiments/` shows 54 runs / 276 step outcomes — three different totals, none matching the headline. The "P8A 7/9 vs baseline 0/9 LLM head-to-head" is doubly false: the artifact `reports/survivability/p8a_baseline_challenge.json` records BrowserMind 9/9 and the baseline as `Skipped due to missing GEMINI_API_KEY` on every task with `execution_time_ms=0, llm_calls=0` — there was never a baseline run. [file: scripts/experiments/p8a_baseline_agent.py, lines: 28] hardcodes `model_name="gemini-3.5-flash"` (not a valid Gemini ID), so the baseline could not have run even with a key. [file: DOCS/audit_evidence/06_replay_experiment.md]; [file: DOCS/audit_evidence/14_contradictions_missing.md].

---

## 3. Biggest architectural strength (with evidence)

The `TargetResolver` is the only component that meets a real production bar. It runs 13 progressive strategies in a defined order — exact CSS → strict semantic ×2 with networkidle waits → loose semantic → container proximity → ambiguity guard → memory prior → recovery R1–R5 (container, placeholder, accessible-name, dom_path, affordance intent, capability intent) — and a final fallback that dumps the failing page HTML and raises a typed `TargetResolutionError`. [file: browsermind_core/runtime/target_resolver.py, class: TargetResolver, lines: 1-714, fallback: 634-646]. The Playwright bridge is real Chromium — `AuthSession.open()` → `Page` → `ActionExecutor.execute()` calls real `loc.click/fill/press/set_input_files` and `page.goto` with no mock mode. [file: browsermind_core/runtime/action_executor.py, class: ActionExecutor]. The semantic recorder's accessible-name guard `!isTextInput` is correctly placed for the role/name path. [file: browsermind_core/recorder/semantic_recorder.py, function: getAccessibleName, lines: 63-68]. The mutation ledger persists with sha256 checksums and atomic writes, hydrates on construct, and survives process restart. [file: browsermind_core/ledger/mutation_ledger.py, function: __init__, lines: 23-29]; [file: browsermind_core/runtime/persistence.py, lines: 58-75].

---

## 4. Biggest architectural weakness (with evidence)

The replay path does not write its outcomes to the OutcomeLedger. `grep` over `browsermind_core/runtime/replay_engine.py` for `OutcomeRecord|outcome_ledger` returns zero matches. The `ReplayReport` returned by `ReplayEngine.replay` is captured in `cli.py:bm_replay` and printed to stdout (`browsermind_core/console/cli.py:697`) then discarded. The only `OutcomeRecord` producer in the entire codebase is the P1 pilot harness at `browsermind_core/pilot/kernel_bridge.py:180-192`, which is invoked from a separate experimental path. [file: DOCS/audit_evidence/03b_replay_engine.md]. This single missing wire collapses the architecture: the replay engine cannot measure itself, the outcome ledger has no producer in the console scope, no execution row exists to gate policy on, and no row-level data exists to feed BC. The downstream consequence is that everything described as "training data", "replay reliability metrics", "policy enforcement on execution", or "outcome-driven retraining" is unanchored — they all read from a ledger that the replay engine does not write to.

A second, parallel weakness: two complete architectures coexist. `core/executor.py` (1,868 LOC), `core/recorder.py`, `core/decision_engine.py`, `core/validator.py` are still the production path for every trainer, every collector, and `studio_api.py`. The `browsermind_core/*` stack is the CLI and Qt path. They share neither schema nor format. There are three classes literally named `SessionRecorder`. [file: core/recorder.py, class: SessionRecorder, lines: 32]; [file: collect_massive.py, class: SessionRecorder, lines: 155]; [file: collect_and_train.py, class: SessionRecorder, lines: 134].

---

## 5. Probability assessments with justification

| Question | Estimate | Justification |
|---|---|---|
| Replay chain completeness within 30 days | **20%** | The chain has ~50% PROVEN links per the replay audit. The largest gap (Replay→OutcomeLedger wire) is small in code but requires defining the OutcomeRecord shape for replay, choosing a producer surface, and migrating the failure taxonomy off the brittle substring classifier in `failure_taxonomy.py:152-153`. Achievable in 30 days only if the team focuses exclusively on this and freezes all P5/P6/P7 representation work. [file: DOCS/audit_evidence/06_replay_experiment.md]. |
| First production workflow end-to-end within 90 days | **10%** | "Production" requires durable persona, encrypted vault, policy enforcement, and cross-process replay of an outcome-anchored workflow. None of these exist today: vault stores SHA-256 hashes, plaintext on disk; PolicyEngine returns ALLOW for any real persona UUID; PersonaManager only emits an event without persisting; profile_dir isolation is bypassed by `cli.py:401` and `kernel_bridge.py:59`. Three subsystems must be replaced, not patched. [file: browsermind_core/managers/identity/secret_vault.py, lines: 12]; [file: browsermind_core/runtime/vault_writer.py, lines: 63-65]; [file: browsermind_core/runtime/policy_engine.py]; [file: browsermind_core/managers/principal/persona_manager.py, lines: 10-21]. |
| BC training readiness within 60 days | **15%** | Score today is 4.5/10 per the data audit. The only populated dataset is `training/gold_v2/samples.json` (10 samples, all action_id=0, fails its own meta-verifier gate). `training/spec_sessions/` (the path `train_bc.py` reads from) does not exist. Step-level outcome data does not flow from replay to ledger. R2D taxonomy referenced in roadmap docs is absent from code (zero grep hits). 60 days is feasible only if the team accepts that BC starts on synthetic data and gates on a manual annotation push. [file: training/gold_v2/samples.json]; [file: train_bc.py, lines: 196-268]; [file: DOCS/audit_evidence/09_tests_data_training.md]. |
| RL training readiness within 180 days | **5%** | RL needs reward signal from outcome verification, which needs the missing replay→ledger wire, which needs ContractVerifier or an equivalent at runtime (today it is offline-only at `scripts/experiments/p8a_task_contracts.py`). PolicyRouter declares four executors; three raise `NotImplementedError` (`ContextExecutor:128, AuthenticatedExecutor:134, VisualExecutor:140`). The ExecutionEngine lifecycle is never wired into ReplayEngine. RL is several layers of plumbing away. [file: browsermind_core/agent/router.py, lines: 147-150]. |

---

## 6. Investment recommendation

**RESTRUCTURE.** Continue the project but on conditions, not on momentum.

Conditions for continued investment:

1. **Single-stack rule.** Within 30 days, declare `core/*` and the root-level `record_session.py` / `collect_*.py` / `studio_api.py` paths LEGACY-FROZEN. No new code touches them. All trainers migrate to `browsermind_core/*` schemas or are themselves frozen. Without this, every audit will find the same duplication next quarter. [file: DOCS/audit_evidence/04_dead_dup_fake.md].

2. **Close the replay→ledger loop.** Within 30 days, `ReplayEngine.replay` writes a structured `OutcomeRecord` per step and per run, and the runtime `failure_taxonomy` classifier replaces the substring-match logic at `browsermind_core/experiments/failure_taxonomy.py:152-153` with explicit error-type dispatch from typed exceptions. This is the smallest change with the largest blast radius; refusing it is refusing to measure.

3. **Honest documentation reset.** `DOCS/research/STATE_OF_PROJECT_JUNE_2026.md`, `DOCS/BrowserMind_Implementation_Plan.md`, and `DOCS/research/TARGET_CHANGED_DOSSIER.md` must be reissued with corrected numbers (205 steps not 45; 9/9 BrowserMind / 0-attempted baseline; 6/6 recovery tests not 7/7). Vault, ABAC, Persona must be re-described as stubs. [file: DOCS/audit_evidence/14_contradictions_missing.md].

4. **Security stop-gap.** Either (a) remove every reference to "encrypted vault", "ABAC", "persona isolation" from product surface and label the system "single-user research" until real crypto and policy enforcement land, or (b) replace `secret_vault.py` and `vault_writer.py` with a real `cryptography.Fernet` implementation and gate `ExecutionEngine` on `policy_engine.evaluate` within 60 days. There is no third option that does not mislead users about what their data is doing. [file: browsermind_core/managers/identity/secret_vault.py, lines: 12]; [file: browsermind_core/runtime/vault_writer.py, lines: 63-65,87]; [file: browsermind_core/runtime/execution_engine.py, lines: 48].

5. **Freeze P5/P6/P7 representation+agent stacks.** `browsermind_core/agent/*` (P7 Flow-Aware Agent) and `browsermind_core/representation/*` (P5/P6 Representation Gateway) have no runtime path despite heavy test coverage. Every hour spent there is an hour not spent closing the replay loop. Treat them as research artifacts, not production candidates. [file: DOCS/audit_evidence/04_dead_dup_fake.md].

6. **No BC, no RL, no production claims** until conditions 1–5 hold and the OutcomeLedger contains ≥500 cross-site step rows from a non-mocked replay run.

If the team will not accept these conditions in the next two weeks, recommendation flips to **PAUSE** until governance changes.
