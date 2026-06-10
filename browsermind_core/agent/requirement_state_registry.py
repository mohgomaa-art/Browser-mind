"""Requirement State Registry — Translates goal Requirements into Target Execution States (Observation Points)."""

from typing import Dict, List, NamedTuple
from browsermind_core.ontology.asset import StateClass


class TargetState(NamedTuple):
    """A target execution state paired with its classification."""
    state: str
    state_class: StateClass


class RequirementStateRegistry:
    def __init__(self):
        # Maps a Requirement to a list of TargetState entries.
        # Each entry is (execution_state, StateClass).
        #
        # StateClass.OBSERVATION  = state means "this place is open for inspection"
        #                           Resource may or may not be there.
        # StateClass.AVAILABILITY = state means "resource is guaranteed present/accessible"
        self.requirement_target_states: Dict[str, List[TargetState]] = {
            "verification_code": [
                TargetState("email.opened",        StateClass.OBSERVATION),
                TargetState("vault.otp_generated", StateClass.AVAILABILITY),
            ],
            "current_password": [
                TargetState("vault.credentials_unlocked", StateClass.AVAILABILITY),
            ],
            "password": [
                TargetState("vault.credentials_unlocked", StateClass.AVAILABILITY),
            ],
            "username": [
                TargetState("vault.credentials_unlocked", StateClass.AVAILABILITY),
            ],
            "credentials": [
                TargetState("vault.credentials_unlocked", StateClass.AVAILABILITY),
            ],
            "payment_method": [
                TargetState("checkout.payment_processed", StateClass.AVAILABILITY),
            ],
            "billing_address": [
                TargetState("wallet.billing_info_loaded", StateClass.AVAILABILITY),
                TargetState("profile.loaded",             StateClass.OBSERVATION),
            ],
            "search_query": [
                TargetState("context.resolved", StateClass.AVAILABILITY),
            ],
            "filter_criteria": [
                TargetState("context.resolved", StateClass.AVAILABILITY),
            ],
            "target_url": [
                TargetState("context.resolved", StateClass.AVAILABILITY),
            ],
            "email": [
                TargetState("profile.loaded", StateClass.OBSERVATION),
            ],
            "email_or_username": [
                TargetState("profile.loaded", StateClass.OBSERVATION),
            ],
            "authenticated_session": [],  # Externally provided by environment
        }

    def get_target_states(self, requirement: str) -> List[str]:
        """Returns the raw execution state names for backward compatibility."""
        return [ts.state for ts in self.requirement_target_states.get(requirement, [])]

    def get_annotated_target_states(self, requirement: str) -> List[TargetState]:
        """Returns TargetState entries with full StateClass annotation."""
        return list(self.requirement_target_states.get(requirement, []))
