"""
IntentFamily — WR-IR Phase 2

Provides a stable, bounded vocabulary of Intent Families.
Maps workflow_role (execution detail) → IntentFamily (abstract category).

Design constraints:
  - Max 7+1 families — prevent taxonomy explosion
  - IntentFamily is NOT execution-specific — it describes WHAT, not HOW
  - AffordanceDiscoverer uses family to know what kind of affordances to look for
  - AffordanceExecutor uses affordance type to decide how to execute

Hierarchy:
  workflow_role (fine-grained) → IntentFamily (bounded) → AffordancePolicy (per-family)
"""
from __future__ import annotations
from enum import Enum
from typing import Optional


class IntentFamily(Enum):
    SEARCH          = "search"          # query, filter, lookup
    AUTH            = "auth"            # login, register, OTP, logout
    FORM            = "form"            # generic form submit, checkout, apply
    NAVIGATION      = "navigation"      # page transitions, link follows
    FILTER          = "filter"          # sort, category, facet selection
    UPLOAD          = "upload"          # file, image, document
    DATA_EXTRACTION = "data_extraction" # scrape, copy, export
    UNKNOWN         = "unknown"         # no mapping — skip affordance discovery


# ---------------------------------------------------------------------------
# Mapping: workflow_role → IntentFamily
# ---------------------------------------------------------------------------
# Keys are the workflow_role values produced by CapabilityClassifier.
# Unmapped roles → UNKNOWN (AffordanceDiscoverer returns [] for UNKNOWN).

_ROLE_TO_FAMILY: dict[str, IntentFamily] = {
    # --- SEARCH ---
    "global_search":         IntentFamily.SEARCH,
    "package_search":        IntentFamily.SEARCH,
    "repository_search":     IntentFamily.SEARCH,
    "model_search":          IntentFamily.SEARCH,
    "documentation_search":  IntentFamily.SEARCH,
    "ecommerce_search":      IntentFamily.SEARCH,
    "trigger_search":        IntentFamily.SEARCH,

    # --- AUTH ---
    "login_email":           IntentFamily.AUTH,
    "login_username":        IntentFamily.AUTH,
    "login_password":        IntentFamily.AUTH,
    "login_otp":             IntentFamily.AUTH,
    "login_submit":          IntentFamily.AUTH,

    # --- FORM ---
    "submit_form":           IntentFamily.FORM,
    "add_item_to_cart":      IntentFamily.FORM,
    "proceed_to_checkout":   IntentFamily.FORM,

    # --- NAVIGATION ---
    "navigate_page":         IntentFamily.NAVIGATION,

    # --- FILTER ---
    "apply_filter":          IntentFamily.FILTER,

    # --- GENERIC (keep for fallback path) ---
    "generic_action":        IntentFamily.UNKNOWN,
}

# Capability-hint fallback (when workflow_role is missing or "generic_action")
_CAPABILITY_TO_FAMILY: dict[str, IntentFamily] = {
    "search_query_input":   IntentFamily.SEARCH,
    "search_submit":        IntentFamily.SEARCH,
    "auth_email_input":     IntentFamily.AUTH,
    "auth_username_input":  IntentFamily.AUTH,
    "auth_password_input":  IntentFamily.AUTH,
    "auth_otp_input":       IntentFamily.AUTH,
    "auth_submit":          IntentFamily.AUTH,
    "form_submit":          IntentFamily.FORM,
    "filter_selector":      IntentFamily.FILTER,
    "navigation_link":      IntentFamily.NAVIGATION,
}


class IntentFamilyMapper:
    """
    Maps descriptor fields to an IntentFamily.
    Tries workflow_role first, falls back to capability_hint, then UNKNOWN.
    """

    @staticmethod
    def map(descriptor: dict) -> IntentFamily:
        """
        Args:
            descriptor: step descriptor dict (has workflow_role, capability_hint)

        Returns:
            IntentFamily — UNKNOWN if no mapping found
        """
        workflow_role   = (descriptor.get("workflow_role")   or "").strip()
        capability_hint = (descriptor.get("capability_hint") or "").strip()

        if workflow_role and workflow_role in _ROLE_TO_FAMILY:
            family = _ROLE_TO_FAMILY[workflow_role]
            if family != IntentFamily.UNKNOWN:
                return family

        if capability_hint and capability_hint in _CAPABILITY_TO_FAMILY:
            return _CAPABILITY_TO_FAMILY[capability_hint]

        return IntentFamily.UNKNOWN

    @staticmethod
    def from_role(workflow_role: str) -> IntentFamily:
        return _ROLE_TO_FAMILY.get(workflow_role, IntentFamily.UNKNOWN)

    @staticmethod
    def from_capability(capability_hint: str) -> IntentFamily:
        return _CAPABILITY_TO_FAMILY.get(capability_hint, IntentFamily.UNKNOWN)
