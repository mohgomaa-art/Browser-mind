"""
cdp_network_monitor.py — CDP-level mutation capture for the L6 Network verifier.

Playwright's response interceptor misses XHR on older sites and loses WebSocket
frames entirely. This monitor attaches via the Chrome DevTools Protocol so every
outbound request is captured before the browser cache touches it.

Only mutation verbs (POST/PUT/PATCH/DELETE) are stored — GET/HEAD carry no
semantic signal for post-execution verification.

Usage:
    monitor = CDPNetworkMonitor()
    await monitor.start(page)
    # ... execute action ...
    mutations = monitor.captured_mutations()
    await monitor.stop()

The monitor is safe to start/stop multiple times on the same page instance.
On stop() it detaches the CDP session but leaves the page alive.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from playwright.async_api import Page

_MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass
class CapturedMutation:
    """One observed mutation request."""
    method: str
    url: str
    request_id: str
    status: Optional[int] = None      # filled when response received
    response_ok: Optional[bool] = None  # True if status 2xx


class CDPNetworkMonitor:
    """
    Attaches a CDP session to a Playwright page and captures all mutation
    HTTP requests. Lightweight — no request body interception, only headers.

    Lifecycle:
        monitor = CDPNetworkMonitor()
        await monitor.start(page)          # before action
        await execute_action(...)
        mutations = monitor.captured_mutations()
        await monitor.stop()               # after verification
    """

    def __init__(self) -> None:
        self._client = None
        self._mutations: Dict[str, CapturedMutation] = {}  # keyed by requestId
        self._started = False

    async def start(self, page: "Page") -> None:
        """Attach CDP session and begin capturing. Idempotent."""
        if self._started:
            return
        try:
            self._client = await page.context.new_cdp_session(page)
            await self._client.send("Network.enable")
            self._client.on("Network.requestWillBeSent", self._on_request)
            self._client.on("Network.responseReceived", self._on_response)
            self._started = True
        except Exception:
            # CDP not available (Firefox, older Chromium builds) — degrade silently
            self._client = None
            self._started = False

    async def stop(self) -> None:
        """Detach CDP session. Captured mutations remain accessible."""
        if self._client is not None:
            try:
                await self._client.detach()
            except Exception:
                pass
            self._client = None
        self._started = False

    def reset(self) -> None:
        """Clear captured mutations for a new action window."""
        self._mutations.clear()

    def captured_mutations(self) -> List[CapturedMutation]:
        """Return all captured mutation requests, ordered by first seen."""
        return list(self._mutations.values())

    def has_mutation_to(
        self,
        url_contains: str,
        method: Optional[str] = None,
        require_success: bool = True,
    ) -> bool:
        """
        Check if a mutation matching the given criteria was captured.

        Args:
            url_contains:    Substring that must appear in the request URL.
            method:          Optional HTTP method filter (POST/PUT/PATCH/DELETE).
            require_success: If True, only match requests with 2xx response.
        """
        for m in self._mutations.values():
            if url_contains and url_contains not in m.url:
                continue
            if method and m.method.upper() != method.upper():
                continue
            if require_success and not m.response_ok:
                continue
            return True
        return False

    def to_captured_requests(self) -> List[Dict[str, str]]:
        """Convert to the legacy list[dict] format expected by NetworkVerifier."""
        return [
            {"method": m.method, "url": m.url, "status": str(m.status or "")}
            for m in self._mutations.values()
        ]

    # ------------------------------------------------------------------
    # CDP event handlers
    # ------------------------------------------------------------------

    def _on_request(self, event: Dict[str, Any]) -> None:
        try:
            req = event.get("request", {})
            method = (req.get("method") or "").upper()
            if method not in _MUTATION_METHODS:
                return
            rid = event.get("requestId", "")
            self._mutations[rid] = CapturedMutation(
                method=method,
                url=req.get("url", ""),
                request_id=rid,
            )
        except Exception:
            pass

    def _on_response(self, event: Dict[str, Any]) -> None:
        try:
            rid = event.get("requestId", "")
            if rid not in self._mutations:
                return
            resp = event.get("response", {})
            status = int(resp.get("status", 0))
            self._mutations[rid].status = status
            self._mutations[rid].response_ok = 200 <= status < 300
        except Exception:
            pass
