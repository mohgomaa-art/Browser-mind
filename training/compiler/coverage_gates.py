"""
Phase B1: Dataset Compiler - Coverage Gates
Evaluates scarcity and enforces distribution limits before sample generation.
"""
from typing import Dict, Any
import collections

class CoverageGates:
    def __init__(self):
        self.MAX_STATE_FAMILY_SHARE = 0.25
        self.MAX_TASK_FAMILY_SHARE = 0.15
        
        # In production, these pull from a live DB indexing the dataset
        self.total_samples = 0
        self.state_family_counts = collections.Counter()
        self.task_family_counts = collections.Counter()
        
    def calculate_scarcity(self, state_family: str, task_family: str) -> float:
        """Returns a scarcity score between 0.0 (too common) and 1.0 (extremely rare)."""
        if self.total_samples == 0:
            return 1.0
            
        task_share = self.task_family_counts[task_family] / self.total_samples
        return max(0.0, 1.0 - (task_share / self.MAX_TASK_FAMILY_SHARE))
        
    def is_opportunity_allowed(self, state_family: str, task_family: str) -> bool:
        """Determines if building a sample for this task family would break limits."""
        if self.total_samples < 50:  # Allow initial filling
            return True
            
        state_share = (self.state_family_counts[state_family] + 1) / (self.total_samples + 1)
        if state_share > self.MAX_STATE_FAMILY_SHARE:
            return False
            
        task_share = (self.task_family_counts[task_family] + 1) / (self.total_samples + 1)
        if task_share > self.MAX_TASK_FAMILY_SHARE:
            return False
            
        return True
