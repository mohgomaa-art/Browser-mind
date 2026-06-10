"""Simple prompt/command parser for the Operator UI."""
from __future__ import annotations

import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Optional, Tuple

from browsermind_ui.core.app_context import AppContext
from browsermind_ui.core.prompt_parse import (
    infer_env_and_url,
    is_browser_intent,
    sanitize_goal,
    split_goal_persona,
)
import browsermind_ui.core.commands as cmd

_UI_PKG = Path(__file__).resolve().parent.parent
ROOT = _UI_PKG.parent


def _find_project_root() -> Path:
    for base in (ROOT, Path.cwd(), Path.cwd().parent):
        if (base / "scripts" / "run_workflow_pilot.py").exists():
            return base
    return ROOT


def _python_exe() -> str:
    root = _find_project_root()
    venv = root / ".venv" / "Scripts" / "python.exe"
    return str(venv) if venv.exists() else sys.executable


def _run_script(rel_script: str, extra_args: list) -> str:
    root = _find_project_root()
    script = root / rel_script
    if not script.exists():
        return f"Not found: {script}"
    py = _python_exe()
    try:
        flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
        subprocess.Popen(
            [py, "-u", str(script), *extra_args],
            cwd=str(root),
            creationflags=flags,
        )
    except Exception as e:
        return f"Failed to start: {e}\nTry: playwright install chromium"
    return "Opening browser — check taskbar / new console window."


def _launch_bat(name: str) -> str:
    root = _find_project_root()
    bat = root / name
    if not bat.exists():
        return f"Not found: {bat}"
    try:
        if os.name == "nt":
            subprocess.Popen(
                ["cmd", "/c", str(bat)],
                cwd=str(root),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            subprocess.Popen([str(bat)], cwd=str(root))
    except Exception as e:
        return f"Failed to start: {e}"
    return f"Started {name}."


def _open_browser(env_key: str, url: str | None = None) -> str:
    args = ["--env", env_key]
    if url:
        args.extend(["--url", url])
    return _run_script("scripts/open_browser.py", args)


def handle_prompt(ctx: AppContext, text: str) -> Tuple[str, Optional[str]]:
    line = (text or "").strip()
    if not line:
        return ("Type a goal or command.", None)

    lower = line.lower()

    if lower in ("help", "?"):
        from browsermind_core.runtime.environment_registry import get_all
        known = ", ".join(e.key for e in get_all())
        return (
            "── Browser commands ──\n"
            "  open huggingface\n"
            "  open linkedin\n"
            "  open github\n"
            "  open https://anysite.com\n"
            "  record huggingface\n"
            "  pilot  (saucedemo smoke test)\n\n"
            f"  Known environments: {known}\n\n"
            "── Task only (no browser) ──\n"
            "  Apply to 50 jobs @ pilot\n\n"
            "── Persona suffix ──\n"
            "  goal text @ persona_name\n"
            "  (space before @, this is NOT an email)\n\n"
            "Do not type passwords here — use the vault.",
            None,
        )

    if lower in ("record", "record start") or lower.startswith("record "):
        env = "facebook" if "facebook" in lower else "saucedemo"
        return (
            _run_script("scripts/run_record.py", ["--env", env, "--persona", "pilot"]),
            "Executions",
        )

    if lower in ("pilot", "run pilot", "workflow"):
        return (_run_script("scripts/run_workflow_pilot.py", []), "Executions")

    if lower == "verify":
        return (_run_script("scripts/verify_p1_workflow.py", []), "Global Ledger")

    if lower in ("train", "train 5000"):
        return (_launch_bat("train_5000.bat"), None)

    if lower.startswith(("open ", "browse ", "go ", "go to ", "navigate ", "visit ", "show me ")):
        rest = line.split(maxsplit=1)[1] if " " in line else ""
        env, url = infer_env_and_url(rest or line)
        if env in ("unknown", "unknown_url") and not url:
            from browsermind_core.runtime.environment_registry import get_all
            known = ", ".join(e.key for e in get_all())
            return (
                f"Unknown site: '{rest}'.\n"
                f"Known: {known}\n"
                "To add: bm environment add --key mysite --url https://mysite.com",
                None,
            )
        return (_open_browser(env, url), "Executions")

    if lower.startswith("start "):
        rest = line[6:].strip()
        task_part, persona = split_goal_persona(rest, "pilot")
        task_name = task_part.replace(" ", "_").lower()[:30]
        cmd.ensure_persona(ctx, persona)
        if cmd.start_execution_command(ctx, task_name, persona):
            return (
                f"Execution started for '{task_name}' (kernel only).\n"
                "To open browser: open facebook",
                "Executions",
            )
        return (f"No task '{task_name}'. Create it first or type: open facebook", "Tasks")

    if is_browser_intent(line):
        goal, persona = split_goal_persona(line)
        safe_goal = sanitize_goal(goal)
        env, url = infer_env_and_url(goal)
        cmd.ensure_persona(ctx, persona)
        cmd.create_task_command(ctx, safe_goal, persona)
        browser_msg = _open_browser(env, url)
        preview = safe_goal if len(safe_goal) <= 80 else safe_goal[:80] + "..."
        return (
            f"{browser_msg}\n\n"
            f"Task saved: {preview}\n"
            "Log in manually. Passwords are not auto-filled.",
            "Executions",
        )

    goal, persona = split_goal_persona(line)
    safe_goal = sanitize_goal(goal)
    cmd.ensure_persona(ctx, persona)
    if cmd.create_task_command(ctx, safe_goal, persona):
        return (
            f"Task saved (no browser opened): {safe_goal}\n"
            "To open Facebook: type  open facebook",
            "Tasks",
        )
    return (f"Could not create task for persona '{persona}'.", "Personas")


def handle_prompt_safe(ctx: AppContext, text: str) -> Tuple[str, Optional[str]]:
    try:
        return handle_prompt(ctx, text)
    except Exception:
        return (f"Error:\n{traceback.format_exc()}", None)
