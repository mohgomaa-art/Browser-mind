from uuid import uuid4

from browsermind_core.recorder.demonstration_repository import DemonstrationRepository
from browsermind_core.recorder.demonstration_session import DemonstrationSession, DemonstrationStep


def test_demonstration_persists_and_lists(tmp_path):
    store = str(tmp_path / "bm")
    repo = DemonstrationRepository(store)
    session = DemonstrationSession(
        persona_name="pilot",
        environment_family="saucedemo",
        environment_instance="https://www.saucedemo.com/",
    )
    session.append(
        DemonstrationStep(seq=0, action_type="click", target_selector="button#login")
    )
    session.complete()
    repo.save(session)

    repo2 = DemonstrationRepository(store)
    loaded = repo2.load(session.id)
    assert loaded is not None
    assert len(loaded.actions) == 1
    rows = repo2.list_sessions()
    assert rows[0]["id"] == str(session.id)
