"""ActionExecutor — Executes semantic actions on resolved Playwright Locators."""
import asyncio
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlunparse

from playwright.async_api import Page, Locator


class ActionExecutionError(Exception):
    pass

class ActionTransitionSuccess(Exception):
    """Raised when an action succeeds but causes the target to detach (e.g. navigation)."""
    pass


class ActionExecutor:
    """
    P3A Scope: Only supports click, fill, submit.
    """

    def __init__(self, page: Page):
        self.page = page

    async def execute(self, action_type: str, loc: Optional[Locator], value: Optional[str] = None, url: str = "", enable_recovery: bool = True) -> None:
        """
        Execute the specified action on the locator.
        """
        try:
            if action_type == "navigate":
                # Special case: navigate action
                if url:
                    parsed_cur = urlparse(self.page.url)
                    parsed_target = urlparse(url)
                    norm_cur = urlunparse((parsed_cur.scheme, parsed_cur.netloc, parsed_cur.path.rstrip('/'), parsed_cur.params, parsed_cur.query, ''))
                    norm_target = urlunparse((parsed_target.scheme, parsed_target.netloc, parsed_target.path.rstrip('/'), parsed_target.params, parsed_target.query, ''))
                    
                    if norm_cur != norm_target:
                        await self.page.goto(url, wait_until="commit")
                return

            if loc is None:
                raise ActionExecutionError(f"Cannot execute '{action_type}' without a valid locator.")

            if action_type == "click":
                # Wait for element to be visible/stable before clicking
                await loc.click(timeout=10000)
                
            elif action_type == "fill":
                if value is None:
                    raise ActionExecutionError("Fill action requires a value.")
                input_type = await loc.evaluate(
                    "el => el.tagName.toLowerCase() === 'input' ? (el.type || '').toLowerCase() : ''"
                )
                if input_type == "file":
                    await loc.set_input_files(value, timeout=10000)
                    await asyncio.sleep(0.5)
                    return
                # We do a clear then fill to ensure clean state
                await loc.fill(value, timeout=10000)

            elif action_type in ("upload", "upload_file", "set_input_files"):
                if value is None:
                    raise ActionExecutionError("Upload action requires a file path.")
                await loc.set_input_files(value, timeout=10000)
                
            elif action_type == "submit":
                # Typically, submit is done by pressing Enter or clicking a button.
                # If target is a form, evaluate a submit on it, or just press enter.
                # Playwright doesn't have a direct loc.submit(), so we evaluate or dispatchEvent.
                # Or simply press Enter if it's an input field.
                tag_name = await loc.evaluate("el => el.tagName.toLowerCase()")
                if tag_name == "form":
                    await loc.evaluate("form => form.submit()")
                else:
                    await loc.press("Enter")
                    
            elif action_type == "keydown":
                if value:
                    await loc.press(value)
                    
            else:
                raise ActionExecutionError(f"Unsupported action type: {action_type}")
                
            # Wait a brief moment for any immediate client-side JS to trigger
            await asyncio.sleep(0.5)
            
        except Exception as e:
            err_str = str(e).lower()
            # If the action caused a navigation or DOM teardown, it's a success
            if action_type in ["submit", "click"] and ("target closed" in err_str or "detached" in err_str or "execution context was destroyed" in err_str or "navigating" in err_str):
                raise ActionTransitionSuccess(f"Transition Success: {str(e)}") from e
            raise ActionExecutionError(f"Failed to execute '{action_type}': {str(e)}") from e
