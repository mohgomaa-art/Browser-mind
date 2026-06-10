"""B-1: recording_evidence plumbing from JS payload -> DemonstrationStep -> repo -> compiler."""
from __future__ import annotations

import tempfile

from browsermind_core.recorder.demonstration_repository import DemonstrationRepository
from browsermind_core.recorder.demonstration_session import (
    DemonstrationSession,
    DemonstrationStep,
)


def _fake_payload() -> dict:
    return {
        "action_type": "click",
        "url": "http://test.local/page",
        "target_role": "button",
        "target_name": "Submit",
        "target_selector": "#submit",
        "value": None,
        "vault_ref": None,
        "result_url": "http://test.local/page",
        "result_state": "success",
        "screenshot_hash": "abc123",
        "descriptor": {"tag": "button"},
        "meta": {"foo": "bar"},
        "recording_evidence": {"candidate_count": 3, "page_url": "http://test.local/x"},
    }


def _build_step_from_payload(payload: dict) -> DemonstrationStep:
    return DemonstrationStep(
        seq=0,
        action_type=payload.get("action_type", "click"),
        url=payload.get("url", ""),
        target_role=payload.get("target_role", ""),
        target_name=payload.get("target_name", ""),
        target_selector=payload.get("target_selector", ""),
        value=payload.get("value"),
        vault_ref=payload.get("vault_ref"),
        result_url=payload.get("result_url", ""),
        result_state=payload.get("result_state", ""),
        screenshot_hash=payload.get("screenshot_hash", ""),
        descriptor=payload.get("descriptor") or {},
        recording_evidence=payload.get("recording_evidence") or {},
        metadata=payload.get("meta") or {},
    )


def test_field_copied_from_payload():
    payload = _fake_payload()
    step = _build_step_from_payload(payload)
    assert step.recording_evidence == {
        "candidate_count": 3,
        "page_url": "http://test.local/x",
    }


def test_field_defaults_to_empty_dict_when_missing():
    payload = _fake_payload()
    payload.pop("recording_evidence")
    step = _build_step_from_payload(payload)
    assert step.recording_evidence == {}


def test_field_roundtrips_through_json():
    step = _build_step_from_payload(_fake_payload())
    dumped = step.model_dump(mode="json")
    assert dumped["recording_evidence"] == {
        "candidate_count": 3,
        "page_url": "http://test.local/x",
    }
    revived = DemonstrationStep.model_validate(dumped)
    assert revived.recording_evidence == {
        "candidate_count": 3,
        "page_url": "http://test.local/x",
    }


def test_compiler_side_getattr_returns_dict_when_set():
    step = _build_step_from_payload(_fake_payload())
    # Emulates demonstration_compiler.py:63
    evidence = getattr(step, "recording_evidence", None)
    assert evidence == {"candidate_count": 3, "page_url": "http://test.local/x"}


def test_compiler_side_getattr_falls_back_to_none_when_absent():
    # Emulates the same line against an object that has no such attribute
    # (e.g. an older action shape that predates the field).
    class LegacyAct:
        pass

    evidence = getattr(LegacyAct(), "recording_evidence", None)
    assert evidence is None


def test_field_roundtrips_through_repository():
    payload = _fake_payload()
    step = _build_step_from_payload(payload)

    with tempfile.TemporaryDirectory() as store_dir:
        repo = DemonstrationRepository(store_dir)
        session = DemonstrationSession(
            persona_name="test_persona",
            environment_family="test_family",
            environment_instance="test_instance",
            profile_path="/tmp/profile",
            start_url="http://test.local/",
        )
        session.append(step)
        session.complete()
        repo.save(session)

        repo2 = DemonstrationRepository(store_dir)
        loaded = repo2.load(session.id)
        assert loaded is not None
        assert len(loaded.actions) == 1
        assert loaded.actions[0].recording_evidence == {
            "candidate_count": 3,
            "page_url": "http://test.local/x",
        }
