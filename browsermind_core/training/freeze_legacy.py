"""Freeze notice for legacy trainers.

The legacy `train_bc.py`, `train_dagger.py`, `train_ppo.py` consume schemas
(`training/spec_sessions/`, `core/*`) that pre-date the
`browsermind_core.recorder` + OutcomeLedger pipeline. The current path is
`browsermind_core.training.episode_extractor`. These warnings are advisory
so existing tests that import the modules continue to load.
"""
from __future__ import annotations

import os
import sys

FROZEN_NOTICE = (
    "Legacy trainer detected. This script reads schemas that the modern "
    "browsermind_core pipeline no longer produces. Use "
    "`python -m browsermind_core.training.cli extract` to build BC episodes "
    "from the OutcomeLedger instead."
)


def check_legacy_trainer_call(script_name: str) -> None:
    """Print a [FROZEN] warning to stderr. Never aborts."""
    try:
        name = os.path.basename(str(script_name))
    except Exception:
        name = str(script_name)
    sys.stderr.write(f"[FROZEN] {name}: {FROZEN_NOTICE}\n")
