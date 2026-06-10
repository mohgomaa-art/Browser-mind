"""DemonstrationCompiler — converts a DemonstrationSession into a reusable WorkflowTemplate."""
from __future__ import annotations

from browsermind_core.ontology.p1_schemas import WorkflowTemplate
from browsermind_core.recorder.demonstration_session import DemonstrationSession
from browsermind_core.recorder.replayability_analyzer import ReplayabilityAnalyzer
from browsermind_core.console.session import KernelSession
from urllib.parse import urlparse, urlunparse


def _field_registry():
    """Lazy import to avoid circular dependency with KernelSession at module load."""
    from browsermind_core.ontology.field_registry import get_registry
    return get_registry()


# ── Semantic equivalence groups ──────────────────────────────────────────────
# A target_name lookup maps to a stable group label. The replay-time
# TargetResolver consults the group when the recorded name fails so a
# template recorded against "Apply Now" can still resolve "Submit Application"
# on a sister site.
SEMANTIC_EQUIVALENTS: dict[str, list[str]] = {
    "submit_application": [
        "Apply Now", "Submit Application", "Continue Application",
        "Apply", "Submit", "Apply for Job", "Send Application",
    ],
    "login":   ["Log In", "Sign In", "Login", "Sign in", "Log in"],
    "register": [
        "Sign Up", "Register", "Create Account", "Get Started",
        "Join", "Create Profile",
    ],
    "search":  ["Search", "Go", "Find", "Look Up", "Search Jobs"],
    "upload_file": [
        "Upload", "Choose File", "Browse", "Select File",
        "Attach", "Upload Resume", "Add File",
    ],
    "next_step": ["Next", "Continue", "Proceed", "Next Step", "Continue to Next Step"],
    "confirm":  ["Confirm", "OK", "Accept", "Agree", "Done", "Complete", "Finish"],
    "checkout": ["Checkout", "Proceed to Checkout", "Check Out", "Buy Now"],
    "add_to_cart": ["Add to Cart", "Add to Bag", "Add", "Add Item"],
    "logout":   ["Log Out", "Sign Out", "Logout", "Sign out"],
}

_LABEL_TO_GROUP: dict[str, str] = {
    label.lower(): group
    for group, labels in SEMANTIC_EQUIVALENTS.items()
    for label in labels
}


def resolve_semantic_group(target_name: str | None) -> str | None:
    """Return the semantic group for a target name, or None if no group matches."""
    if not target_name:
        return None
    return _LABEL_TO_GROUP.get(target_name.strip().lower())


# Optional-field heuristics. ATS forms (Greenhouse, Lever, Workday) attach
# these EEO/voluntary fields. The compiler tags them so the resolver can
# soft-skip if their react-select widget can't be grounded.
_OPTIONAL_NAME_PATTERNS = (
    "(optional)", "if applicable", "if any", "voluntary",
    "gender", "race", "ethnicity", "veteran", "disability",
    "pronoun", "lgbtq", "compensation expectations",
    "sponsorship", "visa sponsorship",
    "how did you hear",
    "linkedin profile", "linkedin url", "website", "portfolio",
)

# Always-required signals: if a name matches these we never mark optional
# even when an above pattern co-occurs.
_REQUIRED_NAME_PATTERNS = (
    "first name", "last name", "email", "password", "submit", "apply",
)


def _classify_step_optionality(act) -> str:
    """Return 'required' | 'optional' | 'structural'."""
    action_type = (getattr(act, "action_type", "") or "").lower()
    if action_type in ("navigate", "session"):
        return "structural"
    name = (getattr(act, "target_name", "") or "").strip().lower()
    descriptor = getattr(act, "descriptor", {}) or {}
    label = (descriptor.get("container_label") or "").strip().lower()
    haystack = name + " " + label

    for pat in _REQUIRED_NAME_PATTERNS:
        if pat in haystack:
            return "required"
    for pat in _OPTIONAL_NAME_PATTERNS:
        if pat in haystack:
            return "optional"
    return "required"


class DemonstrationCompiler:
    def __init__(self, kernel_session: KernelSession):
        self.ks = kernel_session

    def compile(self, session: DemonstrationSession, template_name: str) -> WorkflowTemplate:
        """
        Convert a recorded semantic session into a WorkflowTemplate.
        Raw values are extracted into parameter bindings (vault refs).
        """
        steps = []
        # Seed last_url from session.start_url so the first action's URL is compared
        # against the declared start. Without this, manual navigation before the first
        # recorded action produces no navigate step and replay opens the wrong page.
        last_url = session.start_url or None

        for act in session.actions:
            # Skip session meta-events in the compiled template
            if act.action_type == "session":
                continue
                
            # Anti-bot Noise Filter: Do not compile ephemeral CAPTCHA interactions into the rigid WorkflowTemplate
            # In P3, the Agent Replay engine will detect and solve these dynamically, independent of the template
            is_captcha = False
            target_name = act.target_name.lower() if act.target_name else ""
            if act.target_role == "canvas":
                is_captcha = True
            elif act.action_type == "click" and target_name in ["begin", "loading", "confirm"]:
                # If these are surrounded by canvas clicks, it's a captcha, but let's be safe for this sprint
                is_captcha = True
            elif act.action_type == "submit" and "let's confirm you are human" in target_name:
                is_captcha = True
                
            if is_captcha:
                continue

            # Anti-Redundancy Filter: Filter out redundant `submit` actions if they immediately follow a `click` on a button or generic submit.
            # This prevents the TARGET_CHANGED detachment failures.
            if act.action_type == "submit" and len(steps) > 0:
                last_step = steps[-1]
                if last_step.get("action_type") == "click" and last_step.get("target_role") in ["button", "submit"]:
                    continue

            step_def = {
                "seq": len(steps) + 1,
                "action_type": act.action_type,
                "target_role": act.target_role,
                "target_name": act.target_name,
                "target_selector": act.target_selector,
                "result_state": act.result_state,
                "screenshot_hash": act.screenshot_hash,
                "descriptor": act.descriptor,
            }
            if getattr(act, "recording_evidence", None):
                step_def["recording_evidence"] = act.recording_evidence

            sg = resolve_semantic_group(act.target_name)
            if sg:
                step_def["semantic_group"] = sg

            # Step optionality. The heuristic classifier handles the long tail
            # of forms where no Field is in the registry yet. When a Field DOES
            # resolve, its declared optionality wins — the registry is more
            # authoritative than the string-pattern heuristic.
            step_def["optionality"] = _classify_step_optionality(act)
            descriptor_dict = act.descriptor if isinstance(act.descriptor, dict) else {}
            container_label = descriptor_dict.get("container_label") or ""
            registry_field = (
                _field_registry().resolve(act.target_name)
                or _field_registry().resolve(container_label)
            )
            if registry_field is not None:
                step_def["field_id"]    = registry_field.id
                step_def["field_kind"]  = registry_field.kind.value
                step_def["optionality"] = registry_field.optionality.value
            
            # Parameterize inputs
            if act.vault_ref:
                step_def["input_binding"] = {"type": "vault", "key": act.vault_ref}
            elif act.value is not None:
                # If a value was recorded in plain text, parameterize it as a prompt/input requirement
                param_key = f"input_{len(steps) + 1}_{act.target_name.lower().replace(' ', '_')}"
                if not param_key.strip("_"):
                    param_key = f"input_{len(steps) + 1}"
                step_def["input_binding"] = {"type": "parameter", "key": param_key}
                step_def["default_value"] = act.value
            
            # --- P3.1 Navigation Compilation ---
            # If the URL changed from the last recorded action (and it's not the initial goto),
            # synthesize a navigate step to preserve Workflow Context.
            current_url = act.url
            if current_url and last_url:
                parsed_cur = urlparse(current_url)
                parsed_last = urlparse(last_url)
                # Compare without fragments and trailing slashes
                norm_cur = urlunparse((parsed_cur.scheme, parsed_cur.netloc, parsed_cur.path.rstrip('/'), parsed_cur.params, parsed_cur.query, ''))
                norm_last = urlunparse((parsed_last.scheme, parsed_last.netloc, parsed_last.path.rstrip('/'), parsed_last.params, parsed_last.query, ''))
                
                if act.action_type != "navigate" and norm_cur != norm_last:
                    steps.append({
                        "seq": len(steps) + 1,
                        "action_type": "navigate",
                        "target_role": "browser",
                        "target_name": "context_change",
                        "url": current_url,
                        "target_selector": "",
                        "result_state": "navigation",
                        "screenshot_hash": "",
                    })
                    # Update step_def seq number since we just injected a step
                    step_def["seq"] = len(steps) + 1
            
            if current_url:
                last_url = current_url
                
            # --- P3.1 Compiler Warnings ---
            if act.target_role == "generic":
                step_def["warnings"] = [{"type": "generic_role", "severity": "high", "message": "Target resolved to 'generic'. High risk of TargetNotFound during replay."}]
                
            steps.append(step_def)

        if not steps:
            raise ValueError(
                f"Refusing to compile demonstration {session.id}: 0 steps after filtering. "
                f"Recorded {len(session.actions)} actions, all rejected as captcha/redundant/session-meta. "
                f"Either record additional actions or rerecord without the filtered pages."
            )

        tpl = self.ks.workflow_store.create_template(
            name=template_name,
            description=f"Compiled from demonstration {str(session.id)[:8]}",
            family_key=session.environment_family,
        )
        
        tpl.steps = steps
        tpl.metadata["compiled_from"] = str(session.id)
        tpl.metadata["compiler_version"] = "2.0.0"
        tpl.metadata["recording_version"] = "2.0.0"

        # Stamp compile-time URL so TemplateHealthMonitor can navigate there.
        # The full affordance vector is stamped on first replay (requires a live page).
        _first_nav = next((s for s in steps if s.get("action_type") == "navigate"), None)
        if _first_nav and _first_nav.get("url"):
            tpl.metadata["compile_time_url"] = _first_nav["url"]

        # --- P3.1: Replayability Assessment (observational, non-blocking) ---
        analyzer = ReplayabilityAnalyzer()
        high = ambiguous = unreplayable = 0
        evidence_rows = []
        lesson_reader = getattr(self.ks, "lesson_reader", None)
        env_instance = getattr(session, "environment_instance", None) or ""
        for idx, step in enumerate(tpl.steps):
            assessment = analyzer.assess(step)
            step["replayability"] = assessment   # attach as metadata on the step
            if lesson_reader is not None:
                count = lesson_reader.get_step_failure_count(
                    env=env_instance,
                    action=step.get("action") or "",
                    role=step.get("target_role") or "",
                    name=step.get("target_name") or "",
                    failure_class="TARGET_CHANGED",
                )
                if count >= 3 and assessment["tier"] != "UNREPLAYABLE":
                    evidence_rows.append({
                        "step_seq": idx,
                        "previous_tier": assessment["tier"],
                        "candidate_tier": "AMBIGUOUS",
                        "reason": "lesson_evidence:repeated_target_changed",
                        "observations": count,
                        "requires_human_approval": True,
                        "action": step.get("action"),
                        "role": step.get("target_role") or "",
                        "name": step.get("target_name") or "",
                    })
                    # Self-Learning v1: do NOT mutate the template. Candidate emission below
                    # provides a human-approval surface; runtime keeps the original tier.
                    pass
            tier = step["replayability"]["tier"]
            if tier == "HIGH":             high += 1
            elif tier == "AMBIGUOUS":      ambiguous += 1
            elif tier == "UNREPLAYABLE":   unreplayable += 1

        if unreplayable > 0:
            print(f"  [Compiler WARNING] {unreplayable} step(s) assessed as UNREPLAYABLE. "
                  f"These will likely fail during Replay. "
                  f"(high={high}, ambiguous={ambiguous}, unreplayable={unreplayable})")
        else:
            print(f"  [Compiler] Replayability: high={high}, ambiguous={ambiguous}, unreplayable={unreplayable}")

        tpl.metadata["replayability_summary"] = {
            "high": high, "ambiguous": ambiguous, "unreplayable": unreplayable
        }
        tpl.metadata["lesson_evidence"] = evidence_rows

        # Self-Learning v1: emit a TemplateCandidate carrying the proposed
        # mutations. The compiler does not apply them; an operator must run
        # `bm workflow candidate approve <id>` to commit.
        registry = getattr(self.ks, "candidate_registry", None)
        if registry is not None and evidence_rows:
            from browsermind_core.ontology.template_candidate import TemplateCandidate
            mutations = []
            for ev in evidence_rows:
                mutations.append({
                    "type": "tier_downgrade",
                    "step_seq": ev["step_seq"],
                    "from_tier": ev["previous_tier"],
                    "to_tier": ev["candidate_tier"],
                    "reason": ev["reason"],
                })
            candidate = TemplateCandidate(
                parent_id=tpl.id,
                parent_version=str(tpl.metadata.get("compiler_version", "compiled")),
                mutations=mutations,
                lesson_evidence=evidence_rows,
                previous_state={"steps": tpl.steps},
            )
            registry.save(candidate)
            tpl.metadata["pending_candidate_id"] = str(candidate.id)

        # Save updated template with steps
        self.ks.workflow_store.provider.save(
            self.ks.workflow_store.NS_TEMPLATE, 
            str(tpl.id), 
            tpl.model_dump(mode="json")
        )
        
        self.ks.event_bus.emit(
            "EntityMutated",
            {
                "entity_type": "WorkflowTemplate",
                "entity_id": tpl.id,
                "new_value": {"status": "compiled", "steps": len(steps)},
                "actor": "compiler",
            }
        )
        
        return tpl
