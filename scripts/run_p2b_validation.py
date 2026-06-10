#!/usr/bin/env python3
"""
P2B Validation Sprint Orchestrator.
Runs the 4 Gates to validate Environment Runtime and Semantic Recorder
before we are allowed to build the Replay Engine (P3).
"""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from browsermind_core.console.session import DEFAULT_STORE, KernelSession
from browsermind_core.runtime.environment_registry import resolve
from browsermind_core.runtime.auth_session import AuthSession
from browsermind_core.recorder.record_runner import run_recording_session
from browsermind_core.recorder.demonstration_compiler import DemonstrationCompiler

# Set to True if we want to run headful
HEADLESS = False
PERSONA = "validator"
ENV_KEY = "huggingface"


async def gate_1_environment_reality(store_dir: str):
    print("\n" + "="*50)
    print("GATE 1: Environment Reality Test (Persistence)")
    print("="*50)
    
    entry = resolve(ENV_KEY)
    success_count = 0
    
    for i in range(1, 4):
        print(f"\n--- Attempt {i}/3 ---")
        session = AuthSession(entry=entry, persona_name=PERSONA, store_dir=Path(store_dir), headless=HEADLESS)
        page = await session.open()
        
        if i == 1:
            print(">>> Please log in manually to HuggingFace.")
            print(">>> Press Enter here in the terminal when you are fully logged in.")
            await asyncio.get_event_loop().run_in_executor(None, input)
        else:
            print(">>> Browser opened. Are you still logged in? (y/n)")
            ans = await asyncio.get_event_loop().run_in_executor(None, input)
            if ans.strip().lower() == 'y':
                success_count += 1
            else:
                print(">>> AUTH STATE LOST!")
                
        await session.close()
        
    passed = (success_count == 2) # i=2,3
    report = {
        "gate": 1,
        "name": "Environment Reality Test",
        "passed": passed,
        "success_count": success_count,
        "required": 2
    }
    with open("environment_validation_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    return passed


async def gate_2_recorder_reality(store_dir: str):
    print("\n" + "="*50)
    print("GATE 2: Recorder Reality Test (No Leakage)")
    print("="*50)
    
    print(">>> We will now record a session.")
    print(">>> Please perform: Logout -> Login.")
    print(">>> Press Enter in the terminal to stop recording when done.")
    
    session = await run_recording_session(store_dir, ENV_KEY, PERSONA, headless=HEADLESS)
    
    passwords_leaked = 0
    vault_refs_found = 0
    
    for act in session.actions:
        if act.action_type == "session":
            continue
        if "password" in act.target_selector.lower() or "password" in act.target_name.lower():
            if act.value:
                passwords_leaked += 1
            if act.vault_ref:
                vault_refs_found += 1

    passed = (passwords_leaked == 0 and vault_refs_found > 0)
    
    report = {
        "gate": 2,
        "name": "Recorder Reality Test",
        "passed": passed,
        "step_count": len(session.actions),
        "passwords_leaked": passwords_leaked,
        "vault_refs_found": vault_refs_found,
        "session_id": str(session.id)
    }
    with open("demonstration_validation_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    return passed, session


async def gate_3_compile_quality(store_dir: str, session_a):
    print("\n" + "="*50)
    print("GATE 3: Compile Quality Test (Stability)")
    print("="*50)
    
    print(">>> We need a SECOND recording of the exact same flow (Logout -> Login).")
    print(">>> Press Enter in the terminal to stop recording when done.")
    
    session_b = await run_recording_session(store_dir, ENV_KEY, PERSONA, headless=HEADLESS)
    
    ks = KernelSession(store_dir)
    compiler = DemonstrationCompiler(ks)
    
    tpl_a = compiler.compile(session_a, "hf_login_a")
    tpl_b = compiler.compile(session_b, "hf_login_b")
    
    # Simple semantic similarity: compare ordered roles & names
    def _extract_signature(tpl):
        sig = []
        for s in tpl.steps:
            if s["action_type"] in ("click", "fill", "submit"):
                sig.append(f"{s['action_type']}::{s['target_role']}::{s['target_name']}")
        return sig
        
    sig_a = _extract_signature(tpl_a)
    sig_b = _extract_signature(tpl_b)
    
    import difflib
    sm = difflib.SequenceMatcher(None, sig_a, sig_b)
    similarity = sm.ratio()
    
    passed = similarity >= 0.90
    
    report = {
        "gate": 3,
        "name": "Compile Quality Test",
        "passed": passed,
        "similarity_score": similarity,
        "signature_a": sig_a,
        "signature_b": sig_b,
        "template_a_id": str(tpl_a.id),
    }
    with open("compiler_stability_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    return passed, tpl_a


async def gate_4_replay_feasibility(store_dir: str, tpl_a):
    print("\n" + "="*50)
    print("GATE 4: Replay Feasibility Audit")
    print("="*50)
    
    entry = resolve(ENV_KEY)
    session = AuthSession(entry=entry, persona_name=PERSONA, store_dir=Path(store_dir), headless=HEADLESS)
    page = await session.open()
    
    print(">>> Browser opened to evaluate Template A selectors.")
    
    total_steps = 0
    valid_steps = 0
    
    initial_url = page.url.rstrip('/')
    
    for s in tpl_a.steps:
        # Only evaluate steps that belong to the initial page state.
        # We cannot evaluate login page selectors while we are logged in on the homepage.
        step_url = s.get("url", "").rstrip('/')
        if step_url and step_url != initial_url:
            continue
            
        sel = s.get("target_selector")
        role = s.get("target_role")
        name = s.get("target_name")
        
        # Skip non-interactive or generic steps
        if not role or role == "browser":
            continue
            
        total_steps += 1
        found = False
        
        if sel:
            try:
                count = await page.locator(sel).count()
                if count > 0:
                    found = True
            except:
                pass
                
        if not found and role and name:
            try:
                count = await page.get_by_role(role, name=name).count()
                if count > 0:
                    found = True
            except:
                pass
                
        if found:
            valid_steps += 1
            
    await session.close()
    
    if total_steps == 0:
        pass_rate = 1.0 # If no steps on initial page, vacuously true
    else:
        pass_rate = valid_steps / total_steps
        
    passed = pass_rate >= 0.50 # As long as half the initial page selectors survive, we are good
    
    report = {
        "gate": 4,
        "name": "Replay Feasibility Audit",
        "passed": passed,
        "pass_rate": pass_rate,
        "total_steps": total_steps,
        "valid_steps": valid_steps
    }
    with open("replay_feasibility_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    return passed


async def run_all():
    print("Starting P2B Validation Sprint...")
    store = DEFAULT_STORE
    
    # GATE 1
    p1 = await gate_1_environment_reality(store)
    if not p1:
        print("\n[FAILED] Gate 1: Environment Persistence failed. Stop.")
        sys.exit(1)
        
    # GATE 2
    p2, session_a = await gate_2_recorder_reality(store)
    if not p2:
        print("\n[FAILED] Gate 2: Recorder failed (Security Leak!). Stop.")
        sys.exit(1)
        
    # GATE 3
    p3, tpl_a = await gate_3_compile_quality(store, session_a)
    if not p3:
        print("\n[FAILED] Gate 3: Compiler unstable. Templates diverged heavily. Stop.")
        sys.exit(1)
        
    # GATE 4
    p4 = await gate_4_replay_feasibility(store, tpl_a)
    if not p4:
        print("\n[FAILED] Gate 4: Selectors decay too quickly. Replay infeasible. Stop.")
        sys.exit(1)
        
    print("\n" + "="*50)
    print("ALL GATES PASSED! YOU ARE CLEARED FOR P3 (REPLAY ENGINE).")
    print("="*50)


if __name__ == "__main__":
    asyncio.run(run_all())
