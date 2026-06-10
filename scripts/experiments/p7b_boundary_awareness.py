# scripts/experiments/p7b_boundary_awareness.py
"""P7B Boundary-Aware Validation.

Verifies that the agent correctly identifies its boundaries, halts execution gracefully,
and outputs FailureOntologyDiagnostic self-diagnostics based on live page DOM and state.
"""
import sys
import json
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browsermind_core.agent.router import PolicyRouter, FailureOntologyDiagnostic

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

async def test_flow(router, page, flow_name, context=None):
    print(f"Routing Flow: '{flow_name}' on current URL: {page.url}...")
    try:
        executor = await router.route(flow_name, page, context)
        print(f"  -> Routed successfully to: {executor.__class__.__name__}\n")
        return True
    except FailureOntologyDiagnostic as e:
        print(f"  -> environmental boundary detected!")
        # Print diagnostic dictionary
        diag = e.to_dict()
        print(f"     Diagnostic Payload:")
        print(json.dumps(diag, indent=6))
        print()
        return False

async def main():
    print(f"\n========================================================")
    print(f" P7B: BOUNDARY-AWARE AGENT DIAGNOSTICS (LIVE RUN)")
    print(f"========================================================\n")
    
    router = PolicyRouter()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(6000)
        
        # 1. Structural flows (No context required)
        print("--- 1. Testing Information/Interaction Flows ---")
        await page.goto("https://en.wikipedia.org/wiki/Main_Page")
        await test_flow(router, page, "Navigation")
        
        await page.goto("https://react-shopping-cart-67954.firebaseapp.com/")
        await page.wait_for_load_state("networkidle")
        await test_flow(router, page, "Filtering")
        
        # 2. Settings Flow without context (Boundary - redirects to GitHub login)
        print("--- 2. Testing Settings Redirect (Boundary) ---")
        await page.goto("https://github.com/settings/profile")
        await page.wait_for_load_state("networkidle")
        halted_settings = not await test_flow(router, page, "Settings")
        
        # 3. Settings Flow with context (Rescued)
        print("--- 3. Testing Settings Redirect (With Context) ---")
        # Providing session cookies rescues it, routing it to AuthenticatedExecutor
        await test_flow(router, page, "Settings", {"session_cookies": ["mock_cookie"]})
        
        # 4. Auth Flow without context (Boundary - on login page)
        print("--- 4. Testing Credentials Auth Gate (Boundary) ---")
        await page.goto("https://github.com/login")
        await page.wait_for_load_state("networkidle")
        halted_auth = not await test_flow(router, page, "Auth")
        
        # 5. Captcha Boundary Check (Environmental DOM injection)
        print("--- 5. Testing Environmental Captcha Boundary ---")
        # Programmatically inject a captcha frame in the DOM
        await page.evaluate("""() => {
            const iframe = document.createElement('iframe');
            iframe.src = 'https://www.google.com/recaptcha/api2/anchor';
            document.body.appendChild(iframe);
        }""")
        halted_captcha = not await test_flow(router, page, "Search")
        
        await browser.close()
        
    print("========================================================")
    print(" SUMMARY")
    print("========================================================")
    print(f" Settings redirection boundary caught? : {halted_settings}")
    print(f" Auth credentials boundary caught?     : {halted_auth}")
    print(f" Live Captcha boundary caught?         : {halted_captcha}")
    
    if halted_settings and halted_auth and halted_captcha:
        print(f"\nVERDICT: SUCCESS. The agent successfully recognized live environmental failures and halted with Failure Ontology details.")
    else:
        print(f"\nVERDICT: FAILED. One or more boundaries were not caught correctly.")
    print("========================================================")

if __name__ == "__main__":
    asyncio.run(main())
