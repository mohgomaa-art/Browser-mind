import asyncio
import json
import sys
import os

# Fix encoding for Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from playwright.async_api import async_playwright
from training.graph_builder import build_graph_from_page
from training.compiler import (
    StateFamilyBuilder,
    OpportunityGraphGenerator,
    DifficultyEstimator,
    CoverageGates
)
from training.compiler.gold_compiler import GoldCompiler

async def main():
    family_builder = StateFamilyBuilder()
    coverage_gates = CoverageGates()
    opportunity_gen = OpportunityGraphGenerator(coverage_gates)
    diff_estimator = DifficultyEstimator()
    
    report1 = {
        "domains": 0,
        "state_families": set(),
        "opportunities": {
            "interaction": 0,
            "extraction": 0
        },
        "task_families": set(),
        "difficulty_distribution": {"easy": 0, "medium": 0, "hard": 0},
        "rejected_by_coverage": 0,
        "rejected_by_validation": 0
    }
    
    report2_families = set()
    scarcity_opportunities = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        
        urls_test1 = [
            "https://github.com",
            "https://www.python.org",
            "https://www.wikipedia.org"
        ]
        
        urls_test2 = [
            "https://github.com/login",
            "https://www.reddit.com/login",
            "https://www.linkedin.com/login",
            "https://www.facebook.com/login"
        ]
        
        all_urls = urls_test1 + urls_test2
        
        base_dir = os.path.join(os.path.dirname(__file__), '..', 'training')
        compiler = GoldCompiler(base_dir=base_dir)
        total_interaction_saved = 0
        total_extraction_saved = 0
        
        for url in all_urls:
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                
                ax_graph = await build_graph_from_page(page)
                family_data = family_builder.identify_family(ax_graph, url=url)
                
                if url in urls_test2:
                    report2_families.add(family_data["state_family"])
                    
                if url in urls_test1:
                    report1["domains"] += 1
                
                report1["state_families"].add(family_data["state_family"])
                
                # Test the full compilation pipeline
                i_saved, e_saved = compiler.process_state(url, ax_graph)
                total_interaction_saved += i_saved
                total_extraction_saved += e_saved
                
                opps = opportunity_gen.generate(ax_graph, family_data)
                
                for opp in opps["interaction_opportunities"]:
                    diff = diff_estimator.estimate(ax_graph, opp)
                    report1["opportunities"]["interaction"] += 1
                    report1["task_families"].add(opp["task_family"])
                    report1["difficulty_distribution"][diff["difficulty"]] += 1
                    
                    coverage_gates.total_samples += 1
                    coverage_gates.state_family_counts[family_data["state_family"]] += 1
                    coverage_gates.task_family_counts[opp["task_family"]] += 1
                    
                    opp["combined_score"] = opp["priority"] + opp["scarcity_score"]
                    scarcity_opportunities.append(opp)
                    
                for opp in opps["extraction_opportunities"]:
                    diff = diff_estimator.estimate(ax_graph, opp)
                    report1["opportunities"]["extraction"] += 1
                    report1["task_families"].add(opp["task_family"])
                    report1["difficulty_distribution"][diff["difficulty"]] += 1
                    
                    coverage_gates.total_samples += 1
                    coverage_gates.state_family_counts[family_data["state_family"]] += 1
                    coverage_gates.task_family_counts[opp["task_family"]] += 1
                    
                    opp["combined_score"] = opp["priority"] + opp["scarcity_score"]
                    scarcity_opportunities.append(opp)
                    
                await page.close()
            except Exception as e:
                print(f"Error on {url}: {e}")
        
        await browser.close()
        
    report1["state_families"] = len(report1["state_families"])
    report1["task_families"] = len(report1["task_families"])
    
    print("========== REPORT 1: OPPORTUNITY DISCOVERY ==========")
    print(json.dumps(report1, indent=2))
    print(f"\n[GOLD COMPILER RESULTS]")
    print(f"Interaction Samples Saved: {total_interaction_saved}")
    print(f"Extraction Samples Saved:  {total_extraction_saved}")
    
    print("\n========== REPORT 2: STATE FAMILY EXPLOSION ==========")
    print(f"Login pages processed. Resulting Families: {list(report2_families)}")
    if len(report2_families) == 1:
        print("-> SUCCESS: Consistent Semantic Family (1 Family)")
    else:
        print(f"-> FAILURE: Fragmentation ({len(report2_families)} Families)")
        
    print("\n========== REPORT 3 & 4: SCARCITY AND DIFFICULTY ==========")
    scarcity_opportunities.sort(key=lambda x: x["combined_score"], reverse=True)
    
    top_50 = scarcity_opportunities[:50]
    for i, opp in enumerate(top_50):
        name = opp['name'].replace('\n', ' ').replace('\r', '')
        print(f"{i+1}. [P:{opp['priority']:.2f} S:{opp['scarcity_score']:.2f} C:{opp['combined_score']:.2f}] {opp['task_family']} (Family: {opp['state_family']})")
        
if __name__ == "__main__":
    asyncio.run(main())
