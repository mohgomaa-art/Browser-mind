# browsermind_core/agent/router.py
"""Policy Router & Specialized Executors for the P7 Flow-Aware Agent.

Routes high-level Flow Domains to their target Execution Policies (Solvers).
"""
import asyncio
from playwright.async_api import Page, Locator

class BaseExecutor:
    """Base class for execution policies."""
    def __init__(self):
        pass


class AccessibilityExecutor(BaseExecutor):
    """Executes actions using accessibility tree landmarks, roles, and visual overrides."""

    async def execute_search(self, page: Page, query: str) -> bool:
        """Information-Seeking: Search."""
        search_trigger = page.locator("[aria-label*='Search' i], [role='search']").first
        if await search_trigger.is_visible():
            await search_trigger.click()
        search_input = page.locator("input[type='search'], [role='searchbox'], input[type='text']").first
        await search_input.fill(query)
        await search_input.press("Enter")
        return True

    async def execute_navigation(self, page: Page) -> bool:
        """Information-Seeking: Sequential navigation landmark traversal."""
        # Locate all visible navigation containers
        navs = await page.locator("nav, [role='navigation'], [role='menubar'], [role='menu']").all()
        for nav in navs:
            if not await nav.is_visible():
                continue
            # Find first visible interactive link/menuitem inside the navigation container
            link = nav.locator("a[href]:visible, [role='link']:visible, [role='menuitem']:visible").first
            if await link.count() > 0:
                await link.click()
                return True
                
        # Fallback: look for dropdown controls to expand
        expandables = await page.locator("[aria-expanded='false'], [aria-haspopup='true'], [aria-haspopup='menu']").all()
        for exp in expandables:
            if await exp.is_visible():
                await exp.click()
                await asyncio.sleep(0.5)
                link = page.locator("nav a[href]:visible, [role='navigation'] a[href]:visible, [role='menuitem']:visible").first
                if await link.count() > 0:
                    await link.click()
                    return True
                    
        # Fallback: structural links inside header/footer
        fallback_link = page.locator("header a[href]:visible, footer a[href]:visible").first
        if await fallback_link.count() > 0:
            await fallback_link.click()
            return True
            
        raise Exception("Navigation semantic executor could not locate a visible navigation link.")

    async def execute_discovery(self, page: Page) -> bool:
        """Information-Seeking: Discovery feed content selection."""
        main = page.locator("main, table").first
        article = main.locator("a[href^='http']").first
        await article.click()
        return True

    async def execute_filtering(self, page: Page) -> bool:
        """Information-Seeking: Filter selection inside complementary containers."""
        # Identify complementary/filter containers
        filter_container = page.locator("aside, [role='complementary'], form").first
        if await filter_container.count() == 0 or not await filter_container.is_visible():
            filter_container = page.locator("body")
            
        # Find checkable/toggle elements
        filters = await filter_container.locator(
            "input[type='checkbox'], input[type='radio'], [role='checkbox'], [role='radio'], [role='switch'], button[aria-pressed]"
        ).all()
        
        for f in filters:
            parent_label = f.locator("xpath=ancestor::label").first
            if await f.is_visible() or (await parent_label.count() > 0 and await parent_label.is_visible()):
                is_input = await f.evaluate("el => el.tagName == 'INPUT'")
                type_attr = await f.get_attribute("type")
                if is_input and type_attr in ["checkbox", "radio"]:
                    await f.check(force=True)
                else:
                    await f.click(force=True)
                return True
                
        raise Exception("Filtering semantic executor could not locate a checkable filter control.")

    async def execute_checkout(self, page: Page) -> bool:
        """Security/Transaction-Bound: Standard buttons inside landmarks."""
        add_btn = page.locator("button").filter(has_text="Add to cart").first
        await add_btn.click()
        checkout = page.locator("button").filter(has_text="Checkout").first
        await checkout.click()
        return True


class FailureOntologyDiagnostic(Exception):
    """Exception raised when the agent detects a structural/environmental boundary and halts execution."""
    def __init__(self, flow_name: str, boundary_type: str, confidence: float, evidence: list[str], suggested_policy: str | None = None, recoverable: bool = True):
        message = f"[{boundary_type}] Halted flow '{flow_name}' due to: {', '.join(evidence)}"
        super().__init__(message)
        self.flow_name = flow_name
        self.boundary_type = boundary_type
        self.confidence = confidence
        self.evidence = evidence
        self.suggested_policy = suggested_policy
        self.recoverable = recoverable

    def to_dict(self) -> dict:
        return {
            "flow_name": self.flow_name,
            "boundary_type": self.boundary_type,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "suggested_policy": self.suggested_policy,
            "recoverable": self.recoverable,
            "status": "Halting execution due to environmental boundary"
        }


class ContextExecutor(BaseExecutor):
    """Executes actions on dynamic forms requiring context propagation."""
    async def execute(self, page: Page, context: dict) -> bool:
        raise NotImplementedError("ContextExecutor is not yet fully implemented.")


class AuthenticatedExecutor(BaseExecutor):
    """Executes actions within authenticated scope or setting routes."""
    async def execute(self, page: Page, context: dict) -> bool:
        raise NotImplementedError("AuthenticatedExecutor is not yet fully implemented.")


class VisualExecutor(BaseExecutor):
    """Executes actions using precision templates, coordinates, or pixel fallback."""
    async def execute(self, page: Page, context: dict) -> bool:
        raise NotImplementedError("VisualExecutor is not yet fully implemented.")


class PolicyRouter:
    """Policy Router to match Flow Domains with their corresponding Execution Policies."""

    def __init__(self):
        self.accessibility_executor = AccessibilityExecutor()
        self.context_executor = ContextExecutor()
        self.authenticated_executor = AuthenticatedExecutor()
        self.visual_executor = VisualExecutor()

    async def route(self, flow_name: str, page: Page, context: dict = None) -> BaseExecutor:
        """Route a high-level Flow Domain to its target executor policy, checking context prerequisites and live DOM state."""
        flow_lower = flow_name.lower()
        ctx = context or {}
        
        # 1. Environmental Check: Rate Limiting
        body_text = ""
        body = page.locator("body")
        if await body.count() > 0:
            body_text = (await body.inner_text()).lower()
        if "too many requests" in body_text or "rate limit exceeded" in body_text:
            raise FailureOntologyDiagnostic(
                flow_name=flow_name,
                boundary_type="RATE_LIMITED",
                confidence=0.9,
                evidence=["Rate limit indicator text found in page body"],
                suggested_policy=None,
                recoverable=False
            )
            
        # 2. Environmental Check: Captcha
        captcha_iframes = await page.locator("iframe[src*='recaptcha'], iframe[src*='hcaptcha'], div.g-recaptcha, div#g-recaptcha").all()
        if len(captcha_iframes) > 0:
            raise FailureOntologyDiagnostic(
                flow_name=flow_name,
                boundary_type="CAPTCHA_PRESENT",
                confidence=1.0,
                evidence=["ReCaptcha/hCaptcha iframe or element found in DOM"],
                suggested_policy=None,
                recoverable=False
            )
            
        # 3. Flow Routing with Context and DOM/URL Checks
        if flow_lower in ["search", "navigation", "discovery", "filtering", "checkout"]:
            return self.accessibility_executor
            
        elif flow_lower == "profile":
            current_url = page.url.lower()
            if "/join" in current_url or "/signup" in current_url or "/register" in current_url:
                if "profile_data" not in ctx:
                    raise FailureOntologyDiagnostic(
                        flow_name=flow_name,
                        boundary_type="SESSION_REQUIRED",
                        confidence=0.9,
                        evidence=["Redirected to registration/signup gate URL", f"Current URL: {page.url}"],
                        suggested_policy="ContextExecutor",
                        recoverable=True
                    )
            if "profile_data" not in ctx:
                raise FailureOntologyDiagnostic(
                    flow_name=flow_name,
                    boundary_type="SESSION_REQUIRED",
                    confidence=1.0,
                    evidence=["No profile context data provided for registration flow"],
                    suggested_policy="ContextExecutor",
                    recoverable=True
                )
            return self.context_executor
            
        elif flow_lower == "settings":
            current_url = page.url.lower()
            if ("/login" in current_url or "/signin" in current_url or "/settings" in current_url) and "session_cookies" not in ctx and "auth_token" not in ctx:
                raise FailureOntologyDiagnostic(
                    flow_name=flow_name,
                    boundary_type="SESSION_REQUIRED",
                    confidence=0.95,
                    evidence=["Redirected to login gate URL on Settings request", f"Current URL: {page.url}"],
                    suggested_policy="AuthenticatedExecutor",
                    recoverable=True
                )
            return self.authenticated_executor
            
        elif flow_lower == "auth":
            current_url = page.url.lower()
            if "/login" in current_url or "/signin" in current_url:
                if "credentials" not in ctx:
                    raise FailureOntologyDiagnostic(
                        flow_name=flow_name,
                        boundary_type="CREDENTIALS_REQUIRED",
                        confidence=1.0,
                        evidence=["On login gate URL, no credentials context provided"],
                        suggested_policy="AuthenticatedExecutor",
                        recoverable=True
                    )
            return self.authenticated_executor
            
        else:
            return self.visual_executor
