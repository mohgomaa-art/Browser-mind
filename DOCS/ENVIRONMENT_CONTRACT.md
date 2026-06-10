# ENVIRONMENT_CONTRACT.md

> **Status:** Frozen for P1/P2 | Companion: `WORKFLOW_CONTRACT.md`

One page. Separates **class of site** from **this deployment**.

---

## Definitions

### Environment Family

- **What:** A vendor or product class the system knows procedurally.
- **Examples:** `greenhouse`, `lever`, `ashby`, `saucedemo`, `github`.
- **Keyed by:** stable family id (not full URL).
- **Holds:** risk level, anti-bot notes, capability affordances, `WorkflowTemplate`(s).
- **Today in code:** `Environment` in `p1_schemas.py` is **underspecified** — treat as Family until split.

### Environment Instance

- **What:** One concrete deployment the persona actually visits.
- **Examples:**
  - Family `greenhouse` → Instance `job-boards.greenhouse.io/embed/.../airtable`
  - Family `greenhouse` → Instance `jobs.lever.co/netflix` (Lever family separately)
- **Keyed by:** canonical origin + path pattern (registered).
- **Holds:**
  - Browser profile / storage partition
  - `Identity` (cookies, login state)
  - Recorder sessions tied to **this** origin

### Identity (unchanged role)

- `Identity` belongs to **Persona** + **Environment Family** (schema today: `environment_id`).
- Session material (cookies) is **Instance-specific** in practice — P2 will add `environment_instance_id` on Identity or `BrowserProfile`.

---

## Why it matters

| Without Instance | With Instance |
|------------------|---------------|
| Replay breaks on different host | Profile warms correct origin |
| Selector drift unexplained | Drift scoped to instance |
| "Greenhouse" too vague | Template on family; run on instance |

---

## Mapping (P1 → P2)

| Entity | Family | Instance |
|--------|--------|----------|
| WorkflowTemplate | ✓ | — |
| WorkflowInstance | ✓ (template ref) | ✓ (default instance) |
| DemonstrationSession | ✓ | ✓ (required) |
| Replay | ✓ | ✓ (required) |
| Identity | ✓ (type) | ✓ (where logged in) |

---

## Schema direction (not implemented until P1 accepts)

```text
EnvironmentFamily     id, family_key, risk_level, ...
EnvironmentInstance   id, family_id, origin, path_prefix?, label
Identity              persona_id, family_id, instance_id?, identifier
BrowserProfile        instance_id, storage_path, last_warmed_at
```

**P1 minimum:** `EnvironmentInstanceConfig` in `browsermind_core/runtime/environment_config.py` — `profile_dir(store)` → `~/.browsermind/profiles/<family_key>/` (Option B: isolated Chromium profile).

---

## Examples

```text
Family:     greenhouse
Instance:   https://job-boards.greenhouse.io/embed/job_board?for=airtable
Template:   "Greenhouse — submit application"
Instance binding: persona=freelancer, identity=greenhouse_airtable, profile=chrome_profile_3
```

```text
Family:     saucedemo
Instance:   https://www.saucedemo.com/
Template:   "Saucedemo — purchase flow"
```

---

*Frozen — BrowserMind Kernel — June 2026*
