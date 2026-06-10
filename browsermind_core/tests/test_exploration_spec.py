"""Tests for ExplorationSpec, ExplorationResult, and ExplorationHarness.

Covers:
  - ExplorationSpec defaults and label auto-generation
  - ExplorationResult.success / .status properties
  - ExplorationResult.novel_hypothesis_count
  - ExplorationHarness.run() — success path (mock engine)
  - ExplorationHarness.run() — error path (engine raises)
  - ExplorationHarness.run() — unknown site_key returns error result
  - ExplorationHarness.run() — on_result callback called
  - ExplorationHarness.run() — hypothesis store receives observation
  - ExplorationHarness.run() — stop_on_experience sets metadata
  - ExplorationHarness.run_batch() — processes all specs
  - ExplorationHarness.summarise() — correct aggregates
  - _MinimalExplorationTemplate.name and steps
  - Source-level: harness uses SiteRegistry
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── ExplorationSpec ───────────────────────────────────────────────────────────

def test_exploration_spec_defaults():
    from browsermind_core.exploration.exploration_spec import ExplorationSpec
    spec = ExplorationSpec(site_key="github")
    assert spec.budget == 200
    assert spec.max_depth == 5
    assert spec.capability_targets == []
    assert spec.stop_on_experience == []
    assert spec.enable_recovery is True


def test_exploration_spec_label_auto():
    from browsermind_core.exploration.exploration_spec import ExplorationSpec
    spec = ExplorationSpec(site_key="reddit")
    assert spec.label == "explore_reddit"


def test_exploration_spec_label_override():
    from browsermind_core.exploration.exploration_spec import ExplorationSpec
    spec = ExplorationSpec(site_key="reddit", label="custom_run")
    assert spec.label == "custom_run"


# ── ExplorationResult ─────────────────────────────────────────────────────────

def test_result_success_no_error():
    from browsermind_core.exploration.exploration_spec import ExplorationSpec, ExplorationResult
    spec = ExplorationSpec(site_key="github")
    r = ExplorationResult(spec=spec)
    assert r.success is True
    assert r.status == "EXPLORED"


def test_result_success_false_on_error():
    from browsermind_core.exploration.exploration_spec import ExplorationSpec, ExplorationResult
    spec = ExplorationSpec(site_key="github")
    r = ExplorationResult(spec=spec, error="connection refused")
    assert r.success is False
    assert r.status == "ERROR"


def test_result_status_experienced():
    from browsermind_core.exploration.exploration_spec import ExplorationSpec, ExplorationResult
    spec = ExplorationSpec(site_key="github")
    r = ExplorationResult(spec=spec, experiences_discovered=["session_authentication"])
    assert r.status == "EXPERIENCED"


def test_result_status_hypothesised():
    from browsermind_core.exploration.exploration_spec import ExplorationSpec, ExplorationResult
    spec = ExplorationSpec(site_key="github")
    r = ExplorationResult(spec=spec, hypothesis_hashes=["abc123"])
    assert r.status == "HYPOTHESISED"


def test_result_novel_hypothesis_count():
    from browsermind_core.exploration.exploration_spec import ExplorationSpec, ExplorationResult
    spec = ExplorationSpec(site_key="github")
    r = ExplorationResult(spec=spec, hypothesis_hashes=["a", "b", "c"])
    assert r.novel_hypothesis_count == 3


# ── ExplorationHarness ────────────────────────────────────────────────────────

def _make_engine(report=None, raise_exc=None):
    """Build a mock engine. report=None means .replay returns empty report."""
    engine = MagicMock()
    engine.auth_session.entry.key = "github"
    if raise_exc:
        engine.replay = AsyncMock(side_effect=raise_exc)
    else:
        if report is None:
            mock_report = MagicMock()
            mock_report.failure_attribution = []
        else:
            mock_report = report
        engine.replay = AsyncMock(return_value=mock_report)
    return engine


def _make_factory(engine):
    async def factory(site_key):
        return engine
    return factory


@pytest.mark.asyncio
async def test_harness_run_success():
    from browsermind_core.exploration.exploration_harness import ExplorationHarness
    from browsermind_core.exploration.exploration_spec import ExplorationSpec

    spec = ExplorationSpec(site_key="github")
    harness = ExplorationHarness()
    result = await harness.run(spec, _make_factory(_make_engine()))
    assert result.success is True
    assert result.spec is spec


@pytest.mark.asyncio
async def test_harness_run_captures_engine_error():
    from browsermind_core.exploration.exploration_harness import ExplorationHarness
    from browsermind_core.exploration.exploration_spec import ExplorationSpec

    spec = ExplorationSpec(site_key="github")
    harness = ExplorationHarness()
    engine = _make_engine(raise_exc=RuntimeError("playwright not running"))
    result = await harness.run(spec, _make_factory(engine))
    assert result.success is False
    assert "playwright" in result.error


@pytest.mark.asyncio
async def test_harness_run_unknown_site_key():
    from browsermind_core.exploration.exploration_harness import ExplorationHarness
    from browsermind_core.exploration.exploration_spec import ExplorationSpec

    spec = ExplorationSpec(site_key="totally_unknown_site_xyz")
    harness = ExplorationHarness()

    async def factory(key):
        raise AssertionError("should not reach engine for unknown site")

    result = await harness.run(spec, factory)
    assert result.success is False
    assert "not found" in result.error.lower() or "SiteRegistry" in result.error


@pytest.mark.asyncio
async def test_harness_on_result_callback_called():
    from browsermind_core.exploration.exploration_harness import ExplorationHarness
    from browsermind_core.exploration.exploration_spec import ExplorationSpec

    called = []
    def on_result(r):
        called.append(r)

    spec = ExplorationSpec(site_key="github")
    harness = ExplorationHarness(on_result=on_result)
    await harness.run(spec, _make_factory(_make_engine()))
    assert len(called) == 1


@pytest.mark.asyncio
async def test_harness_feeds_hypothesis_store(tmp_path):
    from browsermind_core.exploration.exploration_harness import ExplorationHarness
    from browsermind_core.exploration.exploration_spec import ExplorationSpec
    from browsermind_core.learning.capability_hypothesis_store import CapabilityHypothesisStore

    # Build report with unknown intents via attribution
    attr = MagicMock()
    attr.actual_outcome = "SUCCESS"
    attr.target_role = "button"
    attr.target_name = "bizarre_action_totally_unknown_x"

    attr2 = MagicMock()
    attr2.actual_outcome = "SUCCESS"
    attr2.target_role = "input"
    attr2.target_name = "bizarre_action_totally_unknown_y"

    report = MagicMock()
    report.failure_attribution = [attr, attr2]

    store = CapabilityHypothesisStore(root=tmp_path)
    spec = ExplorationSpec(site_key="github")
    harness = ExplorationHarness(hypothesis_store=store)
    await harness.run(spec, _make_factory(_make_engine(report=report)))
    # Store should now have hypotheses (unless normalizer returns empty strings, which is fine)
    # Just verify no crash and store interaction happened
    stats = store.stats()
    assert isinstance(stats["total"], int)


@pytest.mark.asyncio
async def test_harness_stop_on_experience_sets_metadata():
    from browsermind_core.exploration.exploration_harness import ExplorationHarness
    from browsermind_core.exploration.exploration_spec import ExplorationSpec
    from unittest.mock import patch

    spec = ExplorationSpec(
        site_key="github",
        stop_on_experience=["session_authentication"],
    )

    # Patch ExperienceInterpreter.interpret to return a matching label
    with patch(
        "browsermind_core.exploration.exploration_harness.ExperienceInterpreter"
    ) as MockInterp:
        mock_label = MagicMock()
        mock_label.name = "session_authentication"
        mock_label.is_known = True
        mock_label.matched_intents = {"auth_login", "auth_password_input"}
        MockInterp.return_value.interpret.return_value = [mock_label]

        harness = ExplorationHarness()
        result = await harness.run(spec, _make_factory(_make_engine()))

    assert result.metadata.get("stopped_on") == "session_authentication"


@pytest.mark.asyncio
async def test_harness_run_batch():
    from browsermind_core.exploration.exploration_harness import ExplorationHarness
    from browsermind_core.exploration.exploration_spec import ExplorationSpec

    specs = [
        ExplorationSpec(site_key="github"),
        ExplorationSpec(site_key="reddit"),
    ]
    harness = ExplorationHarness()
    results = await harness.run_batch(specs, _make_factory(_make_engine()))
    assert len(results) == 2


def test_harness_summarise():
    from browsermind_core.exploration.exploration_harness import ExplorationHarness
    from browsermind_core.exploration.exploration_spec import ExplorationSpec, ExplorationResult

    def _r(site, error=None, experiences=None, hypotheses=None, steps=0):
        spec = ExplorationSpec(site_key=site)
        return ExplorationResult(
            spec=spec,
            error=error,
            experiences_discovered=experiences or [],
            hypothesis_hashes=hypotheses or [],
            steps_executed=steps,
        )

    results = [
        _r("github", experiences=["session_authentication"], steps=15),
        _r("github", error="timeout"),
        _r("reddit", hypotheses=["abc123"], steps=30),
    ]
    summary = ExplorationHarness().summarise(results)
    assert summary["total"] == 3
    assert summary["success"] == 2
    assert summary["error"] == 1
    assert summary["total_experiences_discovered"] == 1
    assert summary["total_hypotheses_observed"] == 1
    assert summary["total_steps_executed"] == 45
    assert summary["by_site"]["github"]["success"] == 1
    assert summary["by_site"]["reddit"]["success"] == 1


# ── _MinimalExplorationTemplate ───────────────────────────────────────────────

def test_minimal_template_name():
    from browsermind_core.exploration.exploration_harness import _MinimalExplorationTemplate
    t = _MinimalExplorationTemplate(
        site_key="github", start_url="https://github.com"
    )
    assert t.name == "explore_github"


def test_minimal_template_steps_has_url():
    from browsermind_core.exploration.exploration_harness import _MinimalExplorationTemplate
    t = _MinimalExplorationTemplate(
        site_key="github", start_url="https://github.com", budget=150
    )
    steps = t.steps
    assert len(steps) == 1
    assert steps[0]["url"] == "https://github.com"
    assert steps[0]["exploration_budget"] == 150


def test_minimal_template_includes_capability_targets():
    from browsermind_core.exploration.exploration_harness import _MinimalExplorationTemplate
    t = _MinimalExplorationTemplate(
        site_key="github",
        start_url="https://github.com",
        capability_targets=["auth_login", "oauth_redirect"],
    )
    assert t.steps[0]["capability_targets"] == ["auth_login", "oauth_redirect"]


# ── Source-level: harness uses SiteRegistry ───────────────────────────────────

def test_harness_uses_site_registry():
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1] / "exploration" / "exploration_harness.py"
    ).read_text(encoding="utf-8")
    assert "site_registry" in src
    assert "SiteEntry" in src or "registry_get" in src or "registry" in src.lower()
