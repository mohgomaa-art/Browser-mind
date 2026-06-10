"""
Phase B: Dataset Compiler - Label Builder
Constructs the ground-truth dual-mode label.
"""
from typing import Dict, Any, List

class LabelBuilder:
    @staticmethod
    def build_interaction_label(action: str, element_idx: int, value: str = None) -> Dict[str, Any]:
        """
        Builds a strict interaction label.
        """
        label = {
            "action": action,
            "element_idx": element_idx
        }
        if value is not None:
            label["value"] = value
        return label

    @staticmethod
    def build_extraction_label(answers: List[str], source_nodes: List[int]) -> Dict[str, Any]:
        """
        Builds a strict extraction label.
        """
        return {
            "answers": answers,
            "source_nodes": source_nodes
        }
