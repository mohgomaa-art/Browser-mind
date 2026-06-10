"""
bot_wall_recovery.py — Shared bot-wall detection and recovery for ReplayEngine.

Consolidates the Cloudflare/CAPTCHA logic that exists separately in
ExplorerPolicy._detect_bot_wall() so that both replay and exploration use
the same detection + recovery path.

Recovery tiers:
  SOFT walls (Cloudflare JS challenge):
    → Wait up to 10 s for the challenge to auto-resolve
    → Attempt checkbox click on challenges.cloudflare.com iframe
  HARD walls (Google automation block, persistent CAPTCHA):
    → Pause the replay and wait for human intervention
    → Resume automatically when the wall clears
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from playwright.async_api import Page


class BotWallSeverity(Enum):
    NONE   = "none"
    SOFT   = "soft"      # auto-recoverable (Cloudflare JS challenge)
    HARD   = "hard"      # requires human intervention
    CAPTCHA = "captcha"  # manual CAPTCHA solve needed


@dataclass
class BotWallResult:
    detected: bool
    severity: BotWallSeverity
    signal: str = ""
    resolved: bool = False
    wait_ms: int = 0


# Soft phrases — JS challenges that typically auto-resolve within ~8 s
_SOFT_PHRASES = [
    "just a moment",
    "ddos protection by cloudflare",
    "ray id",
    "checking your browser",
    "enable javascript and cookies",
    "please wait",
    "redirecting you",
]

# Hard phrases — automation-detected / permanently blocked
_HARD_PHRASES = [
    "browser or app may not be secure",
    "try using a different browser",
    "this app may not be secure",
    "access denied",
    "automated access",
    "your connection is not private",
    "suspicious activity",
    "not available in your region",
]

# CAPTCHA phrases
_CAPTCHA_PHRASES = [
    "recaptcha",
    "hcaptcha",
    "are you human",
    "i'm not a robot",
    "prove you're human",
    "security challenge",
    "captcha",
]

# Hard URL fragments
_HARD_URL_FRAGMENTS = [
    "accounts.google.com/v3/signin/rejected",
    "accounts.google.com/signin/rejected",
    "/cdn-cgi/challenge-platform/",
]


class BotWallRecovery:
    """
    Detect and attempt recovery from bot-wall pages.

    Usage in replay step loop:
        bwr = BotWallRecovery()
        result = await bwr.check_and_recover(page)
        if result.detected and not result.resolved:
            # escalate: pause replay, wait for human
    """

    def __init__(self, soft_wait_s: float = 10.0) -> None:
        self._soft_wait_s = soft_wait_s

    async def check_and_recover(self, page: "Page") -> BotWallResult:
        """
        Scan the current page for a bot wall and attempt recovery.
        Returns immediately if no wall is detected.
        """
        severity, signal = await self._scan(page)
        if severity == BotWallSeverity.NONE:
            return BotWallResult(detected=False, severity=BotWallSeverity.NONE)

        if severity == BotWallSeverity.SOFT:
            start = asyncio.get_event_loop().time()
            resolved = await self._try_cf_bypass(page)
            elapsed_ms = int((asyncio.get_event_loop().time() - start) * 1000)
            return BotWallResult(
                detected=True,
                severity=severity,
                signal=signal,
                resolved=resolved,
                wait_ms=elapsed_ms,
            )

        # HARD or CAPTCHA — cannot auto-recover
        return BotWallResult(
            detected=True,
            severity=severity,
            signal=signal,
            resolved=False,
        )

    async def is_clear(self, page: "Page") -> bool:
        """Quick check — returns True if page looks clean."""
        severity, _ = await self._scan(page)
        return severity == BotWallSeverity.NONE

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    async def _scan(self, page: "Page") -> tuple:
        """Return (severity, signal_phrase)."""
        try:
            url   = page.url or ""
            title = (await page.title() or "").lower()
            body  = await page.evaluate(
                "() => ((document.body && document.body.innerText) || '').slice(0, 2000).toLowerCase()"
            )
        except Exception:
            return BotWallSeverity.NONE, ""

        combined = f"{url} {title} {body}"

        # Check URL hard fragments
        for frag in _HARD_URL_FRAGMENTS:
            if frag in url:
                return BotWallSeverity.HARD, frag

        # CAPTCHA
        for phrase in _CAPTCHA_PHRASES:
            if phrase in combined:
                return BotWallSeverity.CAPTCHA, phrase

        # Hard phrases
        for phrase in _HARD_PHRASES:
            if phrase in combined:
                return BotWallSeverity.HARD, phrase

        # Soft phrases
        for phrase in _SOFT_PHRASES:
            if phrase in combined:
                return BotWallSeverity.SOFT, phrase

        return BotWallSeverity.NONE, ""

    async def _try_cf_bypass(self, page: "Page") -> bool:
        """Attempt Cloudflare JS challenge bypass. Returns True if cleared."""
        deadline = asyncio.get_event_loop().time() + self._soft_wait_s

        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.5)
            severity, _ = await self._scan(page)
            if severity == BotWallSeverity.NONE:
                return True

            # Try clicking the Cloudflare checkbox iframe
            try:
                for frame in page.frames:
                    if "challenges.cloudflare.com" in (frame.url or ""):
                        cb = frame.locator("input[type='checkbox']")
                        if await cb.count() > 0:
                            await cb.first.click(timeout=3_000)
                            await asyncio.sleep(3.0)
                            if await self.is_clear(page):
                                return True
            except Exception:
                pass

        return False
