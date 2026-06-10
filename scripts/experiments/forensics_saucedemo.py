import asyncio
import json
from pathlib import Path
import sys

from browsermind_core.console.session import KernelSession
from browsermind_core.runtime.environment_registry import resolve
from browsermind_core.runtime.auth_session import AuthSession
from browsermind_core.runtime.target_resolver import TargetResolver
from browsermind_core.runtime.action_executor import ActionExecutor, ActionExecutionError

ROOT_DIR = Path(__file__).resolve().parents[2]
STORE_DIR = Path.home() / ".browsermind"

async def run_forensics():
    site_key = "saucedemo"
    template_name = "exp_saucedemo_checkout"
    
    print(f"Starting Forensics on {site_key} / {template_name}")
    
    kernel = KernelSession(str(STORE_DIR))
    
    entry = kernel.workflow_store.lookup_template(template_name)
    if not entry:
        print(f"Error: Template {template_name} not found")
        sys.exit(1)
        
    template = kernel.workflow_store.get_template(entry["id"])
    env_entry = resolve(site_key)
    
    auth = AuthSession(
        entry=env_entry,
        persona_name="validator",
        store_dir=STORE_DIR,
        headless=True
    )
    
    page = await auth.open(env_entry.start_url)
    resolver = TargetResolver(page)
    executor = ActionExecutor(page)
    
    forensics_report = []
    
    print("Executing steps layer by layer...")
    
    for i, step_def in enumerate(template.steps):
        step_seq = step_def.get("seq", i)
        action_type = step_def.get("action_type")
        role = step_def.get("target_role")
        name = step_def.get("target_name")
        target_value = step_def.get("default_value")
        binding = step_def.get("input_binding")
        if binding:
            b_type = binding.get("type")
            b_key = binding.get("key", "")
            if b_type == "vault":
                import os
                vault_val = os.environ.get(f"BM_VAULT_{b_key.upper()}", os.environ.get("BM_VAULT_SECRET"))
                if vault_val:
                    target_value = vault_val
        target_url = step_def.get("url")
        
        print(f"\nStep {step_seq}: {action_type} {role} '{name}'")
        
        report = {
            "step": step_seq,
            "action": action_type,
            "target_role": role,
            "target_name": name,
            "target_value": target_value,
            "resolved": False,
            "executed": False,
            "element_value_before": None,
            "element_value_after": None,
            "url_before": page.url,
            "url_after": None,
            "error": None
        }
        
        try:
            loc_tuple = await resolver.resolve(
                target_role=role,
                target_name=name,
                target_selector=step_def.get("target_selector", ""),
                descriptor=step_def.get("descriptor", {}),
                enable_recovery=True
            )
            loc = loc_tuple[0]
            report["resolved"] = loc is not None
            
            if loc:
                # Pre-action probe
                try:
                    is_input = await loc.evaluate("el => el.tagName.toLowerCase() === 'input' || el.tagName.toLowerCase() === 'textarea'")
                    if is_input:
                        report["element_value_before"] = await loc.evaluate("el => el.value")
                except Exception as e:
                    pass
            
            # Layer 2: Execute
            await executor.execute(action_type, loc, target_value, target_url, enable_recovery=True)
            report["executed"] = True
            
            # Brief pause to allow DOM/Network effect
            await page.wait_for_timeout(500)
            
            # Layer 3: Effect (Post-action probe)
            if loc:
                try:
                    # Sometimes locator detaches after action (e.g. click causes nav)
                    if await loc.count() > 0:
                        is_input = await loc.evaluate("el => el.tagName.toLowerCase() === 'input' || el.tagName.toLowerCase() === 'textarea'")
                        if is_input:
                            report["element_value_after"] = await loc.evaluate("el => el.value")
                except Exception:
                    report["element_value_after"] = "DETACHED"
                    
        except Exception as e:
            report["error"] = str(e)
            print(f"  Error: {e}")
            
        report["url_after"] = page.url
        forensics_report.append(report)
        
    await auth.close()
    
    out_file = ROOT_DIR / "reports" / "saucedemo_forensics.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(forensics_report, indent=2), encoding="utf-8")
    
    print(f"\nForensics complete. Saved to {out_file}")

if __name__ == "__main__":
    asyncio.run(run_forensics())
