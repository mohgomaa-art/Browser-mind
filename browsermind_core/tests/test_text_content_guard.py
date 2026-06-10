"""B-2 regression: text_content must not leak typed input values."""
from __future__ import annotations

import asyncio
import urllib.parse
from typing import Any, Dict, List

import pytest

from browsermind_core.recorder.semantic_recorder import (
    SemanticRecorder,
    _SEMANTIC_OBSERVER_JS,
)


_LEGACY_LINE = "const textContent = (el.innerText || '').trim().slice(0, 120);"
_GUARDED_EXPR = "isTextInput ? '' : (el.innerText"


def test_js_source_contains_guarded_textcontent():
    assert _GUARDED_EXPR in _SEMANTIC_OBSERVER_JS, (
        "getTargetDescriptor must compute textContent via the isTextInput guard"
    )
    # The legacy unguarded line must no longer appear standalone.
    assert _LEGACY_LINE not in _SEMANTIC_OBSERVER_JS, (
        "Unguarded textContent assignment is still present in the JS"
    )
    # Two independent guard sites: one in getAccessibleName, one in getTargetDescriptor.
    assert _SEMANTIC_OBSERVER_JS.count("isTextInput") >= 2, (
        f"Expected >=2 isTextInput occurrences, found "
        f"{_SEMANTIC_OBSERVER_JS.count('isTextInput')}"
    )


_HTML = """<!doctype html>
<html><body>
  <label for="email">Email</label>
  <input id="email" name="email" placeholder="Email address" />
  <button id="go" type="button">Submit Form</button>
</body></html>
"""


async def _run_browser_capture() -> List[Dict[str, Any]]:
    from playwright.async_api import async_playwright

    captured: List[Dict[str, Any]] = []

    def on_step(step: Dict[str, Any]) -> None:
        captured.append(step)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            context = await browser.new_context()
            page = await context.new_page()
            recorder = SemanticRecorder(on_step=on_step)
            await recorder.attach(context, page)
            data_url = "data:text/html;charset=utf-8," + urllib.parse.quote(_HTML)
            await page.goto(data_url)

            await page.fill("#email", "alice@example.com")
            # Click triggers flushInputs() which emits the pending fill event.
            await page.click("#go")
            # Give the exposed function callbacks time to drain.
            await page.wait_for_timeout(500)
        finally:
            await browser.close()

    return captured


def _try_real_browser() -> List[Dict[str, Any]] | None:
    try:
        return asyncio.run(_run_browser_capture())
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"Playwright/Chromium unavailable: {exc}")
        return None


def test_input_text_content_is_empty_on_fill():
    steps = _try_real_browser()
    assert steps, "recorder produced no steps"
    fills = [s for s in steps if s.get("action_type") == "fill"]
    assert fills, f"no fill step captured; got: {[s.get('action_type') for s in steps]}"
    fill = fills[-1]
    descriptor = fill.get("descriptor") or {}
    assert descriptor.get("text_content", None) == "", (
        f"text_content for input must be empty, got {descriptor.get('text_content')!r}"
    )


def test_input_target_name_is_label_not_typed_value():
    steps = _try_real_browser()
    fills = [s for s in steps if s.get("action_type") == "fill"]
    assert fills, "no fill step captured"
    name = fills[-1].get("target_name") or ""
    assert "alice@example.com" not in name, (
        f"target_name leaked typed value: {name!r}"
    )


def test_button_text_content_is_preserved():
    steps = _try_real_browser()
    clicks = [s for s in steps if s.get("action_type") == "click"]
    assert clicks, "no click step captured"
    click = clicks[-1]
    descriptor = click.get("descriptor") or {}
    assert descriptor.get("text_content", "") == "Submit Form", (
        f"button text_content was altered: {descriptor.get('text_content')!r}"
    )
