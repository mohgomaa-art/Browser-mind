"""Regression: KernelSession must not write outside its store_dir.

The honesty surface (`bm system status`) revealed that BehaviorAuditLog
was being constructed without a path argument inside KernelSession.__init__,
so every test that instantiated KernelSession(store_dir=tmp_path) was
silently writing audit rows into ~/.browsermind/audit/behavior_audit.jsonl
in the user's real production store.

These tests catch any future component that defaults to a global path
when a store_dir-scoped path was the obvious correct choice.
"""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from browsermind_core.console.session import KernelSession
from browsermind_core.ontology.recovery_candidate import RecoveryCandidate
from browsermind_core.runtime.recovery_registry import RecoveryStrategy


def test_kernel_session_audit_log_lives_inside_store_dir(tmp_path):
    """The behavior_audit.jsonl path must be under store_dir, NOT under
    ~/.browsermind. This was the leak."""
    ks = KernelSession(store_dir=str(tmp_path))
    audit_path = ks.behavior_audit.path
    home = Path.home()
    assert str(audit_path).startswith(str(tmp_path)), (
        f"BehaviorAuditLog wrote outside store_dir: path={audit_path}, "
        f"store_dir={tmp_path}"
    )
    # Anti-coincidence: explicitly assert it is NOT pointing at the home dir
    # default — even on systems where home and tmp_path could share a prefix.
    assert not str(audit_path).startswith(
        str(home / ".browsermind")
    ), f"audit path leaked to home default: {audit_path}"


def test_kernel_session_audit_writes_land_in_store_dir(tmp_path):
    """Behavioral check: an audit write goes to the right file."""
    ks = KernelSession(store_dir=str(tmp_path))
    ks.behavior_audit.record(
        decision_point="test.regression",
        prior_source="test",
        picked="x",
    )
    expected = tmp_path / "audit" / "behavior_audit.jsonl"
    assert expected.exists(), f"audit row did not land at {expected}"
    # Negative: nothing was written to a sibling default path.
    rogue = tmp_path / ".." / "behavior_audit.jsonl"
    assert not rogue.exists()


def test_kernel_session_construction_does_not_touch_home(tmp_path, monkeypatch):
    """Constructing a session should not create or modify any path under
    ~/.browsermind. This test only verifies non-creation; it doesn't try
    to detect modification of pre-existing files (that's covered by the
    path assertions above)."""
    home_before = Path.home() / ".browsermind"
    pre_existed = home_before.exists()

    KernelSession(store_dir=str(tmp_path))

    if not pre_existed:
        assert not home_before.exists(), (
            "KernelSession created ~/.browsermind even though the test "
            "pointed it at a tmp_path"
        )
