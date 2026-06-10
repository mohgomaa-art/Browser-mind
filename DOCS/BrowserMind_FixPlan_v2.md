# BrowserMind — Fix Plan v2.0 (Revised Priority)

> June 2026 | Supersedes execution order in Fix Plan v1.0 | Status: Actionable

This revision incorporates post-audit architectural decisions. **Kernel moat, not agent.**

---

## What Changed vs v1.0

| Topic | v1.0 | v2.0 |
|-------|------|------|
| Execution order | Tauri → Record → Runtime | **Ledger → Workflow proof → Recorder → UI** |
| Anti-bot | Fatal deadlock | **Personal Operator + HILRF** (session continuity, not stealth) |
| Web state | Semantic scorer only | **Observation (chaotic) ≠ Execution (deterministic)** |
| Ledger | Implied P3 | **P0 — blocks all proof** |

---

## Architectural Decisions (Log)

### 1. Personal Operator, not Universal Agent

Anti-bot is fatal only for **stateless cloud agents** navigating cold sessions.

BrowserMind targets **your** sites, **your** logged-in sessions, **~10 workflows**.

FIX-01 (HILRF) solves this via **session continuity**, not fingerprint evasion:

```text
Human drives (trusted session)
    → Shadow record
    → Replay on warmed profile
    → Interrupt on CAPTCHA/2FA (pause, not crash)
```

### 2. Two-Layer Runtime (replaces monolithic SEM)

**v1 mistake:** `SemanticStateScorer` mixed observation chaos with execution determinism.

**v2 split:**

```text
Web (chaotic)
    ↓
ObservationAdapter     ← probabilistic, DOM + screenshot, ambiguity signals
    ↓
ExecutionStateMachine  ← deterministic states, transitions, ledger commits
```

FIX-03 becomes: build the adapter + strict execution FSM — not one blended scorer.

### 3. Ledger Persistence = P0

M4 guarantees (**who / why / evidence**) require an **append-only audit trail across sessions**.

`LedgerRepository` already exists; `MutationLedger` must **hydrate on startup** (fixed in kernel).

Without this, First Real Workflow runs blind — no audit, no replay evidence.

---

## Revised Priority Stack

```text
P0  Ledger persistence hydration      ← ~1 day   (DONE: hydrate + test)
P1  First Real Workflow E2E          ← 1 week   Login → Fill → Submit (one site)
P2  Workflow Recorder (primitive)    ← 2 weeks  HILRF shadow mode
P3  Tauri UI (minimal)               ← 2 weeks  parallel with P2
P4  Two-Layer Persona Schema         ← 1 week   Principal + Persona + grants
P5  Goal Lifecycle / Intent Model    ← after P1 proof
```

**Do not start COV-scale training recompile or BC until P1 proves workflow + ledger.**

---

## P0 — Ledger (implementation note)

- **Write path:** `EntityMutated` → `MutationLedger` → `LedgerRepository.append`
- **Read path:** new `KernelSession` → `load_all()` into `history`
- **CLI/UI:** prefer `ledger_repo` for tail; `get_history()` now consistent after restart
- **Test:** `test_ledger_persistence.py` — cross-session hydration

---

## P1 — First Real Workflow (success = proof)

One workflow, one authenticated site, end-to-end:

```text
bm record start  → human completes flow
bm record save   → named workflow
bm replay run    → dry-run then live
bm ledger tail   → every mutation explained
```

Deliverables: demo video + ledger export screenshot (FIX-06 proof items).

---

## P2 — Workflow Recorder (FIX-01, no force)

- `SelectorFingerprint` (multi-strategy, no raw nth-child)
- `ShadowRecorder` (observe-only JS, no CDP pollution)
- `SelectorResolver` + `InterruptProtocol`
- **No** `force_capability()` — competition scoring only (see DISC-2.5)

---

## P3 — Tauri (FIX-05, deferred)

Sidecar `bm --json` + minimal Operator UI (executions list, human-interrupt card).

Python kernel unchanged. Rust = thin bridge only.

---

## P4 — Persona (FIX-02)

```text
Principal  → legal truth (phone, billing, DOB) — shared
Persona    → operational context — isolated unless PersonaShareGrant
```

Semantic memory at Principal layer; episodic at Execution; procedural at Workflow.

---

## P5 — Intent (FIX-04)

Only after P1: Intent entity, validator (surfaces stale — never auto-cancels), IntentTimeline.

---

## Training / Compiler Track (parallel, frozen for BC)

Current focus remains **Capability Discoverability** (DISC), not recompile:

```text
DISC-1 Signal funnel  →  DISC-2.5 Competition  →  DISC-2.6 Death report
COV-2 corpus expansion only after classification losses are understood
```

Kernel and training are **decoupled timelines** until P1 proof ships.

---

## Success Criteria (v2)

| Gate | Criterion |
|------|-----------|
| P0 | `bm ledger tail` after restart shows prior session entries |
| P1 | One recorded + replayed authenticated workflow with ledger trail |
| P2 | CAPTCHA/2FA → pause, not crash |
| P3 | Tauri shows `awaiting_human` + resume |
| Proof | Evolution doc + 3 demos published (workflow, ledger, persona) |

---

## Publish

- **EVOLUTION.md** — architectural decision log (evidence over vibe)
- **This file** — execution order contract for contributors
- **[BrowserMind_Implementation_Plan.md](./BrowserMind_Implementation_Plan.md)** — full dual-track roadmap (kernel + compiler, gates, timeline)

---

*BrowserMind Fix Plan v2.0 — Internal — June 2026*
