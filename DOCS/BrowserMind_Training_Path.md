# BrowserMind — Shortest Path to Training-Ready

**Date:** 2026-06-06  
**Constraint:** Engineering time is scarce. Every step that is not on the critical path to training-ready is waste.

---

## CURRENT STATE

### What is proven

1. **Record → Compile → Replay pipeline works end-to-end.**  
   `SemanticRecorder` captures ARIA role, accessible name, descriptor, screenshot hash.  
   `DemonstrationCompiler` produces a `WorkflowTemplate` with per-step `ReplayabilityAssessment`.  
   `ReplayEngine` executes the template, resolves elements via `TargetResolver` (10-layer fallback), and writes `FailureAttribution` per step.  
   The full loop from human demo to structured replay exists and has been exercised.

2. **TargetResolver has a deep fallback chain.**  
   exact_selector → primary_semantic → loose_semantic → semantic+container → ambiguity resolution → memory_prior → container_proximity → placeholder → nearby_text → structural_path → affordance_intent → capability_intent.  
   `AmbiguousIdentityError` is raised correctly. `TargetResolutionError` is the terminal failure. Both are caught and converted to `FailureAttribution` entries.

3. **Per-step training signal schema exists and is correct.**  
   `FailureAttribution` records: `step_seq`, `action_type`, `role`, `name`, `predicted_tier`, `predicted_score`, `actual_outcome`, `resolved_by`, `resolution_depth`, `resolution_time_ms`. This is usable as a training label.

4. **CapabilityClassifier produces mutation-immune features.**  
   `capability_hint` (what the element IS) and `workflow_role` (what it DOES) are derived from element type attributes, not ARIA labels. These survive ARIA label drift — the primary failure mode. They are already embedded in compiled template steps and in `FailureAttribution`.

5. **BC gate criteria are formally defined.**  
   `evaluate_bc_gate()`: resolution_rate ≥ 0.80, false_positive_resolution_rate < 0.05, task_completion_rate ≥ 0.70.  
   `GroundTruthDataset` schema: exactly 100 annotated targets with `true_role`, `true_name`, `true_container`, `true_target`.

6. **Memory system writes per-step outcomes.**  
   `MemoryWriter.write_step_outcome()` → `EpisodeRecord` (append-only JSONL) + `ProceduralRecord` (success/failure counts per strategy per env/intent/action).  
   `MemoryReader.get_strategy_priors()` feeds back into `TargetResolver` as P4B memory prior.  
   This is a functioning online learning loop for resolution strategy selection. It is not a neural training loop, but it accumulates evidence.

7. **`ReplayExperimentHarness` orchestrates the full loop.**  
   `run_full()`: record → compile → replay → `ReplayResult` with `step_outcomes`, `reliability_metrics`, `false_positive_resolution_rate`, `resolution_accuracy`.  
   The harness already computes every metric the BC gate requires.

8. **Persistence is real.**  
   `LocalJSONPersistenceProvider`: atomic writes, SHA-256 integrity.  
   `DemonstrationRepository`: saves/loads sessions.  
   `MemoryStore`: atomic JSONL episodes + atomic JSON procedural/semantic.  
   All three survive process restarts.

9. **`AuthSession` persists login state.**  
   Playwright persistent context saves cookies/localStorage to `profiles/<persona>/<env>/`.  
   A single login survives across replay runs on the same site — no vault roundtrip needed for authenticated replay.

### What is disproven

1. **SecretVault cannot return credentials.**  
   `encrypt_and_store()` = `sha256(raw_secret)`. Irreversible.  
   BUT: `AuthSession.get_credentials()` reads from `persona_vault` namespace in `LocalJSONPersistenceProvider`, NOT from `SecretVault`. The vault is bypassed entirely in the real execution path. Credentials for `ResourceResolver` are stored as plain JSON at `provider.load("persona_vault", persona_name)`.  
   **Consequence:** `SecretVault` is dead code in the replay path. The vault bug does not block replay. It blocks `IdentityService.provision_identity()` which is not called during replay.

2. **The old system (`core/executor.py`) is not the training data source.**  
   The new system (`browsermind_core/`) writes its own `FailureAttribution` and `EpisodeRecord` data. `core/executor.py` `failure_buffer/` is disconnected and irrelevant to training on the new system.

3. **`ShadowRecorder` is not used in the record path.**  
   `record_runner.py` uses `SemanticRecorder`, not `ShadowRecorder`. `SemanticRecorder` captures ARIA role, accessible name, `descriptor`, `capability_hint`, `capability_ordinal`, `screenshot_hash`. The recorder is ARIA-compatible. The previous audit finding ("recorder incompatible with replayer") applied to `ShadowRecorder` — which is not the active recorder.

4. **BaseManager.save() print statement does not affect replay.**  
   `IdentityService.provision_identity()` is not called during `replay start`. The print-only save is a gap in the identity provisioning CLI path, not in the replay execution path.

### What is assumed (unverified)

1. Whether the 73.2% step resolution and 43% workflow completion numbers come from System A or System B. Reports do not carry a `system_source` field.

2. Whether `MemoryReader.get_strategy_priors()` has ever produced a successful prior-guided resolution. EpisodeRecord JSONL files exist on disk but have not been queried in this session.

3. Whether `StateVerifier` YAML rules exist for the gate sites (saucedemo, static_baseline). `replay_engine.py` loads from `browsermind_core/evaluation/state_verification/rules/{site_key}.yaml`. If these files exist and are correct, `task_completed` in `ReplayResult` is populated and the BC gate `task_completion_rate` can be measured.

4. Whether `evaluate_bc_gate()` has ever been run against a real `ReplayResult`. The gate is defined. Whether the current system passes it is unknown.

---

## BLOCKERS

Ranked by impact on reaching the BC gate.

### Blocker 1: No ground truth dataset
**Impact:** CRITICAL. Without 100 annotated targets, `false_positive_resolution_rate` and `resolution_accuracy` are `None`. The BC gate cannot be evaluated. `evaluate_bc_gate()` will return `passed: False` because `fpr` is `None`.  
**Effort:** HIGH (human annotation work, ~4–8 hours per 100 steps).  
**Risk:** Low engineering risk. High time risk.  
**Evidence:** `ground_truth.py` requires exactly 100 `GroundTruthAnnotation` entries. `harness.py` passes `ground_truth=None` → all steps return `RESOLVED_UNJUDGED` → `false_positive_resolution_rate = None`.

### Blocker 2: CLI `replay start` creates dummy WorkflowInstance
**Impact:** HIGH. `replica_id=uuid4()`, `bound_identities={}`. Auth replay via CLI is impossible. The harness (`ReplayExperimentHarness`) does the same — creates a dummy instance. Any workflow that requires credential binding via `bound_identities` cannot be instantiated correctly from the CLI.  
**Effort:** LOW. Fix is 5 lines in `cli.py:676-682`.  
**Risk:** Low.  
**Evidence:** `cli.py:676-682`.

### Blocker 3: `StateVerifier` YAML rules may not exist for gate sites
**Impact:** HIGH. Without YAML rules for saucedemo and static_baseline, `task_completed` is always `None`, `task_completion_rate` is `None`, and the BC gate fails on the third criterion.  
**Effort:** MEDIUM. Writing YAML verification rules for 2–3 sites.  
**Risk:** Low engineering risk.  
**Evidence:** `replay_engine.py:641-648`: `yaml_path = ROOT_DIR / "browsermind_core" / "evaluation" / "state_verification" / "rules" / f"{site_key}.yaml"`. Not verified whether these files exist.

### Blocker 4: No training data pipeline from `FailureAttribution` to a learnable format
**Impact:** HIGH (for training, not for gate measurement).  
Even after the BC gate is passed, there is no script that converts `ReplayResult.step_outcomes` into (state, action, label) tuples consumable by BC.  
**Effort:** MEDIUM. The data exists. The conversion is not written.  
**Risk:** Low.  
**Evidence:** `harness.py` produces `ReplayResult` with `step_outcomes`. No training data writer reads this.

### Blocker 5: `persona_vault` has no write path from the CLI
**Impact:** MEDIUM. `AuthSession.get_credentials()` reads `persona_vault/<persona_name>` from the JSON store. There is no CLI command to write credentials into this namespace. Authenticated replay requires manually writing a JSON file to `.browsermind/persona_vault/<persona_name>.json` with `{"secrets": {"<env_key>": {"username": "...", "password": "..."}}}`.  
**Effort:** LOW. One CLI command.  
**Risk:** Low.  
**Evidence:** `auth_session.py:78-91`, `resource_resolver.py:38-51`.

### Blocker 6: `evaluate_bc_gate()` has never been run against a real dataset
**Impact:** MEDIUM. The gate thresholds (RR≥0.80, FPR<0.05, TCR≥0.70) are defined but their achievability is unknown.  
**Effort:** LOW. Run the harness on the 2 gate sites (saucedemo, static_baseline), collect 20 runs each, annotate 100 steps as ground truth.  
**Risk:** The result might show the system is far below gate. That is valuable information, not a risk.  
**Evidence:** `reliability_metrics.py:72-92`. Gate is formally defined. Not yet evaluated.

---

## ROADMAP

Single track. No parallel work. No optional steps. Each step has a hard exit criterion.

---

### STEP 1 — Verify the record → compile → replay loop on one gate site

**Goal:** Confirm that `SemanticRecorder` → `DemonstrationCompiler` → `ReplayEngine` produces a valid `ReplayResult` on `saucedemo` (the designated gate site). Establish a baseline resolution rate before any fixes.

**Files to run (no modification):**
```
python -m browsermind_core.experiments.harness  # or via CLI
bm record start saucedemo --persona pilot
bm record compile <demo_id> --name saucedemo_checkout_v1
bm replay start saucedemo_checkout_v1 --env saucedemo --persona pilot
```

**Files to read if it fails:**
- `browsermind_core/recorder/record_runner.py`
- `browsermind_core/runtime/replay_engine.py` (lines 103–200, step loop)

**Success metric:** `ReplayResult` JSON written to disk. `resolution_rate > 0.0`. No unhandled exception.  
**Failure metric:** Unhandled exception in `SemanticRecorder.attach()` or `ReplayEngine.replay()`. Resolution rate = 0.  
**Exit criteria:** One `ReplayResult` JSON on disk for saucedemo with `total_steps > 0` and `resolved_steps > 0`.

---

### STEP 2 — Write credentials into `persona_vault` for the gate site

**Goal:** Enable authenticated replay. saucedemo credentials are public (`standard_user` / `secret_sauce`). Write them into the persistence layer so `ResourceResolver` can inject them.

**Files to modify:**
- `browsermind_core/console/cli.py` — add `bm persona vault-set <persona> <env> <key> <value>` command

The command body:
```python
provider = LocalJSONPersistenceProvider(s.store_dir)
data = provider.load("persona_vault", persona_name) or {}
data.setdefault("secrets", {}).setdefault(env_key, {})[key] = value
provider.save("persona_vault", persona_name, data)
```

**Success metric:** `bm persona vault-set pilot saucedemo username standard_user` exits 0. `provider.load("persona_vault", "pilot")` returns `{"secrets": {"saucedemo": {"username": "standard_user"}}}`.  
**Failure metric:** KeyError or missing namespace on load.  
**Exit criteria:** Credentials for saucedemo readable by `AuthSession.get_credentials()` within the same store.

---

### STEP 3 — Fix CLI `replay start` to bind a real WorkflowInstance

**Goal:** Remove dummy `persona_id=uuid4()` and empty `bound_identities`. The replay harness already handles this correctly (it reads `persona_id` from the session). The CLI must match.

**Files to modify:**
- `browsermind_core/console/cli.py:676-682`

Replace:
```python
instance = WorkflowInstance(
    persona_id=uuid4(),
    template_id=template.id,
    bound_resources={},
    bound_identities={}
)
```
With:
```python
persona_entry = s._lookup("persona", persona_name)
if not persona_entry:
    _err(f"Persona '{persona_name}' not found.")
p_id = UUID(persona_entry["id"])
instance = WorkflowInstance(
    persona_id=p_id,
    template_id=template.id,
    bound_resources={},
    bound_identities={}
)
```

**Success metric:** `bm replay start saucedemo_checkout_v1 --env saucedemo --persona pilot` produces a `ReplayResult` with the correct `persona_id` (matches the stored persona, not a random UUID).  
**Failure metric:** persona not found error, or dummy UUID still used.  
**Exit criteria:** `ReplayResult.step_outcomes` shows credential steps resolving via `VaultProvider` (i.e., `resolved_by: "vault"` in resource acquisition log).

---

### STEP 4 — Run 20 replay sessions on saucedemo and static_baseline. Lock the baseline.

**Goal:** Produce a corpus of `ReplayResult` objects large enough to estimate `resolution_rate`, `recovery_rate`, and `task_completed`. Invoke `lock_phase1_baseline()` to freeze numbers before any fixes.

**Files to run:**
```python
from browsermind_core.experiments.harness import ReplayExperimentHarness
harness = ReplayExperimentHarness(headless=True, persona_id="pilot")
# Run 10x on saucedemo, 10x on static_baseline (skip_record=True after first compile)
results = [await harness.run_full("saucedemo", skip_record=True) for _ in range(10)]
```

**Files to create:**
- `reports/phase1_sprint_results.json` — aggregate stats
- `reports/phase1_baseline_locked.json` — output of `lock_phase1_baseline()`

**Success metric:** 20 `ReplayResult` JSON files on disk. `lock_phase1_baseline()` runs without error. Baseline `resolution_rate` recorded.  
**Failure metric:** Fewer than 20 results due to crashes, or `resolution_rate = 0` across all runs.  
**Exit criteria:** `reports/phase1_baseline_locked.json` exists and contains `measurement_before_fixes: True` with a non-zero `resolution_rate`.

---

### STEP 5 — Write `StateVerifier` YAML rules for saucedemo and static_baseline

**Goal:** Make `task_completed` non-null. Without it, `task_completion_rate` is always `None` and the BC gate fails its third criterion unconditionally.

**Files to create:**
- `browsermind_core/evaluation/state_verification/rules/saucedemo.yaml`
- `browsermind_core/evaluation/state_verification/rules/static_baseline.yaml`

Check what format is expected:
- `browsermind_core/evaluation/state_verification/__init__.py` (or `state_verification.py`) — read the `load_verification_config()` and `StateVerifier` interface before writing YAML.

**saucedemo success condition:** After a completed checkout, the URL contains `/checkout-complete.html` OR the page contains the text "Thank you for your order".

**static_baseline (Wikipedia search) success condition:** After search submission, the URL contains `Special:Search` or the page contains a `<h1>` with the searched term.

**Success metric:** `ReplayResult.task_completed` is `True` for sessions that complete the workflow on saucedemo. `task_completed` is `False` (not `None`) for sessions that fail.  
**Failure metric:** `task_completed` remains `None` after adding YAML rules — meaning `load_verification_config()` silently fails.  
**Exit criteria:** At least one saucedemo `ReplayResult` with `task_completed = True`.

---

### STEP 6 — Annotate 100 ground truth targets across 20 sessions

**Goal:** Produce a `GroundTruthDataset` with exactly 100 `GroundTruthAnnotation` entries. This is the only way to compute `false_positive_resolution_rate` and `resolution_accuracy`.

**Method:**  
For each replay session, open `step_outcomes` in the JSON result. For each step where `outcome != "SKIPPED"`, record the intended element: `true_role`, `true_name`, `true_container`, `true_target` (CSS selector or `#id` of the element the human demonstrator intended).

The 100 annotations must span at least 2 sites. Sample from saucedemo (checkout flow) and static_baseline (search flow).

**Files to create:**
- `reports/ground_truth_v1.json` — a JSON file that deserializes as `GroundTruthDataset`

**Schema:**
```json
{
  "dataset_id": "gt-v1",
  "annotations": [
    {
      "annotation_id": "gt-001",
      "site": "saucedemo",
      "template_name": "saucedemo_checkout_v1",
      "step_seq": 1,
      "true_role": "textbox",
      "true_name": "Username",
      "true_container": "",
      "true_target": "#user-name"
    }
  ]
}
```

**Success metric:** `GroundTruthDataset.model_validate(json.loads(...))` succeeds with exactly 100 entries.  
**Failure metric:** `ValueError: exactly 100` raised.  
**Exit criteria:** `reports/ground_truth_v1.json` validates as a `GroundTruthDataset`.

---

### STEP 7 — Run `evaluate_bc_gate()` against the annotated corpus

**Goal:** Get the first real measurement of whether the system is at, near, or far from the BC gate.

**Files to run:**
```python
from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.experiments.ground_truth import GroundTruthDataset
from browsermind_core.experiments.reliability_metrics import evaluate_bc_gate
import json

gt = GroundTruthDataset.model_validate(json.loads(
    open("reports/ground_truth_v1.json").read()
))
harness = ReplayExperimentHarness(headless=True, persona_id="pilot")
results = [
    await harness.run_full("saucedemo", skip_record=True, ground_truth=gt)
    for _ in range(10)
]

# Aggregate step_outcomes across all results
all_outcomes = [so for r in results for so in r.step_outcomes]
from browsermind_core.experiments.reliability_metrics import compute_replay_reliability_metrics
metrics = compute_replay_reliability_metrics(all_outcomes, task_completed=all(r.task_completed for r in results))
gate = evaluate_bc_gate(metrics)
print(gate)
```

**Success metric:** `gate["passed"] = True`. System is training-ready.  
**Failure metric:** `gate["passed"] = False`. At least one of {RR, FPR, TCR} is below threshold.  
**Exit criteria:** `gate` dict is printed with all three `checks` keys populated with actual values (not `None`).

If the gate fails, **do not continue to Step 8 until root cause is identified**. The gate result tells you exactly which metric failed and by how much. Fix only the component responsible for the failing metric. See GATES section for how to read the gate failure.

---

### STEP 8 — Write the training data pipeline

**Goal:** Convert `ReplayResult.step_outcomes` from the annotated corpus into a (state, action, label) format consumable by a BC learner.

This step is only reached after the BC gate passes. Until then, it is premature.

**Files to create:**
- `browsermind_core/training/episode_extractor.py`

**Output format per training episode:**
```json
{
  "site": "saucedemo",
  "step_seq": 3,
  "action_type": "fill",
  "capability_hint": "auth_password_input",
  "workflow_role": "login_password",
  "descriptor": { "role": "textbox", "accessible_name": "Password", "placeholder": "Password", "dom_path": "..." },
  "resolution_strategy": "primary_semantic",
  "resolution_depth": 0,
  "outcome": "RESOLVED_CORRECT",
  "label": 1
}
```

**Success metric:** `episode_extractor.py` reads a `ReplayResult` JSON and writes N training episodes where N = number of non-SKIPPED steps.  
**Failure metric:** Empty output or `KeyError` on `step_outcomes` fields.  
**Exit criteria:** 100+ training episodes on disk in the format above, spanning at least 2 sites and at least 3 distinct `capability_hint` values.

---

## GATES

### Replay Ready Gate
All three must be true:
1. `ReplayResult` written to disk for saucedemo and static_baseline (Step 1 done)
2. `task_completed` is non-null for at least one run on each gate site (Step 5 done)
3. `resolution_rate > 0.5` across 10 runs on each gate site

This gate says: the replay loop is functioning at a level where measurement is possible.

### Data Collection Ready Gate
All three must be true:
1. Replay Ready Gate passed
2. `GroundTruthDataset` with 100 annotations exists and validates (Step 6 done)
3. `false_positive_resolution_rate` is non-null in at least one `compute_replay_reliability_metrics()` call (Step 7 done)

This gate says: you can measure what the system is actually doing, not just whether it resolves.

### Training Ready Gate (BC Gate)
`evaluate_bc_gate()` returns `passed: True`:
- `resolution_rate >= 0.80`
- `false_positive_resolution_rate < 0.05`
- `task_completion_rate >= 0.70`

Measured across at least 20 runs on the 2 gate sites combined, with ground truth annotations for all evaluated steps.

**How to read a gate failure:**

| Failing check | Root cause | Fix |
|---|---|---|
| `resolution_rate < 0.80` | TargetResolver failing on specific element types | Examine `step_outcomes` for `TARGET_CHANGED` — add capability_selectors or improve `SemanticRecorder` ARIA capture for those element types |
| `false_positive_resolution_rate >= 0.05` | Resolver picking wrong elements at low confidence | Raise `capability_intent` confidence threshold; add container_label disambiguation to ambiguity resolution |
| `task_completion_rate < 0.70` | StateVerifier YAML rules too strict, or workflow genuinely failing | Check `verification_report` in failed `ReplayResult`; loosen YAML match conditions or fix the workflow step that's failing |

---

## DELETIONS

### What should NOT be built now

- Neural model for element resolution. The memory prior system (`MemoryStore` + `ProceduralRecord`) already accumulates resolution strategy evidence across runs. It is online, it is free, and it runs today. Build and evaluate it before designing a neural replacement.
- Visual grounding / screenshot-based resolution. This is a valid architectural direction but requires infrastructure (screenshot capture at resolution time, a vision model, a labeled screenshot corpus) that does not exist. Do not start this until the BC gate measurement shows the ARIA-based system cannot reach the gate.
- Tauri UI. Adds no measurement capability. Not on the critical path to training.
- Any new ontology layer (P4 Persona schema, P5 Intent). The schemas already exist in `p1_schemas.py`. The gap is measurement, not schema.
- Any new recording infrastructure. `SemanticRecorder` is ARIA-compatible and captures `capability_hint`. Improving it further before knowing what the baseline FPR is would be optimizing blindly.

### What should be deleted

- `core/executor.py` and the entire `core/` directory. This is System A. It is 1,869 lines of a parallel Playwright automation stack that does not share data with the kernel, does not feed the kernel's training pipeline, and will continue to diverge. Deleting it removes ~8,000 lines of dead maintenance burden. Do this only after a single deliberate decision and a git tag of the current state.
- `browsermind_core/execution/playwright_executor.py`. Handles 3 hardcoded OTP paths to `127.0.0.1:8090`. Dead code in the actual replay path. The real executor is `ActionExecutor` in `browsermind_core/runtime/action_executor.py`.
- `browsermind_core/managers/identity/secret_vault.py` (the SHA256 version). It is not called in the replay path. `AuthSession.get_credentials()` bypasses it entirely. The vault as designed is irreversible; either replace it with real symmetric encryption or delete it. Do not leave a broken security component in place.
- `browsermind_core/runtime/enforcement.py` (the `BaseManager` print-statement version). It provides no enforcement. Replace with real persistence calls or delete the abstraction.

### What should be frozen

- `core/executor.py` — freeze immediately. No new features. Accept pull requests for the kernel only.
- `browsermind_core/agent/` subsystem — `backward_state_planner.py`, `capability_dependency_planner.py`, `inference.py`, `router.py`. Not on the critical path. Freeze until the BC gate passes.
- `browsermind_core/representation/` subsystem — `invariant_compiler.py`, `hypothesis.py`, `generator.py`, `gateway.py`. Not on the critical path. Freeze.
- BC/DAgger/PPO training scripts — `train_ppo.py`, `dagger_tasks.py`, `agent_trainer.py`. Already frozen per FixPlan v2. Keep frozen until Step 7 produces `gate["passed"] = True`.

### What should be merged

- `ShadowRecorder` into a documentation note. It is not used in the active record path. `SemanticRecorder` is the recorder. Remove `ShadowRecorder` from any documentation that references it as the recorder.
- The two `PolicyEngine` implementations. `browsermind_core/managers/policy/policy_engine.py` (UUID dict) and `browsermind_core/runtime/policy_engine.py` (string rules for "alpha"/"beta"). Pick one. The runtime version is used in `ReplayEngine`. The managers version is used in `ExecutionEngine`. They are incompatible in interface. Until a real ABAC requirement exists, replace both with a single permissive stub.

### What should be validated before continuing

1. **Confirm `StateVerifier` YAML rules exist for saucedemo and static_baseline** before writing new ones. Check `browsermind_core/evaluation/state_verification/rules/`. If they exist, skip Step 5.
2. **Confirm `MemoryStore` has any episodes on disk** from prior runs before designing a new memory system. Check `~/.browsermind/memory/`. If JSONL files exist with > 0 lines, the memory loop is already running.
3. **Confirm the existing 41-run forensic corpus** (`reports/forensic/combined_ledger_v2.md`) was produced by `ReplayEngine` (System B) and not `core/executor.py` (System A). If it was System B, the 73.2% resolution rate is already a System B baseline and Step 4 is partly done.

---

## NEXT SPRINT

One week. One person. Three deliverables.

**Day 1:** Run the record → compile → replay loop on saucedemo. Get a `ReplayResult` on disk. Do not fix anything. Observe only.

**Day 2:** Write `persona vault-set` CLI command (30 min). Write saucedemo and static_baseline `StateVerifier` YAML rules (2 hrs). Run 20 sessions headless. Lock the baseline.

**Day 3–4:** Annotate 100 ground truth targets from the 20-session corpus. This is human work. There is no shortcut.

**Day 5:** Run `evaluate_bc_gate()` with the ground truth dataset. Print the gate result. Stop.

The gate result is the only output that matters this sprint. Every other number is noise until you know where you stand against `RR >= 0.80 / FPR < 0.05 / TCR >= 0.70`.

If the gate passes: write the training data pipeline (Step 8). One week.  
If the gate fails: fix only the metric that failed. Nothing else.
