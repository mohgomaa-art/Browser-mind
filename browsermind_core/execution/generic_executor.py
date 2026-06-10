# browsermind_core/execution/generic_executor.py
"""
Generic Capability Executor.
Consumes capabilities and executes them via the PolicyRouter, completely decoupled from workflow goals.
"""
from typing import List, Dict, Any
from playwright.async_api import Page
from browsermind_core.agent.router import PolicyRouter

class GenericCapabilityExecutor:
    def __init__(self, page: Page, base_url: str = "http://127.0.0.1:8090"):
        self.page = page
        self.base_url = base_url
        self.router = PolicyRouter()

    async def execute_capability_path(self, path: List[str], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Executes a complete capability path in order.
        Returns the artifact produced by the final capability in the path.
        """
        ctx = context or {}
        last_artifact = {}
        for cap_name in path:
            cap_meta = self._get_capability_metadata(cap_name)
            last_artifact = await self.execute_capability(cap_name, cap_meta, ctx)
            ctx.update(last_artifact)
        return last_artifact

    async def run(self, cap_name: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Convenience method: run a single capability by name, auto-fetching its metadata.
        Use this instead of execute_capability(name, {}, context) to avoid empty cap_meta bugs.
        """
        cap_meta = self._get_capability_metadata(cap_name)
        return await self.execute_capability(cap_name, cap_meta, context or {})

    async def execute_capability(self, cap_name: str, cap_meta: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a single capability using generic execution policies.
        """
        # 1. Environment transition (Generic navigation to env_url)
        env_url = cap_meta.get("env_url", "")
        if env_url and self.page.url != env_url:
            await self.page.goto(env_url, wait_until="domcontentloaded")

        # 2. Map capability to flow domain (used only for navigate_email action)
        flow_name = self._map_capability_to_flow(cap_name)

        # 3. Run Policy Primitives
        action_type = cap_meta.get("action", "")
        artifact = {}

        if action_type == "type":
            selector = cap_meta["selector"]
            value = context.get(cap_meta.get("value_key", ""), cap_meta.get("value", ""))
            await self.page.fill(selector, value)
            if cap_meta.get("submit", False):
                await self.page.press(selector, "Enter")
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass

        elif action_type == "click":
            selector = cap_meta["selector"]
            await self.page.click(selector)
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass

        elif action_type == "type_click":
            await self.page.fill(cap_meta["type_selector"], context.get(cap_meta.get("value_key", ""), cap_meta.get("value", "")))
            await self.page.click(cap_meta["click_selector"])
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass

        elif action_type == "fill_multi":
            # Fill multiple form fields from context, then optionally submit.
            # fields: {context_key: css_selector}
            # defaults: {context_key: fallback_value}
            defaults = cap_meta.get("defaults", {})
            for field_key, selector in cap_meta.get("fields", {}).items():
                value = context.get(field_key, defaults.get(field_key, ""))
                await self.page.fill(selector, str(value))

        elif action_type == "click_sequence":
            # Click multiple selectors in order, wait for navigation after last click.
            selectors = cap_meta.get("selectors", [])
            for i, selector in enumerate(selectors):
                await self.page.click(selector)
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            
        elif action_type == "extract_form":
            extracted = {}
            for key, selector in cap_meta.get("selectors", {}).items():
                el = self.page.locator(selector)
                if await el.count() > 0:
                    text = (await el.inner_text()).strip()
                    extracted[key] = text
            if "status" in extracted:
                extracted["expired"] = (extracted["status"] == "EXPIRED")
            artifact = extracted
            
        elif action_type == "extract_regex":
            body_text = await self.page.locator(cap_meta.get("selector", "body")).inner_text()
            import re
            match = re.search(cap_meta["regex"], body_text)
            if match:
                artifact = {cap_meta.get("output_key", "result"): match.group(0)}
                
        elif action_type == "navigate_email":
            # Read email content using the email_id produced by search_email.
            # The email_id is the HTML id of the body element (e.g. "body-0").
            # Router is called here — the only action that actually needs it.
            import re
            executor = await self.router.route(flow_name, self.page, context)
            email_id = context.get("email_id", "body-0")
            body_el = self.page.locator(f"#{email_id}")
            if await body_el.count() > 0:
                body_text = await body_el.inner_text()
            else:
                body_text = await self.page.locator("body").inner_text()
            artifact = {"text": body_text}
            otp_match = re.search(r"\b(\d{6})\b", body_text)
            if otp_match:
                artifact["otp"] = otp_match.group(1)
            link_match = re.search(r"http://[^\s]+", body_text)
            if link_match:
                artifact["reset_link"] = link_match.group(0)

        elif action_type == "extract_email_id":
            # Navigate to email inbox and return the ID of the first email found.
            # No search form required — the inbox lists all emails directly.
            email_id_selector = cap_meta.get("email_id_selector", "[id^='body-']")
            default_id = cap_meta.get("default_id", "body-0")
            import re
            body_text = await self.page.locator("body").inner_text()
            # Check if any emails exist (inbox not empty)
            if "inbox is empty" not in body_text.lower():
                el = self.page.locator(email_id_selector).first
                if await el.count() > 0:
                    el_id = await el.get_attribute("id")
                    artifact = {"email_id": el_id or default_id}
                else:
                    artifact = {"email_id": default_id}
            else:
                artifact = {"email_id": None, "inbox_empty": True}

        return artifact

    def _map_capability_to_flow(self, cap_name: str) -> str:
        mapping = {
            "search_email": "Search",
            "read_email": "Navigation",
            "retrieve_credential": "Navigation",
            "generate_otp": "Navigation",
            "fill_login": "Auth",
            "submit_login": "Auth",
            "enter_otp": "Auth",
            "submit_otp": "Auth",
            "fill_checkout": "Checkout",
            "submit_checkout": "Checkout",
            "request_reset_link": "Auth",
            "read_reset_email": "Navigation",
            "search_information": "Search",
            "navigate_menu": "Navigation",
            "filter_xs_products": "Filtering",
            "update_profile_billing": "Profile",
            "submit_contact_form": "Auth"
        }
        return mapping.get(cap_name, "Visual")

    def _get_capability_metadata(self, cap_name: str) -> Dict[str, Any]:
        """Provides the generic primitive execution mappings for capabilities."""
        env_mappings = {
            "search_email": {
                "env_url": f"{self.base_url}/email-client",
                "action": "extract_email_id",
                "email_id_selector": "[id^='body-']",
                "output_key": "email_id",
                "default_id": "body-0"
            },
            "read_email": {
                "env_url": f"{self.base_url}/email-client",
                "action": "navigate_email"
            },
            "retrieve_credential": {
                "env_url": f"{self.base_url}/vault",
                "action": "extract_form",
                "selectors": {"username": "#vault-user", "password": "#vault-pass"}
            },
            "generate_otp": {
                "env_url": f"{self.base_url}/vault",
                "action": "extract_form",
                "selectors": {"otp": "#otp-code", "status": "#vault-status"}
            },
            "fill_login": {
                "env_url": f"{self.base_url}/login",
                "action": "fill_multi",
                "fields": {
                    "username": "#username",
                    "password": "#password",
                },
                "defaults": {
                    "username": "standard_user",
                    "password": "secret_sauce",
                }
            },
            "submit_login": {
                "env_url": f"{self.base_url}/login",
                "action": "click",
                "selector": "#login-btn"
            },
            "enter_otp": {
                "env_url": f"{self.base_url}/2fa",
                "action": "type",
                "selector": "#otp",
                "value_key": "otp"
            },
            "submit_otp": {
                "env_url": f"{self.base_url}/2fa",
                "action": "click",
                "selector": "#verify-btn"
            },
            "fill_checkout": {
                "env_url": f"{self.base_url}/checkout",
                "action": "type_click",
                "type_selector": "#address",
                "value_key": "address",
                "value": "123 AI Lane",
                "click_selector": "#card"
            },
            "submit_checkout": {
                "env_url": f"{self.base_url}/checkout",
                "action": "click",
                "selector": "#purchase-btn"
            },
            "request_reset_link": {
                "env_url": f"{self.base_url}/forgot-password",
                "action": "type_click",
                "type_selector": "#username",
                "value_key": "username",
                "value": "standard_user",
                "click_selector": "#recover-btn"
            },
            "read_reset_email": {
                "env_url": f"{self.base_url}/email-client",
                "action": "extract_regex",
                "selector": "body",
                "regex": r"http://[^\s]+",
                "output_key": "reset_link"
            },
            # Controlled Tasks
            "search_information": {
                "env_url": f"{self.base_url}/search",
                "action": "type",
                "selector": "#query",
                "value": "Verification",
                "submit": True
            },
            "navigate_menu": {
                "env_url": f"{self.base_url}/navigation",
                "action": "click",
                "selector": "#nav-item-1"
            },
            "filter_xs_products": {
                "env_url": f"{self.base_url}/filter",
                "action": "click_sequence",
                "selectors": ["#size-xs", "#filter-btn"]
            },
            "update_profile_billing": {
                "env_url": f"{self.base_url}/profile",
                "action": "type_click",
                "type_selector": "#address",
                "value": "456 Custom Lane",
                "click_selector": "#submit-profile-btn"
            },
            "submit_contact_form": {
                "env_url": f"{self.base_url}/contact",
                "action": "type_click",
                "type_selector": "#username",
                "value_key": "username",
                "value": "standard_user",
                "click_selector": "#submit-contact-btn"
            }
        }
        return env_mappings.get(cap_name, {})
