"""TargetResolver — Translates semantic steps into Playwright Locators.

P4E: Introduces AmbiguousIdentityError when multiple candidates share the same
role+name. Structural path fallback is no longer triggered in that case —
the system honestly admits it cannot uniquely identify the target.

WR-IR Phase 1: Depth 4b capability_intent — selector-based functional fallback.
WR-IR Phase 2: Depth 4a affordance_intent — page-state-based intent resolution.
               Returns ResolutionResult instead of tuple; execution delegated
               to AffordanceExecutor in ReplayEngine.
"""
import os
from typing import Optional, Tuple, Dict, Any, List
from playwright.async_api import Page, Locator
from browsermind_core.recorder.capability_classifier import CAPABILITY_SELECTORS
from browsermind_core.runtime.affordance import Affordance, ResolutionResult
from browsermind_core.runtime.affordance_discoverer import AffordanceDiscoverer, best_affordance
from browsermind_core.runtime.intent_family import IntentFamily, IntentFamilyMapper
from browsermind_core.memory.memory_reader import MemoryReader


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TargetResolutionError(Exception):
    """Raised when zero candidates match role+name and all fallbacks are exhausted."""
    pass


class AmbiguousIdentityError(Exception):
    """Raised when >1 candidates share the same role+name.

    This is *not* a resolution failure — it is an identity failure.
    The element exists, but the system cannot determine *which one* the
    user intended without additional identity signals.
    """
    def __init__(self, role: str, name: str, candidate_count: int, candidates_info: List[Dict] = None):
        self.role = role
        self.name = name
        self.candidate_count = candidate_count
        self.candidates_info = candidates_info or []
        super().__init__(
            f"AMBIGUOUS_IDENTITY: {candidate_count} elements share role='{role}', name='{name}'. "
            f"Cannot uniquely identify target without additional identity signals."
        )


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

class TargetResolver:
    """
    WR-2, WR-3, & WR-4: Robust Target Resolver & Fallback Recovery.

    Resolution hierarchy:
      1. Exact Selector: CSS/XPath selector matching (exact target_selector)
      2. Primary Semantic: exact role + name, count=1
      3. Semantic + Container: role + name nested within container_label/data-test
      4. Loose Semantic: fuzzy role + name
      5. Recovery Track:
         - P4B Memory Prior (historically successful strategy for this persona)
         - Placeholder fallback
         - Nearby text fallback
         - Structural DOM Path
         - Affordance Intent (Intent-based discovery via state space)
         - Capability Intent (Selector-based functionality guess)
    """

    CONFIDENCE_MAP = {
        "exact_selector":     1.0,
        "primary_semantic":   1.0,
        "loose_semantic":     0.8,
        "semantic+container": 0.85,
        "placeholder":        0.7,
        "nearby_text":        0.5,
        "structural_path":    0.1,
        "capability_intent":  0.4,   # WR-IR: functional type + ordinal
        "virtual_list":       0.6,   # R7: scroll-to-render on virtualized grids
        "ambiguous":          0.0,
    }

    def __init__(self, page: Page, env_key: Optional[str] = None, persona_id: str = "default", lesson_reader=None, behavior_audit=None, recovery_registry=None):
        self.page = page
        self.env_key = env_key
        self.persona_id = persona_id
        self._memory_reader = MemoryReader(persona_id=persona_id)
        self._lesson_reader = lesson_reader
        self._behavior_audit = behavior_audit
        self._recovery_registry = recovery_registry

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _find_unique_locator(self, query_fn, descriptor=None, wait_timeout=0) -> Tuple[Optional[Locator], int]:
        """Search all frames in the page. If exactly one frame contains the target, return it."""
        total_count = 0
        matching_locators = []
        for frame in self.page.frames:
            try:
                candidate = query_fn(frame)
                if wait_timeout > 0:
                    try:
                        await candidate.first.wait_for(state="attached", timeout=wait_timeout)
                    except Exception:
                        pass
                count = await candidate.count()
                if count > 0:
                    total_count += count
                    matching_locators.append(candidate)
            except Exception:
                pass
        if len(matching_locators) == 1:
            loc = matching_locators[0]
            count = await loc.count()
            if count == 1:
                return loc, 1
            elif count > 1:
                resolved = await self._resolve_ambiguity(loc, descriptor)
                if resolved:
                    return resolved, count
        return None, total_count

    async def _count_candidates(self, role: str, name: str, exact: bool = True) -> int:
        """Return raw candidate count for role+name across all frames (no filtering)."""
        total = 0
        for frame in self.page.frames:
            try:
                candidate = frame.get_by_role(role, name=name, exact=exact)
                total += await candidate.count()
            except Exception:
                pass
        return total

    async def _try_resolve(
        self,
        role: str,
        name: str,
        exact: bool = True,
        descriptor: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[Locator], int]:
        """
        Try to resolve a unique element by role+name across all frames.
        Returns (locator_or_None, raw_candidate_count).
        """
        if not role or not name:
            return None, 0
        timeout = 1000 if exact else 0
        return await self._find_unique_locator(
            lambda r: r.get_by_role(role, name=name, exact=exact),
            descriptor=descriptor or {},
            wait_timeout=timeout,
        )

    async def _collect_candidates_info(self, role: str, name: str, exact: bool = False) -> List[Dict]:
        """
        For Identity Forensics: collect rich info about every ambiguous candidate across all frames.
        """
        info = []
        for frame in self.page.frames:
            try:
                candidates = frame.get_by_role(role, name=name, exact=exact)
                count = await candidates.count()
                for i in range(min(count, 20)):
                    el = candidates.nth(i)
                    try:
                        tag = await el.evaluate("el => el.tagName.toLowerCase()")
                        text = await el.evaluate("el => (el.innerText || el.textContent || '').trim().substring(0, 80)")
                        parent_text = await el.evaluate("""el => {
                            let p = el.parentElement;
                            for (let i = 0; i < 4 && p; i++, p = p.parentElement) {
                                const h = p.querySelector('h1,h2,h3,h4,[data-test*="name"],[class*="title"],[class*="name"]');
                                if (h) return h.innerText.trim().substring(0, 80);
                            }
                            return null;
                        }""")
                        nearest_heading = await el.evaluate("""el => {
                            let p = el.closest('[data-test]');
                            return p ? p.getAttribute('data-test') : null;
                        }""")
                        info.append({
                            "index": len(info),
                            "role": role,
                            "name": name,
                            "tag": tag,
                            "text": text,
                            "nearest_container_label": parent_text,
                            "data_test_ancestor": nearest_heading,
                            "position_in_collection": len(info) + 1,
                        })
                    except Exception:
                        info.append({"index": len(info), "role": role, "name": name, "error": "inspect_failed"})
            except Exception:
                pass
        return info

    async def _resolve_ambiguity(self, candidates: Locator, descriptor: Dict[str, Any]) -> Optional[Locator]:
        """
        WR-4 Deterministic Ambiguity Resolution.
        Applies visibility filters, container proximity filters, and semantic signature scoring.
        """
        descriptor = descriptor or {}
        count = await candidates.count()
        if count == 0:
            return None
        if count == 1:
            return candidates

        # 1. Visibility filter
        visible_candidates = []
        for i in range(count):
            c = candidates.nth(i)
            try:
                if await c.is_visible():
                    visible_candidates.append(c)
            except Exception:
                pass
        
        if len(visible_candidates) == 1:
            return visible_candidates[0]
            
        active_candidates = visible_candidates if visible_candidates else [candidates.nth(i) for i in range(count)]
        
        # 2. Container Proximity Filter
        container_label = descriptor.get("container_label")
        container_dt = descriptor.get("container_data_test")
        
        if container_label or container_dt:
            nested_candidates = []
            for c in active_candidates:
                try:
                    is_match = await c.evaluate("""(el, args) => {
                        const [label, dt] = args;
                        let p = el.parentElement;
                        for (let i = 0; i < 6 && p && p !== document.body; i++, p = p.parentElement) {
                            if (dt && p.getAttribute('data-test') === dt) return true;
                            if (label && p.innerText && p.innerText.includes(label)) return true;
                        }
                        return false;
                    }""", [container_label or "", container_dt or ""])
                    if is_match:
                        nested_candidates.append(c)
                except Exception:
                    pass
            if len(nested_candidates) == 1:
                return nested_candidates[0]
            if len(nested_candidates) > 1:
                active_candidates = nested_candidates

        # 3. Semantic Signature Similarity scoring (Deterministic)
        best_cand = None
        best_score = -1
        second_best_score = -1
        
        expected_role = descriptor.get("role") or ""
        expected_name = descriptor.get("accessible_name") or descriptor.get("name") or ""
        expected_text = descriptor.get("text_content") or ""
        expected_placeholder = descriptor.get("placeholder") or ""
        
        for c in active_candidates:
            try:
                score = await c.evaluate("""(el, args) => {
                    const [expRole, expName, expText, expPlaceholder] = args;
                    let s = 0;
                    // Tag / role similarity
                    const role = (el.getAttribute('role') || el.tagName || '').toLowerCase();
                    if (expRole && role.includes(expRole.toLowerCase())) s += 2;
                    
                    // Name / aria-label / title similarity
                    const name = (el.getAttribute('aria-label') || el.title || el.innerText || el.value || '').toLowerCase();
                    const expNameLower = expName.toLowerCase();
                    if (expNameLower && name.includes(expNameLower)) s += 2;
                    if (expNameLower && expNameLower.includes(name) && name.length > 2) s += 1;
                    
                    // Text content similarity
                    const text = (el.innerText || el.textContent || '').toLowerCase();
                    const expTextLower = expText.toLowerCase();
                    if (expTextLower && text.includes(expTextLower)) s += 1;
                    
                    // Placeholder similarity
                    const placeholder = (el.getAttribute('placeholder') || '').toLowerCase();
                    if (expPlaceholder && placeholder.includes(expPlaceholder.toLowerCase())) s += 2;
                    
                    return s;
                }""", [expected_role, expected_name, expected_text, expected_placeholder])
                
                if score > best_score:
                    second_best_score = best_score
                    best_score = score
                    best_cand = c
                elif score > second_best_score:
                    second_best_score = score
            except Exception:
                pass
                
        # If there's a clear winner (score difference >= 2)
        if best_cand and (best_score - second_best_score >= 2):
            return best_cand
            
        return None

    async def _try_container_label(self, role: str, name: str, container_label: str, exact: bool = False) -> Tuple[Optional[Locator], int]:
        """Filter candidates by checking if an ancestor contains the container_label across all frames."""
        if not container_label:
            return None, 0
        total_count = 0
        matching_candidates = []
        for frame in self.page.frames:
            try:
                candidates = frame.get_by_role(role, name=name, exact=exact)
                count = await candidates.count()
                for i in range(count):
                    candidate = candidates.nth(i)
                    is_near = await candidate.evaluate("""(el, label) => {
                        let p = el.parentElement;
                        for (let i = 0; i < 6 && p && p !== document.body; i++, p = p.parentElement) {
                            if (p.innerText && p.innerText.includes(label)) {
                                return true;
                            }
                        }
                        return false;
                    }""", container_label)
                    if is_near:
                        matching_candidates.append(candidate)
                        total_count += 1
            except Exception:
                pass
        if len(matching_candidates) == 1:
            return matching_candidates[0], 1
        return None, total_count

    async def _try_placeholder(self, placeholder: str, descriptor: Dict[str, Any]) -> Optional[Locator]:
        if not placeholder:
            return None
        loc, count = await self._find_unique_locator(
            lambda r: r.get_by_placeholder(placeholder),
            descriptor=descriptor
        )
        return loc

    async def _try_text(self, text: str, descriptor: Dict[str, Any]) -> Optional[Locator]:
        if not text:
            return None
        loc, count = await self._find_unique_locator(
            lambda r: r.get_by_text(text),
            descriptor=descriptor
        )
        return loc

    async def _try_find_container(self, descriptor: Dict[str, Any]) -> Optional[Locator]:
        """Try to locate the parent container element across all frames."""
        container_dt = descriptor.get("container_data_test")
        container_label = descriptor.get("container_label")
        
        for frame in self.page.frames:
            if container_dt:
                try:
                    container = frame.locator(f"[data-test='{container_dt}']")
                    if await container.count() == 1:
                        return container
                except Exception:
                    pass
            if container_label:
                try:
                    container = frame.get_by_text(container_label)
                    if await container.count() == 1:
                        return container
                except Exception:
                    pass
        return None

    # ------------------------------------------------------------------
    # Recovery ladder dispatcher (Phase 8 of R6 v1)
    # ------------------------------------------------------------------

    async def _dispatch_recovery_strategy(
        self,
        strategy,
        descriptor: Dict[str, Any],
        target_role: str,
        target_name: str,
        target_selector: str,
    ) -> Optional[ResolutionResult]:
        """Reproduce each builtin's exact original behavior; for `mined`
        rows defer to PRIMITIVE_LIBRARY. Returns ResolutionResult on hit,
        None on miss (caller continues to next ladder row)."""
        primitive = strategy.primitive

        # ---- BUILTIN BRANCHES ------------------------------------------------
        # Each branch below is a 1:1 port of the original R1-R5b code so the
        # seeded ladder is observationally identical to the hardcoded version.

        if primitive == "container_proximity":
            container = await self._try_find_container(descriptor)
            if not container:
                return None
            try:
                if target_selector:
                    cand = container.locator(target_selector)
                    if await cand.count() == 1:
                        return ResolutionResult.from_locator(
                            cand, "exact_selector",
                            recovered_by="container_proximity",
                            depth=strategy.depth, candidate_count=1,
                        )
                cand = container.get_by_role(target_role, name=target_name, exact=False)
                if await cand.count() == 1:
                    return ResolutionResult.from_locator(
                        cand, "loose_semantic",
                        recovered_by="container_proximity",
                        depth=strategy.depth, candidate_count=1,
                    )
                if await cand.count() > 1:
                    resolved = await self._resolve_ambiguity(cand, descriptor)
                    if resolved:
                        return ResolutionResult.from_locator(
                            resolved, "loose_semantic",
                            recovered_by="container_proximity",
                            depth=strategy.depth, candidate_count=1,
                        )
            except Exception:
                return None
            return None

        if primitive == "by_placeholder":
            ph = descriptor.get("placeholder")
            if not ph:
                return None
            loc = await self._try_placeholder(ph, descriptor)
            if loc:
                return ResolutionResult.from_locator(
                    loc, "placeholder", recovered_by="placeholder",
                    depth=strategy.depth, candidate_count=1,
                )
            return None

        if primitive == "by_text_accessible":
            an = descriptor.get("accessible_name")
            if not an:
                return None
            loc = await self._try_text(an, descriptor)
            if loc:
                return ResolutionResult.from_locator(
                    loc, "nearby_text", recovered_by="accessible_name",
                    depth=strategy.depth, candidate_count=1,
                )
            return None

        if primitive == "by_text_content":
            tc = descriptor.get("text_content")
            if not tc:
                return None
            loc = await self._try_text(tc, descriptor)
            if loc:
                return ResolutionResult.from_locator(
                    loc, "nearby_text", recovered_by="nearby_text",
                    depth=strategy.depth, candidate_count=1,
                )
            return None

        if primitive == "structural_with_ambiguity":
            dom_path = descriptor.get("dom_path")
            if not dom_path:
                return None
            try:
                cand = self.page.locator(dom_path)
                count = await cand.count()
                print(f"[DEBUG TRACK] R4 structural_path count={count}")
                if count == 1:
                    return ResolutionResult.from_locator(
                        cand, "structural_path", recovered_by="structural_path",
                        depth=strategy.depth, candidate_count=1,
                    )
                if count > 1:
                    resolved = await self._resolve_ambiguity(cand, descriptor)
                    if resolved:
                        return ResolutionResult.from_locator(
                            resolved, "structural_path", recovered_by="structural_path",
                            depth=strategy.depth, candidate_count=count,
                        )
            except Exception as e:
                print(f"[DEBUG TRACK] R4 Exception: {e}")
                return None
            return None

        if primitive == "affordance_intent":
            family = IntentFamilyMapper.map(descriptor)
            cap_hint = descriptor.get("capability_hint") or ""
            is_input_target = cap_hint.endswith("_input")
            print(f"[DEBUG TRACK] R5a Affordance: family={family}, is_input={is_input_target}")
            if family == IntentFamily.UNKNOWN or is_input_target:
                return None
            try:
                discoverer = AffordanceDiscoverer()
                affordances = await discoverer.discover(self.page, family)
                aff = best_affordance(affordances, min_score=0.5)
                if aff:
                    return ResolutionResult.from_affordance(aff, depth=strategy.depth)
            except Exception as e:
                print(f"[DEBUG TRACK] R5a Exception: {e}")
                return None
            return None

        if primitive == "by_capability":
            print("[DEBUG TRACK] Reached R5b")
            cap_loc = await self._resolve_by_capability(descriptor)
            if cap_loc:
                return ResolutionResult.from_locator(
                    cap_loc, "capability_intent", recovered_by="capability_intent",
                    depth=strategy.depth, candidate_count=1,
                )
            return None

        # ---- MINED STRATEGY DISPATCH ----------------------------------------
        # Delegate to PRIMITIVE_LIBRARY; the resolver loans `self` so library
        # primitives can reuse the existing helpers (_try_text etc.).
        try:
            from browsermind_core.runtime.primitive_library import get_primitive
        except Exception:
            return None
        fn = get_primitive(primitive)
        if fn is None:
            return None
        try:
            loc = await fn(self.page, descriptor, resolver=self)
        except Exception:
            return None
        if loc is None:
            return None
        try:
            if await loc.count() != 1:
                return None
        except Exception:
            return None
        return ResolutionResult.from_locator(
            loc, strategy.name,
            recovered_by=f"mined:{strategy.candidate_id or strategy.name}",
            depth=strategy.depth, candidate_count=1,
        )

    # ------------------------------------------------------------------
    # BC strategy dispatch
    # ------------------------------------------------------------------

    async def _dispatch_bc_strategy(
        self,
        strategy_label: str,
        descriptor: Dict[str, Any],
        target_role: str,
        target_name: str,
        target_selector: str,
    ):
        """Try a single resolution strategy predicted by BC model. Returns ResolutionResult or None."""
        loc = None
        label = None
        if strategy_label == "exact_selector" and target_selector:
            cand = self.page.locator(target_selector)
            if await cand.count() == 1:
                loc, label = cand, "exact_selector"
        elif strategy_label == "primary_semantic":
            cand_loc, count = await self._try_resolve(target_role, target_name, exact=True, descriptor=descriptor)
            if cand_loc:
                loc, label = cand_loc, "primary_semantic"
        elif strategy_label in ("loose_semantic", "semantic+container"):
            cand_loc, count = await self._try_resolve(target_role, target_name, exact=False, descriptor=descriptor)
            if cand_loc:
                loc, label = cand_loc, strategy_label
        elif strategy_label == "placeholder":
            ph = descriptor.get("placeholder")
            if ph:
                cand = await self._try_placeholder(ph, descriptor)
                if cand:
                    loc, label = cand, "placeholder"
        elif strategy_label == "nearby_text":
            tc = descriptor.get("text_content") or descriptor.get("accessible_name")
            if tc:
                cand = await self._try_text(tc, descriptor)
                if cand:
                    loc, label = cand, "nearby_text"
        elif strategy_label == "structural_path":
            dp = descriptor.get("dom_path")
            if dp:
                cand = self.page.locator(dp)
                if await cand.count() == 1:
                    loc, label = cand, "structural_path"
        elif strategy_label == "capability_intent":
            if descriptor.get("capability_hint"):
                cand = await self._resolve_by_capability(descriptor)
                if cand:
                    loc, label = cand, "capability_intent"
        if loc is None or label is None:
            return None
        return ResolutionResult.from_locator(
            loc, label,
            recovered_by=f"bc_prior:{strategy_label}",
            depth=0, candidate_count=1,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def resolve(
        self,
        target_role: str,
        target_name: str,
        target_selector: str,
        descriptor: Dict[str, Any] = None,
        enable_recovery: bool = True,
        step: Optional[Dict[str, Any]] = None,
        prior_belief=None,
    ) -> ResolutionResult:
        """
        Attempt to resolve a target on the page.

        Args:
            prior_belief: Optional StepBelief derived from the previous step's
                          outcome. When set, adjust_strategy_order() reorders the
                          recovery ladder before dispatching. None = no-op (default
                          behaviour unchanged). See execution_belief.py.

        Returns:
            ResolutionResult — mode="locator", "affordance", "skipped", or "failed"

        Raises:
            AmbiguousIdentityError  — when count > 1 and no unique resolution possible
            TargetResolutionError   — when all strategies exhausted

        Note: "affordance" mode means AffordanceExecutor handles execution in ReplayEngine.
        """
        # Navigate / browser steps have no DOM target
        if target_role == "browser" or target_role == "navigate":
            return ResolutionResult.skipped()

        if descriptor is None:
            descriptor = {}

        # ------------------------------------------------------------------
        # 0. React-select rescue
        # ------------------------------------------------------------------
        # Many SaaS forms (Greenhouse, Lever, Workday) render dropdowns as
        # react-select widgets: when closed, the visible element is a
        # <div class="select__placeholder">Select...</div> inside an unlabelled
        # wrapper. Recordings produced before the recorder normalizer landed
        # captured the placeholder as role='generic' name='Select...' — and
        # because every dropdown on the page has identical "Select..." text,
        # primary_semantic always fails. This rescue runs first when the step
        # looks react-select-shaped and uses the descriptor's container_label
        # (the field label, e.g. "Country / Region") to find the right one.
        is_placeholder_name = (target_name or "").strip().lower() in ("", "select...", "select", "select…")
        looks_like_react_select = (
            (target_role in ("generic", "combobox") and is_placeholder_name) or
            ("select__" in (target_selector or ""))
        )
        field_label = (descriptor.get("container_label") or "").strip()
        if looks_like_react_select and field_label:
            try:
                for frame in self.page.frames:
                    cand = frame.locator(
                        "div.select__control"
                    ).filter(
                        has=frame.locator(
                            f"xpath=ancestor-or-self::*[contains(@class,'react-select') or contains(@class,'select__') or .//label[contains(normalize-space(.), {field_label!r})] or ancestor::*[.//label[contains(normalize-space(.), {field_label!r})]]]"
                        )
                    )
                    n = await cand.count()
                    if n == 0:
                        # Fall back to a label-text proximity search: find the label
                        # element with the field text, then the react-select control
                        # nearest after it in document order.
                        try:
                            label_loc = frame.get_by_text(field_label, exact=False).first
                            if await label_loc.count() > 0:
                                cand = label_loc.locator(
                                    "xpath=following::*[contains(@class,'select__control')][1] | following::div[@role='combobox'][1] | following::input[@role='combobox'][1]"
                                )
                                n = await cand.count()
                        except Exception:
                            pass
                    if n == 1:
                        return ResolutionResult.from_locator(
                            cand, "react_select_rescue",
                            recovered_by=f"container_label:{field_label[:48]}",
                            depth=0, candidate_count=1,
                        )
                    if n > 1:
                        resolved = await self._resolve_ambiguity(cand, descriptor)
                        if resolved:
                            return ResolutionResult.from_locator(
                                resolved, "react_select_rescue",
                                recovered_by=f"container_label:{field_label[:48]}",
                                depth=0, candidate_count=n,
                            )
            except Exception as exc:
                print(f"  [TargetResolver] react_select_rescue failed: {type(exc).__name__}: {exc}")

        # ------------------------------------------------------------------
        # 1. Exact CSS Selector Resolution
        # ------------------------------------------------------------------
        if target_selector:
            try:
                candidate = self.page.locator(target_selector)
                try:
                    await candidate.first.wait_for(state="attached", timeout=3000)
                except Exception:
                    pass
                count = await candidate.count()
                if count == 1:
                    return ResolutionResult.from_locator(candidate, "exact_selector", depth=0, candidate_count=1)
                elif count > 1:
                    resolved = await self._resolve_ambiguity(candidate, descriptor)
                    if resolved:
                        return ResolutionResult.from_locator(resolved, "exact_selector", depth=0, candidate_count=count)
            except Exception as e:
                import traceback
                print(f"  [TargetResolver] Exact selector resolution failed for '{target_selector}': {e}")
                traceback.print_exc()

        # ------------------------------------------------------------------
        # 2. Primary Strict Semantic Resolution
        # ------------------------------------------------------------------
        loc, raw_count = await self._try_resolve(
            target_role, target_name, exact=True, descriptor=descriptor
        )
        if loc:
            return ResolutionResult.from_locator(loc, "primary_semantic", depth=0, candidate_count=raw_count)

        # ------------------------------------------------------------------
        # 3. Runtime Robustness: Wait for network idle then retry
        # ------------------------------------------------------------------
        try:
            await self.page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass

        loc, raw_count = await self._try_resolve(
            target_role, target_name, exact=True, descriptor=descriptor
        )
        if loc:
            return ResolutionResult.from_locator(loc, "primary_semantic", depth=0, candidate_count=raw_count)

        strict_count = await self._count_candidates(target_role, target_name, exact=True)

        # ------------------------------------------------------------------
        # 4. Loose Semantic Resolution
        # ------------------------------------------------------------------
        loc, raw_count = await self._try_resolve(
            target_role, target_name, exact=False, descriptor=descriptor
        )
        if loc:
            return ResolutionResult.from_locator(loc, "loose_semantic", depth=0, candidate_count=raw_count)

        loose_count = await self._count_candidates(target_role, target_name, exact=False)
        peak_count = max(strict_count, loose_count)

        # ------------------------------------------------------------------
        # 5. Filter candidates by Container Proximity (Task 3A)
        # ------------------------------------------------------------------
        if peak_count > 1:
            container_label = descriptor.get("container_label")
            if container_label:
                loc, container_count = await self._try_container_label(target_role, target_name, container_label, exact=False)
                if loc:
                    return ResolutionResult.from_locator(loc, "semantic+container", depth=0, candidate_count=peak_count)

            candidates = self.page.get_by_role(target_role, name=target_name, exact=False)
            resolved = await self._resolve_ambiguity(candidates, descriptor)
            if resolved:
                return ResolutionResult.from_locator(resolved, "semantic+container", depth=0, candidate_count=peak_count)

        # ------------------------------------------------------------------
        # 6. If count > 1 → try field_registry_rescue, then AMBIGUOUS_IDENTITY
        # ------------------------------------------------------------------
        if peak_count > 1:
            # Defect A fix: give Field Ontology a chance on ambiguous-identity
            # cases (e.g. 12 buttons with name='Toggle flyout'). The registry
            # uses field aliases × container labels to uniquely identify the
            # right element among structurally-identical candidates.
            fr_loc = await self._resolve_by_field_registry(
                target_role, target_name, descriptor, step
            )
            if fr_loc is not None:
                return ResolutionResult.from_locator(
                    fr_loc, "field_registry_rescue",
                    recovered_by="field_registry", depth=0, candidate_count=peak_count,
                )

            candidates_info = await self._collect_candidates_info(target_role, target_name, exact=False)
            raise AmbiguousIdentityError(
                role=target_role,
                name=target_name,
                candidate_count=peak_count,
                candidates_info=candidates_info,
            )

        # ------------------------------------------------------------------
        # 7. RECOVERY TRACK (count == 0 only)
        # ------------------------------------------------------------------
        if not enable_recovery:
            raise TargetResolutionError(
                f"Failed to resolve target: role='{target_role}', name='{target_name}', selector='{target_selector}'"
            )

        # P4B: Memory Prior — try historically successful strategy first.
        # This is NOT an override: if the prior-guided attempt fails, normal
        # sequential resolution continues uninterrupted.
        if self.env_key:
            try:
                family = IntentFamilyMapper.map(descriptor)
                cap_hint = descriptor.get("capability_hint") or ""
                # Infer step_action from capability_hint (fill targets are inputs, submit are buttons)
                step_action = "fill" if cap_hint.endswith("_input") else "submit"
                priors = self._memory_reader.get_strategy_priors(
                    environment_key=self.env_key,
                    intent_family=family.value,
                    capability_hint=cap_hint,
                    step_action=step_action,
                )
                if priors:
                    best = max(priors, key=lambda k: priors[k])
                    best_weight = priors[best]
                    if best_weight >= 0.6:
                        prior_loc = None
                        if best == "capability_intent" and cap_hint:
                            prior_loc = await self._resolve_by_capability(descriptor)
                        elif best == "placeholder" and descriptor.get("placeholder"):
                            prior_loc = await self._try_placeholder(descriptor.get("placeholder"), descriptor)
                        elif best == "nearby_text" and descriptor.get("accessible_name"):
                            prior_loc = await self._try_text(descriptor.get("accessible_name"), descriptor)
                        elif best == "structural_path" and descriptor.get("dom_path"):
                            candidate = self.page.locator(descriptor.get("dom_path"))
                            count = await candidate.count()
                            if count == 1:
                                prior_loc = candidate
                                
                        if prior_loc:
                            print(f"  [Memory] Prior-guided: {best} ({best_weight:.2f}) for {cap_hint}@{self.env_key}")
                            if self._behavior_audit is not None:
                                try:
                                    self._behavior_audit.memory_prior(
                                        persona=getattr(self, "persona_id", "") or "",
                                        env=self.env_key or "",
                                        picked=best,
                                        fallback_used=False,
                                        extra={"weight": float(best_weight)},
                                    )
                                except Exception:
                                    pass
                            return ResolutionResult.from_locator(
                                prior_loc, best,
                                recovered_by="memory_prior", depth=0, candidate_count=1
                            )
            except Exception:
                pass  # Memory read failure must never block resolution

        # Adaptive v1: Lesson-prior dispatch.
        # When lessons.jsonl has surfaced reliable recovery strategies for
        # TARGET_CHANGED, try them in descending success-rate order BEFORE
        # the hardcoded R1-R5 ladder. Misses fall through to R1-R5 unchanged.
        if self._lesson_reader is not None:
            try:
                lesson_priors = self._lesson_reader.get_recovery_priors("TARGET_CHANGED")
                if lesson_priors:
                    for recovered_by, rate in sorted(
                        lesson_priors.items(), key=lambda kv: kv[1], reverse=True
                    ):
                        if rate < 0.5:
                            continue
                        loc = None
                        label = None
                        if recovered_by == "container_proximity":
                            container = await self._try_find_container(descriptor)
                            if container:
                                if target_selector:
                                    cand = container.locator(target_selector)
                                    if await cand.count() == 1:
                                        loc, label = cand, "exact_selector"
                                if loc is None:
                                    cand = container.get_by_role(target_role, name=target_name, exact=False)
                                    if await cand.count() == 1:
                                        loc, label = cand, "loose_semantic"
                        elif recovered_by == "placeholder":
                            ph = descriptor.get("placeholder")
                            if ph:
                                cand = await self._try_placeholder(ph, descriptor)
                                if cand:
                                    loc, label = cand, "placeholder"
                        elif recovered_by == "accessible_name":
                            an = descriptor.get("accessible_name")
                            if an:
                                cand = await self._try_text(an, descriptor)
                                if cand:
                                    loc, label = cand, "nearby_text"
                        elif recovered_by == "nearby_text":
                            tc = descriptor.get("text_content") or descriptor.get("accessible_name")
                            if tc:
                                cand = await self._try_text(tc, descriptor)
                                if cand:
                                    loc, label = cand, "nearby_text"
                        elif recovered_by == "structural_path":
                            dp = descriptor.get("dom_path")
                            if dp:
                                cand = self.page.locator(dp)
                                if await cand.count() == 1:
                                    loc, label = cand, "structural_path"
                        elif recovered_by == "capability_intent":
                            if descriptor.get("capability_hint"):
                                cand = await self._resolve_by_capability(descriptor)
                                if cand:
                                    loc, label = cand, "capability_intent"
                        else:
                            # Unknown recovered_by label — skip, fall through.
                            continue
                        if loc is not None and label is not None:
                            print(f"  [Lesson] Prior-guided: {recovered_by} ({rate:.2f})")
                            if self._behavior_audit is not None:
                                try:
                                    self._behavior_audit.lesson_prior(
                                        persona=getattr(self, "persona_id", "") or "",
                                        env=self.env_key or "",
                                        picked=recovered_by,
                                        fallback_used=False,
                                        extra={"rate": float(rate)},
                                    )
                                except Exception:
                                    pass
                            return ResolutionResult.from_locator(
                                loc, label,
                                recovered_by=f"lesson_prior:{recovered_by}",
                                depth=0, candidate_count=1,
                            )
            except Exception:
                pass  # Lesson dispatch failure must never block resolution

        # BC strategy prior — mirrors lesson_prior pattern.
        # Gated on BM_BC_STRATEGY=1; failure is always silent.
        if os.environ.get("BM_BC_STRATEGY") == "1":
            try:
                from browsermind_core.runtime.bc_policy import shared as _bc_shared
                _bc = _bc_shared()
                if _bc.ready:
                    _action_hint = (step or {}).get("action_type", "") if step else ""
                    _step_seq = int((step or {}).get("seq", 0)) if step else 0
                    pred = _bc.predict(target_role, _action_hint, _step_seq, env_key=getattr(self, "env_key", "") or "")
                    _strategy_label = pred.get("strategy_label", "") if pred else ""
                    _strategy_conf = pred.get("strategy_probs", [])
                    _strategy_id = pred.get("strategy_id", -1) if pred else -1
                    _conf = _strategy_conf[_strategy_id] if _strategy_conf and 0 <= _strategy_id < len(_strategy_conf) else 0.0
                    if _strategy_label and _strategy_label not in ("unknown", "") and _conf >= 0.6:
                        result = await self._dispatch_bc_strategy(
                            _strategy_label, descriptor, target_role, target_name, target_selector
                        )
                        if result is not None:
                            print(f"  [BC] Prior-guided: {_strategy_label} (conf={_conf:.2f})")
                            return result
            except Exception:
                pass  # BC failure must never block resolution

        # ------------------------------------------------------------------
        # Recovery ladder (data-driven via RecoveryRegistry).
        #
        # When a registry is wired, iterate its rows in order; each row is
        # dispatched to its named primitive. The seeded ladder reproduces the
        # original R1-R5b sequence bit-for-bit. New mined rows append after
        # the builtins. When no registry is wired, fall back to the legacy
        # hardcoded ladder below to keep older callers (tests/harnesses)
        # working untouched.
        # ------------------------------------------------------------------
        if self._recovery_registry is not None:
            try:
                from browsermind_core.runtime.recovery_registry import predicate_matches
                from browsermind_core.training.descriptor_features import features as _features
            except Exception:
                predicate_matches = None
                _features = None
            if predicate_matches is not None and _features is not None:
                feature_vector = _features(descriptor, integrity={})
                # Inter-step belief: reorder ladder when prior step provides evidence.
                ladder_strategies = list(self._recovery_registry.ladder())
                if prior_belief is not None:
                    try:
                        from browsermind_core.runtime.execution_belief import adjust_strategy_order
                        strategy_names = [s.primitive for s in ladder_strategies]
                        reordered_names = adjust_strategy_order(strategy_names, prior_belief)
                        name_to_strategy = {s.primitive: s for s in ladder_strategies}
                        ladder_strategies = [
                            name_to_strategy[n] for n in reordered_names if n in name_to_strategy
                        ] + [s for s in ladder_strategies if s.primitive not in name_to_strategy]
                        if reordered_names != strategy_names:
                            print(
                                f"  [Belief] Prior step belief reordered recovery ladder: "
                                f"failed={prior_belief.failed_strategy} "
                                f"url_changed={prior_belief.url_changed} "
                                f"effect_verified={prior_belief.effect_verified}"
                            )
                    except Exception:
                        pass  # Belief reordering failure must never block resolution
                for strategy in ladder_strategies:
                    if not predicate_matches(strategy.predicate, feature_vector):
                        continue
                    result = await self._dispatch_recovery_strategy(
                        strategy, descriptor, target_role, target_name, target_selector,
                    )
                    if result is not None:
                        return result
                # All ladder rows missed → final fallback identical to legacy.
                print("[DEBUG TRACK] Reached End of Recovery Track - Raising TargetResolutionError")
                try:
                    os.makedirs("scratch", exist_ok=True)
                    with open("scratch/failed_page.html", "w", encoding="utf-8") as f:
                        f.write(await self.page.content())
                    print(f"[FORENSICS] Wrote failed page HTML to scratch/failed_page.html")
                except Exception as e:
                    print(f"[FORENSICS] Failed to write page HTML: {e}")
                raise TargetResolutionError(
                    f"Failed to resolve target: role='{target_role}', name='{target_name}', selector='{target_selector}'"
                )

        # R1: Container proximity
        container = await self._try_find_container(descriptor)
        if container:
            try:
                if target_selector:
                    candidate = container.locator(target_selector)
                    if await candidate.count() == 1:
                        return ResolutionResult.from_locator(
                            candidate, "exact_selector",
                            recovered_by="container_proximity", depth=1, candidate_count=1
                        )
                candidate = container.get_by_role(target_role, name=target_name, exact=False)
                if await candidate.count() == 1:
                    return ResolutionResult.from_locator(
                        candidate, "loose_semantic",
                        recovered_by="container_proximity", depth=1, candidate_count=1
                    )
                elif await candidate.count() > 1:
                    resolved = await self._resolve_ambiguity(candidate, descriptor)
                    if resolved:
                        return ResolutionResult.from_locator(
                            resolved, "loose_semantic",
                            recovered_by="container_proximity", depth=1, candidate_count=1
                        )
            except Exception:
                pass

        # R2: Placeholder Fallback
        placeholder = descriptor.get("placeholder")
        if placeholder:
            loc = await self._try_placeholder(placeholder, descriptor)
            if loc:
                return ResolutionResult.from_locator(
                    loc, "placeholder", recovered_by="placeholder", depth=1, candidate_count=1
                )

        # R3: Accessible Name / Text Content Fallback
        accessible_name = descriptor.get("accessible_name")
        if accessible_name:
            loc = await self._try_text(accessible_name, descriptor)
            if loc:
                return ResolutionResult.from_locator(
                    loc, "nearby_text", recovered_by="accessible_name", depth=2, candidate_count=1
                )

        text_content = descriptor.get("text_content")
        if text_content:
            loc = await self._try_text(text_content, descriptor)
            if loc:
                return ResolutionResult.from_locator(
                    loc, "nearby_text", recovered_by="nearby_text", depth=2, candidate_count=1
                )

        # R3.5: semantic_group equivalents — when the recorded name fails on a
        # sister site, try other names from the same SEMANTIC_EQUIVALENTS group.
        # Bounded: only the recorded role + alternative names; no DOM probing.
        semantic_group = descriptor.get("semantic_group")
        if semantic_group:
            try:
                from browsermind_core.recorder.demonstration_compiler import SEMANTIC_EQUIVALENTS
            except Exception:
                SEMANTIC_EQUIVALENTS = {}
            equivalents = SEMANTIC_EQUIVALENTS.get(semantic_group, [])
            recorded_name = (descriptor.get("name") or descriptor.get("accessible_name") or "").strip().lower()
            role = descriptor.get("role") or "button"
            for equiv in equivalents:
                if equiv.strip().lower() == recorded_name:
                    continue
                try:
                    cand = self.page.get_by_role(role, name=equiv).first
                    if await cand.count() > 0:
                        return ResolutionResult.from_locator(
                            cand, "semantic_group",
                            recovered_by=f"semantic_group:{semantic_group}",
                            depth=2, candidate_count=1,
                        )
                except Exception:
                    continue

        # R4: Structural DOM Path
        dom_path = descriptor.get("dom_path")
        if dom_path:
            try:
                candidate = self.page.locator(dom_path)
                count = await candidate.count()
                print(f"[DEBUG TRACK] R4 structural_path count={count}")
                if count == 1:
                    return ResolutionResult.from_locator(
                        candidate, "structural_path", recovered_by="structural_path", depth=3, candidate_count=1
                    )
                elif count > 1:
                    resolved = await self._resolve_ambiguity(candidate, descriptor)
                    if resolved:
                        return ResolutionResult.from_locator(
                            resolved, "structural_path", recovered_by="structural_path", depth=3, candidate_count=count
                        )
            except Exception as e:
                print(f"[DEBUG TRACK] R4 Exception: {e}")
                pass

        # R5a: Affordance Intent Resolution — Depth 4a (WR-IR Phase 2)
        family = IntentFamilyMapper.map(descriptor)
        cap_hint = descriptor.get("capability_hint") or ""
        is_input_target = cap_hint.endswith("_input")
        
        print(f"[DEBUG TRACK] R5a Affordance: family={family}, is_input={is_input_target}")
        if family != IntentFamily.UNKNOWN and not is_input_target:
            try:
                discoverer = AffordanceDiscoverer()
                affordances = await discoverer.discover(self.page, family)
                aff = best_affordance(affordances, min_score=0.5)
                if aff:
                    return ResolutionResult.from_affordance(aff, depth=4)
            except Exception as e:
                print(f"[DEBUG TRACK] R5a Exception: {e}")
                pass

        print("[DEBUG TRACK] Reached R5b")
        # R5b: Capability Intent Fallback — Depth 4b (WR-IR Phase 1)
        cap_loc = await self._resolve_by_capability(descriptor)
        if cap_loc:
            return ResolutionResult.from_locator(
                cap_loc, "capability_intent", recovered_by="capability_intent", depth=4, candidate_count=1
            )

        # R6: field_registry_rescue — semantic Field identity. Composes existing
        # _try_container_label across every alias declared in the registry,
        # then falls back to direct get_by_role(alias) when no container_label
        # was observed at record time. Pure DOM traversal; no LLM/vision.
        fr_loc = await self._resolve_by_field_registry(target_role, target_name, descriptor, step)
        if fr_loc is not None:
            return ResolutionResult.from_locator(
                fr_loc, "field_registry_rescue",
                recovered_by="field_registry", depth=5, candidate_count=1,
            )

        # R7: Virtual list scroll-to-render protocol.
        # Fires only when the page contains react-virtualized / @tanstack/virtual /
        # AG Grid patterns. DOM only renders 20-50 rows at a time — the target row
        # may not exist yet. Scroll the list container until the row appears or
        # the rendered set stops growing.
        vl_loc = await self._find_in_virtual_list(target_role, target_name, descriptor)
        if vl_loc is not None:
            return ResolutionResult.from_locator(
                vl_loc, "virtual_list",
                recovered_by="virtual_list_scroll", depth=6, candidate_count=1,
            )

        print("[DEBUG TRACK] Reached End of Recovery Track - Raising TargetResolutionError")
        try:
            os.makedirs("scratch", exist_ok=True)
            with open("scratch/failed_page.html", "w", encoding="utf-8") as f:
                f.write(await self.page.content())
            print(f"[FORENSICS] Wrote failed page HTML to scratch/failed_page.html")
        except Exception as e:
            print(f"[FORENSICS] Failed to write page HTML: {e}")

        raise TargetResolutionError(
            f"Failed to resolve target: role='{target_role}', name='{target_name}', selector='{target_selector}'"
        )

    # ------------------------------------------------------------------
    # R7: Virtual list scroll-to-render protocol
    # ------------------------------------------------------------------

    # Selectors that identify the scroll container of a virtual list.
    _VIRTUAL_LIST_CONTAINERS = [
        "[data-virtualized]",
        "[class*='virtualized' i]",
        "[class*='virtual-list' i]",
        "[class*='ReactVirtualized' i]",
        "[class*='ag-body-viewport' i]",       # AG Grid
        "[class*='ag-center-cols-viewport' i]", # AG Grid
        "[data-testid*='virtual' i]",
        "[role='grid']",
        "[role='treegrid']",
        "[role='listbox']",
    ]

    # JS that checks whether a rendered item matches the target role + name.
    _ITEM_MATCH_SCRIPT = """
    (args) => {
        const [role, name] = args;
        const items = document.querySelectorAll(
            "[role='row'], [role='option'], [role='gridcell'], [data-index]"
        );
        const nameLow = (name || '').toLowerCase().trim();
        for (const el of items) {
            const elRole = (el.getAttribute('role') || '').toLowerCase();
            const elText = (el.innerText || el.textContent || '').toLowerCase().trim();
            const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
            if (role && elRole && elRole !== role.toLowerCase()) continue;
            if (nameLow && !elText.includes(nameLow) && !ariaLabel.includes(nameLow)) continue;
            return true;
        }
        return false;
    }
    """

    async def _find_in_virtual_list(
        self,
        target_role: str,
        target_name: str,
        descriptor: Dict[str, Any],
        max_scroll_rounds: int = 15,
    ) -> Optional[Locator]:
        """
        Scroll-to-render protocol for react-virtualized / @tanstack/virtual / AG Grid.

        The DOM only keeps 20-50 rows rendered at a time. If the target row hasn't
        scrolled into view yet, it won't appear via any selector. This method:
          1. Detects whether any virtual list container is present on the page.
          2. Scrolls the container in increments, checking for the target after each.
          3. Stops when found, or when the rendered set stops growing (exhausted).

        Returns a Locator pointing at the matched item, or None if not found.
        """
        import asyncio as _asyncio

        # 1. Find a virtual list container
        container_loc = None
        for sel in self._VIRTUAL_LIST_CONTAINERS:
            try:
                count = await self.page.locator(sel).count()
                if count > 0:
                    candidate = self.page.locator(sel).first
                    if await candidate.is_visible():
                        container_loc = candidate
                        break
            except Exception:
                continue

        if container_loc is None:
            return None  # No virtual list on this page — skip

        # 2. Scroll-to-render loop
        prev_rendered_count = -1
        for _ in range(max_scroll_rounds):
            # Check if target is now rendered
            try:
                found = await self.page.evaluate(
                    self._ITEM_MATCH_SCRIPT, [target_role, target_name]
                )
            except Exception:
                found = False

            if found:
                # Re-query at interaction time (never store handles)
                item_selector = "[role='row'], [role='option'], [role='gridcell'], [data-index]"
                name_low = (target_name or "").lower().strip()
                role_low = (target_role or "").lower()
                items = self.page.locator(item_selector)
                count = await items.count()
                for i in range(count):
                    el = items.nth(i)
                    try:
                        text = (await el.inner_text() or "").lower().strip()
                        aria = (await el.get_attribute("aria-label") or "").lower()
                        el_role = (await el.get_attribute("role") or "").lower()
                        if role_low and el_role and el_role != role_low:
                            continue
                        if name_low and name_low not in text and name_low not in aria:
                            continue
                        return el
                    except Exception:
                        continue
                return None  # evaluate said found but locator sweep missed — bail

            # Count currently rendered rows to detect list exhaustion
            try:
                rendered_count = await self.page.locator(
                    "[role='row'], [role='option'], [data-index]"
                ).count()
            except Exception:
                rendered_count = 0

            if rendered_count == prev_rendered_count:
                # No new rows rendered after last scroll — list exhausted
                return None
            prev_rendered_count = rendered_count

            # Scroll container by one viewport height
            try:
                await container_loc.evaluate(
                    "el => el.scrollTop += el.clientHeight || 400"
                )
            except Exception:
                try:
                    await self.page.keyboard.press("PageDown")
                except Exception:
                    return None

            await _asyncio.sleep(0.2)  # wait for virtual list to render new rows

        return None  # max_scroll_rounds reached without finding target

    async def _resolve_by_field_registry(
        self,
        target_role: str,
        target_name: str,
        descriptor: Dict[str, Any],
        step: Optional[Dict[str, Any]] = None,
    ) -> Optional[Locator]:
        """Last-line semantic rescue: look the step up in the FieldRegistry and
        try each known alias × ARIA role until one resolves uniquely.

        Pure deterministic DOM lookup. No LLM, no vision, no remote calls.
        Composes existing strategies (``_try_container_label``,
        ``page.get_by_role``) rather than reimplementing label-proximity walks.

        Returns the Locator on a unique hit, else None — caller continues to
        raise TargetResolutionError as before.
        """
        try:
            from browsermind_core.ontology.field_registry import get_registry
        except Exception:
            return None

        registry = get_registry()
        # Defect B fix: compiler writes field_id at step-level (see
        # demonstration_compiler.py); legacy callers may pass it via descriptor.
        # Read both, prefer step-level (canonical), fall back to descriptor,
        # then to name-based registry lookup.
        field_id = None
        if step is not None:
            field_id = step.get("field_id")
        if not field_id and descriptor is not None:
            field_id = descriptor.get("field_id")
        field = registry.get(field_id) if field_id else None
        if field is None:
            field = registry.resolve(target_name) or registry.resolve(
                (descriptor or {}).get("container_label") or ""
            )
        if field is None:
            return None

        roles_to_try: List[str] = list(dict.fromkeys(
            [r for r in (field.aria_roles or []) if r] + ([target_role] if target_role else [])
        ))
        if not roles_to_try:
            return None

        # Strategy 1: when the recorded target_name is non-semantic (e.g.
        # "Toggle flyout", "Select...", a generic UI verb that doesn't match
        # any known Field), use label-anchor lookup. Find <label> elements
        # whose text matches a Field alias, then look for the recorded
        # control inside the label's immediate container. This avoids the
        # over-permissive ancestor walk in _try_container_label, which is
        # too coarse for densely-labeled forms (every button's ancestor
        # walk eventually reaches a <form> containing all labels in
        # innerText, so the proximity check matches everything).
        recorded_name_is_semantic = registry.resolve(target_name) is not None
        if not recorded_name_is_semantic and target_name:
            for alias in field.all_labels():
                try:
                    labels = self.page.locator("label").filter(has_text=alias)
                    n_labels = await labels.count()
                except Exception:
                    continue
                winners: List[Locator] = []
                for i in range(n_labels):
                    try:
                        lbl = labels.nth(i)
                        # Strategy 1a: <label for="X"> — direct association.
                        for_id = await lbl.get_attribute("for")
                        if for_id:
                            try:
                                target = self.page.locator(f"#{for_id}")
                                if await target.count() == 1:
                                    winners.append(target)
                                    continue
                            except Exception:
                                pass
                        # Strategy 1b: search the label's immediate parent
                        # for a control matching the recorded role+name.
                        container = lbl.locator("xpath=..")
                        for role in roles_to_try:
                            try:
                                cand = container.get_by_role(
                                    role, name=target_name, exact=False
                                )
                                if await cand.count() == 1:
                                    winners.append(cand)
                                    break
                            except Exception:
                                pass
                    except Exception:
                        pass
                if len(winners) == 1:
                    return winners[0]

        # Strategy 2: when the recorded target_name *is* semantic (e.g. the
        # form labels the field directly with text like "Country"), try each
        # alias as the role/name. This is the original behavior and remains
        # the right move for forms that don't hide the field name behind a
        # generic widget.
        for alias in field.all_labels():
            for role in roles_to_try:
                try:
                    cand = self.page.get_by_role(role, name=alias, exact=False)
                    if await cand.count() == 1:
                        return cand
                except Exception:
                    pass
                try:
                    loc, count = await self._try_container_label(role, alias, alias, exact=False)
                    if loc is not None and count == 1:
                        return loc
                except Exception:
                    pass

        return None

    async def _resolve_by_capability(
        self,
        descriptor: Dict[str, Any],
    ) -> Optional[Locator]:
        """
        WR-IR Depth 4: Resolve element by functional capability.

        Uses:
          descriptor["capability_hint"]    — what type of element this is
          descriptor["capability_ordinal"] — which occurrence to pick (1-indexed)

        This is the fallback that survives Drift Class A+F:
          - A mutates aria-label/placeholder  → kills Depth 1 & placeholder fallback
          - F removes id/data-testid          → kills Depth 0
          - Capability selectors use type/name attributes that A+F do NOT mutate
        """
        capability_hint = descriptor.get("capability_hint")
        if not capability_hint:
            print("[DEBUG capability] No capability_hint")
            return None

        selectors = CAPABILITY_SELECTORS.get(capability_hint, [])
        if not selectors:
            print(f"[DEBUG capability] No selectors for {capability_hint}")
            return None

        # ordinal is 1-indexed; use it to pick the Nth matching visible element
        ordinal = max(1, int(descriptor.get("capability_ordinal") or 1))

        for css_selector in selectors:
            try:
                candidate = self.page.locator(css_selector)
                count = await candidate.count()
                if count == 0:
                    continue

                # Filter to visible only
                visible_indices = []
                for i in range(count):
                    try:
                        if await candidate.nth(i).is_visible():
                            visible_indices.append(i)
                    except Exception:
                        pass

                if not visible_indices:
                    print(f"[DEBUG capability] {css_selector} matched {count} but none visible")
                    continue

                # Use ordinal to pick the correct one (1-indexed among visible)
                target_index = ordinal - 1  # convert to 0-indexed
                if target_index < len(visible_indices):
                    chosen = candidate.nth(visible_indices[target_index])
                    print(f"[DEBUG capability] Resolved using {css_selector}")
                    return chosen
                else:
                    # ordinal out of range — take the last visible one
                    chosen = candidate.nth(visible_indices[-1])
                    print(f"[DEBUG capability] Resolved using {css_selector} (fallback ordinal)")
                    return chosen

            except Exception as e:
                print(f"[DEBUG capability] Exception on {css_selector}: {e}")
                continue

        print("[DEBUG capability] Exhausted all selectors without a match")
        return None
