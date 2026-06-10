from typing import Optional
import json
import os
from pathlib import Path
from playwright.async_api import BrowserContext

AUTH_DIR = Path("c:/Users/mg/.browsermind")
AUTH_FILE = AUTH_DIR / "session_auth.json"

def ensure_auth_dir():
    AUTH_DIR.mkdir(parents=True, exist_ok=True)

async def save_session_state(context: BrowserContext):
    """Saves cookies and local storage to a file."""
    ensure_auth_dir()
    state = await context.storage_state(path=AUTH_FILE)
    print(f"[AUTH] Session state saved to {AUTH_FILE}")
    return state

def get_session_path() -> Optional[Path]:
    """Returns path to auth file if it exists."""
    if AUTH_FILE.exists():
        return AUTH_FILE
    return None

def clear_session():
    """Removes stored session."""
    if AUTH_FILE.exists():
        AUTH_FILE.unlink()
        print("[AUTH] Session cleared.")
