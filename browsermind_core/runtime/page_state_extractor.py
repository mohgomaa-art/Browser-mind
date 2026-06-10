"""
page_state_extractor.py — Live Playwright page signal extraction for L7 classifier.

Executes a single JS bundle against the live page and returns a PageStateSignals
dataclass — a richer superset of EffectSnapshot for classification purposes.

This is the only file that touches Playwright directly in L7. All classifiers
consume PageStateSignals and are therefore unit-testable without a browser.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from playwright.async_api import Page


@dataclass
class PageStateSignals:
    """
    Rich page signal bundle captured from a live page in a single JS evaluation.
    """
    # Location
    url: str = ""
    title: str = ""
    domain: str = ""
    path: str = ""

    # Auth signals
    has_logout_link: bool = False
    has_login_form: bool = False
    has_user_avatar: bool = False
    has_username_display: bool = False
    has_session_cookie: bool = False        # detected via document.cookie parsing

    # Page structure
    element_count: int = 0
    form_count: int = 0
    input_count: int = 0
    visible_button_count: int = 0
    link_count: int = 0
    heading_count: int = 0
    list_item_count: int = 0
    result_count: int = 0
    table_count: int = 0
    iframe_count: int = 0

    # Alert / notification signals
    alert_count: int = 0
    success_alert_count: int = 0
    error_alert_count: int = 0
    validation_count: int = 0

    # Form-specific
    password_field_count: int = 0
    file_input_count: int = 0
    submit_button_count: int = 0
    checkbox_count: int = 0
    select_count: int = 0

    # Wizard / multi-step signals
    has_stepper: bool = False
    stepper_step_count: int = 0
    stepper_current_step: int = 0

    # Modal signals
    has_visible_dialog: bool = False
    has_visible_modal: bool = False

    # Confirmation / success page
    has_confirmation_heading: bool = False
    has_order_number: bool = False

    # Onboarding / pricing
    has_onboarding_cue: bool = False
    has_pricing_tiers: bool = False

    # Upload zone
    has_dropzone: bool = False
    has_file_input: bool = False

    # Content
    content_snippet: str = ""
    content_hash: str = ""
    heading_texts: List[str] = field(default_factory=list)

    # Blocker signals
    has_captcha: bool = False
    has_bot_wall: bool = False
    has_paywall: bool = False
    has_age_gate: bool = False
    has_maintenance: bool = False
    has_geo_block: bool = False

    # Quality
    snapshot_ok: bool = True

    # ------------------------------------------------------------------
    # Compatibility with EffectSnapshot usage in classifier v1
    # ------------------------------------------------------------------
    @property
    def is_empty(self) -> bool:
        return not self.snapshot_ok or (self.url == "" and self.element_count == 0)


_EXTRACTION_SCRIPT = """() => {
    const vis = (el) => {
        try {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        } catch { return false; }
    };
    const q  = (sel) => Array.from(document.querySelectorAll(sel)).filter(vis).length;
    const qA = (sel) => Array.from(document.querySelectorAll(sel)).filter(vis);
    const text = (document.body || document.documentElement).innerText || '';
    const textLow = text.toLowerCase();

    // Alert classification
    const alertEls = qA('[role="alert"], .alert, .notification, .message, .toast, ' +
        '[class*="toast" i], [class*="snackbar" i], [class*="banner" i]');
    const successKw = /success|confirm|complete|done|thank|submitted|saved|congratulations/i;
    const errorKw   = /error|fail|invalid|wrong|incorrect|denied|reject/i;
    const successAlerts = alertEls.filter(el =>
        successKw.test(el.textContent || '') || successKw.test(el.className || '')).length;
    const errorAlerts = alertEls.filter(el =>
        errorKw.test(el.textContent || '') || errorKw.test(el.className || '')).length;

    // Auth signals
    const hasLogout = !!document.querySelector(
        'a[href*="logout" i], a[href*="signout" i], button[class*="logout" i], ' +
        '[data-action*="logout" i], [aria-label*="sign out" i]');
    const hasLoginForm = !!document.querySelector(
        'form input[type="password"], input[autocomplete="current-password"]');
    const hasAvatar = !!document.querySelector(
        '.avatar, [class*="avatar" i], img[alt*="profile" i], img[alt*="avatar" i], ' +
        '[aria-label*="profile picture" i]');
    const hasUsernameDisplay = !!document.querySelector(
        '[class*="username" i], [class*="user-name" i], [data-testid*="username" i], ' +
        '[class*="display-name" i]');
    const cookies = document.cookie || '';
    const hasSessionCookie = /session|sid|auth|token|jwt|access/i.test(cookies);

    // Wizard / stepper
    const stepperEls = qA(
        '[class*="stepper" i], [class*="wizard" i], [class*="progress-steps" i], ' +
        '[role="progressbar"], [class*="step-indicator" i]');
    const hasStepper = stepperEls.length > 0;
    const stepItems = q('[class*="step" i] [class*="step" i], .step, [data-step]');
    const currentStep = qA('.step--active, .step.active, [aria-current="step"]').length;

    // Modal / dialog
    const hasDialog = !!document.querySelector('[role="dialog"], [role="alertdialog"]');
    const hasModal  = !!document.querySelector(
        '.modal.show, .modal[style*="display: block"], [class*="modal-open" i]') ||
        (document.body || document.documentElement).classList.contains('modal-open');

    // Confirmation page signals
    const h1s = Array.from(document.querySelectorAll('h1, h2')).map(e => (e.innerText || '').trim()).filter(Boolean).slice(0, 5);
    const hasConfHeading = h1s.some(t => /order confirmed|payment successful|thank you|registration complete|account created|booking confirmed/i.test(t));
    const hasOrderNum = /order\s*#?[0-9A-Z\-]{4,}|confirmation\s*number/i.test(text);

    // Onboarding / pricing
    const hasOnboarding = /get started|welcome to|set up your|complete your profile|step 1 of/i.test(text.slice(0, 2000));
    const hasPricing = (q('[class*="pricing" i], [class*="plan" i] [class*="price" i]') > 0) ||
        /choose a plan|upgrade your plan|select a tier/i.test(text.slice(0, 2000));

    // Upload zone
    const hasDropzone = !!document.querySelector('[class*="dropzone" i], [class*="drop-zone" i], [data-dropzone]');
    const hasFileInput = !!document.querySelector('input[type="file"]');

    // Blocker signals
    const hasCaptcha   = /recaptcha|hcaptcha|captcha|prove you.{0,15}human/i.test(text.slice(0, 3000));
    const hasBotWall   = /cloudflare|ddos.{0,20}protect|are you human|security check|just a moment/i.test(text.slice(0, 3000));
    const hasPaywall   = /subscribe|upgrade your plan|premium only|members only|paywall/i.test(text.slice(0, 2000));
    const hasAgeGate   = /age verification|must be 18|confirm your age|enter your birth/i.test(text.slice(0, 2000));
    const hasMaintenance = /maintenance mode|down for maintenance|be back soon/i.test(text.slice(0, 2000));
    const hasGeoBlock  = /not available in your (region|country)|geo.{0,10}restrict/i.test(text.slice(0, 2000));

    // Domain / path
    let domain = '', path = '/';
    try {
        const u = new URL(location.href);
        domain = u.hostname;
        path   = u.pathname;
    } catch {}

    return {
        domain, path,
        element_count:       q('*'),
        form_count:          q('form'),
        input_count:         q('input:not([type="hidden"])'),
        visible_button_count:q('button, [role="button"]'),
        link_count:          q('a[href]'),
        heading_count:       q('h1,h2,h3,h4'),
        list_item_count:     q('li, [role="listitem"], article'),
        result_count:        q('[class*="result" i], .search-result'),
        table_count:         q('table, [role="grid"]'),
        iframe_count:        q('iframe'),
        alert_count:         alertEls.length,
        success_alert_count: successAlerts,
        error_alert_count:   errorAlerts,
        validation_count:    q(':invalid, [class*="invalid" i], [class*="field-error" i], .form-error'),
        password_field_count:q('input[type="password"]'),
        file_input_count:    q('input[type="file"]'),
        submit_button_count: q('button[type="submit"], input[type="submit"]'),
        checkbox_count:      q('input[type="checkbox"]'),
        select_count:        q('select'),
        has_logout_link:     hasLogout,
        has_login_form:      hasLoginForm,
        has_user_avatar:     hasAvatar,
        has_username_display:hasUsernameDisplay,
        has_session_cookie:  hasSessionCookie,
        has_stepper:         hasStepper,
        stepper_step_count:  stepItems,
        stepper_current_step:currentStep,
        has_visible_dialog:  hasDialog,
        has_visible_modal:   hasModal,
        has_confirmation_heading: hasConfHeading,
        has_order_number:    hasOrderNum,
        has_onboarding_cue:  hasOnboarding,
        has_pricing_tiers:   hasPricing,
        has_dropzone:        hasDropzone,
        has_file_input:      hasFileInput,
        has_captcha:         hasCaptcha,
        has_bot_wall:        hasBotWall,
        has_paywall:         hasPaywall,
        has_age_gate:        hasAgeGate,
        has_maintenance:     hasMaintenance,
        has_geo_block:       hasGeoBlock,
        heading_texts:       h1s,
        content:             text.slice(0, 200),
        content_full:        text.slice(0, 3000),
    };
}"""


class PageStateExtractor:
    """
    Executes the JS extraction bundle against a live Playwright page.

    Returns a PageStateSignals dataclass. On JS error returns a degraded
    (snapshot_ok=False) instance rather than raising.
    """

    async def extract(self, page: "Page") -> PageStateSignals:
        sig = PageStateSignals()
        try:
            sig.url   = page.url or ""
            sig.title = await page.title() or ""

            raw: Dict = await page.evaluate(_EXTRACTION_SCRIPT)

            sig.domain               = str(raw.get("domain", ""))
            sig.path                 = str(raw.get("path", "/"))
            sig.element_count        = int(raw.get("element_count", 0))
            sig.form_count           = int(raw.get("form_count", 0))
            sig.input_count          = int(raw.get("input_count", 0))
            sig.visible_button_count = int(raw.get("visible_button_count", 0))
            sig.link_count           = int(raw.get("link_count", 0))
            sig.heading_count        = int(raw.get("heading_count", 0))
            sig.list_item_count      = int(raw.get("list_item_count", 0))
            sig.result_count         = int(raw.get("result_count", 0))
            sig.table_count          = int(raw.get("table_count", 0))
            sig.iframe_count         = int(raw.get("iframe_count", 0))
            sig.alert_count          = int(raw.get("alert_count", 0))
            sig.success_alert_count  = int(raw.get("success_alert_count", 0))
            sig.error_alert_count    = int(raw.get("error_alert_count", 0))
            sig.validation_count     = int(raw.get("validation_count", 0))
            sig.password_field_count = int(raw.get("password_field_count", 0))
            sig.file_input_count     = int(raw.get("file_input_count", 0))
            sig.submit_button_count  = int(raw.get("submit_button_count", 0))
            sig.checkbox_count       = int(raw.get("checkbox_count", 0))
            sig.select_count         = int(raw.get("select_count", 0))

            sig.has_logout_link      = bool(raw.get("has_logout_link", False))
            sig.has_login_form       = bool(raw.get("has_login_form", False))
            sig.has_user_avatar      = bool(raw.get("has_user_avatar", False))
            sig.has_username_display = bool(raw.get("has_username_display", False))
            sig.has_session_cookie   = bool(raw.get("has_session_cookie", False))
            sig.has_stepper          = bool(raw.get("has_stepper", False))
            sig.stepper_step_count   = int(raw.get("stepper_step_count", 0))
            sig.stepper_current_step = int(raw.get("stepper_current_step", 0))
            sig.has_visible_dialog   = bool(raw.get("has_visible_dialog", False))
            sig.has_visible_modal    = bool(raw.get("has_visible_modal", False))
            sig.has_confirmation_heading = bool(raw.get("has_confirmation_heading", False))
            sig.has_order_number     = bool(raw.get("has_order_number", False))
            sig.has_onboarding_cue   = bool(raw.get("has_onboarding_cue", False))
            sig.has_pricing_tiers    = bool(raw.get("has_pricing_tiers", False))
            sig.has_dropzone         = bool(raw.get("has_dropzone", False))
            sig.has_file_input       = bool(raw.get("has_file_input", False))
            sig.has_captcha          = bool(raw.get("has_captcha", False))
            sig.has_bot_wall         = bool(raw.get("has_bot_wall", False))
            sig.has_paywall          = bool(raw.get("has_paywall", False))
            sig.has_age_gate         = bool(raw.get("has_age_gate", False))
            sig.has_maintenance      = bool(raw.get("has_maintenance", False))
            sig.has_geo_block        = bool(raw.get("has_geo_block", False))
            sig.heading_texts        = [str(h) for h in (raw.get("heading_texts") or [])]
            sig.content_snippet      = str(raw.get("content", ""))
            full_text                = str(raw.get("content_full", ""))
            sig.content_hash         = hashlib.md5(
                full_text.encode("utf-8", errors="replace")
            ).hexdigest()
            sig.snapshot_ok = True

        except Exception:
            sig.snapshot_ok = False

        return sig
