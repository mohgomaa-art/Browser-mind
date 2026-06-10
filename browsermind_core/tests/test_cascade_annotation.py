"""Unit tests for the cascade annotator (Stage 2.1).

These tests pin the contract: cascade fields are pure derivations, additive,
and idempotent. If they grow execution semantics, these tests should
break and force a review.
"""
from browsermind_core.ledger.cascade import (
    annotate,
    cascade_layer_for,
    proxy_for,
    workflow_class_for,
)


def test_workflow_class_for_known_template():
    assert workflow_class_for(template_name="greenhousev2") == "ats_apply"
    assert workflow_class_for(template_name="saucedemo") == "ecommerce_checkout"
    assert workflow_class_for(template_name="demoqa") == "forms_harness"


def test_workflow_class_falls_back_to_environment():
    assert workflow_class_for(template_name="unknown_tpl",
                              environment_instance="greenhouse") == "ats_apply"
    assert workflow_class_for(template_name="",
                              environment_instance="saucedemo") == "ecommerce_checkout"


def test_workflow_class_unclassified_when_nothing_matches():
    assert workflow_class_for() == "unclassified"
    assert workflow_class_for(template_name="zzz",
                              environment_instance="qqq") == "unclassified"


def test_cascade_layer_for():
    assert cascade_layer_for("step") == 1
    assert cascade_layer_for("execution") == 2
    assert cascade_layer_for("task") == 2
    assert cascade_layer_for("workflow_instance") == 2
    assert cascade_layer_for("unknown_scope") == 0


def test_proxy_for_returns_none_for_all_current_layers():
    """Distal ingestion does not exist yet. Every layer returns None until
    Stage 4 picks a direction. This pins the slot as reserved."""
    for layer in (0, 1, 2, 3, 4, 5):
        assert proxy_for(layer) is None


def test_annotate_adds_three_fields_to_step_metrics():
    metrics = {"step_seq": 10, "action": "click"}
    out = annotate(metrics, scope="step", template_name="greenhousev2",
                   environment_instance="greenhouse")
    assert out is metrics  # in-place
    assert out["cascade_layer"] == 1
    assert out["cascade_workflow_class"] == "ats_apply"
    assert out["cascade_proxy_for"] is None
    # Original keys untouched
    assert out["step_seq"] == 10
    assert out["action"] == "click"


def test_annotate_workflow_instance_is_layer_2():
    metrics = {}
    annotate(metrics, scope="workflow_instance", template_name="greenhousev2")
    assert metrics["cascade_layer"] == 2


def test_annotate_is_idempotent():
    """Re-annotation must not change values once set. Important for
    replay-of-replay scenarios."""
    metrics = {"cascade_layer": 99, "cascade_workflow_class": "preserved",
               "cascade_proxy_for": "stage4_thing"}
    annotate(metrics, scope="step", template_name="greenhousev2")
    assert metrics["cascade_layer"] == 99
    assert metrics["cascade_workflow_class"] == "preserved"
    assert metrics["cascade_proxy_for"] == "stage4_thing"


def test_annotate_adds_only_three_keys():
    """Stage 2 contract: cascade is annotation-only. The annotator must
    not add more than the three documented fields. If this assertion fires,
    someone is sneaking execution semantics in."""
    before = {"step_seq": 1}
    annotate(before, scope="step", template_name="saucedemo")
    new_keys = set(before.keys()) - {"step_seq"}
    assert new_keys == {"cascade_layer", "cascade_workflow_class", "cascade_proxy_for"}, (
        f"Cascade annotator added unexpected keys: {new_keys}. "
        "Stage 2 authorization permits only cascade_layer, "
        "cascade_workflow_class, cascade_proxy_for."
    )
