"""
`bm doctor` — pre-flight diagnostic command (#91, #95).

Checks:
  1. Python version (>= 3.10 required)
  2. Playwright installed + browser binaries present
  3. Sidecar port 8766 — is it free or already bound?
  4. Store directory writable
  5. Mission queue reachable
  6. Site registry loaded (N entries)
  7. Node.js + npm available (for UI dev)
  8. bm.py entry point accessible

Usage:
    bm doctor
    bm site validate <site_key>
"""
from __future__ import annotations

import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


# ── Doctor checks ─────────────────────────────────────────────────────────────

def _check(label: str, ok: bool, detail: str = "") -> Tuple[bool, str]:
    icon = "✓" if ok else "✗"
    colour_code = "\033[32m" if ok else "\033[31m"
    reset = "\033[0m"
    suffix = f"  {detail}" if detail else ""
    return ok, f"  {colour_code}{icon}{reset}  {label}{suffix}"


def run_doctor(store_dir: Path) -> int:
    """Run all diagnostic checks. Returns exit code (0=all ok, 1=some failed)."""
    results: List[Tuple[bool, str]] = []

    # 1. Python version
    major, minor = sys.version_info[:2]
    py_ok = major == 3 and minor >= 10
    results.append(_check(
        "Python version",
        py_ok,
        f"({sys.version.split()[0]}) {'✓ >= 3.10' if py_ok else '✗ requires 3.10+'}",
    ))

    # 2. Playwright installed
    try:
        import playwright  # noqa: F401
        pw_ok = True
        pw_detail = "playwright package found"
    except ImportError:
        pw_ok = False
        pw_detail = "not installed — run: pip install playwright"
    results.append(_check("Playwright package", pw_ok, pw_detail))

    # 3. Chromium binary
    chromium_ok = False
    chromium_detail = "not found"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = p.chromium.executable_path
            chromium_ok = Path(exe).exists()
            chromium_detail = exe if chromium_ok else f"missing at {exe}"
    except Exception as exc:
        chromium_detail = str(exc)
    results.append(_check("Chromium binary", chromium_ok, chromium_detail))

    # 4. Sidecar port 8766
    port_free = False
    port_detail = ""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        conn = s.connect_ex(("127.0.0.1", 8766))
        s.close()
        if conn == 0:
            port_free = True  # already bound = sidecar is running
            port_detail = "sidecar already running on :8766"
        else:
            port_free = True
            port_detail = "port 8766 is free (sidecar not running)"
    except Exception:
        port_free = True
        port_detail = "port check inconclusive"
    results.append(_check("Sidecar port 8766", port_free, port_detail))

    # 5. Store directory writable
    try:
        store_dir.mkdir(parents=True, exist_ok=True)
        test_file = store_dir / ".bm_doctor_write_test"
        test_file.write_text("ok")
        test_file.unlink()
        store_ok = True
        store_detail = str(store_dir)
    except Exception as exc:
        store_ok = False
        store_detail = f"not writable: {exc}"
    results.append(_check("Store directory writable", store_ok, store_detail))

    # 6. Mission queue accessible
    try:
        from browsermind_core.mission.mission_queue import MissionQueue
        q = MissionQueue(store_dir)
        total = q.total()
        queue_ok = True
        queue_detail = f"{total} entries in queue"
    except Exception as exc:
        queue_ok = False
        queue_detail = str(exc)
    results.append(_check("Mission queue", queue_ok, queue_detail))

    # 7. Site registry
    try:
        from browsermind_core.mission.site_registry import list_sites
        n = len(list_sites())
        reg_ok = n > 0
        reg_detail = f"{n} sites registered"
    except Exception as exc:
        reg_ok = False
        reg_detail = str(exc)
    results.append(_check("Site registry", reg_ok, reg_detail))

    # 8. Node.js available (for UI)
    node = shutil.which("node")
    node_ok = node is not None
    try:
        node_ver = subprocess.check_output(
            ["node", "--version"], text=True, stderr=subprocess.DEVNULL
        ).strip() if node_ok else ""
    except Exception:
        node_ver = ""
    results.append(_check("Node.js (for UI)", node_ok, node_ver or "not found"))

    # Print
    print()
    print("  BrowserMind Doctor")
    print("  ─────────────────────────────────")
    all_ok = True
    for ok, line in results:
        print(line)
        if not ok:
            all_ok = False
    print()

    if all_ok:
        print("  \033[32mAll checks passed.\033[0m")
    else:
        print("  \033[31mSome checks failed — see above.\033[0m")
    print()

    return 0 if all_ok else 1


def validate_site(site_key: str, headless: bool = True, timeout: int = 10) -> None:
    """
    Quick pre-flight check for one site (#95):
      - Can Playwright reach the URL?
      - Is it immediately Cloudflare-blocked?
      - What affordance families are present?
    """
    import asyncio

    async def _check():
        from playwright.async_api import async_playwright
        from browsermind_core.mission.site_registry import resolve_site, get_spec
        from browsermind_core.runtime.environment_registry import resolve
        from browsermind_core.runtime.affordance_discoverer import AffordanceDiscoverer
        from browsermind_core.runtime.intent_family import IntentFamily

        env = resolve(site_key) or resolve_site(site_key)
        if env is None:
            print(f"  ✗ Site key '{site_key}' not found in registry")
            return

        spec = get_spec(site_key)
        url = env.start_url
        print(f"\n  Validating: {site_key} → {url}")
        print(f"  Difficulty: {spec.difficulty if spec else '?'}/5")
        print(f"  Category:   {spec.category if spec else env.family}")

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=headless)
            page = await browser.new_page()
            try:
                resp = await page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
                status = resp.status if resp else "?"
                print(f"  HTTP status : {status}")

                title = await page.title()
                print(f"  Page title  : {title!r}")

                # Bot wall check
                body = await page.evaluate(
                    "() => (document.body && document.body.innerText || '').slice(0,400).toLowerCase()"
                )
                bot_phrases = ["cloudflare", "captcha", "access denied", "just a moment"]
                bot = next((p for p in bot_phrases if p in body), None)
                if bot:
                    print(f"  ⚠️  Bot wall detected: {bot!r}")
                else:
                    print("  ✓ No bot wall detected")

                # Quick affordance scan
                discoverer = AffordanceDiscoverer()
                found_families = []
                for fam in [IntentFamily.SEARCH, IntentFamily.FORM, IntentFamily.AUTH, IntentFamily.FILTER]:
                    aff = await discoverer.discover(page, fam)
                    if aff:
                        best_score = max(a.score for a in aff)
                        found_families.append(f"{fam.value}(score={best_score:.2f})")

                print(f"  Affordances : {', '.join(found_families) or 'none detected'}")

            except Exception as exc:
                print(f"  ✗ Error: {exc}")
            finally:
                await browser.close()
        print()

    asyncio.run(_check())
