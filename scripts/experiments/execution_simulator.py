"""
Execution Simulator.

TESTING INFRASTRUCTURE ONLY.
Mocks physical execution to produce artifacts for the ExecutionCoordinator.
"""
from typing import List, Dict, Any

class ExecutionSimulator:
    def __init__(self, mock_scenarios: Dict[tuple, Dict[str, Any]]):
        """
        mock_scenarios maps a path tuple to an expected artifact output.
        e.g., {("retrieve_credential", "generate_otp"): {"otp": "123", "expired": True}}
        """
        self.mock_scenarios = mock_scenarios

    def simulate(self, path: List[str]) -> Dict[str, Any]:
        path_key = tuple(path)
        return self.mock_scenarios.get(path_key, {})  # returns empty artifact by default
