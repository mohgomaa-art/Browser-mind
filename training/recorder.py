"""
BrowserMind — training/recorder.py
=====================================
Re-exports SessionRecorder from core/recorder.py so that
main.py's `from training.recorder import SessionRecorder` works.
"""

from core.recorder import SessionRecorder, get_current_state  # noqa: F401

__all__ = ["SessionRecorder", "get_current_state"]
