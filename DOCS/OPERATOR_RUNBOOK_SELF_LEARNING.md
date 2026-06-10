# Self-Learning Final Push — Operator Runbook

This runbook is what you (the human) run on a real machine to close the
self-learning loop. Everything else is now in code.

## What's in place

| Layer | Status | Where |
|---|---|---|
| OutcomeLedger wire (per step + per run) | ✅ wired | `replay_engine.py:118-342` |
| Execution lifecycle (start / complete / fail) | ✅ wired | `replay_engine.py:84-117` |
| ContractVerifier (runtime) | ✅ shipped | `browsermind_core/runtime/contract_verifier.py` + `runtime/contracts/*.yaml` |
| Real Fernet vault | ✅ shipped | `managers/identity/secret_vault.py` + key at `~/.browsermind/.vault_key` |
| Real ABAC (UUID-keyed, persisted) | ✅ shipped | `runtime/policy_engine.py` |
| Persona-aware Chrome profile | ✅ shipped | `runtime/environment_config.py` |
| Legacy trainers frozen | ✅ warn-on-import | `train_dagger.py`, `train_ppo.py` |
| BC episode extractor | ✅ shipped | `browsermind_core/training/episode_extractor.py` |
| Candidate yield aggregator | ✅ shipped | `browsermind_core/training/candidate_yield.py` |

## Step 1 — bootstrap a persona

```bash
bm principal add operator
bm persona add operator job_seeker
```

## Step 2 — write real credentials into the vault

```bash
# greenhouse, lever, workday all need a recovery email + password
bm persona vault-set job_seeker greenhouse username your@email.test
bm persona vault-set job_seeker greenhouse password 'real-password'
bm persona vault-set job_seeker lever     username your@email.test
bm persona vault-set job_seeker lever     password 'real-password'
```

Verify the file at `~/.browsermind/persona_vault/job_seeker.json` shows
`FRN1:…` ciphertext, NOT plaintext.

## Step 3 — record one workflow per ATS family (~15 min each)

```bash
bm record start greenhouse --persona job_seeker --site https://boards.greenhouse.io/<a-job-you-can-apply-to>
# fill the form by hand in the Chrome window; press Enter in the CLI when done
bm record compile <demo_id> --name greenhouse_apply_v1
```

Repeat for Lever and Workday. Stop after one successful template each. The
contract YAMLs in `browsermind_core/runtime/contracts/` already match these
keys.

## Step 4 — replay each template 20 times against real jobs

```bash
for i in {1..20}; do
  bm replay start greenhouse_apply_v1 --env greenhouse --persona job_seeker
done
```

Every run will:
- Open an Execution row (`ExecutionEngine.start_execution`).
- Emit one `step` OutcomeRecord per step (with `effect_verified`, `failure_class`).
- Emit one `workflow_instance` OutcomeRecord (`replay_run`) summarising the run.
- Emit one `task` OutcomeRecord (`contract_verification`) with `success=True`
  iff the Greenhouse "your application has been submitted" page rendered.

Do the same for Lever and Workday.

## Step 5 — read the yield

```bash
python -m browsermind_core.training.candidate_yield \
  --store ~/.browsermind \
  --out reports/candidate_yield.json
```

The report tells you which template you should promote, iterate, or debug:

```json
{
  "totals": {
    "applications_attempted": 60,
    "applications_submitted": 18,
    "submission_rate": 0.30,
    "step_false_positive_rate_in_failed_runs": 0.04
  },
  "by_environment_instance": {
    "greenhouse": {"attempted": 20, "submitted": 11},
    "lever":      {"attempted": 20, "submitted": 6},
    "workday":    {"attempted": 20, "submitted": 1}
  },
  "by_template": {...},
  "step_failure_classes": {"TARGET_CHANGED": 28, "AMBIGUOUS_IDENTITY": 4, ...},
  "decision": {"verdict": "ITERATE", "reason": "submission_rate=0.30 in (0.20, 0.50)"}
}
```

## Step 6 — extract BC episodes from the same data

```bash
python -m browsermind_core.training.cli extract \
  --store ~/.browsermind \
  --out training/episodes/bc_v1.jsonl
```

The extractor reads `OutcomeRecord(scope="step", outcome_type="step_attempt")`
rows directly. No separate training-data pipeline needed — the runtime ledger
IS the training set.

## Step 7 — BC discussion (Task #10)

Open the BC discussion only after:

- `applications_attempted >= 60` (20 per ATS × 3 ATS).
- `bc_v1.jsonl` has ≥ 500 step rows with at least 3 distinct `failure_class`
  values and at least 3 distinct `template_name` values.
- `step_false_positive_rate_in_failed_runs <= 0.05` (sanity check on the
  effect_verified probe; if it's high, fix the probe before training).

When those three pass, the BC gate (`evaluate_bc_gate` in
`browsermind_core/experiments/reliability_metrics.py`) can be evaluated honestly.
Until then, BC is premature and any training run will optimize toward the
broken effect-verification signal documented in `DOCS/TRAINING_READINESS.md`.

## Why this closes the loop

Before this push: the runtime wrote zero `OutcomeRecord` rows; the vault was a
SHA-256 mock; "policy" was a hardcoded dict with two persona names; Chrome
profiles were shared across personas; and training scripts read a directory
that did not exist.

After this push: every replay emits per-step + per-run + per-contract outcome
rows into a typed, persistent ledger; secrets are real Fernet at rest;
sensitive capabilities default-deny per persona UUID; each persona gets its
own Chrome profile per family; and a single `candidate_yield.py` command
collapses the ledger into a promote/iterate/debug decision.

The loop now exists: act → observe outcome → score → decide. What's left is
the data — which requires you, the operator, to drive the browser on real
sites with real accounts.
