"""BrowserMind Mission Control — live terminal dashboard.

Polls ~/.browsermind/_live_state.json every 0.5 s and renders a live view of
what the engine is doing right now.  Works on Windows (msvcrt) and Unix (select).

Usage:
    python scripts/live_watch.py

Keyboard controls:
    p  — pause engine (writes ~/.browsermind/_pause_requested)
    r  — resume engine (deletes ~/.browsermind/_pause_requested)
    q  — quit

No external dependencies — stdlib only.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

# ── Paths ──────────────────────────────────────────────────────────────────────
BM_DIR       = Path.home() / ".browsermind"
LIVE_STATE   = BM_DIR / "_live_state.json"
SENTINEL     = BM_DIR / "_pause_requested"
HYPOTHESES   = BM_DIR / "memory" / "default" / "hypotheses"
R0_LEDGER    = BM_DIR / "r0_evidence_ledger.jsonl"

POLL_INTERVAL = 0.5   # seconds between redraws


# ── Terminal helpers ───────────────────────────────────────────────────────────

def _clear():
    os.system("cls" if os.name == "nt" else "clear")


def _colour(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def _green(t):  return _colour(t, "32")
def _red(t):    return _colour(t, "31")
def _yellow(t): return _colour(t, "33")
def _cyan(t):   return _colour(t, "36")
def _bold(t):   return _colour(t, "1")


# ── Key detection (non-blocking) ───────────────────────────────────────────────

def _kb_hit() -> bool:
    if os.name == "nt":
        import msvcrt
        return bool(msvcrt.kbhit())
    else:
        import select
        return bool(select.select([sys.stdin], [], [], 0)[0])


def _get_key() -> str:
    if os.name == "nt":
        import msvcrt
        return msvcrt.getwch().lower()
    else:
        return sys.stdin.read(1).lower()


# ── Data readers ───────────────────────────────────────────────────────────────

def _read_live_state() -> Optional[Dict[str, Any]]:
    try:
        return json.loads(LIVE_STATE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_r0_tail(n: int = 5):
    lines = []
    try:
        with R0_LEDGER.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(line)
        return lines[-n:]
    except Exception:
        return []


def _hypothesis_stats() -> Dict[str, int]:
    counts: Dict[str, int] = {}
    if not HYPOTHESES.exists():
        return counts
    try:
        for p in HYPOTHESES.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                s = d.get("status", "UNKNOWN")
                counts[s] = counts.get(s, 0) + 1
            except Exception:
                pass
    except Exception:
        pass
    return counts


# ── Rendering ─────────────────────────────────────────────────────────────────

def _render(state: Optional[Dict[str, Any]]) -> None:
    _clear()
    print(_bold("═" * 65))
    print(_bold("  BrowserMind Mission Control"))
    print(_bold("═" * 65))
    print(f"  {_cyan('p')} pause  |  {_cyan('r')} resume  |  {_cyan('q')} quit")
    print()

    paused = SENTINEL.exists()
    if state is None:
        print(_yellow("  [idle]  No active replay engine detected."))
    else:
        status_tag = _red("PAUSED") if (paused or state.get("is_paused")) else _green("RUNNING")
        print(f"  Status  : {status_tag}")
        if state.get("pause_reason"):
            print(f"  Reason  : {state['pause_reason']}")
        print()
        print(f"  Template: {_bold(state.get('template_name', '?'))}")
        print(f"  Site    : {state.get('environment_instance', '?')}")
        step_done  = state.get("step_count_so_far", 0)
        step_total = state.get("total_steps", 0)
        pct = int(step_done / max(step_total, 1) * 100)
        bar = ("█" * (pct // 5)).ljust(20)
        print(f"  Step    : {step_done}/{step_total}  [{bar}] {pct}%")
        print(f"  Action  : {state.get('current_action', '')}  "
              f"{state.get('current_target_role', '')}  "
              f"{state.get('current_target_name', '')}")
        ts = state.get("last_update_ts", "")
        print(f"  Updated : {ts[:19].replace('T', ' ')}")

    # Hypothesis store
    print()
    print(_bold("── Hypothesis Store ─────────────────────────────────────────"))
    hyp_stats = _hypothesis_stats()
    if hyp_stats:
        for status in ("HYPOTHESIS", "RECURRING", "EMERGING", "CANDIDATE", "PROMOTED", "REFUTED"):
            cnt = hyp_stats.get(status, 0)
            if cnt:
                colour = (_green if status in ("CANDIDATE", "PROMOTED")
                          else _yellow if status in ("EMERGING", "RECURRING")
                          else _red if status == "REFUTED"
                          else str)
                print(f"    {colour(status):<22}  {cnt}")
        print(f"    {'TOTAL':<22}  {sum(hyp_stats.values())}")
    else:
        print("    (no hypotheses yet)")

    # Recent R0 events
    print()
    print(_bold("── Recent R0 Events ─────────────────────────────────────────"))
    r0_lines = _read_r0_tail(5)
    if r0_lines:
        for raw in r0_lines:
            try:
                evt = json.loads(raw)
                ts  = str(evt.get("ts", evt.get("timestamp", "")))[:19].replace("T", " ")
                typ = evt.get("event_type", evt.get("type", ""))
                msg = evt.get("message", evt.get("reason", ""))
                print(f"    {ts}  {_cyan(typ)}  {msg}")
            except Exception:
                print(f"    {raw[:72]}")
    else:
        print("    (no R0 events yet)")

    print()
    print(_bold("═" * 65))


# ── Main loop ──────────────────────────────────────────────────────────────────

def main() -> None:
    if os.name != "nt":
        import tty, termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        tty.setraw(fd)

    try:
        while True:
            state = _read_live_state()
            _render(state)

            deadline = time.monotonic() + POLL_INTERVAL
            while time.monotonic() < deadline:
                if _kb_hit():
                    key = _get_key()
                    if key == "q":
                        print("\n  Exiting Mission Control.")
                        return
                    elif key == "p":
                        BM_DIR.mkdir(parents=True, exist_ok=True)
                        SENTINEL.write_text("paused", encoding="utf-8")
                    elif key == "r":
                        if SENTINEL.exists():
                            SENTINEL.unlink()
                time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n  Interrupted.")
    finally:
        if os.name != "nt":
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


if __name__ == "__main__":
    main()
