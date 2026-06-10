"""
main.py — LEGACY ENTRY POINT (superseded)

The original BrowserMind heuristic engine that lived here has been removed.
The core/ directory it depended on was LEGACY_FROZEN and has been deleted.

Use the active system instead:
    python bm.py --help
    bm record start
    bm replay start <template> --env <site>
    bm explore --site <key>

See BROWSERMIND_COMPLETE_ARCHITECTURE.md for the full system map.
"""
import sys

print(
    "main.py is no longer functional. "
    "The legacy core/ system has been removed.\n"
    "Use: python bm.py --help",
    file=sys.stderr,
)
sys.exit(1)
