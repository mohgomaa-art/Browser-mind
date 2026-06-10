"""
goal_spec.py — Declarative goal specification for the L14 Planning layer.

A GoalSpec names a high-level intent ("purchase an item", "submit a job application")
and provides enough context for GoalDecomposer to route through the SSTG and for
CapabilityDispatcher to locate and execute the right WorkflowTemplates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GoalSpec:
    """
    Declarative descriptor for a high-level execution goal.

    Fields:
        goal_id:            Stable identifier, e.g. "purchase_item", "apply_job".
        description:        Human-readable label for logging / UI.
        target_state:       SSTG fingerprint of the desired end state.
                            Must match a node key in the SemanticStateTransitionGraph.
        capability_hints:   Ordered list of capability_hash values that the planner
                            should prefer when decomposing the path.  May be empty.
        start_state:        Optional SSTG fingerprint for the assumed start state.
                            If None, the current live page state is used at runtime.
        site_key:           Domain / environment key (e.g. "amazon", "linkedin").
                            Used by CapabilityDispatcher to prefer site-specific templates.
        persona_id:         Persona UUID string.  Forwarded to ReplayEngine.
        constraints:        Arbitrary key-value constraints passed to the verifier
                            (e.g. {"min_price": 0, "max_price": 100}).
        metadata:           Catch-all for caller-specific extensions.
    """
    goal_id: str
    description: str
    target_state: str

    capability_hints: List[str] = field(default_factory=list)
    start_state: Optional[str] = None
    site_key: str = ""
    persona_id: str = ""
    constraints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def with_start(self, start_state: str) -> "GoalSpec":
        """Return a copy with a concrete start state."""
        from dataclasses import replace
        return replace(self, start_state=start_state)


# ---------------------------------------------------------------------------
# Pre-defined goal specs for common web tasks
# ---------------------------------------------------------------------------

GOAL_LOGIN = GoalSpec(
    goal_id="login",
    description="Authenticate with site credentials",
    target_state="authenticated",
    capability_hints=["login", "navigate_to_login"],
)

GOAL_SEARCH = GoalSpec(
    goal_id="search",
    description="Search for items or content",
    target_state="search_results_loaded",
    capability_hints=["search", "navigate_to_search"],
)

GOAL_CHECKOUT = GoalSpec(
    goal_id="checkout",
    description="Complete a purchase checkout flow",
    target_state="order_confirmed",
    capability_hints=["add_to_cart", "checkout", "place_order"],
)

GOAL_SUBMIT_FORM = GoalSpec(
    goal_id="submit_form",
    description="Fill and submit a web form",
    target_state="form_submitted",
    capability_hints=["fill_form", "submit_form"],
)

GOAL_APPLY_JOB = GoalSpec(
    goal_id="apply_job",
    description="Submit a job application",
    target_state="application_submitted",
    capability_hints=["navigate_to_job", "fill_application", "submit_form"],
)
