import pytest
from browsermind_core.agent.router import (
    PolicyRouter,
    FailureOntologyDiagnostic,
    AccessibilityExecutor,
    ContextExecutor,
    AuthenticatedExecutor,
)

class MockLocator:
    def __init__(self, count_val=0, text_val="", all_val=None):
        self._count_val = count_val
        self._text_val = text_val
        self._all_val = all_val or []

    async def count(self):
        return self._count_val

    async def inner_text(self):
        return self._text_val

    async def all(self):
        return self._all_val

class MockPage:
    def __init__(self, url="https://example.com", body_text="", captchas=None):
        self.url = url
        self.body_text = body_text
        self.captchas = captchas or []

    def locator(self, selector):
        if selector == "body":
            return MockLocator(count_val=1, text_val=self.body_text)
        elif "captcha" in selector or "recaptcha" in selector:
            return MockLocator(count_val=len(self.captchas), all_val=self.captchas)
        return MockLocator()


@pytest.mark.asyncio
async def test_rate_limiting_boundary():
    router = PolicyRouter()
    # Mock page indicating Rate Limiting
    page = MockPage(body_text="Too many requests. Please try again later.")
    
    with pytest.raises(FailureOntologyDiagnostic) as exc_info:
        await router.route("Search", page)
    
    assert exc_info.value.boundary_type == "RATE_LIMITED"
    assert exc_info.value.recoverable is False
    assert exc_info.value.suggested_policy is None


@pytest.mark.asyncio
async def test_captcha_boundary():
    router = PolicyRouter()
    # Mock page containing a recaptcha iframe element
    page = MockPage(captchas=[MockLocator(count_val=1)])
    
    with pytest.raises(FailureOntologyDiagnostic) as exc_info:
        await router.route("Search", page)
        
    assert exc_info.value.boundary_type == "CAPTCHA_PRESENT"
    assert exc_info.value.recoverable is False
    assert exc_info.value.suggested_policy is None


@pytest.mark.asyncio
async def test_structural_flows_success():
    router = PolicyRouter()
    page = MockPage(url="https://en.wikipedia.org/wiki/Main_Page")
    
    # Structural flow routing does not require active context
    assert isinstance(await router.route("Search", page), AccessibilityExecutor)
    assert isinstance(await router.route("Navigation", page), AccessibilityExecutor)


@pytest.mark.asyncio
async def test_profile_gate_redirect_boundary():
    router = PolicyRouter()
    # Profile request redirected to github join url
    page = MockPage(url="https://github.com/join")
    
    # 1. Missing context -> SESSION_REQUIRED
    with pytest.raises(FailureOntologyDiagnostic) as exc_info:
        await router.route("Profile", page)
    assert exc_info.value.boundary_type == "SESSION_REQUIRED"
    assert exc_info.value.suggested_policy == "ContextExecutor"
    assert exc_info.value.recoverable is True
    
    # 2. Rescued with profile data context
    exec_policy = await router.route("Profile", page, {"profile_data": {"email": "test@test.com"}})
    assert isinstance(exec_policy, ContextExecutor)


@pytest.mark.asyncio
async def test_settings_gate_redirect_boundary():
    router = PolicyRouter()
    # Settings request redirected to login page
    page = MockPage(url="https://github.com/login")
    
    # 1. Missing context -> SESSION_REQUIRED
    with pytest.raises(FailureOntologyDiagnostic) as exc_info:
        await router.route("Settings", page)
    assert exc_info.value.boundary_type == "SESSION_REQUIRED"
    assert exc_info.value.suggested_policy == "AuthenticatedExecutor"
    assert exc_info.value.recoverable is True
    
    # 2. Rescued with authenticated cookies
    exec_policy = await router.route("Settings", page, {"session_cookies": ["cookie1"]})
    assert isinstance(exec_policy, AuthenticatedExecutor)


@pytest.mark.asyncio
async def test_auth_gate_credentials_boundary():
    router = PolicyRouter()
    page = MockPage(url="https://github.com/login")
    
    # 1. Missing credentials on login page -> CREDENTIALS_REQUIRED
    with pytest.raises(FailureOntologyDiagnostic) as exc_info:
        await router.route("Auth", page)
    assert exc_info.value.boundary_type == "CREDENTIALS_REQUIRED"
    assert exc_info.value.suggested_policy == "AuthenticatedExecutor"
    assert exc_info.value.recoverable is True
    
    # 2. Rescued with credentials
    exec_policy = await router.route("Auth", page, {"credentials": {"user": "foo", "pass": "bar"}})
    assert isinstance(exec_policy, AuthenticatedExecutor)
