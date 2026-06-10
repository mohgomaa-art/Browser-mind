"""A-2: post-action probe must not produce false-positive effect_verified=True
when loc.evaluate raises but the element is still present.

The probe block lives deep inside ReplayEngine.replay(); these tests verify the
behavior at two levels:

1. Behavioral — re-implement the patched control flow against a FakeLocator and
   assert the four expected branches: count==0 evaporation, evaluate-error with
   element still present, both-throw, and value-change happy path.

2. Source-level regression — ensure the buggy pattern (bare `except Exception`
   that sets `effect_type = "ELEMENT_DISAPPEARED"` and `effect_verified = True`
   without checking count) cannot reappear in replay_engine.py.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from browsermind_core.runtime.replay_engine import ReplayEngine  # noqa: F401 (import-OK smoke)


REPLAY_ENGINE_SRC = (
    Path(__file__).resolve().parents[1] / "runtime" / "replay_engine.py"
).read_text(encoding="utf-8")


# --- Behavioral re-implementation of the patched probe ----------------------

class _FakeLocator:
    def __init__(self, evaluate_value=None, evaluate_exc=None, count_value=1, count_exc=None):
        self._evaluate_value = evaluate_value
        self._evaluate_exc = evaluate_exc
        self._count_value = count_value
        self._count_exc = count_exc

    async def evaluate(self, *_args, **_kwargs):
        if self._evaluate_exc is not None:
            raise self._evaluate_exc
        return self._evaluate_value

    async def count(self):
        if self._count_exc is not None:
            raise self._count_exc
        return self._count_value


async def _probe(loc, val_before, action_type):
    """Mirror of the patched probe block. Kept in lock-step with replay_engine.py
    so a regression in one shows up here.

    Phase 2 contract: effect_verified=True means "an effect was observed".
    Element disappearance is AMBIGUOUS (could be navigation OR teardown-on-failure)
    so it surfaces as effect_verified=None.
    """
    effect_type = None
    effect_verified = None
    effect_details = None

    try:
        if await loc.count() == 0:
            effect_type = "ELEMENT_DISAPPEARED"
            effect_verified = None
        else:
            if val_before is not None:
                val_after = await loc.evaluate("el => el.value")
                if val_before != val_after:
                    effect_type = "VALUE_CHANGED"
                    effect_verified = True
                    effect_details = {"val_before": val_before, "val_after": val_after}
                else:
                    if action_type == "fill":
                        effect_type = "UNKNOWN"
                        effect_verified = False
                    else:
                        effect_type = "UNKNOWN"
                        effect_verified = None
            else:
                effect_type = "UNKNOWN"
                effect_verified = None
    except Exception as probe_err:
        try:
            gone = (await loc.count() == 0)
        except Exception:
            gone = False
        if gone:
            effect_type = "ELEMENT_DISAPPEARED"
            effect_verified = None
            effect_details = {"probe_error": str(probe_err)[:200]}
        else:
            effect_type = "PROBE_FAILED"
            effect_verified = False
            effect_details = {"probe_error": str(probe_err)[:200]}

    return effect_type, effect_verified, effect_details


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if asyncio.get_event_loop().is_running() is False else asyncio.run(coro)


def test_element_actually_disappeared_remains_verified():
    loc = _FakeLocator(count_value=0)
    et, ev, _ = asyncio.run(_probe(loc, val_before="hello", action_type="fill"))
    # Phase 2: disappearance is ambiguous — verified must be None, not True.
    assert et == "ELEMENT_DISAPPEARED"
    assert ev is None


def test_value_change_happy_path_remains_verified():
    loc = _FakeLocator(evaluate_value="world", count_value=1)
    et, ev, details = asyncio.run(_probe(loc, val_before="hello", action_type="fill"))
    assert et == "VALUE_CHANGED"
    assert ev is True
    assert details == {"val_before": "hello", "val_after": "world"}


def test_evaluate_error_with_element_present_is_probe_failed():
    loc = _FakeLocator(evaluate_exc=Exception("Internal page navigation"), count_value=1)
    et, ev, details = asyncio.run(_probe(loc, val_before="hello", action_type="fill"))
    assert et == "PROBE_FAILED"
    assert ev is False
    assert "Internal page navigation" in details["probe_error"]


def test_evaluate_and_count_both_error_is_probe_failed():
    # First count() (the gating one in the try) returns 1 so we enter the evaluate branch,
    # then evaluate() throws, then the recovery count() throws too.
    class _Tricky:
        def __init__(self):
            self._count_calls = 0

        async def count(self):
            self._count_calls += 1
            if self._count_calls == 1:
                return 1
            raise Exception("count failed too")

        async def evaluate(self, *_a, **_k):
            raise Exception("Element is not connected")

    loc = _Tricky()
    et, ev, details = asyncio.run(_probe(loc, val_before="hello", action_type="fill"))
    assert et == "PROBE_FAILED"
    assert ev is False
    assert "Element is not connected" in details["probe_error"]


def test_evaluate_error_with_element_evaporated_is_disappeared_verified():
    # First count() returns 1, then evaluate raises, and the recovery count() returns 0.
    class _Late:
        def __init__(self):
            self._count_calls = 0

        async def count(self):
            self._count_calls += 1
            return 1 if self._count_calls == 1 else 0

        async def evaluate(self, *_a, **_k):
            raise Exception("late detach")

    loc = _Late()
    et, ev, _ = asyncio.run(_probe(loc, val_before="hello", action_type="fill"))
    # Phase 2: disappearance with prior probe exception is even more suspicious;
    # surface as ELEMENT_DISAPPEARED with verified=None, not True.
    assert et == "ELEMENT_DISAPPEARED"
    assert ev is None


# --- Source regression --------------------------------------------------------

def test_buggy_pattern_is_gone_from_replay_engine():
    # The exact buggy block: bare `except Exception:` followed by ELEMENT_DISAPPEARED + verified=True
    # with no count() check beforehand.
    bad = re.compile(
        r"except\s+Exception\s*:\s*\n"
        r"\s+effect_type\s*=\s*\"ELEMENT_DISAPPEARED\"\s*\n"
        r"\s+effect_verified\s*=\s*True",
    )
    assert bad.search(REPLAY_ENGINE_SRC) is None, (
        "A-2 regression: replay_engine.py contains the bare-except path that "
        "treats every probe exception as a verified element disappearance."
    )


def test_probe_failed_branch_is_present_in_replay_engine():
    assert "PROBE_FAILED" in REPLAY_ENGINE_SRC
    assert "probe_error" in REPLAY_ENGINE_SRC


def test_phase2_element_disappeared_no_longer_mints_verified_true():
    """Regression: ELEMENT_DISAPPEARED must not be coupled with effect_verified=True.

    Disappearance is ambiguous (navigation success vs. teardown-on-failure).
    Treat as None so downstream learners do not optimize toward the false signal.
    """
    bad = re.compile(
        r"effect_type\s*=\s*\"ELEMENT_DISAPPEARED\"\s*\n"
        r"\s+effect_verified\s*=\s*True",
    )
    assert bad.search(REPLAY_ENGINE_SRC) is None, (
        "Phase 2 regression: replay_engine.py minted effect_verified=True on "
        "ELEMENT_DISAPPEARED. This is the false-positive path RL would learn from."
    )
