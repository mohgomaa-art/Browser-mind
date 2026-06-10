"""
CapabilityClassifier — WR-IR: Intent Resolution Layer

Classifies a recorded DOM element into two stable semantic signals:

  capability_hint   — What the element IS (independent of its DOM identity)
  workflow_role     — What the element DOES in this specific workflow context

These signals are mutation-immune:
  - They survive Drift Class A (label/placeholder mutation)
  - They survive Drift Class F (id/attribute removal)
  - They form the basis of WR-X Cross-Site Transfer

Design principle:
  Identity  (id, aria-label)  → can be destroyed
  Capability (input[type=search], form submit) → cannot be destroyed
"""
from __future__ import annotations
from typing import Dict, Any, Optional


# ---------------------------------------------------------------------------
# Capability Hint Rules
# ---------------------------------------------------------------------------
# Each rule is a dict with match keys and a resulting capability_hint.
# Rules are checked in priority order (first match wins).
#
# Match keys (all optional, combined as AND within a rule):
#   role         : str — ARIA role (exact)
#   type         : str — input[type] value
#   name_tokens  : list[str] — ANY of these tokens must appear in
#                  (aria-label + placeholder + name + text_content).lower()
#   context_tokens: list[str] — ANY of these tokens must appear in
#                  (capability_context).lower()
#   tag          : str — HTML tag name (lower)

CAPABILITY_RULES: list[Dict[str, Any]] = [
    # --- Auth inputs ---
    {"type": "email",                           "capability": "auth_email_input"},
    {"type": "password",                        "capability": "auth_password_input"},
    {"role": "textbox",
     "name_tokens": ["username", "user name", "user id", "login", "account"],
                                                "capability": "auth_username_input"},
    {"role": "textbox",
     "name_tokens": ["otp", "one-time", "verification code", "2fa", "token", "code"],
                                                "capability": "auth_otp_input"},

    # --- Search inputs ---
    {"type": "search",                          "capability": "search_query_input"},
    {"role": "searchbox",                       "capability": "search_query_input"},
    {"role": "textbox",
     "name_tokens": ["search", "find", "query", "look up", "lookup"],
                                                "capability": "search_query_input"},
    # DDG and similar sites use role=combobox on the main search input
    {"role": "combobox",
     "name_tokens": ["search", "find", "query", "look up", "lookup"],
                                                "capability": "search_query_input"},
    {"role": "textbox",
     "name_tokens": ["location", "where", "city", "destination"],
                                                "capability": "search_location_input"},

    # --- Navigation / filter ---
    {"role": "combobox",
     "name_tokens": ["sort", "filter", "order", "category"],
                                                "capability": "filter_selector"},
    {"role": "combobox",                        "capability": "generic_combobox"},

    # --- Submit / action buttons ---
    {"type": "submit",                          "capability": "form_submit"},
    {"role": "button",
     "name_tokens": ["search", "find", "go", "lookup"],
                                                "capability": "search_submit"},
    {"role": "button",
     "name_tokens": ["login", "sign in", "log in", "signin", "continue", "next"],
                                                "capability": "auth_submit"},
    {"role": "button",
     "name_tokens": ["add to cart", "add to bag", "buy now", "purchase"],
                                                "capability": "ecommerce_add_to_cart"},
    {"role": "button",
     "name_tokens": ["checkout", "place order", "confirm order"],
                                                "capability": "ecommerce_checkout"},

    # --- Navigation ---
    {"role": "link",                            "capability": "navigation_link"},

    # --- Generic textbox fallback (must be last) ---
    {"role": "textbox",                         "capability": "generic_text_input"},
    {"role": "button",                          "capability": "generic_button"},
]


# ---------------------------------------------------------------------------
# Workflow Role Rules
# ---------------------------------------------------------------------------
# Maps capability_hint + optional context_tokens → workflow_role.
# This answers: "In THIS workflow, what does this element accomplish?"

WORKFLOW_ROLE_RULES: list[Dict[str, Any]] = [
    # Global search (top-level site search)
    {"capability": "search_query_input",
     "context_tokens": ["header", "nav", "site", "global"],
     "workflow_role": "global_search"},
    {"capability": "search_query_input",
     "workflow_role": "global_search"}, # Default fallback

    # Domain-specific searches
    {"capability": "search_query_input",
     "context_tokens": ["package", "pypi", "npm", "pip"],
     "workflow_role": "package_search"},
    {"capability": "search_query_input",
     "context_tokens": ["repo", "repository", "project", "code"],
     "workflow_role": "repository_search"},
    {"capability": "search_query_input",
     "context_tokens": ["model", "dataset", "hugging", "ai", "ml"],
     "workflow_role": "model_search"},
    {"capability": "search_query_input",
     "context_tokens": ["doc", "docs", "api", "reference", "mdn", "developer"],
     "workflow_role": "documentation_search"},
    {"capability": "search_query_input",
     "context_tokens": ["product", "item", "shop", "store", "buy"],
     "workflow_role": "ecommerce_search"},

    # Auth
    {"capability": "auth_email_input",    "workflow_role": "login_email"},
    {"capability": "auth_username_input", "workflow_role": "login_username"},
    {"capability": "auth_password_input", "workflow_role": "login_password"},
    {"capability": "auth_otp_input",      "workflow_role": "login_otp"},
    {"capability": "auth_submit",         "workflow_role": "login_submit"},

    # Submit
    {"capability": "search_submit",   "workflow_role": "trigger_search"},
    {"capability": "form_submit",     "workflow_role": "submit_form"},

    # E-commerce
    {"capability": "ecommerce_add_to_cart", "workflow_role": "add_item_to_cart"},
    {"capability": "ecommerce_checkout",    "workflow_role": "proceed_to_checkout"},
    {"capability": "filter_selector",       "workflow_role": "apply_filter"},

    # Navigation
    {"capability": "navigation_link",   "workflow_role": "navigate_page"},
]

# Default workflow_role when no rule matches
_WORKFLOW_ROLE_DEFAULT = "generic_action"


# ---------------------------------------------------------------------------
# Capability Selectors (used by CapabilityResolver in target_resolver.py)
# Maps capability_hint → ordered list of CSS selectors to try during replay.
# Ordered from most specific to least specific.
# ---------------------------------------------------------------------------
CAPABILITY_SELECTORS: Dict[str, list[str]] = {
    "search_query_input": [
        "input[type='search']",
        "[role='searchbox']",
        "textarea[name='q']",
        "input[name='q']",
        "textarea[id*='search']",
        "input[name='query']",
        "input[name='search']",
        "input[name='s']",
        "input[placeholder*='earch']",
        "textarea[placeholder*='earch']",
        "input[id*='search'][type='text']",
        "input[name*='search'][type='text']",
        "input[id*='query'][type='text']",
        "form input[type='text']:first-of-type",
        "input[type='text']",
    ],
    "auth_email_input": [
        "input[type='email']",
        "input[name='email']",
        "input[name='username'][type='text']",
        "input[name='user']",
        "input[autocomplete='email']",
        "input[autocomplete='username']",
    ],
    "auth_username_input": [
        "input[name='username']",
        "input[name='user']",
        "input[name='login']",
        "input[autocomplete='username']",
        "input[type='text']:first-of-type",
    ],
    "auth_password_input": [
        "input[type='password']",
        "input[autocomplete='current-password']",
    ],
    "auth_otp_input": [
        "input[autocomplete='one-time-code']",
        "input[name='otp']",
        "input[name='code']",
        "input[name='token']",
        "input[placeholder*='code']",
        "input[placeholder*='OTP']",
    ],
    "form_submit": [
        "button[type='submit']",
        "input[type='submit']",
        "form button:last-of-type",
    ],
    "search_submit": [
        "button[type='submit']",
        "form button[type='submit']",
        "form button:last-of-type",
    ],
    "auth_submit": [
        "button[type='submit']",
        "form button[type='submit']",
    ],
    "filter_selector": [
        "select[name*='sort']",
        "select[name*='filter']",
        "select[name*='order']",
    ],
    # For navigation links: too ambiguous to have generic selectors
    # WR-X will handle these via workflow_role + site-specific resolution
    "navigation_link": [],
    "generic_text_input": [
        "input[type='text']",
    ],
    "generic_button": [],
    "generic_combobox": [
        "select",
    ],
    # Fallback aliases — produced when action_type=submit fires on a <form> element
    # (no ARIA role, resolves to "form_element" or "_element" in fallback path)
    "form_element": [
        "button[type='submit']",
        "input[type='submit']",
        "form button:last-of-type",
    ],
    "search_element": [
        "button[type='submit']",
        "form button[type='submit']",
        "form button:last-of-type",
    ],
    "_element": [
        "button[type='submit']",
        "form button:last-of-type",
    ],
}


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class CapabilityClassifier:
    """
    Classifies a recorded DOM element descriptor into:
      - capability_hint  : what the element IS
      - workflow_role    : what the element DOES in this workflow
      - capability_ordinal: position among same-capability siblings (1-indexed)

    Usage (inside SemanticRecorder._handler):
        classifier = CapabilityClassifier()
        caps = classifier.classify(payload, context_str)
        payload["descriptor"].update(caps)
    """

    def classify(
        self,
        payload: Dict[str, Any],
        capability_context: str = "",
        capability_ordinal: int = 1,
    ) -> Dict[str, Any]:
        """
        Returns a dict with capability fields to merge into descriptor.

        Args:
            payload: raw action payload from JS observer
                     (has: target_role, target_name, target_selector, descriptor, ...)
            capability_context: form/section context string extracted from JS
            capability_ordinal: ordinal of this element among same-type siblings
                                (extracted from JS observer, 1-indexed)
        """
        action_type = (payload.get("action_type") or "").lower()
        role        = (payload.get("target_role") or "").lower()
        name        = (payload.get("target_name") or "").lower()
        selector    = (payload.get("target_selector") or "").lower()
        descriptor  = payload.get("descriptor") or {}

        # Build search corpus for token matching
        placeholder = (descriptor.get("placeholder") or "").lower()
        text        = (descriptor.get("text_content") or "").lower()
        corpus      = f"{name} {placeholder} {text} {capability_context}".strip()

        # Determine input type from selector
        input_type = self._extract_input_type(selector)

        # Special case: submit action on a form element (no ARIA role)
        # DDG fires submit on <form id='searchbox_homepage'> itself
        if action_type == "submit" and not role:
            capability_hint = "form_submit"
        else:
            capability_hint = self._match_capability(role, input_type, corpus)

        workflow_role = self._match_workflow_role(capability_hint, capability_context.lower())

        return {
            "capability_hint":     capability_hint,
            "capability_context":  capability_context,
            "capability_ordinal":  capability_ordinal,
            "workflow_role":       workflow_role,
        }

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _extract_input_type(self, selector: str) -> Optional[str]:
        """Extract type from selector like 'input[type=password]' or '#id'."""
        if "[type=" in selector:
            try:
                start = selector.index("[type=") + 6
                end   = selector.index("]", start)
                return selector[start:end].strip("\"'").lower()
            except ValueError:
                pass
        return None

    def _match_capability(self, role: str, input_type: Optional[str], corpus: str) -> str:
        for rule in CAPABILITY_RULES:
            # Check role
            if "role" in rule and rule["role"] != role:
                continue
            # Check type
            if "type" in rule:
                if input_type != rule["type"]:
                    continue
            # Check name_tokens (ANY token must appear in corpus)
            if "name_tokens" in rule:
                if not any(tok in corpus for tok in rule["name_tokens"]):
                    continue
            # Check tag (not commonly needed but available)
            if "tag" in rule:
                pass  # JS payload doesn't carry tag directly; skip for now
            return rule["capability"]
        return f"{role}_element" if role else "unknown_element"

    def _match_workflow_role(self, capability_hint: str, context_lower: str) -> str:
        # First pass: try context-sensitive match
        for rule in WORKFLOW_ROLE_RULES:
            if rule.get("capability") != capability_hint:
                continue
            context_tokens = rule.get("context_tokens", [])
            if context_tokens:
                if any(tok and tok in context_lower for tok in context_tokens):
                    return rule["workflow_role"]
        # Second pass: capability-only match (no context required)
        for rule in WORKFLOW_ROLE_RULES:
            if rule.get("capability") != capability_hint:
                continue
            if not rule.get("context_tokens"):
                return rule["workflow_role"]
        return _WORKFLOW_ROLE_DEFAULT
