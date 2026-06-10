"""
Phase B1: Dataset Compiler - Rejection Gates
A merciless, deterministic filter. If a sample fails any gate, it is rejected.
"""
from typing import Dict, Any

class RejectionGates:
    @staticmethod
    def pass_all_gates(sample: Dict[str, Any]) -> bool:
        """
        Runs the sample through all gates sequentially.
        """
        if not RejectionGates._gate_target_missing(sample): return False
        if not RejectionGates._gate_goal_invalid(sample): return False
        if not RejectionGates._gate_label_missing(sample): return False
        if not RejectionGates._gate_verification_weak(sample): return False
        if not RejectionGates._gate_replay_failed(sample): return False
        
        return True

    @staticmethod
    def _gate_target_missing(sample: Dict[str, Any]) -> bool:
        """Reject if target nodes do not exist in the AX graph."""
        label = sample.get("label", {})
        ax_graph = sample.get("ax_graph", {})
        nodes = {n.get("idx"): n for n in ax_graph.get("nodes", [])}
        
        if sample.get("task_type") == "interaction":
            target_node = label.get("element_idx")
            if target_node is None or target_node not in nodes:
                return False
        elif sample.get("task_type") == "extraction":
            source_nodes = label.get("source_nodes", [])
            if not source_nodes or any(n_idx not in nodes for n_idx in source_nodes):
                return False
        else:
            return False
            
        return True

    @staticmethod
    def _gate_goal_invalid(sample: Dict[str, Any]) -> bool:
        """Reject if the goal is empty, non-string, or syntactically broken."""
        goal = sample.get("goal")
        if not goal or not isinstance(goal, str) or len(goal.strip()) < 3:
            return False
        return True

    @staticmethod
    def _gate_label_missing(sample: Dict[str, Any]) -> bool:
        """Reject if the label structure is missing or malformed."""
        label = sample.get("label")
        if not label or not isinstance(label, dict):
            return False
            
        if sample.get("task_type") == "interaction":
            if "action" not in label or "element_idx" not in label:
                return False
        elif sample.get("task_type") == "extraction":
            if "answers" not in label or "source_nodes" not in label:
                return False
        return True

    @staticmethod
    def _gate_verification_weak(sample: Dict[str, Any]) -> bool:
        """Reject if the causal verification step (simulated here) was weak or ambiguous."""
        # For Phase B1, this is a placeholder for the actual DOM Verification Engine
        # In production, this checks if the action resulted in a verified state transition.
        return sample.get("verified", True)

    @staticmethod
    def _gate_replay_failed(sample: Dict[str, Any]) -> bool:
        """Reject if the sample cannot be successfully replayed in a deterministic test."""
        # For Phase B1, placeholder for the replay runner.
        return sample.get("replay_success", True)
