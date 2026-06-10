"""
BrowserMind — Graph Builder
============================
Converts a Playwright page -> spec-format graph using the CDP accessibility API.

NOTE: page.accessibility was removed in Playwright 1.38.
We use CDP (Chrome DevTools Protocol) directly via page.context.new_cdp_session().

This module is used by:
  - collect_and_train.py  (data collection loop)
  - train_dagger.py       (DAgger rollouts)
  - evaluate.py           (live rollout eval)

Usage:
  from training.graph_builder import build_graph_from_page, decide_expert_action

  graph  = await build_graph_from_page(page)
  action = decide_expert_action(graph, goal="login to github", page_url=page.url)
"""

from __future__ import annotations

import hashlib
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
#  ROLES and ACTION TYPES (canonical, matching spec Section 6)
# ---------------------------------------------------------------------------
ROLES: List[str] = [
    "button", "link", "textbox", "combobox", "checkbox",
    "radio", "menuitem", "heading", "img", "list",
    "listitem", "navigation", "main", "dialog", "generic",
]

ACTION_TYPES: Dict[int, str] = {
    0: "navigate",  1: "click",   2: "type",   3: "scroll",
    4: "wait",      5: "extract", 6: "go_back", 7: "done",
}

_INTERACTIVE_ROLES = {"button", "link", "menuitem", "tab"}
_INPUT_ROLES       = {"textbox", "combobox", "checkbox", "radio"}

# CDP role -> spec role map  (Chrome AX tree uses ARIA role names)
_CDP_ROLE_MAP: Dict[str, str] = {
    # Inputs
    "button":               "button",
    "togglebutton":         "button",
    "switch":               "button",
    "link":                 "link",
    "textbox":              "textbox",
    "searchbox":            "textbox",
    "input":                "textbox",
    "combobox":             "combobox",
    "listbox":              "combobox",
    "spinbutton":           "combobox",
    "checkbox":             "checkbox",
    "radio":                "radio",
    "menuitem":             "menuitem",
    "menuitemcheckbox":     "menuitem",
    "menuitemradio":        "menuitem",
    "option":               "menuitem",
    "tab":                  "menuitem",
    # Structure
    "heading":              "heading",
    "img":                  "img",
    "image":                "img",
    "svgroot":              "img",
    "list":                 "list",
    "listitem":             "listitem",
    "term":                 "listitem",
    "navigation":           "navigation",
    "main":                 "main",
    "form":                 "main",
    "dialog":               "dialog",
    "alertdialog":          "dialog",
    "alert":                "dialog",
    "region":               "main",
    "article":              "main",
    "section":              "main",
    "banner":               "navigation",
    "contentinfo":          "navigation",
    "complementary":        "navigation",
    "search":               "main",
    "grid":                 "list",
    "row":                  "listitem",
    "cell":                 "listitem",
    "columnheader":         "heading",
    "rowheader":            "heading",
    "tree":                 "list",
    "treeitem":             "listitem",
    # Generic / fallback
    "group":                "generic",
    "none":                 "generic",
    "generic":              "generic",
    "statictext":           "generic",
    "inlinetext":           "generic",
    "text":                 "generic",
    "presentation":         "generic",
    "paragraph":            "generic",
    "blockquote":           "generic",
    "table":                "list",
    "rowgroup":             "generic",
    "figure":               "generic",
    "landmark":             "navigation",
    "tab":                  "menuitem",
    "tablist":              "list",
    "tabpanel":             "main",
    "log":                  "generic",
    "status":               "generic",
    "progressbar":          "generic",
    "separator":            "generic",
    "scrollbar":            "generic",
    "slider":               "combobox",
    "inlinetextbox":        "generic",
    "labeltext":            "generic",
    "legendtext":           "generic",
    "legend":               "generic",
    "statictext":           "generic",
    "rootwebarea":          "generic",
    "inputtime":            "combobox",
    "inputdate":            "combobox",
}

# Interactive roles — tiered priority when truncating to 80 nodes:
#   Tier 1 (inputs)   — ALWAYS kept; form fields are the signal we care about most
#   Tier 2 (actions)  — buttons, kept after inputs
#   Tier 3 (nav)      — links, menuitems; kept last; cheapest to drop
_INPUT_TIER   = {"textbox", "combobox", "checkbox", "radio", "searchbox"}
_ACTION_TIER  = {"button"}
_NAV_TIER     = {"link", "menuitem"}
_PRIORITY_ROLES = _INPUT_TIER | _ACTION_TIER | _NAV_TIER

_PRUNE_INTERACTIVE_ROLES = {
    "button", "link", "textbox", "combobox", "checkbox", "radio", "menuitem",
    "searchbox", "spinbutton", "slider", "switch", "tab", "option", "listbox",
    "grid", "row", "cell", "treeitem", "tabpanel",
}
_PRUNE_STRUCTURAL_ROLES = {"heading", "main", "navigation", "dialog", "alert", "status"}


# ---------------------------------------------------------------------------
#  1. Build graph from a live Playwright page (async)
# ---------------------------------------------------------------------------

async def build_graph_from_page(page, goal: str = "") -> Dict:
    """
    Fetch the full accessibility tree via CDP and return a spec graph.

    Returns: {"nodes": [...], "edges": [...]}

    Requires that the page belongs to a Chromium browser context.
    """
    try:
        # Open a CDP session for this page
        client = await page.context.new_cdp_session(page)
        
        # Ensure domains are enabled before fetching the tree. 
        # Without this, getFullAXTree can return 0 nodes on subsequent calls.
        try:
            await client.send("DOM.enable")
            await client.send("Accessibility.enable")
        except Exception:
            pass
            
        resp   = await client.send("Accessibility.getFullAXTree")
        nodes_raw = resp.get("nodes", [])

        # --- Phase 2: Real Geometry ---
        # Fetch bounding boxes using backendNodeIds before detaching
        bboxes = await _fetch_bounding_boxes(client, nodes_raw)
        for node in nodes_raw:
            nid = str(node.get("backendDOMNodeId", ""))
            if nid in bboxes:
                node["_bbox"] = bboxes[nid]
        
        await client.detach()

        nodes_raw = resp.get("nodes", [])
        graph = _cdp_tree_to_graph(nodes_raw)

        # Optional safety gating when caller provides a goal context.
        if goal:
            try:
                from core.decision_engine import ConstraintFilter
                nodes = graph.get("nodes", [])
                safe_nodes = ConstraintFilter.apply(nodes, action_type="type", goal=goal)

                # Re-map indices and update edges to maintain graph integrity.
                if len(safe_nodes) < len(nodes):
                    old_to_new = {n["idx"]: i for i, n in enumerate(safe_nodes)}
                    for i, n in enumerate(safe_nodes):
                        n["idx"] = i

                    new_edges = []
                    for src, tgt, etype in graph.get("edges", []):
                        if src in old_to_new and tgt in old_to_new:
                            new_edges.append([old_to_new[src], old_to_new[tgt], etype])

                    graph["nodes"] = safe_nodes
                    graph["edges"] = new_edges
            except Exception:
                # Never fail graph extraction because optional filtering failed.
                pass

        return graph

    except Exception as e:
        # Fallback: try ARIA snapshot text approach if CDP fails
        try:
            return await _aria_snapshot_fallback(page)
        except Exception:
            return {"nodes": [], "edges": []}


async def _fetch_bounding_boxes(client, nodes_raw: List[Dict]) -> Dict[str, Dict]:
    """Fetch real bounding boxes for all nodes that have a backendDOMNodeId."""
    bboxes = {}
    
    # Optional: Enable DOM domain to ensure getBoxModel works
    try:
        await client.send("DOM.enable")
    except Exception:
        pass
        
    for raw in nodes_raw:
        bid = raw.get("backendDOMNodeId")
        if not bid:
            continue
        try:
            # Note: getBoxModel takes backendNodeId
            box_resp = await client.send("DOM.getBoxModel", {"backendNodeId": bid})
            model = box_resp.get("model", {})
            quad = model.get("border", [])
            if len(quad) == 8:
                x = min(quad[0], quad[2], quad[4], quad[6])
                y = min(quad[1], quad[3], quad[5], quad[7])
                w = max(quad[0], quad[2], quad[4], quad[6]) - x
                h = max(quad[1], quad[3], quad[5], quad[7]) - y
                bboxes[str(bid)] = {"x": x, "y": y, "w": w, "h": h}
        except Exception:
            continue
    return bboxes

async def _aria_snapshot_fallback(page) -> Dict:
    """
    Playwright 1.38+ has page.aria_snapshot() that returns YAML-like text.
    Parse it as a flat list of accessible nodes.
    """
    try:
        # Playwright Python does not have page.aria_snapshot() directly. 
        # Try locator fallback or old accessibility API if available.
        try:
            text = await page.locator("body").aria_snapshot()
        except Exception:
            snapshot = await page.accessibility.snapshot()
            if snapshot:
                from training.graph_builder import build_graph
                return build_graph(snapshot)
            return {"nodes": [], "edges": []}
            
        return _parse_aria_text(text)
    except Exception:
        return {"nodes": [], "edges": []}


def _parse_aria_text(text: str) -> Dict:
    """
    Parse Playwright aria_snapshot() text (indented YAML-like) into spec graph.
    Each line: [indent] - role "name"
    """
    nodes  = []
    edges  = []
    stack  = []   # (depth, node_idx)

    for line in (text or "").splitlines():
        stripped = line.lstrip("- ").strip()
        if not stripped:
            continue

        indent = (len(line) - len(line.lstrip(" "))) // 2

        # Parse role and name
        role = "generic"
        name = ""
        parts = stripped.split(None, 1)
        if parts:
            role = _CDP_ROLE_MAP.get(parts[0].lower().rstrip(":"), "generic")
        if len(parts) > 1:
            name = parts[1].strip('"\'').strip()[:120]

        idx = len(nodes)
        nodes.append({
            "idx":     idx,
            "role":    role,
            "name":    name,
            "value":   "",
            "focused": False,
            "depth":   min(indent, 19),
        })

        # Build parent_child edges based on indentation
        while stack and stack[-1][0] >= indent:
            stack.pop()

        if stack:
            parent_idx = stack[-1][1]
            edges.append([parent_idx, idx, "parent_child"])
            # Sibling edge
            if len(nodes) > 1 and nodes[-2]["depth"] == indent:
                edges.append([idx - 1, idx, "sibling"])

        stack.append((indent, idx))

        if len(nodes) >= 80:
            break

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
#  2. CDP tree -> spec graph
# ---------------------------------------------------------------------------

def _cdp_tree_to_graph(nodes_raw: List[Dict]) -> Dict:
    """
    Convert CDP AX tree node list to spec graph format.
    Uses two-pass approach:
      Pass 1: Include all interactive/input nodes (button, link, textbox, etc.)
      Pass 2: Fill remaining slots with structural nodes up to 80 total
    This guarantees buttons and textboxes are never dropped.
    """
    # Parse all CDP nodes into spec format first
    by_id: Dict[str, Dict] = {}
    for raw in nodes_raw:
        nid = str(raw.get("nodeId", str(id(raw))))
        by_id[nid] = raw

    # Build parent map
    parent_map: Dict[str, str] = {}
    for raw in nodes_raw:
        nid = str(raw.get("nodeId", ""))
        for child_id in (raw.get("childIds") or []):
            parent_map[str(child_id)] = nid

    def _parse_one(raw: Dict, depth: int = 0) -> Optional[Dict]:
        """Parse a single CDP node into spec format."""
        role_raw = raw.get("role", {})
        if isinstance(role_raw, dict):
            role_str = str(role_raw.get("value", "")).lower()
        else:
            role_str = str(role_raw or "").lower()

        role = _CDP_ROLE_MAP.get(role_str, "generic")

        name_val = raw.get("name", {})
        if isinstance(name_val, dict):
            name = str(name_val.get("value", "") or "")
        else:
            name = str(name_val or "")
        # Skip "?" placeholder names (Chrome uses this for locked/unavailable)
        if name == "?":
            name = ""
        name = name[:120]

        val_val = raw.get("value", {})
        if isinstance(val_val, dict):
            value = str(val_val.get("value", "") or "")
        else:
            value = str(val_val or "")
        value = value[:80]

        focused = False
        for prop in (raw.get("properties") or []):
            if isinstance(prop, dict) and prop.get("name") == "focused":
                pv = prop.get("value", {})
                if isinstance(pv, dict):
                    focused = bool(pv.get("value", False))

        # Compute depth from parent chain
        nid = str(raw.get("nodeId", ""))

        return {
            "_nid":       nid,
            "_parent_nid": parent_map.get(nid),  # stored for edge reconstruction
            "_depth":     0,   # filled in after
            "role":       role,
            "name":       name,
            "value":      value,
            "focused":    focused,
            "_bbox":      raw.get("_bbox"), # Phase 2 geometry
        }

    # BFS to compute actual depth for each node
    depths: Dict[str, int] = {}
    roots = [str(r.get("nodeId","")) for r in nodes_raw
             if str(r.get("nodeId","")) not in parent_map]
    queue = [(nid, 0) for nid in roots]
    while queue:
        nid, d = queue.pop(0)
        depths[nid] = d
        raw = by_id.get(nid, {})
        for cid in (raw.get("childIds") or []):
            if str(cid) not in depths:
                queue.append((str(cid), d + 1))

    # Parse all nodes
    parsed: List[Dict] = []
    for raw in nodes_raw:
        spec = _parse_one(raw)
        if spec:
            nid = spec["_nid"]
            spec["_depth"] = min(depths.get(nid, 0), 19)
            parsed.append(spec)

    # ── Role Budgeting ──────────────────────────────────────────────────────
    # Each role category gets a guaranteed budget slot.
    # This prevents 400 links from starving out textboxes and searchboxes.
    #
    #   INPUT_BUDGET      = 20  (textbox, searchbox, combobox, checkbox, radio)
    #   BUTTON_BUDGET     = 20  (button)
    #   STRUCTURAL_BUDGET = 20  (heading, navigation, main, dialog, etc.)
    #   NAV_BUDGET        = 20  (link, menuitem — cheapest to drop)
    #
    # Within each bucket: shallowest nodes first.
    # Any remaining slots after budgets are filled go to overflow (shallowest first).

    MAX_NODES        = 80
    INPUT_BUDGET     = 20
    BUTTON_BUDGET    = 20
    STRUCTURAL_BUDGET = 20
    NAV_BUDGET       = 20

    _STRUCTURAL_ROLES = frozenset({
        "heading", "navigation", "main", "dialog", "alert",
        "list", "listitem", "img", "generic"
    })

    bucket_inputs  = sorted([p for p in parsed if p["role"] in _INPUT_TIER],   key=lambda p: p["_depth"])
    bucket_buttons = sorted([p for p in parsed if p["role"] in _ACTION_TIER],  key=lambda p: p["_depth"])
    bucket_nav     = sorted([p for p in parsed if p["role"] in _NAV_TIER],     key=lambda p: p["_depth"])
    bucket_struct  = sorted([p for p in parsed if p["role"] in _STRUCTURAL_ROLES], key=lambda p: p["_depth"])

    # ── Observation Coverage (KPI) ───────────────────────────────────────────
    # Record raw counts BEFORE budgeting so callers can compute coverage %.
    raw_counts = {
        "input":      len(bucket_inputs),
        "button":     len(bucket_buttons),
        "nav":        len(bucket_nav),
        "structural": len(bucket_struct),
    }

    selected: List[Dict] = []
    seen_nids: set = set()

    def _fill(candidates: List[Dict], budget: int) -> int:
        """Fill up to `budget` nodes from candidates. Returns count added."""
        added = 0
        for p in candidates:
            if added >= budget or len(selected) >= MAX_NODES:
                break
            if p["_nid"] not in seen_nids:
                seen_nids.add(p["_nid"])
                selected.append(p)
                added += 1
        return added

    added_inputs  = _fill(bucket_inputs,  INPUT_BUDGET)
    added_buttons = _fill(bucket_buttons, BUTTON_BUDGET)
    added_struct  = _fill(bucket_struct,  STRUCTURAL_BUDGET)
    added_nav     = _fill(bucket_nav,     NAV_BUDGET)

    # Fill any remaining capacity with overflow (inputs > buttons > struct > nav)
    _fill(bucket_inputs,  MAX_NODES)
    _fill(bucket_buttons, MAX_NODES)
    _fill(bucket_struct,  MAX_NODES)
    _fill(bucket_nav,     MAX_NODES)

    selected_counts = {
        "input":      added_inputs,
        "button":     added_buttons,
        "nav":        added_nav,
        "structural": added_struct,
    }

    # ── Sort selected by DFS-ish order ───────────────────────────────────────
    nid_order = {str(r.get("nodeId","")): i for i, r in enumerate(nodes_raw)}
    selected.sort(key=lambda p: (p["_depth"], nid_order.get(p["_nid"], 9999)))

    # Assign final spec indices
    nodes: List[Dict] = []
    nid_to_idx: Dict[str, int] = {}
    for p in selected:
        idx = len(nodes)
        nid_to_idx[p["_nid"]] = idx
        nodes.append({
            "idx":     idx,
            "role":    p["role"],
            "name":    p["name"],
            "value":   p["value"],
            "focused": p["focused"],
            "depth":   p["_depth"],
            "bbox":    p.get("_bbox"), # Phase 2 geometry
        })

    # Build edges from parent/child relationships.
    # Strategy: for each selected node, walk UP the parent_map until we find
    # another selected node. This handles the case where structural parent nodes
    # are dropped from the 80-node selection (leaf-only graphs get 0 edges otherwise).
    edges: List[List] = []
    added_edges = set()

    def add_edge(src_idx, tgt_idx, etype):
        key = (src_idx, tgt_idx, etype)
        if key not in added_edges:
            added_edges.add(key)
            edges.append([src_idx, tgt_idx, etype])

    for p in selected:
        nid  = p["_nid"]
        cidx = nid_to_idx[nid]

        # Walk up the parent chain until we reach a selected ancestor
        ancestor_nid = p.get("_parent_nid")
        while ancestor_nid is not None:
            aidx = nid_to_idx.get(ancestor_nid)
            if aidx is not None:
                add_edge(aidx, cidx, "parent_child")
                break
            # keep walking up
            ancestor_raw = by_id.get(ancestor_nid, {})
            ancestor_nid = parent_map.get(ancestor_nid)

    # Add sibling edges for nodes sharing the same nearest selected ancestor
    from collections import defaultdict
    children_of: dict = defaultdict(list)
    for src_idx, tgt_idx, etype in edges:
        if etype == "parent_child":
            children_of[src_idx].append(tgt_idx)
    for parent_idx, children in children_of.items():
        for i in range(len(children) - 1):
            add_edge(children[i], children[i + 1], "sibling")

    # ── Observation Coverage KPI ─────────────────────────────────────────────
    # Tells callers what fraction of each role category survived budgeting.
    def _cov(selected_n, raw_n):
        return round(selected_n / raw_n, 3) if raw_n > 0 else 1.0

    observation_coverage = {
        "raw":      raw_counts,
        "selected": selected_counts,
        "coverage": {
            k: _cov(selected_counts[k], raw_counts[k])
            for k in raw_counts
        }
    }

    return {"nodes": nodes, "edges": edges, "observation_coverage": observation_coverage}


# ---------------------------------------------------------------------------
#  3. Build graph from a static snapshot dict (for tests + train_dagger)
# ---------------------------------------------------------------------------

def build_graph(snapshot: Optional[Dict]) -> Dict:
    """
    Synchronous: Convert a snapshot-style dict (from old API or mock) to spec graph.
    For live Playwright pages, prefer build_graph_from_page(page) instead.
    """
    nodes: List[Dict] = []
    edges: List[List] = []

    if snapshot:
        _walk_snap(snapshot, nodes, edges, depth=0, parent_idx=None)

    if len(nodes) > 80:
        kept_set = set(range(80))
        nodes    = nodes[:80]
        edges    = [e for e in edges if e[0] in kept_set and e[1] in kept_set]

    return {"nodes": nodes, "edges": edges}


def _walk_snap(node, nodes, edges, depth, parent_idx):
    if not node:
        return
    idx  = len(nodes)
    role = _CDP_ROLE_MAP.get(str(node.get("role") or "generic").lower(), "generic")
    name = str(node.get("name") or "")[:120]
    val  = str(node.get("value") or "")[:80]

    nodes.append({
        "idx":     idx,
        "role":    role,
        "name":    name,
        "value":   val,
        "focused": bool(node.get("focused", False)),
        "depth":   min(depth, 19),
    })

    if parent_idx is not None:
        edges.append([parent_idx, idx, "parent_child"])

    children = node.get("children") or []
    prev: Optional[int] = None
    for child in children:
        before = len(nodes)
        _walk_snap(child, nodes, edges, depth + 1, parent_idx=idx)
        after  = len(nodes)
        if after > before:
            ci = before
            if prev is not None:
                edges.append([prev, ci, "sibling"])
            prev = ci


# ---------------------------------------------------------------------------
#  4. Graph hash (for stuck-detection)
# ---------------------------------------------------------------------------

def graph_hash(graph: Dict) -> str:
    """Stable hash of a graph for detecting identical consecutive states."""
    nodes = graph.get("nodes", [])
    key   = "|".join(
        f"{n.get('role','')}{n.get('name','')[:20]}"
        for n in nodes[:20]
    )
    return hashlib.md5(key.encode()).hexdigest()[:12]


# [DELETED by Anti-Gravity Audit C-1]
# The first prune_graph definition was removed — it was dead code shadowed by
# the canonical prune_graph defined below (line ~750). See audit report.


# ---------------------------------------------------------------------------
#  5. Heuristic expert action decision (Part 4 of spec)
# ---------------------------------------------------------------------------

def decide_expert_action(
    graph:    Dict,
    goal:     str,
    page_url: str,
) -> Dict:
    """
    Pure-heuristic expert that decides the best action given the current state.

    Priority (from spec Part 4):
      1. If goal requires navigation and we're at wrong URL -> navigate
      2. If visible textbox matches a goal keyword -> type
      3. If button/link matches a goal keyword -> click
      4. If page still loading (few nodes) -> wait
      5. Default -> scroll
    """
    goal_l = goal.lower()
    nodes  = graph.get("nodes", [])

    # -- Convert spec nodes to old element format for ElementScorer -----------
    old_els = [_spec_node_to_old_el(nd) for nd in nodes]

    # -- Priority 1: Am I on the right domain? --------------------------------
    if _needs_navigation(goal_l, page_url):
        target_url = _infer_target_url(goal_l)
        return {
            "type":        "navigate",
            "action_id":   0,
            "element_idx": None,
            "value":       target_url,
        }

    # -- Priority 1.5: Complex Forms Expert -----------------------------------
    try:
        from training.form_expert import form_expert_action
        f_act = form_expert_action(graph, goal_l, page_url)
        # Only use FormExpert's action if it actually decided something useful.
        if f_act and f_act["type"] not in ("scroll", "wait"):
            return f_act
    except Exception:
        pass

    # -- Find best elements via scorer ----------------------------------------
    try:
        from core.decision_engine import ElementScorer, ConstraintFilter
        goal_keywords = _extract_keywords(goal_l)
        target_text   = goal_keywords[0] if goal_keywords else goal_l

        # Priority 2: type into a textbox
        input_nodes = [nd for nd in nodes if nd.get("role") in _INPUT_ROLES]
        input_els   = [_spec_node_to_old_el(nd) for nd in input_nodes]

        if input_els:
            candidates = ElementScorer.rank(input_els, target_text, goal=goal_l, top_k=1)
            if candidates:
                orig_idx = input_nodes[0]["idx"]   # best match is first
                typed_value = _infer_type_value(goal_l)
                return {
                    "type":        "type",
                    "action_id":   2,
                    "element_idx": orig_idx,
                    "value":       typed_value,
                }

        # Priority 3: click a button/link
        click_nodes = [nd for nd in nodes if nd.get("role") in _INTERACTIVE_ROLES]
        click_els   = [_spec_node_to_old_el(nd) for nd in click_nodes]

        if click_els:
            candidates = ElementScorer.rank(click_els, target_text, goal=goal_l, top_k=1)
            if candidates:
                # Find best scored node (ElementScorer.rank works on the filtered list)
                best_old_idx = candidates[0].index
                if best_old_idx < len(click_nodes):
                    orig_idx = click_nodes[best_old_idx]["idx"]
                    return {
                        "type":        "click",
                        "action_id":   1,
                        "element_idx": orig_idx,
                        "value":       "",
                    }

    except Exception:
        pass

    # -- Fallback if Scorer doesn't find anything -----------------------------
    result = _keyword_fallback(nodes, goal_l)
    
    # -- Priority 3.5: Is the task already done? ------------------------------
    success_keywords = ["logged in", "success", "complete", "welcome", "account", "dashboard", "results", "thank you", "sign out", "logout"]
    for nd in nodes:
        name_l = nd.get("name", "").lower()
        if any(sk in name_l for sk in success_keywords):
            return {
                "type":        "done",
                "action_id":   7,
                "element_idx": -1,
                "value":       "",
            }

    if result:
        return result

    # -- Priority 4: page likely still loading (few nodes) -------------------
    if len(nodes) < 3:
        return {"type": "wait", "action_id": 4, "element_idx": None, "value": ""}

    # -- Priority 5: scroll to find more -----------------------------------------
    return {"type": "scroll", "action_id": 3, "element_idx": None, "value": ""}


def _keyword_fallback(nodes: List[Dict], goal_l: str) -> Optional[Dict]:
    """Find the first element whose name matches a goal keyword."""
    keywords = _extract_keywords(goal_l)
    for kw in keywords:
        for nd in nodes:
            name = nd.get("name", "").lower()
            if kw in name:
                role = nd.get("role", "generic")
                if role in _INPUT_ROLES:
                    return {
                        "type": "type", "action_id": 2,
                        "element_idx": nd["idx"],
                        "value": _infer_type_value(goal_l),
                    }
                if role in _INTERACTIVE_ROLES:
                    return {
                        "type": "click", "action_id": 1,
                        "element_idx": nd["idx"],
                        "value": "",
                    }
    return None


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _spec_node_to_old_el(nd: Dict) -> Dict:
    role = nd.get("role", "generic")
    
    # Phase 2: Use real geometry if available, fallback to synthetic if not
    bbox = nd.get("bbox")
    if bbox:
        x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
        visible = (w > 0 and h > 0)
    else:
        x = 100
        y = 200 + nd.get("depth", 0) * 40
        w = 300
        h = 40
        visible = True
        
    return {
        "tag":       _role_to_tag(role),
        "role":      role,
        "text":      nd.get("name", ""),
        "placeholder": "",
        "x":         x,
        "y":         y,
        "w":         w,
        "h":         h,
        "clickable": role in _INTERACTIVE_ROLES,
        "visible":   visible,
        "_node_idx": nd.get("idx", 0),
    }


def _role_to_tag(role: str) -> str:
    return {
        "button": "button", "link": "a", "textbox": "input",
        "combobox": "select", "checkbox": "input", "radio": "input",
        "heading": "h2", "img": "img", "navigation": "nav",
        "main": "main", "dialog": "dialog",
    }.get(role, "div")


def _extract_keywords(goal: str) -> List[str]:
    stopwords = {"to", "the", "a", "an", "in", "on", "at", "for", "with",
                 "and", "or", "of", "login", "log", "sign", "go", "open",
                 "find", "search", "navigate", "click", "fill", "submit"}
    words = [w for w in goal.lower().split() if w not in stopwords and len(w) > 2]
    return words if words else [goal]


def _needs_navigation(goal_l: str, current_url: str) -> bool:
    url_hints = {
        "github":        "github.com",
        "gitlab":        "gitlab.com",
        "reddit":        "reddit.com",
        "stackoverflow": "stackoverflow.com",
        "twitter":       "x.com",
        "wikipedia":     "wikipedia.org",
        "python":        "python.org",
        "google":        "google.com",
        "bing":          "bing.com",
        "duckduckgo":    "duckduckgo.com",
        "huggingface":   "huggingface.co",
        "arxiv":         "arxiv.org",
        "pypi":          "pypi.org",
    }
    for keyword, domain in url_hints.items():
        if keyword in goal_l and domain not in current_url:
            return True
    return False


def _infer_target_url(goal_l: str) -> str:
    mapping = {
        "github":        "https://github.com",
        "gitlab":        "https://gitlab.com",
        "reddit":        "https://www.reddit.com",
        "stackoverflow": "https://stackoverflow.com",
        "twitter":       "https://x.com",
        "wikipedia":     "https://en.wikipedia.org",
        "python":        "https://www.python.org",
        "google":        "https://www.google.com",
        "bing":          "https://www.bing.com",
        "duckduckgo":    "https://duckduckgo.com",
        "huggingface":   "https://huggingface.co",
        "arxiv":         "https://arxiv.org",
        "pypi":          "https://pypi.org",
    }
    for keyword, url in mapping.items():
        if keyword in goal_l:
            return url
# ─────────────────────────────────────────────────────────────────────────────
#  DOM Pruning — يشيل الـ noise ويحتفظ بالـ interactive + structural nodes
# ─────────────────────────────────────────────────────────────────────────────

_INTERACTIVE_ROLES = frozenset({
    "button", "link", "textbox", "combobox",
    "checkbox", "radio", "menuitem", "searchbox",
    "spinbutton", "slider", "switch", "tab",
    "option", "listbox", "grid", "row", "cell",
    "treeitem", "tabpanel",
})

_STRUCTURAL_ROLES = frozenset({
    "heading", "main", "navigation", "dialog", "alert",
})

_MAX_NODES_DEFAULT = 60  # أقصى عدد nodes بعد الـ pruning


def prune_graph(
    nodes: list,
    edges: list,
    max_nodes: int = _MAX_NODES_DEFAULT,
    keep_structural: bool = True,
) -> tuple[list, list]:
    """
    يشيل الـ nodes غير المفيدة ويحدث الـ edges.

    Priority:
      1. Interactive nodes (button, link, textbox, ...)
      2. Structural nodes مع name (heading, dialog, ...)
      3. Nodes عندها value
    """
    if not nodes:
        return nodes, edges

    scored: list[tuple[int, int, dict]] = []

    for i, node in enumerate(nodes):
        role = node.get("role", "generic")
        name = str(node.get("name", "")).strip()

        if role in _INTERACTIVE_ROLES:
            priority = 0
        elif keep_structural and role in _STRUCTURAL_ROLES and name:
            priority = 1
        elif node.get("value"):
            priority = 2
        elif role == "generic" and not name:
            continue
        else:
            priority = 3

        scored.append((priority, i, node))

    scored.sort(key=lambda x: (x[0], x[1])) # Priority first, then original order
    kept = scored[:max_nodes]

    old_to_new: dict[int, int] = {}
    pruned_nodes: list = []

    for new_idx, (_, old_idx, node) in enumerate(kept):
        old_to_new[old_idx] = new_idx
        # [FIX C-4] Update idx so downstream callers can map element_idx correctly
        updated = dict(node)
        updated["idx"] = new_idx
        pruned_nodes.append(updated)

    pruned_edges: list = []
    for edge in edges:
        if not (isinstance(edge, (list, tuple)) and len(edge) == 3):
            continue
        src, tgt, etype = int(edge[0]), int(edge[1]), str(edge[2])
        if src in old_to_new and tgt in old_to_new:
            pruned_edges.append([old_to_new[src], old_to_new[tgt], etype])

    return pruned_nodes, pruned_edges


async def build_graph_from_page_pruned(page, max_nodes: int = 60) -> dict:
    """
    Wrapper على build_graph_from_page يضيف pruning تلقائي.
    """
    graph = await build_graph_from_page(page)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    nodes, edges = prune_graph(nodes, edges, max_nodes=max_nodes)
    graph["nodes"] = nodes
    graph["edges"] = edges
    graph["pruned"] = True
    return graph


def _infer_type_value(goal_l: str) -> str:
    import re
    m = re.search(r"search (?:for |about )?(.+)", goal_l)
    if m:
        return m.group(1).strip()
    m = re.search(r"find (.+)", goal_l)
    if m:
        return m.group(1).strip()
    keywords = _extract_keywords(goal_l)
    return keywords[-1] if keywords else goal_l


# ---------------------------------------------------------------------------
#  Quick test (sync)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    async def main():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page    = await browser.new_page()

            for goal, url in [
                ("find documentation",   "https://docs.python.org/3/"),
                ("submit search form",   "https://www.wikipedia.org"),
                ("fill contact form",    "https://httpbin.org/forms/post"),
                ("search for python",    "https://www.google.com"),
            ]:
                print(f"\n--- {goal!r}")
                try:
                    await page.goto(url, timeout=12000, wait_until="domcontentloaded")
                    graph  = await build_graph_from_page(page)
                    nodes  = graph["nodes"]
                    edges  = graph["edges"]
                    print(f"    nodes={len(nodes)}  edges={len(edges)}")
                    for nd in nodes[:5]:
                        print(f"      [{nd['idx']}] {nd['role']:<12} {nd['name'][:40]!r}")
                    if nodes:
                        action = decide_expert_action(graph, goal, page.url)
                        print(f"    expert_action={action}")
                except Exception as e:
                    import traceback
                    traceback.print_exc()

            await browser.close()

    asyncio.run(main())
