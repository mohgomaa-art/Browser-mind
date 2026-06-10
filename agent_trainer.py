"""
BrowserMind — Agent Trainer v2 (Self-Improving Loop)
=======================================================
اللوب الكامل:

  for each loop:
    1. page.goto(url)                  ← reset
    2. LLM يشوف الصفحة
    3. LLM يقرر الأكشن
    4. DecisionEngine ينفذ (top-k + retry)
    5. Validator يتأكد هل نجح فعلاً؟
    6. Recorder يسجل بس لو success=True
    7. حفظ session

  بعد كل الـ loops:
    DatasetCleaner يفلتر
    train.py يتدرب على النضيف بس

Usage:
    export LLM_API_KEY="sk-..."
    python agent_trainer_v2.py --goal "login to github" --url "https://github.com/login" --loops 20
"""

import asyncio
import json
import os
import sys
import time
import argparse
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx
from playwright.async_api import async_playwright, Page

sys.path.insert(0, str(Path(__file__).parent))

from core.recorder       import SessionRecorder, get_current_state
from core.decision_engine import DecisionEngine
from core.validator       import Validator, ValidationResult
from core.dataset_cleaner import DatasetCleaner
from core.privacy         import (
    redact_sensitive_text,
    sanitize_goal_for_storage,
    sanitize_state_for_storage,
    sanitize_typed_text,
)


# ─────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────
LLM_API_KEY   = os.getenv("LLM_API_KEY",  "YOUR_API_KEY_HERE")
LLM_BASE_URL  = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
LLM_MODEL     = os.getenv("LLM_MODEL",    "google/gemini-2.5-flash")

MAX_STEPS     = 15      # أقصى steps في loop واحدة
ACTION_DELAY  = 1.2     # ثواني بين الـ actions
PAGE_TIMEOUT  = 8000    # ms


# ─────────────────────────────────────────────
#  LLM Client
# ─────────────────────────────────────────────
class LLMClient:
    def __init__(self):
        self.base_url = LLM_BASE_URL.rstrip("/")
        self.model    = LLM_MODEL

    async def ask(self, system: str, user: str) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model":       self.model,
                    "max_tokens":  400,
                    "temperature": 0.1,   # أقل = أكثر consistency = داتا أنضف
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()


# ─────────────────────────────────────────────
#  Prompt
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """You are a precise browser automation agent.
Goal: complete the given task in minimum steps.

Output ONLY valid JSON — no explanation, no markdown:
  {"action": "click",  "target_text": "exact visible text"}
  {"action": "type",   "target_text": "input placeholder/label", "value": "text to type"}
  {"action": "scroll", "direction": "down"}
  {"action": "done",   "reason": "goal achieved"}
  {"action": "stuck",  "reason": "cannot proceed"}

Rules:
- ONLY valid JSON. Nothing else.
- target_text must be the EXACT visible text or placeholder.
- If goal is done → {"action": "done", ...}
- If truly blocked → {"action": "stuck", ...}
"""


def build_prompt(goal: str, elements: List[Dict], step: int, history: List[str]) -> str:
    lines = []
    for i, e in enumerate(elements[:30]):
        label = (e.get("text") or e.get("placeholder") or "").strip()[:60]
        if label:
            lines.append(f'[{i}] <{e["tag"]}> "{label}"')

    return (
        f"Goal: {goal}\n"
        f"Step: {step}/{MAX_STEPS}\n"
        f"History: {' → '.join(history[-5:]) or 'none'}\n\n"
        f"Elements:\n" + "\n".join(lines) +
        "\n\nNext action?"
    )


async def parse_action(response: str) -> Optional[Dict]:
    try:
        text = response.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception:
        return None


# ─────────────────────────────────────────────
#  Clean Recorder — يسجل بس لو success=True
# ─────────────────────────────────────────────
class CleanRecorder:
    """
    أهم سطر في السيستم كله:
        if not success: return   # لا تسجل الغلط
    """
    def __init__(self, goal: str, save_dir: str = "training/sessions"):
        self.goal      = sanitize_goal_for_storage(goal)
        self.save_dir  = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.samples:  List[Dict] = []
        self._step     = 0
        self._session_id = __import__("uuid").uuid4().hex[:8]
        self._start    = time.time()

    def record(
        self,
        state:           Dict,
        action_type:     str,
        target_text:     str,
        target_selector: str,
        typed_text:      str,
        success:         bool,
        verify_signal:   str = "",
    ):
        self._step += 1

        # ══════════════════════════════════════
        # أهم سطر — مسجلش الغلط خالص
        if not success:
            print(f"  [Recorder] [X] step {self._step}: {action_type} FAILED - not recorded")
            return
        # ══════════════════════════════════════

        self.samples.append({
            "step": self._step,
            "state": sanitize_state_for_storage({
                "elements":  state.get("elements", []),
                "page_url":  state.get("page_url", ""),
                "page_type": state.get("page_type", "unknown"),
            }),
            "action": {
                "action_type":     action_type,
                "target_text":     redact_sensitive_text(target_text),
                "target_selector": redact_sensitive_text(target_selector),
                "typed_text":      sanitize_typed_text(typed_text, target_text=target_text, goal_text=self.goal),
                "goal":            self.goal,
            },
            "success":        True,
            "verify_signal":  verify_signal,
        })
        print(f"  [Recorder] [OK] step {self._step}: {action_type} -> '{redact_sensitive_text(target_text)}' [{verify_signal}]")

    def save(self) -> str:
        if not self.samples:
            print("  [Recorder] (!) 0 valid samples - session not saved")
            return ""

        data = {
            "session_id":  self._session_id,
            "goal":        self.goal,
            "timestamp":   self._start,
            "duration_s":  round(time.time() - self._start, 1),
            "total_steps": len(self.samples),
            "samples":     self.samples,
        }
        path = self.save_dir / f"session_{self._session_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  [Recorder] [SAVED] {len(self.samples)} clean steps -> {path}")
        return str(path)


# ─────────────────────────────────────────────
#  Step Executor — نفذ + تحقق
# ─────────────────────────────────────────────
async def execute_and_verify(
    page:        Page,
    action:      Dict,
    elements:    List[Dict],
    goal:        str,
    validator:   Validator,
) -> Tuple[bool, str, str, str]:
    """
    ينفذ الأكشن باستخدام DecisionEngine (filter → rank → retry)
    ثم يتحقق بـ Validator (semantic success)

    Returns: (success, target_text, target_selector, verify_signal)
    """
    act         = action.get("action", "")
    target_text = action.get("target_text", "")
    value       = action.get("value", "")
    url_before  = page.url

    try:
        if act == "click":
            engine = DecisionEngine(top_k=3, max_retries=3)
            result = await engine.execute_action(
                page        = page,
                action_type = "click",
                target_text = target_text,
                goal        = goal,
                elements    = elements,
            )
            if not result.success:
                return False, target_text, "", "engine_failed"

            # Semantic validation
            await asyncio.sleep(1.0)
            vr = await validator.check(page, goal, url_before)
            return vr.success, target_text, "", vr.signal

        elif act == "type":
            engine = DecisionEngine(top_k=3, max_retries=3)
            result = await engine.execute_action(
                page         = page,
                action_type  = "type",
                target_text  = target_text,
                goal         = goal,
                elements     = elements,
                typed_value  = value,
            )
            # بالنسبة لـ type: نجاح الكتابة كافي (مش محتاجين URL change)
            selector = ""
            if result.used_candidate and result.used_candidate.element:
                el = result.used_candidate.element
                selector = f"#{el['id_attr']}" if el.get("id_attr") else target_text

            signal = "typed_ok" if result.success else "type_failed"
            return result.success, target_text, selector, signal

        elif act == "scroll":
            direction = action.get("direction", "down")
            delta     = 500 if direction == "down" else -500
            await page.mouse.wheel(0, delta)
            await asyncio.sleep(0.5)
            return True, f"scroll_{direction}", "", "scrolled"

        elif act == "go_back":
            await page.go_back()
            try:
                await page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT)
            except Exception:
                pass
            return True, "go_back", "", "navigated_back"

    except Exception as e:
        print(f"    (!) Execution exception: {e}")

    return False, target_text, "", "exception"


# ─────────────────────────────────────────────
#  Main Training Loop
# ─────────────────────────────────────────────
async def run(goal: str, start_url: str, num_loops: int):
    llm       = LLMClient()
    validator = Validator()

    print(f"\n{'='*55}")
    print(f"  BrowserMind v2 — Self-Improving Agent")
    print(f"{'='*55}")
    print(f"  Goal   : {goal}")
    print(f"  URL    : {start_url}")
    print(f"  Loops  : {num_loops}")
    print(f"  Model  : {LLM_MODEL}")
    print(f"{'='*55}\n")

    total_recorded = 0
    total_loops_ok = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-gpu",
            ],
        )
        context = await browser.new_context(
            viewport    = {"width": 1280, "height": 720},
            user_agent  = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale      = "en-US",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        for loop_num in range(1, num_loops + 1):
            print(f"\n── Loop {loop_num:02d}/{num_loops} {'─'*35}")

            recorder = CleanRecorder(goal=goal)
            page     = await context.new_page()
            history: List[str] = []
            goal_achieved = False

            try:
                # ① Reset — كل loop تبدأ من الأول
                await page.goto(start_url)
                try:
                    await page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT)
                except Exception:
                    pass

                for step in range(1, MAX_STEPS + 1):

                    # ② State capture
                    state    = await get_current_state(page)
                    elements = state.get("elements", [])

                    if not elements:
                        print(f"  (!) Step {step}: no elements found")
                        break

                    # ③ LLM decision
                    prompt = build_prompt(goal, elements, step, history)
                    try:
                        response = await llm.ask(SYSTEM_PROMPT, prompt)
                        print(f"  Step {step:02d} | LLM -> {response[:90]}")
                    except Exception as e:
                        print(f"  [X] LLM error: {e}")
                        break

                    # ④ Parse
                    action = await parse_action(response)
                    if not action:
                        print(f"  (!) Parse failed: {response[:60]}")
                        continue

                    act = action.get("action", "")

                    # ⑤ Terminal actions
                    if act == "done":
                        print(f"  [OK] Goal achieved: {action.get('reason', '')}")
                        goal_achieved = True
                        break
                    if act == "stuck":
                        print(f"  [X] Agent stuck: {action.get('reason', '')}")
                        break

                    # ⑥ Execute + Verify
                    success, target_text, selector, signal = await execute_and_verify(
                        page, action, elements, goal, validator
                    )

                    # ⑦ Record — بس لو success=True
                    recorder.record(
                        state           = state,
                        action_type     = act,
                        target_text     = target_text,
                        target_selector = selector,
                        typed_text      = action.get("value", ""),
                        success         = success,
                        verify_signal   = signal,
                    )

                    status = "OK" if success else "FAIL"
                    history.append(f"{act}({target_text[:15]}){status}")

                    await asyncio.sleep(ACTION_DELAY)

            except Exception as e:
                print(f"  [X] Loop error: {e}")

            finally:
                saved_path = recorder.save()
                if saved_path:
                    total_recorded  += len(recorder.samples)
                    total_loops_ok  += 1
                await page.close()

        await browser.close()

    # ─────────────────────────────────────────
    #  بعد الـ loops — clean ثم train
    # ─────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"  Data Collection Done")
    print(f"  Loops completed : {total_loops_ok}/{num_loops}")
    print(f"  Clean steps     : {total_recorded}")
    print(f"{'='*55}")

    # Step 1: Clean dataset
    print(f"\n── Cleaning Dataset ──────────────────────────────")
    cleaner = DatasetCleaner(
        input_dir  = "training/sessions",
        output_dir = "training/cleaned_sessions",
        min_steps  = 2,
    )
    stats = cleaner.clean_all()

    if stats["samples_kept"] == 0:
        print("⚠️  No clean samples to train on. Collect more data.")
        return

    # Step 2: Train on clean data
    print(f"── Training on cleaned data ──────────────────────")
    subprocess.run(
        [
            sys.executable, "train.py",
            "--sessions", "training/cleaned_sessions",
            "--epochs",   "3",
        ],
        cwd=str(Path(__file__).parent),
    )

    print(f"\n✅ Done. Model updated.")
    print(f"   Test: python main.py '{goal}' --model")


# ─────────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BrowserMind Self-Improving Agent")
    parser.add_argument("--goal",  required=True, help="Task goal")
    parser.add_argument("--url",   required=True, help="Start URL")
    parser.add_argument("--loops", type=int, default=20, help="Training loops")
    args = parser.parse_args()

    if LLM_API_KEY == "YOUR_API_KEY_HERE":
        print("❌ Set your API key:")
        print("   export LLM_API_KEY='sk-...'")
        print("   export LLM_BASE_URL='https://openrouter.ai/api/v1'")
        sys.exit(1)

    asyncio.run(run(args.goal, args.url, args.loops))
