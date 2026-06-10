"""Tests for browsermind_core.training.episode_extractor."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from browsermind_core.ledger.outcome_ledger import OutcomeLedger, OutcomeRecord
from browsermind_core.training.episode_extractor import (
    extract_bc_episodes,
    summarize,
    write_jsonl,
)


def _step_record(*, site: str, success: bool, action: str = "click",
                 step_seq: int = 1, template_id: str = "tmpl-1",
                 failure_class: str | None = None,
                 persona_id=None, execution_id=None) -> OutcomeRecord:
    return OutcomeRecord(
        scope="step",
        scope_id=uuid4(),
        persona_id=persona_id or uuid4(),
        environment_family="web",
        environment_instance=site,
        outcome_type="step_attempt",
        success=success,
        evidence=f"{action} {'ok' if success else 'fail'}",
        execution_id=execution_id,
        metrics={
            "step_id": f"hash-{site}-{step_seq}",
            "step_seq": step_seq,
            "action": action,
            "role": "button",
            "name": "Login",
            "resolved_by": "selector_v1",
            "recovered_by": None,
            "resolution_depth": 0,
            "effect_verified": success,
            "failure_class": failure_class,
            "root_cause": None if success else "selector_miss",
            "resolution_time_ms": 42,
            "environment_key": f"{site}:default",
            "template_id": template_id,
            "template_name": "demo",
        },
    )


def _ledger_with(*records: OutcomeRecord) -> OutcomeLedger:
    ledger = OutcomeLedger()
    for r in records:
        ledger.record(r)
    return ledger


def test_extract_from_synthetic_ledger():
    ledger = _ledger_with(
        _step_record(site="saucedemo", success=True, step_seq=1),
        _step_record(site="saucedemo", success=True, step_seq=2, action="fill"),
        _step_record(site="saucedemo", success=False, step_seq=3,
                     failure_class="selector_miss"),
    )
    eps = extract_bc_episodes(ledger, success_only=False)
    assert len(eps) == 3
    labels = sorted(e["label"] for e in eps)
    assert labels == [0, 1, 1]
    # Field plumbing
    e0 = next(e for e in eps if e["step_seq"] == 1)
    assert e0["site"] == "saucedemo"
    assert e0["action_type"] == "click"
    assert e0["resolution_strategy"] == "selector_v1"
    assert e0["step_id"] == "hash-saucedemo-1"
    assert e0["template_id"] == "tmpl-1"


def test_success_only_filter():
    ledger = _ledger_with(
        _step_record(site="saucedemo", success=True, step_seq=1),
        _step_record(site="saucedemo", success=True, step_seq=2),
        _step_record(site="saucedemo", success=False, step_seq=3,
                     failure_class="timeout"),
    )
    eps = extract_bc_episodes(ledger, success_only=True)
    assert len(eps) == 2
    assert all(e["label"] == 1 for e in eps)


def test_site_filter():
    ledger = _ledger_with(
        _step_record(site="saucedemo", success=True, step_seq=1),
        _step_record(site="saucedemo", success=True, step_seq=2),
        _step_record(site="github", success=True, step_seq=1),
    )
    eps = extract_bc_episodes(ledger, success_only=True, sites=["saucedemo"])
    assert len(eps) == 2
    assert {e["site"] for e in eps} == {"saucedemo"}


def test_write_jsonl_roundtrip():
    ledger = _ledger_with(
        _step_record(site="saucedemo", success=True, step_seq=1),
        _step_record(site="saucedemo", success=True, step_seq=2, action="fill"),
    )
    eps = extract_bc_episodes(ledger, success_only=True)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "nested" / "bc.jsonl"
        write_jsonl(eps, out)
        assert out.exists()
        lines = out.read_text(encoding="utf-8").splitlines()
        assert len(lines) == len(eps)
        parsed = [json.loads(line) for line in lines]
        assert [p["step_seq"] for p in parsed] == [1, 2]
        assert [p["action_type"] for p in parsed] == ["click", "fill"]


def test_summarize_counts():
    ledger = _ledger_with(
        _step_record(site="saucedemo", success=True, step_seq=1, action="click"),
        _step_record(site="saucedemo", success=True, step_seq=2, action="fill"),
        _step_record(site="github", success=False, step_seq=1, action="click",
                     failure_class="selector_miss"),
    )
    eps = extract_bc_episodes(ledger, success_only=False)
    s = summarize(eps)
    assert s["total"] == 3
    assert s["by_site"] == {"saucedemo": 2, "github": 1}
    assert s["by_action"] == {"click": 2, "fill": 1}
    assert s["by_failure_class"]["selector_miss"] == 1
    assert s["by_failure_class"]["_none_"] == 2
    assert s["success_rate"] == pytest.approx(2 / 3)
    assert s["sites_count"] == 2
    assert s["templates_count"] == 1
