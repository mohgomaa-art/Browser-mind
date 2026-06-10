"""
MissionWorker — async loop that drains MissionQueue site-by-site.

Enhanced with:
  - Stuck-worker detection (#87): warns if no step fires in > threshold seconds
  - Intervention timeout auto-skip (#82): checks paused entries at loop start
  - Structured health metrics (#33): emits metrics dict every N sites
  - Budget auto-adaptation (#30): expands budget for sites with many affordances
  - Worker pause/resume (#31): pause() suspends without marking entry failed
  - Site availability backoff (#28): skips entries whose backoff_until hasn't elapsed
  - Orphan browser cleanup (#34): atexit / try-finally guarantees browser close
"""
from __future__ import annotations

import asyncio
import atexit
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from browsermind_core.mission.mission_queue import MissionQueue, MissionEntry

_BOT_WALL_KEYWORDS = (
    "bot_detected", "cloudflare", "captcha", "ddos", "access_denied",
    "may not be secure", "browser or app", "try using a different browser",
    "automated", "unusual activity", "verify you are human",
    "just a moment", "ray id", "ddos-guard", "forbidden",
    "prove you are human", "not a robot", "security check",
    # French / German / Spanish / Portuguese bot walls
    "vérification requise", "bitte bestätigen", "verificación requerida",
    "verificação necessária",
    # Arabic Google / general
    "قد يكون هذا المتصفّح",
    "غير آمن",
)
_AUTH_WALL_KEYWORDS = ("auth_required", "login_required", "identity_expired")

# How long without a successful step before we warn "worker may be stuck" (#87)
_STUCK_THRESHOLD_SECONDS = 300  # 5 minutes


class WorkerMetrics:
    """Lightweight live metrics tracker (#33)."""

    def __init__(self) -> None:
        self.sites_done = 0
        self.sites_paused = 0
        self.sites_failed = 0
        self.total_steps = 0
        self.total_hypotheses = 0
        self.total_affordances_executed = 0
        self.total_verified_effects = 0
        self.total_duration_s = 0.0
        self.started_at = time.time()
        self._last_step_ts = time.time()

    def record_step(self) -> None:
        self._last_step_ts = time.time()

    def seconds_since_last_step(self) -> float:
        return time.time() - self._last_step_ts

    def steps_per_second(self) -> float:
        elapsed = time.time() - self.started_at
        return self.total_steps / elapsed if elapsed > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "sites_done":              self.sites_done,
            "sites_paused":            self.sites_paused,
            "sites_failed":            self.sites_failed,
            "total_steps":             self.total_steps,
            "total_hyps":              self.total_hypotheses,
            "total_affordances_exec":  self.total_affordances_executed,
            "total_verified_effects":  self.total_verified_effects,
            "steps_per_sec":           round(self.steps_per_second(), 3),
            "elapsed_h":               round((time.time() - self.started_at) / 3600, 2),
            "stuck_s":                 round(self.seconds_since_last_step(), 1),
        }


class MissionWorker:
    """
    Drains a MissionQueue by running ExplorationHarness on each pending site.
    """

    def __init__(
        self,
        queue: MissionQueue,
        session,
        headless: bool = False,
        store_dir: Optional[Path] = None,
        on_site_start: Optional[Callable[[MissionEntry], None]] = None,
        on_site_done: Optional[Callable[[MissionEntry], None]] = None,
        inter_site_delay: float = 3.0,
    ) -> None:
        self._queue = queue
        self._session = session
        self._headless = headless
        self._store_dir = store_dir or Path(session.store_dir)
        self._on_site_start = on_site_start
        self._on_site_done = on_site_done
        self._inter_site_delay = inter_site_delay
        self._stop_flag = False
        self._pause_flag = False
        self._metrics = WorkerMetrics()
        self._active_harness = None  # track for orphan cleanup (#34)

        atexit.register(self._atexit_cleanup)

    def stop(self) -> None:
        self._stop_flag = True

    def pause(self) -> None:
        """Suspend worker between sites without failing current entry (#31)."""
        self._pause_flag = True
        print("  [MissionWorker] Pausing after current site completes…")

    def resume_worker(self) -> None:
        """Resume a paused worker (#31)."""
        self._pause_flag = False
        print("  [MissionWorker] Resuming.")

    def metrics(self) -> dict:
        return self._metrics.to_dict()

    def _atexit_cleanup(self) -> None:
        """Best-effort cleanup of active harness on process exit (#34)."""
        if self._active_harness is not None:
            try:
                import asyncio as _a
                loop = _a.get_event_loop()
                if not loop.is_closed():
                    loop.run_until_complete(
                        getattr(self._active_harness, "cleanup", lambda: asyncio.sleep(0))()
                    )
            except Exception:
                pass

    # ── Main loop ────────────────────────────────────────────────────────

    async def run(
        self,
        hours: Optional[float] = None,
        max_sites: Optional[int] = None,
    ) -> dict:
        deadline = time.time() + hours * 3600 if hours else None
        sites_done = 0

        # Recover from previous crash
        recovered = self._queue.reset_running()
        if recovered:
            print(f"  [MissionWorker] Recovered {recovered} stale 'running' entries → 'pending'")

        # Auto-skip expired paused entries (#82)
        skipped = self._queue.auto_skip_expired_pauses()
        if skipped:
            print(f"  [MissionWorker] Auto-skipped {len(skipped)} expired paused entries: {skipped}")

        while not self._stop_flag:
            # Time budget check
            if deadline and time.time() >= deadline:
                print(f"  [MissionWorker] Time budget ({hours}h) exhausted.")
                break

            # Site count limit
            if max_sites is not None and sites_done >= max_sites:
                print(f"  [MissionWorker] Reached max_sites={max_sites}.")
                break

            # Pause flag
            if self._pause_flag:
                print("  [MissionWorker] Paused. Waiting for resume_worker()…")
                await asyncio.sleep(5)
                continue

            # Stuck detection (#87)
            stuck_s = self._metrics.seconds_since_last_step()
            if sites_done > 0 and stuck_s > _STUCK_THRESHOLD_SECONDS:
                print(
                    f"  [MissionWorker] WARNING: No activity for {stuck_s:.0f}s — worker may be stuck!"
                )

            entry = self._queue.next_pending()
            if entry is None:
                print("  [MissionWorker] Queue empty — all sites processed.")
                break

            # Mark running
            self._queue.update(entry.id, status="running", last_run_ts=time.time())
            if self._on_site_start:
                try:
                    self._on_site_start(entry)
                except Exception:
                    pass

            _print_site_header(entry)

            # Budget auto-adaptation (#30): expand budget for complex sites
            adapted_budget = self._adapt_budget(entry)
            if adapted_budget != entry.budget:
                print(f"  [MissionWorker] Budget adapted: {entry.budget} → {adapted_budget}")

            try:
                result = await self._run_site(entry, budget=adapted_budget)
            except Exception as exc:
                result = {
                    "status": "failed", "error": str(exc),
                    "steps": 0, "hypotheses": 0, "experiences": [],
                    "affordances_executed": 0, "verified_effects": 0,
                    "duration": 0.0, "quality_score": 0.0,
                }

            sites_done += 1
            new_status = result.get("status", "done")

            # Update metrics (#33)
            self._metrics.sites_done += 1
            if new_status == "paused":
                self._metrics.sites_paused += 1
            elif new_status == "failed":
                self._metrics.sites_failed += 1
            self._metrics.total_steps += result.get("steps", 0) or 0
            self._metrics.total_hypotheses += result.get("hypotheses", 0) or 0
            self._metrics.total_affordances_executed += result.get("affordances_executed", 0) or 0
            self._metrics.total_verified_effects += result.get("verified_effects", 0) or 0
            self._metrics.total_duration_s += result.get("duration", 0.0) or 0.0
            self._metrics.record_step()

            # Record full run history (#29)
            self._queue.record_run(
                entry.id,
                status=new_status,
                steps=result.get("steps", 0) or 0,
                hypotheses=result.get("hypotheses", 0) or 0,
                duration=result.get("duration", 0.0) or 0.0,
                error=result.get("error"),
                quality_score=result.get("quality_score", 0.0) or 0.0,
            )
            self._queue.update(
                entry.id,
                status=new_status,
                attempts=entry.attempts + 1,
                last_error=result.get("error"),
                last_experiences=result.get("experiences"),
            )

            _print_site_result(entry, result, new_status)

            # Re-queue on transient failure if retries remain
            if new_status == "failed" and entry.attempts < entry.max_retries:
                self._queue.update(entry.id, status="pending")
                print(
                    f"  [Mission] RETRY   {entry.site_key}"
                    f" (attempt {entry.attempts + 1}/{entry.max_retries})"
                )

            if self._on_site_done:
                try:
                    self._on_site_done(entry)
                except Exception:
                    pass

            # Emit metrics every 5 sites
            if sites_done % 5 == 0:
                m = self._metrics.to_dict()
                print(
                    f"  [MissionWorker] Metrics: done={m['sites_done']}"
                    f" steps={m['total_steps']} hyps={m['total_hyps']}"
                    f" aff_exec={m['total_affordances_exec']}"
                    f" vfx={m['total_verified_effects']}"
                    f" rate={m['steps_per_sec']:.2f}/s"
                    f" elapsed={m['elapsed_h']:.2f}h"
                )

            await asyncio.sleep(self._inter_site_delay)

        counts = self._queue.counts()
        summary = {
            "sites_done":              sites_done,
            "total_steps":             self._metrics.total_steps,
            "total_hypotheses":        self._metrics.total_hypotheses,
            "total_affordances_exec":  self._metrics.total_affordances_executed,
            "total_verified_effects":  self._metrics.total_verified_effects,
            "queue_pending":     counts.get("pending", 0),
            "queue_done":        counts.get("done", 0),
            "queue_failed":      counts.get("failed", 0),
            "queue_paused":      counts.get("paused", 0),
            "metrics":           self._metrics.to_dict(),
        }
        return summary

    # ── Login prompt ─────────────────────────────────────────────────────────

    async def _maybe_prompt_login(
        self, env_entry, site_key: str, persona_name: str, store_dir
    ) -> None:
        """If the site requires login and has no saved session, open Chrome and wait for user.

        Uses raw Chrome subprocess (no CDP) so Google and similar sites won't detect automation.
        Skipped when:
          - The site doesn't require login
          - A profile already exists (previous login was saved)
          - BROWSERMIND_SKIP_LOGIN_PROMPT env var is set (for CI/batch without interaction)
          - Running in headless mode (no user interaction possible)
        """
        import os
        import subprocess
        import time as _time
        if os.environ.get("BROWSERMIND_SKIP_LOGIN_PROMPT"):
            return
        # Never block in headless mode — interactive login requires a visible browser
        if self._headless:
            return

        try:
            from browsermind_core.mission.site_registry import get_spec
            spec = get_spec(site_key)
            needs_login = spec is not None and (spec.requires_login or bool(spec.login_url))
        except Exception:
            needs_login = bool(env_entry.login_url)

        if not needs_login:
            return

        from browsermind_core.runtime.auth_session import AuthSession
        session_check = AuthSession(
            entry=env_entry,
            persona_name=persona_name,
            store_dir=store_dir,
            headless=True,
        )
        if session_check.is_profile_initialized():
            return  # already logged in from a prior run

        login_url = env_entry.login_url or env_entry.start_url
        profile = session_check.profile_path
        profile.mkdir(parents=True, exist_ok=True)

        print(
            f"\n  [MissionWorker] LOGIN REQUIRED  {site_key}\n"
            f"  A browser window will open at: {login_url}\n"
            f"  Please log in, then press ENTER here to continue.\n"
            f"  (Set BROWSERMIND_SKIP_LOGIN_PROMPT=1 to suppress this prompt.)"
        )

        # Strategy 1: Raw Chrome subprocess — no CDP, Google/Meta won't block
        chrome_exe = _find_chrome_exe()
        if chrome_exe:
            try:
                proc = subprocess.Popen([
                    chrome_exe,
                    f"--user-data-dir={profile}",
                    "--no-first-run", "--no-default-browser-check",
                    "--disable-default-apps", "--disable-sync",
                    login_url,
                ])
                import concurrent.futures
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    await loop.run_in_executor(
                        pool, lambda: input("  → Press ENTER after logging in: ")
                    )
                try:
                    proc.terminate()
                    _time.sleep(1.5)  # let Chrome flush cookies to disk
                except Exception:
                    pass
                print(f"  [MissionWorker] Login session saved for {site_key}.")
                return
            except Exception as exc:
                print(f"  [MissionWorker] Raw Chrome failed ({exc}), falling back to Playwright.")

        # Strategy 2: Playwright fallback
        try:
            from playwright.async_api import async_playwright
            _pw = await async_playwright().start()
            ctx = None
            for channel in ("chrome", None):
                try:
                    kw = dict(
                        user_data_dir=str(profile),
                        headless=False,
                        viewport={"width": 1280, "height": 800},
                        args=["--no-first-run", "--disable-blink-features=AutomationControlled"],
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/125.0.0.0 Safari/537.36"
                        ),
                    )
                    if channel:
                        kw["channel"] = channel
                    ctx = await _pw.chromium.launch_persistent_context(**kw)
                    break
                except Exception:
                    if not channel:
                        raise
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto(login_url, wait_until="domcontentloaded")
            import concurrent.futures
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                await loop.run_in_executor(
                    pool, lambda: input("  → Press ENTER after logging in: ")
                )
            await ctx.close()
            await _pw.stop()
            print(f"  [MissionWorker] Login session saved for {site_key}.")
        except Exception as exc:
            print(f"  [MissionWorker] Login prompt error (non-fatal): {exc}")

    # ── Per-site runner ──────────────────────────────────────────────────

    def _adapt_budget(self, entry: MissionEntry) -> int:
        """
        Adapt budget based on run history (#30).
        If previous runs exhausted full budget (steps == budget), expand by 50%.
        If previous runs were tiny (<10% of budget), shrink by 25%.
        """
        budget = entry.budget
        history = entry.run_history or []
        if len(history) < 2:
            return budget

        recent = history[-3:]
        avg_steps = sum(r["steps"] for r in recent) / len(recent)

        if avg_steps >= budget * 0.9:
            # Site keeps hitting budget ceiling — likely has more affordances
            return min(int(budget * 1.5), budget + 500)
        if avg_steps < budget * 0.1:
            # Site is very sparse — don't waste budget
            return max(int(budget * 0.75), 20)
        return budget

    async def _run_site(self, entry: MissionEntry, budget: Optional[int] = None) -> dict:
        from browsermind_core.exploration.exploration_spec import ExplorationSpec
        from browsermind_core.exploration.exploration_harness import ExplorationHarness
        from browsermind_core.runtime.environment_registry import resolve
        from browsermind_core.runtime.auth_session import AuthSession
        from browsermind_core.runtime.replay_engine import ReplayEngine
        from uuid import UUID as _UUID

        # Also try site_registry for unregistered sites
        site_key = entry.site_key
        env_entry = resolve(site_key)
        if env_entry is None:
            try:
                from browsermind_core.mission.site_registry import resolve_site
                env_entry = resolve_site(site_key)
            except Exception:
                pass
        if env_entry is None:
            return _failure(f"environment '{site_key}' not found in registry or site_registry")

        persona_name = entry.persona
        run_budget = budget or entry.budget

        s = self._session
        pe = s._lookup("persona", persona_name)
        if not pe:
            personas = s.persona_manager.list_personas()
            if not personas:
                return _failure("no personas available")
            fallback = personas[0]
            persona_id = (
                fallback.id if isinstance(fallback.id, _UUID)
                else _UUID(str(fallback.id))
            )
            persona_name = fallback.name
        else:
            persona_id = _UUID(pe["id"])

        headless = self._headless
        store_dir = self._store_dir

        # Protected environment gate: these sites actively detect automation.
        # If no saved profile exists, pause immediately — use `bm mission intervene` first.
        try:
            from browsermind_core.mission.site_registry import get_spec
            _spec = get_spec(site_key)
            if _spec is not None and getattr(_spec, "protected", False):
                from browsermind_core.runtime.auth_session import AuthSession as _AS
                _chk = _AS(entry=env_entry, persona_name=persona_name,
                           store_dir=store_dir, headless=True)
                if not _chk.is_profile_initialized():
                    print(
                        f"\n  [MissionWorker] PROTECTED SITE: {site_key}\n"
                        f"  This site actively blocks automation. Run first:\n"
                        f"    bm mission intervene {site_key}\n"
                        f"  Then re-queue with: bm mission resume {site_key}\n"
                    )
                    return {
                        **_failure(f"protected_site: no session — run `bm mission intervene {site_key}` first"),
                        "status": "paused",
                    }
        except Exception:
            pass  # if registry lookup fails, proceed normally

        # Login prompt: if the site requires login and has no saved profile,
        # open the browser visibly so the user can log in manually.
        await self._maybe_prompt_login(env_entry, site_key, persona_name, store_dir)

        async def engine_factory(_key: str) -> ReplayEngine:
            session = AuthSession(
                entry=env_entry,
                persona_name=persona_name,
                store_dir=store_dir,
                headless=headless,
            )
            return ReplayEngine(
                session,
                outcome_ledger=s.outcome_ledger,
                lesson_reader=getattr(s, "lesson_reader", None),
                behavior_audit=getattr(s, "behavior_audit", None),
                recovery_registry=getattr(s, "recovery_registry", None),
                recovery_candidate_registry=getattr(s, "recovery_candidate_registry", None),
                auto_pilot=getattr(s, "auto_pilot", None),
                persona_id=persona_id,
                environment_family=env_entry.family,
                environment_instance=env_entry.key,
                execution_engine=s.execution_engine,
                exploration_mode=True,
                state_classifier=getattr(s, "state_classifier", None),
                sstg=getattr(s, "sstg", None),
                task_id=s.task_manager.create_task(
                    persona_id=persona_id,
                    goal=f"mission:{site_key}",
                ).id,
            )

        spec = ExplorationSpec(
            site_key=site_key,
            budget=run_budget,
            label=f"mission_{site_key}",
        )
        harness = ExplorationHarness(
            hypothesis_store=getattr(s, "hypothesis_store", None),
        )
        self._active_harness = harness

        t0 = time.time()
        try:
            result = await harness.run(spec, engine_factory)
        finally:
            self._active_harness = None
        duration = round(time.time() - t0, 2)

        # Compute quality from hypotheses and experiences found
        quality_score = 0.0
        steps_done = result.steps_executed
        n_hyps = len(result.hypothesis_hashes)
        n_exps = len(result.experiences_discovered)
        if steps_done > 0:
            # Each hypothesis: 0.25 pts; any recognised experience: +0.25; cap at 1.0
            quality_score = min(1.0, n_hyps * 0.25 + (0.25 if n_exps > 0 else 0.0))

        base = {
            "steps":                result.steps_executed,
            "hypotheses":           len(result.hypothesis_hashes),
            "experiences":          result.experiences_discovered,
            "affordances_executed": result.affordances_executed,
            "verified_effects":     result.verified_effects,
            "duration":             duration,
            "error":                result.error,
            "quality_score":        quality_score,
        }

        if result.error:
            err_lower = result.error.lower()
            if any(kw in err_lower for kw in _BOT_WALL_KEYWORDS):
                return {**base, "status": "paused", "error": f"bot_wall: {result.error}"}
            if any(kw in err_lower for kw in _AUTH_WALL_KEYWORDS):
                return {**base, "status": "paused", "error": f"auth_gate: {result.error}"}
            return {**base, "status": "failed"}

        return {**base, "status": "done"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _failure(msg: str) -> dict:
    return {
        "status": "failed", "error": msg,
        "steps": 0, "hypotheses": 0, "experiences": [],
        "affordances_executed": 0, "verified_effects": 0,
        "duration": 0.0, "quality_score": 0.0,
    }


def _print_site_header(entry: MissionEntry) -> None:
    print(
        f"\n  [Mission] START   {entry.site_key:<28}"
        f"  budget={entry.budget:<6}"
        f"  priority={entry.priority}"
        f"  persona={entry.persona}"
        f"  attempt={entry.attempts + 1}/{entry.max_retries + 1}"
    )


def _print_site_result(entry: MissionEntry, result: dict, status: str) -> None:
    icons = {"done": "✓", "paused": "⏸", "failed": "✗", "skipped": "—"}
    icon = icons.get(status, "?")
    aff  = result.get("affordances_executed", 0)
    vfx  = result.get("verified_effects", 0)
    print(
        f"  [Mission] {icon}  {entry.site_key:<28}"
        f"  status={status:<8}"
        f"  steps={result.get('steps', 0):<5}"
        f"  hyps={result.get('hypotheses', 0):<4}"
        f"  aff={aff:<3}  vfx={vfx:<3}"
        f"  quality={result.get('quality_score', 0):.2f}"
        f"  t={result.get('duration', 0):.1f}s"
    )
    if status == "paused":
        print(
            f"  [Mission] PAUSED  human required: {result.get('error', '')}\n"
            f"            → bm mission resume {entry.site_key}"
        )


def _find_chrome_exe() -> "str | None":
    """Return path to Chrome or Edge executable, or None if not found."""
    import os
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        # macOS
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        # Linux
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None
