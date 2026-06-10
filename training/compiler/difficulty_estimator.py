"""
Phase B1: Dataset Compiler - Difficulty Estimator
Computes complexity based on DOM features, state family, and workflow length.
"""
from __future__ import annotations

from typing import Any, Dict

_COMPLEX_STATE_FAMILIES = frozenset(
    {
        "checkout_form",
        "signup_form",
        "multi_field_form",
        "settings_panel",
        "application_form",
        "dialog_form",
    }
)


class DifficultyEstimator:
    def estimate(self, ax_graph: Dict[str, Any], opportunity: Dict[str, Any]) -> Dict[str, Any]:
        nodes = ax_graph.get("nodes", [])

        depth_max = max((n.get("depth", 0) for n in nodes), default=0)
        interactive_roles = {"button", "link", "textbox", "combobox", "searchbox", "checkbox"}
        interactive_count = sum(
            1 for n in nodes if n.get("role", "").lower() in interactive_roles
        )
        form_elements = sum(
            1
            for n in nodes
            if n.get("role", "").lower() in {"textbox", "checkbox", "radio", "combobox"}
        )

        task_family = opportunity.get("task_family", "")
        state_family = opportunity.get("state_family", "")

        workflow_length_estimate = 1
        if "login" in task_family or "signup" in task_family or "upload" in task_family:
            workflow_length_estimate = 4
        elif "composer" in task_family or "checkout" in task_family:
            workflow_length_estimate = 8
        elif state_family in _COMPLEX_STATE_FAMILIES:
            workflow_length_estimate = 5

        score = 0
        if depth_max > 10:
            score += 1
        if interactive_count > 20:
            score += 1
        if workflow_length_estimate > 3:
            score += 1
        if workflow_length_estimate > 6:
            score += 2
        if state_family in _COMPLEX_STATE_FAMILIES:
            score += 2

        if score <= 1:
            difficulty = "easy"
        elif score <= 3:
            difficulty = "medium"
        else:
            difficulty = "hard"

        return {
            "difficulty": difficulty,
            "metrics": {
                "dom_depth": depth_max,
                "interactive_density": interactive_count,
                "form_complexity": form_elements,
                "workflow_length_estimate": workflow_length_estimate,
                "state_family": state_family,
            },
        }
