import pytest
from browsermind_core.agent.router import (
    PolicyRouter,
    AccessibilityExecutor,
    ContextExecutor,
    AuthenticatedExecutor,
    VisualExecutor,
)
from browsermind_core.tests.test_boundary_awareness import MockPage

@pytest.mark.asyncio
async def test_policy_router_routing():
    router = PolicyRouter()
    page = MockPage()
    
    # Accessibility routing
    assert isinstance(await router.route("Search", page), AccessibilityExecutor)
    assert isinstance(await router.route("Navigation", page), AccessibilityExecutor)
    assert isinstance(await router.route("Discovery", page), AccessibilityExecutor)
    assert isinstance(await router.route("Filtering", page), AccessibilityExecutor)
    assert isinstance(await router.route("Checkout", page), AccessibilityExecutor)
    
    # Context routing
    assert isinstance(await router.route("Profile", page, {"profile_data": {}}), ContextExecutor)
    
    # Authenticated routing
    assert isinstance(await router.route("Settings", page), AuthenticatedExecutor)
    assert isinstance(await router.route("Auth", page), AuthenticatedExecutor)
    
    # Fallback routing
    assert isinstance(await router.route("UnknownFlow", page), VisualExecutor)
