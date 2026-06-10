"""P6 Utility Validation: Evidence Ledger and Authority Engine.

A minimal tracking mechanism to record if Representation actually helped Replay.
"""
from dataclasses import dataclass
from typing import List

@dataclass
class EvidenceRow:
    ontology_id: str
    trace_id: str
    outcome: str  # "SUCCESS" or "FAILURE"
    surface_drift: bool
    compression_ratio: float

class EvidenceLedger:
    def __init__(self):
        self.rows: List[EvidenceRow] = []
        
    def record(self, row: EvidenceRow):
        self.rows.append(row)
        
class AuthorityEngine:
    """Minimal Authority Engine to track confirm/refute ratios."""
    def __init__(self, ledger: EvidenceLedger):
        self.ledger = ledger
        
    def get_stats(self) -> dict:
        stats = {}
        for row in self.ledger.rows:
            if row.ontology_id not in stats:
                stats[row.ontology_id] = {"success": 0, "total": 0, "drift_success": 0, "drift_total": 0, "avg_compression": 0.0}
                
            s = stats[row.ontology_id]
            s["total"] += 1
            if row.outcome == "SUCCESS":
                s["success"] += 1
                
            if row.surface_drift:
                s["drift_total"] += 1
                if row.outcome == "SUCCESS":
                    s["drift_success"] += 1
                    
            # Incremental average for compression
            s["avg_compression"] = s["avg_compression"] + (row.compression_ratio - s["avg_compression"]) / s["total"]
            
        return stats

class AuthorityEngineLite:
    """Minimal Authority Engine to compute a single formal score."""
    def __init__(self, ledger: EvidenceLedger):
        self.ledger = ledger
        
    def calculate_authority_scores(self) -> dict:
        """Calculates Authority Score: (Drift Survival * 0.7) + (Normalized Compression * 0.3)"""
        stats = {}
        for row in self.ledger.rows:
            if row.ontology_id not in stats:
                stats[row.ontology_id] = {"success": 0, "total": 0, "drift_success": 0, "drift_total": 0, "avg_compression": 0.0}
                
            s = stats[row.ontology_id]
            s["total"] += 1
            if row.outcome == "SUCCESS":
                s["success"] += 1
            if row.surface_drift:
                s["drift_total"] += 1
                if row.outcome == "SUCCESS":
                    s["drift_success"] += 1
            s["avg_compression"] = s["avg_compression"] + (row.compression_ratio - s["avg_compression"]) / s["total"]

        scores = {}
        for ont, s in stats.items():
            if s["drift_total"] == 0:
                survival_rate = 0.0
            else:
                survival_rate = s["drift_success"] / s["drift_total"]
                
            # Normalize compression to a 0-1 scale (cap at 5x)
            norm_comp = min(s["avg_compression"] / 5.0, 1.0)
            
            # The official Authority Score formula for P6C
            scores[ont] = (survival_rate * 0.7) + (norm_comp * 0.3)
            
        return scores

