# browsermind_core/agent/capability_discovery.py
"""Capability Discovery — Maps Environments to their baseline and override execution Capabilities."""
from typing import Dict, List, Optional
from browsermind_core.ontology.asset import Capability, AssetGraph


class CapabilityDiscoveryEngine:
    """Discovers and binds Environment capabilities in the AssetGraph."""

    def __init__(self):
        # 1. Baseline capabilities associated with each environment kind
        self.baseline_capabilities: Dict[str, List[Capability]] = {
            "email_client": [
                Capability(
                    name="search_email",
                    description="Search user inbox for emails matching specific queries.",
                    inputs=["email_account", "query"],
                    outputs=["email_id"],
                    consumes_state=[],
                    produces_state=["email.selected"]
                ),
                Capability(
                    name="read_email",
                    description="Read contents of incoming emails to retrieve message content.",
                    inputs=["email_account", "email_id"],
                    outputs=["email_content"],
                    consumes_state=["email.selected"],
                    produces_state=["email.opened"]
                )
            ],
            "secrets_manager": [
                Capability(
                    name="retrieve_credential",
                    description="Fetch stored usernames and passwords securely from vault.",
                    inputs=["credential_asset"],
                    outputs=["username", "password"],
                    consumes_state=[],
                    produces_state=["vault.credentials_unlocked"]
                )
            ],
            "wallet": [
                Capability(
                    name="charge_payment",
                    description="Process card payment transaction or billing checkout.",
                    inputs=["payment_asset"],
                    outputs=["receipt_id", "payment_status"],
                    consumes_state=[],
                    produces_state=["checkout.payment_processed"]
                ),
                Capability(
                    name="read_billing_info",
                    description="Read stored billing address and card metadata from the wallet.",
                    inputs=["payment_asset"],
                    outputs=["billing_info"],
                    consumes_state=[],
                    produces_state=["wallet.billing_info_loaded"]
                )
            ],
            "profile_manager": [
                Capability(
                    name="read_profile",
                    description="Retrieve user personal profile data, addresses, or bio metadata.",
                    inputs=["identity_profile"],
                    outputs=["profile_data"],
                    consumes_state=[],
                    produces_state=["profile.loaded"]
                )
            ],
            "context_bridge": [
                Capability(
                    name="read_context",
                    description="Resolve dynamic search queries and custom target URLs from goal context.",
                    inputs=["goal_context"],
                    outputs=["query_parameters"],
                    consumes_state=[],
                    produces_state=["context.resolved"]
                )
            ]
        }

        # 2. Environment-specific overrides (Gmail-specific features, 1Password-specific features, etc.)
        self.overrides: Dict[str, List[Capability]] = {
            "gmail": [
                Capability(
                    name="manage_labels",
                    description="Gmail-specific feature to manage custom labels or categories.",
                    inputs=["email_account"],
                    outputs=["label_status"],
                    consumes_state=["email.selected"],
                    produces_state=["email.label_managed"]
                )
            ],
            "outlook": [
                Capability(
                    name="manage_folders",
                    description="Outlook-specific folder organizational capability.",
                    inputs=["email_account"],
                    outputs=["folder_status"],
                    consumes_state=["email.selected"],
                    produces_state=["email.folder_managed"]
                )
            ],
            "onepassword": [
                Capability(
                    name="generate_otp",
                    description="1Password capability to generate one-time-password (OTP) codes.",
                    inputs=["credential_asset"],
                    outputs=["one_time_password"],
                    consumes_state=["vault.credentials_unlocked"],
                    produces_state=["vault.otp_generated"]
                )
            ],
            "credential_vault": [
                Capability(
                    name="generate_otp",
                    description="Vault capability to generate one-time-password (OTP) codes.",
                    inputs=["credential_asset"],
                    outputs=["one_time_password"],
                    consumes_state=["vault.credentials_unlocked"],
                    produces_state=["vault.otp_generated"]
                )
            ]
        }

    def discover_capabilities(self, env_id: str, env_kind: str) -> List[Capability]:
        """Discovers capabilities for a specific environment by merging baseline kind capabilities and specific overrides."""
        # Start with baseline capabilities for the environment kind
        capabilities = list(self.baseline_capabilities.get(env_kind, []))
        
        # Merge overrides if specific to this environment ID
        if env_id in self.overrides:
            capabilities.extend(self.overrides[env_id])
            
        return capabilities

    def bind_capabilities(self, graph: AssetGraph) -> AssetGraph:
        """Finds Environment nodes in the AssetGraph, discovers their Capabilities (baseline + overrides), and binds them."""
        env_nodes = [
            node_name for node_name, node_data in graph.nodes.items()
            if node_data["type"] == "Environment"
        ]

        for env_name in env_nodes:
            metadata = graph.nodes[env_name].get("metadata", {})
            env_kind = metadata.get("kind")
            if not env_kind:
                continue

            # Discover utilizing env_name (id) and env_kind
            caps = self.discover_capabilities(env_name, env_kind)
            for cap in caps:
                # Add Capability node
                graph.add_node(cap.name, "Capability", {
                    "inputs": cap.inputs,
                    "outputs": cap.outputs,
                    "consumes_state": cap.consumes_state,
                    "produces_state": cap.produces_state,
                    "description": cap.description
                })
                # Add relationship: Environment supports Capability
                graph.add_edge(env_name, cap.name, "supports")

        return graph
