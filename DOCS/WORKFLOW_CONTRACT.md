# WORKFLOW_CONTRACT.md

> **Status:** Frozen for P1 implementation | **Owner:** Kernel Track A  
> **Rule:** No `workflow.py` / recorder code until this contract is accepted.

One page of boundaries. When in doubt, cite this file.

---

## 1. The question

```text
"Apply to Job" — what is it?
```

| Name in conversation | What it actually is (in BrowserMind) |
|----------------------|--------------------------------------|
| Apply to Job (the human goal) | **Intent** |
| Apply on Greenhouse (the procedure) | **WorkflowTemplate** |
| My Greenhouse apply with CV v7 (configured) | **WorkflowInstance** |
| Run #47 at 14:32 today | **Execution** |
| Click → type → submit (mechanics) | **Demonstration** → becomes **WorkflowCandidate** |

---

## 2. Definitions (frozen)

### Intent — *why* (human goal over time)

- Durable. May span weeks.
- Not executable directly.
- Example: *"Apply to 50 AI engineering roles by September."*
- **Ledger:** Intent Timeline (future P5) — why goals change.
- **Not stored as:** a list of clicks.

### WorkflowTemplate — *what procedure* (system-level, persona-agnostic)

- Reusable recipe for an **Environment Family** (e.g. Greenhouse job board).
- No secrets, no CV file, no "my account."
- Example: *"Greenhouse: open job → fill application → submit."*
- References: `Capability[]`, `EnvironmentFamily`.
- **Analog:** interface / class.

### WorkflowInstance — *this persona's configured workflow*

- `WorkflowTemplate` + bindings:
  - `Persona`
  - `Identity`(ies) per **Environment Instance**
  - `Resource`(s) (e.g. default resume)
- Example: *"Mohamed / freelancer → Greenhouse / resume=CV_v7."*
- **Analog:** configured object.

### Task — *one concrete run request*

- Single invocation: *"Run my Greenhouse apply workflow now."*
- Links: `Persona`, `WorkflowInstance`, spawns **Execution**.
- Short-lived. Completes or fails.
- **Today in code:** `Task` in `p1_schemas.py` ≈ this (goal string + status).

### Execution — *one runtime state machine instance*

- Runs **one** Task against **one** WorkflowInstance.
- Status: `running | paused | awaiting_human | succeeded | failed`.
- **Ledger:** Mutation Ledger — *what happened* (state changes).
- **Not:** the workflow definition itself.

### Demonstration (P2A) — *raw human trace*

- Append-only recording session: actions + observations + timestamps.
- **Not** yet a workflow. May include mistakes, backspaces, detours.
- Stored as: `DemonstrationSession` (to be added).

### WorkflowCandidate (P2B) — *curated procedure extracted from demonstration(s)*

- Editor-approved subset of a Demonstration.
- Stable steps + expected states + selector fingerprints.
- **Becomes** bindable to a `WorkflowTemplate` or new template version.

### Replay (P2C) — *machine re-execution of WorkflowCandidate*

- Uses warmed **Environment Instance** (browser profile + Identity).
- Emits Mutation Ledger entries per step.
- May pause (`awaiting_human`); does not rewrite Intent.

---

## 3. What "Workflow" means in conversation

| When we say | We mean |
|-------------|---------|
| "workflow" (lowercase, casual) | Usually **WorkflowInstance** or **WorkflowTemplate** — clarify in docs |
| "record a workflow" (P2A) | Record a **Demonstration** |
| "save a workflow" (P2B) | Promote to **WorkflowCandidate** → link **WorkflowTemplate** |
| "run a workflow" (P1/P2C) | Start **Task** → **Execution** → **Replay** |

**Code naming (P1+):**

- `WorkflowTemplate` — already in `p1_schemas.py`
- `WorkflowInstance` — already in `p1_schemas.py`
- Do **not** add a vague `Workflow` class; use Template / Instance / Candidate explicitly.

---

## 4. Relationships (diagram)

```text
Principal
  └── Persona
        ├── Intent (P5) ──────────────── human goal
        ├── WorkflowInstance ─────────── bound template + resources
        │       └── WorkflowTemplate (system)
        ├── Task ───────────────────── one-shot "run it"
        │       └── Execution ───────── state machine
        │               ├── MutationLedger (what)
        │               └── OutcomeLedger (did it work?)  ← P1.5
        └── DemonstrationSession (P2A)
                └── WorkflowCandidate (P2B)
                        └── Replay (P2C)
```

---

## 5. Environment (pointer)

Workflows are **never** tied to a bare domain string alone.

See **`ENVIRONMENT_CONTRACT.md`**:

- **Environment Family** — `greenhouse.io` (class of sites)
- **Environment Instance** — `boards.greenhouse.io/embed/.../airtable` (this deployment)

`WorkflowTemplate` → Family.  
`Identity` + browser profile → Instance.

---

## 6. P1 scope (minimal proof)

P1 **does not** require Demonstration or Replay.

P1 requires:

1. `WorkflowTemplate` (can be stub: 1 step "login")
2. `WorkflowInstance` (bindings)
3. `Task` + `Execution`
4. Manual or scripted steps that emit **`EntityMutated`**
5. **`OutcomeLedger`** entry at end: `login_succeeded | login_failed` + evidence (required in P1 — not deferred)

Success sentence:

```text
One real WorkflowInstance run → full Mutation trail → Outcome recorded → visible after restart
```

---

## 7. Anti-patterns (forbidden)

| Forbidden | Why |
|-----------|-----|
| Storing clicks under `Task.goal` only | Loses structure |
| Calling everything `Workflow` | Collapses Intent / Template / Run |
| `force_capability()` in recorder | Breaks label truth (Track B) |
| Replay without Environment Instance | Session / selector drift |
| Mutation Ledger as Outcome | Records *change*, not *result* |

---

## 8. Acceptance

This contract is **accepted** when:

- [ ] P1 runbook references Template / Instance / Task / Execution by name
- [ ] No new type named bare `Workflow` without Template|Instance|Candidate suffix
- [ ] `ENVIRONMENT_CONTRACT.md` accepted alongside this file

---

*Frozen boundary document — BrowserMind Kernel — June 2026*
