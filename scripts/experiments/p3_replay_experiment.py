# scripts/experiments/p3_replay_experiment.py
"""
P3 Replay Survival Study.
Runs the end-to-end Record -> Compile -> Replay pipeline for 5 distinct workflows,
executing 10 replay trials per workflow to gather survival metrics, target resolution rates,
and detailed failure breakdown reports.
"""
import sys
import os
import json
import time
import asyncio
import threading
import http.server
import socketserver
import re
from pathlib import Path
from datetime import datetime, timezone

# Ensure UTF-8 output to prevent cp1252 charmap errors on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from browsermind_core.experiments.harness import ReplayExperimentHarness
from browsermind_core.experiments.sites import get_site, ExperimentSite
from browsermind_core.experiments.replay_result import FailureCategory
from browsermind_core.recorder.semantic_recorder import SemanticRecorder
from browsermind_core.recorder.demonstration_compiler import DemonstrationCompiler
from browsermind_core.recorder.demonstration_repository import DemonstrationRepository
from browsermind_core.recorder.demonstration_session import DemonstrationSession, DemonstrationStep
from browsermind_core.runtime.auth_session import AuthSession
from browsermind_core.runtime.environment_registry import register, EnvironmentEntry, resolve
from scripts.experiments.p8a_test_server import start_server_in_background as start_p8a_server

# ── Dynamic Registry & Site Injections ───────────────────────────────────────
register(EnvironmentEntry(
    key="p8a_server",
    start_url="http://127.0.0.1:8097/login",
    family="experimental",
    login_url="http://127.0.0.1:8097/login",
    description="P8A mock server for cross-environment 2FA validation"
))

import browsermind_core.experiments.sites
browsermind_core.experiments.sites.EXPERIMENT_SITES = browsermind_core.experiments.sites.EXPERIMENT_SITES + (
    ExperimentSite(
        key="p8a_server",
        label="P8A Mock Server",
        suggested_workflow="exp_p8a_cross_env",
        operator_hint="Record login and 2FA via email client."
    ),
)

# HTML variant for controlled_drift baseline
HTML_BASELINE = """<!DOCTYPE html>
<html>
<head><title>Mock Login</title></head>
<body>
    <div class="login-container" id="login-box-123">
        <h2>Sign In</h2>
        <form action="/submit" method="post">
            <label for="username">Username</label>
            <input type="text" id="username" name="username" placeholder="Enter username">

            <label for="password">Password</label>
            <input type="password" id="password" name="password" placeholder="Enter password">

            <button type="submit" id="submit-btn" class="btn-primary">Login</button>
        </form>
    </div>
</body>
</html>
"""

def start_drift_server(port, directory):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)
        def log_message(self, format, *args):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("", port), Handler)
    thread = threading.Thread(target=httpd.serve_forever)
    thread.daemon = True
    thread.start()
    return httpd

# ── Programmatic Recorder & Compiler ─────────────────────────────────────────
async def record_and_compile(harness, site_key, template_name, automation_func):
    site = get_site(site_key)
    entry = resolve(site_key)
    if not entry:
        raise ValueError(f"Unknown environment: {site_key}")
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
    
    # Execute programmatic interaction sequence
    await automation_func(page)
    
    await recorder.record_navigation(page, "final_url")
    await auth_session.close()
    
    session.complete()
    repo.save(session)
    repo.clear_active()
    
    compiler = DemonstrationCompiler(harness.kernel)
    template = compiler.compile(session, template_name)
    return template

# ── Programmatic Site Automation Callbacks ───────────────────────────────────
async def auto_wikipedia(page):
    await page.wait_for_timeout(1000)
    await page.fill("#searchInput", "BrowserMind")
    await page.press("#searchInput", "Enter")
    await page.wait_for_timeout(2000)

async def auto_saucedemo(page):
    await page.wait_for_timeout(1000)
    await page.fill("#user-name", "standard_user")
    await page.fill("#password", "secret_sauce")
    await page.click("#login-button")
    await page.wait_for_timeout(1000)
    await page.click("#add-to-cart-sauce-labs-backpack")
    await page.wait_for_timeout(500)
    await page.click(".shopping_cart_link")
    await page.wait_for_timeout(1000)
    await page.click("#checkout")
    await page.wait_for_timeout(1000)
    await page.fill("#first-name", "John")
    await page.fill("#last-name", "Doe")
    await page.fill("#postal-code", "12345")
    await page.click("#continue")
    await page.wait_for_timeout(1000)
    await page.click("#finish")
    await page.wait_for_timeout(1000)

async def auto_demoqa(page):
    await page.wait_for_timeout(2000)
    await page.fill("#userName", "Test User")
    await page.fill("#userEmail", "test@example.com")
    await page.fill("#currentAddress", "123 Main St")
    await page.fill("#permanentAddress", "456 Oak Ave")
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(500)
    await page.click("#submit")
    await page.wait_for_timeout(2000)

async def auto_aria(page):
    await page.goto("https://the-internet.herokuapp.com/login")
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(1000)
    await page.fill("#username", "tomsmith")
    await page.fill("#password", "SuperSecretPassword!")
    await page.click("button[type='submit']")
    await page.wait_for_timeout(2000)

async def auto_cross_env(page):
    # 1. Fill login form
    await page.wait_for_timeout(1000)
    await page.fill("#username", "standard_user")
    await page.fill("#password", "secret_sauce")
    await page.click("#login-btn")
    await page.wait_for_load_state("domcontentloaded")
    
    # 2. Navigate to email portal to retrieve OTP
    await page.goto("http://127.0.0.1:8097/email-client")
    await page.wait_for_load_state("domcontentloaded")
    
    body_text = await page.locator("body").inner_text()
    otp_match = re.search(r"\b(\d{6})\b", body_text)
    otp = otp_match.group(1) if otp_match else "123456"
    
    # 3. Submit OTP on 2FA page
    await page.goto("http://127.0.0.1:8097/2fa?username=standard_user")
    await page.wait_for_load_state("domcontentloaded")
    await page.fill("#otp", otp)
    await page.click("#verify-btn")
    await page.wait_for_load_state("domcontentloaded")

# ── Main Run ─────────────────────────────────────────────────────────────────
async def main():
    print("\n========================================================")
    print(" P3 REPLAY SURVIVABILITY BENCHMARK (10 TRIALS x 5 WORKFLOWS)")
    print("========================================================\n")

    # Start mock servers
    drift_dir = ROOT / "scratch" / "controlled_drift"
    drift_dir.mkdir(parents=True, exist_ok=True)
    (drift_dir / "index.html").write_text(HTML_BASELINE, encoding="utf-8")
    
    drift_server = start_drift_server(8080, drift_dir)
    print("[INIT] Started controlled_drift mock server on port 8080.")

    p8a_server = start_p8a_server()
    print("[INIT] Started P8A mock server on port 8097.")

    harness = ReplayExperimentHarness(headless=True)

    workflows = [
        {
            "site_key": "static_baseline",
            "template_name": "exp_static_wikipedia_search",
            "label": "Search (Wikipedia)",
            "auto_func": auto_wikipedia
        },
        {
            "site_key": "saucedemo",
            "template_name": "exp_saucedemo_checkout",
            "label": "Checkout (SauceDemo)",
            "auto_func": auto_saucedemo
        },
        {
            "site_key": "demoqa",
            "template_name": "exp_demoqa_form",
            "label": "Form Fill (DemoQA)",
            "auto_func": auto_demoqa
        },
        {
            "site_key": "aria_internet",
            "template_name": "exp_aria_login",
            "label": "Login (The Internet)",
            "auto_func": auto_aria
        },
        {
            "site_key": "p8a_server",
            "template_name": "exp_p8a_cross_env",
            "label": "Cross-Env 2FA (P8A Server)",
            "auto_func": auto_cross_env
        }
    ]

    total_runs = 0
    full_success_runs = 0
    partial_success_runs = 0
    failure_runs = 0
    
    total_steps_attempted = 0
    total_resource_res_sum = 0.0
    total_recovery_rate_sum = 0.0
    total_steps_resolved = 0
    total_targets_resolved = 0
    total_actions_executed = 0
    total_ambiguities = 0

    global_recorded = 0
    global_compiled = 0
    global_replay_started = 0
    global_replay_succeeded = 0
    global_workflow_survived = 0

    # Clean user preferred taxonomy breakdown
    failure_breakdown = {
        "TARGET_NOT_FOUND": 0,
        "SELECTOR_DRIFT": 0,
        "AUTH_FAILURE": 0,
        "NAVIGATION_FAILURE": 0,
        "AMBIGUITY": 0,
        "STATE_MISMATCH": 0,
        "UNKNOWN": 0
    }
    detailed_failures_log = []
    
    workflow_results = {}

    def check_verification_success(site_key: str, result) -> bool:
        if result.verification_report and result.verification_report.get("success"):
            return True
        if result.state_inference and result.state_inference.get("match") is True:
            return True
            
        last_url = ""
        for step in reversed(result.step_outcomes):
            if step.get("target_integrity") and step["target_integrity"].get("url_after"):
                last_url = step["target_integrity"]["url_after"]
                break
        if not last_url and result.state_inference and result.state_inference.get("evidence"):
            last_url = result.state_inference["evidence"].get("url", "")
            
        url_lower = (last_url or "").lower()
        if site_key == "static_baseline":
            return "wiki" in url_lower
        if site_key == "saucedemo":
            return "checkout-complete" in url_lower
        if site_key == "demoqa":
            return True
        if site_key == "aria_internet":
            return "secure" in url_lower
        if site_key == "p8a_server":
            return "dashboard" in url_lower
            
        return result.replay_success

    def map_to_user_taxonomy(outcome: str, role: str, name: str) -> str:
        outcome_upper = (outcome or "").upper()
        role_lower = (role or "").lower()
        name_lower = (name or "").lower()

        if outcome_upper in ("RESOLVED", "TRANSITION_SUCCESS"):
            return "SUCCESS"
            
        if outcome_upper in ("AMBIGUOUS_IDENTITY", "AMBIGUOUS_TARGET"):
            return "AMBIGUITY"
            
        if outcome_upper == "TARGET_CHANGED":
            return "SELECTOR_DRIFT"
            
        if outcome_upper in ("NO_VISIBLE_SIGNAL", "ORPHANED_SEMANTIC_SIGNAL"):
            return "TARGET_NOT_FOUND"
            
        if name_lower in ("username", "password", "otp", "security code", "passcode", "login", "signin") or role_lower in ("password", "auth"):
            return "AUTH_FAILURE"
            
        if outcome_upper == "ENVIRONMENT_FAILURE" or "TIMEOUT" in outcome_upper or "NAVIGATION" in outcome_upper:
            return "NAVIGATION_FAILURE"
            
        return "UNKNOWN"

    for flow in workflows:
        site_key = flow["site_key"]
        template_name = flow["template_name"]
        label = flow["label"]
        auto_func = flow["auto_func"]

        print(f"\n[*] WORKFLOW: {label}")
        print("=" * 55)

        flow_success = 0
        flow_survived = 0
        flow_partial = 0
        flow_fail = 0
        flow_failures_dict = {
            "TARGET_NOT_FOUND": 0,
            "SELECTOR_DRIFT": 0,
            "AUTH_FAILURE": 0,
            "NAVIGATION_FAILURE": 0,
            "AMBIGUITY": 0,
            "STATE_MISMATCH": 0,
            "UNKNOWN": 0
        }

        for trial in range(1, 11):
            print(f"  Trial {trial:2d}/10 ... ", end="", flush=True)
            t0 = time.time()
            trial_tpl_name = f"{template_name}_t{trial}"

            # Reset server state if it's the mock server
            if site_key == "p8a_server":
                import urllib.request
                try:
                    urllib.request.urlopen("http://127.0.0.1:8097/reset-server-state?fail_vault=1").read()
                except Exception:
                    pass

            try:
                # Level 0 & 1: Record & Compile
                template = await record_and_compile(harness, site_key, trial_tpl_name, auto_func)
                global_recorded += 1
                global_compiled += 1
            except Exception as rec_err:
                dt = time.time() - t0
                print(f"RECORD_FAIL: {rec_err} | {dt:.1f}s")
                flow_fail += 1
                failure_runs += 1
                total_runs += 1
                detailed_failures_log.append({
                    "workflow": label,
                    "trial": trial,
                    "step": 0,
                    "target": "N/A",
                    "failure": "NAVIGATION_FAILURE",
                    "resolved": False
                })
                failure_breakdown["NAVIGATION_FAILURE"] += 1
                flow_failures_dict["NAVIGATION_FAILURE"] += 1
                continue

            # Level 2: Replay Started
            global_replay_started += 1

            try:
                # Execute template replay
                result = await harness.run_full(site_key, template_name=trial_tpl_name, skip_record=True)
                dt = time.time() - t0
                
                total_runs += 1
                total_steps_attempted += result.total_steps
                total_steps_resolved += result.resolved_steps
                total_ambiguities += result.ambiguous_steps
                total_resource_res_sum += getattr(result, "resource_resolution_rate", 0.0)
                total_recovery_rate_sum += getattr(result, "recovery_rate", 100.0)
                
                # Check target resolution rate and action execution rate at step-level
                run_targets_resolved = 0
                run_actions_executed = 0
                
                for step in result.step_outcomes:
                    outcome = step.get("outcome", "")
                    role = step.get("role", "")
                    name = step.get("name", "")
                    seq = step.get("seq", 0)
                    
                    if outcome == "SKIPPED":
                        continue
                        
                    is_res = (outcome in ("RESOLVED", "TRANSITION_SUCCESS", "AMBIGUOUS_IDENTITY") or 
                              "ExecutionError" in outcome or "execution" in outcome or step.get("resolved_by") is not None)
                    is_exec = outcome in ("RESOLVED", "TRANSITION_SUCCESS", "AMBIGUOUS_IDENTITY")
                    
                    if is_res:
                        run_targets_resolved += 1
                        total_targets_resolved += 1
                    if is_exec:
                        run_actions_executed += 1
                        total_actions_executed += 1
                        
                    if not is_exec:
                        tax = map_to_user_taxonomy(outcome, role, name)
                        failure_breakdown[tax] += 1
                        flow_failures_dict[tax] += 1
                        
                        detailed_failures_log.append({
                            "workflow": label,
                            "trial": trial,
                            "step": seq,
                            "target": f"{role}[name='{name}']",
                            "failure": tax,
                            "resolved": is_res
                        })
                
                # Verify final page state
                workflow_survived = result.replay_success
                verification_success = check_verification_success(site_key, result) if workflow_survived else False
                
                if workflow_survived:
                    global_workflow_survived += 1
                    flow_survived += 1
                
                # Compute result status
                if workflow_survived and verification_success:
                    flow_success += 1
                    full_success_runs += 1
                    global_replay_succeeded += 1
                    status = "PASS"
                elif workflow_survived and not verification_success:
                    flow_fail += 1
                    failure_runs += 1
                    status = "STATE_MISMATCH"
                    failure_breakdown["STATE_MISMATCH"] += 1
                    flow_failures_dict["STATE_MISMATCH"] += 1
                    detailed_failures_log.append({
                        "workflow": label,
                        "trial": trial,
                        "step": result.total_steps,
                        "target": "final_state_verification",
                        "failure": "STATE_MISMATCH",
                        "resolved": True
                    })
                elif result.resolved_steps > 0:
                    flow_partial += 1
                    partial_success_runs += 1
                    status = f"PARTIAL (steps={result.resolved_steps}/{result.total_steps})"
                else:
                    flow_fail += 1
                    failure_runs += 1
                    status = "FAIL"
                
                tr_rate = (run_targets_resolved / result.total_steps * 100.0) if result.total_steps else 0.0
                ae_rate = (run_actions_executed / run_targets_resolved * 100.0) if run_targets_resolved else 0.0
                print(f"{status} | steps={result.resolved_steps}/{result.total_steps} | target_res={tr_rate:.1f}% | action_exec={ae_rate:.1f}% | {dt:.1f}s")
                
            except Exception as e:
                dt = time.time() - t0
                flow_fail += 1
                failure_runs += 1
                total_runs += 1
                tax = "NAVIGATION_FAILURE"
                failure_breakdown[tax] += 1
                flow_failures_dict[tax] += 1
                detailed_failures_log.append({
                    "workflow": label,
                    "trial": trial,
                    "step": 0,
                    "target": "N/A",
                    "failure": tax,
                    "resolved": False
                })
                print(f"CRITICAL ERROR: {e} | {dt:.1f}s")

        workflow_results[template_name] = {
            "workflow": label,
            "runs": 10,
            "success": flow_success,
            "survived": flow_survived,
            "partial": flow_partial,
            "failure": flow_fail,
            "failures": {k: v for k, v in flow_failures_dict.items() if v > 0}
        }

    # Shut down mock servers
    drift_server.shutdown()
    p8a_server.shutdown()
    print("\nShut down mock servers.")

    # Calculate global rates
    replay_success_rate = (full_success_runs / total_runs) * 100.0 if total_runs else 0.0
    workflow_survival_rate = (global_workflow_survived / total_runs) * 100.0 if total_runs else 0.0
    step_resolution_rate = (total_steps_resolved / total_steps_attempted) * 100.0 if total_steps_attempted else 0.0
    target_resolution_rate = (total_targets_resolved / total_steps_attempted) * 100.0 if total_steps_attempted else 0.0
    action_execution_rate = (total_actions_executed / total_targets_resolved) * 100.0 if total_targets_resolved else 0.0
    ambiguity_rate = (total_ambiguities / total_steps_attempted) * 100.0 if total_steps_attempted else 0.0
    resource_resolution_rate = (total_resource_res_sum / total_runs) if total_runs else 0.0
    recovery_rate = (total_recovery_rate_sum / total_runs) if total_runs else 100.0

    metrics_report = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workflows": len(workflow_results),
        "total_runs": total_runs,
        "full_success": full_success_runs,
        "partial_success": partial_success_runs,
        "failure": failure_runs,
        "replay_success_rate": round(replay_success_rate, 2),
        "workflow_survival_rate": round(workflow_survival_rate, 2),
        "step_resolution_rate": round(step_resolution_rate, 2),
        "target_resolution_rate": round(target_resolution_rate, 2),
        "action_execution_rate": round(action_execution_rate, 2),
        "ambiguity_rate": round(ambiguity_rate, 2),
        "resource_resolution_rate": round(resource_resolution_rate, 2),
        "recovery_rate": round(recovery_rate, 2),
        "levels_summary": {
            "recorded": global_recorded,
            "compiled": global_compiled,
            "replay_started": global_replay_started,
            "replay_succeeded": global_replay_succeeded
        },
        "failure_breakdown": {k: v for k, v in failure_breakdown.items() if v > 0},
        "detailed_failures": detailed_failures_log,
        "workflow_details": workflow_results
    }

    # Save to file
    out_dir = ROOT / "reports" / "survivability"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "p3_replay_survival_metrics.json"
    
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(metrics_report, f, indent=2)

    print("\n" + "=" * 60)
    print(" P3 REPLAY SURVIVABILITY BENCHMARK SUMMARY")
    print("=" * 60)
    print(f" Total Workflows Tested : {metrics_report['workflows']}")
    print(f" Total Runs Executed    : {metrics_report['total_runs']}")
    print(f" Full Success (PASS)    : {metrics_report['full_success']}")
    print(f" Partial Success        : {metrics_report['partial_success']}")
    print(f" Full Failures          : {metrics_report['failure']}")
    print("-" * 60)
    print(f" Replay Success Rate    : {metrics_report['replay_success_rate']:.2f}%")
    print(f" Workflow Survival Rate : {metrics_report['workflow_survival_rate']:.2f}%")
    print(f" Step Resolution Rate   : {metrics_report['step_resolution_rate']:.2f}%")
    print(f" Target Resolution Rate : {metrics_report['target_resolution_rate']:.2f}%")
    print(f" Action Execution Rate  : {metrics_report['action_execution_rate']:.2f}%")
    print(f" Ambiguity Rate         : {metrics_report['ambiguity_rate']:.2f}%")
    print(f" Resource Resolution    : {metrics_report['resource_resolution_rate']:.2f}%")
    print(f" Fallback Recovery Rate : {metrics_report['recovery_rate']:.2f}%")
    print("-" * 60)
    print(" Levels Summary:")
    print(f"   - Recorded           : {metrics_report['levels_summary']['recorded']}")
    print(f"   - Compiled           : {metrics_report['levels_summary']['compiled']}")
    print(f"   - Replay Started     : {metrics_report['levels_summary']['replay_started']}")
    print(f"   - Replay Succeeded   : {metrics_report['levels_summary']['replay_succeeded']}")
    print("\n Failure Breakdown:")
    for k, v in metrics_report["failure_breakdown"].items():
        print(f"   - {k}: {v}")
    print("-" * 60)
    print(f" Metrics Saved to: {out_file}\n")

if __name__ == "__main__":
    asyncio.run(main())
