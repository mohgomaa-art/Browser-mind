"""
action_registry.py — Canonical registry of 80+ supported browser actions.

Actions are grouped into 14 families. Each entry declares:
  - name: canonical action type string
  - family: grouping for documentation and routing
  - requires_locator: False for page-level actions (navigate, screenshot, wait)
  - requires_value: True when a value payload is expected (fill, select, etc.)
  - description: short human-readable description
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ActionDefinition:
    name: str
    family: str
    requires_locator: bool
    requires_value: bool
    description: str
    aliases: tuple = ()


_REGISTRY: List[ActionDefinition] = [
    # --- navigation ---
    ActionDefinition("navigate", "navigation", False, True, "Navigate to a URL"),
    ActionDefinition("navigate_back", "navigation", False, False, "Browser back"),
    ActionDefinition("navigate_forward", "navigation", False, False, "Browser forward"),
    ActionDefinition("reload", "navigation", False, False, "Reload the current page"),
    ActionDefinition("navigate_new_tab", "navigation", False, True, "Open URL in new tab"),
    ActionDefinition("close_tab", "navigation", False, False, "Close current tab"),

    # --- click ---
    ActionDefinition("click", "click", True, False, "Left-click an element"),
    ActionDefinition("dblclick", "click", True, False, "Double-click an element"),
    ActionDefinition("right_click", "click", True, False, "Right-click (context menu)"),
    ActionDefinition("middle_click", "click", True, False, "Middle-click (new tab)"),
    ActionDefinition("click_by_text", "click", False, True, "Click element containing text"),

    # --- type/input ---
    ActionDefinition("fill", "input", True, True, "Clear and fill an input field",
                     aliases=("type", "input")),
    ActionDefinition("fill_append", "input", True, True, "Append text to an input (no clear)"),
    ActionDefinition("press_key", "input", True, True, "Press a keyboard key on focused element",
                     aliases=("keydown",)),
    ActionDefinition("press_keys", "input", True, True, "Press a key sequence"),
    ActionDefinition("clear", "input", True, False, "Clear an input field"),
    ActionDefinition("paste", "input", True, True, "Paste text via clipboard API"),

    # --- form ---
    ActionDefinition("submit", "form", True, False, "Submit a form",
                     aliases=("form_submit",)),
    ActionDefinition("select_option", "form", True, True, "Select a <select> option by value"),
    ActionDefinition("select_option_by_text", "form", True, True, "Select <select> option by label"),
    ActionDefinition("check", "form", True, False, "Check a checkbox"),
    ActionDefinition("uncheck", "form", True, False, "Uncheck a checkbox"),
    ActionDefinition("set_checked", "form", True, True, "Set checkbox to given boolean"),
    ActionDefinition("choose_radio", "form", True, True, "Select a radio button by value"),
    ActionDefinition("toggle_switch", "form", True, False, "Toggle an ARIA switch"),
    ActionDefinition("range_input", "form", True, True, "Set a range/slider value"),

    # --- scroll ---
    ActionDefinition("scroll_down", "scroll", False, False, "Scroll page down"),
    ActionDefinition("scroll_up", "scroll", False, False, "Scroll page up"),
    ActionDefinition("scroll_to", "scroll", True, False, "Scroll element into view"),
    ActionDefinition("scroll_to_bottom", "scroll", False, False, "Scroll to page bottom"),
    ActionDefinition("scroll_to_top", "scroll", False, False, "Scroll to page top"),
    ActionDefinition("scroll_by", "scroll", False, True, "Scroll page by pixel offset"),

    # --- file ---
    ActionDefinition("upload", "file", True, True, "Upload a file to a file input",
                     aliases=("upload_file", "set_input_files")),
    ActionDefinition("upload_multiple", "file", True, True, "Upload multiple files"),

    # --- hover/focus ---
    ActionDefinition("hover", "hover_focus", True, False, "Mouse-hover an element"),
    ActionDefinition("focus", "hover_focus", True, False, "Programmatically focus an element"),
    ActionDefinition("blur", "hover_focus", True, False, "Remove focus from element"),
    ActionDefinition("mouse_move", "hover_focus", False, True, "Move mouse to coordinates"),

    # --- wait ---
    ActionDefinition("wait_for_selector", "wait", False, True, "Wait for a CSS selector to appear"),
    ActionDefinition("wait_for_navigation", "wait", False, False, "Wait for page navigation"),
    ActionDefinition("wait_for_load_state", "wait", False, True, "Wait for page load state"),
    ActionDefinition("wait_for_timeout", "wait", False, True, "Sleep for N milliseconds"),
    ActionDefinition("wait_for_url", "wait", False, True, "Wait for URL to match pattern"),
    ActionDefinition("wait_for_text", "wait", False, True, "Wait for text to appear on page"),

    # --- auth ---
    ActionDefinition("oauth_flow", "auth", False, True, "Trigger OAuth flow by provider"),
    ActionDefinition("mfa_enter_code", "auth", True, True, "Enter MFA/OTP code"),
    ActionDefinition("logout", "auth", False, False, "Log out of current session"),

    # --- drag/drop ---
    ActionDefinition("drag_to", "drag_drop", True, True, "Drag element to another element"),
    ActionDefinition("drag_to_offset", "drag_drop", True, True, "Drag to (x,y) offset"),
    ActionDefinition("drop_file", "drag_drop", False, True, "Drop a file onto the page"),

    # --- frame/shadow ---
    ActionDefinition("frame_action", "frame_shadow", False, True,
                     "Execute action inside an iframe"),
    ActionDefinition("shadow_click", "frame_shadow", False, True,
                     "Click inside shadow DOM by selector path"),
    ActionDefinition("shadow_fill", "frame_shadow", False, True,
                     "Fill inside shadow DOM by selector path"),

    # --- javascript ---
    ActionDefinition("evaluate", "javascript", False, True, "Evaluate a JS expression"),
    ActionDefinition("click_js", "javascript", True, False, "Click via JS (bypasses visibility)"),
    ActionDefinition("set_attribute", "javascript", True, True, "Set element attribute via JS"),
    ActionDefinition("remove_attribute", "javascript", True, True, "Remove element attribute"),
    ActionDefinition("dispatch_event", "javascript", True, True, "Dispatch a custom DOM event"),
    ActionDefinition("trigger_change", "javascript", True, False,
                     "Trigger input+change events (for framework inputs)"),

    # --- dialog ---
    ActionDefinition("accept_dialog", "dialog", False, False, "Accept an alert/confirm dialog"),
    ActionDefinition("dismiss_dialog", "dialog", False, False, "Dismiss an alert/confirm dialog"),
    ActionDefinition("fill_dialog", "dialog", False, True, "Fill prompt dialog and accept"),
    ActionDefinition("accept_cookie_banner", "dialog", False, False,
                     "Click primary accept button on cookie consent banner"),

    # --- read/extract ---
    ActionDefinition("read_text", "extract", True, False, "Extract visible text from element"),
    ActionDefinition("read_attribute", "extract", True, True, "Read an element attribute"),
    ActionDefinition("read_table", "extract", True, False, "Extract table as structured data"),
    ActionDefinition("count_elements", "extract", False, True, "Count elements matching selector"),
    ActionDefinition("read_value", "extract", True, False, "Read input/textarea current value"),
    ActionDefinition("snapshot_page", "extract", False, False,
                     "Take an EffectSnapshot for verification"),

    # --- screenshot ---
    ActionDefinition("screenshot", "screenshot", False, False, "Take a full-page screenshot"),
    ActionDefinition("screenshot_element", "screenshot", True, False,
                     "Screenshot a single element"),

    # --- storage/session ---
    ActionDefinition("set_local_storage", "storage", False, True, "Set localStorage key/value"),
    ActionDefinition("get_local_storage", "storage", False, True, "Get localStorage value by key"),
    ActionDefinition("clear_local_storage", "storage", False, False, "Clear localStorage"),
    ActionDefinition("set_session_storage", "storage", False, True, "Set sessionStorage key"),
    ActionDefinition("set_cookie", "storage", False, True, "Set a browser cookie"),
    ActionDefinition("delete_cookie", "storage", False, True, "Delete a browser cookie"),
    ActionDefinition("clear_cookies", "storage", False, False, "Clear all cookies for origin"),

    # --- rich text editors ---
    ActionDefinition("rich_text_fill", "rich_text", True, True,
                     "Fill a rich text editor (Quill/TipTap/CKEditor/etc.)"),
    ActionDefinition("rich_text_clear", "rich_text", True, False, "Clear a rich text editor"),
    ActionDefinition("code_editor_fill", "rich_text", True, True,
                     "Fill a code editor (CodeMirror/Monaco)"),
]


class ActionRegistry:
    """Lookup ActionDefinition by name or alias."""

    def __init__(self) -> None:
        self._by_name: Dict[str, ActionDefinition] = {}
        for defn in _REGISTRY:
            self._by_name[defn.name] = defn
            for alias in defn.aliases:
                self._by_name[alias] = defn

    def get(self, action_type: str) -> Optional[ActionDefinition]:
        return self._by_name.get(action_type)

    def is_known(self, action_type: str) -> bool:
        return action_type in self._by_name

    def families(self) -> List[str]:
        seen: Dict[str, None] = {}
        for defn in _REGISTRY:
            seen[defn.family] = None
        return list(seen)

    def by_family(self, family: str) -> List[ActionDefinition]:
        return [d for d in _REGISTRY if d.family == family]

    def all_names(self) -> List[str]:
        return [d.name for d in _REGISTRY]


# Module-level singleton — import and use directly
REGISTRY = ActionRegistry()
