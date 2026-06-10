"""Tests for CapabilityContract and CapabilityVerifier.

Verifies:
  - CapabilityContract schema and registration
  - lookup_capability_contract() returns None for unknown hashes
  - lookup_capability_contract() returns registered contracts
  - CapabilityVerifier evaluates url_contains conditions correctly
  - CapabilityVerifier returns False when conditions fail
  - CapabilityVerifier handles page=None gracefully
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── CapabilityContract schema ─────────────────────────────────────────────────

def test_capability_contract_fields():
    from browsermind_core.learning.capability_contract import CapabilityContract, CapabilityCondition
    c = CapabilityContract(
        invariant_hash="abcd1234abcd1234",
        description="After auth, dashboard visible",
        conditions=[
            CapabilityCondition(kind="url_contains", target="/dashboard", label="dashboard_url"),
        ],
    )
    assert c.invariant_hash == "abcd1234abcd1234"
    assert len(c.conditions) == 1
    assert c.conditions[0].kind == "url_contains"


def test_capability_condition_default_value():
    from browsermind_core.learning.capability_contract import CapabilityCondition
    cond = CapabilityCondition(kind="url_contains", target="/foo")
    assert cond.value == ""
    assert cond.label == ""


# ── lookup_capability_contract ────────────────────────────────────────────────

def test_lookup_unknown_hash_returns_none():
    from browsermind_core.learning.capability_contract import lookup_capability_contract
    result = lookup_capability_contract("0000000000000000")
    assert result is None


def test_register_and_lookup():
    from browsermind_core.learning.capability_contract import (
        CapabilityContract,
        CapabilityCondition,
        register_capability_contract,
        lookup_capability_contract,
    )
    TEST_HASH = "testtest12345678"
    contract = CapabilityContract(
        invariant_hash=TEST_HASH,
        description="test",
        conditions=[CapabilityCondition(kind="url_contains", target="/test")],
    )
    register_capability_contract(contract)
    result = lookup_capability_contract(TEST_HASH)
    assert result is not None
    assert result.invariant_hash == TEST_HASH


def test_lookup_empty_hash_returns_none():
    from browsermind_core.learning.capability_contract import lookup_capability_contract
    assert lookup_capability_contract("") is None


# ── CapabilityVerifier ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verifier_url_contains_satisfied():
    from browsermind_core.learning.capability_contract import (
        CapabilityContract,
        CapabilityCondition,
        CapabilityVerifier,
    )
    page = MagicMock()
    page.url = "https://example.com/dashboard"

    contract = CapabilityContract(
        invariant_hash="abcd1234abcd1234",
        conditions=[CapabilityCondition(kind="url_contains", target="/dashboard")],
    )
    result = await CapabilityVerifier().verify(page, contract)
    assert result["transition_verified"] is True
    assert result["capability_hash"] == "abcd1234abcd1234"


@pytest.mark.asyncio
async def test_verifier_url_contains_not_satisfied():
    from browsermind_core.learning.capability_contract import (
        CapabilityContract,
        CapabilityCondition,
        CapabilityVerifier,
    )
    page = MagicMock()
    page.url = "https://example.com/login"

    contract = CapabilityContract(
        invariant_hash="abcd1234abcd1234",
        conditions=[CapabilityCondition(kind="url_contains", target="/dashboard")],
    )
    result = await CapabilityVerifier().verify(page, contract)
    assert result["transition_verified"] is False


@pytest.mark.asyncio
async def test_verifier_no_conditions_returns_false():
    from browsermind_core.learning.capability_contract import (
        CapabilityContract,
        CapabilityVerifier,
    )
    page = MagicMock()
    page.url = "https://example.com/dashboard"
    contract = CapabilityContract(invariant_hash="abcd1234abcd1234", conditions=[])
    result = await CapabilityVerifier().verify(page, contract)
    assert result["transition_verified"] is False


@pytest.mark.asyncio
async def test_verifier_page_none_returns_false():
    from browsermind_core.learning.capability_contract import (
        CapabilityContract,
        CapabilityCondition,
        CapabilityVerifier,
    )
    contract = CapabilityContract(
        invariant_hash="abcd1234abcd1234",
        conditions=[CapabilityCondition(kind="url_contains", target="/dashboard")],
    )
    result = await CapabilityVerifier().verify(None, contract)
    assert result["transition_verified"] is False


@pytest.mark.asyncio
async def test_verifier_element_visible_condition():
    from browsermind_core.learning.capability_contract import (
        CapabilityContract,
        CapabilityCondition,
        CapabilityVerifier,
    )
    page = MagicMock()
    page.url = "https://example.com/"
    mock_locator = MagicMock()
    mock_locator.first = MagicMock()
    mock_locator.first.is_visible = AsyncMock(return_value=True)
    page.locator = MagicMock(return_value=mock_locator)

    contract = CapabilityContract(
        invariant_hash="abcd1234abcd1234",
        conditions=[
            CapabilityCondition(
                kind="element_visible",
                target="[data-testid='user-avatar']",
                label="avatar_present",
            )
        ],
    )
    result = await CapabilityVerifier().verify(page, contract)
    assert result["transition_verified"] is True


@pytest.mark.asyncio
async def test_verifier_all_conditions_must_pass():
    from browsermind_core.learning.capability_contract import (
        CapabilityContract,
        CapabilityCondition,
        CapabilityVerifier,
    )
    page = MagicMock()
    page.url = "https://example.com/dashboard"

    mock_locator = MagicMock()
    mock_locator.first = MagicMock()
    mock_locator.first.is_visible = AsyncMock(return_value=False)  # second condition fails
    page.locator = MagicMock(return_value=mock_locator)

    contract = CapabilityContract(
        invariant_hash="abcd1234abcd1234",
        conditions=[
            CapabilityCondition(kind="url_contains", target="/dashboard"),
            CapabilityCondition(kind="element_visible", target=".user-menu"),
        ],
    )
    result = await CapabilityVerifier().verify(page, contract)
    assert result["transition_verified"] is False


# ── Source-level: replay_engine wires capability verification ─────────────────

def test_replay_engine_calls_verify_capabilities():
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1] / "runtime" / "replay_engine.py"
    ).read_text(encoding="utf-8")
    assert "_verify_capabilities_in_execution" in src
    assert "CapabilityVerifier" in src
    assert "lookup_capability_contract" in src


def test_replay_engine_builds_completed_intent_set():
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1] / "runtime" / "replay_engine.py"
    ).read_text(encoding="utf-8")
    assert "_completed_intents" in src
    assert "PrimitiveNormalizer" in src


def test_replay_engine_writes_capability_record_in_compile():
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1] / "runtime" / "replay_engine.py"
    ).read_text(encoding="utf-8")
    assert "CapabilityRecord" in src
    assert "update_capability" in src
    assert "invariant_hash" in src
    assert "CapLoop/Compile] CapabilityRecord written" in src
