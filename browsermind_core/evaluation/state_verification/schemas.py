from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field
import yaml
import os

class StateRule(BaseModel):
    """A rule defining a specific condition to check on the page."""
    type: Literal[
        "url_equals",
        "url_contains",
        "element_exists",
        "element_visible",
        "text_present",
        "attribute_equals",
        "count_equals"
    ]
    value: Optional[Any] = None
    selector: Optional[str] = None
    attribute: Optional[str] = None
    count: Optional[int] = None

class VerificationReport(BaseModel):
    """The result of evaluating rules against evidence."""
    workflow: str
    state_match: bool
    rule_results: List[Dict[str, Any]]
    verifier_result: bool
    human_result: Optional[bool] = None  # For manual adjudication
    timestamp: str

class StateVerifierConfig(BaseModel):
    """A complete verification config loaded from YAML."""
    workflow: str
    success: List[StateRule]

def load_verification_config(yaml_path: str) -> StateVerifierConfig:
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return StateVerifierConfig(**data)
