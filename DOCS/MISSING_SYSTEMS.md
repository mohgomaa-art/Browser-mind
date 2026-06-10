# BrowserMind — Missing Systems

Date: 2026-06-06. Evidence-only.

For each system: required by what (documented architecture / explicit roadmap / declared API), evidence of absence, impact of its absence, realistic effort to build, priority.

---

## Missing Systems Table

| System | Required by | Code location (or MISSING) | Status | Impact of absence (1-10) | Effort to build (1-10) | Priority (Impact × Need / Effort) |
|---|---|---|---:|---:|---:|---:|
| Replay → OutcomeLedger wire | Every claim about replay reliability, BC training input, RL reward channel | `grep` over `browsermind_core/runtime/replay_engine.py` for `OutcomeRecord`/`outcome_ledger` returns 0 | MISSING | 10 | 3 | **33** |
| Runtime ContractVerifier | Per-step success measurement, eventual RL reward | `scripts/experiments/p8a_task_contracts.py:217-310` is offline-only; not invoked by `ReplayEngine` or `ActionExecutor` | MISSING | 9 | 7 | **13** |
| Real Secret Vault (encryption) | "Encrypted vault" claim across documentation | `browsermind_core/managers/identity/secret_vault.py:12` SHA-256 in `f"ENC[AES256:{...}]"`; no `cryptography`/`Fernet`/`nacl`/`Crypto` imports | MISSING | 9 | 5 | **18** |
| Real ABAC evaluator | "ABAC engine" / cross-persona policy claims | `browsermind_core/managers/policy/policy_engine.py` UUID-keyed dict; `browsermind_core/runtime/policy_engine.py` hardcoded `"alpha"`/`"beta"` rules; falls through to ALLOW | MISSING | 9 | 8 | **11** |
| Execution policy gate | "Policy enforced before sensitive operation" | `browsermind_core/runtime/execution_engine.py:48` evaluates `approval_level` but no `if` denies/pauses/prompts | MISSING | 9 | 3 | **30** |
| Per-persona browser-profile isolation (consistent) | "Persona isolation" / "browser profiles per persona" claims | `environment_registry.profile_dir` is persona-aware but `cli.py:401`, `kernel_bridge.py:59`, `run_workflow_pilot.py` use the persona-less `EnvironmentInstanceConfig.profile_dir`. Cross-persona Chrome cookie sharing on these paths. | PARTIAL → fix to FULL | 9 | 3 | **30** |
| PersonaShareGrant / IsolationLevel / CrossPersonaPolicy | Two-layer persona model in design docs | Zero grep hits in `.py` | MISSING | 7 | 6 | **8** |
| ExecutionStateMachine | Lifecycle from start → step → contract → complete | `ExecutionEngine.start_execution` and `complete_execution` exist as standalone calls but ReplayEngine never invokes them | MISSING | 8 | 4 | **16** |
| IntentTimeline / IntentValidator | Intent lifecycle in design docs | Zero grep hits in `.py` | MISSING | 6 | 7 | **5** |
| Decision Ledger | Decision audit trail in design docs | Zero grep hits in `.py` | MISSING | 6 | 5 | **7** |
| SelectorFingerprint multi-strategy resolver class | Documented as a first-class class | The 13-strategy resolver exists inline in `target_resolver.py:1-714`; no `SelectorFingerprint` class | PARTIAL (functionality exists, abstraction does not) | 4 | 3 | **5** |
| InterruptProtocol / AWAITING_HUMAN | Human-in-the-loop pause + resume in roadmap | Zero grep hits | MISSING | 6 | 5 | **7** |
| ObservationAdapter | Adapter from raw page to observation tensor for BC/RL | Zero grep hits with that name; trainers consume legacy `core/*` schema directly | MISSING | 7 | 6 | **8** |
| SemanticStateScorer | "Semantic state machine" claim | Zero grep hits | MISSING | 5 | 6 | **4** |
| AmbiguityClassifier / AmbiguityResolver | Multi-target disambiguation surface | `target_resolver.py` raises `AmbiguousIdentityError` on count>1 but no resolver class exists; recovery R-paths cover narrow cases | PARTIAL | 6 | 5 | **7** |
| MemoryLayer-PRINCIPAL | Memory tier separation per principal | `browsermind_core/memory/*` exists but is not wired into ReplayEngine; no producer/consumer trace | MISSING (as wired) | 5 | 5 | **5** |
| Failure ledger (`failure_ledger.jsonl`) | Documented training input | `find . -name "failure_ledger*"` returns nothing | MISSING | 6 | 3 | **12** |
| R2D taxonomy | Documented training plan | grep `R2D|reality.*taxonomy` returns 0 hits in `**/*.{py,md}` | MISSING | 4 | 6 | **3** |
| `training/spec_sessions/` directory | `train_bc.py:196-268` reads from it | Directory does not exist | MISSING | 6 | 1 | **30** |
| Real Persona persistence in `PersonaManager` | Persona durable storage | `browsermind_core/managers/principal/persona_manager.py:10-21` only emits an event; UI sidecar `browsermind_ui/core/commands.py:22` writes the actual file | MISSING (manager-level) | 6 | 2 | **18** |
| Environment Family class hierarchy | "Environment family / instance" two-layer design | `environment_registry.family` is a free-form string; no Family class, no inheritance, no shared capability set | PARTIAL → MISSING (class) | 5 | 4 | **6** |
| Capability taxonomy runtime hookup | "Capability taxonomy v1" used at runtime | `training/capability_taxonomy_v1.json` referenced only by `training/capability_taxonomy.py:21` and `scripts/value_audit.py:135`; zero hits in `browsermind_core/` | EXPERIMENTAL → MISSING (runtime) | 4 | 4 | **4** |
| Gate-3 similarity validation artifact | "Gate 3 passed (similarity 1.0)" claim | Function exists at `scripts/run_p2b_validation.py:109`; no committed artifact | MISSING (artifact) | 4 | 1 | **16** |
| 7th recovery test | "7/7 recovery tests pass" claim | Pytest collects 6 tests (4 + 2). Either add a 7th or correct the claim. | MISSING | 4 | 2 | **8** |
| Cross-process recovery test (real new process) | "Persistence survives restart" claim | All current recovery tests reuse same in-memory `ExecutionRepository` (`test_execution_recovery.py:55-59`) | MISSING | 7 | 3 | **14** |
| Real Playwright integration tests | "Replay reliability validated" claim | Zero `async_playwright`/`chromium` hits in `browsermind_core/tests/` (string-literal-only) | MISSING | 7 | 6 | **8** |
| Episodic / procedural / semantic memory wiring | Three memory tiers in design docs | `browsermind_core/memory/episode.py`, `procedural.py`, `semantic.py` exist but not wired into ReplayEngine | MISSING (integration) | 5 | 5 | **5** |
| `RequirementLedger` persistence | Standalone class implies durability | `browsermind_core/ledger/requirement_ledger.py:23` in-memory list only; not instantiated by `KernelSession` | MISSING | 4 | 2 | **8** |
| `AssetGraph` persistence | Standalone class implies durability | `browsermind_core/ontology/asset.py:82-105` no I/O | MISSING | 3 | 3 | **3** |
| Custom-environment persistence | `bm environment add` should persist | `browsermind_core/console/environment_commands.py:48` warns "Custom environments are session-only" | MISSING | 4 | 2 | **8** |
| BROWSERMIND_HOME / XDG_DATA_HOME env-var support | Standard config surface | Only `--store` CLI flag and `~/.browsermind` default; grep over `browsermind_core/` for `BROWSERMIND_HOME`/`XDG_DATA_HOME` is empty | MISSING | 3 | 1 | **9** |
| EventBus `publish` method (vs only `emit`) | "Pub/Sub" docstring | `browsermind_core/runtime/event_bus.py` exposes `subscribe` + `emit` only | MISSING | 2 | 1 | **4** |
| Production credential isolation between trainers and runtime | Trainers consume legacy `core/*` schema; runtime uses `browsermind_core/recorder/*` | Two parallel architectures | MISSING (unification) | 7 | 9 | **6** |
| Top-level migration plan from `core/*` to `browsermind_core/*` | Acknowledged duplication | No migration plan in repo; both stacks evolve | MISSING | 7 | 8 | **6** |

---

## Implications

The two highest-priority missing systems by `(Impact × Need) / Effort` are:

1. **Replay → OutcomeLedger wire** (priority 33) — small change, unblocks measurement.
2. **Execution policy gate** (priority 30) and **persona-aware profile_dir on CLI/pilot paths** (priority 30) — both are 1-3 day fixes.

Two more sit just below at priority 18:
3. **Real Secret Vault** — replace SHA-256 mock with Fernet; 1-2 weeks.
4. **PersonaManager persistence** — replace event-only with provider-backed write; 2 days.

If only those four ship in the next 30 days, BrowserMind moves from "research repo with credibility gaps" to "research repo with a closed measurement loop and an honest security baseline."

The systems that are MISSING but **low priority today** (R2D taxonomy, IntentTimeline, SemanticStateScorer, full memory wiring) should not be built until the four above are real and producing data. Building them earlier just adds surface area on top of an unmeasured base.

End.
