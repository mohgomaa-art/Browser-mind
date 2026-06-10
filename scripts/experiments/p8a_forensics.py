import os
import sys
import json
import asyncio
import traceback
import urllib.request
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.experiments.p8a_test_server import start_server_in_background, PORT
from browsermind_core.agent.inference import FlowInferenceEngine
from browsermind_core.agent.asset_graph import AssetGraphResolver
from browsermind_core.agent.environment_binder import EnvironmentBinder
from browsermind_core.agent.capability_discovery import CapabilityDiscoveryEngine
from browsermind_core.agent.backward_state_planner import BackwardStatePlanner
from browsermind_core.execution.outcome_verifier import OutcomeVerifier
from browsermind_core.execution.execution_coordinator import ExecutionCoordinator
from browsermind_core.execution.generic_executor import GenericCapabilityExecutor

async def run_forensics(task_id: str, goal: str, target_state: str, fallback_state: str = None, reset_params: str = ""):
    print(f"\n================================================================================")
    print(f" FORENSICS: {task_id}")
    print(f" GOAL: {goal}")
    print(f"================================================================================\n")
    
    urllib.request.urlopen(f"http://127.0.0.1:{PORT}/reset-server-state{reset_params}").read()

    ledger = {
        "task": task_id,
        "goal": goal,
        "candidate_paths": [],
        "selected_path": None,
        "fallback_path": None,
        "execution_trace": [],
        "exception": None,
        "failure_stage": None,
        "verifier_result": None
    }

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        inference_engine = FlowInferenceEngine()
        resolver = AssetGraphResolver()
        binder = EnvironmentBinder()
        cap_engine = CapabilityDiscoveryEngine()
        planner = BackwardStatePlanner()
        verifier = OutcomeVerifier()
        coordinator = ExecutionCoordinator(verifier)
        executor = GenericCapabilityExecutor(page, f"http://127.0.0.1:{PORT}")
        
        try:
            ledger["failure_stage"] = "binding"
            flows = inference_engine.infer_flow_graph(goal)
            candidates = inference_engine.infer_requirement_candidates(goal, flows)
            graph = resolver.build_graph(goal, flows, candidates)
            bound_graph = binder.bind_graph(graph, goal)
            cap_graph = cap_engine.bind_capabilities(bound_graph)

            ledger["failure_stage"] = "planning"
            res = planner.check_reachability(target_state, cap_graph)
            
            all_paths = []
            if res["reachable"]:
                all_paths.extend(res["candidate_paths"])
            
            if fallback_state:
                fallback_res = planner.check_reachability(fallback_state, cap_graph)
                if fallback_res["reachable"]:
                    all_paths.extend(fallback_res["candidate_paths"])

            ledger["candidate_paths"] = all_paths
            if all_paths:
                ledger["selected_path"] = all_paths[0]
                if len(all_paths) > 1:
                    ledger["fallback_path"] = all_paths[1:]

            ledger["failure_stage"] = "execution"
            
            # Simplified mock context
            context = {
                "username": "standard_user",
                "password": "secret_sauce",
                "address": "123 AI Lane",
                "card": "1111-2222-3333-4444"
            }

            if task_id == "T1_2FA":
                exec_ctx = {
                    "validation_contract": {"required_keys": ["otp"], "constraints": {"expired": False}},
                    "context": context
                }
            elif task_id == "T2_Recovery":
                exec_ctx = {"validation_contract": {"required_keys": ["reset_link"]}, "context": context}
            elif task_id == "T3_MultiEnv":
                exec_ctx = {"validation_contract": {"required_keys": ["otp"]}, "context": context}
            elif task_id == "T7_Profile":
                exec_ctx = {"validation_contract": {}, "context": context}
                # T7 doesn't use fallback coordinator in the standard runner, but we'll trace it
                
            if task_id in ["T1_2FA", "T2_Recovery", "T3_MultiEnv"]:
                coordinator_res = await coordinator.execute_with_fallback(all_paths, executor, exec_ctx)
                ledger["execution_trace"] = coordinator_res.get("log", [])
                ledger["verifier_result"] = "VALID" if coordinator_res["success"] else "INVALID"
            else:
                # T7 directly executed capabilities in the challenge script
                await executor.execute_capability("update_profile_billing", {}, context)
                ledger["execution_trace"] = [{"action": "update_profile_billing", "status": "completed"}]
                ledger["verifier_result"] = "UNKNOWN"

            ledger["failure_stage"] = None

        except Exception as e:
            ledger["exception"] = traceback.format_exc()

        await page.close()
        await browser.close()

    print(json.dumps(ledger, indent=2))
    return ledger

async def main():
    server = start_server_in_background()
    await asyncio.sleep(1.0)
    
    tasks = [
        ("T1_2FA", "Log in with 2FA using Vault credentials and OTP", "vault.otp_generated", "email.opened", "?fail_vault=1"),
        ("T2_Recovery", "Reset forgotten password and log in with new password", "email.opened", None, ""),
        ("T3_MultiEnv", "Retrieve code from Vault and verify it in the Email Portal", "vault.otp_generated", None, ""),
        ("T7_Profile", "Update the billing address in user profile", "profile.updated", None, ""),
    ]

    for t in tasks:
        await run_forensics(t[0], t[1], t[2], t[3], t[4])
        
    server.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
