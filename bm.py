#!/usr/bin/env python
"""
bm.py — BrowserMind Console entry point.
Usage: python bm.py <command>
Or add to PATH and run: bm <command>
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

# Ensure stdout/stderr use UTF-8 on Windows where the default codepage (cp1252)
# cannot encode box-drawing characters, progress bars, and other Unicode glyphs
# used throughout the CLI.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from browsermind_core.console.cli import cli

if __name__ == "__main__":
    cli()
