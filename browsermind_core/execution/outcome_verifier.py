"""
Outcome Verifier.

Part of the Execution Stack. Evaluates raw execution artifacts 
to verify their validity independently of the Planning Stack.
It knows nothing about Goals, Requirements, or Target States.
It only knows how to inspect data.
"""
from enum import Enum
from typing import Dict, Any


class VerificationResult(Enum):
    VALID = "valid"
    MISSING_ARTIFACT = "missing_artifact"
    SCHEMA_MISMATCH = "schema_mismatch"
    CONSTRAINT_VIOLATION = "constraint_violation"
    EXECUTION_ERROR = "execution_error"


class OutcomeVerifier:
    """
    Validates physical data outcomes produced by capabilities.
    """
    
    def verify(self, artifact: Dict[str, Any], execution_context: Dict[str, Any]) -> VerificationResult:
        """
        Inspect the artifact against a formal Validation Contract in the execution_context.
        The verifier knows nothing about the source planner or requirements.
        """
        if not artifact:
            return VerificationResult.MISSING_ARTIFACT
            
        contract = execution_context.get("validation_contract", {})
        
        # 1. Schema Validation
        required_keys = contract.get("required_keys", [])
        for key in required_keys:
            if key not in artifact:
                return VerificationResult.SCHEMA_MISMATCH
                
        # 2. Constraint Validation (e.g. must not be expired)
        constraints = contract.get("constraints", {})
        for key, expected_value in constraints.items():
            val = artifact.get(key)
            if val is None and expected_value is False:
                continue
            if val != expected_value:
                return VerificationResult.CONSTRAINT_VIOLATION
                
        return VerificationResult.VALID
