"""P5A.0 — Primitive Canonicalization with Collapse Levels.

Maps raw UI interactions into Intent Primitives at multiple abstraction levels:
  Level 0 (fine):     OPEN_SEARCH, SUBMIT_QUERY, UPLOAD_FILE, ACCEPT_CONSENT, ...
  Level 1 (merged):   LOCATE, SELECT, AUTHENTICATE, INTERACT_OBJECT, TRANSACT, ...
  Level 2 (abstract): NAVIGATE, ACT
"""
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── Collapse Maps ─────────────────────────────────────────────────────────────

# Level-0 → Level-1
_COLLAPSE_L1: Dict[str, str] = {
    # Discovery / Search
    "OPEN_SEARCH":      "LOCATE",
    "SUBMIT_QUERY":     "LOCATE",
    # Auth
    "SIGN_IN":          "AUTHENTICATE",
    "AUTHENTICATE":     "AUTHENTICATE",
    # Selection / Navigation
    "OPEN_OBJECT":      "SELECT",
    "OPEN_ISSUES":      "SELECT",
    "OPEN_MENU":        "SELECT",
    "SELECT_OPTION":    "SELECT",
    "NEXT_PAGE":        "SELECT",
    "PREV_PAGE":        "SELECT",
    "SORT_FILTER":      "SELECT",
    # Interaction
    "TOGGLE_STAR":      "INTERACT_OBJECT",
    "CREATE_ISSUE":     "INTERACT_OBJECT",
    "LIKE_CONTENT":     "INTERACT_OBJECT",
    "SHARE_CONTENT":    "INTERACT_OBJECT",
    "FOLLOW_USER":      "INTERACT_OBJECT",
    "BOOKMARK":         "INTERACT_OBJECT",
    "PLAY_MEDIA":       "INTERACT_OBJECT",
    "PAUSE_MEDIA":      "INTERACT_OBJECT",
    "MUTE_MEDIA":       "INTERACT_OBJECT",
    # Content / CRUD
    "SUBMIT_FORM":      "TRANSACT",
    "EDIT_ITEM":        "TRANSACT",
    "DELETE_ITEM":      "TRANSACT",
    "SAVE_ITEM":        "TRANSACT",
    "CLEAR_FORM":       "TRANSACT",
    "UPLOAD_FILE":      "TRANSACT",
    "DOWNLOAD_FILE":    "TRANSACT",
    # Commerce
    "ADD_TO_CART":      "TRANSACT",
    "CHECKOUT":         "TRANSACT",
    "APPLY_COUPON":     "TRANSACT",
    # Consent / Dialog
    "ACCEPT_CONSENT":   "CONSENT",
    "DECLINE_CONSENT":  "CONSENT",
    "CLOSE_DIALOG":     "CONSENT",
    "CONFIRM_ACTION":   "CONSENT",
}

# Level-1 → Level-2
_COLLAPSE_L2: Dict[str, str] = {
    "LOCATE":           "NAVIGATE",
    "AUTHENTICATE":     "NAVIGATE",
    "SELECT":           "ACT",
    "INTERACT_OBJECT":  "ACT",
    "TRANSACT":         "ACT",
    "CONSENT":          "ACT",
}

# All named vocabulary at Level-0 — used for fallback detection
_KNOWN_L0 = frozenset(_COLLAPSE_L1.keys())

# Runtime vocabulary extensions loaded from ~/.browsermind/vocab_extensions.json
# Each entry: (l0_name, l1_name, [name_fragment_patterns])
# Populated by load_vocab_extensions(); empty until explicitly called.
_RUNTIME_PATTERNS: List[Tuple[str, str, List[str]]] = []
_RUNTIME_L0: set = set()  # l0_names added via runtime extensions


def load_vocab_extensions(path=None) -> int:
    """Load confirmed vocab extensions from vocab_extensions.json.

    Called once at startup (or after a confirmation in vocab_review.py).
    Returns the number of extension entries loaded.

    Extensions are stored as:
      [{"l0_name": "WISHLIST_ITEM", "l1_name": "INTERACT_OBJECT",
        "patterns": ["add to wishlist", "save for later"], ...}, ...]
    """
    import json as _json
    from pathlib import Path as _Path

    global _RUNTIME_PATTERNS, _RUNTIME_L0

    if path is None:
        path = _Path.home() / ".browsermind" / "vocab_extensions.json"

    path = _Path(path)
    if not path.exists():
        return 0

    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0

    new_patterns: List[Tuple[str, str, List[str]]] = []
    new_l0: set = set()
    for entry in data:
        l0   = entry.get("l0_name", "")
        l1   = entry.get("l1_name", "INTERACT_OBJECT")
        pats = [str(p).lower() for p in entry.get("patterns", []) if p]
        if l0 and pats:
            new_patterns.append((l0, l1, pats))
            new_l0.add(l0)

    _RUNTIME_PATTERNS = new_patterns
    _RUNTIME_L0 = new_l0
    return len(new_patterns)


class PrimitiveNormalizer:
    """Maps a raw UI interaction to a canonical Intent Primitive.

    Args:
        collapse_level: 0 = fine-grained (~30 patterns), 1 = merged (~7 groups), 2 = abstract (2)
        logger: optional callable(record: dict) invoked after each normalize() call.
                Each record contains action_type, target_role, target_name, result,
                is_fallback. Enables fallback-rate measurement for discovery validation.
    """

    def __init__(
        self,
        collapse_level: int = 0,
        logger: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.collapse_level = collapse_level
        self._logger = logger

    def normalize(self, action_type: str, target_role: str, target_name: str) -> str:
        raw = _raw_intent(action_type, target_role, target_name)
        intent = raw
        if self.collapse_level >= 1:
            intent = _COLLAPSE_L1.get(intent, intent)
        if self.collapse_level >= 2:
            intent = _COLLAPSE_L2.get(intent, intent)

        if self._logger is not None:
            is_fallback = raw not in _KNOWN_L0 and raw not in _RUNTIME_L0
            try:
                self._logger({
                    "action_type": action_type,
                    "target_role": target_role,
                    "target_name": target_name,
                    "result": intent,
                    "is_fallback": is_fallback,
                })
            except Exception:
                pass

        return intent


# ── Core intent detection ─────────────────────────────────────────────────────

def _raw_intent(action_type: str, target_role: str, target_name: str) -> str:
    """Level-0: fine-grained intent detection.

    Order matters — more specific patterns check first. Falls back to
    the generic {ACTION_TYPE}_{ROLE}_{name} token for unrecognised interactions.
    """
    name_lower = (target_name or "").lower()
    role_lower = (target_role or "").lower()
    act_lower  = (action_type or "").lower()

    # ── 1. File operations ────────────────────────────────────────────────────
    if any(kw in name_lower for kw in ("upload", "attach", "choose file", "browse files",
                                        "drag and drop", "drop files", "select file")):
        return "UPLOAD_FILE"
    if role_lower in ("file", "input") and act_lower == "click":
        return "UPLOAD_FILE"
    if any(kw in name_lower for kw in ("download", "export", "save as", "get file",
                                        "save file", "download file")):
        return "DOWNLOAD_FILE"

    # ── 2. Consent / cookie banners ───────────────────────────────────────────
    if any(kw in name_lower for kw in ("accept all", "accept cookies", "allow all",
                                        "i agree", "agree to", "allow cookies")):
        return "ACCEPT_CONSENT"
    if any(kw in name_lower for kw in ("decline all", "reject all", "refuse cookies",
                                        "deny cookies", "manage preferences", "only necessary")):
        return "DECLINE_CONSENT"

    # ── 3. Dialog / modal interactions ───────────────────────────────────────
    if (any(kw in name_lower for kw in ("confirm", "ok", "yes", "proceed", "continue",
                                         "got it", "understood"))
            and role_lower in ("button", "dialog", "alertdialog")):
        return "CONFIRM_ACTION"
    if (any(kw in name_lower for kw in ("close", "dismiss", "cancel", "×", "✕", "✗"))
            or role_lower in ("dialog", "alertdialog")):
        if act_lower == "click":
            return "CLOSE_DIALOG"

    # ── 4. Commerce ───────────────────────────────────────────────────────────
    if any(kw in name_lower for kw in ("add to cart", "add to bag", "add to basket",
                                        "add to trolley")):
        return "ADD_TO_CART"
    if any(kw in name_lower for kw in ("checkout", "proceed to checkout", "buy now",
                                        "place order", "complete purchase")):
        return "CHECKOUT"
    if any(kw in name_lower for kw in ("apply coupon", "promo code", "discount code",
                                        "apply code", "enter code")):
        return "APPLY_COUPON"

    # ── 5. Social / community ────────────────────────────────────────────────
    if any(kw in name_lower for kw in ("like", "upvote", "heart", "thumbs up", "clap",
                                        "react", "love", "+1")):
        return "LIKE_CONTENT"
    if any(kw in name_lower for kw in ("share", "repost", "retweet", "forward",
                                        "send to", "copy link")):
        return "SHARE_CONTENT"
    if any(kw in name_lower for kw in ("follow", "subscribe", "connect", "add friend",
                                        "add connection")):
        return "FOLLOW_USER"
    if any(kw in name_lower for kw in ("bookmark", "save for later", "add to list",
                                        "wishlist", "favourite", "favorite")):
        return "BOOKMARK"

    # ── 6. Media ──────────────────────────────────────────────────────────────
    if any(kw in name_lower for kw in ("mute", "unmute", "volume")):
        return "MUTE_MEDIA"
    if any(kw in name_lower for kw in ("pause", "stop playing")):
        return "PAUSE_MEDIA"
    if any(kw in name_lower for kw in ("play", "watch now", "start video", "watch video",
                                        "stream")):
        return "PLAY_MEDIA"

    # ── 7. Pagination / filtering ─────────────────────────────────────────────
    if any(kw in name_lower for kw in ("load more", "show more", "next page", "page forward",
                                        "older posts", "more results")):
        return "NEXT_PAGE"
    if any(kw in name_lower for kw in ("previous page", "page back", "older", "go back",
                                        "prev page")):
        return "PREV_PAGE"
    if any(kw in name_lower for kw in ("filter", "sort by", "order by", "refine",
                                        "narrow results", "filters")):
        return "SORT_FILTER"

    # ── 8. CRUD actions ───────────────────────────────────────────────────────
    if any(kw in name_lower for kw in ("delete", "remove", "trash", "discard", "destroy")):
        return "DELETE_ITEM"
    if (any(kw in name_lower for kw in ("edit", "modify", "pencil", "change", "rename"))
            and not any(x in name_lower for x in ("password", "email", "username"))):
        return "EDIT_ITEM"
    if (any(kw in name_lower for kw in ("save changes", "save draft", "update settings",
                                         "save settings"))
            or (act_lower in ("submit", "click")
                and any(kw in name_lower for kw in ("save",))
                and not any(x in name_lower for x in ("password", "email")))):
        return "SAVE_ITEM"
    if any(kw in name_lower for kw in ("reset form", "clear form", "start over", "clear all")):
        return "CLEAR_FORM"

    # ── 9. Search ────────────────────────────────────────────────────────────
    if act_lower == "click" and any(x in name_lower for x in ["search", "find", "jump to"]):
        return "OPEN_SEARCH"
    if act_lower in ("fill", "keydown", "submit"):
        if role_lower in ("textbox", "searchbox", "combobox", "dialog"):
            if not any(x in name_lower for x in ["password", "username", "email"]):
                return "SUBMIT_QUERY"

    # ── 10. Authentication ────────────────────────────────────────────────────
    if any(x in name_lower for x in ("sign in", "log in", "login", "sign-in", "log-in")):
        return "SIGN_IN"
    if any(x in name_lower for x in ("password", "username", "email")):
        return "AUTHENTICATE"

    # ── 11. Form submission ───────────────────────────────────────────────────
    if act_lower == "submit" or (act_lower == "click" and role_lower == "submit"):
        return "SUBMIT_FORM"

    # ── 12. Selection / dropdowns ─────────────────────────────────────────────
    if role_lower in ("option", "listbox") and act_lower == "click":
        return "SELECT_OPTION"
    if role_lower == "combobox" and act_lower in ("click", "select"):
        return "SELECT_OPTION"

    # ── 13. Runtime extensions (confirmed VocabProposals — checked before catch-alls) ──
    for l0_name, _l1_name, patterns in _RUNTIME_PATTERNS:
        if any(p in name_lower for p in patterns):
            return l0_name

    # ── 14. Object / UI interactions ──────────────────────────────────────────
    if act_lower == "click":
        ui_verbs = ["create", "new", "settings", "profile", "menu",
                    "issues", "pull requests", "code", "star", "unstar"]
        is_ui = any(w in name_lower for w in ui_verbs)

        if "star" in name_lower:
            return "TOGGLE_STAR"
        if "issues" in name_lower:
            return "OPEN_ISSUES"
        if "new issue" in name_lower or "create issue" in name_lower:
            return "CREATE_ISSUE"
        if not is_ui:
            return "OPEN_OBJECT"

    # ── 14. Navigation / menus ────────────────────────────────────────────────
    if act_lower == "click" and role_lower in ("banner", "navigation", "menu", "menuitem"):
        return "OPEN_MENU"

    # ── Fallback: per-element token (is_fallback=True for discovery instrumentation) ──
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", name_lower).strip()
    cleaned = cleaned[:30] + "..." if len(cleaned) > 30 else cleaned
    return f"{action_type.upper()}_{target_role.upper()}_{cleaned.replace(' ', '_')}"


# ── Measurement utility ───────────────────────────────────────────────────────

def measure_fallback_rate(
    samples: List[Tuple[str, str, str]],
) -> Dict[str, Any]:
    """Measure vocabulary coverage against a list of (action_type, role, name) tuples.

    Returns:
        total         — number of samples
        fallback_count — samples that hit the generic fallback code path
        fallback_rate  — fallback_count / total (0.0–1.0)
        fallback_examples — up to 10 fallback samples for inspection
        known_intents — set of recognised Level-0 intent strings seen
    """
    records: List[Dict[str, Any]] = []
    norm = PrimitiveNormalizer(collapse_level=0, logger=records.append)
    for action_type, role, name in samples:
        norm.normalize(action_type, role, name)

    total          = len(records)
    fallback_count = sum(1 for r in records if r["is_fallback"])
    fallback_rate  = fallback_count / max(total, 1)
    fallback_ex    = [r for r in records if r["is_fallback"]][:10]
    known_intents  = {r["result"] for r in records if not r["is_fallback"]}

    return {
        "total":             total,
        "fallback_count":    fallback_count,
        "fallback_rate":     round(fallback_rate, 4),
        "fallback_examples": fallback_ex,
        "known_intents":     sorted(known_intents),
    }
