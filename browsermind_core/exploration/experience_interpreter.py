"""ExperienceInterpreter — maps completed intent sets to semantic experience labels.

This is the bridge between raw execution traces and meaningful capability
discovery. It answers: "what did BrowserMind just *do*?"

  Raw:          {"auth_password_input", "auth_login", "form_submit"}
  Interpreted:  ExperienceLabel(name="session_authentication", confidence=0.95)

The vocabulary
──────────────
Intent strings come from PrimitiveNormalizer output (via ExplorationHarness) or
directly from capability_hint strings in CAPABILITY_RULES. Both sources produce
the same string format used in ExperiencePattern.required_intents.

Pattern matching algorithm
──────────────────────────
For each ExperiencePattern:
  1. required_coverage = |required_intents ∩ completed| / |required_intents|
  2. A pattern MATCHES only if required_coverage == 1.0 (all required present)
  3. optional_bonus = |optional_intents ∩ completed| / max(1, |optional_intents|)
  4. confidence = 0.8 * required_coverage + 0.2 * optional_bonus
     (always 0.8-1.0 for full matches, so ranking is by optional coverage)

Unknown intents
───────────────
Intents NOT claimed by any matched pattern are returned in
ExperienceLabel.unmatched_intents. If ≥ 2 unmatched intents exist, the
caller (ExplorationHarness) feeds them to CapabilityHypothesisStore.observe()
as a novel pattern candidate.

The 30-category coverage
─────────────────────────
Patterns are defined for the most common experience types across all 30
site categories. The taxonomy maps to TransferArena families so that
experiences accumulate into transfer-measurable capability families.

Extending patterns
──────────────────
Register additional patterns via ExperienceInterpreter.register_pattern()
or by calling register_experience_pattern() at import time.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Set


# ── ExperiencePattern ─────────────────────────────────────────────────────────

@dataclass
class ExperiencePattern:
    """One recognisable type of user experience.

    Fields
    ──────
    name                Short identifier. Used as ExperienceLabel.name.
    required_intents    All of these must be present for the pattern to match.
    optional_intents    Any present boosts confidence (0.0 – 0.2 bonus).
    description         Human-readable description of the experience.
    capability_family   TransferArena family this experience contributes to.
                        One of: "authentication", "search", "community", "form_fill"
                        or None for uncategorised.
    """
    name: str
    required_intents: FrozenSet[str]
    optional_intents: FrozenSet[str]
    description: str
    capability_family: Optional[str] = None

    def matches(self, completed: Set[str]) -> bool:
        """Return True iff ALL required_intents are in completed."""
        return self.required_intents.issubset(completed)

    def confidence(self, completed: Set[str]) -> float:
        """Compute match confidence (0.8 – 1.0 for full matches)."""
        if not self.matches(completed):
            return 0.0
        optional_present = len(self.optional_intents & completed)
        optional_total   = max(1, len(self.optional_intents))
        optional_bonus   = optional_present / optional_total
        return round(0.8 + 0.2 * optional_bonus, 4)


# ── ExperienceLabel ───────────────────────────────────────────────────────────

@dataclass
class ExperienceLabel:
    """The result of matching one ExperiencePattern against a completed intent set.

    Fields
    ──────
    name                Pattern name ("session_authentication", etc.).
    description         Human-readable summary of what happened.
    confidence          0.8 – 1.0 for known patterns; 0.0 for unknown.
    is_known            True = matched a registered ExperiencePattern.
                        False = novel intent cluster, candidate for hypothesis.
    matched_intents     Intents claimed by this label's pattern.
    unmatched_intents   Intents not claimed by any matched label (only set on
                        the UNKNOWN sentinel label, if returned).
    capability_family   From ExperiencePattern.capability_family.
    """
    name: str
    description: str
    confidence: float
    is_known: bool
    matched_intents: Set[str] = field(default_factory=set)
    unmatched_intents: Set[str] = field(default_factory=set)
    capability_family: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "confidence": self.confidence,
            "is_known": self.is_known,
            "matched_intents": sorted(self.matched_intents),
            "unmatched_intents": sorted(self.unmatched_intents),
            "capability_family": self.capability_family,
        }


# ── Built-in patterns ─────────────────────────────────────────────────────────
# Vocabulary: capability_hint strings from CAPABILITY_RULES + normalizer output.
# Required intents represent the minimum observable signal for each experience.

_BUILTIN_PATTERNS: List[ExperiencePattern] = [

    # ── Authentication family ─────────────────────────────────────────────────
    ExperiencePattern(
        name="session_authentication",
        required_intents=frozenset({"auth_password_input", "auth_login"}),
        optional_intents=frozenset({"auth_mfa_input", "auth_remember_me",
                                    "auth_username_input", "oauth_redirect"}),
        description="User credentials submitted and session established",
        capability_family="authentication",
    ),
    ExperiencePattern(
        name="account_registration",
        required_intents=frozenset({"auth_password_input", "auth_username_input",
                                    "form_submit"}),
        optional_intents=frozenset({"auth_email_input", "auth_terms_accept",
                                    "auth_captcha_solve"}),
        description="New account created via registration flow",
        capability_family="authentication",
    ),
    ExperiencePattern(
        name="password_reset",
        required_intents=frozenset({"auth_password_input", "auth_email_input"}),
        optional_intents=frozenset({"auth_token_input", "form_submit"}),
        description="Password reset flow initiated or completed",
        capability_family="authentication",
    ),
    ExperiencePattern(
        name="oauth_delegation",
        required_intents=frozenset({"oauth_redirect", "auth_login"}),
        optional_intents=frozenset({"auth_scope_confirm"}),
        description="OAuth/SSO delegation completed",
        capability_family="authentication",
    ),
    ExperiencePattern(
        name="mfa_verification",
        required_intents=frozenset({"auth_mfa_input"}),
        optional_intents=frozenset({"auth_login", "auth_remember_me"}),
        description="Multi-factor authentication code entered",
        capability_family="authentication",
    ),
    ExperiencePattern(
        name="session_logout",
        required_intents=frozenset({"auth_logout"}),
        optional_intents=frozenset({"profile_view"}),
        description="Active session terminated via logout",
        capability_family="authentication",
    ),
    ExperiencePattern(
        name="cookie_consent",
        required_intents=frozenset({"auth_terms_accept"}),
        optional_intents=frozenset({"form_submit"}),
        description="Cookie consent or terms banner accepted",
        capability_family="authentication",
    ),

    # ── Search family ─────────────────────────────────────────────────────────
    ExperiencePattern(
        name="search_query_executed",
        required_intents=frozenset({"search_query_input"}),
        optional_intents=frozenset({"search_filter_apply", "search_sort_apply",
                                    "search_pagination", "search_results_parse"}),
        description="Search query submitted and results page reached",
        capability_family="search",
    ),
    ExperiencePattern(
        name="faceted_search",
        required_intents=frozenset({"search_query_input", "search_filter_apply"}),
        optional_intents=frozenset({"search_sort_apply", "search_pagination"}),
        description="Search with at least one filter or facet applied",
        capability_family="search",
    ),
    ExperiencePattern(
        name="content_discovery",
        required_intents=frozenset({"search_query_input", "content_navigation"}),
        optional_intents=frozenset({"search_filter_apply", "link_follow"}),
        description="Information located via search and navigation",
        capability_family="search",
    ),
    ExperiencePattern(
        name="autocomplete_search",
        required_intents=frozenset({"search_query_input", "search_suggestion_select"}),
        optional_intents=frozenset({"search_results_parse"}),
        description="Search completed via autocomplete suggestion selection",
        capability_family="search",
    ),

    # ── Community family ──────────────────────────────────────────────────────
    ExperiencePattern(
        name="content_published",
        required_intents=frozenset({"community_post", "form_submit"}),
        optional_intents=frozenset({"media_attach", "tag_apply", "draft_save"}),
        description="Content created and submitted to community",
        capability_family="community",
    ),
    ExperiencePattern(
        name="community_reaction",
        required_intents=frozenset({"community_vote"}),
        optional_intents=frozenset({"community_post", "community_follow"}),
        description="Reaction or vote submitted on community content",
        capability_family="community",
    ),
    ExperiencePattern(
        name="social_connection",
        required_intents=frozenset({"social_follow"}),
        optional_intents=frozenset({"profile_view", "community_post"}),
        description="Social connection initiated (follow, subscribe, connect)",
        capability_family="community",
    ),
    ExperiencePattern(
        name="profile_updated",
        required_intents=frozenset({"profile_edit", "form_submit"}),
        optional_intents=frozenset({"media_upload", "profile_view"}),
        description="User profile fields edited and saved",
        capability_family="community",
    ),
    ExperiencePattern(
        name="direct_message_sent",
        required_intents=frozenset({"social_message_send"}),
        optional_intents=frozenset({"social_follow", "profile_view"}),
        description="Direct or private message sent to another user",
        capability_family="community",
    ),
    ExperiencePattern(
        name="comment_posted",
        required_intents=frozenset({"community_comment", "form_submit"}),
        optional_intents=frozenset({"community_vote", "media_attach"}),
        description="Comment posted on a piece of content",
        capability_family="community",
    ),

    # ── Form-fill family ──────────────────────────────────────────────────────
    ExperiencePattern(
        name="form_submission",
        required_intents=frozenset({"form_submit"}),
        optional_intents=frozenset({"form_field_fill", "form_validation_pass",
                                    "form_captcha"}),
        description="Form fields completed and submitted",
        capability_family="form_fill",
    ),
    ExperiencePattern(
        name="checkout_completed",
        required_intents=frozenset({"cart_add", "form_submit"}),
        optional_intents=frozenset({"payment_input", "address_input",
                                    "promo_code_apply"}),
        description="E-commerce checkout flow initiated or completed",
        capability_family="form_fill",
    ),
    ExperiencePattern(
        name="file_uploaded",
        required_intents=frozenset({"media_upload", "form_submit"}),
        optional_intents=frozenset({"media_preview", "file_type_select"}),
        description="File or media asset uploaded successfully",
        capability_family="form_fill",
    ),

    # ── E-commerce family ─────────────────────────────────────────────────────
    ExperiencePattern(
        name="product_searched",
        required_intents=frozenset({"search_query_input", "ecommerce_product_view"}),
        optional_intents=frozenset({"search_filter_apply", "search_sort_apply",
                                    "ecommerce_price_filter"}),
        description="Product located via search on an e-commerce site",
        capability_family="ecommerce",
    ),
    ExperiencePattern(
        name="cart_item_added",
        required_intents=frozenset({"cart_add"}),
        optional_intents=frozenset({"ecommerce_product_view", "ecommerce_quantity_set"}),
        description="Item added to shopping cart",
        capability_family="ecommerce",
    ),
    ExperiencePattern(
        name="product_filtered",
        required_intents=frozenset({"search_filter_apply", "ecommerce_product_view"}),
        optional_intents=frozenset({"ecommerce_price_filter", "search_sort_apply",
                                    "search_pagination"}),
        description="Product catalog filtered by at least one facet",
        capability_family="ecommerce",
    ),
    ExperiencePattern(
        name="wishlist_saved",
        required_intents=frozenset({"ecommerce_wishlist_add"}),
        optional_intents=frozenset({"ecommerce_product_view", "auth_login"}),
        description="Product saved to wishlist or favourites",
        capability_family="ecommerce",
    ),
    ExperiencePattern(
        name="coupon_applied",
        required_intents=frozenset({"promo_code_apply", "form_submit"}),
        optional_intents=frozenset({"cart_add", "payment_input"}),
        description="Discount or coupon code entered and validated",
        capability_family="ecommerce",
    ),

    # ── Jobs / ATS family ─────────────────────────────────────────────────────
    ExperiencePattern(
        name="job_searched",
        required_intents=frozenset({"search_query_input", "jobs_listing_view"}),
        optional_intents=frozenset({"search_filter_apply", "jobs_location_filter",
                                    "search_sort_apply"}),
        description="Job listings retrieved via search",
        capability_family="jobs",
    ),
    ExperiencePattern(
        name="job_applied",
        required_intents=frozenset({"jobs_apply_click", "form_submit"}),
        optional_intents=frozenset({"resume_upload", "jobs_cover_letter_input",
                                    "jobs_ats_field_fill"}),
        description="Job application submitted through apply flow",
        capability_family="jobs",
    ),
    ExperiencePattern(
        name="resume_uploaded",
        required_intents=frozenset({"resume_upload"}),
        optional_intents=frozenset({"jobs_apply_click", "form_submit",
                                    "media_preview"}),
        description="Resume or CV file uploaded to a job platform",
        capability_family="jobs",
    ),
    ExperiencePattern(
        name="job_saved",
        required_intents=frozenset({"jobs_save_click"}),
        optional_intents=frozenset({"jobs_listing_view", "auth_login"}),
        description="Job posting saved or bookmarked for later",
        capability_family="jobs",
    ),
    ExperiencePattern(
        name="ats_form_filled",
        required_intents=frozenset({"jobs_ats_field_fill", "form_submit"}),
        optional_intents=frozenset({"resume_upload", "jobs_cover_letter_input",
                                    "jobs_apply_click"}),
        description="ATS multi-step application form completed and submitted",
        capability_family="jobs",
    ),

    # ── Developer / DevTools family ───────────────────────────────────────────
    ExperiencePattern(
        name="repository_created",
        required_intents=frozenset({"dev_repo_create", "form_submit"}),
        optional_intents=frozenset({"dev_readme_init", "dev_visibility_set"}),
        description="New code repository created",
        capability_family="developer",
    ),
    ExperiencePattern(
        name="issue_created",
        required_intents=frozenset({"dev_issue_create", "form_submit"}),
        optional_intents=frozenset({"dev_label_apply", "dev_assignee_set",
                                    "media_attach"}),
        description="Issue or bug report created in a dev platform",
        capability_family="developer",
    ),
    ExperiencePattern(
        name="pull_request_created",
        required_intents=frozenset({"dev_pr_create", "form_submit"}),
        optional_intents=frozenset({"dev_reviewer_assign", "dev_label_apply",
                                    "dev_branch_select"}),
        description="Pull request or merge request submitted",
        capability_family="developer",
    ),
    ExperiencePattern(
        name="api_key_generated",
        required_intents=frozenset({"dev_api_key_create"}),
        optional_intents=frozenset({"form_submit", "dev_scope_select"}),
        description="API key or access token generated",
        capability_family="developer",
    ),

    # ── Booking / Travel family ───────────────────────────────────────────────
    ExperiencePattern(
        name="availability_searched",
        required_intents=frozenset({"booking_date_select", "search_query_input"}),
        optional_intents=frozenset({"booking_guest_count", "booking_location_input"}),
        description="Availability searched for dates on a booking platform",
        capability_family="booking",
    ),
    ExperiencePattern(
        name="booking_confirmed",
        required_intents=frozenset({"booking_confirm", "form_submit"}),
        optional_intents=frozenset({"payment_input", "booking_date_select",
                                    "booking_seat_select"}),
        description="Reservation or booking submitted and confirmed",
        capability_family="booking",
    ),
    ExperiencePattern(
        name="seat_selected",
        required_intents=frozenset({"booking_seat_select"}),
        optional_intents=frozenset({"booking_confirm", "booking_date_select"}),
        description="Specific seat or room selected in a booking flow",
        capability_family="booking",
    ),

    # ── SaaS / Productivity family ────────────────────────────────────────────
    ExperiencePattern(
        name="workspace_created",
        required_intents=frozenset({"saas_workspace_create", "form_submit"}),
        optional_intents=frozenset({"saas_team_invite", "saas_plan_select"}),
        description="New workspace, project, or organization created in SaaS product",
        capability_family="saas",
    ),
    ExperiencePattern(
        name="team_member_invited",
        required_intents=frozenset({"saas_team_invite", "form_submit"}),
        optional_intents=frozenset({"auth_email_input", "saas_role_assign"}),
        description="Team member invited to a workspace via email",
        capability_family="saas",
    ),
    ExperiencePattern(
        name="data_exported",
        required_intents=frozenset({"saas_export_trigger"}),
        optional_intents=frozenset({"form_submit", "saas_format_select"}),
        description="Data or report exported from SaaS application",
        capability_family="saas",
    ),
    ExperiencePattern(
        name="settings_saved",
        required_intents=frozenset({"saas_settings_edit", "form_submit"}),
        optional_intents=frozenset({"profile_edit"}),
        description="Application settings or preferences saved",
        capability_family="saas",
    ),

    # ── Media / consumption (no transfer family — cross-cutting) ──────────────
    ExperiencePattern(
        name="media_consumed",
        required_intents=frozenset({"media_play"}),
        optional_intents=frozenset({"search_query_input", "media_seek",
                                    "media_quality_select"}),
        description="Audio or video media played",
        capability_family=None,
    ),

    # ── Navigation (lowest confidence anchor — very broad) ────────────────────
    ExperiencePattern(
        name="site_navigated",
        required_intents=frozenset({"content_navigation"}),
        optional_intents=frozenset({"link_follow", "breadcrumb_follow",
                                    "pagination_next"}),
        description="Site navigated to a new section or page",
        capability_family=None,
    ),
]

# Global registry
_PATTERN_REGISTRY: Dict[str, ExperiencePattern] = {
    p.name: p for p in _BUILTIN_PATTERNS
}


def register_experience_pattern(pattern: ExperiencePattern) -> None:
    """Add or replace a pattern in the global registry."""
    _PATTERN_REGISTRY[pattern.name] = pattern


# ── ExperienceInterpreter ─────────────────────────────────────────────────────

class ExperienceInterpreter:
    """Map a completed intent set to a list of ExperienceLabel objects.

    Instantiation is cheap — the pattern registry is module-level. Custom
    patterns can be injected via the patterns parameter.
    """

    def __init__(
        self,
        patterns: Optional[Dict[str, ExperiencePattern]] = None,
    ) -> None:
        self._patterns: Dict[str, ExperiencePattern] = (
            dict(patterns) if patterns is not None else dict(_PATTERN_REGISTRY)
        )

    def register(self, pattern: ExperiencePattern) -> None:
        """Add or replace a pattern on this instance."""
        self._patterns[pattern.name] = pattern

    def interpret(
        self,
        completed_intents: Set[str],
        min_confidence: float = 0.0,
    ) -> List[ExperienceLabel]:
        """Match completed_intents against all patterns.

        Returns a list of ExperienceLabel objects sorted by confidence
        descending. Includes a sentinel UNKNOWN label if there are ≥2
        unmatched intents not claimed by any matched pattern.

        Args:
            completed_intents:  Set of intent strings from PrimitiveNormalizer
                                or capability hint strings.
            min_confidence:     Exclude labels below this threshold. Default 0.0
                                (include all matches).
        Returns:
            List of ExperienceLabel, sorted confidence descending.
            The UNKNOWN sentinel (if present) is always last.
        """
        if not completed_intents:
            return []

        labels: List[ExperienceLabel] = []
        all_claimed: Set[str] = set()

        for pattern in self._patterns.values():
            if not pattern.matches(completed_intents):
                continue
            conf = pattern.confidence(completed_intents)
            if conf < min_confidence:
                continue
            matched = pattern.required_intents | (pattern.optional_intents & completed_intents)
            all_claimed.update(matched)
            labels.append(ExperienceLabel(
                name=pattern.name,
                description=pattern.description,
                confidence=conf,
                is_known=True,
                matched_intents=set(matched),
                capability_family=pattern.capability_family,
            ))

        labels.sort(key=lambda lb: lb.confidence, reverse=True)

        # Sentinel for novel / unmatched intents
        unmatched = completed_intents - all_claimed
        if len(unmatched) >= 2:
            labels.append(ExperienceLabel(
                name="unknown_capability_cluster",
                description=(
                    f"Unrecognised intent cluster ({len(unmatched)} intents). "
                    "Candidate for CapabilityHypothesis."
                ),
                confidence=0.0,
                is_known=False,
                unmatched_intents=set(unmatched),
                capability_family=None,
            ))

        return labels

    def interpret_and_report(self, completed_intents: Set[str]) -> str:
        """Return a one-line text report for logging."""
        labels = self.interpret(completed_intents)
        if not labels:
            return "no experiences matched"
        parts = []
        for lb in labels:
            if lb.is_known:
                parts.append(f"{lb.name}({lb.confidence:.2f})")
            else:
                parts.append(f"UNKNOWN[{len(lb.unmatched_intents)}]")
        return " | ".join(parts)

    def known_experience_names(self) -> List[str]:
        """All registered pattern names."""
        return sorted(self._patterns.keys())
