# browsermind_core/execution/playwright_executor.py
"""
Playwright Capability Executor.
Bridges abstract capability names to real page actions on the local mock app.
"""
import re
from typing import List, Dict, Any
from playwright.async_api import Page

class PlaywrightCapabilityExecutor:
    def __init__(self, page: Page, base_url: str = "http://127.0.0.1:8090"):
        self.page = page
        self.base_url = base_url

    async def execute_capability_path(self, path: List[str]) -> Dict[str, Any]:
        """
        Executes a sequence of capabilities in the browser.
        Returns the resulting data artifact.
        """
        path_tuple = tuple(path)
        
        # 1. Vault OTP generation path
        if path_tuple == ("retrieve_credential", "generate_otp"):
            return await self._execute_vault_otp()
            
        # 2. Email verification code search path
        elif path_tuple == ("search_email", "read_email"):
            return await self._execute_email_otp()
            
        # 3. Forgot Password / reset link path
        elif path_tuple == ("request_reset_link", "read_reset_email"):
            return await self._execute_reset_link()

        return {}

    async def _execute_vault_otp(self) -> Dict[str, Any]:
        try:
            await self.page.goto(f"{self.base_url}/vault")
            await self.page.wait_for_selector("#otp-code", timeout=3000)
            otp = (await self.page.locator("#otp-code").inner_text()).strip()
            status = (await self.page.locator("#vault-status").inner_text()).strip()
            
            return {
                "otp": otp,
                "expired": status == "EXPIRED"
            }
        except Exception as e:
            return {"error": str(e)}

    async def _execute_email_otp(self) -> Dict[str, Any]:
        try:
            await self.page.goto(f"{self.base_url}/email-client")
            await self.page.wait_for_selector("#emails-container", timeout=3000)
            
            # Find all email items and scan for dynamic OTP
            email_bodies = await self.page.locator(".email-body").all_inner_texts()
            for body in reversed(email_bodies):  # Start from newest
                match = re.search(r"\b(\d{6})\b", body)
                if match:
                    return {
                        "otp": match.group(1),
                        "expired": False
                    }
            return {}
        except Exception as e:
            return {"error": str(e)}

    async def _execute_reset_link(self) -> Dict[str, Any]:
        try:
            await self.page.goto(f"{self.base_url}/email-client")
            await self.page.wait_for_selector("#emails-container", timeout=3000)
            
            email_bodies = await self.page.locator(".email-body").all_inner_texts()
            for body in reversed(email_bodies):
                match = re.search(r"http://[^\s]+", body)
                if match:
                    return {
                        "reset_link": match.group(0),
                        "expired": False
                    }
            return {}
        except Exception as e:
            return {"error": str(e)}
