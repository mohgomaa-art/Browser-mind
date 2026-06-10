"""
BrowserMind — Form Expert
==========================
Expert heuristic متخصص للـ forms المعقدة.

يُكمّل `graph_builder.decide_expert_action` بـ logic أعمق لـ:
  - Dropdowns (combobox / listbox / option)
  - Checkboxes & Radio buttons
  - Multi-step wizard forms
  - Signup / Registration flows
  - Login / Logout flows
  - Date pickers
  - Address forms (country → region chain)
  - Password fields
  - Submit / Continue / Next buttons

الاستخدام:
    from training.form_expert import FormExpert

    expert = FormExpert()
    action = expert.decide(graph, goal, page_url, step_history)
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _name(nd: Dict) -> str:
    return str(nd.get("name", "") or "").lower().strip()

def _role(nd: Dict) -> str:
    return str(nd.get("role", "generic")).lower()

def _val(nd: Dict) -> str:
    return str(nd.get("value", "") or "").lower().strip()

def _idx(nd: Dict) -> int:
    return int(nd.get("idx", 0))

def _find_by_role(nodes: List[Dict], *roles) -> List[Dict]:
    role_set = set(roles)
    return [nd for nd in nodes if _role(nd) in role_set]

def _find_by_name_contains(nodes: List[Dict], *keywords) -> Optional[Dict]:
    """أول node اسمه يحتوي على أي keyword."""
    for kw in keywords:
        kw_l = kw.lower()
        for nd in nodes:
            if kw_l in _name(nd):
                return nd
    return None

def _find_empty_input(nodes: List[Dict]) -> Optional[Dict]:
    """أول textbox / searchbox فاضي."""
    for nd in nodes:
        if _role(nd) in ("textbox", "searchbox") and not _val(nd) and not nd.get("focused"):
            return nd
    return None

def _find_focused(nodes: List[Dict]) -> Optional[Dict]:
    for nd in nodes:
        if nd.get("focused"):
            return nd
    return None

def _find_submit_button(nodes: List[Dict]) -> Optional[Dict]:
    """زرار submit / continue / next / proceed."""
    SUBMIT_KEYWORDS = (
        "submit", "continue", "next", "proceed", "register", "create account",
        "sign up", "join", "complete", "finish", "confirm", "save", "update",
        "send", "done", "ok", "accept",
    )
    buttons = _find_by_role(nodes, "button")
    for kw in SUBMIT_KEYWORDS:
        for btn in buttons:
            if kw in _name(btn):
                return btn
    return None

def _find_login_button(nodes: List[Dict]) -> Optional[Dict]:
    LOGIN_KEYWORDS = ("sign in", "log in", "login", "signin")
    buttons = _find_by_role(nodes, "button")
    for kw in LOGIN_KEYWORDS:
        for btn in buttons:
            if kw in _name(btn):
                return btn
    # fallback: any submit-looking button
    return _find_submit_button(nodes)

def _find_logout_button(nodes: List[Dict]) -> Optional[Dict]:
    LOGOUT_KEYWORDS = ("sign out", "log out", "logout", "signout", "déconnexion")
    for kw in LOGOUT_KEYWORDS:
        nd = _find_by_name_contains(nodes, kw)
        if nd:
            return nd
    return None

def _find_unchecked_checkbox(nodes: List[Dict], name_hint: str = "") -> Optional[Dict]:
    """Checkbox غير محدد، وإن في hint يفضل المطابق."""
    checkboxes = [nd for nd in nodes if _role(nd) == "checkbox"]
    if name_hint:
        hint_l = name_hint.lower()
        for cb in checkboxes:
            if hint_l in _name(cb) and not _val(cb):
                return cb
    # fallback: أول checkbox مش checked
    for cb in checkboxes:
        v = _val(cb)
        if v not in ("true", "checked", "on", "1"):
            return cb
    return None

def _find_radio(nodes: List[Dict], name_hint: str) -> Optional[Dict]:
    radios = [nd for nd in nodes if _role(nd) == "radio"]
    hint_l = name_hint.lower()
    for rd in radios:
        if hint_l in _name(rd):
            return rd
    return radios[0] if radios else None

def _find_combobox(nodes: List[Dict], name_hint: str = "") -> Optional[Dict]:
    combos = _find_by_role(nodes, "combobox")
    if name_hint:
        hint_l = name_hint.lower()
        for cb in combos:
            if hint_l in _name(cb):
                return cb
    return combos[0] if combos else None

def _find_option(nodes: List[Dict], name_hint: str) -> Optional[Dict]:
    options = _find_by_role(nodes, "option", "menuitem", "listitem")
    hint_l = name_hint.lower()
    for opt in options:
        if hint_l in _name(opt):
            return opt
    return None

def _extract_quoted_value(goal: str) -> Optional[str]:
    """استخرج القيمة بين علامات التنصيص."""
    m = re.search(r"['\"]([^'\"]+)['\"]", goal)
    return m.group(1) if m else None

def _extract_email(goal: str) -> Optional[str]:
    m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", goal)
    return m.group(0) if m else None

def _extract_phone(goal: str) -> Optional[str]:
    m = re.search(r"[\+\d][\d\s\-]{7,15}", goal)
    return m.group(0).strip() if m else None

def _extract_name(goal: str) -> Optional[str]:
    """استخرج اسم شخص من الـ goal."""
    m = re.search(
        r"(?:name|username|first name|last name)\s+(?:with\s+)?([A-Za-z\u0600-\u06FF][A-Za-z\u0600-\u06FF\s]{1,40}?)(?:\s+and|\s+in|\s*,|\s*$)",
        goal, re.IGNORECASE
    )
    if m:
        return m.group(1).strip()
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  FormExpert
# ─────────────────────────────────────────────────────────────────────────────

class FormExpert:
    """
    Expert heuristic متخصص للـ form interactions المعقدة.

    يُستدعى من graph_builder.decide_expert_action كـ fallback
    عندما تكون المهمة form-heavy.
    """

    # keyword sets للكشف عن نوع المهمة
    _SIGNUP_KW   = ("sign up", "signup", "register", "create account", "join",
                    "registration", "new account", "إنشاء حساب", "تسجيل")
    _LOGIN_KW    = ("log in", "login", "sign in", "signin",
                    "تسجيل الدخول", "ادخل")
    _LOGOUT_KW   = ("log out", "logout", "sign out", "signout",
                    "تسجيل الخروج", "اخرج")
    _DROPDOWN_KW = ("select", "choose", "pick", "dropdown", "option",
                    "اختر", "حدد")
    _CHECKBOX_KW = ("check", "uncheck", "tick", "select", "enable",
                    "اختر", "حدد الخيار")
    _FILL_KW     = ("fill", "enter", "type", "input", "write", "put",
                    "post", "publish", "compose", "comment",
                    "اكتب", "ادخل", "املأ")

    def _detect_intent(self, goal_l: str) -> str:
        """كشف نوع المهمة من الـ goal."""
        if any(kw in goal_l for kw in self._LOGOUT_KW):
            return "logout"
        if any(kw in goal_l for kw in self._SIGNUP_KW):
            return "signup"
        if any(kw in goal_l for kw in self._LOGIN_KW):
            return "login"
        if any(kw in goal_l for kw in self._DROPDOWN_KW):
            return "dropdown"
        if any(kw in goal_l for kw in self._CHECKBOX_KW):
            return "checkbox"
        if any(kw in goal_l for kw in self._FILL_KW):
            return "fill"
        return "unknown"

    # ── Action builders ───────────────────────────────────────────────────

    @staticmethod
    def _click(nd: Dict, label: str = "") -> Dict:
        return {
            "type": "click",
            "action_id": 1,
            "element_idx": _idx(nd),
            "value": "",
            "_reason": label or f"click:{_name(nd)}",
        }

    @staticmethod
    def _type(nd: Dict, value: str, label: str = "") -> Dict:
        return {
            "type": "type",
            "action_id": 2,
            "element_idx": _idx(nd),
            "value": value,
            "_reason": label or f"type:{value[:30]}→{_name(nd)}",
        }

    @staticmethod
    def _scroll() -> Dict:
        return {
            "type": "scroll",
            "action_id": 3,
            "element_idx": None,
            "value": "",
            "_reason": "scroll:reveal_more",
        }

    @staticmethod
    def _wait() -> Dict:
        return {
            "type": "wait",
            "action_id": 4,
            "element_idx": None,
            "value": "",
            "_reason": "wait:loading",
        }

    # ── Intent handlers ───────────────────────────────────────────────────

    def _handle_logout(self, nodes: List[Dict], goal_l: str) -> Optional[Dict]:
        """ابحث عن زرار Sign Out / Log Out."""
        btn = _find_logout_button(nodes)
        if btn:
            return self._click(btn, "logout:button")

        # قد يكون في قائمة منسدلة — ابحث عن avatar/profile أولاً
        profile_hints = ("profile", "account", "user", "avatar", "me", "you")
        profile_btn = _find_by_name_contains(nodes, *profile_hints)
        if profile_btn and _role(profile_btn) in ("button", "link", "menuitem"):
            return self._click(profile_btn, "logout:open_menu")

        return None

    def _handle_login(self, nodes: List[Dict], goal_l: str) -> Optional[Dict]:
        """ملء حقول username/email + password + click login."""
        email = _extract_email(goal_l)
        password_hint = re.search(
            r"password[:\s]+([^\s,]+)", goal_l, re.IGNORECASE
        )
        password = password_hint.group(1) if password_hint else None

        # أول حقل فاضي: email/username
        email_field = _find_by_name_contains(
            nodes, "email", "username", "user name", "login", "identifier",
            "البريد", "اسم المستخدم"
        )
        if email_field and _role(email_field) in ("textbox", "searchbox"):
            if not _val(email_field):
                return self._type(
                    email_field,
                    email or "testuser@example.com",
                    "login:fill_email"
                )

        # حقل password
        pwd_field = _find_by_name_contains(nodes, "password", "كلمة المرور")
        if pwd_field and _role(pwd_field) in ("textbox", "searchbox"):
            if not _val(pwd_field):
                return self._type(
                    pwd_field,
                    password or "TestPass123!",
                    "login:fill_password"
                )

        # زرار login
        btn = _find_login_button(nodes)
        if btn:
            return self._click(btn, "login:submit")

        return None

    def _handle_signup(self, nodes: List[Dict], goal_l: str) -> Optional[Dict]:
        """ملء نموذج التسجيل خطوة بخطوة."""
        email    = _extract_email(goal_l)
        phone    = _extract_phone(goal_l)
        name_val = _extract_name(goal_l)

        # First name
        fname_field = _find_by_name_contains(
            nodes, "first name", "firstname", "given name", "الاسم الأول", "name"
        )
        if fname_field and _role(fname_field) in ("textbox", "searchbox"):
            if not _val(fname_field):
                first = (name_val or "Test User").split()[0]
                return self._type(fname_field, first, "signup:first_name")

        # Last name
        lname_field = _find_by_name_contains(
            nodes, "last name", "lastname", "family name", "surname",
            "الاسم الأخير", "العائلة"
        )
        if lname_field and _role(lname_field) in ("textbox", "searchbox"):
            if not _val(lname_field):
                parts = (name_val or "Test User").split()
                last = parts[-1] if len(parts) > 1 else "User"
                return self._type(lname_field, last, "signup:last_name")

        # Username
        uname_field = _find_by_name_contains(
            nodes, "username", "user name", "handle", "اسم المستخدم"
        )
        if uname_field and _role(uname_field) in ("textbox", "searchbox"):
            if not _val(uname_field):
                return self._type(uname_field, "testuser_2024", "signup:username")

        # Email
        email_field = _find_by_name_contains(
            nodes, "email", "e-mail", "البريد الإلكتروني"
        )
        if email_field and _role(email_field) in ("textbox", "searchbox"):
            if not _val(email_field):
                return self._type(
                    email_field,
                    email or "newuser@test.example.com",
                    "signup:email"
                )

        # Phone
        phone_field = _find_by_name_contains(
            nodes, "phone", "mobile", "telephone", "رقم الهاتف", "الجوال"
        )
        if phone_field and _role(phone_field) in ("textbox", "searchbox"):
            if not _val(phone_field):
                return self._type(
                    phone_field,
                    phone or "01012345678",
                    "signup:phone"
                )

        # Password
        pwd_fields = [
            nd for nd in nodes
            if _role(nd) in ("textbox", "searchbox")
            and "password" in _name(nd)
            and not _val(nd)
        ]
        if pwd_fields:
            return self._type(pwd_fields[0], "SecurePass123!", "signup:password")

        # Confirm password
        confirm_fields = [
            nd for nd in nodes
            if _role(nd) in ("textbox", "searchbox")
            and any(k in _name(nd) for k in ("confirm", "repeat", "retype", "تأكيد"))
            and not _val(nd)
        ]
        if confirm_fields:
            return self._type(confirm_fields[0], "SecurePass123!", "signup:confirm_pwd")

        # Terms checkbox
        terms_cb = _find_unchecked_checkbox(nodes, "terms") or \
                   _find_unchecked_checkbox(nodes, "agree") or \
                   _find_unchecked_checkbox(nodes, "privacy")
        if terms_cb:
            return self._click(terms_cb, "signup:accept_terms")

        # Submit / Register button
        btn = _find_submit_button(nodes)
        if btn:
            return self._click(btn, "signup:submit")

        return None

    def _handle_dropdown(self, nodes: List[Dict], goal_l: str) -> Optional[Dict]:
        """اختيار من dropdown / combobox."""
        # استخرج القيمة المطلوبة
        target = _extract_quoted_value(goal_l)
        if not target:
            # حاول استخراج من pattern "select X from"
            m = re.search(
                r"select\s+(.+?)\s+(?:from|in|as|option)", goal_l, re.IGNORECASE
            )
            target = m.group(1).strip() if m else None

        # هل في options مفتوحة (list مفتوحة)؟
        options = _find_by_role(nodes, "option")
        if options and target:
            opt = _find_option(nodes, target)
            if opt:
                return self._click(opt, f"dropdown:select_option:{target}")
            # اختار أول option
            return self._click(options[0], "dropdown:select_first_option")

        # افتح الـ combobox
        combo_hint = ""
        if "size" in goal_l:
            combo_hint = "size"
        elif "country" in goal_l:
            combo_hint = "country"
        elif "region" in goal_l or "state" in goal_l:
            combo_hint = "region"
        elif "language" in goal_l:
            combo_hint = "language"
        elif "color" in goal_l or "colour" in goal_l:
            combo_hint = "color"

        combo = _find_combobox(nodes, combo_hint)
        if combo:
            return self._click(combo, f"dropdown:open:{combo_hint or 'combobox'}")

        # أي menuitem مطابق
        if target:
            mi = _find_option(nodes, target)
            if mi:
                return self._click(mi, f"dropdown:click_menuitem:{target}")

        return None

    def _handle_checkbox(self, nodes: List[Dict], goal_l: str) -> Optional[Dict]:
        """تحديد / إلغاء تحديد checkbox أو radio."""
        # radio buttons
        if "radio" in goal_l or any(
            k in goal_l for k in ("male", "female", "other", "yes", "no",
                                   "impressive", "option 1", "option 2")
        ):
            target_hint = ""
            for word in ("male", "female", "other", "yes", "no",
                         "impressive", "option 1", "option 2"):
                if word in goal_l:
                    target_hint = word
                    break
            radio = _find_radio(nodes, target_hint)
            if radio:
                return self._click(radio, f"checkbox:radio:{target_hint}")

        # استخرج اسم الـ checkbox من الـ goal
        hint = ""
        for kw in ("bacon", "terms", "agree", "privacy", "newsletter",
                   "sports", "reading", "music", "home", "desktop",
                   "remember", "subscribe", "accept", "private",
                   "express", "standard"):
            if kw in goal_l:
                hint = kw
                break

        cb = _find_unchecked_checkbox(nodes, hint)
        if cb:
            return self._click(cb, f"checkbox:check:{hint or 'first'}")

        # all checkboxes
        if "all" in goal_l:
            cbs = [nd for nd in nodes if _role(nd) == "checkbox"]
            if cbs:
                return self._click(cbs[0], "checkbox:check_all_start")

        return None

    def _handle_fill(self, nodes: List[Dict], goal_l: str) -> Optional[Dict]:
        """ملء حقل input معين."""
        email = _extract_email(goal_l)
        phone = _extract_phone(goal_l)
        quoted = _extract_quoted_value(goal_l)

        # تحديد الحقل المقصود
        field_hints = {
            "email":   (("email", "e-mail", "البريد"),    email or "test@example.com"),
            "phone":   (("phone", "mobile", "telephone", "الهاتف"), phone or "01012345678"),
            "name":    (("name", "الاسم"),                 quoted or "Test User"),
            "first":   (("first name", "firstname"),       quoted or "John"),
            "last":    (("last name", "lastname"),         quoted or "Smith"),
            "user":    (("username", "user name"),         quoted or "testuser"),
            "message": (("message", "description", "body", "الرسالة"), quoted or "Test message content"),
            "address": (("address", "street", "العنوان"), quoted or "123 Main Street"),
            "city":    (("city", "المدينة"),               quoted or "Cairo"),
            "zip":     (("zip", "postal", "الرمز البريدي"), quoted or "11511"),
            "company": (("company", "organization", "الشركة"), quoted or "Test Company"),
            "title":   (("title", "subject", "العنوان"),  quoted or "Test Title"),
            "bio":     (("bio", "about", "نبذة"),          quoted or "Software developer"),
        }

        for key, (kws, default_val) in field_hints.items():
            if key in goal_l or any(kw in goal_l for kw in kws):
                field = _find_by_name_contains(nodes, *kws)
                if field and _role(field) in ("textbox", "searchbox"):
                    if not _val(field):
                        return self._type(field, default_val, f"fill:{key}")

        # fallback: أول حقل فاضي
        empty = _find_empty_input(nodes)
        if empty:
            val = quoted or email or phone or "test input"
            return self._type(empty, val, "fill:first_empty")

        # submit
        btn = _find_submit_button(nodes)
        if btn:
            return self._click(btn, "fill:submit")

        return None

    # ── Main entry point ──────────────────────────────────────────────────

    def decide(
        self,
        graph:        Dict,
        goal:         str,
        page_url:     str   = "",
        step_history: List[Dict] | None = None,
    ) -> Optional[Dict]:
        """
        يحاول يحدد الـ expert action للـ form interaction.
        يرجع None لو مش متأكد (fallback to graph_builder).
        """
        nodes    = graph.get("nodes", [])
        goal_l   = goal.lower()
        intent   = self._detect_intent(goal_l)

        if not nodes:
            return self._wait()

        # ── Logout له أولوية عالية ────────────────────────────────────────
        if intent == "logout":
            action = self._handle_logout(nodes, goal_l)
            if action:
                return action

        # ── Login ─────────────────────────────────────────────────────────
        if intent == "login":
            action = self._handle_login(nodes, goal_l)
            if action:
                return action

        # ── Signup ────────────────────────────────────────────────────────
        if intent == "signup":
            action = self._handle_signup(nodes, goal_l)
            if action:
                return action

        # ── Dropdown ──────────────────────────────────────────────────────
        if intent == "dropdown" or _find_by_role(nodes, "combobox", "listbox", "option"):
            if intent in ("dropdown", "unknown"):
                action = self._handle_dropdown(nodes, goal_l)
                if action:
                    return action

        # ── Checkbox / Radio ──────────────────────────────────────────────
        if intent == "checkbox" or _find_by_role(nodes, "checkbox", "radio"):
            if intent in ("checkbox", "unknown"):
                action = self._handle_checkbox(nodes, goal_l)
                if action:
                    return action

        # ── Fill ──────────────────────────────────────────────────────────
        if intent in ("fill", "unknown"):
            action = self._handle_fill(nodes, goal_l)
            if action:
                return action

        # ── آخر ملاذ: scroll لاكتشاف المزيد ─────────────────────────────
        return self._scroll()


# ─────────────────────────────────────────────────────────────────────────────
#  Integration helper — يُستدعى من graph_builder
# ─────────────────────────────────────────────────────────────────────────────

_FORM_EXPERT = FormExpert()

def form_expert_action(
    graph:        Dict,
    goal:         str,
    page_url:     str = "",
    step_history: List[Dict] | None = None,
) -> Optional[Dict]:
    """
    Thin wrapper يُستخدم من graph_builder.decide_expert_action.
    يرجع None لو FormExpert مش واثق.
    """
    return _FORM_EXPERT.decide(graph, goal, page_url, step_history)


# ─────────────────────────────────────────────────────────────────────────────
#  Quick self-test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    expert = FormExpert()

    test_cases = [
        # (goal, nodes, expected_action_type)
        (
            "login to GitHub with username testuser and password testpass123",
            [
                {"idx": 0, "role": "textbox", "name": "username", "value": "", "focused": False, "depth": 2},
                {"idx": 1, "role": "textbox", "name": "password", "value": "", "focused": False, "depth": 2},
                {"idx": 2, "role": "button",  "name": "sign in",  "value": "", "focused": False, "depth": 2},
            ],
            "type",  # fill username first
        ),
        (
            "select large from the pizza size dropdown",
            [
                {"idx": 0, "role": "combobox", "name": "pizza size", "value": "medium", "focused": False, "depth": 2},
                {"idx": 1, "role": "button",   "name": "submit",     "value": "",       "focused": False, "depth": 2},
            ],
            "click",  # open the combobox
        ),
        (
            "check the bacon topping checkbox",
            [
                {"idx": 0, "role": "checkbox", "name": "bacon",   "value": "",   "focused": False, "depth": 3},
                {"idx": 1, "role": "checkbox", "name": "cheese",  "value": "on", "focused": False, "depth": 3},
                {"idx": 2, "role": "button",   "name": "order",   "value": "",   "focused": False, "depth": 2},
            ],
            "click",  # check bacon
        ),
        (
            "register a new account with email newuser@test.com",
            [
                {"idx": 0, "role": "textbox", "name": "first name", "value": "", "focused": False, "depth": 2},
                {"idx": 1, "role": "textbox", "name": "email",      "value": "", "focused": False, "depth": 2},
                {"idx": 2, "role": "button",  "name": "register",   "value": "", "focused": False, "depth": 2},
            ],
            "type",  # fill first name
        ),
        (
            "log out from the account",
            [
                {"idx": 0, "role": "button", "name": "profile",  "value": "", "focused": False, "depth": 1},
                {"idx": 1, "role": "link",   "name": "sign out", "value": "", "focused": False, "depth": 3},
            ],
            "click",  # click sign out
        ),
    ]

    print("\n" + "="*60)
    print("  FormExpert — Quick Test")
    print("="*60)

    all_pass = True
    for goal, nodes, expected in test_cases:
        action = expert.decide({"nodes": nodes, "edges": []}, goal, "https://example.com")
        ok = action is not None and action["type"] == expected
        status = "✓" if ok else "✗"
        if not ok:
            all_pass = False
        print(f"  {status}  [{expected:<8}] {goal[:55]}")
        if not ok:
            print(f"      Got: {action}")

    print()
    if all_pass:
        print("  All tests passed ✓")
    else:
        print("  Some tests failed ✗")
    print("="*60 + "\n")
