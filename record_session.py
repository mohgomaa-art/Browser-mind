"""
BrowserMind - Manual Recording Mode
===================================
Open a headed browser, manually interact with a social website,
and auto-record click/type demonstrations as training sessions.

Examples:
  python record_session.py --goal "facebook like and comment" --url "https://www.facebook.com" --browser chrome
  python record_session.py --goal "reddit post interaction" --url "https://www.reddit.com" --browser chrome --train-social
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parent))
from core.recorder import SessionRecorder, get_current_state


def _default_profile_dir() -> str:
  return str((Path.home() / ".browsermind" / "chrome_profile").resolve())


def _default_chrome_exe() -> str:
  candidates = [
    Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe",
  ]
  for c in candidates:
    if c.exists():
      return str(c)
  return ""


def _run_native_auth_portal(args) -> None:
  profile_dir = Path(args.user_data_dir).expanduser().resolve()
  profile_dir.mkdir(parents=True, exist_ok=True)

  chrome_exe = args.chrome_exe or _default_chrome_exe()
  if not chrome_exe:
    print("[WARN] Could not auto-detect Chrome executable for auth portal; skipping auth-first step.")
    return

  print("\n" + "=" * 60)
  print("Native Chrome Authentication Step")
  print(f"Chrome exe  : {chrome_exe}")
  print(f"Profile dir : {profile_dir}")
  print(f"Auth URL    : {args.auth_url}")
  print("Log in on all desired sites, then close all Chrome windows to continue.")
  print("=" * 60 + "\n")

  cmd = [
    chrome_exe,
    f"--user-data-dir={profile_dir}",
    "--no-first-run",
    "--start-maximized",
    args.auth_url,
  ]

  try:
    proc = subprocess.Popen(cmd)
    proc.wait()
  except Exception as exc:
    print(f"[WARN] Native auth portal launch failed: {exc}")


def _cleanup_profile_chrome_processes(user_data_dir: str) -> None:
  """Terminate Chrome processes that still hold the target profile lock."""
  if not user_data_dir:
    return
  profile_dir = str(Path(user_data_dir).expanduser().resolve())
  # Build a regex-safe path fragment for Win32_Process command line matching.
  escaped_profile = re.escape(profile_dir)
  ps_script = (
    "$p=Get-CimInstance Win32_Process | "
    "Where-Object { $_.Name -ieq 'chrome.exe' -and $_.CommandLine -match '"
    + escaped_profile
    + "' }; "
    "if($p){ foreach($x in $p){ try { Stop-Process -Id $x.ProcessId -Force -ErrorAction SilentlyContinue; "
    "Write-Output ('STOPPED_CHROME_PID=' + $x.ProcessId) } catch {} } }"
  )
  try:
    subprocess.run(
      ["powershell", "-NoProfile", "-Command", ps_script],
      check=False,
      capture_output=True,
      text=True,
    )
  except Exception:
    pass


_INJECT_RECORDER_JS = r"""
(() => {
  if (window.__bmRecordHooksInstalled) return;
  window.__bmRecordHooksInstalled = true;

  const readText = (el) => {
    try {
      const t = (el.innerText || el.value || el.getAttribute('aria-label') || el.placeholder || '').toString().trim();
      return t.slice(0, 120);
    } catch {
      return '';
    }
  };

  const selectorFor = (el) => {
    try {
      if (el.id) return '#' + el.id;
      const tag = (el.tagName || 'unknown').toLowerCase();
      const cls = (el.className || '').toString().split(/\s+/).filter(Boolean)[0];
      if (cls) return tag + '.' + cls;
      const nameAttr = el.getAttribute('name');
      if (nameAttr) return tag + '[name="' + nameAttr + '"]';
      return tag;
    } catch {
      return '';
    }
  };

  const emit = (payload) => {
    try {
      if (typeof window.__bm_record === 'function') {
        window.__bm_record(payload);
      }
    } catch {}
  };

  document.addEventListener('click', (ev) => {
    const el = ev.target;
    if (!el || !el.tagName) return;
    emit({
      action_type: 'click',
      target_text: readText(el),
      target_selector: selectorFor(el),
      typed_text: ''
    });
  }, true);

  document.addEventListener('input', (ev) => {
    const el = ev.target;
    if (!el || !el.tagName) return;
    const tag = el.tagName.toLowerCase();
    if (tag !== 'input' && tag !== 'textarea' && !el.isContentEditable) return;
    let typed = '';
    try {
      typed = (el.value || el.innerText || '').toString().slice(0, 200);
    } catch {}
    emit({
      action_type: 'type',
      target_text: readText(el),
      target_selector: selectorFor(el),
      typed_text: typed
    });
  }, true);
})();
"""


async def _attach_dom_recording(page, recorder: SessionRecorder) -> None:
    recent_click = {"selector": "", "at": 0.0}
    recent_type = {"value": "", "at": 0.0}

    async def _record_payload(payload: dict) -> None:
        if not isinstance(payload, dict):
            return

        action_type = str(payload.get("action_type", "")).strip().lower()
        if action_type not in {"click", "type"}:
            return

        target_text = str(payload.get("target_text", ""))[:120]
        target_selector = str(payload.get("target_selector", ""))[:140]
        typed_text = str(payload.get("typed_text", ""))[:200] if action_type == "type" else ""

        now = time.time()
        if action_type == "click":
            if target_selector == recent_click["selector"] and (now - float(recent_click["at"])) < 0.25:
                return
            recent_click["selector"] = target_selector
            recent_click["at"] = now
        else:
            if typed_text == recent_type["value"] and (now - float(recent_type["at"])) < 0.25:
                return
            recent_type["value"] = typed_text
            recent_type["at"] = now

        state = await get_current_state(page)
        recorder.record_step(
            state=state,
            action_type=action_type,
            target_text=target_text,
            target_selector=target_selector,
            typed_text=typed_text,
            success=True,
        )

    async def _binding(_source, payload):
        try:
            await _record_payload(payload)
        except Exception as exc:
            print(f"[Recorder] listener error: {exc}")

    await page.expose_binding("__bm_record", _binding)
    await page.add_init_script(_INJECT_RECORDER_JS)


async def _open_context_and_page(pw, args):
    profile_dir = Path(args.user_data_dir).expanduser().resolve() if args.user_data_dir else None

    if profile_dir is not None:
        profile_dir.mkdir(parents=True, exist_ok=True)

        launch_kwargs = {
            "user_data_dir": str(profile_dir),
            "headless": False,
            "ignore_default_args": ["--enable-automation"],
            "args": ["--no-first-run"],
        }
        if args.chrome_exe:
            launch_kwargs["executable_path"] = args.chrome_exe
        elif args.browser == "chrome":
            launch_kwargs["channel"] = "chrome"

        context = await pw.chromium.launch_persistent_context(**launch_kwargs)
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.pages[0] if context.pages else await context.new_page()
        return context, None, page

    launch_kwargs = {
        "headless": False,
        "ignore_default_args": ["--enable-automation"],
        "args": ["--no-first-run"],
    }
    if args.chrome_exe:
        launch_kwargs["executable_path"] = args.chrome_exe
    elif args.browser == "chrome":
        launch_kwargs["channel"] = "chrome"

    browser = await pw.chromium.launch(**launch_kwargs)
    context = await browser.new_context()
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    page = await context.new_page()
    return context, browser, page


def _run_social_training(args) -> None:
  epochs = int(args.epochs)
  if args.resume:
    ckpt_path = Path(str(args.ckpt))
    if ckpt_path.exists():
      try:
        import torch

        ckpt = torch.load(ckpt_path, map_location="cpu")
        current_epoch = int(ckpt.get("epoch", 0))
        # If requested epochs are behind/equal to current, treat the value as an increment.
        if epochs <= current_epoch:
          epochs = current_epoch + epochs
      except Exception:
        pass

    cmd = [
        sys.executable,
        "scripts/train_social_real_only.py",
        "--epochs",
    str(epochs),
        "--batch-size",
        str(int(args.batch_size)),
        "--ckpt",
        str(args.ckpt),
    ]
    if args.resume:
        cmd.append("--resume")

    print("\n[TRAIN] Starting social-only training...")
    print("[TRAIN] cmd: " + " ".join(cmd))
    subprocess.run(cmd, check=False)


async def record(args) -> None:
    recorder = SessionRecorder(goal=args.goal, save_dir=args.save_dir)
    if args.auth_first:
        _run_native_auth_portal(args)

    print("\n" + "=" * 60)
    print("BrowserMind Manual Recorder")
    print(f"Goal       : {args.goal}")
    print(f"Start URL  : {args.url}")
    print(f"Browser    : {args.browser}")
    print(f"Save dir   : {args.save_dir}")
    print("Interact manually in the browser window; close tab/window when done.")
    print("=" * 60 + "\n")

    async with async_playwright() as p:
        context = None
        browser = None
        saved = ""
        try:
            context, browser, page = await _open_context_and_page(p, args)
        except PlaywrightError as exc:
            if args.user_data_dir:
                _cleanup_profile_chrome_processes(args.user_data_dir)
                try:
                    context, browser, page = await _open_context_and_page(p, args)
                except PlaywrightError:
                    pass
                else:
                    exc = None

            if exc is None:
                pass
            elif args.browser == "chrome":
                print(f"[WARN] Chrome channel launch failed ({exc}); falling back to chromium.")
                args.browser = "chromium"
                context, browser, page = await _open_context_and_page(p, args)
            else:
                raise

        await _attach_dom_recording(page, recorder)

        # Initialize Failure Observatory
        from core.observatory import FailureObservatory
        observatory = FailureObservatory()
        
        goal_lower = args.goal.lower()
        workflow_name = "manual_workflow"
        if "lever" in goal_lower:
            workflow_name = "lever"
        elif "greenhouse" in goal_lower:
            workflow_name = "greenhouse"
        elif "workday" in goal_lower:
            workflow_name = "workday"
            
        execution_ctx = {
            "intent": "manual_record",
            "workflow_template": workflow_name,
            "current_step": "manual_interaction",
            "resource_dependencies": [],
            "provider_chain": []
        }
        if getattr(args, "mission_id", None):
            execution_ctx["mission_id"] = args.mission_id
        if getattr(args, "mission_family", None):
            execution_ctx["mission_family"] = args.mission_family
        if getattr(args, "run_number", None) is not None:
            execution_ctx["run_number"] = args.run_number
        # Detect resource dependencies
        deps = []
        if any(k in goal_lower for k in ["resume", "cv", "file"]):
            deps.append("resume")
        if any(k in goal_lower for k in ["otp", "code", "verification"]):
            deps.append("otp")
        if any(k in goal_lower for k in ["email", "gmail"]):
            deps.append("email")
        execution_ctx["resource_dependencies"] = deps
        
        providers = []
        if "otp" in deps or "email" in deps:
            providers.append("email_provider")
        execution_ctx["provider_chain"] = providers

        observatory.start_tracking(
            page, 
            workflow=workflow_name, 
            environment="production",
            execution_context=execution_ctx
        )

        await page.goto(args.url, wait_until="domcontentloaded")
        await page.evaluate(_INJECT_RECORDER_JS)

        try:
            print("\n" + "*" * 60)
            print("  RECORDING ACTIVE.")
            print("  Interact manually in the browser window.")
            print("  When you are finished (e.g. form submitted, error shown, or done):")
            print("  DO NOT close the browser window. Instead, return to this terminal")
            print("  and press [ENTER] to save the recording and capture the final page state.")
            print("*" * 60 + "\n")
            
            # Use run_in_executor to block on input asynchronously
            await asyncio.get_event_loop().run_in_executor(None, input, "  Press [ENTER] when finished...\n")
        except Exception:
            pass
        finally:
            # Prompt the user for outcome details while page is still open
            print("\n" + "=" * 50)
            print("  Execution Outcome Entry")
            print("=" * 50)
            success_input = input("  Did the execution succeed? (y/n) [y]: ").strip().lower()
            success = success_input not in {"n", "no", "f", "false"}
            
            failure_phase = None
            failure_symptom = None
            if not success:
                failure_phase = input("  Failure phase (e.g. auth, fill, submit, upload) [submit]: ").strip() or "submit"
                failure_symptom = input("  Failure symptom / error message: ").strip() or "unknown verification error"
                
            # Stop observatory tracking and dump artifacts (screenshot & DOM taken while page is open!)
            await observatory.stop_tracking(
                success=success,
                failure_phase=failure_phase,
                failure_symptom=failure_symptom,
                active_page=page
            )
            
            recorder.summary()
            saved = recorder.save()
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass
            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    pass

    if args.train_social and saved:
        _run_social_training(args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manual browser recording for training sessions")
    parser.add_argument("--goal", default="social media task", help="session goal")
    parser.add_argument("--url", default="https://www.facebook.com", help="initial URL")
    parser.add_argument("--browser", choices=["chrome", "chromium"], default="chrome")
    parser.add_argument("--auth-first", action="store_true", help="open native Chrome first for manual secure logins")
    parser.add_argument("--auth-url", default="https://accounts.google.com", help="URL to open during native auth step")
    parser.add_argument("--user-data-dir", default=_default_profile_dir(), help="persistent Chrome profile path")
    parser.add_argument("--chrome-exe", default="", help="optional explicit Chrome executable path")
    parser.add_argument("--save-dir", default="training/sessions", help="where to store recorded sessions")

    parser.add_argument("--train-social", action="store_true", help="run social-only BC training after recording")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--ckpt", default="checkpoints/browsermind_social_real_only.pt")
    parser.add_argument("--resume", action="store_true")

    # R2A campaign parameters
    parser.add_argument("--mission-id", default="", help="R2A mission ID")
    parser.add_argument("--mission-family", default="", help="R2A mission family name")
    parser.add_argument("--run-number", type=int, default=1, help="R2A mission run number index")

    cli_args = parser.parse_args()
    asyncio.run(record(cli_args))
