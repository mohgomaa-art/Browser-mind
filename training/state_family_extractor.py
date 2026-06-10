from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_utils import domain_from_url, graph_edges, graph_nodes, iter_dataset_samples, rel


INTERACTIVE_ROLES = {
    "button",
    "link",
    "textbox",
    "searchbox",
    "combobox",
    "checkbox",
    "radio",
    "menuitem",
    "tab",
    "option",
}


def _node_token(node: Dict[str, Any]) -> str:
    role = str(node.get("role", "generic")).lower()
    name = str(node.get("name", "")).lower()
    value = str(node.get("value", "")).lower()
    text = f"{name} {value}"

    if role == "textbox" and any(k in text for k in ("search", "query", "find")):
        return "searchbox"
    if role == "button" and any(k in text for k in ("next", "continue", "back", "previous")):
        return "wizard_nav"
    if role == "button" and any(k in text for k in ("submit", "save", "finish", "done", "send")):
        return "submit"
    if role == "button" and any(k in text for k in ("ok", "yes", "confirm", "accept", "allow")):
        return "confirm"
    if role == "button" and any(k in text for k in ("cancel", "close", "dismiss", "no")):
        return "dismiss"
    if role == "link" and any(k in text for k in ("next", "prev", "page", "pagination")):
        return "paginate"
    if role in {"combobox", "menuitem", "option"}:
        return role
    if role in INTERACTIVE_ROLES:
        return role
    if role in {"dialog", "alertdialog"}:
        return "modal"
    if role in {"row", "cell", "grid", "table", "list", "listitem"}:
        return "table"
    return role


def extract_state_family(sample_or_nodes: Dict[str, Any] | Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(sample_or_nodes, dict):
        sample = sample_or_nodes
        nodes = graph_nodes(sample)
        edges = graph_edges(sample)
    else:
        sample = {}
        nodes = list(sample_or_nodes)
        edges = []

    tokens = [_node_token(n) for n in nodes if isinstance(n, dict)]
    interactive = [t for t in tokens if t in INTERACTIVE_ROLES or t in {"searchbox", "wizard_nav", "submit", "confirm", "dismiss", "paginate"}]

    has_modal = "modal" in tokens
    has_table = "table" in tokens or sum(1 for t in tokens if t in {"row", "cell"}) > 3
    has_search = "searchbox" in interactive
    has_wizard = "wizard_nav" in interactive and ("submit" in interactive or len([t for t in interactive if t == "wizard_nav"]) > 1)
    has_form = sum(1 for t in interactive if t in {"textbox", "searchbox", "combobox", "checkbox", "radio"}) >= 1
    has_results = any(t in tokens for t in {"list", "listitem", "table"}) and len(nodes) >= 10

    if has_modal and "confirm" in interactive:
        family = "modal->confirm"
    elif has_modal:
        family = "modal->action"
    elif has_table and ("combobox" in interactive or has_search):
        family = "table->filter->paginate" if "paginate" in interactive else "table->filter"
    elif has_table:
        family = "table->paginate" if "paginate" in interactive else "table"
    elif has_wizard:
        family = "wizard->next->submit"
    elif has_search and has_results:
        family = "searchbox->results"
    elif has_search:
        family = "searchbox->submit"
    elif has_form:
        compact = []
        for token in interactive:
            if not compact or compact[-1] != token:
                compact.append(token)
        family = "->".join(compact[:8]) or "form"
    else:
        compact = []
        for token in interactive or tokens:
            if token in {"generic", ""}:
                continue
            if not compact or compact[-1] != token:
                compact.append(token)
        family = "->".join(compact[:8]) or "empty"

    raw = "|".join(interactive[:80]) + f"|n={len(nodes)}|e={len(edges)}|m={int(has_modal)}|t={int(has_table)}"
    family_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    return {
        "state_family": family,
        "state_family_hash": family_hash,
        "interactive_sequence": interactive,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "has_modal": has_modal,
        "has_table": has_table,
        "has_search": has_search,
        "has_wizard": has_wizard,
    }


def analyze_state_families(
    paths: List[str] | None = None,
    max_state_family: int = 50,
    max_domain: int = 100,
    max_examples: int = 25,
) -> Dict[str, Any]:
    family_counts = Counter()
    domain_counts = Counter()
    family_success = defaultdict(lambda: {"success": 0, "total": 0})
    cap_violations = []
    total = 0

    for fp, loc, sample in iter_dataset_samples(paths):
        total += 1
        fam = extract_state_family(sample)
        family = fam["state_family"]
        domain = domain_from_url(str(sample.get("url", "")))
        family_counts[family] += 1
        domain_counts[domain] += 1
        family_success[family]["total"] += 1
        if bool(sample.get("success", True)):
            family_success[family]["success"] += 1

        reasons = []
        if family_counts[family] == max_state_family + 1:
            reasons.append("state_family_cap_exceeded")
        if domain_counts[domain] == max_domain + 1:
            reasons.append("domain_cap_exceeded")
        if reasons and len(cap_violations) < max_examples:
            cap_violations.append(
                {
                    "file": rel(fp),
                    "location": loc,
                    "domain": domain,
                    "state_family": family,
                    "reasons": reasons,
                }
            )

    success_by_family = {
        family: {
            "count": stats["total"],
            "success_rate": round(stats["success"] / max(stats["total"], 1), 4),
        }
        for family, stats in sorted(
            family_success.items(),
            key=lambda item: item[1]["total"],
            reverse=True,
        )
    }

    return {
        "total_samples": total,
        "unique_state_families": len(family_counts),
        "state_family_frequency": dict(family_counts.most_common()),
        "state_family_success": success_by_family,
        "domain_frequency": dict(domain_counts.most_common()),
        "caps": {
            "max_samples_per_state_family": max_state_family,
            "max_samples_per_domain": max_domain,
        },
        "cap_violations": cap_violations,
        "families_over_cap": {
            family: count for family, count in family_counts.items() if count > max_state_family
        },
        "domains_over_cap": {
            domain: count for domain, count in domain_counts.items() if count > max_domain
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract BrowserMind state families.")
    parser.add_argument("paths", nargs="*", help="Dataset files/directories to inspect.")
    parser.add_argument("--max-state-family", type=int, default=50)
    parser.add_argument("--max-domain", type=int, default=100)
    parser.add_argument("--max-examples", type=int, default=25)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    report = analyze_state_families(
        args.paths or None,
        max_state_family=args.max_state_family,
        max_domain=args.max_domain,
        max_examples=args.max_examples,
    )
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
