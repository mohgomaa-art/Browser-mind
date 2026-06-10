"""
Gold dataset audit -- writes reports/gold_dataset_audit_v3.json
"""
from __future__ import annotations

import json
import math
import os
import glob
import random
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse


def calculate_entropy(counts_dict: Counter, total: int) -> float:
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in counts_dict.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)
    return round(entropy, 4)


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc or "unknown"
    except Exception:
        return "unknown"


LOW_VALUE_HEADINGS = frozenset(
    {
        "navigation menu",
        "site-wide links",
        "site wide links",
        "footer",
        "skip to",
        "breadcrumb",
    }
)


def build_gold_report(samples: list) -> dict:
    total = len(samples)
    families = Counter()
    tasks = Counter()
    domains = Counter()
    difficulty = Counter()
    role_counter = Counter()
    quality_scores = []
    confidences = []

    for s in samples:
        opp = s.get("opportunity_data", {})
        sf = s.get("state_family_data", {}).get("state_family", "unknown")
        families[sf] += 1
        tasks[opp.get("task_family", "unknown")] += 1
        domains[_domain(s.get("url", ""))] += 1
        difficulty[s.get("difficulty", "unknown")] += 1
        conf = s.get("state_family_data", {}).get("confidence")
        if conf is not None:
            confidences.append(conf)
        if s.get("task_type") == "extraction":
            role_counter["extraction"] += 1
        else:
            role_counter[opp.get("role", "unknown")] += 1
        if "quality_score" in opp:
            quality_scores.append(opp["quality_score"])

    ent = calculate_entropy(tasks, total)
    role_pct = {k: round(v / total, 4) if total else 0.0 for k, v in role_counter.most_common()}
    textbox_pct = (
        role_pct.get("textbox", 0.0)
        + role_pct.get("combobox", 0.0)
        + role_pct.get("searchbox", 0.0)
    )
    link_button_pct = role_pct.get("link", 0.0) + role_pct.get("button", 0.0)
    dom_share = max((c / total for c in domains.values()), default=0.0) if total else 0.0
    fam_share = max((c / total for c in families.values()), default=0.0) if total else 0.0
    med_hard = (difficulty.get("medium", 0) + difficulty.get("hard", 0)) / total if total else 0.0

    gates = {
        "entropy_gt_3": {"pass": ent > 3.0, "value": ent, "threshold": 3.0},
        "textbox_gt_20pct": {"pass": textbox_pct > 0.20, "value": textbox_pct, "threshold": 0.20},
        "largest_domain_lt_35pct": {"pass": dom_share < 0.35, "value": round(dom_share, 4), "threshold": 0.35},
        "largest_family_lt_35pct": {"pass": fam_share < 0.35, "value": round(fam_share, 4), "threshold": 0.35},
        "medium_hard_gt_20pct": {"pass": med_hard > 0.20, "value": round(med_hard, 4), "threshold": 0.20},
        "link_button_lt_80pct": {"pass": link_button_pct < 0.80, "value": round(link_button_pct, 4), "threshold": 0.80},
    }

    return {
        "schema": "browsermind.gold_dataset_audit.v3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "taxonomy_version": "2.0",
        "builder_version": 5,
        "total_samples": total,
        "state_families": dict(families.most_common()),
        "task_families": dict(tasks.most_common(30)),
        "domains": dict(domains.most_common()),
        "difficulty": dict(difficulty.most_common()),
        "role_distribution": dict(role_counter.most_common()),
        "role_distribution_pct": role_pct,
        "textbox_combined_pct": round(textbox_pct, 4),
        "link_plus_button_pct": round(link_button_pct, 4),
        "extraction_pct": round(role_pct.get("extraction", 0.0), 4),
        "avg_quality_score": round(sum(quality_scores) / len(quality_scores), 3) if quality_scores else None,
        "avg_family_confidence": round(sum(confidences) / len(confidences), 3) if confidences else None,
        "entropy": ent,
        "duplicates": 0,
        "gates": gates,
        "all_gates_pass": all(g["pass"] for g in gates.values()),
    }


def build_human_truth_report(samples: list) -> dict:
    random.seed(42)
    pool = random.sample(samples, min(20, len(samples)))
    reviewed = []
    auto_pass = 0
    failure_reasons: Counter = Counter()

    for s in pool:
        opp = s.get("opportunity_data", {})
        sf_data = s.get("state_family_data", {})
        sf = sf_data.get("state_family", "unknown")
        conf = sf_data.get("confidence", 0.0)
        goal = s.get("goal", "")
        name = opp.get("name", "")
        role = opp.get("role", "")
        url = s.get("url", "")
        q = opp.get("quality_score")
        issues = []

        if sf == "login_form" and "github.com" in url and "/login" not in url:
            issues.append("misclassified_landing_as_login")
        if sf == "search_interface" and "python.org" in url and role == "link":
            issues.append("misclassified_nav_as_search")
        if role == "heading" and any(t in name.lower() for t in LOW_VALUE_HEADINGS):
            issues.append("low_value_extraction")
        if role in ("link", "button") and sf in ("login_form", "search_interface", "landing_page"):
            nav_words = ("navigate to", "homepage", "solutions", "resources", "education", "security")
            if any(x in goal.lower() for x in nav_words):
                issues.append("low_information_nav_task")
        if q is not None and q < 0.5:
            issues.append("quality_below_threshold")
        if conf < 0.6:
            issues.append("low_family_confidence")

        verdict = "pass" if not issues else "fail"
        if verdict == "pass":
            auto_pass += 1
        else:
            for i in issues:
                failure_reasons[i] += 1

        reviewed.append(
            {
                "id": s.get("id"),
                "url": url,
                "goal": goal,
                "state_family": sf,
                "family_confidence": conf,
                "quality_score": q,
                "task_family": opp.get("task_family"),
                "role": role,
                "target_name": name,
                "auto_verdict": verdict,
                "issues": issues,
                "human_verdict": None,
            }
        )

    return {
        "schema": "browsermind.human_truth_audit.v3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "auto_heuristic_prefill_human_verdict_null",
        "samples_reviewed": len(reviewed),
        "auto_pass": auto_pass,
        "auto_fail": len(reviewed) - auto_pass,
        "auto_pass_rate": round(auto_pass / len(reviewed), 4) if reviewed else 0.0,
        "common_failure_reasons": dict(failure_reasons.most_common()),
        "production_ready_heuristic": auto_pass == len(reviewed),
        "samples": reviewed,
    }


def load_samples(base_dir: str) -> list:
    interaction_dir = os.path.join(base_dir, "gold_interaction")
    extraction_dir = os.path.join(base_dir, "gold_extraction")
    files = glob.glob(os.path.join(interaction_dir, "*.json")) + glob.glob(
        os.path.join(extraction_dir, "*.json")
    )
    samples = []
    seen = set()
    duplicates = 0
    for fpath in files:
        with open(fpath, encoding="utf-8") as f:
            sample = json.load(f)
        url = sample.get("url", "")
        opp = sample.get("opportunity_data", {})
        label = sample.get("label", {})
        sig = f"{url}_{opp.get('task_family')}_{label.get('action')}_{label.get('element_idx')}"
        if sig in seen:
            duplicates += 1
            continue
        seen.add(sig)
        samples.append(sample)
    return samples, duplicates


def main():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "training"))
    reports_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "reports"))
    os.makedirs(reports_dir, exist_ok=True)

    samples, duplicates = load_samples(base_dir)
    gold = build_gold_report(samples)
    gold["duplicates"] = duplicates
    human = build_human_truth_report(samples)

    gold_path = os.path.join(reports_dir, "gold_dataset_audit_v3.json")
    human_path = os.path.join(reports_dir, "human_truth_audit_v3.json")
    with open(gold_path, "w", encoding="utf-8") as f:
        json.dump(gold, f, indent=2, ensure_ascii=False)
    with open(human_path, "w", encoding="utf-8") as f:
        json.dump(human, f, indent=2, ensure_ascii=False)

    print("========== GOLD DATASET AUDIT v3 ==========")
    print(json.dumps(gold, indent=2))
    print(f"\nWrote {gold_path}")
    print(f"Wrote {human_path}")
    print("\n========== HUMAN TRUTH AUDIT v3 (summary) ==========")
    print(
        json.dumps(
            {
                "auto_pass": human["auto_pass"],
                "auto_fail": human["auto_fail"],
                "auto_pass_rate": human["auto_pass_rate"],
                "common_failure_reasons": human["common_failure_reasons"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
