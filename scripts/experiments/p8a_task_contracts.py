# scripts/experiments/p8a_task_contracts.py
"""
P8A.5 — Task Success Contracts
================================
Strict, deterministic, browser-state-based verification.

No heuristics.
No "word disappeared".
No "page changed".
No default_ok.

Each task has exactly ONE definition of success,
expressed as verifiable conditions against the live browser DOM and URL.

ContractVerifier is the ground truth for BOTH agents.
Neither agent's self-reported success matters.
Only the browser state after execution matters.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from playwright.async_api import Page


# ─────────────────────────────────────────────────────────────────────────────
# Data Model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SuccessCondition:
    """A single verifiable condition against the live browser state."""
    kind: str       # "url_contains" | "element_visible" | "element_text_contains"
    target: str     # URL substring or CSS selector
    value: str = "" # Required text value (for element_text_contains only)
    label: str = "" # Human-readable description for the evidence report


@dataclass
class TaskSuccessContract:
    """
    Formal definition of task completion.
    All conditions are AND-combined — every condition must be satisfied.
    """
    task_id: str
    description: str
    rationale: str
    conditions: List[SuccessCondition]


# ─────────────────────────────────────────────────────────────────────────────
# Contract Registry — 9 Tasks
# ─────────────────────────────────────────────────────────────────────────────

CONTRACTS: Dict[str, TaskSuccessContract] = {

    "T1_2FA": TaskSuccessContract(
        task_id="T1_2FA",
        description="Log in with 2FA using Vault credentials and OTP",
        rationale=(
            "Success requires the browser to be on /dashboard with the "
            "welcome header visible — proving full authentication completed, "
            "including the 2FA OTP step."
        ),
        conditions=[
            SuccessCondition(
                kind="url_contains",
                target="/dashboard",
                label="Browser is on /dashboard (authenticated session)"
            ),
            SuccessCondition(
                kind="element_visible",
                target="#welcome-header",
                label="Welcome header visible (session valid)"
            ),
        ]
    ),

    "T2_Recovery": TaskSuccessContract(
        task_id="T2_Recovery",
        description="Reset forgotten password and log in with new password",
        rationale=(
            "Success requires the browser to be on /dashboard with the "
            "welcome header visible — proving the new password was accepted."
        ),
        conditions=[
            SuccessCondition(
                kind="url_contains",
                target="/dashboard",
                label="Browser is on /dashboard (new password accepted)"
            ),
            SuccessCondition(
                kind="element_visible",
                target="#welcome-header",
                label="Welcome header visible (session valid)"
            ),
        ]
    ),

    "T3_MultiEnv": TaskSuccessContract(
        task_id="T3_MultiEnv",
        description="Retrieve code from Vault and verify it in the Email Portal",
        rationale=(
            "Success requires the browser to end on /email-client, "
            "proving the agent crossed from vault to email environment as required."
        ),
        conditions=[
            SuccessCondition(
                kind="url_contains",
                target="/email-client",
                label="Browser is on /email-client (cross-environment reached)"
            ),
        ]
    ),

    "T4_Search": TaskSuccessContract(
        task_id="T4_Search",
        description="Search information query",
        rationale=(
            "Success requires the #search-results element to be visible, "
            "proving the search query was submitted and results rendered."
        ),
        conditions=[
            SuccessCondition(
                kind="element_visible",
                target="#search-results",
                label="#search-results element visible (results rendered)"
            ),
        ]
    ),

    "T5_Nav": TaskSuccessContract(
        task_id="T5_Nav",
        description="Click first navigation menu item on menu client",
        rationale=(
            "Success requires URL to contain menu=1, "
            "proving nav item 1 was clicked and the server acknowledged it."
        ),
        conditions=[
            SuccessCondition(
                kind="url_contains",
                target="menu=1",
                label="URL contains menu=1 (nav item clicked)"
            ),
        ]
    ),

    "T6_Filter": TaskSuccessContract(
        task_id="T6_Filter",
        description="Filter products by size XS on the shopping portal",
        rationale=(
            "Success requires the #filtered-results element to be visible, "
            "proving the XS filter was applied and results are shown."
        ),
        conditions=[
            SuccessCondition(
                kind="element_visible",
                target="#filtered-results",
                label="#filtered-results visible (filter applied)"
            ),
        ]
    ),

    "T7_Profile": TaskSuccessContract(
        task_id="T7_Profile",
        description="Update the billing address in user profile",
        rationale=(
            "Success requires the #profile-status element to be visible, "
            "proving the profile form was submitted and the server confirmed the update."
        ),
        conditions=[
            SuccessCondition(
                kind="element_visible",
                target="#profile-status",
                label="#profile-status visible (address update confirmed)"
            ),
        ]
    ),

    "T8_Contact": TaskSuccessContract(
        task_id="T8_Contact",
        description="Submit a simple contact form username",
        rationale=(
            "Success requires the #contact-status element to be visible, "
            "proving the contact form was submitted and the server confirmed receipt."
        ),
        conditions=[
            SuccessCondition(
                kind="element_visible",
                target="#contact-status",
                label="#contact-status visible (contact form submitted)"
            ),
        ]
    ),

    "T9_ForgotLink": TaskSuccessContract(
        task_id="T9_ForgotLink",
        description="Click Forgot Password link on the login page",
        rationale=(
            "Success requires URL to contain /forgot-password, "
            "proving the link was clicked and the browser navigated to the recovery page."
        ),
        conditions=[
            SuccessCondition(
                kind="url_contains",
                target="/forgot-password",
                label="URL contains /forgot-password (link clicked)"
            ),
        ]
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Contract Verifier
# ─────────────────────────────────────────────────────────────────────────────

class ContractVerifier:
    """
    Evaluates task completion strictly against declared TaskSuccessContracts.

    This is the ground truth for both BrowserMind and Baseline.
    Neither agent's self-reported 'success' field is trusted.
    Only the live browser state after execution is evaluated.

    Returns a structured evidence report for every task.
    """

    async def verify(self, page: Page, task_id: str) -> Dict[str, Any]:
        """
        Verify task completion against the registered contract.

        Returns:
            {
                "goal_completed": bool,
                "success_contract": {...},
                "contract_evidence": {
                    "url_at_verification": str,
                    "conditions": {label: {kind, target, satisfied}}
                },
                "validator_result": bool
            }
        """
        contract = CONTRACTS.get(task_id)
        if not contract:
            return {
                "goal_completed": False,
                "success_contract": None,
                "contract_evidence": {
                    "error": f"No contract registered for task_id='{task_id}'"
                },
                "validator_result": False,
            }

        current_url = page.url
        evidence_conditions: Dict[str, Any] = {}
        all_satisfied = True

        for cond in contract.conditions:
            satisfied = await self._evaluate(page, cond, current_url)
            evidence_conditions[cond.label] = {
                "kind": cond.kind,
                "target": cond.target,
                "satisfied": satisfied,
            }
            if not satisfied:
                all_satisfied = False

        return {
            "goal_completed": all_satisfied,
            "success_contract": {
                "task_id": contract.task_id,
                "description": contract.description,
                "rationale": contract.rationale,
                "conditions": [
                    {"kind": c.kind, "target": c.target, "label": c.label}
                    for c in contract.conditions
                ],
            },
            "contract_evidence": {
                "url_at_verification": current_url,
                "conditions": evidence_conditions,
            },
            "validator_result": all_satisfied,
        }

    async def _evaluate(
        self,
        page: Page,
        cond: SuccessCondition,
        current_url: str
    ) -> bool:
        try:
            if cond.kind == "url_contains":
                return cond.target in current_url

            elif cond.kind == "element_visible":
                el = page.locator(cond.target).first
                return await el.is_visible(timeout=2000)

            elif cond.kind == "element_text_contains":
                el = page.locator(cond.target).first
                if not await el.is_visible(timeout=2000):
                    return False
                text = await el.inner_text()
                return cond.value.lower() in text.lower()

        except Exception:
            return False

        return False
