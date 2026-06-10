# BrowserMind — R2A 30-Day Execution Plan

**Status date:** June 2026  
**Authority:** This document supersedes ad-hoc mission selection. The 50-mission registry (`production_missions_r2a.md`) is **backlog only** until baseline gates pass.

---

## Mission

Determine whether BrowserMind's core thesis is true.

**Not:**

- Build new features
- Improve architecture
- Add learning
- Add AI

**Prove or disprove:**

> Semantic workflow replay survives reality.

---

## Hard freeze (until R2A completes)

| Prohibited | Allowed only |
|------------|----------------|
| RL, BC, Learning Layer | Recording |
| Preference learning | Replay |
| Authority Runtime | Observation |
| Anti-bot / human simulation | Attribution (human review of evidence) |
| Workflow evolution | |
| Strategy database | |
| New core modules | |

**Operational rule:** No new runtime, no new features, no automation scripts whose purpose is to *predict* report shape before **3–5 replay campaigns** exist. Infrastructure before evidence is out of scope.

**Explicitly deferred until data exists:**

- `scripts/r2a_baseline_run.py` or any batch replay aggregator
- Deliverable templates under `DOCS/reports/r2a/`
- Any tooling built from assumed KPI shapes

**Allowed doc-only addition:** this file.

---

## Core question

Can a workflow recorded on a real production website survive replay on the **same** company, **same** job, **same** environment?

Everything else depends on this.

---

## The one number (Week 0)

```
ASM Replay Resolution Rate (mean of ×5)
```

Plus **replay variance** (min / max / stddev) so a flaky 63% mean is not mistaken for a stable system.

- **≥ 70% mean** (same-day, 5 runs, no template edits between runs) → expand to 2 more Greenhouse, then Lever, then Workday per phase gates below — **unless** variance shows severe run-to-run instability (see metric 5).
- **40–70%** → stop new sites; forensics on ASM failures only.
- **< 40%** → stop new recordings; do not add runtime; do not build attribution pipelines; ask only: **Why did ASM fail?** (recorder vs compiler vs resolver vs environment).

> One production number unlocks or blocks everything else.

---

## Success metrics (track only five)

### 1. Replay resolution rate

```
resolved_steps / total_steps
```

Report **mean** across runs in a campaign (e.g. ASM ×5). Mean alone is not sufficient — see metric 5.

### 2. Replay success rate

```
successful_replays / total_replays
```

### 3. Temporal decay rate

```
resolution_rate_day0  vs  resolution_rate_day7
```

(No re-record, no repairs, no template updates for day+7 pass.)

### 4. Failure distribution

Top failure mechanisms, e.g.:

- `selector_missing`
- `recorder_mismatch`
- `auth_expired`
- `upload_failure`
- `verification_failure`

Use existing taxonomy (`browsermind_core/experiments/failure_taxonomy.py`) and Observatory scars where applicable.

### 5. Replay variance

Spread of resolution rate across repeated replays of the **same** compiled template (same job, same environment, no edits between runs).

After each ×5 campaign, record by hand:

```
mean
min
max
stddev   (optional: spreadsheet or calculator; not required in code)
```

**Why this matters:** A stable system and an unstable one can share the same mean.

Low variance (stable):

```text
Run1 91%  Run2 88%  Run3 90%  Run4 92%  Run5 89%  → mean ~90%
```

High variance (unstable — treat as a finding even if mean ≥ 70%):

```text
Run1 92%  Run2 15%  Run3 87%  Run4 31%  Run5 90%  → mean ~63%
```

Interpretation: mean **63%** with that spread means **replay is not reliably reproducible** (timing, auth, upload, or environment flake) — not “passing” on mean alone.

For ASM gate: **≥ 70% mean** AND document min/max/stddev. If variance is extreme (e.g. min &lt; 50% while max &gt; 85%), do **not** expand to new sites until forensics explain run-to-run divergence.

---

## Manual capture (until 3–5 campaigns exist)

Do **not** wait for report generators. Use a simple table per campaign (ASM first):

| Run | Resolution | Success | Duration | First failure | Category |
|-----|------------|---------|----------|---------------|----------|
| 1 | ? | ? | ? | ? | ? |
| 2 | ? | ? | ? | ? | ? |
| 3 | ? | ? | ? | ? | ? |
| 4 | ? | ? | ? | ? | ? |
| 5 | ? | ? | ? | ? | ? |

Optional: terminal state note, Observatory scar path.

After 5 runs, compute by hand:

1. **Mean resolution**
2. **Replay success rate** (PASS count / 5)
3. **Variance summary:** min, max, stddev

Example block:

```text
Replay 1 — Resolution: 92% — Success: PASS
Replay 2 — Resolution: 89% — Success: PASS
Replay 3 — Resolution: 41% — Success: FAIL — Failure: upload_validation @ step 44

Campaign summary:
  mean=74%  min=41%  max=92%  stddev=…
  success_rate=2/5=40%
```

This is the first **real KPI** set; architectural KPIs do not count.

---

## Phase map (do not skip order)

| Phase | Question |
|-------|----------|
| **R2A-1** | Can replay work? |
| **R2A-2** | Why did replay fail? |
| **R2A-3** | Does replay decay? |
| **R2A-4** | Can replay transfer? |

Nothing in R2A-2–4 matters if R2A-1 (ASM ×5) does not produce interpretable replay data.

---

## Phase R2A-1 — Production replay baseline

**Duration:** Week 1  
**Goal:** Validate replay on the exact workflow that generated the recording.

### Target workflows (minimum 8, only after ASM gate)

| Platform | Count |
|----------|-------|
| Greenhouse | 3 |
| Lever | 3 |
| Workday | 2 |

### Week 1 sequence (strict order)

1. **Today:** ASM Greenhouse — Record (done) → Compile → Replay ×5  
2. If ASM **≥ 70%:** add **2** additional Greenhouse (same company/job/env, replay ×5 each)  
3. If still passing: begin Lever set (3), then Workday (2)  
4. If ASM **< 40%:** no new sites; forensics on failed replays only  

### Procedure (per workflow)

```
Record → Compile → Replay ×5
```

- Same company, same job, same environment  
- No transfer  
- No modifications between the five runs  

### Capture (per replay)

- Step resolution rate  
- Terminal success  
- Replay duration  
- Failure step  
- Failure category  

### Exit criteria

**Mean replay resolution rate ≥ 70%** on baseline (ASM first), with min / max / stddev recorded.

If mean below 70%: **stop expansion**, investigate (Week 2 process).

---

## Phase R2A-2 — Replay forensics

**Duration:** Week 2  
**Goal:** Understand failures. **Not** fix failures.

### Process (every failed replay)

```
Observatory → Artifacts → Review board → Local hypothesis
```

### Required question (every scar)

Was this:

- Recorder issue?
- Resolver issue?
- Execution issue?
- Environment issue?

### Deliverable (when enough scars exist)

`scar_baseline_v1.md` — top failure mechanisms, count, evidence paths, confidence.  
Write only from observed campaigns; no template file required in advance.

---

## Phase R2A-3 — Temporal stability

**Duration:** Week 3  
**Goal:** Measure semantic decay.

### Procedure

- Take all Week 1 workflows  
- Replay again at **day +7**  
- No re-recording, no modifications, no repairs  

### Measure

- Resolution rate  
- Replay success  
- Failure drift  

### Deliverable

`semantic_decay_report.md` — authored after day+7 data exists.

---

## Phase R2A-4 — Transfer validation

**Duration:** Week 4  
**Goal:** Test portability **only after** same-environment baseline is known (≥ 70%).

### Transfer ladder

| Level | Scope |
|-------|--------|
| 1 | Same company, different job |
| 2 | Different company, same platform (e.g. ASM Greenhouse → Databricks Greenhouse) |
| 3 | Cross-platform — **only if** levels 1 and 2 survive |

### Measure

- Transfer resolution rate  
- Transfer success rate  
- Failure mechanisms  

---

## Critical questions (end of 30 days)

1. Can replay survive reality?  
2. What breaks replay?  
3. Is semantic targeting actually stable?  
4. Does replay decay over time?  
5. Can workflows transfer?  
6. Are failures mostly recorder or resolver problems?  

---

## What success looks like

**Not:** 50 features, new architecture, more modules.

**Yes:**

- 20+ production executions  
- 10+ replay attempts  
- 10+ attributed scars  
- `semantic_decay_report.md` (written from data)  
- `replay_baseline_report.md` (written from data)  
- `failure_taxonomy_v1.md` (rollup from scars, not a new code module)  

---

## What failure looks like (still success as science)

- Replay resolution rate **< 40%**, or  
- Most failures are **recorder corruption**  

That falsifies assumptions before more engineering time is wasted.

---

## Repo touchpoints (existing only)

| Step | Tool |
|------|------|
| Record | `record_reality.bat` / `record_session.py` |
| ASM ×5 launcher | `run_asm_replay_baseline.bat` (menu + run notes template) |
| Observatory | `core/observatory.py` → `logs/observatory/` |
| Compile | `python -m browsermind_core.console record compile …` |
| Replay | `python -m browsermind_core.console replay start …` |
| Scar rollup | `python scripts/scar_report.py` |
| Harvest discipline | `DOCS/production_harvest_protocol.md` |

Do not add parallel pipelines.

---

## Immediate next action (ASM only)

Do not open the editor for new code, architecture review, or learning work. The project reduces to one experiment:

```
ASM → Compile → Replay ×5 → Measure
```

```
Code freeze     = ON
New runtime     = OFF
New feature     = OFF
```

| Step | Action |
|------|--------|
| 1 | Compile ASM workflow |
| 2 | Replay #1 … #5 (no template changes between runs) |
| 3 | Fill the 5-row table (resolution, success, first failure, category) |
| 4 | Compute mean resolution, success rate, min / max / stddev |
| 5 | Apply gate on **mean** resolution; interpret **variance** before expanding |

**Decision gate (after ×5):**

| Condition | Action |
|-----------|--------|
| **Mean ≥ 70%** and **variance low** | Proceed → Greenhouse #2 (then Lever / Workday per R2A-1) |
| **Mean 40–70%** | **STOP** — forensics sprint only (R2A-2); no new sites |
| **Mean &lt; 40%** | **STOP EVERYTHING** — no new sites, features, or runtime. Recorder / compiler / resolver audit only. Ask: **Why did ASM fail?** |

**Variance low (manual judgment):** e.g. all five runs within ~10–15 points of each other (91–89–90–92–89). **Variance high:** large spread (92–15–87–31–90) even if mean ≈ 63% — system is **unstable**; do not expand until run-to-run divergence is explained.

---

## ASM baseline — identifiers (June 2026)

Pre-flight on this machine (`~/.browsermind`):

| Item | Value |
|------|--------|
| Demonstration session | `ed785c73` (71 actions, `greenhouse` / `asm`) |
| Job URL | `https://www.asm.com/open-vacancies/senior-engineer-global-product-support-4763867101?gh_jid=4763867101` |
| Compiled template | `asm_apply_greenhouse` (may already exist — re-compile only if session changed) |
| Profile | `~/.browsermind/profiles/validator/greenhouse` |

**Step 1 — compile** (skip if template unchanged):

```powershell
python -m browsermind_core.console record compile ed785c73 asm_apply_greenhouse
```

**Steps 2–6 — replay** (headed; same warmed profile; **no** template edits between runs):

```powershell
$URL = "https://www.asm.com/open-vacancies/senior-engineer-global-product-support-4763867101?gh_jid=4763867101"
python -m browsermind_core.console replay start asm_apply_greenhouse --env greenhouse --persona validator --url $URL
```

Run that command **five times**. From each `REPLAY REPORT` JSON, copy: `resolution_rate`, terminal success (`failed_steps == 0` and full resolve), duration (wall clock), first failure step, failure category.

**What you still lack until ×5 completes:** `Replay Baseline` — the table + mean / min / max / stddev / success rate.

---

## Final rule

For the next 30 days:

- **Reality** is the product.  
- **Evidence** is the deliverable.  
- **Scars** are progress.  
- Everything else is secondary.
