"""Tests for browsermind_core.training.objective_fn."""
from __future__ import annotations

import math
import pytest
from browsermind_core.training.objective_fn import (
    TaskValueScore,
    CorpusStats,
    score_execution,
    score_all_executions,
)


# ── helpers ─────────────────────────────────────────────────────────────────

def _ep(
    *,
    execution_id: str = "exec_1",
    site: str = "greenhouse",
    template_id: str = "greenhouse",
    label: int = 1,
    resolution_strategy: str = "primary_semantic",
    vault_resolution_path: str | None = None,
) -> dict:
    return {
        "execution_id": execution_id,
        "site": site,
        "template_id": template_id,
        "label": label,
        "resolution_strategy": resolution_strategy,
        "vault_resolution_path": vault_resolution_path,
        "step_seq": 1,
        "action_type": "click",
    }


# ── TaskValueScore ───────────────────────────────────────────────────────────

class TestTaskValueScore:
    def test_aggregate_equal_weights(self):
        sc = TaskValueScore(0.4, 0.6, 0.2, 0.8, 1.0)
        assert abs(sc.aggregate - (0.4 + 0.6 + 0.2 + 0.8 + 1.0) / 5) < 1e-9

    def test_aggregate_custom_weights(self):
        sc = TaskValueScore(1.0, 0.0, 0.0, 0.0, 0.0, weights=[1.0, 0.0, 0.0, 0.0, 0.0])
        assert abs(sc.aggregate - 1.0) < 1e-9

    def test_as_dict_has_aggregate(self):
        sc = TaskValueScore(0.5, 0.5, 0.5, 0.5, 0.5)
        d = sc.as_dict()
        assert "aggregate" in d
        assert abs(d["aggregate"] - 0.5) < 1e-3

    def test_all_zero(self):
        sc = TaskValueScore(0.0, 0.0, 0.0, 0.0, 0.0)
        assert sc.aggregate == 0.0


# ── CorpusStats ──────────────────────────────────────────────────────────────

class TestCorpusStats:
    def test_builds_from_episodes(self):
        episodes = [
            _ep(site="greenhouse", template_id="greenhouse", execution_id="e1"),
            _ep(site="saucedemo", template_id="saucedemo", execution_id="e2"),
            _ep(site="greenhouse", template_id="greenhouse", execution_id="e1"),
        ]
        stats = CorpusStats.from_episodes(episodes)
        assert stats.total_envs == 2

    def test_workflow_class_env_count(self):
        episodes = [
            _ep(site="greenhouse", template_id="greenhouse", execution_id="e1"),
            _ep(site="lever", template_id="lever", execution_id="e2"),
        ]
        stats = CorpusStats.from_episodes(episodes)
        # Both "greenhouse" and "lever" map to "ats_apply"
        assert "ats_apply" in stats.workflow_class_env_count
        assert len(stats.workflow_class_env_count["ats_apply"]) == 2

    def test_empty_episodes(self):
        stats = CorpusStats.from_episodes([])
        assert stats.total_envs == 1  # max(1, 0)

    def test_exec_count(self):
        episodes = [
            _ep(site="greenhouse", template_id="greenhouse", execution_id="e1"),
            _ep(site="greenhouse", template_id="greenhouse", execution_id="e2"),
            _ep(site="greenhouse", template_id="greenhouse", execution_id="e1"),  # duplicate
        ]
        stats = CorpusStats.from_episodes(episodes)
        # 2 distinct executions for ats_apply
        assert stats.workflow_class_exec_count.get("ats_apply") == 2


# ── score_execution ──────────────────────────────────────────────────────────

class TestScoreExecution:
    def _stats_for(self, episodes):
        return CorpusStats.from_episodes(episodes)

    def test_empty_records_returns_zeros(self):
        stats = CorpusStats.from_episodes([])
        sc = score_execution([], stats)
        assert sc.aggregate == 0.0

    def test_workflow_depth_saturates_at_norm(self):
        steps = [_ep(execution_id="e1") for _ in range(15)]
        stats = self._stats_for(steps)
        sc = score_execution(steps, stats, depth_norm=15)
        assert abs(sc.workflow_depth - 1.0) < 1e-9

    def test_workflow_depth_partial(self):
        steps = [_ep(execution_id="e1") for _ in range(5)]
        stats = self._stats_for(steps)
        sc = score_execution(steps, stats, depth_norm=10)
        assert abs(sc.workflow_depth - 0.5) < 1e-9

    def test_success_outcome_all_success(self):
        steps = [_ep(execution_id="e1", label=1) for _ in range(4)]
        stats = self._stats_for(steps)
        sc = score_execution(steps, stats)
        assert abs(sc.success_outcome - 1.0) < 1e-9

    def test_success_outcome_all_failure(self):
        steps = [_ep(execution_id="e1", label=0) for _ in range(4)]
        stats = self._stats_for(steps)
        sc = score_execution(steps, stats)
        assert sc.success_outcome == 0.0

    def test_resource_acquisition_vault_steps(self):
        steps = [
            _ep(execution_id="e1", vault_resolution_path="env_secrets"),
            _ep(execution_id="e1", vault_resolution_path="env_secrets"),
            _ep(execution_id="e1", vault_resolution_path=None),
            _ep(execution_id="e1", vault_resolution_path=None),
        ]
        stats = self._stats_for(steps)
        sc = score_execution(steps, stats)
        assert abs(sc.resource_acquisition_value - 0.5) < 1e-9

    def test_capability_rarity_decreases_with_count(self):
        # Build a corpus where ats_apply is seen many times
        many = [_ep(site="greenhouse", template_id="greenhouse", execution_id=f"e{i}") for i in range(50)]
        stats = self._stats_for(many)
        sc_common = score_execution(many[:3], stats)
        # A rare class (not in corpus) should have higher rarity
        rare_steps = [_ep(site="lever", template_id="lever", execution_id="rx")]
        rare_stats = CorpusStats.from_episodes(rare_steps)
        sc_rare = score_execution(rare_steps, rare_stats)
        assert sc_rare.capability_rarity > sc_common.capability_rarity

    def test_transferability_single_env(self):
        steps = [_ep(site="greenhouse", template_id="greenhouse", execution_id="e1")]
        stats = self._stats_for(steps)
        sc = score_execution(steps, stats)
        # 1 env / 1 total = 1.0
        assert abs(sc.transferability - 1.0) < 1e-9

    def test_transferability_two_envs_of_three(self):
        episodes = [
            _ep(site="greenhouse", template_id="greenhouse", execution_id="e1"),
            _ep(site="lever", template_id="lever", execution_id="e2"),
            _ep(site="saucedemo", template_id="saucedemo", execution_id="e3"),
        ]
        stats = self._stats_for(episodes)
        # ats_apply covers greenhouse + lever = 2 envs, total = 3
        ats_steps = [_ep(site="greenhouse", template_id="greenhouse", execution_id="e1")]
        sc = score_execution(ats_steps, stats)
        assert abs(sc.transferability - 2 / 3) < 1e-9

    def test_custom_weights(self):
        steps = [_ep(execution_id="e1", label=1)]
        stats = self._stats_for(steps)
        sc = score_execution(steps, stats, weights=[0.0, 0.0, 0.0, 0.0, 1.0])
        assert abs(sc.aggregate - sc.success_outcome) < 1e-9


# ── score_all_executions ─────────────────────────────────────────────────────

class TestScoreAllExecutions:
    def test_returns_one_score_per_execution(self):
        episodes = [
            _ep(execution_id="e1", site="greenhouse"),
            _ep(execution_id="e1", site="greenhouse"),
            _ep(execution_id="e2", site="saucedemo", template_id="saucedemo"),
        ]
        stats = CorpusStats.from_episodes(episodes)
        scores = score_all_executions(episodes, stats)
        assert set(scores.keys()) == {"e1", "e2"}

    def test_empty_episodes(self):
        stats = CorpusStats.from_episodes([])
        scores = score_all_executions([], stats)
        assert scores == {}

    def test_all_scores_in_unit_interval(self):
        episodes = [
            _ep(execution_id=f"e{i}", site="greenhouse", template_id="greenhouse")
            for i in range(5)
        ]
        stats = CorpusStats.from_episodes(episodes)
        scores = score_all_executions(episodes, stats)
        for sc in scores.values():
            assert 0.0 <= sc.aggregate <= 1.0


# ── annotate_with_scores ─────────────────────────────────────────────────────

class TestAnnotateWithScores:
    def test_adds_task_value_score_field(self):
        from browsermind_core.training.episode_extractor import annotate_with_scores
        episodes = [_ep(execution_id="e1"), _ep(execution_id="e1")]
        annotated = annotate_with_scores(episodes)
        for ep in annotated:
            assert "task_value_score" in ep
            assert "task_value_components" in ep
            assert 0.0 <= ep["task_value_score"] <= 1.0

    def test_no_mutation_of_unrelated_fields(self):
        from browsermind_core.training.episode_extractor import annotate_with_scores
        episodes = [_ep(execution_id="e1", label=1)]
        annotate_with_scores(episodes)
        assert episodes[0]["label"] == 1

    def test_empty_list(self):
        from browsermind_core.training.episode_extractor import annotate_with_scores
        result = annotate_with_scores([])
        assert result == []
