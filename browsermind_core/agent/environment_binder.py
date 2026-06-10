# browsermind_core/agent/environment_binder.py
"""Environment Binder — Resolves AssetTypes to context-aware user AssetInstances and host Environments."""
from typing import Dict, List, Optional, Set
from browsermind_core.ontology.asset import Persona, AssetOwnership, AssetType, AssetInstance, Environment, AssetGraph, TrustTier


class AmbiguousAssetError(Exception):
    """Raised when multiple asset instances match a requirement and cannot be resolved automatically."""
    def __init__(self, asset_type: str, candidates: List[str]):
        super().__init__(f"Ambiguity detected: Multiple matching assets found for type '{asset_type}': {candidates}")
        self.asset_type = asset_type
        self.candidates = candidates


class EnvironmentBinder:
    """Binds abstract AssetTypes to user-owned AssetInstances and host Environments based on task context."""

    def __init__(self):
        # 1. Active Persona definition
        self.persona = Persona(name="primary_user", description="Default Active Persona")

        # 2. Mapped Environments (Keep very small and metadata-only as requested)
        self.environments: Dict[str, Environment] = {
            "gmail": Environment(id="gmail", kind="email_client", trust_tier=TrustTier.MEDIUM, url="https://mail.google.com", aliases=["gmail", "google mail"]),
            "outlook": Environment(id="outlook", kind="email_client", trust_tier=TrustTier.MEDIUM, url="https://outlook.office.com", aliases=["outlook", "microsoft mail", "work mail"]),
            "proton": Environment(id="proton", kind="email_client", trust_tier=TrustTier.MEDIUM, url="https://mail.proton.me", aliases=["proton", "protonmail"]),
            "credential_vault": Environment(id="credential_vault", kind="secrets_manager", trust_tier=TrustTier.HIGH, aliases=["vault", "credential vault", "secure vault", "local vault"]),
            "onepassword": Environment(id="onepassword", kind="secrets_manager", trust_tier=TrustTier.HIGH, url="https://1password.com", aliases=["onepassword", "1password", "otp generator", "authenticator"]),
            "stripe_wallet": Environment(id="stripe_wallet", kind="wallet", trust_tier=TrustTier.HIGH, url="https://stripe.com", aliases=["stripe", "wallet", "payment provider"]),
            "local_profile": Environment(id="local_profile", kind="profile_manager", trust_tier=TrustTier.LOW, aliases=["profile", "local settings"]),
            "user_prompt": Environment(id="user_prompt", kind="context_bridge", trust_tier=TrustTier.LOW, aliases=["prompt", "input context"])
        }

        # Multi-tenant asset instances owned by user Persona
        self.assets_registry: Dict[str, List[AssetInstance]] = {
            "session_token": [
                AssetInstance(name="session_active", asset_type="session_token", environment="local_profile", description="Active Session Tokens", canonical_name="Active Session Token", aliases=["session", "active session"])
            ],
            "email_account": [
                AssetInstance(name="outlook_work", asset_type="email_account", environment="outlook", description="Work Outlook Account", canonical_name="Work Outlook Account", aliases=["work email", "outlook", "office email"]),
                AssetInstance(name="proton_secure", asset_type="email_account", environment="proton", description="Secure Proton Mail Account", canonical_name="Secure Proton Mail Account", aliases=["proton", "protonmail", "secure email"]),
                AssetInstance(name="gmail_primary", asset_type="email_account", environment="gmail", description="Primary Personal Gmail Account", canonical_name="Primary Personal Gmail Account", aliases=["gmail", "personal email", "private mail", "email portal"])
            ],
            "credential_asset": [
                AssetInstance(name="1password_work", asset_type="credential_asset", environment="onepassword", description="Corporate Password Vault", canonical_name="Corporate Password Vault", aliases=["onepassword", "1password", "otp", "work vault"]),
                AssetInstance(name="vault_local", asset_type="credential_asset", environment="credential_vault", description="Local Secure Vault", canonical_name="Local Secure Vault", aliases=["vault", "credential vault", "credentials", "local vault"])
            ],
            "payment_asset": [
                AssetInstance(name="amex_corporate", asset_type="payment_asset", environment="stripe_wallet", description="Amex Corporate Credit Card", canonical_name="Amex Corporate Card", aliases=["corporate card", "business card", "amex"]),
                AssetInstance(name="visa_personal", asset_type="payment_asset", environment="stripe_wallet", description="Personal Visa Credit Card", canonical_name="Personal Visa Card", aliases=["personal card", "personal visa", "private card"])
            ],
            "identity_profile": [
                AssetInstance(name="profile_personal", asset_type="identity_profile", environment="local_profile", description="Personal Profile Data", canonical_name="Personal Profile Data", aliases=["profile", "personal bio"])
            ],
            "goal_context": [
                AssetInstance(name="goal_parameters", asset_type="goal_context", environment="user_prompt", description="Task input parameter context", canonical_name="Goal Context Parameters", aliases=["goal", "parameters", "context"])
            ]
        }

        # 3. Define Persona Inventory with tags and explicit AssetOwnership relations
        self.inventory: List[Dict] = [
            # Sessions
            {
                "instance": AssetInstance(name="session_active", asset_type="session_token", environment="local_profile", description="Active Session Tokens", canonical_name="Active Session Token", aliases=["session", "active session"]),
                "tags": ["personal", "session", "login", "auth", "secure"]
            },
            # Email accounts
            {
                "instance": AssetInstance(name="gmail_primary", asset_type="email_account", environment="gmail", description="Primary Personal Gmail Account", canonical_name="Primary Personal Gmail Account", aliases=["gmail", "personal email", "private mail", "email portal"]),
                "tags": ["personal", "inbox", "gmail", "private"]
            },
            {
                "instance": AssetInstance(name="gmail_school", asset_type="email_account", environment="gmail", description="University Student Email Account", canonical_name="University Student Email Account", aliases=["student email", "school email", "edu mail"]),
                "tags": ["school", "university", "edu", "college", "student", "class"]
            },
            {
                "instance": AssetInstance(name="outlook_work", asset_type="email_account", environment="outlook", description="Work Outlook Account", canonical_name="Work Outlook Account", aliases=["work email", "outlook", "office email"]),
                "tags": ["work", "company", "office", "corporate", "job", "employer", "outlook"]
            },
            # Credential vaults
            {
                "instance": AssetInstance(name="1password_work", asset_type="credential_asset", environment="onepassword", description="Corporate Password Vault", canonical_name="Corporate Password Vault", aliases=["onepassword", "1password", "otp", "work vault"]),
                "tags": ["work", "company", "corporate", "onepassword", "office"]
            },
            {
                "instance": AssetInstance(name="vault_local", asset_type="credential_asset", environment="credential_vault", description="Local Secure Vault", canonical_name="Local Secure Vault", aliases=["vault", "credential vault", "credentials", "local vault"]),
                "tags": ["personal", "local", "secure", "private", "personal"]
            },
            # Payment assets
            {
                "instance": AssetInstance(name="amex_corporate", asset_type="payment_asset", environment="stripe_wallet", description="Amex Corporate Credit Card", canonical_name="Amex Corporate Card", aliases=["corporate card", "business card", "amex"]),
                "tags": ["work", "company", "corporate", "amex", "business"]
            },
            {
                "instance": AssetInstance(name="visa_personal", asset_type="payment_asset", environment="stripe_wallet", description="Personal Visa Credit Card", canonical_name="Personal Visa Card", aliases=["personal card", "personal visa", "private card"]),
                "tags": ["personal", "visa", "private", "card"]
            },
            # Identity Profiles
            {
                "instance": AssetInstance(name="profile_personal", asset_type="identity_profile", environment="local_profile", description="Personal Profile Data", canonical_name="Personal Profile Data", aliases=["profile", "personal bio"]),
                "tags": ["personal", "profile", "bio", "avatar"]
            },
            # Goal Contexts
            {
                "instance": AssetInstance(name="goal_parameters", asset_type="goal_context", environment="user_prompt", description="Task input parameter context", canonical_name="Goal Context Parameters", aliases=["goal", "parameters", "context"]),
                "tags": ["search", "navigation", "url", "filter"]
            }
        ]

        # Populate explicit ownership links
        self.ownerships: List[AssetOwnership] = [
            AssetOwnership(persona_name=self.persona.name, asset_instance_name=item["instance"].name)
            for item in self.inventory
        ]

    def _select_instance(self, asset_type: str, goal: str) -> AssetInstance:
        """Finds instances matching the AssetType and applies a context-matching policy, raising error on ambiguity."""
        goal_lower = goal.lower()
        import json
        import sys
        
        # 1. Filter inventory by AssetType
        candidates = [item for item in self.inventory if item["instance"].asset_type == asset_type]
        if not candidates:
            raise Exception(f"No asset instances registered in inventory for type '{asset_type}'.")
            
        if len(candidates) == 1:
            return candidates[0]["instance"]
            
        # 2. Score candidates by matching tags, name/canonical_name, aliases, environment and env aliases in user goal
        matches = []
        for c in candidates:
            instance = c["instance"]
            
            # Identity Match: candidate's name or canonical name (weight: 5)
            identity_score = 0
            instance_names = [instance.name.lower(), instance.canonical_name.lower()]
            for name in instance_names:
                if name and name in goal_lower:
                    identity_score = 5
                    break
            
            # Alias Match: candidate's aliases (weight: 5)
            alias_score = 0
            instance_aliases = [a.lower() for a in getattr(instance, "aliases", [])]
            for alias in instance_aliases:
                if alias in goal_lower:
                    alias_score = 5
                    break
                    
            # Tag Match: tags associated with the asset instance (weight: 1 per match)
            tag_score = 0
            for t in c["tags"]:
                if t in goal_lower:
                    tag_score += 1
                    
            # Environment Match: environment ID and its aliases (weight: 3)
            env_score = 0
            env_id = instance.environment.lower()
            env_obj = self.environments.get(instance.environment)
            env_aliases = [env_id] + [a.lower() for a in getattr(env_obj, "aliases", [])] if env_obj else [env_id]
            for alias in env_aliases:
                if alias in goal_lower:
                    env_score = 3
                    break
                    
            total = identity_score + alias_score + tag_score + env_score
            
            # Print audit breakdown to stderr
            breakdown = {
                "candidate": instance.name,
                "identity_score": identity_score,
                "alias_score": alias_score,
                "tag_score": tag_score,
                "environment_score": env_score,
                "total": total
            }
            print(f"[BINDER AUDIT] {json.dumps(breakdown)}", file=sys.stderr)
            
            if total > 0:
                matches.append((instance, total))
                
        # 3. Apply Selection Policy
        if len(matches) == 1:
            return matches[0][0]
        elif len(matches) > 1:
            # Sort by score descending
            matches.sort(key=lambda x: x[1], reverse=True)
            if matches[0][1] > matches[1][1]:
                return matches[0][0]
            # Otherwise, it's ambiguous among the matched ones
            raise AmbiguousAssetError(asset_type, [m[0].name for m in matches])
        else:
            # No contextual evidence was available. Do not silently choose a
            # personal/primary asset; that turns ambiguity into hidden policy.
            raise AmbiguousAssetError(asset_type, [c["instance"].name for c in candidates])

    def bind_graph(self, graph: AssetGraph, goal: str) -> AssetGraph:
        """Finds AssetType nodes and binds them to specific AssetInstances and host Environments."""
        asset_type_nodes = [
            node_name for node_name, node_data in graph.nodes.items()
            if node_data["type"] == "AssetType"
        ]
        
        # Add Persona node to represent ownership
        graph.add_node(self.persona.name, "Persona", {
            "description": self.persona.description
        })
        
        # Standard execution context (user prompt / goal parameters)
        graph.add_node("goal_context", "AssetType", {"description": "Task input parameter context"})
        graph.add_node("goal_parameters", "AssetInstance", {
            "asset_type": "goal_context",
            "environment": "user_prompt",
            "description": "Task input parameter context"
        })
        graph.add_edge("goal_context", "goal_parameters", "bound_to")
        graph.add_edge(self.persona.name, "goal_parameters", "owns")
        
        graph.add_node("user_prompt", "Environment", {
            "kind": "context_bridge",
            "description": "Task input parameter context"
        })
        graph.add_edge("goal_parameters", "user_prompt", "hosted_in")
        
        for asset_type_name in asset_type_nodes:
            # 1. Selection of context-aware Instance (raises AmbiguousAssetError on ambiguity)
            try:
                instance = self._select_instance(asset_type_name, goal)
                graph.add_node(instance.name, "AssetInstance", {
                    "asset_type": instance.asset_type,
                    "environment": instance.environment,
                    "description": instance.description
                })
                graph.add_edge(asset_type_name, instance.name, "bound_to")
                
                # Add explicit ownership relation edge
                graph.add_edge(self.persona.name, instance.name, "owns")
                
                # 2. Selection of host Environment
                env = self.environments.get(instance.environment)
                if env:
                    graph.add_node(env.id, "Environment", {
                        "kind": env.kind,
                        "trust_tier": env.trust_tier,
                        "url": env.url,
                        "description": env.description
                    })
                    graph.add_edge(instance.name, env.id, "hosted_in")
            except AmbiguousAssetError as e:
                unresolved_node_name = f"UNRESOLVED_{asset_type_name}"
                graph.add_node(unresolved_node_name, "UNRESOLVED", {
                    "status": "ambiguous",
                    "candidates": e.candidates,
                    "asset_type": asset_type_name
                })
                graph.add_edge(asset_type_name, unresolved_node_name, "bound_to")
                raise

        return graph
