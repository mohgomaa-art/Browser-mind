"""
Phase B4: Dataset Compiler - Gold Compiler
Orchestrates the bottom-up generation pipeline and strictly segregates outputs.
"""
import json
import os
import uuid
from typing import Dict, Any

from .state_family_builder import StateFamilyBuilder
from .opportunity_graph_generator import OpportunityGraphGenerator
from .difficulty_estimator import DifficultyEstimator
from .task_template_library import TaskTemplateLibrary
from .label_builder import LabelBuilder
from .rejection_gates import RejectionGates
from .coverage_gates import CoverageGates

class GoldCompiler:
    def __init__(self, base_dir: str):
        self.interaction_dir = os.path.join(base_dir, "gold_interaction")
        self.extraction_dir = os.path.join(base_dir, "gold_extraction")
        
        os.makedirs(self.interaction_dir, exist_ok=True)
        os.makedirs(self.extraction_dir, exist_ok=True)
        
        self.family_builder = StateFamilyBuilder()
        self.coverage_gates = CoverageGates()  # Now global to the compiler
        self.opportunity_generator = OpportunityGraphGenerator(self.coverage_gates)
        self.difficulty_estimator = DifficultyEstimator()
        self.template_lib = TaskTemplateLibrary()
        self.gates = RejectionGates()

    def process_state(self, url: str, ax_graph: Dict[str, Any]):
        # B1: State Family Identification
        family_data = self.family_builder.identify_family(ax_graph)
        
        # B1: Opportunity Graph Generation (with built-in coverage rejection)
        opportunities = self.opportunity_generator.generate(ax_graph, family_data)
        
        interaction_samples = []
        extraction_samples = []

        # Synthesize Interaction Samples
        for opp in opportunities.get("interaction_opportunities", []):
            diff_data = self.difficulty_estimator.estimate(ax_graph, opp)
            goal = self.template_lib.generate_interaction_goal(opp)
            label = LabelBuilder.build_interaction_label(action="click", element_idx=opp["node"])
            
            sample = {
                "id": str(uuid.uuid4()),
                "url": url,
                "state_family_data": family_data,
                "opportunity_data": opp,
                "task_type": "interaction",
                "goal": goal,
                "label": label,
                "difficulty": diff_data["difficulty"],
                "metrics": diff_data["metrics"],
                "ax_graph": ax_graph
            }
            
            if self.gates.pass_all_gates(sample):
                interaction_samples.append(sample)
                self._update_coverage_metrics(family_data["state_family"], opp["task_family"])

        # Synthesize Extraction Samples
        for opp in opportunities.get("extraction_opportunities", []):
            diff_data = self.difficulty_estimator.estimate(ax_graph, opp)
            goal = self.template_lib.generate_extraction_goal(opp)
            label = LabelBuilder.build_extraction_label(answers=[str(opp["node_ids"][0])], source_nodes=opp["node_ids"])
            
            sample = {
                "id": str(uuid.uuid4()),
                "url": url,
                "state_family_data": family_data,
                "opportunity_data": opp,
                "task_type": "extraction",
                "goal": goal,
                "label": label,
                "difficulty": diff_data["difficulty"],
                "metrics": diff_data["metrics"],
                "ax_graph": ax_graph
            }
            
            if self.gates.pass_all_gates(sample):
                extraction_samples.append(sample)
                self._update_coverage_metrics(family_data["state_family"], opp["task_family"])

        self._save_samples(interaction_samples, self.interaction_dir)
        self._save_samples(extraction_samples, self.extraction_dir)
        
        return len(interaction_samples), len(extraction_samples)

    def _update_coverage_metrics(self, state_family: str, task_family: str):
        self.coverage_gates.total_samples += 1
        self.coverage_gates.state_family_counts[state_family] += 1
        self.coverage_gates.task_family_counts[task_family] += 1

    def _save_samples(self, samples: list, directory: str):
        for s in samples:
            path = os.path.join(directory, f"{s['id']}.json")
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(s, f, indent=2)
