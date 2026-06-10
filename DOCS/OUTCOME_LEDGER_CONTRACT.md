# OUTCOME_LEDGER_CONTRACT.md

> **Status:** Required for P1.5 (before P2A) | Companion: Mutation Ledger

Answers: **Did it work?** — not *what changed*.

---

## Three ledgers

| Ledger | Question | When | Example |
|--------|----------|------|---------|
| **Mutation** | What happened? | Every state change | `Execution.status: running → succeeded` |
| **Decision** (future) | Why this action? | Policy / planner | `chose resume_v7 because preference weight` |
| **Outcome** | Did it work? | End of step / task / workflow | `application_submitted: true` |

```text
Mutation  = accounting
Decision  = reasoning  (P5+ / planner)
Outcome   = learning   (preference, memory, optimization)
```

Without Outcome:

```text
The system remembers actions.
It does not learn results.
```

---

## OutcomeRecord (minimal schema)

```python
OutcomeRecord:
  id: UUID
  timestamp: datetime
  scope: Literal["step", "execution", "task", "workflow_instance"]
  scope_id: UUID
  persona_id: UUID
  environment_family: str
  environment_instance: str   # origin URL or registered instance id

  outcome_type: str           # e.g. "application_submitted", "login_succeeded"
  success: bool
  evidence: str               # human-readable
  evidence_uris: list[str]     # screenshot, DOM hash, confirmation text

  links:
    execution_id: Optional[UUID]
    task_id: Optional[UUID]
    resource_ids: list[UUID]    # e.g. CV_v7 used

  metrics: dict               # optional: duration_ms, retry_count
```

---

## Examples

### P1 (manual proof)

```json
{
  "outcome_type": "login_succeeded",
  "success": true,
  "scope": "execution",
  "evidence": "Landed on /dashboard; no error banner",
  "resource_ids": []
}
```

### Job apply (future)

```json
{
  "outcome_type": "application_submitted",
  "success": true,
  "scope": "execution",
  "evidence": "Greenhouse confirmation: Application received",
  "resource_ids": ["<cv_v7_uuid>"],
  "metrics": { "time_to_submit_ms": 142000 }
}
```

### Failure (still an outcome)

```json
{
  "outcome_type": "application_submitted",
  "success": false,
  "evidence": "Submit button disabled; validation error on phone field"
}
```

---

## vs Mutation Ledger

| Event | Mutation | Outcome |
|-------|----------|---------|
| Clicked Submit | ✓ (action logged) | — |
| Form accepted | maybe (status field) | ✓ `success: true` |
| Used CV_v7 | ✓ (resource reference) | ✓ `resource_ids` |
| Got interview later | — | ✓ delayed outcome (P5 / manual) |

---

## P1 vs P1.5

| Item | Phase |
|------|-------|
| One `OutcomeRecord` at end of `run_workflow_pilot.py` | **P1** (last line of runbook) |
| `bm outcome list`, persistence tests | **P1** ✅ |
| `bm outcome record` manual CLI | P1.5 |
| UI/Tauri outcome badge | P3 |

P1 success without Outcome answers only *what happened*, not *did login work*.

---

## P1.5 deliverables

- [x] `outcome_ledger.py` + `outcome_repository.py`
- [x] `bm outcome list`
- [x] P1 runbook ends with **one** OutcomeRecord
- [ ] `bm outcome record` (manual entry)
- [ ] UI/Tauri panel (P3): outcome badge on execution card

---

## Downstream (why we care)

| Consumer | Uses Outcome |
|----------|--------------|
| Preference learning | `resume_v7` → higher interview rate |
| Intent validator (P5) | goal achieved elsewhere |
| Workflow promotion (P2B) | candidate rejected if outcomes poor |
| Track B (compiler) | optional label on gold samples |

---

*Frozen — BrowserMind Kernel — June 2026*
