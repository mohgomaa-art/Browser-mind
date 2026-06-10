"""Minimal in-page observer for P2A (clicks + input). Not replay-grade."""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from playwright.async_api import BrowserContext, Page

_OBSERVER_JS = """
() => {
  if (window.__bmObserverInstalled) return;
  window.__bmObserverInstalled = true;
  const hint = (el) => {
    if (!el || !el.tagName) return '';
    const tag = el.tagName.toLowerCase();
    const id = el.id ? '#' + el.id : '';
    const name = el.getAttribute('name') ? '[name="' + el.getAttribute('name') + '"]' : '';
    const testId = el.getAttribute('data-test') ? '[data-test="' + el.getAttribute('data-test') + '"]' : '';
    const role = el.getAttribute('role') ? '[role="' + el.getAttribute('role') + '"]' : '';
    const text = (el.innerText || el.value || '').trim().slice(0, 40);
    return tag + id + name + testId + role + (text ? '::' + text : '');
  };
  const send = (type, el, extra) => {
    if (typeof window.__bmRecordAction !== 'function') return;
    window.__bmRecordAction({
      type,
      url: location.href,
      selector_hint: hint(el),
      value: extra && extra.value !== undefined ? String(extra.value).slice(0, 200) : null,
      meta: extra || {}
    });
  };
  document.addEventListener('click', (e) => {
    send('click', e.target, { x: e.clientX, y: e.clientY });
  }, true);
  document.addEventListener('input', (e) => {
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable))
      send('input', t, { value: t.value });
  }, true);
  window.addEventListener('keydown', (e) => {
    if (['Enter', 'Tab', 'Escape'].includes(e.key))
      send('keydown', e.target, { key: e.key });
  }, true);
}
"""


class ShadowRecorder:
    """Attach observer to a Playwright page; buffer events in memory."""

    def __init__(self, on_action: Callable[[Dict[str, Any]], None]):
        self._on_action = on_action
        self._buffer: List[Dict[str, Any]] = []

    @property
    def buffer(self) -> List[Dict[str, Any]]:
        return list(self._buffer)

    async def attach(self, context: BrowserContext, page: Page):
        async def _handler(payload: Dict[str, Any]):
            self._buffer.append(payload)
            self._on_action(payload)

        await context.expose_function("__bmRecordAction", _handler)
        await page.add_init_script(_OBSERVER_JS)
        await page.evaluate(_OBSERVER_JS)

    async def record_navigation(self, page: Page, reason: str = "goto"):
        self._on_action(
            {
                "type": "navigation",
                "url": page.url,
                "selector_hint": reason,
                "value": None,
                "meta": {},
            }
        )
