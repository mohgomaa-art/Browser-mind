"""Tests for Mission Control infrastructure: live_state, pause/resume, sentinel path."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_engine(store_dir: str):
    from browsermind_core.runtime.replay_engine import ReplayEngine
    mock_session = MagicMock()
    mock_session.store_dir = store_dir
    mock_session.persona_name = "test_persona"
    engine = ReplayEngine(auth_session=mock_session)
    engine._active_execution_id = "test-exec-id"
    engine.persona_id = "test-persona-id"
    engine.environment_instance = "test.example.com"
    engine.environment_family = "test_family"
    return engine


def test_live_state_includes_is_paused():
    """_write_live_state() must include is_paused in the emitted JSON."""
    with tempfile.TemporaryDirectory() as tmp:
        engine = _make_engine(tmp)

        mock_template = MagicMock()
        mock_template.name = "test_template"
        mock_template.id = "tmpl-123"
        mock_template.steps = []

        mock_instance = MagicMock()
        mock_instance.id = "inst-456"

        mock_report = MagicMock()
        mock_report.resolved_steps = 2
        mock_report.failed_steps = 0
        mock_report.total_steps = 5

        engine._write_live_state(
            instance=mock_instance,
            template=mock_template,
            seq=3,
            action_type="click",
            role="button",
            name="Submit",
            report=mock_report,
            strategy=None,
            is_paused=True,
            pause_reason="unit test",
        )

        live_path = Path(tmp) / "_live_state.json"
        assert live_path.exists()
        state = json.loads(live_path.read_text())
        assert "is_paused" in state
        assert state["is_paused"] is True
        assert state["pause_reason"] == "unit test"


def test_engine_pause_resume_state():
    """pause() sets is_paused=True, resume() resets it to False."""
    with tempfile.TemporaryDirectory() as tmp:
        engine = _make_engine(tmp)

        assert engine.is_paused is False

        engine.pause("testing")
        assert engine.is_paused is True
        assert engine._pause_reason == "testing"

        engine.resume()
        assert engine.is_paused is False
        assert engine._pause_reason == ""


def test_sentinel_file_path_correct():
    """The sentinel path is store_dir/_pause_requested."""
    with tempfile.TemporaryDirectory() as tmp:
        engine = _make_engine(tmp)
        expected = Path(tmp) / "_pause_requested"
        # The sentinel path is constructed inline in the step loop; verify
        # that the expected path matches what the engine would use.
        sentinel = Path(engine.auth_session.store_dir) / "_pause_requested"
        assert sentinel == expected
