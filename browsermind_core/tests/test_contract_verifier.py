"""Tests for ContractVerifier (runtime)."""
import asyncio
from pathlib import Path
import tempfile

import pytest

from browsermind_core.runtime.contract_verifier import (
    ContractVerifier,
    SuccessCondition,
    TaskSuccessContract,
    register_contract,
    lookup_contract,
)


class _FakeLocator:
    def __init__(self, visible: bool, text: str = ""):
        self._visible = visible
        self._text = text
        self.first = self

    async def is_visible(self, timeout=None):
        return self._visible

    async def inner_text(self):
        return self._text


class _FakePage:
    def __init__(self, url: str, locators: dict):
        self.url = url
        self._locators = locators

    def locator(self, selector: str):
        return self._locators.get(selector, _FakeLocator(False))


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_url_contains_passes():
    page = _FakePage("https://x.test/dashboard?ok=1", {})
    contract = TaskSuccessContract(
        task_id="T_url", description="", rationale="",
        conditions=[SuccessCondition(kind="url_contains", target="/dashboard", label="L")],
    )
    result = _run(ContractVerifier().verify(page, contract))
    assert result["goal_completed"] is True
    assert result["validator_result"] is True


def test_url_contains_fails():
    page = _FakePage("https://x.test/login", {})
    contract = TaskSuccessContract(
        task_id="T_url2", description="", rationale="",
        conditions=[SuccessCondition(kind="url_contains", target="/dashboard", label="L")],
    )
    result = _run(ContractVerifier().verify(page, contract))
    assert result["goal_completed"] is False


def test_element_visible_passes():
    page = _FakePage("https://x.test/", {"#welcome": _FakeLocator(True)})
    contract = TaskSuccessContract(
        task_id="T_el", description="", rationale="",
        conditions=[SuccessCondition(kind="element_visible", target="#welcome", label="L")],
    )
    result = _run(ContractVerifier().verify(page, contract))
    assert result["goal_completed"] is True


def test_element_text_contains_case_insensitive():
    page = _FakePage("https://x.test/", {"#status": _FakeLocator(True, text="Application RECEIVED")})
    contract = TaskSuccessContract(
        task_id="T_text", description="", rationale="",
        conditions=[SuccessCondition(
            kind="element_text_contains", target="#status",
            value="application received", label="L",
        )],
    )
    result = _run(ContractVerifier().verify(page, contract))
    assert result["goal_completed"] is True


def test_no_contract_returns_false_with_error():
    page = _FakePage("https://x.test/", {})
    result = _run(ContractVerifier().verify(page, None, task_id="UNKNOWN_T"))
    assert result["goal_completed"] is False
    assert "no contract" in result["contract_evidence"]["error"].lower()


def test_register_then_lookup():
    contract = TaskSuccessContract(
        task_id="T_runtime_only", description="", rationale="",
        conditions=[SuccessCondition(kind="url_contains", target="/x", label="L")],
    )
    register_contract(contract)
    found = lookup_contract("T_runtime_only")
    assert found is not None
    assert found.task_id == "T_runtime_only"


def test_yaml_contract_roundtrip(tmp_path: Path):
    pytest.importorskip("yaml")
    import yaml
    contracts_dir = tmp_path / "browsermind_core" / "runtime" / "contracts"
    contracts_dir.mkdir(parents=True)
    (contracts_dir / "saucedemo_login.yaml").write_text(yaml.dump({
        "task_id": "saucedemo_login",
        "description": "saucedemo login",
        "rationale": "",
        "conditions": [
            {"kind": "url_contains", "target": "/inventory", "label": "Inventory shown"},
        ],
    }), encoding="utf-8")
    found = lookup_contract("saucedemo_login", root=tmp_path)
    assert found is not None
    assert found.task_id == "saucedemo_login"
    assert found.conditions[0].target == "/inventory"


def test_partial_satisfaction_fails():
    page = _FakePage("https://x.test/dashboard", {"#missing": _FakeLocator(False)})
    contract = TaskSuccessContract(
        task_id="T_partial", description="", rationale="",
        conditions=[
            SuccessCondition(kind="url_contains", target="/dashboard", label="A"),
            SuccessCondition(kind="element_visible", target="#missing", label="B"),
        ],
    )
    result = _run(ContractVerifier().verify(page, contract))
    assert result["goal_completed"] is False
    conds = result["contract_evidence"]["conditions"]
    assert conds["A"]["satisfied"] is True
    assert conds["B"]["satisfied"] is False


def test_no_conditions_fails_safe():
    page = _FakePage("https://x.test/", {})
    contract = TaskSuccessContract(
        task_id="T_empty", description="", rationale="", conditions=[],
    )
    result = _run(ContractVerifier().verify(page, contract))
    # An empty contract is not "completed" — caller must declare success conditions.
    assert result["goal_completed"] is False
