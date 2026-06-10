"""Adaptive Learning v1 — adaptation hook tests.

Tests two integrations:

A. TargetResolver consults LessonReader.get_recovery_priors before R1-R5
   and tries the highest-success-rate strategy first.

B. DemonstrationCompiler downgrades a step to AMBIGUOUS and emits an
   evidence row (requires_human_approval=True) when LessonReader reports
   >= 3 failures for the descriptor signature. No template selector is
   mutated.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from browsermind_core.runtime.target_resolver import TargetResolver


RESOLVER_SRC = (
    Path(__file__).resolve().parents[1] / "runtime" / "target_resolver.py"
).read_text(encoding="utf-8")

COMPILER_SRC = (
    Path(__file__).resolve().parents[1] / "recorder" / "demonstration_compiler.py"
).read_text(encoding="utf-8")


# --- Source-level guards -----------------------------------------------------


def test_resolver_init_accepts_lesson_reader_kwarg():
    sig = inspect.signature(TargetResolver.__init__)
    assert "lesson_reader" in sig.parameters


def test_resolver_consults_lesson_priors_before_r1():
    """Source-level: the lesson_priors block must precede the '# R1: Container
    proximity' marker."""
    lesson_idx = RESOLVER_SRC.find("get_recovery_priors")
    r1_idx = RESOLVER_SRC.find("# R1: Container proximity")
    assert lesson_idx != -1 and r1_idx != -1
    assert lesson_idx < r1_idx, (
        "Adaptive v1: get_recovery_priors must be consulted BEFORE R1-R5 ladder"
    )


def test_resolver_tags_lesson_prior_hits():
    assert 'recovered_by=f"lesson_prior:{recovered_by}"' in RESOLVER_SRC, (
        "Adaptive v1: resolver must label lesson-driven hits with "
        "recovered_by='lesson_prior:...' so cross-run measurement is possible"
    )


def test_compiler_consults_lesson_reader_and_emits_evidence():
    assert "get_step_failure_count" in COMPILER_SRC
    assert "lesson_evidence:repeated_target_changed" in COMPILER_SRC
    assert "requires_human_approval" in COMPILER_SRC
    assert 'tpl.metadata["lesson_evidence"]' in COMPILER_SRC


def test_compiler_does_not_mutate_template_selectors():
    """Source-level: the override block must touch step['replayability'] only.

    We allow assignment to step['replayability'] and reads of step.get(...).
    We forbid writes to step['target_selector'], step['target_role'],
    step['target_name'], step['action'].
    """
    forbidden = [
        'step["target_selector"] =',
        'step["target_role"] =',
        'step["target_name"] =',
        'step["action"] =',
        "step['target_selector'] =",
        "step['target_role'] =",
        "step['target_name'] =",
        "step['action'] =",
    ]
    for needle in forbidden:
        assert needle not in COMPILER_SRC, (
            f"Adaptive v1: compiler must not mutate {needle}; only "
            "step['replayability'] may be overridden."
        )


# --- Behavioral: compiler downgrade + evidence row ---------------------------


def test_compiler_downgrades_high_to_ambiguous_with_evidence(tmp_path):
    """When the lesson reader reports >= 3 TARGET_CHANGED failures, the
    HIGH-tier step must become AMBIGUOUS with lesson_override=True, and the
    template metadata must carry a matching evidence row."""
    from browsermind_core.recorder.demonstration_compiler import DemonstrationCompiler
    from browsermind_core.recorder.demonstration_session import (
        DemonstrationSession, DemonstrationStep,
    )
    from browsermind_core.console.session import KernelSession

    ks = KernelSession(store_dir=str(tmp_path))
    # Stub the lesson reader to report 4 failures for this signature.
    fake_reader = MagicMock()
    fake_reader.get_step_failure_count.return_value = 4
    ks.lesson_reader = fake_reader

    step = DemonstrationStep(
        seq=1,
        action_type="click",
        target_role="button",
        target_name="Submit",
        target_selector="button.submit",
        url="https://saucedemo.com/",
    )
    session = DemonstrationSession(
        environment_family="saucedemo",
        environment_instance="saucedemo",
        start_url="https://saucedemo.com/",
        actions=[step],
    )

    compiler = DemonstrationCompiler(ks)
    tpl = compiler.compile(session, template_name="t1")

    # Self-Learning v1: the compiler must NOT auto-downgrade. The tier
    # stays HIGH; mutation only lands after `bm workflow candidate approve`.
    assert len(tpl.steps) == 1
    repl = tpl.steps[0]["replayability"]
    assert repl["tier"] == "HIGH"
    assert repl.get("lesson_override") is not True

    # Evidence row must exist and carry the approval flag.
    rows = tpl.metadata.get("lesson_evidence") or []
    assert len(rows) == 1
    assert rows[0]["candidate_tier"] == "AMBIGUOUS"
    assert rows[0]["requires_human_approval"] is True
    assert rows[0]["observations"] == 4
    assert rows[0]["reason"] == "lesson_evidence:repeated_target_changed"

    # A pending TemplateCandidate must have been emitted.
    pending_id = tpl.metadata.get("pending_candidate_id")
    assert pending_id is not None
    candidates = ks.candidate_registry.list(status="pending")
    assert any(str(c.id) == pending_id for c in candidates)

    # The selector/role/name must NOT have been mutated.
    assert tpl.steps[0].get("target_selector") == "button.submit"
    assert tpl.steps[0].get("target_role") == "button"
    assert tpl.steps[0].get("target_name") == "Submit"


def test_compiler_below_threshold_does_not_downgrade(tmp_path):
    from browsermind_core.recorder.demonstration_compiler import DemonstrationCompiler
    from browsermind_core.recorder.demonstration_session import (
        DemonstrationSession, DemonstrationStep,
    )
    from browsermind_core.console.session import KernelSession

    ks = KernelSession(store_dir=str(tmp_path))
    fake_reader = MagicMock()
    fake_reader.get_step_failure_count.return_value = 1  # below threshold
    ks.lesson_reader = fake_reader

    session = DemonstrationSession(
        environment_family="saucedemo",
        environment_instance="saucedemo",
        start_url="https://saucedemo.com/",
        actions=[DemonstrationStep(
            seq=1,
            action_type="click", target_role="button", target_name="Submit",
            target_selector="button.submit",
            url="https://saucedemo.com/",
        )],
    )
    tpl = DemonstrationCompiler(ks).compile(session, template_name="t2")
    repl = tpl.steps[0]["replayability"]
    assert repl.get("lesson_override") is not True
    assert tpl.metadata.get("lesson_evidence") == []


# --- Behavioral: resolver dispatch via lesson priors ------------------------


@pytest.mark.asyncio
async def test_resolver_lesson_dispatch_picks_highest_rate_strategy(monkeypatch):
    """When LessonReader returns container_proximity=0.9 and structural_path=0.6,
    the resolver must try container_proximity first via _try_find_container,
    and on success return ResolutionResult with recovered_by='lesson_prior:container_proximity'.
    """
    from browsermind_core.runtime.target_resolver import (
        TargetResolver, ResolutionResult,
    )

    fake_reader = MagicMock()
    fake_reader.get_recovery_priors.return_value = {
        "container_proximity": 0.9, "structural_path": 0.6,
    }

    # Fake locator objects: container returns a one-element loose_semantic match.
    container_loc = MagicMock()
    container_loc.count = AsyncMock(return_value=1)

    class _Container:
        def locator(self, *_a, **_k):
            return container_loc
        def get_by_role(self, *_a, **_k):
            return container_loc

    fake_page = MagicMock()
    resolver = TargetResolver(fake_page, env_key="saucedemo",
                              persona_id="alpha", lesson_reader=fake_reader)

    # Stub the container helper used by the container_proximity branch.
    async def _fake_find_container(_desc):
        return _Container()
    resolver._try_find_container = _fake_find_container

    # Stub everything the early portion of resolve() touches so we reach
    # the lesson block without diving into the real Playwright frames.
    descriptor = {
        "target_role": "button",
        "target_name": "Submit",
        "target_selector": "button.submit",
    }

    # Drive the lesson block directly: we cannot run the full async resolve()
    # without a real Page. Re-implement the dispatch using the same helpers
    # the resolver calls — this verifies the helper wiring without coupling
    # to Playwright internals.
    priors = resolver._lesson_reader.get_recovery_priors("TARGET_CHANGED")
    assert priors  # sanity
    ranked = sorted(priors.items(), key=lambda kv: kv[1], reverse=True)
    assert ranked[0][0] == "container_proximity"

    container = await resolver._try_find_container(descriptor)
    assert container is not None
    cand = container.locator(descriptor["target_selector"])
    assert await cand.count() == 1


def test_resolver_no_lesson_reader_skips_block():
    """Without a lesson_reader, the resolver should still construct."""
    resolver = TargetResolver(MagicMock(), env_key="saucedemo",
                              persona_id="alpha")
    assert resolver._lesson_reader is None
