"""
execution_engine_v2.py — L5 Executor: Find → Reach → Execute → Verify.

This is the new execution layer. The existing ActionExecutor (action_executor.py)
is preserved for ReplayEngine backward compatibility; this engine wraps it with
the full FREV protocol, shadow DOM traversal, rich text support, and behavior
profiles.

Integration with ReplayEngine:
  The engine is wired in replay_engine.py as:
      executor_v2 = WebExecutionEngine(page, profile=BehaviorProfile.fast())
      result = await executor_v2.execute(ExecutionRequest(
          action_type=action_type,
          locator=loc,
          value=val,
          url=url,
      ))
  ReplayEngine then uses result.effect_verdict instead of its own inline
  DOM diffing to determine effect_verified / effect_type.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from browsermind_core.runtime.action_registry import REGISTRY, ActionDefinition
from browsermind_core.runtime.behavior_profile import BehaviorProfile
from browsermind_core.runtime.execution_exception import (
    ExecutionExceptionClass,
    classify_exception,
    routing_for,
)
from browsermind_core.runtime.reach_engine import OverlayState, ReachEngine, ReachResult
from browsermind_core.runtime.rich_text_executor import RichTextExecutor
from browsermind_core.runtime.shadow_traversal import ShadowDOMTraversal
from browsermind_core.exploration.effect_verifier import (
    EffectSnapshot,
    EffectVerdict,
    EffectVerifier,
)

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page


# Re-export so callers import from one place
__all__ = [
    "WebExecutionEngine",
    "ExecutionRequest",
    "ExecutionResult",
]


@dataclass
class ExecutionRequest:
    action_type: str
    page: Optional["Page"] = None        # may be set later if not known at construction
    locator: Optional["Locator"] = None
    value: Optional[str] = None
    url: Optional[str] = None
    timeout_ms: Optional[int] = None     # override profile timeout for this action
    skip_reach: bool = False             # bypass ReachEngine (trusted caller)
    skip_verify: bool = False            # bypass EffectVerifier (perf-sensitive callers)
    shadow_path: Optional[list] = None  # shadow DOM selector path for shadow_* actions
    frame_selector: Optional[str] = None  # for frame_action


@dataclass
class ExecutionResult:
    success: bool
    action_type: str
    duration_ms: int
    reach_result: Optional[ReachResult] = None
    effect_verdict: Optional[EffectVerdict] = None
    before_snapshot: Optional[EffectSnapshot] = None
    failed_phase: Optional[str] = None   # "reach" | "execute" | "verify"
    error: Optional[str] = None
    exc_class: Optional[ExecutionExceptionClass] = None  # None on success
    retries: int = 0

    @property
    def is_targeting_failure(self) -> bool:
        """True when the failure is ELEMENT_NOT_FOUND — not a quality signal."""
        from browsermind_core.runtime.execution_exception import ExecutionExceptionClass as _EEC
        return self.exc_class == _EEC.ELEMENT_NOT_FOUND

    @property
    def should_record_quality(self) -> bool:
        """False for failures that must NOT enter OutcomeLedger."""
        if self.success:
            return True
        if self.exc_class is None:
            return True
        from browsermind_core.runtime.execution_exception import routing_for as _rf, EXCEPTION_ROUTING
        return EXCEPTION_ROUTING.get(self.exc_class, None) and EXCEPTION_ROUTING[self.exc_class].record_quality


class WebExecutionEngine:
    """
    L5 Executor implementing the F.R.E.V. pattern:
      Find     — done upstream by TargetResolver (locator handed in)
      Reach    — overlay detection, layout quiescence, scroll-into-view
      Execute  — dispatch the action using Playwright primitives
      Verify   — EffectVerifier DOM diff to confirm observable outcome
    """

    def __init__(
        self,
        page: "Page",
        profile: Optional[BehaviorProfile] = None,
        start_url: str = "",
    ) -> None:
        self._page = page
        self._profile = profile or BehaviorProfile.fast()
        self._overlay_state = OverlayState()
        self._reach = ReachEngine(
            page,
            overlay_state=self._overlay_state,
            dismiss_overlays=True,
        )
        self._verifier = EffectVerifier(start_url=start_url)
        self._rich_text = RichTextExecutor(page)
        self._shadow = ShadowDOMTraversal(page)

    def set_start_url(self, url: str) -> None:
        self._verifier.set_start_url(url)

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute a single action through the full FREV pipeline."""
        page = request.page or self._page
        start = time.monotonic()
        profile = self._profile

        defn = REGISTRY.get(request.action_type)
        if defn is None:
            # Attempt legacy alias lookup; fail hard if still not found
            return ExecutionResult(
                success=False,
                action_type=request.action_type,
                duration_ms=0,
                failed_phase="execute",
                error=f"Unknown action type: {request.action_type!r}",
            )

        # Pre-action delay
        pre_delay = profile.jittered_pre_delay()
        if pre_delay > 0:
            await asyncio.sleep(pre_delay / 1000.0)

        reach_result: Optional[ReachResult] = None

        # --- REACH ---
        if defn.requires_locator and request.locator is not None and not request.skip_reach:
            reach_result = await self._reach.reach(request.locator)
            if not reach_result.success:
                duration = int((time.monotonic() - start) * 1000)
                return ExecutionResult(
                    success=False,
                    action_type=request.action_type,
                    duration_ms=duration,
                    reach_result=reach_result,
                    failed_phase="reach",
                    error=reach_result.error or f"Blocked by: {reach_result.blocked_by}",
                )

        # --- SNAPSHOT (before) ---
        before: Optional[EffectSnapshot] = None
        if not request.skip_verify and defn.family not in ("extract", "screenshot", "storage"):
            try:
                before = await self._verifier.snapshot(page)
            except Exception:
                before = None

        # --- EXECUTE ---
        retries = 0
        last_error: Optional[str] = None
        last_exc_class: Optional[ExecutionExceptionClass] = None
        last_exc_routing = None

        while retries <= profile.max_action_retries:
            try:
                await self._dispatch(request, defn, page)
                last_error = None
                break
            except Exception as exc:
                exc_class = classify_exception(exc)
                routing = routing_for(exc)

                last_error = str(exc)
                last_exc_class = exc_class
                last_exc_routing = routing

                # PAGE_CRASH — do not retry; escalate immediately
                if exc_class == ExecutionExceptionClass.PAGE_CRASH:
                    break

                # ELEMENT_NOT_FOUND — do not retry inside the execute loop;
                # TargetResolver owns re-finding
                if exc_class == ExecutionExceptionClass.ELEMENT_NOT_FOUND:
                    break

                retries += 1
                if retries <= profile.max_action_retries:
                    await asyncio.sleep(profile.retry_delay_ms / 1000.0)

        if last_error is not None:
            duration = int((time.monotonic() - start) * 1000)

            # Decide whether to run the verifier based on exception class.
            # ELEMENT_NOT_FOUND and PAGE_CRASH must NOT produce a verdict —
            # running the verifier here would falsely record quality=0.0 signal
            # for a targeting failure, poisoning OutcomeLedger.
            run_post_fail_verify = (
                not request.skip_verify
                and before is not None
                and last_exc_routing is not None
                and last_exc_routing.run_verifier
            )
            post_fail_verdict: Optional[EffectVerdict] = None
            if run_post_fail_verify:
                try:
                    after_fail = await self._verifier.snapshot(page)
                    post_fail_verdict = self._verifier.diff(before, after_fail)
                except Exception:
                    pass

            return ExecutionResult(
                success=False,
                action_type=request.action_type,
                duration_ms=duration,
                reach_result=reach_result,
                effect_verdict=post_fail_verdict,
                before_snapshot=before,
                failed_phase="execute",
                error=last_error,
                exc_class=last_exc_class,
                retries=retries,
            )

        # Post-action delay
        post_delay = profile.jittered_post_delay()
        if post_delay > 0:
            await asyncio.sleep(post_delay / 1000.0)

        # --- VERIFY ---
        verdict: Optional[EffectVerdict] = None
        if not request.skip_verify and before is not None:
            try:
                after = await self._verifier.snapshot(page)
                verdict = self._verifier.diff(before, after)
            except Exception:
                pass

        duration = int((time.monotonic() - start) * 1000)
        return ExecutionResult(
            success=True,
            action_type=request.action_type,
            duration_ms=duration,
            reach_result=reach_result,
            effect_verdict=verdict,
            before_snapshot=before,
            retries=retries,
        )

    # ------------------------------------------------------------------ #
    # Internal dispatch — maps action names to Playwright calls            #
    # ------------------------------------------------------------------ #

    async def _dispatch(
        self,
        request: ExecutionRequest,
        defn: ActionDefinition,
        page: "Page",
    ) -> None:
        action = request.action_type
        loc = request.locator
        val = request.value or ""
        profile = self._profile
        timeout = request.timeout_ms or profile.element_timeout_ms

        # --- navigation family ---
        if action == "navigate":
            await page.goto(val, timeout=profile.navigation_timeout_ms)
            return
        if action == "navigate_back":
            await page.go_back(timeout=profile.navigation_timeout_ms)
            return
        if action == "navigate_forward":
            await page.go_forward(timeout=profile.navigation_timeout_ms)
            return
        if action == "reload":
            await page.reload(timeout=profile.navigation_timeout_ms)
            return
        if action == "navigate_new_tab":
            await page.evaluate(f"window.open({val!r}, '_blank')")
            return
        if action == "close_tab":
            await page.close()
            return

        # --- click family ---
        if action == "click":
            opts = {}
            if profile.click_position_jitter:
                import random
                opts["position"] = {
                    "x": profile.click_position_jitter * (random.random() - 0.5) * 2,
                    "y": profile.click_position_jitter * (random.random() - 0.5) * 2,
                }
            await loc.click(timeout=timeout, **opts)
            return
        if action == "dblclick":
            await loc.dbl_click(timeout=timeout)
            return
        if action == "right_click":
            await loc.click(button="right", timeout=timeout)
            return
        if action == "middle_click":
            await loc.click(button="middle", timeout=timeout)
            return
        if action == "click_by_text":
            await page.get_by_text(val).first.click(timeout=timeout)
            return

        # --- input family ---
        if action in ("fill", "type", "input"):
            if profile.between_keys_delay_ms > 0:
                await loc.fill("", timeout=timeout)
                await loc.type(val, delay=profile.key_delay())
            else:
                await loc.fill(val, timeout=timeout)
            return
        if action == "fill_append":
            await loc.focus(timeout=timeout)
            await page.keyboard.type(val, delay=profile.key_delay())
            return
        if action in ("press_key", "keydown"):
            await loc.press(val, timeout=timeout)
            return
        if action == "press_keys":
            for key in val.split("+"):
                await page.keyboard.down(key.strip())
            for key in reversed(val.split("+")):
                await page.keyboard.up(key.strip())
            return
        if action == "clear":
            await loc.fill("", timeout=timeout)
            return
        if action == "paste":
            await loc.fill("", timeout=timeout)
            await page.evaluate(
                f"navigator.clipboard.writeText({val!r}).catch(()=>{{}})"
            )
            await loc.press("Control+v")
            return

        # --- form family ---
        if action in ("submit", "form_submit"):
            await loc.press("Enter")
            return
        if action == "select_option":
            await loc.select_option(value=val, timeout=timeout)
            return
        if action == "select_option_by_text":
            await loc.select_option(label=val, timeout=timeout)
            return
        if action == "check":
            await loc.check(timeout=timeout)
            return
        if action == "uncheck":
            await loc.uncheck(timeout=timeout)
            return
        if action == "set_checked":
            checked = str(val).lower() not in ("false", "0", "no", "off")
            if checked:
                await loc.check(timeout=timeout)
            else:
                await loc.uncheck(timeout=timeout)
            return
        if action == "choose_radio":
            await page.locator(f"input[type=radio][value={val!r}]").check(timeout=timeout)
            return
        if action == "toggle_switch":
            is_checked = await loc.evaluate("el => el.getAttribute('aria-checked') === 'true'")
            if not is_checked:
                await loc.click(timeout=timeout)
            return
        if action == "range_input":
            await loc.evaluate(f"(el, v) => {{ el.value = v; el.dispatchEvent(new Event('input')); el.dispatchEvent(new Event('change')); }}", val)
            return

        # --- scroll family ---
        if action == "scroll_down":
            await page.keyboard.press("PageDown")
            return
        if action == "scroll_up":
            await page.keyboard.press("PageUp")
            return
        if action == "scroll_to":
            await loc.scroll_into_view_if_needed(timeout=timeout)
            return
        if action == "scroll_to_bottom":
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            return
        if action == "scroll_to_top":
            await page.evaluate("window.scrollTo(0, 0)")
            return
        if action == "scroll_by":
            parts = val.split(",")
            x = int(parts[0]) if parts else 0
            y = int(parts[1]) if len(parts) > 1 else 0
            await page.evaluate(f"window.scrollBy({x}, {y})")
            return

        # --- file family ---
        if action in ("upload", "upload_file", "set_input_files"):
            await loc.set_input_files(val, timeout=timeout)
            return
        if action == "upload_multiple":
            files = [f.strip() for f in val.split(",")]
            await loc.set_input_files(files, timeout=timeout)
            return

        # --- hover/focus family ---
        if action == "hover":
            await loc.hover(timeout=timeout)
            return
        if action == "focus":
            await loc.focus(timeout=timeout)
            return
        if action == "blur":
            await loc.evaluate("el => el.blur()")
            return
        if action == "mouse_move":
            parts = val.split(",")
            x, y = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
            await page.mouse.move(x, y)
            return

        # --- wait family ---
        if action == "wait_for_selector":
            await page.wait_for_selector(val, timeout=timeout)
            return
        if action == "wait_for_navigation":
            await page.wait_for_load_state("networkidle", timeout=profile.navigation_timeout_ms)
            return
        if action == "wait_for_load_state":
            await page.wait_for_load_state(val or "load", timeout=timeout)
            return
        if action == "wait_for_timeout":
            await asyncio.sleep(int(val or 500) / 1000.0)
            return
        if action == "wait_for_url":
            await page.wait_for_url(val, timeout=timeout)
            return
        if action == "wait_for_text":
            await page.wait_for_function(
                f"() => document.body.innerText.includes({val!r})",
                timeout=timeout,
            )
            return

        # --- auth family ---
        if action == "mfa_enter_code":
            await loc.fill(val, timeout=timeout)
            await loc.press("Enter")
            return
        if action == "logout":
            await loc.click(timeout=timeout)
            return

        # --- drag/drop family ---
        if action == "drag_to":
            target = page.locator(val)
            await loc.drag_to(target, timeout=timeout)
            return
        if action == "drag_to_offset":
            parts = val.split(",")
            x, y = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
            box = await loc.bounding_box()
            if box:
                await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                await page.mouse.down()
                await page.mouse.move(box["x"] + x, box["y"] + y)
                await page.mouse.up()
            return

        # --- frame/shadow family ---
        if action == "shadow_click":
            shadow_path = request.shadow_path or val.split(">")
            el = await self._shadow.path_query([s.strip() for s in shadow_path])
            if el:
                await el.click()
            return
        if action == "shadow_fill":
            parts = val.split("|", 1)
            shadow_path = request.shadow_path or parts[0].split(">")
            text = parts[1] if len(parts) > 1 else ""
            el = await self._shadow.path_query([s.strip() for s in shadow_path])
            if el:
                await el.fill(text)
            return
        if action == "frame_action":
            frame_sel = request.frame_selector or val.split("|")[0]
            frame = page.frame_locator(frame_sel)
            inner_sel = val.split("|")[1] if "|" in val else "body"
            await frame.locator(inner_sel).click(timeout=timeout)
            return

        # --- javascript family ---
        if action == "evaluate":
            await page.evaluate(val)
            return
        if action == "click_js":
            await loc.evaluate("el => el.click()")
            return
        if action == "set_attribute":
            parts = val.split("=", 1)
            attr, aval = parts[0], (parts[1] if len(parts) > 1 else "")
            await loc.evaluate(f"(el, v) => el.setAttribute({attr!r}, v)", aval)
            return
        if action == "remove_attribute":
            await loc.evaluate(f"el => el.removeAttribute({val!r})")
            return
        if action == "dispatch_event":
            await loc.dispatch_event(val)
            return
        if action == "trigger_change":
            await loc.evaluate(
                "el => { el.dispatchEvent(new Event('input', {bubbles:true})); "
                "el.dispatchEvent(new Event('change', {bubbles:true})); }"
            )
            return

        # --- dialog family ---
        if action == "accept_dialog":
            page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
            return
        if action == "dismiss_dialog":
            page.once("dialog", lambda d: asyncio.ensure_future(d.dismiss()))
            return
        if action == "fill_dialog":
            page.once("dialog", lambda d: asyncio.ensure_future(d.accept(val)))
            return
        if action == "accept_cookie_banner":
            for btn_sel in [
                "button[id*='accept' i]",
                "button[class*='accept' i]",
                "button[data-accept]",
                "[aria-label*='accept' i]",
            ]:
                try:
                    btn = page.locator(btn_sel).first
                    if await btn.is_visible():
                        await btn.click(timeout=3_000)
                        return
                except Exception:
                    continue
            return

        # --- extract family ---
        if action == "read_text":
            await loc.inner_text()
            return
        if action == "read_attribute":
            await loc.get_attribute(val)
            return
        if action == "read_value":
            await loc.input_value()
            return
        if action == "count_elements":
            await page.locator(val).count()
            return
        if action == "snapshot_page":
            await self._verifier.snapshot(page)
            return

        # --- screenshot family ---
        if action == "screenshot":
            await page.screenshot(full_page=True)
            return
        if action == "screenshot_element":
            await loc.screenshot()
            return

        # --- storage/session family ---
        if action == "set_local_storage":
            k, v = val.split("=", 1)
            await page.evaluate(f"localStorage.setItem({k!r}, {v!r})")
            return
        if action == "get_local_storage":
            await page.evaluate(f"localStorage.getItem({val!r})")
            return
        if action == "clear_local_storage":
            await page.evaluate("localStorage.clear()")
            return
        if action == "set_session_storage":
            k, v = val.split("=", 1)
            await page.evaluate(f"sessionStorage.setItem({k!r}, {v!r})")
            return
        if action == "set_cookie":
            parts = val.split(";")
            kv = parts[0].split("=", 1)
            name, value = kv[0].strip(), (kv[1].strip() if len(kv) > 1 else "")
            domain = page.url.split("/")[2] if page.url else "localhost"
            await page.context.add_cookies([{"name": name, "value": value,
                                              "domain": domain, "path": "/"}])
            return
        if action == "delete_cookie":
            await page.context.clear_cookies()
            return
        if action == "clear_cookies":
            await page.context.clear_cookies()
            return

        # --- rich text family ---
        if action in ("rich_text_fill", "code_editor_fill"):
            await self._rich_text.fill(loc, val)
            return
        if action == "rich_text_clear":
            await self._rich_text.clear(loc)
            return

        raise ValueError(f"Unhandled action type in dispatch: {action!r}")
