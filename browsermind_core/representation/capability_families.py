"""P5D — Capability Family Registry.

Assigns each variance group key prefix to a Capability Family.
This is the ontological claim we are testing in P5D:
    Do invariants converge within families but diverge across them?
"""

# Maps group key PREFIXES to Capability Family tags.
# Add new entries here as more variance groups are recorded.
FAMILY_REGISTRY: dict[str, str] = {
    # --- DISCOVERY: Find an object across a domain ---
    "var_github_":           "DISCOVERY",
    "var_static_baseline_":  "DISCOVERY",
    "var_huggingface_":      "DISCOVERY",

    # --- TRANSACTION: Complete a multi-step purchase/checkout ---
    "var_saucedemo_":        "TRANSACTION",

    # --- AUTHENTICATION: Prove identity ---
    "var_aria_internet_":    "AUTHENTICATION",

    # --- CREATION: Produce a new artifact ---
    # e.g. var_github_create_issue_XXXXXXXX
    "var_github_create_":    "CREATION",

    # --- CONFIGURATION: Modify settings or profile ---
    # (to be added)
}


def get_family(group_key: str) -> str:
    """Returns the Capability Family for a given group key, or 'UNKNOWN'."""
    for prefix, family in FAMILY_REGISTRY.items():
        if group_key.startswith(prefix):
            return family
    return "UNKNOWN"
