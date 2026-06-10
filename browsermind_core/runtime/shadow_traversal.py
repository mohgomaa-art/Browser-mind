"""
shadow_traversal.py — Recursive shadow DOM traversal helpers.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from playwright.async_api import ElementHandle, Locator, Page


class ShadowDOMTraversal:
    """
    Walks shadow roots to find elements that standard CSS selectors miss.

    Usage:
        traversal = ShadowDOMTraversal(page)
        element = await traversal.query("input[type=text]")
    """

    def __init__(self, page: "Page") -> None:
        self._page = page

    async def query(self, selector: str) -> Optional["ElementHandle"]:
        """Find first element matching selector across all shadow roots."""
        return await self._page.evaluate_handle(
            """(selector) => {
                function findInShadow(root, sel) {
                    try {
                        const el = root.querySelector(sel);
                        if (el) return el;
                    } catch { return null; }
                    const all = root.querySelectorAll('*');
                    for (const el of all) {
                        if (el.shadowRoot) {
                            const found = findInShadow(el.shadowRoot, sel);
                            if (found) return found;
                        }
                    }
                    return null;
                }
                return findInShadow(document, selector);
            }""",
            selector,
        )

    async def query_all(self, selector: str) -> List["ElementHandle"]:
        """Find all elements matching selector across all shadow roots."""
        result = await self._page.evaluate(
            """(selector) => {
                const results = [];
                function findAllInShadow(root, sel) {
                    try {
                        for (const el of root.querySelectorAll(sel)) {
                            results.push(el);
                        }
                    } catch {}
                    for (const el of root.querySelectorAll('*')) {
                        if (el.shadowRoot) findAllInShadow(el.shadowRoot, sel);
                    }
                }
                findAllInShadow(document, selector);
                return results;
            }""",
            selector,
        )
        return result or []

    async def path_query(self, path: List[str]) -> Optional["ElementHandle"]:
        """
        Navigate a dot-separated path of selectors through shadow roots.
        Example path: ["my-app", "login-form", "input[type=password]"]
        """
        return await self._page.evaluate_handle(
            """(path) => {
                let root = document;
                for (let i = 0; i < path.length; i++) {
                    const sel = path[i];
                    const el = root.querySelector ? root.querySelector(sel) : null;
                    if (!el) return null;
                    if (i === path.length - 1) return el;
                    root = el.shadowRoot || el;
                }
                return null;
            }""",
            path,
        )

    async def has_shadow_root(self, locator: "Locator") -> bool:
        try:
            result = await locator.evaluate("el => !!el.shadowRoot")
            return bool(result)
        except Exception:
            return False

    async def list_shadow_hosts(self) -> List[str]:
        """Return selectors for all elements that have shadow roots."""
        return await self._page.evaluate(
            """() => {
                const hosts = [];
                function collect(root) {
                    for (const el of root.querySelectorAll('*')) {
                        if (el.shadowRoot) {
                            const tag = el.tagName.toLowerCase();
                            const id  = el.id ? '#' + el.id : '';
                            hosts.push(tag + id);
                            collect(el.shadowRoot);
                        }
                    }
                }
                collect(document);
                return hosts;
            }"""
        )
