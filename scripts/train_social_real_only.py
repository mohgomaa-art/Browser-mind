"""
Train BrowserMind on real social-media actions only.

What this script does:
1) Scans session JSON files from source directories.
2) Normalizes old-format and spec-format samples.
3) Keeps only REAL social-media samples.
4) Excludes synthetic/fake/simulated datasets.
5) Redacts sensitive text before writing curated data.
6) Optionally launches Behavioral Cloning on the curated dataset.

Usage examples:
  python scripts/train_social_real_only.py --prepare-only
  python scripts/train_social_real_only.py --epochs 8 --batch-size 24
  python scripts/train_social_real_only.py --resume --ckpt checkpoints/browsermind_social_real_only.pt
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.privacy import (
    redact_sensitive_text,
    sanitize_expert_action,
    sanitize_goal_for_storage,
    sanitize_graph_for_storage,
)
from training.session_adapter import SessionAdapter


SOCIAL_HOST_TOKENS = (
    "facebook.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "linkedin.com",
    "reddit.com",
    "youtube.com",
    "tiktok.com",
    "pinterest.com",
    "snapchat.com",
    "threads.com",
    "threads.net",
    "discord.com",
    "discord.gg",
    "mastodon",
)

SOCIAL_GOAL_TOKENS = (
    "facebook",
    "instagram",
    "twitter",
    "x.com",
    "linkedin",
    "reddit",
    "youtube",
    "tiktok",
    "pinterest",
    "snapchat",
    "threads",
    "discord",
    "mastodon",
)

FAKE_FILE_PATTERNS = (
    "s_syn_",
    "s_gold_syn",
    "synthetic",
    "simulated",
    "mock",
    "fake",
    "social_network_",
    "generate_500",
)

FAKE_GOAL_PATTERNS = (
    "social_network_",
    "simulated",
    "synthetic",
    "mock",
    "fake",
)


def _normalize_host(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    try:
        return urlparse(raw).netloc.lower()
    except Exception:
        return ""


def _is_synthetic_file(path: Path) -> bool:
    name_l = path.name.lower()
    return any(tok in name_l for tok in FAKE_FILE_PATTERNS)


def _host_matches_token(host: str, token: str) -> bool:
    if not host:
        return False
    host = host.lower().strip()
    token = token.lower().strip()
    return host == token or host.endswith("." + token)


def _text_mentions_token(text: str, token: str) -> bool:
    if not text:
        return False
    pattern = rf"(^|[^a-z0-9]){re.escape(token)}($|[^a-z0-9])"
    return re.search(pattern, text.lower()) is not None


def _is_real_social_sample(sample: dict[str, Any]) -> bool:
    goal_l = str(sample.get("goal", "")).lower()
    host_l = _normalize_host(str(sample.get("url", "")))

    if any(tok in goal_l for tok in FAKE_GOAL_PATTERNS):
        return False
    if re.search(r"social-\d+\.net", host_l):
        return False

    host_hit = any(_host_matches_token(host_l, tok) for tok in SOCIAL_HOST_TOKENS)
    goal_hit = any(_text_mentions_token(goal_l, tok) for tok in SOCIAL_GOAL_TOKENS)
    # For strict social-only training, require social host when URL is present.
    if host_l:
        return host_hit

    # For samples without URL, rely on explicit platform mention in the goal.
    return goal_hit


def _sanitize_sample(sample: dict[str, Any]) -> dict[str, Any]:
    out = dict(sample)
    goal = sanitize_goal_for_storage(str(out.get("goal", "")))
    out["goal"] = goal
    out["url"] = redact_sensitive_text(str(out.get("url", "")))

    graph = out.get("graph", {})
    if isinstance(graph, dict):
        out["graph"] = sanitize_graph_for_storage(graph)

    expert = out.get("expert_action", {})
    if isinstance(expert, dict):
        out["expert_action"] = sanitize_expert_action(expert, goal_text=goal)

    return out


def _extract_action_label(sample: dict[str, Any]) -> str:
    expert = sample.get("expert_action", {})
    if isinstance(expert, dict):
        t = str(expert.get("type", "")).strip().lower()
        if t:
            return t
        aid = expert.get("action_id")
        if aid is not None:
            return f"id_{aid}"
    return "unknown"


def _iter_source_files(source_dir: Path) -> list[Path]:
    if not source_dir.exists():
        return []
    if source_dir.is_file() and source_dir.suffix.lower() == ".json":
        return [source_dir]
    return sorted(source_dir.rglob("*.json"))


def _normalize_file_samples(path: Path, adapter: SessionAdapter) -> list[dict[str, Any]]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    out: list[dict[str, Any]] = []

    def add_from_item(item: Any) -> None:
        if not isinstance(item, dict):
            return

        if "graph" in item and "expert_action" in item:
            out.append(item)
            return

        if "state" in item and "action" in item:
            converted = adapter._convert_sample(item)  # noqa: SLF001 - intentionally reusing adapter logic
            if converted:
                out.append(converted)

    if isinstance(doc, list):
        for item in doc:
            add_from_item(item)
    elif isinstance(doc, dict):
        if isinstance(doc.get("samples"), list):
            for item in doc["samples"]:
                add_from_item(item)
        else:
            add_from_item(doc)

    return out


def curate_social_real_dataset(source_dirs: list[Path], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    removed_stale_files = 0
    for old_json in output_dir.rglob("*.json"):
        old_json.unlink(missing_ok=True)
        removed_stale_files += 1

    adapter = SessionAdapter(input_dir="training/sessions", output_dir=str(output_dir))

    files_scanned = 0
    files_written = 0
    samples_seen = 0
    samples_kept = 0

    action_counts: Counter[str] = Counter()
    host_counts: Counter[str] = Counter()

    for src in source_dirs:
        for fp in _iter_source_files(src):
            files_scanned += 1

            if _is_synthetic_file(fp):
                continue

            normalized = _normalize_file_samples(fp, adapter)
            if not normalized:
                continue

            kept_for_file: list[dict[str, Any]] = []
            for sample in normalized:
                samples_seen += 1
                if not _is_real_social_sample(sample):
                    continue

                safe = _sanitize_sample(sample)
                kept_for_file.append(safe)
                samples_kept += 1

                action_counts[_extract_action_label(safe)] += 1
                host_counts[_normalize_host(str(safe.get("url", "")))] += 1

            if not kept_for_file:
                continue

            out_path = output_dir / fp.name
            out_path.write_text(json.dumps(kept_for_file, indent=2, ensure_ascii=False), encoding="utf-8")
            files_written += 1

    return {
        "removed_stale_files": removed_stale_files,
        "files_scanned": files_scanned,
        "files_written": files_written,
        "samples_seen": samples_seen,
        "samples_kept": samples_kept,
        "action_counts": dict(sorted(action_counts.items())),
        "host_counts": dict(sorted(host_counts.items())),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Real-only social-media BC training pipeline")
    p.add_argument(
        "--sources",
        nargs="+",
        default=[
            "training/social_sessions",
            "training/massive_sessions",
            "training/spec_sessions",
            "training/sessions",
        ],
        help="Source session dirs/files to scan",
    )
    p.add_argument(
        "--output",
        default="training/social_real_only",
        help="Curated social real-only spec sessions output dir",
    )
    p.add_argument("--prepare-only", action="store_true", help="Only build curated dataset, do not train")

    p.add_argument("--ckpt", default="checkpoints/browsermind_social_real_only.pt")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--epochs", type=int, default=10)
    p.add_argument("--batch-size", type=int, default=24)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--val-ratio", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--target-action-acc", type=float, default=0.90)
    return p.parse_args()


def main() -> None:
    args = parse_args()

    source_dirs = [Path(p) for p in args.sources]
    output_dir = Path(args.output)

    print("=" * 72)
    print("[social-real] Curating REAL social-media training set (no synthetic/fake)")
    print(f"[social-real] sources: {', '.join(str(p) for p in source_dirs)}")
    print(f"[social-real] output : {output_dir}")
    print("=" * 72)

    stats = curate_social_real_dataset(source_dirs, output_dir)

    print(f"[social-real] removed_stale_files={stats['removed_stale_files']}")
    print(f"[social-real] files_scanned={stats['files_scanned']}")
    print(f"[social-real] files_written={stats['files_written']}")
    print(f"[social-real] samples_seen={stats['samples_seen']}")
    print(f"[social-real] samples_kept={stats['samples_kept']}")

    print("[social-real] action_breakdown:")
    for k, v in stats["action_counts"].items():
        print(f"  - {k}: {v}")

    print("[social-real] host_breakdown:")
    for k, v in stats["host_counts"].items():
        host_name = k or "<missing_host>"
        print(f"  - {host_name}: {v}")

    if stats["samples_kept"] == 0:
        print("[social-real] ERROR: no real social samples found after filtering.")
        sys.exit(1)

    if args.prepare_only:
        print("[social-real] prepare-only complete.")
        return

    cmd = [
        sys.executable,
        "train_bc.py",
        "--data",
        str(output_dir),
        "--ckpt",
        str(args.ckpt),
        "--epochs",
        str(args.epochs),
        "--batch-size",
        str(args.batch_size),
        "--lr",
        str(args.lr),
        "--val-ratio",
        str(args.val_ratio),
        "--seed",
        str(args.seed),
        "--target-action-acc",
        str(args.target_action_acc),
        "--no-augment",
    ]
    if args.resume:
        cmd.append("--resume")

    print("[social-real] Starting Behavioral Cloning on curated social real-only data...")
    print("[social-real] cmd: " + " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(ROOT))


if __name__ == "__main__":
    main()
