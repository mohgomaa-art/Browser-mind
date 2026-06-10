"""Hypothesis store stats and top exploration targets."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from browsermind_core.learning.capability_hypothesis_store import CapabilityHypothesisStore

store = CapabilityHypothesisStore()
stats = store.stats()

print()
print(f"  Total hypotheses : {stats['total']}")
by_s = stats.get("by_status", {})
for s in ["HYPOTHESIS", "RECURRING", "EMERGING", "CANDIDATE", "PROMOTED", "REFUTED"]:
    cnt = by_s.get(s, 0)
    if cnt:
        print(f"    {s:<14} : {cnt}")

print()
targets = store.exploration_targets(limit=10)
if targets:
    print("  Top exploration targets (by freq x importance):")
    for h in targets:
        inv_preview = " | ".join(h.invariants[:3])
        print(f"    [{h.status}] freq={h.frequency} imp={h.importance_score:.2f}  {inv_preview}")
else:
    print("  No exploration targets yet.")
print()
