"""Tests for ReachEngine overlay state machine upgrade."""
import pytest
from browsermind_core.runtime.reach_engine import OverlayState, ReachEngine


class TestOverlayState:
    def test_initial_state_empty(self):
        state = OverlayState()
        assert len(state.dismissed_selectors) == 0
        assert len(state.css_suppressed_selectors) == 0
        assert state.session_marker_set is False

    def test_dismissed_selectors_is_mutable_set(self):
        state = OverlayState()
        state.dismissed_selectors.add("[role='dialog']")
        assert "[role='dialog']" in state.dismissed_selectors

    def test_two_engines_share_state(self):
        """OverlayState shared between two ReachEngine instances persists dismissals."""
        from unittest.mock import MagicMock
        page = MagicMock()
        shared = OverlayState()
        e1 = ReachEngine(page, overlay_state=shared)
        e2 = ReachEngine(page, overlay_state=shared)
        shared.dismissed_selectors.add(".cookie-banner")
        assert ".cookie-banner" in e2._overlay_state.dismissed_selectors

    def test_default_overlay_state_is_local(self):
        """When no OverlayState is passed, engine creates a private one."""
        from unittest.mock import MagicMock
        page = MagicMock()
        e1 = ReachEngine(page)
        e2 = ReachEngine(page)
        e1._overlay_state.dismissed_selectors.add(".x")
        assert ".x" not in e2._overlay_state.dismissed_selectors


class TestReachEngineCSSSuppression:
    @pytest.mark.asyncio
    async def test_css_suppress_called_on_reappearing_overlay(self):
        """An overlay already in dismissed_selectors triggers CSS suppression on second encounter."""
        from unittest.mock import AsyncMock, MagicMock, patch

        page = MagicMock()
        locator = AsyncMock()
        locator.scroll_into_view_if_needed = AsyncMock()
        locator.is_visible = AsyncMock(return_value=False)  # target not visible
        locator.is_enabled = AsyncMock(return_value=False)

        shared = OverlayState()
        shared.dismissed_selectors.add("[role='dialog']")  # pre-dismissed

        engine = ReachEngine(page, overlay_state=shared, dismiss_overlays=True)

        # Simulate: _find_overlay returns the already-dismissed selector
        engine._find_overlay = AsyncMock(return_value="[role='dialog']")
        engine._css_suppress = AsyncMock(return_value=True)
        engine._soft_dismiss = AsyncMock(return_value=True)
        engine._wait_for_quiescence = AsyncMock()
        engine._is_interactable = AsyncMock(return_value=False)

        result = await engine.reach(locator)

        engine._css_suppress.assert_called_once_with("[role='dialog']")
        engine._soft_dismiss.assert_not_called()
        assert result.css_suppressed is True

    @pytest.mark.asyncio
    async def test_soft_dismiss_on_first_encounter(self):
        from unittest.mock import AsyncMock, MagicMock

        page = MagicMock()
        locator = AsyncMock()
        locator.scroll_into_view_if_needed = AsyncMock()

        shared = OverlayState()
        engine = ReachEngine(page, overlay_state=shared, dismiss_overlays=True)
        engine._find_overlay = AsyncMock(return_value="[class*='cookie' i]")
        engine._soft_dismiss = AsyncMock(return_value=True)
        engine._css_suppress = AsyncMock(return_value=True)
        engine._wait_for_quiescence = AsyncMock()
        # First call: not interactable (overlay present); second call: interactable (after dismiss)
        engine._is_interactable = AsyncMock(side_effect=[False, True])
        engine._set_session_marker = AsyncMock()

        result = await engine.reach(locator)

        engine._soft_dismiss.assert_called_once()
        engine._css_suppress.assert_not_called()
        assert result.dismissed_overlay is True
        assert result.success is True
        assert "[class*='cookie' i]" in shared.dismissed_selectors

    @pytest.mark.asyncio
    async def test_session_marker_set_after_first_dismiss(self):
        from unittest.mock import AsyncMock, MagicMock

        page = MagicMock()
        locator = AsyncMock()
        locator.scroll_into_view_if_needed = AsyncMock()

        shared = OverlayState()
        engine = ReachEngine(page, overlay_state=shared)
        engine._find_overlay = AsyncMock(return_value=".cookie-banner")
        engine._soft_dismiss = AsyncMock(return_value=True)
        engine._wait_for_quiescence = AsyncMock()
        engine._is_interactable = AsyncMock(side_effect=[False, True])
        engine._set_session_marker = AsyncMock()

        await engine.reach(locator)
        engine._set_session_marker.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_dismiss_when_element_already_interactable(self):
        from unittest.mock import AsyncMock, MagicMock

        page = MagicMock()
        locator = AsyncMock()
        locator.scroll_into_view_if_needed = AsyncMock()

        engine = ReachEngine(page, overlay_state=OverlayState())
        engine._wait_for_quiescence = AsyncMock()
        engine._is_interactable = AsyncMock(return_value=True)
        engine._find_overlay = AsyncMock()

        result = await engine.reach(locator)

        engine._find_overlay.assert_not_called()
        assert result.success is True
        assert result.dismissed_overlay is False
