"""P5D — Candidate Family Registry.

NOTE: These are CANDIDATE families, not proven Capability Families.
The P5D experiment itself will determine whether these groupings correspond
to real behavioral clusters, or whether the ontology is flat.

Do NOT treat these labels as ground truth until the Separability Score validates them.
"""

# Maps group key PREFIXES to Candidate Family tags.
# Expand as more variance groups are recorded.
CANDIDATE_FAMILY_REGISTRY: dict[str, str] = {
    # --- DISCOVERY CANDIDATE: Find an object across a domain ---
    "var_github_":           "DISCOVERY",
    "var_static_baseline_":  "DISCOVERY",
    "var_huggingface_":      "DISCOVERY",

    # --- TRANSACTION CANDIDATE: Complete a multi-step checkout/purchase ---
    "var_saucedemo_":        "TRANSACTION",

    # --- AUTHENTICATION CANDIDATE: Prove identity ---
    "var_aria_internet_":    "AUTHENTICATION",
}


def get_candidate_family(group_key: str) -> str:
    """Returns the Candidate Family for a given group key, or 'UNKNOWN'.
    
    UNKNOWN means the group has not been assigned to a candidate family yet.
    It will be excluded from family-level analysis.
    """
    for prefix, family in CANDIDATE_FAMILY_REGISTRY.items():
        if group_key.startswith(prefix):
            return family
    return "UNKNOWN"
