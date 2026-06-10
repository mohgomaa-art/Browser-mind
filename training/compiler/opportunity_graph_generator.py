"""
Phase B1 / V1.2: Opportunity Graph Generator
Quality = task_value × actionability × confidence × rarity
task_value = capability_prior × workflow_potential × cross_site_value × completion_probability
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from training.capability_taxonomy import build_zone_text_map
from training.task_value_estimator import compose_quality_score, estimate_task_value

MAX_PER_STATE_FAMILY_ROLE = 3
MIN_QUALITY_SCORE = 0.5

_LOW_VALUE_EXTRACTION_TERMS = frozenset(
    {
        "navigation menu",
        "site-wide links",
        "site wide links",
        "footer",
        "skip to",
        "skip navigation",
        "breadcrumb",
        "related links",
        "quick links",
        "on this page",
        "table of contents",
    }
)


class OpportunityGraphGenerator:
    def __init__(self, coverage_gates):
        self.interaction_roles = {
            "button",
            "link",
            "textbox",
            "checkbox",
            "searchbox",
            "combobox",
            "menuitem",
        }
        self.extraction_roles = {"article", "list", "table", "row", "heading", "main"}
        self.coverage_gates = coverage_gates

    def _heading_context(self, ax_graph: Dict[str, Any]) -> List[str]:
        return [
            n.get("name", "")
            for n in ax_graph.get("nodes", [])
            if n.get("role") == "heading" and n.get("name", "").strip()
        ]

    def _actionability(self, name: str, opportunity_type: str) -> float:
        if opportunity_type == "extraction":
            return 0.85 if len(name) < 60 else 0.35
        return 0.9 if len(name) < 40 else 0.25

    def _score_opportunity(
        self,
        *,
        role: str,
        name: str,
        state_family: str,
        confidence: float,
        scarcity: float,
        opportunity_type: str,
        node: Optional[Dict[str, Any]],
        ax_graph: Dict[str, Any],
        heading_context: List[str],
        zone_texts: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        tv = estimate_task_value(
            name,
            role=role,
            state_family=state_family,
            opportunity_type=opportunity_type,
            node=node,
            ax_graph=ax_graph,
            heading_context=heading_context,
            zone_texts=zone_texts,
        )
        actionability = self._actionability(name, opportunity_type)
        rarity = min(1.0, 0.35 + scarcity * 0.65)
        quality = compose_quality_score(
            tv["task_value"],
            actionability=actionability,
            confidence=confidence,
            rarity=rarity,
        )
        return {
            **tv,
            "quality_score": round(quality, 4),
            "actionability": round(actionability, 4),
            "rarity": round(rarity, 4),
        }

    def generate(
        self, ax_graph: Dict[str, Any], family_data: Dict[str, Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        interaction_opportunities: List[Dict[str, Any]] = []
        extraction_opportunities: List[Dict[str, Any]] = []
        role_budget: Dict[str, int] = {}

        state_family = family_data["state_family"]
        confidence = family_data.get("confidence", 1.0)
        nodes = ax_graph.get("nodes", [])
        node_by_idx = {n["idx"]: n for n in nodes if "idx" in n}
        headings = self._heading_context(ax_graph)
        from training.compiler import StateFamilyBuilder

        zones = StateFamilyBuilder().identify_zones(ax_graph).get("zones", [])
        zone_text_by_idx = build_zone_text_map(ax_graph, zones)

        for node in nodes:
            role = node.get("role", "").lower()
            name = node.get("name", "").strip()
            node_id = node.get("idx")

            if node_id is None or not name:
                continue

            budget_key = f"{state_family}:{role}"

            if role in self.interaction_roles:
                if role_budget.get(budget_key, 0) >= MAX_PER_STATE_FAMILY_ROLE:
                    continue

                scored = self._score_opportunity(
                    role=role,
                    name=name,
                    state_family=state_family,
                    confidence=confidence,
                    scarcity=self.coverage_gates.calculate_scarcity(
                        state_family, f"{state_family}_{role}"
                    ),
                    opportunity_type="interaction",
                    node=node,
                    ax_graph=ax_graph,
                    heading_context=headings,
                    zone_texts=zone_text_by_idx.get(node_id, []),
                )

                if scored["quality_score"] < MIN_QUALITY_SCORE:
                    continue
                if scored["learning_stage"] == "skip":
                    continue

                task_family = f"{state_family}_{role}"
                if not self.coverage_gates.is_opportunity_allowed(state_family, task_family):
                    continue

                priority = 0.9 if role in ("button", "textbox", "searchbox") else 0.5
                interaction_opportunities.append(
                    {
                        "node": node_id,
                        "role": role,
                        "name": name,
                        "state_family": state_family,
                        "family_hash": family_data["family_hash"],
                        "opportunity_type": "interaction",
                        "task_family": task_family,
                        "priority": priority,
                        "scarcity_score": self.coverage_gates.calculate_scarcity(
                            state_family, task_family
                        ),
                        "quality_score": scored["quality_score"],
                        "task_value": scored["task_value"],
                        "task_value_factors": scored["task_value_factors"],
                        "capability": scored["capability"],
                        "capability_confidence": scored["capability_confidence"],
                        "learning_stage": scored["learning_stage"],
                    }
                )
                role_budget[budget_key] = role_budget.get(budget_key, 0) + 1

            if role in self.extraction_roles:
                ext_budget_key = f"{state_family}:{role}:extraction"
                if role_budget.get(ext_budget_key, 0) >= MAX_PER_STATE_FAMILY_ROLE:
                    continue

                if any(term in name.lower() for term in _LOW_VALUE_EXTRACTION_TERMS):
                    continue

                scored = self._score_opportunity(
                    role=role,
                    name=name,
                    state_family=state_family,
                    confidence=confidence,
                    scarcity=self.coverage_gates.calculate_scarcity(
                        state_family, f"{state_family}_{role}_extraction"
                    ),
                    opportunity_type="extraction",
                    node=node,
                    ax_graph=ax_graph,
                    heading_context=headings,
                    zone_texts=zone_text_by_idx.get(node_id, []),
                )

                if scored["quality_score"] < MIN_QUALITY_SCORE:
                    continue
                if scored["learning_stage"] == "skip":
                    continue

                task_family = f"{state_family}_{role}_extraction"
                if not self.coverage_gates.is_opportunity_allowed(state_family, task_family):
                    continue

                extraction_opportunities.append(
                    {
                        "node_ids": [node_id],
                        "role": role,
                        "name": name,
                        "state_family": state_family,
                        "family_hash": family_data["family_hash"],
                        "opportunity_type": "extraction",
                        "task_family": task_family,
                        "priority": 0.8 if role in ("table", "article", "list") else 0.4,
                        "scarcity_score": self.coverage_gates.calculate_scarcity(
                            state_family, task_family
                        ),
                        "quality_score": scored["quality_score"],
                        "task_value": scored["task_value"],
                        "task_value_factors": scored["task_value_factors"],
                        "capability": scored["capability"],
                        "capability_confidence": scored["capability_confidence"],
                        "learning_stage": scored["learning_stage"],
                    }
                )
                role_budget[ext_budget_key] = role_budget.get(ext_budget_key, 0) + 1

        return {
            "interaction_opportunities": interaction_opportunities,
            "extraction_opportunities": extraction_opportunities,
        }
