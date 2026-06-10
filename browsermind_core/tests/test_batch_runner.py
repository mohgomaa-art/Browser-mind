"""Tests for BatchRunner execution harness.

Verifies:
  - BatchRunSpec label auto-generation
  - BatchRunResult.success / .status
  - BatchRunner.run() captures report on success
  - BatchRunner.run() captures error on exception without aborting
  - BatchRunner.summarise() computes correct counts
  - on_result callback is called per run
  - Source-level: replay_engine passes prior_belief to resolver
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock


# ── BatchRunSpec ──────────────────────────────────────────────────────────────

def test_batch_run_spec_label_auto():
    from browsermind_core.evaluation.batch_runner import BatchRunSpec
    tmpl = MagicMock()
    tmpl.name = "login_github"
    spec = BatchRunSpec(template=tmpl, site_key="github", instance=MagicMock())
    assert spec.label == "login_github@github"


def test_batch_run_spec_label_override():
    from browsermind_core.evaluation.batch_runner import BatchRunSpec
    tmpl = MagicMock()
    tmpl.name = "login"
    spec = BatchRunSpec(template=tmpl, site_key="github", instance=MagicMock(), label="custom_label")
    assert spec.label == "custom_label"


# ── BatchRunResult ────────────────────────────────────────────────────────────

def test_batch_run_result_success():
    from browsermind_core.evaluation.batch_runner import BatchRunResult, BatchRunSpec
    spec = BatchRunSpec(template=MagicMock(), site_key="github", instance=MagicMock())
    report = MagicMock()
    report.status = "SUCCESS"
    result = BatchRunResult(spec=spec, report=report)
    assert result.success is True
    assert result.status == "SUCCESS"


def test_batch_run_result_error():
    from browsermind_core.evaluation.batch_runner import BatchRunResult, BatchRunSpec
    spec = BatchRunSpec(template=MagicMock(), site_key="github", instance=MagicMock())
    result = BatchRunResult(spec=spec, error="connection refused")
    assert result.success is False
    assert result.status == "ERROR"


def test_batch_run_result_failed_status():
    from browsermind_core.evaluation.batch_runner import BatchRunResult, BatchRunSpec
    spec = BatchRunSpec(template=MagicMock(), site_key="github", instance=MagicMock())
    report = MagicMock()
    report.status = "FAILED"
    result = BatchRunResult(spec=spec, report=report)
    assert result.success is False
    assert result.status == "FAILED"


# ── BatchRunner.run() ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_batch_runner_captures_report():
    from browsermind_core.evaluation.batch_runner import BatchRunner, BatchRunSpec

    report = MagicMock()
    report.status = "SUCCESS"

    engine = MagicMock()
    engine.auth_session.entry.key = "github"
    engine.replay = AsyncMock(return_value=report)

    async def factory(site_key):
        return engine

    spec = BatchRunSpec(template=MagicMock(), site_key="github", instance=MagicMock())
    results = await BatchRunner().run([spec], factory)
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].report is report


@pytest.mark.asyncio
async def test_batch_runner_captures_error_without_aborting():
    from browsermind_core.evaluation.batch_runner import BatchRunner, BatchRunSpec

    async def factory(site_key):
        raise RuntimeError("playwright not installed")

    specs = [
        BatchRunSpec(template=MagicMock(), site_key="github", instance=MagicMock()),
        BatchRunSpec(template=MagicMock(), site_key="gitlab", instance=MagicMock()),
    ]
    results = await BatchRunner().run(specs, factory)
    assert len(results) == 2
    for r in results:
        assert r.error is not None


@pytest.mark.asyncio
async def test_batch_runner_on_result_callback():
    from browsermind_core.evaluation.batch_runner import BatchRunner, BatchRunSpec

    report = MagicMock()
    report.status = "SUCCESS"

    engine = MagicMock()
    engine.auth_session.entry.key = "github"
    engine.replay = AsyncMock(return_value=report)

    async def factory(site_key):
        return engine

    called = []

    def on_result(r):
        called.append(r)

    specs = [BatchRunSpec(template=MagicMock(), site_key="github", instance=MagicMock())]
    await BatchRunner(on_result=on_result).run(specs, factory)
    assert len(called) == 1


# ── BatchRunner.summarise() ───────────────────────────────────────────────────

def test_batch_runner_summarise():
    from browsermind_core.evaluation.batch_runner import BatchRunner, BatchRunResult, BatchRunSpec

    def _spec(site):
        tmpl = MagicMock()
        tmpl.name = "t"
        return BatchRunSpec(template=tmpl, site_key=site, instance=MagicMock())

    def _result(spec, status):
        r = MagicMock()
        r.status = status
        return BatchRunResult(spec=spec, report=r)

    results = [
        _result(_spec("github"), "SUCCESS"),
        _result(_spec("github"), "FAILED"),
        _result(_spec("gitlab"), "SUCCESS"),
        BatchRunResult(spec=_spec("gitlab"), error="boom"),
    ]
    summary = BatchRunner().summarise(results)
    assert summary["total"] == 4
    assert summary["success"] == 2
    assert summary["error"] == 1
    assert summary["by_env"]["github"]["success"] == 1
    assert summary["by_env"]["gitlab"]["success"] == 1


# ── Source-level: prior_belief wired in replay_engine ────────────────────────

def test_replay_engine_passes_prior_belief_to_resolver():
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1] / "runtime" / "replay_engine.py"
    ).read_text(encoding="utf-8")
    assert "prior_belief=_prior_belief" in src
    assert "_prior_belief = None" in src
    assert "belief_from_attribution" in src


def test_target_resolver_resolve_accepts_prior_belief():
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1] / "runtime" / "target_resolver.py"
    ).read_text(encoding="utf-8")
    assert "prior_belief" in src
    assert "adjust_strategy_order" in src
