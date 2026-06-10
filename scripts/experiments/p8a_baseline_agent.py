# scripts/experiments/p8a_baseline_agent.py
"""
P8A Strong Baseline Agent (LLM + Playwright).
Uses gemini-2.0-flash directly via google.generativeai.
Strictly exits if GEMINI_API_KEY is missing.
"""
import os
import sys
import json
import asyncio
import google.genai as genai
from google.genai import types as genai_types
from playwright.async_api import Page, async_playwright
# NOTE: Validator intentionally removed.
# Success is determined externally by ContractVerifier (P8A.5).
# The agent executes actions and returns the raw log.

class StrongBaselineAgent:
    def __init__(self, page: Page):
        self.page = page
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            print("ERROR: GEMINI_API_KEY is not set in environment.", file=sys.stderr)
            print("Halting baseline agent. Scientific comparison requires a live LLM API key.", file=sys.stderr)
            sys.exit(1)
            
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = "gemini-3.5-flash"
        self.history = []
        # Cost accounting counters (P8A Information Budget Contract §2)
        self.llm_calls: int = 0
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0

    async def get_visible_elements(self) -> list:
        """Extracts visible interactive elements from the DOM."""
        js_code = """
        () => {
            const elms = Array.from(document.querySelectorAll('input, button, a, select, [role="button"], span, h1, h2, h4'));
            return elms.map((el, i) => {
                const tag = el.tagName.toLowerCase();
                const type = el.getAttribute('type') || '';
                const id = el.id || '';
                const name = el.name || '';
                const placeholder = el.getAttribute('placeholder') || '';
                const text = el.textContent.trim().substring(0, 100);
                const ariaLabel = el.getAttribute('aria-label') || '';
                const visible = el.offsetWidth > 0 && el.offsetHeight > 0;
                return { index: i, tag, type, id, name, placeholder, text, ariaLabel, visible };
            }).filter(e => e.visible);
        }
        """
        try:
            return await self.page.evaluate(js_code)
        except Exception:
            return []

    async def run_task(self, goal: str, start_url: str, max_steps: int = 15) -> dict:
        """Executes a single task rollout on the page. Returns raw execution log.
        
        Success is NOT determined here. ContractVerifier in the challenge
        script evaluates the final browser state as the ground truth.
        """
        steps_log = []
        
        try:
            await self.page.goto(start_url, wait_until="domcontentloaded")
        except Exception as e:
            return {"success": False, "steps": 0, "error": f"Failed to load start URL: {e}"}

        self.history = []

        for step in range(1, max_steps + 1):
            elements = await self.get_visible_elements()
            
            # Format elements list for LLM prompt
            elements_str = ""
            for el in elements[:30]:
                desc = f"[{el['tag']}] id={el['id']} name={el['name']}"
                if el['placeholder']:
                    desc += f" placeholder='{el['placeholder']}'"
                if el['text']:
                    desc += f" text='{el['text']}'"
                elements_str += f"- {desc}\n"

            recent_history = "\n".join(self.history[-5:]) or "None"

            prompt = f"""You are an autonomous browser agent. Your task is to achieve the following goal:
Goal: {goal}
Current URL: {self.page.url}

Visible elements on the page:
{elements_str}

Action history:
{recent_history}

Decide the next action to perform. You must output ONLY a valid JSON object matching one of these templates:
- Click a visible element:
  {{"action": "click", "selector": "#element-id-or-css-selector"}}
- Type into an input field:
  {{"action": "type", "selector": "#input-id-or-css-selector", "value": "text to type"}}
- Navigate to a URL:
  {{"action": "navigate", "url": "URL to navigate to"}}
- Mark the goal as successfully completed:
  {{"action": "done"}}

Rules:
1. Output ONLY JSON. No explanation. No code block markdown.
2. Select the element most relevant to the goal.
3. If you have successfully completed the goal, output "done".
"""
            action_data = None
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    response = self.client.models.generate_content(
                        model=self.model_name,
                        contents=prompt,
                        config=genai_types.GenerateContentConfig(
                            response_mime_type="application/json"
                        )
                    )
                    # Track cost per the P8A contract
                    self.llm_calls += 1
                    if response.usage_metadata:
                        self.prompt_tokens     += response.usage_metadata.prompt_token_count or 0
                        self.completion_tokens += response.usage_metadata.candidates_token_count or 0
                    action_data = json.loads(response.text.strip())
                    break  # Success
                except Exception as e:
                    err_msg = str(e)
                    if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                        if attempt < max_retries - 1:
                            wait_time = 15 * (2 ** attempt)  # 15s, 30s, 60s...
                            print(f"      [Baseline] 429 Rate Limit Hit. Waiting {wait_time}s (Attempt {attempt+1}/{max_retries})...", flush=True)
                            await asyncio.sleep(wait_time)
                            continue
                    action_data = {"action": "stuck", "reason": err_msg}
                    break

            action_type = action_data.get("action", "stuck")
            steps_log.append({
                "step": step,
                "action": action_type,
                "url": self.page.url,
                "details": action_data
            })
            
            self.history.append(f"Step {step}: {action_data}")

            if action_type == "done":
                # Agent declares done — return log, let ContractVerifier decide success
                return {
                    "success": None,   # to be filled by ContractVerifier
                    "steps": step,
                    "log": steps_log,
                    "agent_declared": "done"
                }

            if action_type == "stuck":
                return {
                    "success": False,
                    "steps": step,
                    "log": steps_log,
                    "error": action_data.get("reason", "Unknown stuck reason")
                }

            # Execute Playwright Action
            try:
                if action_type == "click":
                    selector = action_data["selector"]
                    # If selector is just text, use page.get_by_text
                    if selector.startswith("text="):
                        await self.page.get_by_text(selector[5:]).first.click(timeout=5000)
                    else:
                        await self.page.click(selector, timeout=5000)
                    await self.page.wait_for_load_state("domcontentloaded")
                    
                elif action_type == "type":
                    selector = action_data["selector"]
                    value = action_data["value"]
                    await self.page.fill(selector, value, timeout=5000)
                    # Submit if it's an input field and the task calls for search/login
                    if any(k in goal.lower() for k in ("search", "find", "login", "submit")):
                        await self.page.keyboard.press("Enter")
                    await self.page.wait_for_load_state("domcontentloaded")
                    
                elif action_type == "navigate":
                    url = action_data["url"]
                    await self.page.goto(url, wait_until="domcontentloaded", timeout=10000)

            except Exception as e:
                self.history.append(f"Action error: {e}")
                steps_log[-1]["error"] = str(e)

            # No internal validation check — ContractVerifier runs after agent finishes
            await asyncio.sleep(0.3)

        return {"success": None, "steps": max_steps, "log": steps_log, "agent_declared": "max_steps"}
