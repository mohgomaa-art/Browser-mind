"""Field Ontology tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from browsermind_core.ontology import field_registry as fr_module
from browsermind_core.ontology.field_ontology import Field, FieldKind, Optionality
from browsermind_core.ontology.field_registry import (
    FieldRegistry,
    _normalize,
    get_registry,
    _reset_registry_for_tests,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def empty_registry(tmp_path) -> FieldRegistry:
    """Fresh registry whose user-path is in tmp_path and never falls back to seed."""
    path = tmp_path / "field_registry.json"
    path.write_text(json.dumps({"version": "1", "fields": []}), encoding="utf-8")
    return FieldRegistry(registry_path=path)


@pytest.fixture
def seed_registry(monkeypatch, tmp_path) -> FieldRegistry:
    """Registry that reads from the shipped seed (no user file yet)."""
    monkeypatch.setattr(fr_module, "_USER_PATH", tmp_path / "no_user_file.json")
    return FieldRegistry(registry_path=tmp_path / "no_user_file.json")


@pytest.fixture(autouse=True)
def _reset_singleton():
    _reset_registry_for_tests()
    yield
    _reset_registry_for_tests()


# ── Field data model ──────────────────────────────────────────────────────────


def test_field_all_labels_returns_canonical_plus_aliases():
    f = Field(
        id="country", label="Country", kind=FieldKind.single_select,
        optionality=Optionality.required,
        aliases=["Country/Region", "Nation"],
    )
    assert f.all_labels() == ["Country", "Country/Region", "Nation"]


def test_field_default_optionality_is_required():
    f = Field(id="x", label="X", kind=FieldKind.text)
    assert f.optionality == Optionality.required


# ── Normalization ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Country", "country"),
        ("  Country  ", "country"),
        ("Country *", "country"),
        ("Country:", "country"),
        ("Country (optional)", "country"),
        ("Country (Optional)", "country"),
        ("COUNTRY/REGION", "country/region"),
    ],
)
def test_normalize_strips_decoration(raw, expected):
    assert _normalize(raw) == expected


# ── Seed integrity ────────────────────────────────────────────────────────────


def test_seed_loads_with_at_least_twenty_fields(seed_registry):
    assert len(seed_registry.list_fields()) >= 20


@pytest.mark.parametrize(
    "label,expected_id,expected_opt",
    [
        ("Country / Region", "country", "required"),
        ("Compensation Expectations", "salary_expectation", "optional"),
        ("CV", "resume", "required"),
        ("Apply Now", "submit_application", "structural"),
        ("Veteran", "veteran_status", "optional"),
        ("Gender", "gender", "optional"),
        ("LinkedIn Profile", "linkedin_url", "optional"),
        ("Continue", "next_step", "structural"),
    ],
)
def test_seed_resolves_canonical_lookups(seed_registry, label, expected_id, expected_opt):
    f = seed_registry.resolve(label)
    assert f is not None, f"{label!r} did not resolve"
    assert f.id == expected_id
    assert f.optionality.value == expected_opt


def test_unknown_label_returns_none(seed_registry):
    assert seed_registry.resolve("Some Random Greenhouse Asylum Question") is None


def test_empty_label_returns_none(seed_registry):
    assert seed_registry.resolve("") is None
    assert seed_registry.resolve(None) is None
    assert seed_registry.resolve("   ") is None


# ── Fuzzy match ───────────────────────────────────────────────────────────────


def test_fuzzy_match_within_distance_two_on_long_label(seed_registry):
    # "compansation expectations" - 1 edit from "compensation expectations"
    f = seed_registry.resolve("Compansation Expectations")
    assert f is not None
    assert f.id == "salary_expectation"


def test_fuzzy_match_does_not_fire_on_short_labels(seed_registry):
    # "City" (4 chars) should not fuzzy-match anything; only exact wins.
    f = seed_registry.resolve("Caty")
    assert f is None


# ── Register / alias uniqueness ───────────────────────────────────────────────


def test_register_persists_across_reload(empty_registry, tmp_path):
    empty_registry.register(Field(
        id="custom_x", label="Custom X", kind=FieldKind.text,
        aliases=["Custom Field X"],
    ))
    reopened = FieldRegistry(registry_path=tmp_path / "field_registry.json")
    f = reopened.resolve("Custom Field X")
    assert f is not None and f.id == "custom_x"


def test_register_rejects_alias_collision_across_fields(empty_registry):
    empty_registry.register(Field(id="a", label="A Field", kind=FieldKind.text, aliases=["Shared"]))
    with pytest.raises(ValueError, match="already belongs to"):
        empty_registry.register(Field(id="b", label="B Field", kind=FieldKind.text, aliases=["Shared"]))


def test_register_can_replace_existing_field_without_collision(empty_registry):
    empty_registry.register(Field(id="a", label="A", kind=FieldKind.text, aliases=["X"]))
    empty_registry.register(Field(id="a", label="A", kind=FieldKind.text, aliases=["X", "Y"]))
    assert empty_registry.resolve("Y").id == "a"


def test_add_alias_extends_existing_field(empty_registry):
    empty_registry.register(Field(id="email", label="Email", kind=FieldKind.email))
    empty_registry.add_alias("email", "Work Email")
    assert empty_registry.resolve("Work Email").id == "email"


def test_add_alias_to_unknown_field_raises(empty_registry):
    with pytest.raises(KeyError):
        empty_registry.add_alias("does_not_exist", "Whatever")


def test_add_alias_collision_across_fields_raises(empty_registry):
    empty_registry.register(Field(id="a", label="A", kind=FieldKind.text, aliases=["Conflict"]))
    empty_registry.register(Field(id="b", label="B", kind=FieldKind.text))
    with pytest.raises(ValueError, match="already belongs"):
        empty_registry.add_alias("b", "Conflict")


def test_add_alias_idempotent(empty_registry):
    empty_registry.register(Field(id="a", label="A", kind=FieldKind.text, aliases=["X"]))
    empty_registry.add_alias("a", "X")
    assert empty_registry.get("a").aliases.count("X") == 1


# ── Singleton ─────────────────────────────────────────────────────────────────


def test_singleton_is_idempotent_within_a_process():
    a = get_registry()
    b = get_registry()
    assert a is b


def test_reset_for_tests_drops_the_singleton():
    a = get_registry()
    _reset_registry_for_tests()
    b = get_registry()
    assert a is not b
