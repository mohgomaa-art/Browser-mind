"""
SemanticFact — P4C: Structured Semantic Memory

Structured facts about an environment. NOT free text.

CRITICAL DESIGN PRINCIPLE:
  fact="github uses search modal"   <- BAD: unqueryable, ambiguous
  SemanticFact(concept="search_interface", value="modal")  <- GOOD: queryable

  concept/value pairs are machine-readable. The system can query:
    "what is the search_interface of github?"
  and get a deterministic, typed answer.

Known concept vocabulary (extend as needed):
  search_interface    : "inline" | "modal" | "sidebar"
  search_input_type   : "input" | "textarea" | "contenteditable"
  submit_method       : "enter" | "button_click" | "form_submit"
  auth_flow           : "single_page" | "multi_step" | "redirect"
  result_layout       : "card_list" | "link_list" | "table"

Scope: Environment-global.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional
import json


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SemanticFact:
    """
    A structured, queryable fact about an environment.

    concept: the semantic dimension being described (e.g. "search_input_type")
    value:   the observed value for that dimension (e.g. "textarea")
    confidence: 0.0–1.0, updated on repeated observation

    A fact is identified by (environment_key, concept). Multiple observations
    of the same concept update confidence rather than creating new records.
    """
    environment_key: str    # e.g. "brave_search"
    concept: str            # e.g. "search_input_type"
    value: str              # e.g. "textarea"
    confidence: float = 1.0
    observation_count: int = 1
    evidence: str = ""      # what triggered this fact (e.g. "selector: textarea[name='q']")
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def reinforce(self, new_value: str, evidence: str = "") -> None:
        """Called when the same concept is observed again."""
        if new_value == self.value:
            # Consistent observation — boost confidence
            self.confidence = min(1.0, self.confidence + 0.05)
            self.observation_count += 1
        else:
            # Conflicting observation — decay confidence, keep majority value
            self.confidence = max(0.1, self.confidence - 0.15)
        if evidence:
            self.evidence = evidence
        self.updated_at = _utc_now()

    def to_json_line(self) -> str:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        d["updated_at"] = self.updated_at.isoformat()
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "SemanticFact":
        d = dict(d)
        for key in ("created_at", "updated_at"):
            if isinstance(d.get(key), str):
                d[key] = datetime.fromisoformat(d[key])
        return cls(**d)


# ---------------------------------------------------------------------------
# Known concept vocabulary — used by MemoryWriter to produce structured facts
# from raw Affordance/Capability discovery signals.
# ---------------------------------------------------------------------------

CONCEPT_SEARCH_INPUT_TYPE = "search_input_type"    # "input" | "textarea"
CONCEPT_SEARCH_INTERFACE  = "search_interface"      # "inline" | "modal" | "sidebar"
CONCEPT_SUBMIT_METHOD     = "submit_method"         # "enter" | "button_click" | "form_submit"
CONCEPT_AUTH_FLOW         = "auth_flow"             # "single_page" | "multi_step" | "redirect"
CONCEPT_RESULT_LAYOUT     = "result_layout"         # "card_list" | "link_list" | "table"
