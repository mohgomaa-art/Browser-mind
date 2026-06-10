"""
BrowserMind — Gemini Agent Trainer
=====================================
Gemini Flash بيشتغل زي Antigravity بالظبط:
  - يشوف الصفحة
  - يقرر الأكشن
  - Playwright ينفذ
  - Recorder يسجل
  - train.py يدرب الموديل

API Key مجاني من: https://aistudio.google.com/apikey

الاستخدام:
    export GEMINI_API_KEY="AIza..."
    python agent_trainer_gemini.py --goal "search for python jobs" --url "https://google.com" --loops 30
"""

import asyncio
import json
import os
import sys
import subprocess
import argparse
from pathlib import Path

import google.generativeai as genai
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parent))
from core.recorder import SessionRecorder, get_current_state


# ─────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "YOUR_KEY_HERE")
GEMINI_MODEL       = "gemini-2.0-flash"   # مجاني + سريع
MAX_STEPS          = 12                   # أقصى خطوات في session
DELAY_SECS         = 1.2                  # تأخير بين الأكشنات


# ─────────────────────────────────────────────
#  Gemini Client
# ─────────────────────────────────────────────
class GeminiAgent:
    def __init__(self):
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction="""You are a browser automation agent.
Given a goal and a list of page elements, output ONE action as JSON only.

Available actions:
  {"action": "click",  "target": "exact text of element"}
  {"action": "type",   "target": "placeholder or label", "value": "text to type"}
  {"action": "scroll", "direction": "down"}
  {"action": "done",   "reason": "goal achieved"}
  {"action": "stuck",  "reason": "cannot proceed"}

Rules:
- Output ONLY valid JSON. No explanation. No markdown.
- Pick the element most relevant to the goal.
- If the goal is complete, output done.
- If nothing makes sense after 3 tries, output stuck."""
        )

    async def decide(self, goal: str, elements: list, history: list) -> dict:
        # بناء prompt مختصر
        el_list = "\n".join([
            f'[{i}] <{e["tag"]}> "{e.get("text") or e.get("placeholder","")}" '
            f'clickable={e.get("clickable",False)} pos=({e.get("x",0)},{e.get("y",0)})'
            for i, e in enumerate(elements[:20])
            if e.get("text") or e.get("placeholder")
        ])
        recent = " → ".join(history[-4:]) or "none"

        prompt = f"""Goal: {goal}
Recent actions: {recent}

Elements on page:
{el_list}

What action next?"""

        try:
            resp = self.model.generate_content(prompt)
            text = resp.text.strip()
            # شيل markdown لو موجود
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        except Exception as e:
            print(f"    ⚠️  Gemini error: {e}")
            return {"action": "stuck", "reason": str(e)}


# ─────────────────────────────────────────────
#  Execute action
# ─────────────────────────────────────────────
async def _try_click(page, target: str) -> bool:
    """جرب click بطرق مختلفة — True لو نجحت"""
    for get_el in [
        lambda: page.get_by_text(target, exact=True).first,
        lambda: page.get_by_text(target, exact=False).first,
        lambda: page.get_by_placeholder(target).first,
        lambda: page.get_by_role("button", name=target).first,
    ]:
        try:
            el = get_el()
            if await el.is_visible():
                await el.click()
                await page.wait_for_load_state("networkidle", timeout=3000)
                return True
        except Exception:
            continue
    return False


async def execute(page, action: dict, top_candidates: list = None) -> tuple[bool, str]:
    """UPGRADE-2: retry على top-3 candidates لو أول محاولة فشلت"""
    act    = action.get("action", "")
    target = action.get("target", "")

    try:
        if act == "click":
            if await _try_click(page, target):
                return True, target

            # retry بالـ top candidates من الـ state
            if top_candidates:
                for c in top_candidates:
                    el_text = (c.get("element") or {}).get("text") or                               (c.get("element") or {}).get("placeholder", "")
                    if el_text and el_text != target:
                        print(f"    ↩️  Retry: '{el_text}'")
                        if await _try_click(page, el_text):
                            return True, el_text
            return False, target

        elif act == "type":
            value = action.get("value", "")
            for get_el in [
                lambda: page.get_by_placeholder(target).first,
                lambda: page.get_by_label(target).first,
                lambda: page.locator("input:visible").first,
            ]:
                try:
                    el = get_el()
                    if await el.is_visible():
                        await el.click()
                        await el.fill(value)
                        return True, target
                except Exception:
                    continue
            return False, target

        elif act == "scroll":
            direction = action.get("direction", "down")
            await page.mouse.wheel(0, 600 if direction == "down" else -600)
            await asyncio.sleep(0.4)
            return True, f"scroll_{direction}"

        elif act in ("done", "stuck"):
            return True, act

    except Exception as e:
        print(f"    ⚠️  Execute error: {e}")

    return False, act


# ─────────────────────────────────────────────
#  One training loop
# ─────────────────────────────────────────────
async def run_loop(browser, agent: GeminiAgent, goal: str, start_url: str, loop_num: int):
    recorder = SessionRecorder(goal=goal)
    page     = await browser.new_page()
    history  = []
    steps_done = 0

    try:
        await page.goto(start_url, wait_until="networkidle", timeout=10000)

        for step in range(1, MAX_STEPS + 1):
            state    = await get_current_state(page)
            elements = state.get("elements", [])

            if not elements:
                print(f"    No elements — skipping")
                break

            # Gemini يقرر
            action = await agent.decide(goal, elements, history)
            act    = action.get("action", "")
            print(f"    [{step}] Gemini → {action}")

            # لو خلص أو وقف
            if act in ("done", "stuck"):
                recorder.record_step(
                    state       = state,
                    action_type = act,
                    target_text = action.get("reason", ""),
                    success     = act == "done",
                )
                break

            # نفذ
            success, target_text = await execute(page, action)

            # سجل الناجح فقط
            if success:
                recorder.record_step(
                    state       = state,
                    action_type = act,
                    target_text = target_text,
                    typed_text  = action.get("value", ""),
                    success     = True,
                )
            else:
                print(f"    ⚠️  Failed — not recorded")

            history.append(f"{act}({target_text[:15]})")
            steps_done += 1
            await asyncio.sleep(DELAY_SECS)

    except Exception as e:
        print(f"    ❌ Loop error: {e}")
    finally:
        recorder.save()
        await page.close()

    return steps_done


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────
async def train(goal: str, start_url: str, num_loops: int):
    if GEMINI_API_KEY == "YOUR_KEY_HERE":
        print("❌ محتاج Gemini API key!")
        print("   1. روح: https://aistudio.google.com/apikey")
        print("   2. اعمل key مجاني")
        print("   3. export GEMINI_API_KEY='AIza...'")
        sys.exit(1)

    agent = GeminiAgent()
    total = 0

    print(f"\n{'='*55}")
    print(f"  🤖 GEMINI AGENT TRAINER")
    print(f"  Goal  : {goal}")
    print(f"  URL   : {start_url}")
    print(f"  Loops : {num_loops}")
    print(f"  Model : {GEMINI_MODEL} (free)")
    print(f"{'='*55}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        for i in range(1, num_loops + 1):
            print(f"\n── Loop {i}/{num_loops} ───────────────────────────")
            steps = await run_loop(browser, agent, goal, start_url, i)
            total += steps
            print(f"   ✅ {steps} steps recorded")

        await browser.close()

    # درب الموديل بعد ما كل الداتا اتجمعت
    print(f"\n{'='*55}")
    print(f"  ✅ Done! Total samples: {total}")
    print(f"  🏋️  Training model now...")
    print(f"{'='*55}\n")
    subprocess.run([sys.executable, "train.py", "--epochs", "5"])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--goal",  required=True)
    p.add_argument("--url",   required=True)
    p.add_argument("--loops", type=int, default=20)
    args = p.parse_args()
    asyncio.run(train(args.goal, args.url, args.loops))
