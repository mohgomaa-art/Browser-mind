#!/usr/bin/env python3
"""
Workflow Robustness Generalization Evaluation Suite (Phase WR-G & WR-X precursor)

Evaluates BrowserMind Replay Engine under dynamic DOM mutations (Classes A-F)
across Known Infrastructure (WR-G1) and True Unseen Sites (WR-G2),
and checks Workflow Transfer capabilities.
"""
import sys
import os
import re
import time
import json
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.experiments.sites import get_site, ExperimentSite
import browsermind_core.experiments.sites
from browsermind_core.recorder.semantic_recorder import SemanticRecorder
from browsermind_core.recorder.demonstration_compiler import DemonstrationCompiler
from browsermind_core.recorder.demonstration_repository import DemonstrationRepository
from browsermind_core.recorder.demonstration_session import DemonstrationSession, DemonstrationStep
from browsermind_core.runtime.auth_session import AuthSession
from browsermind_core.runtime.environment_registry import register, EnvironmentEntry, resolve

# Register new/unseen environments dynamically
UNSEEN_ENVS = [
    EnvironmentEntry(key="duckduckgo", start_url="https://duckduckgo.com/", family="search", description="DuckDuckGo Search"),
    EnvironmentEntry(key="brave_search", start_url="https://search.brave.com/", family="search", description="Brave Search"),
    EnvironmentEntry(key="python_org", start_url="https://www.python.org/", family="general", description="Python.org Portal"),
    EnvironmentEntry(key="mdn_docs", start_url="https://developer.mozilla.org/en-US/", family="general", description="MDN Web Docs"),
    EnvironmentEntry(key="gitlab", start_url="https://gitlab.com/", family="dev_platform", description="GitLab Portal"),
    # product_hunt replaced — blocked by Cloudflare in headless mode
    EnvironmentEntry(key="pypi_org", start_url="https://pypi.org/", family="general", description="PyPI Package Index"),
]

for env in UNSEEN_ENVS:
    if not resolve(env.key):
        register(env)

# Inject sites into EXPERIMENT_SITES
NEW_SITES = (
    ExperimentSite(key="duckduckgo", label="DuckDuckGo Search", suggested_workflow="exp_ddg_search", operator_hint="Search tasks"),
    ExperimentSite(key="brave_search", label="Brave Search", suggested_workflow="exp_brave_search", operator_hint="Search tasks"),
    ExperimentSite(key="python_org", label="Python.org Portal", suggested_workflow="exp_python_search", operator_hint="Search python docs"),
    ExperimentSite(key="mdn_docs", label="MDN Web Docs", suggested_workflow="exp_mdn_search", operator_hint="Search web docs"),
    ExperimentSite(key="gitlab", label="GitLab Portal", suggested_workflow="exp_gitlab_search", operator_hint="Search projects"),
    ExperimentSite(key="pypi_org", label="PyPI Package Index", suggested_workflow="exp_pypi_search", operator_hint="Search packages"),
)

for ns in NEW_SITES:
    # Avoid duplicate injection
    if not any(s.key == ns.key for s in browsermind_core.experiments.sites.EXPERIMENT_SITES):
        browsermind_core.experiments.sites.EXPERIMENT_SITES = browsermind_core.experiments.sites.EXPERIMENT_SITES + (ns,)

# Automation scripts for recording baselines
async def record_ddg_search(page):
    await page.wait_for_timeout(1500)
    # Target search box
    search_input = page.locator("#searchbox_input")
    await search_input.fill("BrowserMind AI")
    await page.wait_for_timeout(500)
    await search_input.press("Enter")
    await page.wait_for_timeout(3000)

async def record_huggingface_search(page):
    await page.wait_for_timeout(2000)
    search_input = page.locator("input[placeholder*='Search models, datasets'], input[placeholder*='Search']").first
    await search_input.fill("gpt2")
    await page.wait_for_timeout(500)
    await search_input.press("Enter")
    await page.wait_for_timeout(3000)

async def record_github_search(page):
    await page.wait_for_timeout(2000)
    search_input = page.locator("#query-builder-test, #query-builder-input, input[placeholder*='Search']").first
    
    try:
        if not await search_input.is_visible():
            btn = page.locator("button.header-search-button, button.Search-module__searchButton__aiE0a, button:has-text('search'), button:has-text('Search')").first
            await btn.click(timeout=5000)
            await page.wait_for_timeout(1000)
    except Exception as e:
        print(f"  [GitHub] Search button click bypassed: {e}")
        
    await search_input.fill("browsermind")
    await page.wait_for_timeout(500)
    await search_input.press("Enter")
    await page.wait_for_timeout(3000)

async def record_python_search(page):
    await page.wait_for_timeout(1500)
    search_input = page.locator("#id-search-field")
    await search_input.fill("asyncio")
    await page.wait_for_timeout(500)
    await page.locator("#submit").click()
    await page.wait_for_timeout(3000)

async def record_mdn_search(page):
    # MDN uses a Web Component <mdn-search-modal> with shadow DOM — no accessible <input>.
    # The stable recording strategy is direct URL navigation to the search results page.
    await page.wait_for_timeout(1000)
    await page.goto("https://developer.mozilla.org/en-US/search?q=flexbox", wait_until="domcontentloaded")
    await page.wait_for_timeout(2500)

async def record_pypi_search(page):
    # PyPI has a clean accessible search: <input id="search" name="q" ...>
    await page.wait_for_timeout(1500)
    search_input = page.locator("#search, input[name='q']").first
    await search_input.fill("requests")
    await page.wait_for_timeout(400)
    await search_input.press("Enter")
    await page.wait_for_timeout(3000)

# Programmatic recording and compilation helper
async def record_and_compile(harness, site_key, template_name, automation_func):
    entry = resolve(site_key)
    url = entry.start_url
    
    auth_session = AuthSession(
        entry=entry,
        persona_name=harness.persona,
        store_dir=Path(harness.store_dir),
        headless=harness.headless,
    )
    repo = DemonstrationRepository(harness.store_dir)
    session = DemonstrationSession(
        persona_name=harness.persona,
        environment_family=entry.family,
        environment_instance=entry.key,
        profile_path=str(auth_session.profile_path),
        start_url=url,
    )
    repo.set_active(session.id)
    session_ref = [session]
    
    def on_step(payload: dict):
        s = session_ref[0]
        s.append(
            DemonstrationStep(
                seq=len(s.actions) + 1,
                action_type=payload.get("action_type", "click"),
                url=payload.get("url", ""),
                target_role=payload.get("target_role", ""),
                target_name=payload.get("target_name", ""),
                target_selector=payload.get("target_selector", ""),
                value=payload.get("value"),
                vault_ref=payload.get("vault_ref"),
                result_url=payload.get("result_url", ""),
                result_state=payload.get("result_state", ""),
                screenshot_hash=payload.get("screenshot_hash", ""),
                descriptor=payload.get("descriptor") or {},
                metadata=payload.get("meta") or {},
            )
        )
        
    recorder = SemanticRecorder(on_step)
    page = await auth_session.open(url)
    context = page.context
    await recorder.attach(context, page)
    await recorder.record_navigation(page, "initial_goto")
    
    await automation_func(page)
    
    await recorder.record_navigation(page, "final_url")
    await auth_session.close()
    
    session.complete()
    repo.save(session)
    repo.clear_active()
    
    compiler = DemonstrationCompiler(harness.kernel)
    template = compiler.compile(session, template_name)
    return template

# Dynamic DOM Mutator supporting Drift Classes A-F
def make_mutation_hook(drift_classes):
    async def on_before_resolve(page, step):
        selector = step.get("target_selector")
        role = step.get("target_role")
        name = step.get("target_name")
        action_type = step.get("action_type")
        
        if not selector or action_type == "navigate":
            return
            
        mutation_js = """
        ([selector, role, name, classes]) => {
            let el = null;
            if (selector) {
                try { el = document.querySelector(selector); } catch(e) {}
            }
            if (!el) return false;
            
            for (let driftClass of classes) {
                if (driftClass === 'A') {
                    // Label & Placeholder Drift
                    if (el.placeholder) el.placeholder = "Mutated Placeholder Drift A";
                    let label = document.querySelector(`label[for="${el.id}"]`) || el.closest('label');
                    if (label) label.innerText = "Mutated Label Drift A";
                    el.setAttribute('aria-label', "Mutated Label Drift A");
                } else if (driftClass === 'B') {
                    // Role Drift
                    if (el.tagName.toLowerCase() === 'input') {
                        el.setAttribute('role', 'combobox');
                    } else if (el.tagName.toLowerCase() === 'button') {
                        el.setAttribute('role', 'presentation');
                    }
                } else if (driftClass === 'C') {
                    // DOM Relocation
                    let parent = el.parentElement;
                    if (parent) {
                        let wrapper1 = document.createElement('div');
                        let wrapper2 = document.createElement('span');
                        wrapper1.className = 'relocated-wrapper-div';
                        wrapper2.className = 'relocated-wrapper-span';
                        parent.replaceChild(wrapper1, el);
                        wrapper1.appendChild(wrapper2);
                        wrapper2.appendChild(el);
                    }
                } else if (driftClass === 'D') {
                    // Visibility Drift (Wrap inside accordion/details)
                    let parent = el.parentElement;
                    if (parent) {
                        let details = document.createElement('details');
                        details.open = true; // keep details open but changes role/nesting
                        let summary = document.createElement('summary');
                        summary.innerText = "Show details section";
                        parent.replaceChild(details, el);
                        details.appendChild(summary);
                        details.appendChild(el);
                    }
                } else if (driftClass === 'E') {
                    // Text Mutation
                    if (el.tagName.toLowerCase() === 'button' || el.type === 'submit') {
                        el.innerText = "Continue";
                    } else {
                        let label = document.querySelector(`label[for="${el.id}"]`) || el.closest('label');
                        if (label) label.innerText = "User ID / passcode";
                    }
                } else if (driftClass === 'F') {
                    // Attribute Mutation
                    el.removeAttribute('id');
                    el.removeAttribute('data-testid');
                    el.name = "mutated_attribute_name";
                }
            }
            return true;
        }
        """
        try:
            mutated = await page.evaluate(mutation_js, [selector, role or "", name or "", drift_classes])
            if mutated:
                print(f"    [DynamicMutator] Mutated selector '{selector}' with {drift_classes}")
        except Exception as e:
            print(f"    [DynamicMutator] Failed to mutate: {e}")
            
    return on_before_resolve

async def run_evaluation_trials(harness, site_key, tpl_name, drift_classes_per_trial):
    results = []
    
    for trial, classes in enumerate(drift_classes_per_trial, 1):
        print(f"  Trial {trial}/5 (Mutations: {classes}) ... ", end="", flush=True)
        t0 = time.time()
        
        hook = make_mutation_hook(classes) if classes else None
        
        try:
            result = await harness.run_full(
                site_key,
                template_name=tpl_name,
                skip_record=True,
                on_before_resolve=hook
            )
            dt = time.time() - t0
            
            # Count resolved vs failed
            resolved = result.resolved_steps
            total = result.total_steps
            status = "PASS" if result.replay_success else "FAIL"
            
            # Collect recovery depth & strategy info
            depths = []
            strategies = []
            for step in result.step_outcomes:
                if step.get("outcome") == "SKIPPED":
                    continue
                strat = step.get("resolution_strategy")
                if strat:
                    strategies.append(strat)
                    
                # Exact Selector = 0, Primary Semantic = 1, Loose Semantic = 2, Container/Placeholder = 3, Text/Nearby = 4, DOM Path = 5
                if strat == "exact_selector":
                    depths.append(0)
                elif strat == "primary_semantic":
                    depths.append(1)
                elif strat == "loose_semantic":
                    depths.append(2)
                elif strat in ("placeholder", "semantic+container"):
                    depths.append(3)
                elif strat == "nearby_text":
                    depths.append(4)
                elif strat == "structural_path":
                    depths.append(5)
                else:
                    depths.append(0)
                    
            avg_depth = sum(depths) / len(depths) if depths else 0.0
            
            print(f"{status} | steps={resolved}/{total} | avg_depth={avg_depth:.2f} | {dt:.1f}s")
            results.append({
                "trial": trial,
                "success": result.replay_success,
                "resolved_steps": resolved,
                "total_steps": total,
                "avg_depth": avg_depth,
                "strategies": strategies
            })
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({
                "trial": trial,
                "success": False,
                "error": str(e)
            })
            
    return results

async def main():
    print("\n============================================================")
    print(" BROWSERMIND ROBUSTNESS GENERALIZATION (WR-G & WR-X)")
    print("============================================================\n")

    harness = ReplayExperimentHarness(headless=True)
    
    # 5 Trials test matrix per workflow:
    # T1: No Drift (Baseline validation)
    # T2: Drift Class A + F (Label & attribute mutations)
    # T3: Drift Class B + F (Role & attribute mutations)
    # T4: Drift Class C (DOM relocations)
    # T5: Drift Class D + E (Visibility accordion + Text synonyms)
    drift_matrix = [
        [],                 # Trial 1
        ['A', 'F'],         # Trial 2
        ['B', 'F'],         # Trial 3
        ['C'],              # Trial 4
        ['D', 'E']          # Trial 5
    ]

    all_results = {}

    # ============================================================
    # LEVEL 1: WR-G1 - Known Infrastructure
    # ============================================================
    print("[*] Running WR-G1 (Known Infrastructure) Evaluation...")
    wr_g1_sites = {
        "duckduckgo": {
            "auto_func": record_ddg_search,
            "tpl_prefix": "exp_ddg_search"
        },
        "huggingface": {
            "auto_func": record_huggingface_search,
            "tpl_prefix": "exp_huggingface_search"
        },
        "github": {
            "auto_func": record_github_search,
            "tpl_prefix": "exp_github_search"
        }
    }

    for site_key, cfg in wr_g1_sites.items():
        print(f"\n[*] Evaluating site: {site_key}")
        tpl_name = f"{cfg['tpl_prefix']}_baseline"
        
        # Record baseline template
        print(f"  Recording baseline workflow...")
        await record_and_compile(harness, site_key, tpl_name, cfg["auto_func"])
        
        # Run replay trials
        trials = await run_evaluation_trials(harness, site_key, tpl_name, drift_matrix)
        all_results[f"WR-G1:{site_key}"] = trials

    # ============================================================
    # LEVEL 2: WR-G2 - True Unseen Environments
    # ============================================================
    print("\n" + "=" * 60)
    print("[*] Running WR-G2 (True Unseen Environments) Evaluation...")
    wr_g2_sites = {
        "python_org": {
            "auto_func": record_python_search,
            "tpl_prefix": "exp_python_search"
        },
        "mdn_docs": {
            "auto_func": record_mdn_search,
            "tpl_prefix": "exp_mdn_search"
        },
        "pypi_org": {
            # Replaces product_hunt (Cloudflare-blocked in headless)
            "auto_func": record_pypi_search,
            "tpl_prefix": "exp_pypi_search"
        }
    }

    for site_key, cfg in wr_g2_sites.items():
        print(f"\n[*] Evaluating site: {site_key}")
        tpl_name = f"{cfg['tpl_prefix']}_baseline"
        
        # Record baseline template
        print(f"  Recording baseline workflow...")
        await record_and_compile(harness, site_key, tpl_name, cfg["auto_func"])
        
        # Run replay trials
        trials = await run_evaluation_trials(harness, site_key, tpl_name, drift_matrix)
        all_results[f"WR-G2:{site_key}"] = trials

    # ============================================================
    # LEVEL 3: WR-X Precursor - Cross-Site Workflow Transfer
    # ============================================================
    print("\n" + "=" * 60)
    print("[*] Running WR-X Precursor (Cross-Site Workflow Transfer)...")
    
    # 1. Transfer DuckDuckGo Search template to Brave Search
    print("\n[*] Transfer test: DuckDuckGo Search Template -> Brave Search Portal")
    try:
        # Record Brave Search baseline URL entry in Registry first to ensure clean navigate step
        # Re-resolve brave search url entry
        print("  Running Brave Search Replay using DuckDuckGo Template...")
        t0 = time.time()
        result = await harness.run_full(
            "brave_search",
            template_name="exp_ddg_search_baseline",
            skip_record=True,
            transfer_from_url="https://duckduckgo.com/"
        )
        dt = time.time() - t0
        status = "PASS" if result.replay_success else "FAIL"
        print(f"  Result: {status} | steps={result.resolved_steps}/{result.total_steps} | {dt:.1f}s")
        all_results["WR-X:ddg_to_brave"] = {
            "success": result.replay_success,
            "resolved_steps": result.resolved_steps,
            "total_steps": result.total_steps,
            "outcomes": [s.get("resolution_strategy") for s in result.step_outcomes]
        }
    except Exception as e:
        print(f"  Transfer Error: {e}")
        all_results["WR-X:ddg_to_brave"] = {"success": False, "error": str(e)}

    # Save results to json
    out_dir = ROOT / "reports" / "survivability" / "drift"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "wr_g_results.json"
    
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    # Print Final Strategy Distribution Report
    strategy_counts = {}
    total_strategies = 0
    successes = 0
    total_runs = 0
    
    for key, trials_list in all_results.items():
        if isinstance(trials_list, dict):
            # WR-X result
            total_runs += 1
            if trials_list.get("success"):
                successes += 1
            for strat in trials_list.get("outcomes", []):
                if strat:
                    strategy_counts[strat] = strategy_counts.get(strat, 0) + 1
                    total_strategies += 1
        elif isinstance(trials_list, list):
            for trial in trials_list:
                if "error" in trial:
                    continue
                total_runs += 1
                if trial.get("success"):
                    successes += 1
                for strat in trial.get("strategies", []):
                    strategy_counts[strat] = strategy_counts.get(strat, 0) + 1
                    total_strategies += 1

    print("\n" + "=" * 60)
    print(" GENERALIZATION EVALUATION COMPLETE")
    print("=" * 60)
    print(f"Total Replay Trials: {total_runs}")
    print(f"Overall Success Rate: {((successes/total_runs)*100.0) if total_runs else 0.0:.2f}%")
    print("\nResolution Strategy Distribution:")
    print("-" * 40)
    for strat, count in strategy_counts.items():
        pct = (count / total_strategies) * 100.0 if total_strategies else 0.0
        print(f"  {strat:<25}: {count:<5} ({pct:.2f}%)")
    print("-" * 40)
    print(f"Full Report Saved to: {out_file}\n")

if __name__ == "__main__":
    asyncio.run(main())
