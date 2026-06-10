from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]

CANONICAL_ACTIONS: Dict[int, str] = {
    0: "navigate",
    1: "click",
    2: "type",
    3: "scroll",
    4: "wait",
    5: "extract",
    6: "go_back",
    7: "done",
}
ACTION_TO_ID: Dict[str, int] = {v: k for k, v in CANONICAL_ACTIONS.items()}
ACTION_ALIASES: Dict[str, str] = {
    "open_url": "navigate",
    "back": "go_back",
    "finish": "done",
    "complete": "done",
    "fail": "done",
}

DEFAULT_AUDIT_ROOTS = [
    "training",
    "sessions",
    "logs",
    "benchmarks",
    "scripts",
    "scratch",
    "pipeline",
    "pipelines",
    "pipeline_results",
]

EXCLUDED_DIR_NAMES = {
    ".git",
    "__pycache__",
    "agent_vault",
    "agent_vault_bin",
    "exports",
}

SOURCE_ROOTS = ["core", "model", "training", "scripts", "scratch", "main.py", "evaluate.py", "train_bc.py"]


def repo_path(path: str | Path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except Exception:
        return path.as_posix()


def resolve_roots(paths: Optional[Sequence[str | Path]] = None) -> List[Path]:
    roots = paths or DEFAULT_AUDIT_ROOTS
    resolved: List[Path] = []
    for item in roots:
        p = repo_path(item)
        if p.exists():
            resolved.append(p)
    return resolved


def iter_files(roots: Optional[Sequence[str | Path]], suffixes: Tuple[str, ...]) -> Iterator[Path]:
    for root in resolve_roots(roots):
        if root.is_file():
            if root.suffix.lower() in suffixes:
                yield root
            continue
        for fp in root.rglob("*"):
            if not fp.is_file():
                continue
            if any(part in EXCLUDED_DIR_NAMES for part in fp.parts):
                continue
            if fp.suffix.lower() in suffixes:
                yield fp


def load_json_file(path: Path) -> Tuple[Optional[Any], Optional[str]]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except UnicodeDecodeError:
        try:
            return json.loads(path.read_text(encoding="utf-8-sig")), None
        except Exception as exc:
            return None, str(exc)
    except Exception as exc:
        return None, str(exc)


def _looks_like_sample(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    return any(k in obj for k in ("expert_action", "graph", "goal", "url", "state")) and (
        "expert_action" in obj or "action_id" in obj or "action" in obj
    )


def iter_samples_from_data(data: Any) -> Iterator[Tuple[str, Dict[str, Any]]]:
    if isinstance(data, dict):
        if isinstance(data.get("samples"), list):
            for idx, sample in enumerate(data["samples"]):
                if isinstance(sample, dict):
                    yield f"samples[{idx}]", sample
            return
        if _looks_like_sample(data):
            yield "$", data
            return
        for key in ("steps", "records", "events"):
            if isinstance(data.get(key), list):
                for idx, sample in enumerate(data[key]):
                    if _looks_like_sample(sample):
                        yield f"{key}[{idx}]", sample
    elif isinstance(data, list):
        for idx, sample in enumerate(data):
            if isinstance(sample, dict) and _looks_like_sample(sample):
                yield f"[{idx}]", sample


def iter_dataset_samples(paths: Optional[Sequence[str | Path]] = None) -> Iterator[Tuple[Path, str, Dict[str, Any]]]:
    for fp in iter_files(paths, (".json", ".jsonl")):
        if fp.suffix.lower() == ".jsonl":
            try:
                with fp.open(encoding="utf-8") as f:
                    for idx, line in enumerate(f):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        for loc, sample in iter_samples_from_data(obj):
                            yield fp, f"line[{idx + 1}].{loc}", sample
            except Exception:
                continue
            continue

        data, _ = load_json_file(fp)
        if data is None:
            continue
        for loc, sample in iter_samples_from_data(data):
            yield fp, loc, sample


def normalize_action_name(value: Any) -> str:
    name = str(value or "").strip().lower()
    if "." in name:
        name = name.split(".")[-1]
    return ACTION_ALIASES.get(name, name)


def extract_action(sample: Dict[str, Any]) -> Dict[str, Any]:
    action = sample.get("expert_action")
    if not isinstance(action, dict):
        action = sample.get("action")
    if not isinstance(action, dict):
        action = sample
    return action if isinstance(action, dict) else {}


def extract_action_id_and_name(sample: Dict[str, Any]) -> Tuple[Optional[int], str, Dict[str, Any]]:
    action = extract_action(sample)
    raw_id = action.get("action_id")
    action_id: Optional[int] = None
    if raw_id is not None and raw_id != "":
        try:
            action_id = int(raw_id)
        except Exception:
            action_id = None

    raw_name = action.get("type") or action.get("action_type") or action.get("name")
    action_name = normalize_action_name(raw_name)
    if action_id is None and action_name in ACTION_TO_ID:
        action_id = ACTION_TO_ID[action_name]
    return action_id, action_name, action


def domain_from_url(url: str) -> str:
    if not url:
        return "unknown"
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        return (parsed.netloc or parsed.path.split("/")[0]).lower().replace("www.", "") or "unknown"
    except Exception:
        return "unknown"


def graph_nodes(sample: Dict[str, Any]) -> List[Dict[str, Any]]:
    graph = sample.get("graph") if isinstance(sample.get("graph"), dict) else {}
    nodes = graph.get("nodes", [])
    return nodes if isinstance(nodes, list) else []


def graph_edges(sample: Dict[str, Any]) -> List[Any]:
    graph = sample.get("graph") if isinstance(sample.get("graph"), dict) else {}
    edges = graph.get("edges", [])
    return edges if isinstance(edges, list) else []


def stable_json_hash(obj: Any, size: int = 16) -> str:
    payload = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:size]


def graph_signature(sample: Dict[str, Any]) -> str:
    nodes = []
    for node in graph_nodes(sample):
        if not isinstance(node, dict):
            continue
        nodes.append(
            {
                "idx": node.get("idx"),
                "role": node.get("role", "generic"),
                "name": str(node.get("name", ""))[:120],
                "value": str(node.get("value", ""))[:80],
                "depth": node.get("depth", 0),
            }
        )
    return stable_json_hash({"nodes": nodes, "edges": graph_edges(sample)})


def state_family_key(sample: Dict[str, Any]) -> str:
    roles = []
    for node in graph_nodes(sample):
        role = str(node.get("role", "generic")) if isinstance(node, dict) else "generic"
        if role in {"button", "link", "textbox", "checkbox", "radio", "combobox", "menuitem"}:
            roles.append(role)
    return ",".join(roles) or "empty"


def sample_dedup_key(sample: Dict[str, Any]) -> str:
    action_id, action_name, action = extract_action_id_and_name(sample)
    raw = {
        "url": sample.get("url", ""),
        "goal": sample.get("goal", ""),
        "action_id": action_id,
        "action_name": action_name,
        "element_idx": action.get("element_idx"),
        "graph": graph_signature(sample),
    }
    return stable_json_hash(raw)


def trajectory_signature(samples: Sequence[Dict[str, Any]]) -> str:
    return stable_json_hash([sample_dedup_key(sample) for sample in samples])


def source_files() -> Iterator[Path]:
    for root in SOURCE_ROOTS:
        p = repo_path(root)
        if not p.exists():
            continue
        if p.is_file():
            yield p
            continue
        for fp in p.rglob("*.py"):
            if any(part in EXCLUDED_DIR_NAMES for part in fp.parts):
                continue
            yield fp


def find_done_id_mismatches() -> List[Dict[str, Any]]:
    patterns = [
        re.compile(r"[\"']done[\"']\s*:\s*9"),
        re.compile(r"[\"']action_id[\"']\s*:\s*9"),
        re.compile(r"action_id\s*=\s*9"),
    ]
    refs: List[Dict[str, Any]] = []
    for fp in source_files():
        try:
            lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for lineno, line in enumerate(lines, start=1):
            if any(p.search(line) for p in patterns):
                refs.append({"file": rel(fp), "line": lineno, "text": line.strip()[:180]})
    return refs


def counter_to_sorted_dict(counter: Counter) -> Dict[str, int]:
    return {str(k): int(v) for k, v in counter.most_common()}
