"""
BrowserMind â€” Session Adapter
===============================
Converts old-format sessions (tag/text/x/y DOM) to spec-format (graph/nodes/edges).

Old format  (training/sessions/*.json):
  state.elements  = [{tag, text, placeholder, x, y, w, h, clickable, id_attr, classes}]
  action          = {action_type, target_text, target_selector, typed_text, goal}

Spec format (training/spec_sessions/*.json):
  goal            = "..."
  graph.nodes     = [{idx, role, name, value, focused, depth}]
  graph.edges     = [[src, tgt, etype], ...]
  expert_action   = {type, action_id, element_idx, value}
  success         = bool
  step            = int
  url             = "..."

Usage:
  python -m training.session_adapter
  python -m training.session_adapter --input training/sessions --output training/spec_sessions
  python -m training.session_adapter --dry-run   (print stats only)
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.privacy import (
    redact_sensitive_text,
    sanitize_expert_action,
    sanitize_goal_for_storage,
    sanitize_graph_for_storage,
)

# [FIX C-7] Align with canonical ACTION_TYPES from model/agent_policy.py:
#   0:navigate, 1:click, 2:type, 3:scroll, 4:wait,
#   5:extract, 6:go_back, 7:done
_OLD_ACTION_TO_SPEC_ID: Dict[str, int] = {
    "open_url":       0,  # navigate
    "navigate":       0,
    "click":          1,
    "type":           2,
    "scroll":         3,
    "wait":           4,
    "extract":        5,
    "go_back":        6,
    "done":           7,
    "fail":           7,  # terminal â€” quality filters will reject failed sessions anyway
}

# â”€â”€ Role mapping: HTML tag â†’ accessibility role â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_TAG_TO_ROLE: Dict[str, str] = {
    "button":   "button",
    "a":        "link",
    "input":    "textbox",     # may be refined by type attr
    "select":   "combobox",
    "textarea": "textbox",
    "h1":       "heading",
    "h2":       "heading",
    "h3":       "heading",
    "h4":       "heading",
    "h5":       "heading",
    "h6":       "heading",
    "img":      "img",
    "ul":       "list",
    "ol":       "list",
    "li":       "listitem",
    "nav":      "navigation",
    "main":     "main",
    "dialog":   "dialog",
}
_DEFAULT_ROLE = "generic"


def _tag_to_role(tag: str, el: Dict) -> str:
    """Convert HTML tag to accessibility role, with input[type=checkbox] override."""
    tag = tag.lower()
    if tag == "input":
        t = (el.get("type") or "").lower()
        if t == "checkbox": return "checkbox"
        if t == "radio":    return "radio"
    return _TAG_TO_ROLE.get(tag, _DEFAULT_ROLE)


def _element_name(el: Dict) -> str:
    """Best human-readable name for an element (for SemanticGoalEncoder)."""
    parts = [
        el.get("text", ""),
        el.get("placeholder", ""),
        el.get("aria_label", "") or el.get("aria-label", ""),
        el.get("title", ""),
        el.get("alt", ""),
    ]
    name = " ".join(p for p in parts if p).strip()
    return name[:120]   # truncate very long names


def _elements_to_graph(elements: List[Dict]) -> Tuple[List[Dict], List[List]]:
    """
    Build spec-format graph from flat element list.

    Nodes:  role, name, value, focused, depth (approximated from y position)
    Edges:  consecutive elements are 'sibling'; all linked to a virtual root (idx=N) as parent
    """
    # Max 80 nodes per spec (truncate from bottom = high y values)
    sorted_els = sorted(elements, key=lambda e: (e.get("y", 0), e.get("x", 0)))
    els = sorted_els[:80]

    nodes = []
    for i, el in enumerate(els):
        tag   = str(el.get("tag", "")).lower()
        role  = _tag_to_role(tag, el)
        name  = _element_name(el)
        value = str(el.get("value", "") or "")
        # Approximate depth from nesting level OR y position bucket
        depth = int(el.get("depth", 0)) or max(1, int(el.get("y", 0) / 150))
        depth = min(depth, 19)

        nodes.append({
            "idx":     i,
            "role":    role,
            "name":    name,
            "value":   value,
            "focused": bool(el.get("focused", False)),
            "depth":   depth,
        })

    # Edges: sibling links (i â†’ i+1), plus parent_child from a virtual root
    edges: List[List] = []
    for i in range(len(nodes) - 1):
        edges.append([i, i + 1, "sibling"])

    # Virtual parent node provides structure signal (not added as a real node)
    # So we just let the graph be flat siblings for now â€” that's valid for BC

    return nodes, edges


def _find_element_idx(
    elements: List[Dict],
    target_text: Optional[str],
    target_selector: Optional[str],
) -> Optional[int]:
    """
    Same logic as ImitationTrainer._find_element_idx.
    Returns None if no match â€” NEVER defaults to 0.
    """
    target_text     = (target_text or "").lower().strip()
    target_selector = (target_selector or "").lower().strip()

    if not target_text and not target_selector:
        return None

    for i, el in enumerate(elements):
        el_text = (
            (el.get("text", "") or "") + " " +
            (el.get("placeholder", "") or "")
        ).lower()
        el_id   = (el.get("id_attr") or "").lower()
        el_cls  = (el.get("classes") or "").lower()

        if target_text and (
            target_text in el_text or
            target_text in el_id
        ):
            return i
        if target_selector and (
            target_selector.lstrip("#.") in el_id or
            target_selector.lstrip("#.") in el_cls
        ):
            return i

    return None   # no match â†’ caller must handle


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  SessionAdapter
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class SessionAdapter:

    def __init__(
        self,
        input_dir:  str = "training/sessions",
        output_dir: str = "training/spec_sessions",
    ):
        self.input_dir  = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.stats = {
            "sessions_read":    0,
            "sessions_written": 0,
            "samples_in":       0,
            "samples_out":      0,
            "skipped_no_action_id":      0,
            "skipped_element_not_found": 0,
            "skipped_empty_nodes":       0,
        }

    # â”€â”€ Public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def convert_all(self, dry_run: bool = False) -> Dict:
        files = sorted(self.input_dir.glob("*.json"))
        if not files:
            print(f"[!] No JSON files in {self.input_dir}")
            return self.stats

        print(f"\n{'='*55}")
        print(f"  SessionAdapter â€” converting {len(files)} session(s)")
        print(f"  {self.input_dir}  ->  {self.output_dir}")
        print(f"{'='*55}")

        for f in files:
            self._convert_file(f, dry_run=dry_run)

        self._print_report()
        return self.stats

    # â”€â”€ File Processing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _convert_file(self, path: Path, dry_run: bool = False):
        self.stats["sessions_read"] += 1

        try:
            with open(path, encoding="utf-8") as f:
                session = json.load(f)
        except Exception as e:
            print(f"  [ERR] {path.name}: parse error - {e}")
            return

        raw_samples = session.get("samples", [])
        self.stats["samples_in"] += len(raw_samples)

        out_samples = []
        for raw in raw_samples:
            sample = self._convert_sample(raw)
            if sample is not None:
                out_samples.append(sample)
                self.stats["samples_out"] += 1

        if not out_samples:
            print(f"  [SKIP] {path.name}: 0 valid samples after conversion")
            return

        if not dry_run:
            out_path = self.output_dir / path.name
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(out_samples, f, indent=2, ensure_ascii=False)

        self.stats["sessions_written"] += 1
        print(f"  [OK] {path.name:<40} {len(out_samples)}/{len(raw_samples)} samples")

    # -- Sample Conversion ----------------------------------------------------

    def _convert_sample(self, raw: Dict) -> Optional[Dict]:
        """Convert one old-format sample -> one spec-format sample, or None."""
        state  = raw.get("state", {})
        action = raw.get("action", {})

        elements = state.get("elements", [])
        if not elements:
            self.stats["skipped_empty_nodes"] += 1
            return None

        # Build graph
        nodes, edges = _elements_to_graph(elements)
        if len(nodes) < 2:
            self.stats["skipped_empty_nodes"] += 1
            return None

        # Resolve action_id
        act_type = action.get("action_type", "")
        action_id = _OLD_ACTION_TO_SPEC_ID.get(act_type)
        if action_id is None:
            self.stats["skipped_no_action_id"] += 1
            return None

        # Resolve element_idx
        target_text     = action.get("target_text")
        target_selector = action.get("target_selector")
        element_idx     = _find_element_idx(elements, target_text, target_selector)

        # Validate element_idx bounds
        if element_idx is not None and element_idx >= len(nodes):
            element_idx = None

        # If action needs an element but we couldn't resolve it â†’ skip
        needs_element = act_type in ("click", "type", "extract")
        if needs_element and element_idx is None:
            self.stats["skipped_element_not_found"] += 1
            return None

        expert_action: Dict = {
            "type":      act_type,
            "action_id": action_id,
        }
        if element_idx is not None:
            expert_action["element_idx"] = element_idx
        typed_val = action.get("typed_text") or action.get("value") or ""
        if typed_val:
            expert_action["value"] = typed_val

        goal_clean = sanitize_goal_for_storage(action.get("goal", ""))
        expert_action = sanitize_expert_action(expert_action, goal_text=goal_clean)
        safe_graph = sanitize_graph_for_storage({"nodes": nodes, "edges": edges})

        return {
            "goal":         goal_clean,
            "graph":        safe_graph,
            "expert_action": expert_action,
            "success":      raw.get("success", True),
            "step":         raw.get("step", 0),
            "url":          redact_sensitive_text(state.get("page_url", "")),
        }

    # â”€â”€ Report â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _print_report(self):
        s = self.stats
        print(f"\n  Sessions : {s['sessions_written']}/{s['sessions_read']} converted")
        print(f"  Samples  : {s['samples_out']}/{s['samples_in']} converted")
        print(f"  Skips    :")
        print(f"    empty_nodes       : {s['skipped_empty_nodes']}")
        print(f"    no_action_id      : {s['skipped_no_action_id']}")
        print(f"    element_not_found : {s['skipped_element_not_found']}")
        print(f"{'='*55}\n")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  CLI
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert old sessions to spec format")
    parser.add_argument("--input",   default="training/sessions",
                        help="Input directory with old-format session JSONs")
    parser.add_argument("--output",  default="training/spec_sessions",
                        help="Output directory for spec-format session JSONs")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without writing files")
    args = parser.parse_args()

    adapter = SessionAdapter(input_dir=args.input, output_dir=args.output)
    adapter.convert_all(dry_run=args.dry_run)
