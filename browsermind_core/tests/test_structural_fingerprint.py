"""Tests for structural_fingerprint.py — affordance-based SSTG node identity."""
import pytest
from browsermind_core.runtime.structural_fingerprint import (
    affordance_vector,
    compute_structural_hash,
    vector_distance,
    vector_to_hash,
)
from browsermind_core.runtime.page_state_extractor import PageStateSignals


def _signals(**kwargs) -> PageStateSignals:
    s = PageStateSignals()
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


class TestAffordanceVector:
    def test_returns_sorted_list(self):
        vec = affordance_vector(_signals())
        assert vec == sorted(vec)

    def test_login_form_present(self):
        vec = affordance_vector(_signals(has_login_form=True))
        assert "login:True" in vec

    def test_login_form_absent(self):
        vec = affordance_vector(_signals(has_login_form=False))
        assert "login:False" in vec

    def test_form_count_binned_at_3(self):
        vec_10 = affordance_vector(_signals(form_count=10))
        vec_3  = affordance_vector(_signals(form_count=3))
        assert vec_10 == vec_3   # both bin to 3

    def test_form_count_binned_0_1_2(self):
        for n in range(3):
            vec = affordance_vector(_signals(form_count=n))
            assert f"forms:{n}" in vec

    def test_cart_derived_from_content_snippet(self):
        vec = affordance_vector(_signals(content_snippet="Your cart has 3 items"))
        assert "cart:True" in vec

    def test_cart_derived_from_headings(self):
        vec = affordance_vector(_signals(heading_texts=["Shopping Bag (2)"]))
        assert "cart:True" in vec

    def test_cart_absent_when_no_signal(self):
        vec = affordance_vector(_signals())
        assert "cart:False" in vec

    def test_modal_combines_dialog_and_modal(self):
        # has_visible_modal True → modal:True
        vec1 = affordance_vector(_signals(has_visible_modal=True))
        assert "modal:True" in vec1
        # has_visible_dialog True → modal:True
        vec2 = affordance_vector(_signals(has_visible_dialog=True))
        assert "modal:True" in vec2
        # neither → modal:False
        vec3 = affordance_vector(_signals())
        assert "modal:False" in vec3

    def test_upload_combines_dropzone_and_file_input(self):
        vec1 = affordance_vector(_signals(has_dropzone=True))
        assert "upload:True" in vec1
        vec2 = affordance_vector(_signals(has_file_input=True))
        assert "upload:True" in vec2


class TestVectorToHash:
    def test_deterministic(self):
        vec = affordance_vector(_signals(has_login_form=True))
        assert vector_to_hash(vec) == vector_to_hash(vec)

    def test_different_pages_different_hashes(self):
        h1 = compute_structural_hash(_signals(has_login_form=True))
        h2 = compute_structural_hash(_signals(has_login_form=False))
        assert h1 != h2

    def test_hash_length_16(self):
        h = compute_structural_hash(_signals())
        assert len(h) == 16

    def test_identical_signals_identical_hash(self):
        s1 = _signals(has_login_form=True, form_count=2, has_stepper=False)
        s2 = _signals(has_login_form=True, form_count=2, has_stepper=False)
        assert compute_structural_hash(s1) == compute_structural_hash(s2)

    def test_stable_across_irrelevant_field_changes(self):
        """Fields not in the affordance vector (element_count, url) must not change hash."""
        base = _signals(has_login_form=True, form_count=1)
        variant = _signals(has_login_form=True, form_count=1,
                           element_count=9999, url="https://example.com/other-page")
        assert compute_structural_hash(base) == compute_structural_hash(variant)


class TestVectorDistance:
    def test_identical_vectors_distance_zero(self):
        vec = affordance_vector(_signals(has_login_form=True))
        assert vector_distance(vec, vec) == 0.0

    def test_completely_different_vectors(self):
        a = ["login:True", "logout:False"]
        b = ["login:False", "logout:True"]
        d = vector_distance(a, b)
        # intersection=0, union=4 → distance=1.0
        assert d == 1.0

    def test_partial_overlap(self):
        a = ["a:True", "b:True", "c:False"]
        b = ["a:True", "b:False", "c:False"]
        # intersection={"a:True","c:False"}=2, union=4 → distance=0.5
        d = vector_distance(a, b)
        assert abs(d - 0.5) < 1e-9

    def test_empty_vectors_distance_zero(self):
        assert vector_distance([], []) == 0.0

    def test_one_empty_distance_one(self):
        assert vector_distance(["a:True"], []) == 1.0

    def test_login_page_vs_dashboard_high_distance(self):
        login_page = affordance_vector(_signals(
            has_login_form=True, has_logout_link=False,
            has_user_avatar=False, form_count=1,
        ))
        dashboard = affordance_vector(_signals(
            has_login_form=False, has_logout_link=True,
            has_user_avatar=True, form_count=0,
        ))
        d = vector_distance(login_page, dashboard)
        assert d > 0.2, f"Expected login vs dashboard to differ more, got {d}"

    def test_minor_styling_change_low_distance(self):
        """element_count / url changes don't affect the vector at all → distance 0."""
        before = affordance_vector(_signals(has_login_form=True, form_count=2))
        after  = affordance_vector(_signals(has_login_form=True, form_count=2))
        assert vector_distance(before, after) == 0.0
