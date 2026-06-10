"""BrowserMind Field Ontology.

A Field is a semantic workflow object — Country, Resume, Phone — not a DOM
element. The FieldRegistry maps observable label strings to these objects so
the resolver can reason about what a form field IS rather than what its DOM
attributes happen to say.

See DOCS/FIELD_ONTOLOGY_SPEC.md for the full design rationale.
"""
from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field as PydanticField


class FieldKind(str, Enum):
    text          = "text"
    email         = "email"
    phone         = "phone"
    url           = "url"
    number        = "number"
    textarea      = "textarea"
    single_select = "single_select"
    multi_select  = "multi_select"
    date          = "date"
    checkbox      = "checkbox"
    radio         = "radio"
    file_upload   = "file_upload"
    address       = "address"
    submit        = "submit"
    custom        = "custom"


class Optionality(str, Enum):
    required   = "required"
    optional   = "optional"
    structural = "structural"


class Field(BaseModel):
    """A semantic workflow object.

    Identity is the ``id``. Everything else (label, aliases, kind, optionality)
    can be edited without breaking templates compiled against an earlier
    version of the registry.
    """

    id:              str
    label:           str
    kind:            FieldKind
    optionality:     Optionality = Optionality.required
    aliases:         List[str]   = PydanticField(default_factory=list)
    container_hints: List[str]   = PydanticField(default_factory=list)
    aria_roles:      List[str]   = PydanticField(default_factory=list)
    note:            str         = ""

    def all_labels(self) -> List[str]:
        """All strings that should map to this Field (canonical + aliases)."""
        return [self.label] + list(self.aliases)
