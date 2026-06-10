"""
Simple BrowserMind Live Model GUI.

Features:
- Pick a checkpoint file
- Enter a chat-style prompt/goal and max steps
- Run model live in headful browser
- Use the same task decomposition + execution flow as Studio API
- Watch predicted and executed actions stream in real time
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import shutil
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Optional, TypedDict, cast

import tkinter as tk
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

PROFILE_LAUNCH_TIMEOUT_MS = 25000
STEALTH_CHROME_ARGS = [
    "--disable-blink-features=AutomationControlled",
]
STEALTH_IGNORE_DEFAULT_ARGS = ["--enable-automation"]
STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
"""


def _default_ckpt() -> str:
    candidates = [
        ROOT / "checkpoints" / "browsermind_super_complex_10h.pt",
        ROOT / "checkpoints" / "browsermind_no_mercy_24h.pt",
        ROOT / "checkpoints" / "best_ever.pt",
        ROOT / "checkpoints" / "best.pt",
        ROOT / "browsermind_policy_v2.pt",
        ROOT / "browsermind_policy.pt",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return str(ROOT / "checkpoints" / "best.pt")


def _default_chrome_user_data_dir() -> str:
    local = os.getenv("LOCALAPPDATA", "").strip()
    if local:
        p = Path(local) / "Google" / "Chrome" / "User Data"
        if p.exists():
            return str(p)
    return ""


def _default_session_state_path() -> str:
    return str(ROOT / "sessions" / "live_model_state.json")


def _normalized_path(path_str: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path_str)))


def _is_default_chrome_user_data_dir(path_str: str) -> bool:
    default_dir = _default_chrome_user_data_dir()
    if not default_dir or not path_str:
        return False
    return _normalized_path(default_dir) == _normalized_path(path_str)


def _clone_chrome_profile_for_automation(user_data_dir: str, profile_dir: str) -> Path:
    """
    Chrome blocks remote-debugging on the default profile directory.
    Create a temporary clone of the requested profile and launch against it.
    """
    src_root = Path(user_data_dir)
    src_profile = src_root / profile_dir
    if not src_profile.exists():
        raise FileNotFoundError(f"Profile directory does not exist: {src_profile}")

    run_id = int(time.time())
    temp_root = Path(tempfile.gettempdir()) / "browsermind_chrome_profile" / f"run_{run_id}"
    dst_root = temp_root / "User Data"
    dst_profile = dst_root / profile_dir
    dst_root.mkdir(parents=True, exist_ok=True)

    local_state = src_root / "Local State"
    if local_state.exists():
        shutil.copy2(local_state, dst_root / "Local State")

    ignore = shutil.ignore_patterns(
        "Cache",
        "Code Cache",
        "GPUCache",
        "ShaderCache",
        "GrShaderCache",
        "DawnCache",
        "Crashpad",
        "Service Worker",
        "OptimizationHints",
    )
    shutil.copytree(src_profile, dst_profile, dirs_exist_ok=True, ignore=ignore)
    return dst_root


async def _apply_stealth_context(context: Any) -> None:
    try:
        await context.add_init_script(STEALTH_INIT_SCRIPT)
    except Exception:
        pass


async def _is_google_secure_signin_block(page: Any) -> bool:
    try:
        url_l = str(getattr(page, "url", "") or "").lower()
        if "accounts.google.com" not in url_l:
            return False
        body_text = await page.locator("body").inner_text(timeout=1200)
        tl = str(body_text or "").lower()
        return (
            "couldn't sign you in" in tl
            or "couldn't sign you in" in tl
            or "may not be secure" in tl
            or "this browser or app may not be secure" in tl
        )
    except Exception:
        return False


class RunConfig(TypedDict):
    ckpt: str
    goal: str
    max_steps: int
    use_profile: bool
    user_data_dir: str
    profile_dir: str
    persist_session: bool
    session_state_path: str
    upload_file_path: str


class LiveModelGui:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("BrowserMind Chat UI")
        self.root.geometry("1000x700")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.log_queue: queue.SimpleQueue[str] = queue.SimpleQueue()
        self.next_cfg_queue: queue.Queue[Optional[RunConfig]] = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.running = False

        self._build_ui()
        self._pump_logs()

    def _build_ui(self) -> None:
        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        # Row 0: checkpoint
        ttk.Label(frm, text="Checkpoint").grid(row=0, column=0, sticky="w")
        self.ckpt_var = tk.StringVar(value=_default_ckpt())
        ttk.Entry(frm, textvariable=self.ckpt_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(frm, text="Browse", command=self._browse_ckpt).grid(row=0, column=2, sticky="ew")

        # Row 1: Chat prompt
        ttk.Label(frm, text="Chat Prompt").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.goal_var = tk.StringVar(value="Open python.org and find asyncio documentation")
        ttk.Entry(frm, textvariable=self.goal_var).grid(row=1, column=1, columnspan=2, sticky="ew", padx=6, pady=(8, 0))

        # Row 2: steps and controls
        ttk.Label(frm, text="Max Steps").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.max_steps_var = tk.StringVar(value="10")
        ttk.Entry(frm, textvariable=self.max_steps_var, width=8).grid(row=2, column=1, sticky="w", padx=6, pady=(8, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=2, column=2, sticky="e", pady=(8, 0))
        self.run_btn = ttk.Button(btns, text="Send Prompt", command=self._start_run)
        self.run_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.stop_btn = ttk.Button(btns, text="Stop", command=self._stop_run, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT)

        # Row 3: Chrome profile reuse
        ttk.Label(frm, text="Chrome Profile").grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.use_profile_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frm,
            text="Use existing logged-in Chrome profile",
            variable=self.use_profile_var,
        ).grid(row=3, column=1, columnspan=2, sticky="w", padx=6, pady=(8, 0))

        # Row 4: Chrome user data dir
        ttk.Label(frm, text="User Data Dir").grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.user_data_dir_var = tk.StringVar(value=_default_chrome_user_data_dir())
        ttk.Entry(frm, textvariable=self.user_data_dir_var).grid(row=4, column=1, sticky="ew", padx=6, pady=(8, 0))
        ttk.Button(frm, text="Browse", command=self._browse_user_data_dir).grid(row=4, column=2, sticky="ew", pady=(8, 0))

        # Row 5: profile directory name
        ttk.Label(frm, text="Profile Dir").grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.profile_dir_var = tk.StringVar(value="Default")
        ttk.Entry(frm, textvariable=self.profile_dir_var).grid(row=5, column=1, columnspan=2, sticky="ew", padx=6, pady=(8, 0))

        # Row 6: upload media/file path
        ttk.Label(frm, text="Upload File").grid(row=6, column=0, sticky="w", pady=(8, 0))
        self.upload_file_var = tk.StringVar(value="")
        ttk.Entry(frm, textvariable=self.upload_file_var).grid(row=6, column=1, sticky="ew", padx=6, pady=(8, 0))
        ttk.Button(frm, text="Browse", command=self._browse_upload_file).grid(row=6, column=2, sticky="ew", pady=(8, 0))

        # Row 7: cookie/session persistence
        ttk.Label(frm, text="Session State").grid(row=7, column=0, sticky="w", pady=(8, 0))
        self.persist_session_var = tk.BooleanVar(value=True)
        state_controls = ttk.Frame(frm)
        state_controls.grid(row=7, column=1, columnspan=2, sticky="ew", padx=6, pady=(8, 0))
        ttk.Checkbutton(
            state_controls,
            text="Save/load cookies and local session state",
            variable=self.persist_session_var,
        ).pack(side=tk.LEFT)

        ttk.Label(frm, text="State File").grid(row=8, column=0, sticky="w", pady=(8, 0))
        self.session_state_var = tk.StringVar(value=_default_session_state_path())
        ttk.Entry(frm, textvariable=self.session_state_var).grid(row=8, column=1, sticky="ew", padx=6, pady=(8, 0))
        ttk.Button(frm, text="Browse", command=self._browse_session_state_file).grid(row=8, column=2, sticky="ew", pady=(8, 0))

        # Row 9: status
        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(frm, textvariable=self.status_var).grid(row=9, column=0, columnspan=3, sticky="w", pady=(8, 0))

        # Row 10: logs
        self.log = ScrolledText(frm, wrap=tk.WORD, height=30)
        self.log.grid(row=10, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        self.log.configure(font=("Consolas", 10))

        frm.columnconfigure(1, weight=1)
        frm.columnconfigure(2, weight=0)
        frm.rowconfigure(10, weight=1)

        self._append_log("Ready. Type a prompt and click 'Send Prompt'. No start URL is required.")

    def _browse_ckpt(self) -> None:
        p = filedialog.askopenfilename(
            title="Select checkpoint",
            filetypes=[("PyTorch checkpoint", "*.pt"), ("All files", "*.*")],
            initialdir=str(ROOT / "checkpoints"),
        )
        if p:
            self.ckpt_var.set(p)

    def _browse_user_data_dir(self) -> None:
        p = filedialog.askdirectory(
            title="Select Chrome User Data directory",
            initialdir=self.user_data_dir_var.get().strip() or str(Path.home()),
        )
        if p:
            self.user_data_dir_var.set(p)

    def _browse_upload_file(self) -> None:
        p = filedialog.askopenfilename(
            title="Select file/media to upload",
            filetypes=[("All files", "*.*")],
            initialdir=str(Path.home()),
        )
        if p:
            self.upload_file_var.set(p)

    def _browse_session_state_file(self) -> None:
        p = filedialog.asksaveasfilename(
            title="Select session state file",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            initialdir=str(ROOT / "sessions"),
            initialfile=Path(self.session_state_var.get() or _default_session_state_path()).name,
        )
        if p:
            self.session_state_var.set(p)

    def _append_log(self, msg: str) -> None:
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)

    def _enqueue_log(self, msg: str) -> None:
        self.log_queue.put(msg)

    def _pump_logs(self) -> None:
        try:
            while True:
                msg = self.log_queue.get_nowait()
                if msg == "__RUN_DONE__":
                    self.running = False
                    self.run_btn.config(state=tk.NORMAL)
                    self.stop_btn.config(state=tk.DISABLED)
                    self.status_var.set("Idle")
                    continue
                self._append_log(msg)
        except queue.Empty:
            pass
        self.root.after(100, self._pump_logs)

    def _on_close(self) -> None:
        self.stop_event.set()
        try:
            self.next_cfg_queue.put_nowait(None)
        except Exception:
            pass
        self.root.destroy()

    def _stop_run(self) -> None:
        if self.running:
            self.stop_event.set()
            self._append_log("Stop requested. Waiting for current step to finish...")

    def _start_run(self) -> None:
        if self.running:
            return

        ckpt = self.ckpt_var.get().strip()
        goal = self.goal_var.get().strip()
        use_profile = bool(self.use_profile_var.get())
        user_data_dir = self.user_data_dir_var.get().strip()
        profile_dir = self.profile_dir_var.get().strip() or "Default"
        upload_file_path = self.upload_file_var.get().strip()
        persist_session = bool(self.persist_session_var.get())
        session_state_path = self.session_state_var.get().strip()

        if not ckpt:
            self._append_log("[ERROR] Checkpoint path is required.")
            return
        if not Path(ckpt).exists():
            self._append_log(f"[ERROR] Checkpoint not found: {ckpt}")
            return
        if not goal:
            self._append_log("[ERROR] Prompt is required.")
            return
        if use_profile and not user_data_dir:
            self._append_log("[ERROR] User Data Dir is required when profile reuse is enabled.")
            return
        if use_profile and not Path(user_data_dir).exists():
            self._append_log(f"[ERROR] User Data Dir not found: {user_data_dir}")
            return
        if upload_file_path and not Path(upload_file_path).exists():
            self._append_log(f"[ERROR] Upload file not found: {upload_file_path}")
            return
        if persist_session and not session_state_path:
            self._append_log("[ERROR] State File path is required when session persistence is enabled.")
            return

        try:
            max_steps = int(self.max_steps_var.get().strip())
        except Exception:
            self._append_log("[ERROR] Max Steps must be an integer.")
            return

        self.running = True
        self.stop_event.clear()
        self.run_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.status_var.set("Running...")

        cfg: RunConfig = {
            "ckpt": ckpt,
            "goal": goal,
            "max_steps": max_steps,
            "use_profile": use_profile,
            "user_data_dir": user_data_dir,
            "profile_dir": profile_dir,
            "persist_session": persist_session,
            "session_state_path": session_state_path,
            "upload_file_path": upload_file_path,
        }

        if self.worker is None or not self.worker.is_alive():
            self.worker = threading.Thread(target=self._run_worker, daemon=True)
            self.worker.start()
        self.next_cfg_queue.put(cfg)

    def _run_worker(self) -> None:
        try:
            asyncio.run(self._run_live())
        except Exception:
            self._enqueue_log("[FATAL] Unhandled exception in worker:")
            self._enqueue_log(traceback.format_exc())
        finally:
            self._enqueue_log("__RUN_DONE__")

    async def _run_live(self) -> None:
        import torch
        from playwright.async_api import async_playwright

        from core.executor import ActionExecutor
        from core.privacy import redact_sensitive_text, sanitize_goal_for_storage
        from core.task_decomposer import TaskDecomposer
        from model.agent_policy import AgentPolicy
        decomposer = TaskDecomposer()
        policy: Any = None
        policy_ckpt = ""
        device = "cuda" if torch.cuda.is_available() else "cpu"

        async with async_playwright() as pw:
            browser: Any = None
            context: Any = None
            page: Any = None
            cloned_user_data_dir: Path | None = None
            context_is_persistent = False
            active_launch_sig: tuple[Any, ...] | None = None

            async def _close_active_session() -> None:
                nonlocal browser, context, page, cloned_user_data_dir, context_is_persistent, active_launch_sig

                if context is not None:
                    try:
                        await context.close()
                    except Exception:
                        pass
                    context = None

                if browser is not None and not context_is_persistent:
                    try:
                        await browser.close()
                    except Exception:
                        pass
                    browser = None

                page = None
                context_is_persistent = False
                active_launch_sig = None

                if cloned_user_data_dir is not None:
                    try:
                        shutil.rmtree(cloned_user_data_dir.parent, ignore_errors=True)
                        self._enqueue_log("[INFO] Cleaned up temporary cloned Chrome profile.")
                    except Exception:
                        pass
                    cloned_user_data_dir = None

            current_cfg = await asyncio.to_thread(self.next_cfg_queue.get)
            if current_cfg is None:
                return

            while current_cfg is not None:
                cfg = current_cfg
                ckpt = cfg["ckpt"]
                goal = cfg["goal"]
                max_steps = cfg["max_steps"]
                use_profile = cfg["use_profile"]
                user_data_dir = cfg["user_data_dir"].strip()
                profile_dir = cfg["profile_dir"].strip() or "Default"
                persist_session = bool(cfg["persist_session"])
                session_state_path = cfg["session_state_path"].strip()
                upload_file_path = cfg["upload_file_path"].strip()
                session_state_file = Path(session_state_path) if session_state_path else Path(_default_session_state_path())
                safe_goal = sanitize_goal_for_storage(goal)

                self._enqueue_log("=" * 70)
                self._enqueue_log("Live model run started")
                self._enqueue_log(f"User> {safe_goal}")
                self._enqueue_log(f"Checkpoint: {ckpt}")
                self._enqueue_log(f"Device: {device}")
                if use_profile:
                    self._enqueue_log(f"Chrome profile reuse: ON ({user_data_dir} | {profile_dir})")
                    profile_path = Path(user_data_dir) / profile_dir
                    if not profile_path.exists():
                        self._enqueue_log(
                            f"[WARN] Profile directory not found: {profile_path}. "
                            "If your account is in another profile, set Profile Dir correctly (e.g., Profile 1)."
                        )
                    self._enqueue_log("If launch hangs, close all Chrome windows first (profile lock).")
                else:
                    self._enqueue_log("Chrome profile reuse: OFF (fresh browser session)")
                if persist_session:
                    self._enqueue_log(f"Session persistence: ON ({session_state_file})")
                else:
                    self._enqueue_log("Session persistence: OFF")
                if upload_file_path:
                    self._enqueue_log(f"Upload file preset: {upload_file_path}")

                if policy is None or policy_ckpt != ckpt:
                    self._enqueue_log("Loading policy...")
                    policy = AgentPolicy.load(ckpt, map_location=device).to(torch.device(device))
                    policy_ckpt = ckpt
                else:
                    self._enqueue_log("Reusing loaded policy.")

                launch_sig = (
                    bool(use_profile),
                    _normalized_path(user_data_dir) if use_profile and user_data_dir else "",
                    profile_dir,
                )

                if context is None or active_launch_sig != launch_sig:
                    if context is not None or browser is not None:
                        await _close_active_session()

                    if use_profile:
                        launch_user_data_dir = user_data_dir

                        if _is_default_chrome_user_data_dir(user_data_dir):
                            self._enqueue_log(
                                "[INFO] Default Chrome profile detected; cloning profile to a temporary automation directory..."
                            )
                            try:
                                cloned_user_data_dir = _clone_chrome_profile_for_automation(user_data_dir, profile_dir)
                                launch_user_data_dir = str(cloned_user_data_dir)
                                self._enqueue_log(f"[INFO] Using cloned profile dir: {launch_user_data_dir}")
                            except Exception as e:
                                self._enqueue_log(
                                    f"[WARN] Failed to clone profile for automation: {redact_sensitive_text(str(e))}"
                                )
                                self._enqueue_log(
                                    "[WARN] Falling back to original profile path; Chrome may reject automation on default dir."
                                )

                        profile_args = [f"--profile-directory={profile_dir}"] if profile_dir else []
                        launch_args = profile_args + STEALTH_CHROME_ARGS

                        try:
                            self._enqueue_log("Launching Chrome with persistent profile...")
                            context = await pw.chromium.launch_persistent_context(
                                user_data_dir=launch_user_data_dir,
                                channel="chrome",
                                headless=False,
                                args=launch_args,
                                ignore_default_args=STEALTH_IGNORE_DEFAULT_ARGS,
                                ignore_https_errors=True,
                                timeout=PROFILE_LAUNCH_TIMEOUT_MS,
                            )
                            await _apply_stealth_context(context)
                            context_is_persistent = True
                            self._enqueue_log("Google Chrome launched with existing profile (channel=chrome).")
                        except Exception as e:
                            self._enqueue_log(
                                "[WARN] Chrome profile launch failed. "
                                "Close all Chrome windows and retry if profile is locked."
                            )
                            self._enqueue_log(
                                f"[WARN] Profile launch detail: {redact_sensitive_text(str(e))}"
                            )

                        if context is None:
                            chrome_candidates = [
                                Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                                Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
                            ]
                            for chrome_path in chrome_candidates:
                                if not chrome_path.exists():
                                    continue
                                try:
                                    self._enqueue_log(
                                        f"Retrying persistent profile launch via executable: {chrome_path}"
                                    )
                                    context = await pw.chromium.launch_persistent_context(
                                        user_data_dir=launch_user_data_dir,
                                        executable_path=str(chrome_path),
                                        headless=False,
                                        args=launch_args,
                                        ignore_default_args=STEALTH_IGNORE_DEFAULT_ARGS,
                                        ignore_https_errors=True,
                                        timeout=PROFILE_LAUNCH_TIMEOUT_MS,
                                    )
                                    await _apply_stealth_context(context)
                                    context_is_persistent = True
                                    self._enqueue_log(f"Google Chrome launched with existing profile ({chrome_path}).")
                                    break
                                except Exception as e:
                                    self._enqueue_log(
                                        f"[WARN] Profile launch failed ({chrome_path}): "
                                        f"{redact_sensitive_text(str(e))}"
                                    )

                    if use_profile and context is None:
                        self._enqueue_log(
                            "[INFO] Falling back to non-profile Chrome session (profile reuse unavailable for this run)."
                        )

                    if context is None:
                        try:
                            browser = await pw.chromium.launch(
                                channel="chrome",
                                headless=False,
                                args=STEALTH_CHROME_ARGS,
                                ignore_default_args=STEALTH_IGNORE_DEFAULT_ARGS,
                            )
                            self._enqueue_log("Google Chrome launched (channel=chrome).")
                        except Exception as e:
                            self._enqueue_log(
                                f"[WARN] Chrome channel launch failed: {redact_sensitive_text(str(e))}"
                            )

                    if context is None and browser is None:
                        chrome_candidates = [
                            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
                        ]
                        for chrome_path in chrome_candidates:
                            if not chrome_path.exists():
                                continue
                            try:
                                browser = await pw.chromium.launch(
                                    executable_path=str(chrome_path),
                                    headless=False,
                                    args=STEALTH_CHROME_ARGS,
                                    ignore_default_args=STEALTH_IGNORE_DEFAULT_ARGS,
                                )
                                self._enqueue_log(f"Google Chrome launched ({chrome_path}).")
                                break
                            except Exception as e:
                                self._enqueue_log(
                                    f"[WARN] Chrome executable launch failed ({chrome_path}): "
                                    f"{redact_sensitive_text(str(e))}"
                                )

                    if context is None and browser is None:
                        self._enqueue_log(
                            "[FATAL] Could not launch Google Chrome. If profile reuse is ON, close Chrome and retry."
                        )
                        self._enqueue_log("Run complete.")
                        self._enqueue_log("=" * 70)
                        self._enqueue_log("Waiting for next instructions...")
                        self._enqueue_log("__RUN_DONE__")
                        current_cfg = await asyncio.to_thread(self.next_cfg_queue.get)
                        self.stop_event.clear()
                        continue

                    if context is None:
                        if browser is None:
                            self._enqueue_log("[FATAL] Browser launch failed unexpectedly.")
                            self._enqueue_log("Run complete.")
                            self._enqueue_log("=" * 70)
                            self._enqueue_log("Waiting for next instructions...")
                            self._enqueue_log("__RUN_DONE__")
                            current_cfg = await asyncio.to_thread(self.next_cfg_queue.get)
                            self.stop_event.clear()
                            continue
                        context = await cast(Any, browser).new_context(ignore_https_errors=True)
                        await _apply_stealth_context(context)

                    if persist_session and session_state_file.exists():
                        try:
                            with open(session_state_file, "r", encoding="utf-8") as fh:
                                state_any: Any = json.load(fh)
                            if isinstance(state_any, dict):
                                state_dict = cast(dict[str, Any], state_any)
                                cookies_any: Any = state_dict.get("cookies", [])
                            else:
                                cookies_any = []
                            if isinstance(cookies_any, list) and cookies_any:
                                cookies = cast(list[dict[str, Any]], cookies_any)
                                await context.add_cookies(cookies)
                                self._enqueue_log(
                                    f"[INFO] Loaded {len(cookies)} cookies from session state."
                                )
                        except Exception as e:
                            self._enqueue_log(
                                f"[WARN] Failed to load session state: {redact_sensitive_text(str(e))}"
                            )

                    active_launch_sig = launch_sig
                else:
                    self._enqueue_log("[INFO] Reusing existing browser session.")

                if context is None:
                    self._enqueue_log("[FATAL] Browser context unavailable.")
                    self._enqueue_log("Run complete.")
                    self._enqueue_log("=" * 70)
                    self._enqueue_log("Waiting for next instructions...")
                    self._enqueue_log("__RUN_DONE__")
                    current_cfg = await asyncio.to_thread(self.next_cfg_queue.get)
                    self.stop_event.clear()
                    continue

                if page is None or page.is_closed():
                    page = await cast(Any, context).new_page()
                page_obj: Any = page
                await page_obj.bring_to_front()
                executor: Any = ActionExecutor(page=page_obj, policy_v2=policy)

                self._enqueue_log("Browser session ready in headful mode.")

                task = decomposer.decompose(
                    "search_interactive",
                    "Standard User",
                    goal,
                    upload_file_path=upload_file_path,
                )
                if max_steps > 0:
                    task.actions = task.actions[:max_steps]

                self._enqueue_log(
                    f"Task decomposed into {len(task.actions)} steps (intent={task.intent})."
                )

                start_idx = 0
                if task.actions:
                    first_action = task.actions[0]
                    first_type = str(first_action.action_type.value)
                    first_target = str(first_action.target or "")
                    if first_type == "open_url" and first_target.startswith(("http://", "https://")):
                        self._enqueue_log(
                            f"[Boot] Navigating to start URL: {redact_sensitive_text(first_target)}"
                        )
                        try:
                            await page_obj.goto(first_target, wait_until="domcontentloaded", timeout=30000)
                            self._enqueue_log(f"[Boot] Opened: {page_obj.url}")
                            start_idx = 1
                        except Exception as e:
                            self._enqueue_log(
                                f"[Boot] start URL navigation failed: {redact_sensitive_text(str(e))}"
                            )

                run_actions = task.actions[start_idx:]
                total_steps = len(run_actions)
                for idx, action in enumerate(run_actions, start=1):
                    if self.stop_event.is_set():
                        self._enqueue_log("Stop flag detected. Exiting run.")
                        break

                    if await _is_google_secure_signin_block(page_obj):
                        self._enqueue_log(
                            "[AUTH-BLOCK] Google blocked automated sign-in: 'This browser or app may not be secure'."
                        )
                        self._enqueue_log(
                            "[AUTH-BLOCK] Use an already signed-in session/profile and skip login prompts when possible."
                        )
                        self._enqueue_log(
                            "[AUTH-BLOCK] If needed, sign in manually in regular Chrome first, then reuse session state here."
                        )
                        break

                    step_tag = f"[Step {idx}/{total_steps} | plan#{action.step}]"
                    target = redact_sensitive_text(str(action.target or ""))
                    self._enqueue_log(
                        f"{step_tag} plan action={action.action_type.value} target={target}"
                    )

                    try:
                        res = await executor.execute_atomic_action(action, goal=goal)
                    except Exception as e:
                        self._enqueue_log(f"{step_tag} execute exception: {redact_sensitive_text(str(e))}")
                        break

                    if bool(getattr(res, "success", False)):
                        self._enqueue_log(f"{step_tag} execute OK")
                        data: Any = getattr(res, "data", None)
                        if isinstance(data, list) and data:
                            preview_data = cast(list[Any], data)
                            preview = redact_sensitive_text(str(preview_data))[:220]
                            self._enqueue_log(f"{step_tag} extract preview: {preview}")
                    else:
                        err = redact_sensitive_text(str(getattr(res, "error", "")))
                        self._enqueue_log(f"{step_tag} execute FAIL: {err}")
                        if bool(getattr(action, "critical", True)):
                            self._enqueue_log(f"{step_tag} critical failure -> stopping")
                            break

                    await asyncio.sleep(0.25)

                self._enqueue_log(f"Final URL: {page_obj.url}")
                if await _is_google_secure_signin_block(page_obj):
                    self._enqueue_log(
                        "[AUTH-BLOCK] Current page is Google secure-auth block. Login cannot proceed in this automated context."
                    )
                await asyncio.sleep(1)

                if persist_session and context is not None:
                    try:
                        session_state_file.parent.mkdir(parents=True, exist_ok=True)
                        await context.storage_state(path=str(session_state_file))
                        self._enqueue_log(f"[INFO] Saved session state to: {session_state_file}")
                    except Exception as e:
                        self._enqueue_log(
                            f"[WARN] Failed to save session state: {redact_sensitive_text(str(e))}"
                        )

                self._enqueue_log("Run complete.")
                self._enqueue_log("=" * 70)
                self._enqueue_log("Waiting for next instructions...")
                self._enqueue_log("__RUN_DONE__")

                current_cfg = await asyncio.to_thread(self.next_cfg_queue.get)
                self.stop_event.clear()

            await _close_active_session()


def main() -> None:
    root = tk.Tk()
    LiveModelGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
