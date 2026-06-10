from uuid import uuid4

from browsermind_core.ontology.workflow_store import WorkflowStore


def test_workflow_template_and_instance_persist(tmp_path):
    store = WorkflowStore(str(tmp_path / "bm"))
    tpl = store.create_template("saucedemo_login", family_key="saucedemo")
    persona_id = uuid4()
    inst = store.create_instance(
        "pilot",
        persona_id=persona_id,
        template_id=tpl.id,
        environment_family="saucedemo",
        profile_path=str(tmp_path / "profiles" / "saucedemo"),
    )

    store2 = WorkflowStore(str(tmp_path / "bm"))
    assert store2.lookup_template("saucedemo_login")["id"] == str(tpl.id)
    assert store2.lookup_instance("pilot")["id"] == str(inst.id)
    rehydrated = store2.get_template(tpl.id)
    assert rehydrated.name == "saucedemo_login"
    assert rehydrated.metadata.get("family_key") == "saucedemo"

def test_workflow_template_unique_name(tmp_path):
    import pytest
    store = WorkflowStore(str(tmp_path / "bm"))
    store.create_template("saucedemo_login", family_key="saucedemo")
    with pytest.raises(ValueError) as exc:
        store.create_template("saucedemo_login", family_key="saucedemo")
    assert "already exists in store" in str(exc.value)

