"""
BrowserMind — State Family Builder v5
======================================
5-tier semantic classification cascade (topology is last resort).

TAXONOMY v2.0
  login_form, signup_form, search_interface, newsletter_signup, landing_page,
  navigation_hub, article_page, action_toolbar, dialog, dialog_form,
  content_feed, multi_field_form, post_composer, data_table, dropdown_menu,
  generic_interactive
"""
from __future__ import annotations

import collections
import hashlib
from typing import Any, Dict, List, Tuple

from training.compiler.region_segmenter import RegionSegmenter

TAXONOMY_VERSION = "2.0"

# --- Signal families (keyword sets, not single-word rules) ---
_PASSWORD_TERMS = frozenset(
    {"password", "passwd", "كلمة المرور", "mot de passe", "contraseña", "passwort"}
)
_EMAIL_TERMS = frozenset({"email", "e-mail", "mail", "بريد", "correo"})
_USERNAME_TERMS = frozenset({"username", "user name", "login", "اسم المستخدم"})
_CONFIRM_TERMS = frozenset(
    {"confirm", "repeat", "verify", "re-enter", "confirmation", "تأكيد"}
)
_CREATE_ACCOUNT_TERMS = frozenset(
    {"create account", "new account", "choose a password", "إنشاء"}
)

_LOGIN_TERMS = frozenset(
    {"sign in", "log in", "login", "signin", "تسجيل الدخول", "connexion", "iniciar sesión"}
)
_SIGNUP_TERMS = frozenset(
    {
        "sign up",
        "signup",
        "create account",
        "register",
        "join",
        "get started",
        "إنشاء حساب",
        "التسجيل",
    }
)
_SEARCH_TERMS = frozenset(
    {"search", "query", "find", "lookup", "بحث", "recherche", "buscar"}
)
_NEWSLETTER_TERMS = frozenset(
    {
        "subscribe",
        "newsletter",
        "waitlist",
        "updates",
        "early access",
        "notify me",
        "join waitlist",
        "get updates",
        "stay in the loop",
        "اشترك",
        "القائمة البريدية",
    }
)
_LANDING_TERMS = frozenset(
    {
        "get started",
        "try for free",
        "pricing",
        "features",
        "solutions",
        "learn more",
        "platform",
        "ابدأ الآن",
    }
)

_HEADING_LOGIN = frozenset({"log in", "sign in", "login", "تسجيل الدخول"})
_HEADING_SIGNUP = frozenset(
    {"create account", "sign up", "register", "join", "إنشاء حساب"}
)
_HEADING_CONTACT = frozenset({"contact", "get in touch", "reach us", "اتصل"})
_HEADING_SETTINGS = frozenset({"settings", "profile", "preferences", "account settings"})
_HEADING_SEARCH = frozenset({"search", "find", "بحث"})


def _name_matches(name: str, keywords: frozenset) -> bool:
    return any(kw in name for kw in keywords)


def _count_matches(names: List[str], keywords: frozenset) -> int:
    return sum(1 for name in names if _name_matches(name, keywords))


def _zone_score(
    textboxes: List[Dict],
    searchboxes: List[Dict],
    checkboxes: List[Dict],
    buttons: List[Dict],
) -> float:
    inputs = len(textboxes) + len(searchboxes)
    score = (inputs * 3.0) + (len(searchboxes) * 3.0) + (len(checkboxes) * 1.5) + (len(buttons) * 1.0)
    if (inputs > 0 or searchboxes) and buttons:
        score += 2.0
    return score


def _confidence_from_scores(winner: float, runner_up: float, ceiling: float = 0.99) -> float:
    if winner <= 0:
        return 0.1
    margin = (winner - runner_up) / winner if winner > 0 else 0.0
    base = min(winner / 8.0, 1.0)
    conf = base * (0.6 + 0.4 * margin)
    return max(0.1, min(round(conf, 2), ceiling))


class StateFamilyBuilder:
    def __init__(self):
        self.segmenter = RegionSegmenter()

    def identify_zones(self, ax_graph: Dict[str, Any]) -> Dict[str, Any]:
        regions = self.segmenter.segment(ax_graph)
        zones = []

        for r in regions:
            member_nodes = list(r["nodes"])
            if not member_nodes:
                continue

            family, score, confidence = self._classify_and_score(member_nodes, r["region_type"])
            role_counts = r["roles"]

            hash_base = (
                f"{r['region_type']}-{r['node_count']}-"
                + "-".join(f"{k}:{role_counts[k]}" for k in sorted(role_counts))
            )

            zones.append(
                {
                    "family": family,
                    "confidence": confidence,
                    "taxonomy_version": TAXONOMY_VERSION,
                    "family_hash": hashlib.md5(hash_base.encode()).hexdigest()[:8],
                    "zone_score": round(score, 3),
                    "role_counts": role_counts,
                    "node_idxs": [n["idx"] for n in member_nodes],
                    "anchor_role": r["region_type"],
                    "node_count": r["node_count"],
                }
            )

        zones.sort(key=lambda z: z["zone_score"], reverse=True)

        seen: Dict[tuple, bool] = {}
        deduped = []
        for z in zones:
            key = (z["family"], z["family_hash"])
            if key not in seen:
                seen[key] = True
                deduped.append(z)

        unclassified = sum(
            1
            for z in deduped
            if z["family"]
            in ("generic_interactive", "generic_page", "empty_page", "root_fallback")
        )

        return {
            "zones": deduped,
            "primary_zone": deduped[0] if deduped else None,
            "unclassified_count": unclassified,
        }

    def identify_family(self, ax_graph: Dict[str, Any], url: str = "") -> Dict[str, Any]:
        result = self.identify_zones(ax_graph)
        primary = result.get("primary_zone")
        if primary:
            return {
                "state_family": primary["family"],
                "confidence": primary["confidence"],
                "taxonomy_version": primary["taxonomy_version"],
                "family_hash": primary["family_hash"],
                "family_version": 5,
                "primary_zone": {
                    "size": len(primary["node_idxs"]),
                    "role_counts": primary["role_counts"],
                },
            }
        return {
            "state_family": "empty_page",
            "confidence": 1.0,
            "taxonomy_version": TAXONOMY_VERSION,
            "family_hash": "00000000",
            "family_version": 5,
            "primary_zone": {"size": 0, "role_counts": {}},
        }

    def _extract_signals(self, member_nodes: List[Dict]) -> Dict[str, Any]:
        textboxes = [
            n for n in member_nodes if n.get("role") in ("textbox", "combobox", "searchbox")
        ]
        buttons = [n for n in member_nodes if n.get("role") == "button"]
        links = [n for n in member_nodes if n.get("role") == "link"]
        headings = [n for n in member_nodes if n.get("role") == "heading"]
        searchboxes = [n for n in member_nodes if n.get("role") == "searchbox"]
        checkboxes = [n for n in member_nodes if n.get("role") in ("checkbox", "radio")]
        menus = [n for n in member_nodes if n.get("role") == "menuitem"]
        listitems = [n for n in member_nodes if n.get("role") == "listitem"]

        tb_names = [n.get("name", "").lower().strip() for n in textboxes]
        btn_names = [n.get("name", "").lower().strip() for n in buttons]
        hdg_names = [n.get("name", "").lower().strip() for n in headings]
        link_names = [n.get("name", "").lower().strip() for n in links]

        inputs = len(textboxes)

        return {
            "textboxes": textboxes,
            "buttons": buttons,
            "links": links,
            "headings": headings,
            "searchboxes": searchboxes,
            "checkboxes": checkboxes,
            "menus": menus,
            "listitems": listitems,
            "tb_names": tb_names,
            "btn_names": btn_names,
            "hdg_names": hdg_names,
            "link_names": link_names,
            "inputs": inputs,
            "has_password_input": _count_matches(tb_names, _PASSWORD_TERMS) > 0,
            "has_searchbox_role": len(searchboxes) > 0,
            "has_search_input": _count_matches(tb_names, _SEARCH_TERMS) > 0,
            "has_email_input": _count_matches(tb_names, _EMAIL_TERMS) > 0,
            "has_username_input": _count_matches(tb_names, _USERNAME_TERMS) > 0,
            "login_btn": _count_matches(btn_names, _LOGIN_TERMS) > 0,
            "signup_btn": _count_matches(btn_names, _SIGNUP_TERMS) > 0,
            "search_btn": _count_matches(btn_names, _SEARCH_TERMS) > 0,
            "newsletter_btn": _count_matches(btn_names, _NEWSLETTER_TERMS) > 0,
            "landing_btn": _count_matches(btn_names, _LANDING_TERMS) > 0,
            "long_buttons": sum(1 for name in btn_names if len(name) > 25),
            "zone_score": _zone_score(textboxes, searchboxes, checkboxes, buttons),
            "total_nodes": len(member_nodes),
        }

    def _auth_scores(self, sig: Dict[str, Any]) -> Tuple[float, float]:
        """Login vs signup when password textbox is present (never use input count alone)."""
        tb_names = sig["tb_names"]
        btn_names = sig["btn_names"]

        login_score = 5.0  # password present → auth region
        login_score += _count_matches(btn_names, _LOGIN_TERMS) * 2.0
        login_score += _count_matches(tb_names, _USERNAME_TERMS) * 1.5

        signup_score = 0.0
        signup_score += _count_matches(btn_names, _SIGNUP_TERMS) * 4.0
        signup_score += _count_matches(tb_names, _CONFIRM_TERMS) * 3.0
        signup_score += _count_matches(tb_names, _CREATE_ACCOUNT_TERMS) * 3.0
        if sig["signup_btn"] and not sig["login_btn"]:
            signup_score += 2.0

        return login_score, signup_score

    def _heading_family(self, hdg_names: List[str]) -> str | None:
        for name in hdg_names:
            if _name_matches(name, _HEADING_LOGIN):
                return "login_form"
            if _name_matches(name, _HEADING_SIGNUP):
                return "signup_form"
            if _name_matches(name, _HEADING_CONTACT):
                return "multi_field_form"
            if _name_matches(name, _HEADING_SETTINGS):
                return "multi_field_form"
            if _name_matches(name, _HEADING_SEARCH):
                return "search_interface"
        return None

    def _topology_scores(self, sig: Dict[str, Any], anchor_type: str) -> Dict[str, float]:
        scores: Dict[str, float] = collections.defaultdict(float)
        inputs = sig["inputs"]
        buttons = sig["buttons"]
        links = sig["links"]
        listitems = sig["listitems"]
        menus = sig["menus"]

        if anchor_type == "navigation":
            scores["navigation_hub"] += 5.0
        if inputs == 0 and len(links) >= 8 and len(buttons) <= 2:
            scores["navigation_hub"] += 4.0

        if inputs == 0 and len(listitems) >= 5:
            scores["content_feed"] += 4.0

        if anchor_type == "article":
            scores["article_page"] += 5.0
        if inputs == 0 and len(links) >= 3 and len(buttons) >= 1:
            scores["article_page"] += 2.0

        if inputs == 0 and len(links) <= 1 and len(buttons) >= 3:
            scores["action_toolbar"] += 4.0

        if len(menus) >= 5:
            scores["dropdown_menu"] += 4.0

        if inputs == 1 and len(buttons) >= 2:
            scores["post_composer"] += 3.0

        return scores

    def _semantic_scores(self, sig: Dict[str, Any]) -> Dict[str, float]:
        """Tier 3 semantic scores (no password field)."""
        scores: Dict[str, float] = collections.defaultdict(float)
        tb_names = sig["tb_names"]
        btn_names = sig["btn_names"]

        search_tb = _count_matches(tb_names, _SEARCH_TERMS)
        search_btn = _count_matches(btn_names, _SEARCH_TERMS)
        scores["search_interface"] += search_tb * 4.0 + search_btn * 2.0
        if search_tb > 0 and search_btn > 0:
            scores["search_interface"] += 3.0

        newsletter_btn = _count_matches(btn_names, _NEWSLETTER_TERMS)
        scores["newsletter_signup"] += newsletter_btn * 4.0
        if newsletter_btn > 0 and sig["has_email_input"] and sig["inputs"] <= 2:
            scores["newsletter_signup"] += 4.0

        landing_btn = _count_matches(btn_names, _LANDING_TERMS)
        scores["landing_page"] += landing_btn * 2.0
        scores["landing_page"] += sig["long_buttons"] * 1.5
        if sig["has_email_input"] and not sig["has_password_input"]:
            scores["landing_page"] += 2.0
        if sig["inputs"] <= 2 and not sig["has_password_input"] and len(sig["buttons"]) >= 3:
            scores["landing_page"] += 2.0

        landing_signals = sig["long_buttons"] >= 3 or landing_btn >= 2
        if sig["login_btn"] and (sig["has_email_input"] or sig["has_username_input"]):
            if not landing_signals:
                scores["login_form"] += 4.0
            else:
                scores["login_form"] += 0.5  # nav "Sign in" on marketing pages

        if sig["inputs"] >= 5 and len(sig["buttons"]) >= 1:
            scores["multi_field_form"] += 4.0 + sig["inputs"] * 0.5

        return scores

    def _classify_and_score(
        self, member_nodes: List[Dict], anchor_type: str
    ) -> Tuple[str, float, float]:
        if not member_nodes:
            return "empty_page", 0.0, 1.0

        sig = self._extract_signals(member_nodes)
        zone_score = sig["zone_score"]

        # --- Tier 0: WAI-ARIA structural override ---
        if anchor_type == "search" or sig["has_searchbox_role"]:
            return "search_interface", zone_score, 0.95

        if anchor_type == "dialog" or any(n.get("role") == "dialog" for n in member_nodes):
            if sig["inputs"] >= 1 and len(sig["buttons"]) >= 1:
                return "dialog_form", zone_score, 0.90
            return "dialog", zone_score, 0.90

        if any(n.get("role") in ("table", "grid") for n in member_nodes):
            return "data_table", zone_score, 0.90

        # --- Tier 1: Password textbox only (never button names) ---
        if sig["has_password_input"]:
            login_score, signup_score = self._auth_scores(sig)
            if signup_score > login_score:
                conf = _confidence_from_scores(signup_score, login_score, 0.95)
                return "signup_form", zone_score, conf
            conf = _confidence_from_scores(login_score, signup_score, 0.95)
            return "login_form", zone_score, max(conf, 0.85)

        # --- Tier 2: Search input / role ---
        if sig["has_search_input"]:
            return "search_interface", zone_score, 0.90

        # --- Tier 3: Semantic name analysis (score-based) ---
        scores = self._semantic_scores(sig)

        # Strong single-family shortcuts before heading/topology merge
        if sig["newsletter_btn"] and sig["has_email_input"] and sig["inputs"] <= 2:
            if scores["newsletter_signup"] >= scores["landing_page"]:
                return "newsletter_signup", zone_score, 0.82

        landing_signals = sig["long_buttons"] >= 3 or sig["landing_btn"]
        if (
            sig["has_email_input"]
            and not sig["has_password_input"]
            and landing_signals
            and scores["landing_page"] >= scores.get("login_form", 0)
        ):
            return "landing_page", zone_score, 0.80

        # --- Tier 4: Heading context ---
        heading_family = self._heading_family(sig["hdg_names"])
        if heading_family:
            return heading_family, zone_score, 0.85

        # --- Tier 5: Topology + semantic winner ---
        for family, val in self._topology_scores(sig, anchor_type).items():
            scores[family] += val

        best_family = "generic_interactive"
        best_score = 0.0
        runner_up = 0.0
        for family, s in scores.items():
            if s > best_score:
                runner_up = best_score
                best_score = s
                best_family = family
            elif s > runner_up:
                runner_up = s

        confidence = _confidence_from_scores(best_score, runner_up)
        return best_family, zone_score, confidence
