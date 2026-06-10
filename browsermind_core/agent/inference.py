# browsermind_core/agent/inference.py
"""Goal to Flow Inference Engine.

Translates unstructured user goal strings into Flow Domain representations,
supporting both single-flow classification and multi-flow graph decomposition.
"""

class FlowInferenceEngine:
    FLOW_PATTERNS = {
        "AUTH_FLOW": [
            "login", "log in", "signin", "sign in", "logout", "sign out", 
            "forgot password", "lost access", "get into", "cant access", "cant get in",
            "access account", "sign-in", "sign-out", "credentials", "password reset",
            "verify", "verification", "2fa", "otp", "code", "mfa"
        ],
        "SEARCH_FLOW": [
            "find", "search", "lookup", "query", "locate", "seek", "google", 
            "bing", "look up", "retrieve", "looking for", "where is", "show me", "search for"
        ],
        "NAVIGATION_FLOW": [
            "goto", "go to", "navigate", "open link", "click link", "visit", "redirect",
            "open homepage", "home page"
        ],
        "DISCOVERY_FLOW": [
            "read", "discover", "feed", "news", "articles", "latest", "posts", 
            "view feed", "stories", "reviews", "browse"
        ],
        "FILTERING_FLOW": [
            "filter", "sort", "checkbox", "size", "color", "price range", 
            "refine", "category", "under", "cheaper", "above", "range", "cost", "price"
        ],
        "CHECKOUT_FLOW": [
            "checkout", "pay", "buy", "purchase", "order", "cart", "payment", 
            "add to cart", "enroll", "subscribe", "acquire", "obtain", "complete order", "complete purchase"
        ],
        "SETTINGS_FLOW": [
            "settings", "change password", "enable", "disable", "toggle", 
            "configuration", "preferences", "dark mode", "light mode", "billing", 
            "payment details", "configure", "update email", "modify settings"
        ],
        "PROFILE_FLOW": [
            "profile", "update bio", "change profile picture", "edit profile", 
            "registration", "signup", "sign up", "join", "avatar", "bio", 
            "upload photo", "publish", "create account", "profile picture",
            "personalize page", "personalize my page", "about me"
        ]
    }

    # Logical sequence of flows in a standard user journey (Temporal Sequence Grammar)
    TEMPORAL_ORDER = [
        "AUTH_FLOW",
        "SEARCH_FLOW",
        "NAVIGATION_FLOW",
        "FILTERING_FLOW",
        "DISCOVERY_FLOW",
        "CHECKOUT_FLOW",
        "PROFILE_FLOW",
        "SETTINGS_FLOW"
    ]

    def _normalize_text(self, text: str) -> str:
        """Filter out common filler words to match action-verb patterns robustly."""
        text_lower = text.lower()
        fillers = ["my", "the", "a", "an", "to", "for", "in", "from", "on", "with", "into", "again", "our", "your"]
        # Replace punctuation to avoid splitting issues
        for p in [".", ",", "!", "?", "-", "_"]:
            text_lower = text_lower.replace(p, " ")
        words = text_lower.split()
        filtered_words = [w for w in words if w not in fillers]
        return " ".join(filtered_words)

    def infer_flow(self, goal: str) -> tuple[str, float]:
        """Infer Flow Domain and compute normalized confidence for a single intent."""
        goal_normalized = self._normalize_text(goal)
        goal_raw = goal.lower()
        scores = {}
        
        for flow, keywords in self.FLOW_PATTERNS.items():
            score = 0
            for kw in keywords:
                if " " in kw:
                    kw_words = kw.split()
                    if all(w in goal_normalized or w in goal_raw for w in kw_words):
                        score += len(kw)
                else:
                    if kw in goal_normalized or kw in goal_raw:
                        score += len(kw)
            scores[flow] = score
            
        best_flow = max(scores, key=scores.get)
        best_score = scores[best_flow]
        
        if best_score == 0:
            if "http" in goal_raw or "/" in goal_raw:
                return "NAVIGATION_FLOW", 0.5
            return "SEARCH_FLOW", 0.3
            
        total_score = sum(scores.values())
        confidence = best_score / total_score if total_score > 0 else 0.0
        
        return best_flow, round(confidence, 2)

    def infer_flow_graph(self, goal: str) -> list[str]:
        """Decompose a composite goal into a sequential list (Flow Graph) of Flow Domains."""
        goal_normalized = self._normalize_text(goal)
        goal_raw = goal.lower()
        matched = set()
        
        # 1. Direct Action-Verb Keyword Matching
        for flow, keywords in self.FLOW_PATTERNS.items():
            for kw in keywords:
                if " " in kw:
                    kw_words = kw.split()
                    if all(w in goal_normalized or w in goal_raw for w in kw_words):
                        matched.add(flow)
                        break
                else:
                    if kw in goal_normalized or kw in goal_raw:
                        matched.add(flow)
                        break
                    
        # 2. Semantic Rules for Implied Flows
        # Rule A: If PROFILE/SETTINGS are requested and goal refers to user/personal context, Auth is implied
        if ("PROFILE_FLOW" in matched or "SETTINGS_FLOW" in matched) and "AUTH_FLOW" not in matched:
            if any(w in goal.lower() for w in ["my", "login", "account", "credentials", "private", "billing", "profile"]):
                matched.add("AUTH_FLOW")
                
        # Rule B: If SEARCH and CHECKOUT are present, insert intermediate FILTERING/DISCOVERY if appropriate
        if "SEARCH_FLOW" in matched and "CHECKOUT_FLOW" in matched:
            if any(w in goal.lower() for w in ["under", "price", "size", "sort", "filter", "range", "cost", "cheaper"]):
                matched.add("FILTERING_FLOW")
            matched.add("DISCOVERY_FLOW") # bridging product selection
            
        # Rule C: If SEARCH and DISCOVERY are present, but user is looking to buy/enroll, insert CHECKOUT
        if "SEARCH_FLOW" in matched and "DISCOVERY_FLOW" in matched:
            if any(w in goal.lower() for w in ["enroll", "buy", "purchase", "subscribe", "acquire", "obtain", "pay"]):
                matched.add("CHECKOUT_FLOW")
                
        # Rule D: If CHECKOUT_FLOW is present, but SEARCH_FLOW is not:
        # Prepend SEARCH_FLOW and DISCOVERY_FLOW if the goal specifies a target item/product
        if "CHECKOUT_FLOW" in matched and "SEARCH_FLOW" not in matched:
            if any(w in goal.lower() for w in ["laptop", "shirt", "course", "model", "product", "item", "book", "ticket", "card", "billing"]):
                matched.add("SEARCH_FLOW")
                matched.add("DISCOVERY_FLOW")
                
        # 3. Sort according to Temporal Sequence Grammar
        sorted_flows = [flow for flow in self.TEMPORAL_ORDER if flow in matched]
        
        return sorted_flows

    def infer_abstract_requirements(self, goal: str, flows: list[str]) -> list[str]:
        """Infers the abstract challenge evidence classes required by the goal."""
        goal_raw = goal.lower()
        goal_normalized = self._normalize_text(goal)
        abstract_reqs = []

        # 1. Signup challenge evidence
        signup_patterns = [
            ["signup"], ["sign", "up"], ["register"], ["registration"], ["create", "account"], ["join"],
            ["personalize", "page"]
        ]
        is_signup = any(all(w in goal_normalized or w in goal_raw for w in pattern) for pattern in signup_patterns)
        
        # 2. Recovery challenge evidence
        recovery_patterns = [
            ["forgot"], ["lost", "access"], ["reset", "password"], ["locked", "out"]
        ]
        is_recovery = any(all(w in goal_normalized or w in goal_raw for w in pattern) for pattern in recovery_patterns)
        
        # 3. Logout challenge
        logout_patterns = [
            ["logout"], ["sign", "out"]
        ]
        is_logout = any(all(w in goal_normalized or w in goal_raw for w in pattern) for pattern in logout_patterns)

        # Map to abstract challenges
        if is_signup and ("PROFILE_FLOW" in flows or "AUTH_FLOW" in flows):
            abstract_reqs.append("SignupEvidenceRequirement")
        elif is_recovery:
            abstract_reqs.append("RecoveryEvidenceRequirement")
        elif "AUTH_FLOW" in flows and not is_logout:
            abstract_reqs.append("IdentityEvidenceRequirement")

        if ("SETTINGS_FLOW" in flows or "PROFILE_FLOW" in flows) and not is_signup:
            abstract_reqs.append("authenticated_session")
            
        if ("change" in goal_raw or "update" in goal_raw) and "password" in goal_raw and not is_recovery:
            abstract_reqs.append("current_password")

        if "CHECKOUT_FLOW" in flows:
            abstract_reqs.append("PaymentEvidenceRequirement")
            
        if "SEARCH_FLOW" in flows:
            abstract_reqs.append("search_query")
            
        if "NAVIGATION_FLOW" in flows:
            abstract_reqs.append("target_url")
            
        if "FILTERING_FLOW" in flows:
            abstract_reqs.append("filter_criteria")

        return abstract_reqs

    def expand_evidence_requirements(self, goal: str, abstract_reqs: list[str]) -> list[str]:
        """Expands high-level abstract challenge/evidence requirements into concrete system requirements."""
        goal_raw = goal.lower()
        concrete_reqs = []

        for req in abstract_reqs:
            if req == "IdentityEvidenceRequirement":
                # Authentication challenge expansion
                # Does the challenge involve a multi-factor authentication (MFA) evidence check?
                is_mfa_challenge = any(w in goal_raw for w in ["2fa", "otp", "mfa", "verification", "verify", "code"])
                if is_mfa_challenge:
                    concrete_reqs.extend(["credentials", "verification_code"])
                else:
                    concrete_reqs.append("credentials")
            elif req == "RecoveryEvidenceRequirement":
                # Recovery challenge expansion
                concrete_reqs.extend(["email_or_username", "verification_code"])
            elif req == "SignupEvidenceRequirement":
                # Signup challenge expansion
                concrete_reqs.extend(["email", "username", "password"])
            elif req == "PaymentEvidenceRequirement":
                # Payment challenge expansion
                concrete_reqs.extend(["payment_method", "billing_address"])
            else:
                # Standard concrete requirements pass through
                concrete_reqs.append(req)

        return concrete_reqs

    def infer_requirement_candidates(self, goal: str, flows: list[str] = None) -> list[str]:
        """Extract candidate requirements (prerequisites) needed to execute the goal."""
        if flows is None:
            flows = self.infer_flow_graph(goal)
            
        # 1. Infer abstract evidence requirements first (Challenge Ontology)
        abstract_reqs = self.infer_abstract_requirements(goal, flows)
        
        # 2. Expand evidence requirements to concrete requirements (Requirement Expansion layer)
        concrete_reqs = self.expand_evidence_requirements(goal, abstract_reqs)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_reqs = []
        for r in concrete_reqs:
            if r not in seen:
                seen.add(r)
                unique_reqs.append(r)
                
        return unique_reqs

    def infer_goal_state(self, goal: str) -> dict:
        """Infer both the Flow Graph and the candidate execution prerequisites for a goal."""
        flows = self.infer_flow_graph(goal)
        candidates = self.infer_requirement_candidates(goal, flows)
        return {
            "flows": flows,
            "requirement_candidates": candidates
        }
