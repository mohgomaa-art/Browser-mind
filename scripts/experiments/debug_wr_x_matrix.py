import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from browsermind_core.experiments.harness import ReplayExperimentHarness

TIERS = {
    "Tier 1: Same Intent Same Domain": [
        ("DDG -> DDG", "exp_ddg_search_baseline", "duckduckgo", True),
        ("DDG -> Brave", "exp_ddg_search_baseline", "brave_search", False),
        ("MDN -> Python Docs", "exp_mdn_search_baseline", "python_org", False),
    ],
    "Tier 2: Same Intent Different Domain": [
        ("PyPI -> Python.org", "exp_pypi_search_baseline", "python_org", False),
        ("HF -> GitHub", "exp_huggingface_search_baseline", "github", False),
    ],
    "Tier 3: Stress Test": [
        ("DDG -> GitHub", "exp_ddg_search_baseline", "github", False),
    ]
}

async def run_matrix():
    print("[*] Running WR-X Validation Matrix\\n")
    harness = ReplayExperimentHarness(headless=True)
    
    matrix_results = {}
    
    for tier_name, tests in TIERS.items():
        print(f"============================================================")
        print(f" {tier_name}")
        print(f"============================================================")
        
        tier_passed = 0
        tier_total = len(tests)
        
        for test_name, template_name, target_site, intra_site in tests:
            print(f"\\n--- {test_name} ---")
            try:
                res = await harness.run_transfer(
                    template_name=template_name,
                    target_site_key=target_site,
                    intra_site=intra_site
                )
                
                status = "PASS" if res.replay_success else "FAIL"
                if res.replay_success:
                    tier_passed += 1
                
                print(f"  Result: {status} | steps={res.resolved_steps}/{res.total_steps}")
                
                # Print transfer depth
                for step in res.step_outcomes:
                    # 'resolved_by' is at the root, or inside 'target_integrity' -> 'resolution_strategy'
                    strategy = step.get('resolution_strategy') or step.get('resolved_by')
                    if not strategy:
                        ti = step.get('target_integrity', {})
                        strategy = ti.get('resolution_strategy')
                    
                    outcome = step['outcome']
                    disp = strategy if strategy else "None"
                    if outcome == "SKIPPED":
                        disp = "skipped"
                    print(f"    Step {step['seq']} [{step['action_type']}]: {outcome} (by {disp})")
                
            except Exception as e:
                print(f"  Result: ERROR | {str(e)}")
        
        matrix_results[tier_name] = f"{tier_passed}/{tier_total} PASS"
        print("\\n")
        
    print("============================================================")
    print(" MATRIX SUMMARY")
    print("============================================================")
    for tier_name, result in matrix_results.items():
        print(f"{tier_name}:\\n{result}\\n")

if __name__ == "__main__":
    asyncio.run(run_matrix())
