"""
Unit tests for P7G-B3a: Lexicographic State Quality Ranking.

Verifies that:
1. AVAILABILITY strictly dominates OBSERVATION based on Lexicographic ordering.
2. Ranking is completely deterministic, relying on Python tuple comparison.
"""
import sys
import unittest
sys.path.insert(0, '.')

from browsermind_core.ontology.asset import AssetGraph, StateClass, TrustTier
from browsermind_core.agent.backward_state_planner import BackwardStatePlanner
from browsermind_core.agent.path_utility import PathUtilityScorer, PathScore


def build_ranking_test_graph() -> AssetGraph:
    """
    Graph with TWO independent paths for `verification_code`.
    Path A: email chain (OBSERVATION)
    Path B: vault chain (AVAILABILITY)
    """
    graph = AssetGraph()

    graph.add_node("email_account", "AssetType")
    graph.add_node("goal_context", "AssetType")
    graph.add_node("credential_asset", "AssetType")

    # Path A: Email (Observation)
    graph.add_node("search_email", "Capability", {
        "inputs": ["email_account", "goal_context"],
        "outputs": ["email_id"],
        "consumes_state": [],
        "produces_state": ["email.selected"]
    })

    graph.add_node("read_email", "Capability", {
        "inputs": ["email_id"],
        "outputs": ["email_content"],
        "consumes_state": ["email.selected"],
        "produces_state": ["email.opened"]
    })

    # Path B: Vault (Availability)
    graph.add_node("retrieve_credential", "Capability", {
        "inputs": ["credential_asset"],
        "outputs": ["credential_id"],
        "consumes_state": [],
        "produces_state": ["vault.credentials_unlocked"]
    })

    graph.add_node("generate_otp", "Capability", {
        "inputs": ["credential_id"],
        "outputs": ["otp_code"],
        "consumes_state": ["vault.credentials_unlocked"],
        "produces_state": ["vault.otp_generated"]
    })

    return graph


class TestPathRankingLexicographic(unittest.TestCase):

    def setUp(self):
        self.graph = build_ranking_test_graph()
        self.planner = BackwardStatePlanner()
        self.scorer = PathUtilityScorer()

    def test_lexicographic_comparison(self):
        """Test that the PathScore object compares correctly."""
        score_a = PathScore(state_quality=StateClass.OBSERVATION, path_length=2)
        score_b = PathScore(state_quality=StateClass.AVAILABILITY, path_length=2)
        score_c = PathScore(state_quality=StateClass.AVAILABILITY, path_length=5) # Longer, but AVAILABILITY

        # AVAILABILITY strictly dominates OBSERVATION
        self.assertTrue(self.scorer.get_sort_key(score_b) > self.scorer.get_sort_key(score_a))
        self.assertTrue(self.scorer.get_sort_key(score_c) > self.scorer.get_sort_key(score_a))

        # For tie-breakers, shorter is better
        self.assertTrue(self.scorer.get_sort_key(score_b) > self.scorer.get_sort_key(score_c))

    def test_planner_lexicographic_sorting(self):
        """Test that the planner sorts Candidate paths properly without scalar values."""
        res_a = self.planner.check_reachability("email.opened", self.graph)
        res_b = self.planner.check_reachability("vault.otp_generated", self.graph)

        self.assertTrue(res_a["reachable"])
        self.assertTrue(res_b["reachable"])

        path_a = res_a["candidate_paths"][0]
        path_b = res_b["candidate_paths"][0]
        
        score_a = res_a["path_scores"][0]
        score_b = res_b["path_scores"][0]

        all_candidates = [
            (path_a, score_a),
            (path_b, score_b)
        ]
        
        # Sort using the explicit ranking policy
        all_candidates.sort(key=lambda x: self.scorer.get_sort_key(x[1]), reverse=True)

        top_path = all_candidates[0][0]
        top_score = all_candidates[0][1]

        self.assertEqual(top_path, ["retrieve_credential", "generate_otp"])
        self.assertEqual(top_score.state_quality, StateClass.AVAILABILITY)


if __name__ == '__main__':
    unittest.main()
