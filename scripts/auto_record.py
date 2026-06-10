import sys
import builtins
import threading
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

input_event = threading.Event()

def fake_input(prompt=""):
    input_event.wait()
    return ""

builtins.input = fake_input

from browsermind_core.recorder.semantic_recorder import SemanticRecorder
original_attach = SemanticRecorder.attach

async def run_automation(page, url):
    try:
        print(f"[AutoRecorder] Starting automation for {url}")
        await asyncio.sleep(2)
        if "demoqa.com" in url:
            await page.wait_for_timeout(2000)
            await page.fill("#userName", "Test User")
            await page.fill("#userEmail", "test@example.com")
            await page.fill("#currentAddress", "123 Main St")
            await page.fill("#permanentAddress", "456 Oak Ave")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(500)
            await page.click("#submit")
            await page.wait_for_timeout(2000)
        elif "the-internet" in url:
            await page.goto("https://the-internet.herokuapp.com/login")
            await page.wait_for_timeout(2000)
            await page.fill("#username", "tomsmith")
            await page.fill("#password", "SuperSecretPassword!")
            await page.click("button[type='submit']")
            await page.wait_for_timeout(2000)
        elif "github.com" in url:
            await page.goto("https://github.com/microsoft/playwright")
            await page.wait_for_timeout(2000)
            await page.click("a#issues-tab")
            await page.wait_for_timeout(2000)
        elif "huggingface.co" in url:
            await page.goto("https://huggingface.com/models")
            await page.wait_for_timeout(2000)
            await page.fill("input[type='search']", "bert")
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)
            # Find the first article and click it
            await page.locator("article").first.click()
            await page.wait_for_timeout(2000)
            await page.click("text=Files and versions")
            await page.wait_for_timeout(2000)
        elif "saucedemo.com" in url:
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
        elif "wikipedia.org" in url:
            await page.wait_for_timeout(1000)
            await page.fill("#searchInput", "BrowserMind")
            await page.click("button[type='submit']")
            await page.wait_for_timeout(2000)
            try:
                await page.click("text=Browser")
                await page.wait_for_timeout(2000)
            except Exception:
                pass
        elif "localhost" in url or "127.0.0.1" in url:
            await page.wait_for_timeout(1000)
            await page.fill("input[name='username']", "driftuser")
            await page.fill("input[name='password']", "driftpass")
            await page.click("button[type='submit']")
            await page.wait_for_timeout(2000)
        print(f"[AutoRecorder] Automation completed")
    except Exception as e:
        print(f"[AutoRecorder] Error: {e}")
    finally:
        input_event.set()

async def auto_attach(self, context, page):
    await original_attach(self, context, page)
    asyncio.create_task(run_automation(page, page.url))

SemanticRecorder.attach = auto_attach

if __name__ == "__main__":
    import scripts.run_replay_experiments
    sys.exit(scripts.run_replay_experiments.main())
