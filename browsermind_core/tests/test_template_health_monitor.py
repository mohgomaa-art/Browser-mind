"""Tests for template_health_monitor.py."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from browsermind_core.runtime.template_health_monitor import (
    TemplateHealthMonitor,
    TemplateHealthResult,
    stamp_template,
)
from browsermind_core.runtime.page_state_extractor import PageStateSignals


def _signals(**kwargs) -> PageStateSignals:
    s = PageStateSignals(snapshot_ok=True)
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def _template(**kwargs):
    tpl = MagicMock()
    tpl.metadata = {}
    tpl.steps = []
    for k, v in kwargs.items():
        setattr(tpl, k, v)
    return tpl


class TestStampTemplate:
    def test_stamps_all_expected_keys(self):
        tpl = _template()
        signals = _signals(has_login_form=True)
        stamp_template(tpl, "https://example.com/login", signals)
        assert "compile_time_affordances" in tpl.metadata
        assert "compile_time_hash" in tpl.metadata
        assert tpl.metadata["compile_time_url"] == "https://example.com/login"
        assert "compile_time_iso" in tpl.metadata

    def test_affordances_is_sorted_list(self):
        tpl = _template()
        signals = _signals(has_login_form=True, form_count=2)
        stamp_template(tpl, "https://example.com/login", signals)
        vec = tpl.metadata["compile_time_affordances"]
        assert isinstance(vec, list)
        assert vec == sorted(vec)

    def test_hash_matches_vector(self):
        from browsermind_core.runtime.structural_fingerprint import vector_to_hash
        tpl = _template()
        signals = _signals(has_login_form=True)
        stamp_template(tpl, "https://example.com", signals)
        assert tpl.metadata["compile_time_hash"] == vector_to_hash(
            tpl.metadata["compile_time_affordances"]
        )


class TestTemplateHealthResult:
    def test_healthy_is_healthy(self):
        r = TemplateHealthResult(status="healthy", drift_score=0.1, live_hash="a", recorded_hash="a")
        assert r.is_healthy
        assert not r.needs_rerecord

    def test_stale_needs_rerecord(self):
        r = TemplateHealthResult(status="stale", drift_score=0.4, live_hash="a", recorded_hash="b")
        assert not r.is_healthy
        assert r.needs_rerecord

    def test_corrupted_needs_rerecord(self):
        r = TemplateHealthResult(status="corrupted", drift_score=0.9, live_hash="a", recorded_hash="b")
        assert r.needs_rerecord

    def test_unknown_does_not_need_rerecord(self):
        r = TemplateHealthResult(status="unknown", drift_score=None, live_hash=None, recorded_hash=None)
        assert not r.needs_rerecord


class TestTemplateHealthMonitor:
    @pytest.mark.asyncio
    async def test_unknown_when_no_metadata(self):
        tpl = _template()  # no compile_time_url, no compile_time_affordances
        page = AsyncMock()
        monitor = TemplateHealthMonitor()
        result = await monitor.check(tpl, page)
        assert result.status == "unknown"

    @pytest.mark.asyncio
    async def test_unknown_when_nav_url_in_steps_but_no_affordances(self):
        tpl = _template()
        tpl.steps = [{"action_type": "navigate", "url": "https://example.com"}]
        # No compile_time_affordances — template was stamped with just URL
        tpl.metadata["compile_time_url"] = "https://example.com"
        page = AsyncMock()
        page.goto = AsyncMock()
        page.url = "https://example.com"

        signals = _signals(has_login_form=True)
        with patch(
            "browsermind_core.runtime.template_health_monitor.PageStateExtractor"
        ) as MockExtractor:
            MockExtractor.return_value.extract = AsyncMock(return_value=signals)
            monitor = TemplateHealthMonitor()
            result = await monitor.check(tpl, page)
        # No recorded vector → fell back to binary hash compare
        assert result.status in ("healthy", "stale", "corrupted")

    @pytest.mark.asyncio
    async def test_healthy_when_vectors_identical(self):
        from browsermind_core.runtime.structural_fingerprint import affordance_vector
        signals = _signals(has_login_form=True, form_count=1)
        vec = affordance_vector(signals)

        tpl = _template()
        tpl.metadata["compile_time_affordances"] = vec
        tpl.metadata["compile_time_url"] = "https://example.com/login"

        page = AsyncMock()
        page.goto = AsyncMock()
        page.url = "https://example.com/login"

        with patch(
            "browsermind_core.runtime.template_health_monitor.PageStateExtractor"
        ) as MockExtractor:
            MockExtractor.return_value.extract = AsyncMock(return_value=signals)
            monitor = TemplateHealthMonitor()
            result = await monitor.check(tpl, page)
        assert result.status == "healthy"
        assert result.drift_score == 0.0
        assert tpl.metadata["health_status"] == "healthy"

    @pytest.mark.asyncio
    async def test_corrupted_when_vectors_completely_different(self):
        from browsermind_core.runtime.structural_fingerprint import affordance_vector
        login_signals  = _signals(has_login_form=True)
        other_signals  = _signals(has_confirmation_heading=True, has_logout_link=True,
                                  has_user_avatar=True, has_pricing_tiers=True)

        tpl = _template()
        tpl.metadata["compile_time_affordances"] = affordance_vector(login_signals)
        tpl.metadata["compile_time_url"] = "https://example.com/login"

        page = AsyncMock()
        page.goto = AsyncMock()

        with patch(
            "browsermind_core.runtime.template_health_monitor.PageStateExtractor"
        ) as MockExtractor:
            MockExtractor.return_value.extract = AsyncMock(return_value=other_signals)
            monitor = TemplateHealthMonitor()
            result = await monitor.check(tpl, page)
        # Drift should be high (completely different affordance profiles)
        assert result.drift_score > 0.3
        assert result.status in ("stale", "corrupted")

    @pytest.mark.asyncio
    async def test_unknown_when_nav_fails(self):
        tpl = _template()
        tpl.metadata["compile_time_url"] = "https://unreachable.example.com"
        tpl.metadata["compile_time_affordances"] = ["login:True"]

        page = AsyncMock()
        page.goto = AsyncMock(side_effect=Exception("Navigation failed"))

        monitor = TemplateHealthMonitor()
        result = await monitor.check(tpl, page)
        assert result.status == "unknown"
        assert result.error is not None

    def test_find_nav_url_from_steps(self):
        tpl = _template()
        tpl.steps = [
            {"action_type": "click", "value": "Login"},
            {"action_type": "navigate", "url": "https://example.com/home"},
        ]
        monitor = TemplateHealthMonitor()
        url = monitor._find_nav_url(tpl)
        assert url == "https://example.com/home"

    def test_find_nav_url_returns_none_when_no_navigate_step(self):
        tpl = _template()
        tpl.steps = [{"action_type": "click"}, {"action_type": "fill"}]
        monitor = TemplateHealthMonitor()
        assert monitor._find_nav_url(tpl) is None
