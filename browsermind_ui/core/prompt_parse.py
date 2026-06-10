"""Parse prompt text — resolve environment names via EnvironmentRegistry."""
from __future__ import annotations

import re
from typing import Tuple, Optional

from browsermind_core.runtime.environment_registry import resolve, EnvironmentEntry

# Persona only at end: " ... @ pilot" (not email@domain.com)
_PERSONA_SUFFIX = re.compile(r"\s+@\s+([a-zA-Z][a-zA-Z0-9_-]*)\s*$")
_PASS_PATTERN = re.compile(
    r"\b(?:pass|password)\s*(?:is|:)\s*\S+",
    re.IGNORECASE,
)
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)

_BROWSER_VERBS = (
    "open ", "go to ", "browse ", "navigate ", "navigate to ",
    "login to ", "log in to ", "visit ", "show me ",
)


def split_goal_persona(line: str, default_persona: str = "pilot") -> Tuple[str, str]:
    """Split goal and persona; emails in the goal are preserved."""
    text = (line or "").strip()
    m = _PERSONA_SUFFIX.search(text)
    if m:
        return text[: m.start()].strip(), m.group(1)
    return text, default_persona


def sanitize_goal(goal: str) -> str:
    """Never persist raw passwords from the prompt."""
    return _PASS_PATTERN.sub("[password-redacted]", goal).strip()


def is_browser_intent(line: str) -> bool:
    lower = line.lower()
    if _URL_PATTERN.search(line):
        return True
    if any(k in lower for k in _BROWSER_VERBS):
        return True
    # If the line resolves to a known environment, it's a browser intent
    entry = resolve(lower)
    return entry is not None


def infer_env_and_url(line: str) -> Tuple[str, Optional[str]]:
    """
    Return (env_key, optional_url_override).
    Uses EnvironmentRegistry — never silently falls back to Facebook.
    Returns ("unknown", None) if no match.
    """
    lower = line.lower()

    # Explicit URL takes priority
    m = _URL_PATTERN.search(line)
    if m:
        url = m.group(0).rstrip(".,)")
        # Try to resolve a known environment from the URL
        for word in re.split(r"[./\s]", url.lower()):
            entry = resolve(word)
            if entry:
                return entry.key, url
        return "unknown_url", url

    # Try resolving individual words from the line
    words = re.split(r"[\s,;]+", lower)
    for word in words:
        entry = resolve(word)
        if entry:
            return entry.key, entry.start_url

    # Try the whole line (catches multi-word names like "hugging face")
    entry = resolve(lower)
    if entry:
        return entry.key, entry.start_url

    return "unknown", None
