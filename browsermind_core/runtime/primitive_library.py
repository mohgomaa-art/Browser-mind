"""PrimitiveLibrary — Phase 3 of R6 v1.

Names every Playwright/resolver primitive currently used by the recovery
ladder so they can be referenced from data (recovery_ladder.json) instead
of hardcoded if/elif branches.

Each primitive is an async callable with the signature:
    async fn(page, descriptor, *, resolver=None, read_only=False) -> Optional[Locator]

Primitives never click. They only return a Locator (or None) the caller can
test via .count() / .first.wait_for(). The `read_only` flag is informational
for shadow validation — primitives already do not mutate the page.

Why this module is small: the resolver helpers (_try_find_container,
_try_placeholder, _try_text, _resolve_by_capability) already exist on
TargetResolver. This module delegates to them, plus exposes the bare
Playwright entry points (get_by_role, get_by_label, get_by_test_id) that
recovery_ladder.json may reference directly.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from playwright.async_api import Locator, Page


PrimitiveFn = Callable[..., Awaitable[Optional[Locator]]]


# --- Concrete primitives ---------------------------------------------------


async def by_role(
    page: Page,
    descriptor: Dict[str, Any],
    *,
    resolver=None,
    read_only: bool = False,
) -> Optional[Locator]:
    role = (descriptor.get("target_role") or "").strip()
    name = (descriptor.get("target_name") or "").strip()
    if not role or not name:
        return None
    cand = page.get_by_role(role, name=name, exact=False)
    return cand if await cand.count() == 1 else None


async def by_text(
    page: Page,
    descriptor: Dict[str, Any],
    *,
    resolver=None,
    read_only: bool = False,
) -> Optional[Locator]:
    text = descriptor.get("accessible_name") or descriptor.get("text_content") or ""
    if not text:
        return None
    if resolver is not None and hasattr(resolver, "_try_text"):
        return await resolver._try_text(text, descriptor)
    cand = page.get_by_text(text)
    return cand if await cand.count() == 1 else None


async def by_placeholder(
    page: Page,
    descriptor: Dict[str, Any],
    *,
    resolver=None,
    read_only: bool = False,
) -> Optional[Locator]:
    ph = descriptor.get("placeholder") or ""
    if not ph:
        return None
    if resolver is not None and hasattr(resolver, "_try_placeholder"):
        return await resolver._try_placeholder(ph, descriptor)
    cand = page.get_by_placeholder(ph)
    return cand if await cand.count() == 1 else None


async def by_label(
    page: Page,
    descriptor: Dict[str, Any],
    *,
    resolver=None,
    read_only: bool = False,
) -> Optional[Locator]:
    label = descriptor.get("accessible_name") or ""
    if not label:
        return None
    cand = page.get_by_label(label)
    return cand if await cand.count() == 1 else None


async def by_test_id(
    page: Page,
    descriptor: Dict[str, Any],
    *,
    resolver=None,
    read_only: bool = False,
) -> Optional[Locator]:
    test_id = descriptor.get("container_data_test") or descriptor.get("test_id") or ""
    if not test_id:
        return None
    cand = page.get_by_test_id(test_id)
    return cand if await cand.count() == 1 else None


async def structural(
    page: Page,
    descriptor: Dict[str, Any],
    *,
    resolver=None,
    read_only: bool = False,
) -> Optional[Locator]:
    dom_path = descriptor.get("dom_path") or ""
    if not dom_path:
        return None
    cand = page.locator(dom_path)
    return cand if await cand.count() == 1 else None


async def by_capability(
    page: Page,
    descriptor: Dict[str, Any],
    *,
    resolver=None,
    read_only: bool = False,
) -> Optional[Locator]:
    if resolver is None or not hasattr(resolver, "_resolve_by_capability"):
        return None
    if not descriptor.get("capability_hint"):
        return None
    return await resolver._resolve_by_capability(descriptor)


async def container_proximity(
    page: Page,
    descriptor: Dict[str, Any],
    *,
    resolver=None,
    read_only: bool = False,
) -> Optional[Locator]:
    """The R1 strategy. Delegates to the existing helpers on TargetResolver
    so the data-driven ladder produces identical behavior to the hardcoded
    R1 branch (target_resolver.py:535-560)."""
    if resolver is None:
        return None
    container = await resolver._try_find_container(descriptor)
    if container is None:
        return None
    target_selector = descriptor.get("target_selector") or ""
    target_role = (descriptor.get("target_role") or "").strip()
    target_name = (descriptor.get("target_name") or "").strip()
    try:
        if target_selector:
            cand = container.locator(target_selector)
            if await cand.count() == 1:
                return cand
        if target_role and target_name:
            cand = container.get_by_role(target_role, name=target_name, exact=False)
            if await cand.count() == 1:
                return cand
            if await cand.count() > 1 and hasattr(resolver, "_resolve_ambiguity"):
                resolved = await resolver._resolve_ambiguity(cand, descriptor)
                if resolved is not None:
                    return resolved
    except Exception:
        return None
    return None


# --- Registry --------------------------------------------------------------


PRIMITIVE_LIBRARY: Dict[str, PrimitiveFn] = {
    "by_role":              by_role,
    "by_text":              by_text,
    "by_placeholder":       by_placeholder,
    "by_label":             by_label,
    "by_test_id":           by_test_id,
    "structural":           structural,
    "by_capability":        by_capability,
    "container_proximity":  container_proximity,
}


def get_primitive(name: str) -> Optional[PrimitiveFn]:
    """Lookup a primitive by name. Returns None on miss so the registry
    can skip unknown rows defensively."""
    return PRIMITIVE_LIBRARY.get(name)


def known_primitives() -> tuple:
    return tuple(PRIMITIVE_LIBRARY.keys())
