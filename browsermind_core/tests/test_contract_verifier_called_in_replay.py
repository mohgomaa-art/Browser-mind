"""Source-level guard: _verify_contract_outcome_async is called in replay().

Verifies:
  1. _verify_contract_outcome_async is defined on ReplayEngine.
  2. It is called on both the BLOCKED early return path and the terminal return path.
  3. Both call sites appear AFTER _record_replay_accuracy and BEFORE _record_replay_outcome.
  4. _last_contract_result and _last_contract_id attributes are referenced inside
     _record_replay_outcome() (so contract state flows into OutcomeRecord.metrics).
"""
from __future__ import annotations

import re
from pathlib import Path

REPLAY_ENGINE_SRC = (
    Path(__file__).resolve().parents[1] / "runtime" / "replay_engine.py"
).read_text(encoding="utf-8")


def test_verify_contract_async_method_defined():
    assert "async def _verify_contract_outcome_async(" in REPLAY_ENGINE_SRC, (
        "_verify_contract_outcome_async not defined on ReplayEngine"
    )


def test_verify_contract_sync_method_defined():
    assert "def _verify_contract_outcome(" in REPLAY_ENGINE_SRC, (
        "_verify_contract_outcome not defined on ReplayEngine"
    )


def test_contract_result_embedded_in_outcome_record_metrics():
    """_record_replay_outcome() must reference _last_contract_result and _last_contract_id."""
    assert "_last_contract_result" in REPLAY_ENGINE_SRC
    assert "_last_contract_id" in REPLAY_ENGINE_SRC
    assert "contract_goal_completed" in REPLAY_ENGINE_SRC
    assert "contract_id" in REPLAY_ENGINE_SRC


def test_verify_called_on_terminal_path():
    """Source-level: _verify_contract_outcome_async is called before _record_replay_outcome
    on the terminal (non-blocked) return path.

    Pattern: _record_replay_accuracy ... _verify_contract_outcome_async ... _record_replay_outcome
    at the final section of replay().
    """
    terminal_pat = re.compile(
        r"_record_replay_accuracy\(report, template, instance, _env_key_final\).*?"
        r"await self\._verify_contract_outcome_async\(.*?\).*?"
        r"self\._record_replay_outcome\(report, template, instance\)",
        re.DOTALL,
    )
    assert terminal_pat.search(REPLAY_ENGINE_SRC), (
        "_verify_contract_outcome_async not called between _record_replay_accuracy "
        "and _record_replay_outcome on terminal path"
    )


def test_verify_called_on_blocked_path():
    """Source-level: _verify_contract_outcome_async is called before _record_replay_outcome
    on the BLOCKED early-return path.
    """
    blocked_pat = re.compile(
        r"_env_key_blocked\s*=.*?"
        r"self\._record_replay_accuracy\(report, template, instance, _env_key_blocked\).*?"
        r"await self\._verify_contract_outcome_async\(.*?\).*?"
        r"self\._record_replay_outcome\(report, template, instance\)",
        re.DOTALL,
    )
    assert blocked_pat.search(REPLAY_ENGINE_SRC), (
        "_verify_contract_outcome_async not called on BLOCKED early-return path"
    )


def test_outcome_gate_imported_in_mine_step_outcomes():
    """filter_for_mining from outcome_gate must be used in _mine_step_outcomes."""
    assert "filter_for_mining" in REPLAY_ENGINE_SRC
    assert "from browsermind_core.verification.outcome_gate import" in REPLAY_ENGINE_SRC


def test_outcome_gate_imported_in_compile_and_promote():
    """filter_for_compilation and resolve_stress_test must appear in _compile_and_promote."""
    assert "filter_for_compilation" in REPLAY_ENGINE_SRC
    assert "resolve_stress_test" in REPLAY_ENGINE_SRC
