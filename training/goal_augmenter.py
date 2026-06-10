"""
BrowserMind — Goal Augmenter
==============================
يأخد الـ sessions الموجودة ويضرب الـ data بـ 5x
عن طريق paraphrasing الـ goals بدون ما يغير الـ actions.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Optional


_PATTERNS: list[tuple[str, list[str]]] = [
    (
        r"^(?:search for|find|look up|explore)\s+(.+)$",
        [
            "search for {0}",
            "find {0}",
            "look up {0}",
            "explore {0}",
            "I need information about {0}",
            "show me results for {0}",
            "query: {0}",
            "get me {0}",
            "browse {0}",
        ],
    ),
    (
        r"^(?:navigate to|go to|open|access|visit)\s+(.+)$",
        [
            "navigate to {0}",
            "go to {0}",
            "open {0}",
            "access {0}",
            "visit {0}",
            "take me to {0}",
            "I want to see {0}",
        ],
    ),
    (
        r"^(?:extract|get|collect|retrieve|read)\s+(.+?)(?:\s+from\s+page)?$",
        [
            "extract {0}",
            "get {0} from page",
            "collect {0}",
            "retrieve {0}",
            "scrape {0}",
            "pull out {0}",
        ],
    ),
    (
        r"^(?:fill|complete|submit)\s+(.+?)\s+form$",
        [
            "fill {0} form",
            "complete the {0} form",
            "submit {0} form",
            "enter data in {0} form",
        ],
    ),
    (
        r"^(?:login|log in|sign in)\s+(?:to\s+)?(.+)$",
        [
            "login to {0}",
            "sign in to {0}",
            "log into {0}",
            "authenticate with {0}",
            "access my account on {0}",
        ],
    ),
    (
        r"^search\s+(.+?)\s+then\s+open\s+first\s+result$",
        [
            "search {0} then open first result",
            "find {0} and click the first result",
            "look up {0} and open top result",
            "search for {0} then navigate to first link",
        ],
    ),
]

_FALLBACK_PREFIXES = [
    "please ",
    "can you ",
    "I want to ",
    "help me to ",
    "", "", "",
]


def _paraphrase_goal(goal: str, n: int = 5) -> list[str]:
    """
    يرجع n paraphrases مختلفة للـ goal.
    """
    goal = goal.strip()
    results: list[str] = [goal]

    for pattern, templates in _PATTERNS:
        m = re.match(pattern, goal, re.IGNORECASE)
        if m:
            slot = m.group(1).strip()
            for tpl in templates:
                candidate = tpl.format(slot)
                if candidate.lower() != goal.lower():
                    results.append(candidate)
            break

    if len(results) < n:
        for prefix in _FALLBACK_PREFIXES:
            candidate = (prefix + goal).strip()
            if candidate not in results:
                results.append(candidate)

    seen = set()
    unique = []
    for r in results:
        key = r.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(r)

    random.shuffle(unique[1:])
    return unique[:n]


def augment_session_data(session_data: list, multiplier: int = 5) -> list[list]:
    """
    يأخد session data (list of samples) ويرجع multiplier versions.
    """
    if not session_data:
        return [session_data]

    original_goal = session_data[0].get("goal", "")
    if not original_goal:
        return [session_data]

    paraphrases = _paraphrase_goal(original_goal, n=multiplier)
    versions = []

    for phrase in paraphrases:
        new_version = []
        for sample in session_data:
            new_sample = dict(sample)
            new_sample["goal"] = phrase
            new_version.append(new_sample)
        versions.append(new_version)

    return versions


def augment_session_file(
    src_path: str | Path,
    dst_dir:  Optional[str | Path] = None,
    multiplier: int = 5,
    suffix: str = "_aug",
) -> list[Path]:
    """
    يأخد JSON session file ويعمل multiplier نسخ augmented.
    """
    src_path = Path(src_path)
    dst_dir  = Path(dst_dir) if dst_dir else src_path.parent
    dst_dir.mkdir(parents=True, exist_ok=True)

    try:
        with open(src_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    if isinstance(data, list):
        samples = data
    elif isinstance(data, dict):
        samples = data.get("samples", [])
    else:
        return []

    versions = augment_session_data(samples, multiplier=multiplier)
    saved: list[Path] = []

    for i, version in enumerate(versions):
        if i == 0:
            continue
        stem = src_path.stem
        out_path = dst_dir / f"{stem}{suffix}_{i}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(version, f, ensure_ascii=False)
        saved.append(out_path)

    return saved


def augment_all_sessions(
    src_dir:    str | Path,
    dst_dir:    str | Path,
    multiplier: int = 5,
    pattern:    str = "*.json",
    verbose:    bool = True,
) -> int:
    """
    يعمل augmentation على كل الـ sessions في directory.
    """
    src_dir = Path(src_dir)
    dst_dir = Path(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    all_files = list(src_dir.glob(pattern))
    total_new = 0

    for i, fp in enumerate(all_files):
        # Exclude already augmented files to avoid explosion
        if "_aug_" in fp.name:
            continue
        try:
            new_files = augment_session_file(fp, dst_dir=dst_dir, multiplier=multiplier)
            total_new += len(new_files)
            if verbose and (i + 1) % 100 == 0:
                print(f"  [{i+1}/{len(all_files)}] augmented → {total_new} new files")
        except Exception as e:
            if verbose:
                print(f"  [skip] {fp.name}: {e}")
            continue

    if verbose:
        print(f"\nDone: {len(all_files)} original → {total_new} augmented files")
    return total_new
