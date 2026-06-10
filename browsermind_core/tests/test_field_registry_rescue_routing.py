"""Stage 1 fixes — Defect B (location-mismatch) and Defect A (resolver routing).

These tests verify the two behaviors that were broken:

  Defect B: _resolve_by_field_registry must read field_id from step-level
            (where the compiler writes it), not just descriptor.

  Defect A: count>1 branch must give field_registry_rescue a chance before
            raising AmbiguousIdentityError.

The tests inspect the source code structure (cheap, no Playwright dependency)
and exercise the field-id-resolution branch of _resolve_by_field_registry
with a minimal mock that returns None at the locator stage — sufficient to
prove field lookup happens, without needing a real DOM.
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from browsermind_core.runtime import target_resolver as tr_mod
from browsermind_core.runtime.target_resolver import TargetResolver


# ── Defect B: step-level field_id is read by the resolver ────────────────


def test_resolve_signature_accepts_step_parameter():
    """resolve() must accept a `step` keyword argument so the call site can
    thread the full step dict through to recovery strategies."""
    sig = inspect.signature(TargetResolver.resolve)
    assert "step" in sig.parameters, (
        "TargetResolver.resolve must accept `step`; otherwise the replay "
        "engine cannot thread step-level field_id into the recovery track."
    )
    assert sig.parameters["step"].default is None, (
        "step must default to None to keep the signature backwards-compatible "
        "for any caller that doesn't supply it."
    )


def test_field_registry_rescue_signature_accepts_step():
    """_resolve_by_field_registry must accept `step` and read field_id from it."""
    sig = inspect.signature(TargetResolver._resolve_by_field_registry)
    assert "step" in sig.parameters, (
        "_resolve_by_field_registry must accept step= so it can read "
        "field_id from the canonical step-level location."
    )


def test_field_registry_rescue_reads_step_field_id():
    """When descriptor lacks field_id but step has it, the rescue must use the
    step value. Defect B was that descriptor was the only source consulted."""
    src = inspect.getsource(TargetResolver._resolve_by_field_registry)
    # The fix must read step.get("field_id") — verify both shapes are read.
    assert 'step.get("field_id")' in src, (
        "_resolve_by_field_registry must read step.get('field_id') as the "
        "canonical source. Defect B fix not applied."
    )
    # And descriptor.get("field_id") must still be a fallback (for any legacy
    # caller that puts it there).
    assert 'descriptor.get("field_id")' in src, (
        "descriptor.get('field_id') must remain as a fallback path for "
        "callers that pass field_id via descriptor."
    )


@pytest.mark.asyncio
async def test_field_registry_rescue_uses_step_field_id_when_descriptor_missing():
    """End-to-end behavior: with step['field_id']='country' and an empty
    descriptor, the rescue must look up the 'country' Field in the registry
    and attempt resolution against it.

    We mock the page so every locator returns count=0; this proves the
    rescue *attempted* the lookup (otherwise field would be None and the
    function would short-circuit before any locator call)."""
    # Mock page where every locator has count() == 0
    locator_mock = MagicMock()
    locator_mock.count = AsyncMock(return_value=0)

    page_mock = MagicMock()
    page_mock.get_by_role = MagicMock(return_value=locator_mock)
    page_mock.locator = MagicMock(return_value=locator_mock)

    # _try_container_label is also a method on the resolver; mock it to (None, 0)
    resolver = TargetResolver(page_mock, env_key="test", persona_id="test")
    resolver._try_container_label = AsyncMock(return_value=(None, 0))

    # Step has field_id='country'; descriptor has neither field_id nor
    # container_label. Pre-fix this would have field_id=None.
    step = {"field_id": "country", "target_name": "Toggle flyout"}
    descriptor = {"role": "button", "container_label": ""}

    result = await resolver._resolve_by_field_registry(
        target_role="button",
        target_name="Toggle flyout",
        descriptor=descriptor,
        step=step,
    )

    # With every locator returning 0 candidates, rescue must return None,
    # but get_by_role must have been called *at least once* — that proves
    # the field was looked up (else we'd have short-circuited at field=None).
    assert result is None
    assert page_mock.get_by_role.called, (
        "_resolve_by_field_registry must call get_by_role when step['field_id'] "
        "resolves to a known Field in the registry. If this assertion fires, "
        "the rescue is short-circuiting because step-level field_id is being "
        "ignored — Defect B is not actually fixed."
    )


@pytest.mark.asyncio
async def test_field_registry_rescue_short_circuits_when_no_field_resolvable():
    """Negative case: when neither step nor descriptor nor target_name nor
    container_label resolves to a Field, the rescue returns None without
    calling get_by_role. This was already correct; we re-assert it after
    the fix to ensure no regression."""
    locator_mock = MagicMock()
    locator_mock.count = AsyncMock(return_value=0)
    page_mock = MagicMock()
    page_mock.get_by_role = MagicMock(return_value=locator_mock)

    resolver = TargetResolver(page_mock, env_key="test", persona_id="test")
    resolver._try_container_label = AsyncMock(return_value=(None, 0))

    # Nothing semantic here: target_name is gibberish, no field_id anywhere,
    # no container_label.
    result = await resolver._resolve_by_field_registry(
        target_role="button",
        target_name="zxqv-not-a-field-name-1234",
        descriptor={"role": "button", "container_label": ""},
        step={"target_name": "zxqv-not-a-field-name-1234"},
    )

    assert result is None
    assert not page_mock.get_by_role.called, (
        "When no Field is identifiable, rescue must short-circuit without "
        "issuing any DOM queries. Otherwise it wastes resolver time on "
        "every unresolvable step."
    )


# ── Defect A: ambiguity branch tries R6 before raising ───────────────────


def test_count_gt_one_branch_calls_field_registry_rescue_before_raising():
    """In the count>1 branch (line ~705), Defect A required adding an attempt
    at field_registry_rescue *before* raising AmbiguousIdentityError. Verify
    the source structure: the rescue call appears before the raise inside
    the `if peak_count > 1:` block."""
    src = inspect.getsource(TargetResolver.resolve)
    # Find the count>1 block.
    marker = "if peak_count > 1"
    idx = src.find(marker)
    assert idx >= 0, "Could not find peak_count>1 branch in resolve()"

    # Within a reasonable window after the marker, both the rescue call and
    # the raise must appear, in that order.
    window = src[idx : idx + 2000]
    rescue_pos = window.find("_resolve_by_field_registry")
    raise_pos = window.find("raise AmbiguousIdentityError")
    assert rescue_pos > 0, (
        "Defect A fix not applied: count>1 branch does not call "
        "_resolve_by_field_registry before raising AmbiguousIdentityError."
    )
    assert raise_pos > rescue_pos, (
        "Order is wrong: AmbiguousIdentityError is raised before the rescue "
        "is attempted. The whole point of Defect A is to give R6 a chance "
        "*before* the error becomes terminal."
    )


def test_recovery_track_field_registry_rescue_call_passes_step():
    """The R6 call inside the recovery track (count==0 path) must also be
    updated to pass step. Without this, step-level field_id is unreachable
    on TargetNotFound cases too."""
    src = inspect.getsource(TargetResolver.resolve)
    # Find the resolve_by_field_registry calls. There should be at least
    # two — one in count>1 branch, one in recovery track. Both must pass step.
    import re
    calls = re.findall(
        r"_resolve_by_field_registry\([^)]*\)",
        src,
        flags=re.DOTALL,
    )
    assert len(calls) >= 2, (
        f"Expected at least 2 calls to _resolve_by_field_registry; found "
        f"{len(calls)}. count>1 branch and recovery track should both call it."
    )
    for call in calls:
        assert "step" in call, (
            f"This call to _resolve_by_field_registry omits step: {call!r}. "
            "Defect B fix incomplete — step must be threaded into every "
            "rescue invocation."
        )


# ── Replay engine wiring ────────────────────────────────────────────────


def test_replay_engine_passes_step_to_resolver():
    """replay_engine.py must pass step= when calling resolver.resolve(),
    otherwise the resolver receives only the descriptor sub-dict and the
    Defect B fix is reachable but never exercised."""
    from browsermind_core.runtime import replay_engine as re_mod
    src = inspect.getsource(re_mod)
    # Find the resolver.resolve call. It must include step= as a kwarg.
    assert "resolver.resolve(" in src
    # The exact call site
    idx = src.find("resolver.resolve(")
    window = src[idx : idx + 500]
    assert "step=step" in window, (
        "replay_engine.py must call resolver.resolve(..., step=step). "
        "Without this, the new step parameter on resolve() is reachable "
        "from tests but never actually exercised in a real replay."
    )
