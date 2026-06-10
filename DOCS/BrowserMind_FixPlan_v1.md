# BrowserMind — Full Fix Implementation Plan v1.0
> Date: June 2026 | Scope: All 6 Critical Issues | Status: Actionable

---

## Table of Contents

1. [Issue Map & Priority](#issue-map)
2. [FIX-01 — Anti-Bot Deadlock](#fix-01)
3. [FIX-02 — Hard Persona Isolation](#fix-02)
4. [FIX-03 — Web State Machine](#fix-03)
5. [FIX-04 — Intent vs State](#fix-04)
6. [FIX-05 — PySide6 → Tauri](#fix-05)
7. [FIX-06 — Competitive Repositioning](#fix-06)
8. [Execution Timeline](#timeline)
9. [Success Criteria](#success)

---

## Issue Map & Priority {#issue-map}

| ID | Issue | Severity | Blocks | Fix Type |
|----|-------|----------|--------|----------|
| FIX-01 | Anti-Bot Deadlock | ☠️ Fatal | Everything | Architecture |
| FIX-02 | Hard Persona Isolation | 🔴 Critical | Cross-persona workflows | Schema |
| FIX-03 | Web State Machine | 🔴 Critical | Production reliability | Runtime |
| FIX-04 | Intent vs State | 🟠 High | Long-horizon value | New Layer |
| FIX-05 | PySide6 Choice | 🟡 Medium | Dev velocity | Stack Swap |
| FIX-06 | Competitive Positioning | 🟠 High | Market entry | Strategy |

**Execution Order:**
```
FIX-05 (stack) → FIX-01 (record first) → FIX-03 (runtime) →
FIX-02 (schema) → FIX-04 (intent) → FIX-06 (positioning)
```

---

## FIX-01 — Anti-Bot Deadlock {#fix-01}

### Root Cause

The current architecture assumes the agent navigates autonomously. But every major
site uses bot detection that defeats headless automation at the network layer —
not the UI layer.

The deadlock is circular:

```
Stealth browser  →  needs human-like behavior patterns
Human patterns   →  needs Behavior Cloning
Behavior Cloning →  needs working environment
Working env      →  needs stealth browser
```

This cannot be broken from inside the loop. It must be broken from outside.

### The Fix: Human-in-Loop Recording First (HILRF)

The agent does NOT navigate autonomously on first run. The human does.
The agent watches, records, learns, then replays.

```
Phase 1: Human Drives (no bot detection triggered)
    ↓
Phase 2: BrowserMind Records (shadow mode)
    ↓
Phase 3: Agent Replays (on proven, logged-in, warmed session)
    ↓
Phase 4: Agent Adapts (minor deviations only)
```

This is not a compromise. It is the correct architecture for authenticated workflows.
OpenAI Operator and Claude Computer Use are both solving the wrong problem by
trying to navigate from scratch. HILRF leverages the human's existing trust relationship
with every site.

### Architecture: Shadow Recorder

```python
# core/recorder/shadow_recorder.py

@dataclass
class RecordedAction:
    action_type: ActionType       # click | type | select | scroll | navigate
    selector: SelectorFingerprint # not raw CSS — semantic fingerprint
    value: Optional[str]
    timestamp_ms: int
    page_url: str
    page_hash: str                # DOM state hash at time of action
    visual_context: bytes         # screenshot region around element
    confidence: float             # how reliable is this selector

@dataclass
class SelectorFingerprint:
    """
    Stores multiple selector strategies ranked by stability.
    Never stores raw XPath or nth-child — too brittle.
    """
    aria_label: Optional[str]
    role: Optional[str]
    text_content: Optional[str]
    placeholder: Optional[str]
    data_testid: Optional[str]
    nearby_text: Optional[str]    # text within 100px, for fallback
    fallback_css: str             # last resort only

class ShadowRecorder:
    """
    Attaches to a running Playwright page in observe-only mode.
    Injects a non-detectable JS observer (no CDP pollution).
    """

    def attach(self, page: Page, execution_id: str) -> None:
        # Inject via evaluate — avoids CDP addScriptToEvaluateOnNewDocument
        # which is a known bot-detection signal
        page.evaluate(self._observer_script)
        page.expose_function("__bm_record__", self._on_action)

    def _build_fingerprint(self, el_info: dict) -> SelectorFingerprint:
        return SelectorFingerprint(
            aria_label   = el_info.get("ariaLabel"),
            role         = el_info.get("role"),
            text_content = el_info.get("textContent", "")[:80],
            placeholder  = el_info.get("placeholder"),
            data_testid  = el_info.get("testId"),
            nearby_text  = el_info.get("nearbyText"),
            fallback_css = el_info.get("cssSelector"),
        )

    def _on_action(self, raw: dict) -> None:
        action = RecordedAction(
            action_type = ActionType(raw["type"]),
            selector    = self._build_fingerprint(raw["element"]),
            value       = raw.get("value"),
            timestamp_ms = raw["ts"],
            page_url    = raw["url"],
            page_hash   = raw["domHash"],
            visual_context = self._capture_region(raw["rect"]),
            confidence  = self._score_fingerprint(raw["element"]),
        )
        self.ledger.record(action, execution_id=self.execution_id)
```

### Replay Engine: Resilient Selector Resolution

```python
# core/replay/selector_resolver.py

class SelectorResolver:
    """
    Tries selector strategies in order of stability.
    Falls back gracefully. Never crashes on missing element.
    """

    STRATEGY_ORDER = [
        "aria_label",
        "role+text",
        "placeholder",
        "data_testid",
        "nearby_text_proximity",
        "fallback_css",
    ]

    async def resolve(
        self,
        page: Page,
        fingerprint: SelectorFingerprint,
        timeout_ms: int = 5000
    ) -> Optional[ElementHandle]:

        for strategy in self.STRATEGY_ORDER:
            handle = await self._try_strategy(page, fingerprint, strategy, timeout_ms)
            if handle:
                self.ledger.record_resolution(
                    fingerprint=fingerprint,
                    strategy_used=strategy,
                    success=True
                )
                return handle

        # All strategies failed — escalate to human
        self._request_human_assist(fingerprint, page.url)
        return None

    async def _try_strategy(self, page, fp, strategy, timeout_ms):
        try:
            match strategy:
                case "aria_label":
                    if fp.aria_label:
                        return await page.wait_for_selector(
                            f'[aria-label="{fp.aria_label}"]',
                            timeout=timeout_ms
                        )
                case "role+text":
                    if fp.role and fp.text_content:
                        return await page.get_by_role(
                            fp.role, name=fp.text_content
                        ).element_handle()
                # ... other strategies
        except:
            return None
```

### CAPTCHA / 2FA Interrupt Protocol

```python
# core/replay/interrupt_protocol.py

class InterruptProtocol:
    """
    Detects mid-replay obstacles and requests human intervention
    without aborting the execution context.
    """

    INTERRUPT_SIGNALS = [
        "captcha", "verify you're human", "robot", "challenge",
        "verification code", "two-factor", "confirm it's you"
    ]

    async def check(self, page: Page, execution: Execution) -> InterruptResult:
        page_text = await page.inner_text("body")

        for signal in self.INTERRUPT_SIGNALS:
            if signal.lower() in page_text.lower():
                # Pause execution — don't abort
                execution.status = ExecutionStatus.AWAITING_HUMAN
                self.event_bus.emit(HumanInterruptRequired(
                    execution_id = execution.id,
                    reason       = signal,
                    page_url     = page.url,
                    screenshot   = await page.screenshot(),
                ))
                # Block until human resolves OR timeout
                return await self._wait_for_resolution(execution, timeout_s=300)

        return InterruptResult.CLEAR

    async def _wait_for_resolution(
        self, execution: Execution, timeout_s: int
    ) -> InterruptResult:
        # Operator UI sends resume signal via event bus
        for _ in range(timeout_s):
            if execution.status == ExecutionStatus.RUNNING:
                return InterruptResult.RESOLVED
            await asyncio.sleep(1)
        return InterruptResult.TIMEOUT
```

### New CLI Commands

```bash
bm record start  --persona freelancer --site upwork.com
bm record stop   --execution <id>
bm record review --execution <id>       # review before saving
bm record save   --execution <id> --name "apply-upwork-job"

bm replay run    --workflow "apply-upwork-job" --dry-run
bm replay run    --workflow "apply-upwork-job" --live
```

### Success Criteria

- [ ] Human session recorded on 3+ real sites without errors
- [ ] Replay succeeds on same site within 24h (fresh session)
- [ ] CAPTCHA triggers pause (not crash)
- [ ] 2FA triggers pause (not crash)
- [ ] Selector resolution logs strategy used per action

---

## FIX-02 — Hard Persona Isolation {#fix-02}

### Root Cause

The current schema states: `Nothing crosses Persona.`

This is wrong for two distinct reasons:

**Reason 1 — Shared Identity Reality**
The human behind all personas is the same person. Some data is
inherently cross-persona: real name, date of birth, phone number,
billing address. Duplicating these per persona creates dangerous drift
(outdated phone in one persona, current in another).

**Reason 2 — Intentional Cross-Persona Operations**
Some tasks explicitly require multiple personas to cooperate:
- Job application using `freelancer` persona with assets from `medical-student` persona
- A portfolio site that references both professional identities

### The Fix: Two-Layer Identity Model

```
Layer 1: Principal Layer (cross-persona, immutable truth)
    Real name, DOB, phone, billing address, primary email

Layer 2: Persona Layer (isolated operational context)
    Professional name, work email, credentials, style, assets
```

```python
# core/ontology/principal.py — revised schema

@dataclass
class Principal:
    id: str
    # IMMUTABLE TRUTH — never duplicated in personas
    legal_name: str
    date_of_birth: date
    primary_phone: str
    billing_address: Address

    # Personas owned by this principal
    persona_ids: list[str]

@dataclass
class Persona:
    id: str
    principal_id: str             # always traceable to root
    name: str                     # "Mohamed — Freelancer"
    display_name: str             # "Mohamed Gomaa"
    isolation_level: IsolationLevel

    # Explicit cross-persona sharing registry
    shared_with: list[PersonaShareGrant]

@dataclass
class PersonaShareGrant:
    """
    Explicit, audited permission for one persona to access
    another persona's resource.
    """
    source_persona_id: str
    target_persona_id: str
    resource_type: ResourceType   # ASSET | IDENTITY | WORKFLOW | MEMORY
    resource_id: str
    granted_by: str               # principal_id
    granted_at: datetime
    expires_at: Optional[datetime]
    reason: str                   # mandatory — why is this crossing?

class IsolationLevel(Enum):
    STRICT   = "strict"    # nothing crosses — current behavior
    STANDARD = "standard"  # principal data shared, persona data isolated
    LINKED   = "linked"    # explicit grants allowed
```

### Cross-Persona Asset Access

```python
# core/policy/cross_persona_policy.py

class CrossPersonaPolicy:

    def can_access(
        self,
        requesting_persona: str,
        target_resource: Resource,
        operation: Operation,
    ) -> PolicyDecision:

        # Principal-layer data: always accessible to all owned personas
        if target_resource.layer == ResourceLayer.PRINCIPAL:
            return PolicyDecision.ALLOW

        # Same persona: always allowed
        if target_resource.persona_id == requesting_persona:
            return PolicyDecision.ALLOW

        # Check explicit grants
        grant = self.grant_registry.find(
            source=requesting_persona,
            resource_id=target_resource.id,
        )
        if grant and not grant.is_expired():
            self.ledger.record_cross_persona_access(
                requesting=requesting_persona,
                resource=target_resource,
                grant_id=grant.id,
            )
            return PolicyDecision.ALLOW

        return PolicyDecision.DENY
```

### Semantic Memory: Shared by Default

The current memory split:
```
Episodic   → Execution-scoped
Semantic   → Persona-scoped      ← THIS IS WRONG
Procedural → Workflow-scoped
```

Semantic memory (who I am, what I know, my preferences) belongs at the
**Principal layer**, not the Persona layer. A medical student persona and
a freelancer persona both know the same facts about the world.

```python
@dataclass
class MemoryNode:
    id: str
    layer: MemoryLayer            # PRINCIPAL | PERSONA | EXECUTION
    persona_id: Optional[str]     # None if PRINCIPAL layer
    content: str
    embedding: list[float]
    created_at: datetime

class MemoryLayer(Enum):
    PRINCIPAL = "principal"   # who I am, what I know — shared
    PERSONA   = "persona"     # how I present in this context — isolated
    EXECUTION = "execution"   # what happened in this run — scoped
```

### Migration Script

```python
# scripts/migrate_persona_isolation.py

def migrate():
    """
    Migrate existing strict-isolated personas to standard isolation.
    Identifies principal-layer data and moves it up.
    """
    principals = principal_repo.list_all()
    for principal in principals:
        personas = persona_repo.list_by_principal(principal.id)

        # Find duplicate fields across personas → they belong at principal layer
        common_phones   = _find_common_field(personas, "phone")
        common_names    = _find_common_field(personas, "legal_name")
        common_addresses = _find_common_field(personas, "billing_address")

        # Promote to principal, remove from personas
        principal.primary_phone   = common_phones[0] if common_phones else None
        principal.legal_name      = common_names[0] if common_names else None
        principal.billing_address = common_addresses[0] if common_addresses else None

        # Log every migration in ledger
        ledger.record_migration(
            principal_id=principal.id,
            promoted_fields=["phone", "legal_name", "billing_address"],
            source_persona_ids=[p.id for p in personas],
        )
```

### Success Criteria

- [ ] Principal layer holds legal name, phone, billing — not duplicated
- [ ] `bm persona share-grant create` command works end-to-end
- [ ] Cross-persona asset access logged in Mutation Ledger
- [ ] Semantic memory queries resolve across personas for same principal
- [ ] `bm persona share-grant list` shows all active grants with reason

---

## FIX-03 — Web State Machine {#fix-03}

### Root Cause

The current execution model assumes:
```
State A → Event → State B
```

Real web pages produce:
```
State A → Concurrent Events → Partial B + Residual A + Unexpected C
```

The existing Crash/Checkpoint/Corruption/Retry recovery handles **system-level** failures.
It does not handle **semantic ambiguity mid-execution**: the page partially loaded,
the SPA re-rendered, the modal appeared unexpectedly.

### The Fix: Semantic Execution Model (SEM)

Replace the strict state machine with an **evidence-weighted observation loop**:

```
Observe page state (DOM + screenshot)
    ↓
Score against expected state (semantic similarity, not DOM equality)
    ↓
If score > threshold → continue
If score < threshold → classify ambiguity type
    ↓
Resolve ambiguity via strategy table
    ↓
Commit resolved state to ledger
    ↓
Continue or escalate to human
```

### Implementation

```python
# core/runtime/semantic_execution.py

@dataclass
class PageObservation:
    url: str
    dom_hash: str
    semantic_regions: list[SemanticRegion]
    visible_text: str
    screenshot_embedding: list[float]
    timestamp: datetime

@dataclass
class ExpectedState:
    description: str                    # human-readable intent
    semantic_keywords: list[str]        # what should be visible
    required_elements: list[str]        # what must exist
    forbidden_elements: list[str]       # what must NOT exist (error indicators)
    url_pattern: Optional[str]          # regex

class SemanticStateScorer:

    def score(
        self,
        observation: PageObservation,
        expected: ExpectedState,
    ) -> StateScore:

        url_match     = self._score_url(observation.url, expected.url_pattern)
        text_match    = self._score_text(observation.visible_text, expected.semantic_keywords)
        element_match = self._score_elements(observation, expected.required_elements)
        error_absent  = self._score_errors(observation, expected.forbidden_elements)

        composite = (
            url_match     * 0.20 +
            text_match    * 0.40 +
            element_match * 0.30 +
            error_absent  * 0.10
        )

        return StateScore(
            value          = composite,
            url_match      = url_match,
            text_match     = text_match,
            element_match  = element_match,
            error_absent   = error_absent,
            confidence     = self._compute_confidence(composite),
        )

class AmbiguityClassifier:

    AMBIGUITY_TYPES = {
        "partial_load":     lambda obs: obs.dom_hash == "" or "loading" in obs.visible_text,
        "modal_injected":   lambda obs: "dialog" in obs.semantic_regions_roles,
        "spa_rerender":     lambda obs: obs.url == obs.prev_url and obs.dom_hash != obs.prev_dom_hash,
        "error_page":       lambda obs: any(w in obs.visible_text for w in ["404", "403", "error", "unavailable"]),
        "session_expired":  lambda obs: any(w in obs.visible_text for w in ["sign in", "log in", "session"]),
        "captcha":          lambda obs: any(w in obs.visible_text for w in ["captcha", "verify", "robot"]),
        "rate_limited":     lambda obs: any(w in obs.visible_text for w in ["too many", "rate limit", "slow down"]),
    }

    def classify(self, observation: PageObservation) -> AmbiguityType:
        for ambiguity_type, detector in self.AMBIGUITY_TYPES.items():
            if detector(observation):
                return AmbiguityType(ambiguity_type)
        return AmbiguityType.UNKNOWN

class AmbiguityResolver:

    RESOLUTION_STRATEGIES = {
        AmbiguityType.PARTIAL_LOAD:    "_wait_and_retry",
        AmbiguityType.MODAL_INJECTED:  "_handle_modal",
        AmbiguityType.SPA_RERENDER:    "_wait_for_stability",
        AmbiguityType.ERROR_PAGE:      "_escalate_human",
        AmbiguityType.SESSION_EXPIRED: "_restore_session",
        AmbiguityType.CAPTCHA:         "_escalate_human",
        AmbiguityType.RATE_LIMITED:    "_backoff_and_retry",
        AmbiguityType.UNKNOWN:         "_escalate_human",
    }

    async def resolve(
        self,
        ambiguity: AmbiguityType,
        page: Page,
        execution: Execution,
    ) -> ResolutionResult:

        strategy = self.RESOLUTION_STRATEGIES[ambiguity]
        handler  = getattr(self, strategy)
        result   = await handler(page, execution)

        self.ledger.record_ambiguity_resolution(
            execution_id   = execution.id,
            ambiguity_type = ambiguity,
            strategy_used  = strategy,
            result         = result,
        )
        return result

    async def _handle_modal(self, page, execution) -> ResolutionResult:
        """
        Modal appeared unexpectedly. Classify it:
        - Cookie consent → auto-dismiss
        - Login wall     → restore session
        - GDPR           → auto-accept
        - Custom modal   → escalate
        """
        modal_text = await page.inner_text("[role=dialog]")

        if any(w in modal_text.lower() for w in ["cookie", "gdpr", "consent"]):
            await self._auto_dismiss_consent(page)
            return ResolutionResult.RESOLVED_AUTO

        if any(w in modal_text.lower() for w in ["sign in", "log in", "create account"]):
            await self._restore_session(page, execution)
            return ResolutionResult.RESOLVED_AUTO

        return ResolutionResult.ESCALATED

    async def _backoff_and_retry(self, page, execution) -> ResolutionResult:
        delay = min(30 * (2 ** execution.retry_count), 300)  # exponential, max 5min
        await asyncio.sleep(delay)
        execution.retry_count += 1
        return ResolutionResult.RETRY
```

### Execution Loop Integration

```python
# core/runtime/execution_loop.py

class ExecutionLoop:

    SEMANTIC_THRESHOLD = 0.70   # below this → ambiguity resolution
    ESCALATION_THRESHOLD = 0.40 # below this → force human escalation

    async def execute_action(
        self,
        action: RecordedAction,
        page: Page,
        execution: Execution,
    ) -> ActionResult:

        # 1. Observe current state
        observation = await self.observer.observe(page)

        # 2. Score against expected state
        score = self.scorer.score(observation, action.expected_state)

        # 3. Route based on score
        if score.value >= self.SEMANTIC_THRESHOLD:
            return await self._execute_direct(action, page)

        if score.value < self.ESCALATION_THRESHOLD:
            return await self._escalate_human(action, observation, execution)

        # Mid-range: attempt resolution
        ambiguity = self.classifier.classify(observation)
        resolution = await self.resolver.resolve(ambiguity, page, execution)

        if resolution == ResolutionResult.RESOLVED_AUTO:
            return await self._execute_direct(action, page)
        else:
            return await self._escalate_human(action, observation, execution)
```

### Success Criteria

- [ ] Execution survives modal injection on 5 real sites
- [ ] Rate-limit detection triggers backoff (not crash)
- [ ] SPA re-render detected and waited for stability
- [ ] Session expiry triggers re-auth (not crash)
- [ ] Every ambiguity resolution logged in Mutation Ledger with type + strategy

---

## FIX-04 — Intent vs State {#fix-04}

### Root Cause

The Mutation Ledger answers:
```
Who changed it? Why? Based on what evidence?
```

But the system has no model for:
```
Is this task still what the human wants?
Has the goal become irrelevant?
Is the workflow working toward an obsolete intent?
```

State can be perfectly preserved while intent has completely changed.

### The Fix: Intent Model Layer

```python
# core/intent/intent_model.py

@dataclass
class Intent:
    id: str
    task_id: str
    persona_id: str
    statement: str                    # "Apply to 50 AI engineering jobs"
    created_at: datetime

    # Structured decomposition
    goal_type: GoalType               # ACQUIRE | MAINTAIN | COMPLETE | EXPLORE
    target_quantity: Optional[int]    # 50
    target_domain: Optional[str]      # "AI engineering jobs"
    deadline: Optional[datetime]
    success_conditions: list[str]     # ["received interview", "offer extended"]
    failure_conditions: list[str]     # ["account banned", "goal achieved elsewhere"]

    # Lifecycle
    status: IntentStatus
    last_validated_at: datetime
    validation_interval_days: int     # how often to check relevance

class IntentStatus(Enum):
    ACTIVE     = "active"
    ACHIEVED   = "achieved"      # success condition met
    OBSOLETE   = "obsolete"      # human explicitly cancelled
    STALE      = "stale"         # not validated recently
    CONFLICTED = "conflicted"    # contradicts another active intent
```

### Intent Validator: Staleness Detection

```python
# core/intent/intent_validator.py

class IntentValidator:
    """
    Runs on a schedule. Detects when an intent may no longer reflect
    current human goals. Surfaces to human for confirmation.
    Does NOT auto-cancel intents — human decides.
    """

    STALE_THRESHOLD_DAYS = 30

    def validate_all(self, principal_id: str) -> list[ValidationResult]:
        intents = self.intent_repo.list_active(principal_id)
        results = []

        for intent in intents:
            result = self._validate_single(intent)
            results.append(result)

        return results

    def _validate_single(self, intent: Intent) -> ValidationResult:
        checks = [
            self._check_staleness(intent),
            self._check_success_achieved(intent),
            self._check_failure_triggered(intent),
            self._check_conflict_with_peers(intent),
            self._check_execution_progress(intent),
        ]

        issues = [c for c in checks if c.has_issue]

        if not issues:
            return ValidationResult.HEALTHY

        return ValidationResult(
            intent_id = intent.id,
            issues    = issues,
            recommendation = self._recommend_action(issues),
            requires_human_confirmation = True,  # ALWAYS — never auto-decide
        )

    def _check_success_achieved(self, intent: Intent) -> Check:
        """
        Did the human achieve this goal through a different channel?
        Example: Got a job offer, so "Apply to 50 jobs" is now obsolete.
        This requires cross-intent awareness.
        """
        related_executions = self.execution_repo.list_by_task(intent.task_id)
        success_signals = [
            ex for ex in related_executions
            if any(
                cond.lower() in ex.final_page_text.lower()
                for cond in intent.success_conditions
            )
        ]
        if success_signals:
            return Check(
                has_issue=True,
                type=CheckType.SUCCESS_SIGNAL_DETECTED,
                evidence=success_signals[0].id,
            )
        return Check(has_issue=False)

    def _check_execution_progress(self, intent: Intent) -> Check:
        """
        Is the execution making progress toward the goal?
        50 applications → 0 successful after 20 runs = something is wrong.
        """
        executions = self.execution_repo.list_by_intent(intent.id)
        if len(executions) < 5:
            return Check(has_issue=False)

        recent = executions[-5:]
        success_rate = sum(1 for e in recent if e.status == ExecutionStatus.COMPLETED) / 5

        if success_rate < 0.2:
            return Check(
                has_issue=True,
                type=CheckType.LOW_SUCCESS_RATE,
                evidence=f"Recent success rate: {success_rate:.0%}",
            )
        return Check(has_issue=False)
```

### Intent Timeline: Preserving Human Intent Across Time

```python
# core/intent/intent_timeline.py

class IntentTimeline:
    """
    Immutable append-only log of intent evolution.
    Answers: "What did the human want, when, and why did it change?"
    This is what "preserving human intent across years" actually means.
    """

    def record_creation(self, intent: Intent, evidence: str) -> None:
        self.timeline.append(IntentEvent(
            type      = IntentEventType.CREATED,
            intent_id = intent.id,
            timestamp = datetime.utcnow(),
            statement = intent.statement,
            evidence  = evidence,
        ))

    def record_modification(
        self,
        intent: Intent,
        field: str,
        old_value: Any,
        new_value: Any,
        reason: str,
    ) -> None:
        self.timeline.append(IntentEvent(
            type      = IntentEventType.MODIFIED,
            intent_id = intent.id,
            timestamp = datetime.utcnow(),
            delta     = {"field": field, "from": old_value, "to": new_value},
            reason    = reason,
        ))

    def record_obsolescence(self, intent: Intent, reason: str) -> None:
        self.timeline.append(IntentEvent(
            type      = IntentEventType.OBSOLETED,
            intent_id = intent.id,
            timestamp = datetime.utcnow(),
            reason    = reason,
        ))

    def reconstruct_at(self, intent_id: str, point_in_time: datetime) -> Intent:
        """
        Replay the intent timeline up to a point in time.
        Useful for: "What did I want in January? Why did I stop?"
        """
        events = [e for e in self.timeline if e.intent_id == intent_id and e.timestamp <= point_in_time]
        return self._replay_events(events)
```

### CLI: Intent Management

```bash
bm intent create  --persona freelancer --statement "Apply to 50 AI jobs" \
                  --success "received interview" --deadline 2026-09-01
bm intent list    --persona freelancer
bm intent status  <intent_id>
bm intent history <intent_id>     # full timeline
bm intent resolve <intent_id> --outcome achieved
bm intent validate                # run validator now
```

### Success Criteria

- [ ] Intent created and linked to task at task creation time
- [ ] Validator runs on schedule and surfaces stale intents
- [ ] Intent timeline reconstructable at any past date
- [ ] `bm intent history` shows full evolution with reasons
- [ ] Conflicting intents detected and surfaced (not auto-resolved)

---

## FIX-05 — PySide6 → Tauri {#fix-05}

### Root Cause

PySide6 was chosen for "native Python integration." But:

- NotebookMG is already built on Tauri v2 + React — proven stack
- Python backend (bm CLI) is accessible via sidecar from Tauri
- PySide6 packaging is complex, especially on Windows
- Qt licensing overhead for a solo project is unnecessary friction
- All existing BrowserMind Python infrastructure stays unchanged

### The Fix: Tauri v2 Sidecar Architecture

```
React Frontend (Tauri window)
    ↓  Tauri commands
Rust Bridge Layer (thin)
    ↓  sidecar spawn
Python BM Kernel (bm CLI)
    ↓  existing infrastructure
SQLite + Playwright + Vault
```

The Rust layer is a thin bridge. It spawns the Python sidecar and proxies
JSON between the frontend and the kernel. No Rust business logic needed.

### Tauri Sidecar Setup

```rust
// src-tauri/src/kernel_bridge.rs

use tauri::Manager;
use serde_json::Value;

#[tauri::command]
async fn bm_command(
    app: tauri::AppHandle,
    command: String,
    args: Vec<String>,
) -> Result<Value, String> {

    let sidecar = app.shell()
        .sidecar("bm-kernel")
        .map_err(|e| e.to_string())?;

    let (mut rx, _child) = sidecar
        .args(&[command.as_str()].iter().chain(args.iter()).collect::<Vec<_>>())
        .spawn()
        .map_err(|e| e.to_string())?;

    let mut output = String::new();
    while let Some(event) = rx.recv().await {
        match event {
            tauri_plugin_shell::process::CommandEvent::Stdout(line) => {
                output.push_str(&String::from_utf8_lossy(&line));
            }
            tauri_plugin_shell::process::CommandEvent::Terminated(_) => break,
            _ => {}
        }
    }

    serde_json::from_str(&output).map_err(|e| e.to_string())
}
```

### Python Kernel: JSON Mode

```python
# bm/cli/json_mode.py
# When called with --json flag, output machine-readable JSON instead of human text

import json, sys

def json_output(data: dict) -> None:
    print(json.dumps(data), flush=True)
    sys.exit(0)

def json_error(error: str, code: int = 1) -> None:
    print(json.dumps({"error": error, "code": code}), flush=True)
    sys.exit(code)

# Usage in existing CLI commands:
# if args.json: json_output({"personas": [...]})
# else: pretty_print_table(...)
```

### React Frontend: Operator UI

```tsx
// src/components/ExecutionDashboard.tsx

import { invoke } from "@tauri-apps/api/core";

interface Execution {
  id: string;
  workflow_name: string;
  status: "running" | "paused" | "completed" | "failed" | "awaiting_human";
  current_action: string;
  progress: number;
  screenshot?: string;
}

export function ExecutionDashboard() {
  const [executions, setExecutions] = useState<Execution[]>([]);

  useEffect(() => {
    const poll = setInterval(async () => {
      const result = await invoke<{ executions: Execution[] }>(
        "bm_command",
        { command: "execution", args: ["list", "--json", "--active"] }
      );
      setExecutions(result.executions);
    }, 1000);
    return () => clearInterval(poll);
  }, []);

  return (
    <div className="execution-dashboard">
      {executions.map(ex => (
        <ExecutionCard
          key={ex.id}
          execution={ex}
          onResume={() => invoke("bm_command", {
            command: "execution",
            args: ["resume", ex.id, "--json"]
          })}
        />
      ))}
    </div>
  );
}

// Human interrupt card — shown when execution.status === "awaiting_human"
function ExecutionCard({ execution, onResume }: { execution: Execution, onResume: () => void }) {
  if (execution.status === "awaiting_human") {
    return (
      <div className="interrupt-card">
        <h3>⚠️ Human Action Required</h3>
        <p>{execution.current_action}</p>
        {execution.screenshot && (
          <img src={`data:image/png;base64,${execution.screenshot}`} />
        )}
        <button onClick={onResume}>Resume After Handling</button>
      </div>
    );
  }
  // ... normal card
}
```

### Migration Steps

```bash
# Step 1: Add JSON output mode to existing bm CLI
# (no structural changes — just add --json flag to commands)

# Step 2: Create Tauri project alongside existing Python kernel
npm create tauri-app@latest bm-operator -- --template react-ts

# Step 3: Configure sidecar in tauri.conf.json
# Step 4: Build React UI (reuse NotebookMG design system patterns)
# Step 5: Package Python kernel as sidecar binary via PyInstaller

# Build command:
pyinstaller --onefile bm/cli/main.py --name bm-kernel
```

### Success Criteria

- [ ] `bm execution list --json` returns parseable JSON
- [ ] Tauri window launches and shows active executions
- [ ] Human interrupt card appears and disappears on resume
- [ ] App packages to single installer on Windows and Linux
- [ ] Python kernel sidecar starts/stops with Tauri lifecycle

---

## FIX-06 — Competitive Repositioning {#fix-06}

### Root Cause

BrowserMind is currently described as a "Personal Web OS" — a large, ambitious
framing that competes directly with OpenAI Operator, Claude Computer Use, and
Google Project Mariner.

All those competitors are cloud-first, stateless between sessions, have no persona
isolation, no mutation auditability, and no offline mode.

The kernel BrowserMind already built solves a problem none of them address:
**trusted, auditable, human-sovereign web automation.**

### Three Reframings

Each reframing targets a different market with the same underlying kernel:

---

**Reframing A — Privacy-First Multi-Identity Browser Manager**

```
Target: Privacy advocates, journalists, security researchers,
        people with multiple professional identities

Pitch: "Isolated browser personas with cryptographic ownership.
        Your work persona never leaks to your medical records.
        Your freelance identity never bleeds into your personal life.
        Everything audited, everything local, nothing in the cloud."

Time to build: 2 weeks on existing kernel
Differentiator: No competitor offers persona-level browser isolation
                with local-first vault and audit log
```

**Reframing B — Automation Audit Layer for Teams**

```
Target: Enterprise automation teams, legal compliance, medical data entry

Pitch: "Every automated action answered: who did it, why, what evidence,
        reversible at any point. HIPAA-adjacent auditability for
        browser workflows."

Time to build: 3 weeks (expose Mutation Ledger as readable report)
Differentiator: The Mutation Ledger is already built — this is packaging
```

**Reframing C — Workflow Replay Engine (Developer Tool)**

```
Target: Developers building QA, testing, RPA workflows

Pitch: "Record once with a real browser. Replay reliably with
        semantic selector resolution. Audit every step.
        Works on authenticated sites."

Time to build: 4 weeks (Human-in-Loop Recording from FIX-01 + Tauri UI)
Differentiator: Selenium/Playwright require code; this requires only recording
```

### Recommended Order

Start with **Reframing A** (fastest, clearest niche, immediate value).
Build toward **Reframing C** as the workflow recording layer matures.
**Reframing B** is the long-term enterprise angle.

### Immediate Proof Actions

These are the minimum viable evidence items that change the hiring/funding narrative:

```
1. Record a real workflow on a real authenticated site
   → Demo video on GitHub README
   → "BrowserMind recorded and replayed a full Upwork job application"

2. Mutation Ledger export
   → Screenshot of a real audit trail with real actions
   → "Every action is explained: who, why, what evidence"

3. Persona isolation demo
   → Screen recording: two Chrome profiles, two identities, zero leakage
   → This is visually compelling and immediately understandable

These three things are buildable in parallel with FIX-01/02/03.
None require new architecture — only running the existing system on real data.
```

---

## Execution Timeline {#timeline}

```
Week 1-2    FIX-05 (Tauri migration)
            ├── bm CLI --json mode
            ├── Tauri project scaffold
            └── Basic Operator UI shell

Week 3-4    FIX-01 (Shadow Recorder)
            ├── ShadowRecorder implementation
            ├── SelectorFingerprint schema
            └── Record 3 real workflows

Week 5-6    FIX-01 (Replay Engine)
            ├── SelectorResolver
            ├── InterruptProtocol
            └── End-to-end replay test on 3 sites

Week 7-8    FIX-03 (Semantic Execution)
            ├── SemanticStateScorer
            ├── AmbiguityClassifier
            └── AmbiguityResolver (all types)

Week 9      FIX-02 (Persona Schema Migration)
            ├── Two-layer identity model
            ├── PersonaShareGrant
            └── Migration script on existing data

Week 10     FIX-04 (Intent Model)
            ├── Intent entity + lifecycle
            ├── IntentValidator
            └── IntentTimeline

Week 11-12  FIX-06 (Proof + Positioning)
            ├── Demo video: recorded workflow
            ├── Demo video: persona isolation
            ├── Mutation Ledger export screenshot
            └── GitHub README rewrite
```

---

## Success Criteria {#success}

### System Level

| Criterion | Target |
|-----------|--------|
| Workflows recorded on real authenticated sites | ≥ 3 sites |
| Workflow replay success rate | ≥ 70% within 24h |
| CAPTCHA / 2FA handled without crash | 100% (escalate, not crash) |
| Cross-persona access logged in Ledger | 100% of accesses |
| Intent validation runs on schedule | Weekly minimum |
| Ambiguity types handled without human | ≥ 4 of 7 types |
| Tauri app packages to single installer | Windows + Linux |

### Proof Level

| Item | Status |
|------|--------|
| Demo video: end-to-end workflow recording + replay | Required |
| Demo video: persona isolation (2 profiles, 0 leakage) | Required |
| Mutation Ledger export with real data | Required |
| GitHub README with architecture diagram | Required |
| One public blog post: BrowserMind Evolution story | Recommended |

---

*BrowserMind Fix Plan v1.0 — Internal document — June 2026*
