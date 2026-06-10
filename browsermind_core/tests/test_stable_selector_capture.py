"""P1.5: recorder must capture stable selector attributes in descriptor.

Validates two things:
1. The JS source contains the attribute capture expressions (static, no browser).
2. A real Playwright capture produces descriptor fields id/data_testid/aria_label/name
   when the target element has those attributes (browser, skipped if unavailable).
"""
from __future__ import annotations

import asyncio
import urllib.parse
from typing import Any, Dict, List

import pytest

from browsermind_core.recorder.semantic_recorder import (
    SemanticRecorder,
    _SEMANTIC_OBSERVER_JS,
)

# ---------------------------------------------------------------------------
# Static JS-source checks (no browser required)
# ---------------------------------------------------------------------------

def test_js_captures_data_testid_attr():
    assert "getAttribute('data-testid')" in _SEMANTIC_OBSERVER_JS, (
        "getTargetDescriptor must capture data-testid attribute"
    )


def test_js_captures_elem_id():
    assert "elemId = el.id" in _SEMANTIC_OBSERVER_JS, (
        "getTargetDescriptor must capture el.id as elemId"
    )


def test_js_captures_name_attr():
    assert "getAttribute('name')" in _SEMANTIC_OBSERVER_JS, (
        "getTargetDescriptor must capture name attribute"
    )


def test_js_descriptor_returns_id_field():
    assert "id: elemId" in _SEMANTIC_OBSERVER_JS, (
        "getTargetDescriptor return dict must include id field"
    )


def test_js_descriptor_returns_data_testid_field():
    assert "data_testid: dataTestid" in _SEMANTIC_OBSERVER_JS, (
        "getTargetDescriptor return dict must include data_testid field"
    )


def test_js_descriptor_returns_aria_label_field():
    assert "aria_label: ariaLabel" in _SEMANTIC_OBSERVER_JS, (
        "getTargetDescriptor return dict must include aria_label field"
    )


def test_js_descriptor_returns_name_field():
    assert "name: nameAttr" in _SEMANTIC_OBSERVER_JS, (
        "getTargetDescriptor return dict must include name field"
    )


# ---------------------------------------------------------------------------
# Browser integration (skipped when Playwright/Chromium unavailable)
# ---------------------------------------------------------------------------

_HTML = """<!doctype html>
<html><body>
  <button
    id="submit-btn"
    data-testid="submit"
    aria-label="Send form"
    name="submit_action"
    type="button">Submit</button>
</body></html>
"""


async def _run_capture() -> List[Dict[str, Any]]:
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
            await page.click("button")
            await page.wait_for_timeout(500)
        finally:
            await browser.close()

    return captured


def _try_capture() -> List[Dict[str, Any]] | None:
    try:
        return asyncio.run(_run_capture())
    except Exception as exc:
        pytest.skip(f"Playwright/Chromium unavailable: {exc}")
        return None


def test_descriptor_has_id():
    steps = _try_capture()
    clicks = [s for s in steps if s.get("action_type") == "click"]
    assert clicks, "no click captured"
    d = clicks[-1].get("descriptor") or {}
    assert d.get("id") == "submit-btn", f"id field wrong: {d.get('id')!r}"


def test_descriptor_has_data_testid():
    steps = _try_capture()
    clicks = [s for s in steps if s.get("action_type") == "click"]
    assert clicks, "no click captured"
    d = clicks[-1].get("descriptor") or {}
    assert d.get("data_testid") == "submit", f"data_testid wrong: {d.get('data_testid')!r}"


def test_descriptor_has_aria_label():
    steps = _try_capture()
    clicks = [s for s in steps if s.get("action_type") == "click"]
    assert clicks, "no click captured"
    d = clicks[-1].get("descriptor") or {}
    assert d.get("aria_label") == "Send form", f"aria_label wrong: {d.get('aria_label')!r}"


def test_descriptor_has_name():
    steps = _try_capture()
    clicks = [s for s in steps if s.get("action_type") == "click"]
    assert clicks, "no click captured"
    d = clicks[-1].get("descriptor") or {}
    assert d.get("name") == "submit_action", f"name wrong: {d.get('name')!r}"
