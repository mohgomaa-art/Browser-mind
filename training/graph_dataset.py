"""
BrowserMind — GraphDataset
============================
PyTorch Dataset for spec-format session JSON files.
Implements all DATA QUALITY RULES from spec Section 7.

Expected file format: a JSON array of samples (as output by session_adapter.py)
Each sample conforms to Section 2 schema.

Quality rules enforced:
  1. Never element_idx=0 as fallback → element_idx=None → skip element_loss
  2. Failed steps (success=False): action_loss only (weight=0.1), element_loss=0
  3. Deduplication by (url, goal, action_id, element_idx)
  4. Min nodes per graph: 2
  5. Max nodes: 80 (truncate from bottom — by position in node list)

Train/val split at session-file level (80/20).
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any
from PIL import Image


from transformers import CLIPImageProcessor
import torch
from torch.utils.data import Dataset
from training.graph_builder import prune_graph

# Mapper for schema robustness (from Section 6)
ACTION_TYPES = {
    0: "navigate",  1: "click",   2: "type",   3: "scroll",
    4: "wait",      5: "extract", 6: "go_back", 7: "done",
}
ACTION_TO_ID = {v: k for k, v in ACTION_TYPES.items()}

def _get_action_id(ea: Dict) -> Optional[int]:
    """Robustly extract action_id from expert_action dict, handling 'type' or 'action_type' aliases."""
    # 1. Direct match
    aid = ea.get("action_id")
    if aid is not None:
        return int(aid)
        
    # 2. Key aliases
    type_str = ea.get("type") or ea.get("action_type")
    if type_str:
        type_str = type_str.lower().strip()
        # Handle variants like "open_url" -> "navigate"
        if type_str == "open_url": type_str = "navigate"
        return ACTION_TO_ID.get(type_str)
        
    return None

# ──────────────────────────────────────────────────────────────────────────────
#  GraphSample  — what the dataset yields per item
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class GraphSample:
    goal:        str
    nodes:       List[Dict]        # [{idx, role, name, value, focused, depth}]
    edges:       List              # [[src, tgt, etype], ...]
    action_id:   int               # 0–7
    element_idx: Optional[int]     # None → skip element_loss
    success:     bool
    weight:      float             # 1.0 if success else 0.1
    url:         str = ""
    step:        int = 0
    image:       Optional[torch.Tensor] = None # [3, 224, 224] tensor
    screenshot:  str = ""          # Path to .png file




# ──────────────────────────────────────────────────────────────────────────────
#  Goal Augmentation (Round 8)
# ──────────────────────────────────────────────────────────────────────────────
GOAL_PARAPHRASES = {
    "search for {topic}": [
        "search for {topic}", "find {topic}", "look up {topic}", "explore {topic}",
        "I need information about {topic}", "show me results for {topic}", "query: {topic}",
    ],
    "click {element}": [
        "click {element}", "press {element}", "tap on {element}", "select {element}",
    ],
}

def _extract_goal_topic(goal: str) -> str:
    g = (goal or "").strip()
    if not g: return "information"
    g_low = g.lower()
    for prefix in ("search for ", "find ", "look up ", "explore ", "query: "):
        if g_low.startswith(prefix):
            topic = g[len(prefix):].strip()
            return topic or g
    return g

def paraphrase_goal(goal: str, max_variants: int = 5) -> List[str]:
    """Generates up to 5 paraphrases for a goal."""
    topic = _extract_goal_topic(goal)
    res = [goal]
    if "click" in goal.lower():
        element = goal.lower().replace("click", "").strip()
        templates = GOAL_PARAPHRASES["click {element}"]
        res = [t.format(element=element) for t in templates]
    else:
        templates = GOAL_PARAPHRASES["search for {topic}"]
        res = [t.format(topic=topic) for t in templates]
    
    unique_res = []
    seen = set()
    for r in res:
        if r.lower() not in seen:
            unique_res.append(r)
            seen.add(r.lower())
    return unique_res[:max_variants]

# ──────────────────────────────────────────────────────────────────────────────
#  Data quality helpers (Section 7)
# ──────────────────────────────────────────────────────────────────────────────

def _dedup_key(sample: Dict) -> str:
    """unique key for deduplication: (url, goal, action_id, element_idx)"""
    ea  = sample.get("expert_action", {})
    url = sample.get("url", "")
    g   = sample.get("goal", "")
    aid = _get_action_id(ea)
    eid = ea.get("element_idx", None)
    raw = f"{url}|{g}|{aid}|{eid}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _validate_sample(sample: Dict) -> Tuple[bool, str]:
    """Returns (valid, reason). Implements all skip rules from Section 2 + Section 7."""
    goal = sample.get("goal", "")
    if not goal:
        return False, "missing_goal"

    graph = sample.get("graph", {})
    nodes = graph.get("nodes", [])

    # Required fields (Section 2)
    if not nodes:
        return False, "empty_nodes"

    ea = sample.get("expert_action", {})
    if ea is None:
        return False, "missing_expert_action"

    action_id = _get_action_id(ea)
    if action_id is None or not (0 <= action_id <= 7):
        return False, "invalid_action_id"

    element_idx = ea.get("element_idx")
    if element_idx is not None and int(element_idx) >= len(nodes):
        return False, "element_idx_oob"

    # Quality rule 4: min nodes
    if len(nodes) < 2:
        return False, "too_few_nodes"

    return True, ""


def _apply_quality_rules(sample: Dict) -> Optional[GraphSample]:
    """
    Validates and transforms a raw dict into a GraphSample,
    applying all Section 7 quality rules.
    Returns None if the sample should be skipped entirely.
    """
    valid, reason = _validate_sample(sample)
    if not valid:
        return None

    graph   = sample["graph"]
    nodes_raw = graph["nodes"]
    edges_raw = graph.get("edges", [])
    
    # [Round 8] Apply Pruning
    nodes, edges = prune_graph(nodes_raw, edges_raw)

    # Pruning can remove most nodes; skip unusable graphs.
    if len(nodes) < 2:
        return None
    
    ea      = sample["expert_action"]
    action_id   = _get_action_id(ea)
    element_idx = ea.get("element_idx")
    
    # If pruning removed the target element, demote to action-only or skip
    if element_idx is not None:
        element_idx = int(element_idx)
        # Find new index of the target element
        new_idx = None
        for i, n in enumerate(nodes):
            if n.get("idx") == element_idx: # idx is the original index
                new_idx = i
                break
        element_idx = new_idx

    success = bool(sample.get("success", True))

    # [Deprecated Rule 5] We now use dynamic prune_graph instead of just [:80]
    # But we still enforce a hard 80 limit just in case.
    if len(nodes) > 80:
        nodes = nodes[:80]
        edges = [e for e in edges if e[0] < 80 and e[1] < 80]
        if element_idx is not None and element_idx >= 80:
            element_idx = None

    # Quality rule 2: failed steps use action_loss only, no element_loss
    if not success:
        element_idx = None

    # Success weighting
    weight = 1.0 if success else 0.1
    
    # Screenshot handling (Visual Upgrade)
    screenshot_name = sample.get("screenshot") or sample.get("state", {}).get("screenshot")

    return GraphSample(
        goal        = sample.get("goal", ""),
        nodes       = nodes,
        edges       = edges,
        action_id   = action_id,
        element_idx = element_idx,
        success     = success,
        weight      = weight,
        url         = sample.get("url", ""),
        step        = sample.get("step", 0),
        screenshot  = screenshot_name or ""
    )


# ──────────────────────────────────────────────────────────────────────────────
#  GraphDataset
# ──────────────────────────────────────────────────────────────────────────────
class GraphDataset(Dataset):
    """
    Loads spec-format JSON files from data_dir and yields GraphSample objects.

    split:  "train" | "val" | "all"
    val_ratio:  fraction of session files held out for validation (default 0.2)
    seed:  controls train/val file split shuffle
    """

    def __init__(
        self,
        data_dir:  Union[str, Path, List[Path]],
        split:     str   = "all",
        val_ratio: float = 0.15,
        seed:      int   = 42,
        augment:   bool  = True,
    ):
        if isinstance(data_dir, list):
            self.data_dir = None
            self.file_list = data_dir
        else:
            self.data_dir  = Path(data_dir)
            self.file_list = None

        self.split     = split
        self.val_ratio = val_ratio
        self.seed      = seed
        self.augment   = augment

        self.samples: List[GraphSample] = []
        self._load_stats = {
            "files_total":    0,
            "files_loaded":   0,
            "samples_raw":    0,
            "samples_kept":   0,
            "drop_reasons":   {},
            "duplicates":     0,
        }
        
        # [Visual Upgrade] Initialize CLIP processor
        try:
            self.processor = CLIPImageProcessor.from_pretrained("openai/clip-vit-base-patch32")
        except Exception:
            self.processor = None

        self._load()
        self._init_vision()

    def _init_vision(self):
        try:
            from transformers import CLIPImageProcessor
            self.processor = CLIPImageProcessor.from_pretrained("openai/clip-vit-base-patch32")
        except Exception as e:
            print(f"⚠️  GraphDataset: failed to init CLIP processor: {e}")
            self.processor = None

    # ── Loading ──────────────────────────────────────────────────────────────

    def _load(self):
        if self.file_list is not None:
            all_files = sorted(self.file_list)
        else:
            all_files = sorted(self.data_dir.glob("*.json"))

        if not all_files:
            msg = f"no JSON files in {self.data_dir}" if self.data_dir else "empty file list"
            print(f"[WARN] GraphDataset: {msg}")
            return

        self._load_stats["files_total"] = len(all_files)

        # Train/val split at DOMAIN level (System of Proof).
        # We need to map each file to its primary domain to ensure zero leakage.
        domain_to_files = {}
        for fp in all_files:
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                samples = data.get("samples", [data]) if isinstance(data, dict) else data
                if not samples: continue
                # Use the first sample's URL to determine the file's domain
                url = samples[0].get("url", "")
                domain = url.split("//")[-1].split("/")[0].replace("www.", "")
                if not domain: domain = "unknown"
                if domain not in domain_to_files:
                    domain_to_files[domain] = []
                domain_to_files[domain].append(fp)
            except Exception:
                continue

        domains = sorted(list(domain_to_files.keys()))
        rng = random.Random(self.seed)
        rng.shuffle(domains)

        if len(domains) == 1:
            train_domains = domains
            val_domains = domains
        else:
            n_val = max(1, int(len(domains) * self.val_ratio))
            val_domains = domains[:n_val]
            train_domains = domains[n_val:]

        if self.split == "val":
            selected_domains = val_domains
        elif self.split == "train":
            selected_domains = train_domains
        else:
            selected_domains = domains

        files = []
        for d in selected_domains:
            files.extend(domain_to_files[d])

        seen_keys: set = set()

        for fp in files:
            try:
                with open(fp, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                print(f"  ⚠️  Could not load {fp.name}: {e}")
                continue

            self._load_stats["files_loaded"] += 1

            # data may be a list of samples or a single dict with "samples" key
            if isinstance(data, dict):
                raw_samples = data.get("samples", [data])
            elif isinstance(data, list):
                raw_samples = data
            else:
                continue

            for raw in raw_samples:
                self._load_stats["samples_raw"] += 1
                
                # Fix screenshot paths to be absolute (Visual Upgrade)
                if "state" in raw and raw["state"].get("screenshot_path"):
                    raw["state"]["screenshot"] = str(fp.parent / raw["state"]["screenshot_path"])
                elif raw.get("screenshot"):
                    raw["screenshot"] = str(fp.parent / raw["screenshot"])


                # Quality rule 3: deduplication
                key = _dedup_key(raw)
                if key in seen_keys:
                    self._load_stats["duplicates"] += 1
                    continue
                seen_keys.add(key)

                # Goal Augmentation (Round 8)
                goals = paraphrase_goal(raw.get("goal","")) if self.augment else [raw.get("goal","")]
                
                base_sample = _apply_quality_rules(raw)
                if base_sample is None:
                    self._increment_drop(raw)
                    continue

                for g in goals:
                    # Create a new sample with the same graph but different goal
                    s = GraphSample(
                        goal=g,
                        nodes=base_sample.nodes,
                        edges=base_sample.edges,
                        action_id=base_sample.action_id,
                        element_idx=base_sample.element_idx,
                        success=base_sample.success,
                        weight=base_sample.weight,
                        url=base_sample.url,
                        step=base_sample.step
                    )
                    self.samples.append(s)
                    self._load_stats["samples_kept"] += 1

        print(
            f"GraphDataset [{self.split}]: "
            f"{self._load_stats['samples_kept']} samples from "
            f"{self._load_stats['files_loaded']} files "
            f"(dropped {self._load_stats['samples_raw'] - self._load_stats['samples_kept']}, "
            f"dupes {self._load_stats['duplicates']})"
        )

    def _increment_drop(self, raw: Dict):
        valid, reason = _validate_sample(raw)
        r = reason or "unknown"
        d = self._load_stats["drop_reasons"]
        d[r] = d.get(r, 0) + 1

    # ── Dataset interface ────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> GraphSample:
        sample = self.samples[idx]
        
        # Lazy load image
        if sample.screenshot and self.processor and sample.image is None:
            try:
                img = Image.open(sample.screenshot).convert("RGB")
                pixel_values = self.processor(images=img, return_tensors="pt")["pixel_values"]
                # Store it in the sample to avoid reloading (if memory permits)
                # For 6GB VRAM safety, we might NOT want to store all tensors in RAM.
                # But GraphDataset usually holds everything.
                # Given we might have 10k+ samples, [3, 224, 224] * 10k = 6GB RAM.
                # Let's keep it lazy (don't cache in GraphSample.image).
                sample.image = pixel_values.squeeze(0) 
            except Exception as e:
                # print(f"⚠️  GraphDataset: failed to load image {sample.screenshot}: {e}")
                pass

        return sample

    # ── Reporting ────────────────────────────────────────────────────────────

    def stats(self) -> Dict:
        return self._load_stats

    def print_stats(self):
        s   = self._load_stats
        pct = s["samples_kept"] / max(s["samples_raw"], 1) * 100
        print(f"\n  GraphDataset stats ({self.split}):")
        print(f"    Files   : {s['files_loaded']}/{s['files_total']}")
        print(f"    Samples : {s['samples_kept']}/{s['samples_raw']} ({pct:.0f}%)")
        print(f"    Dupes   : {s['duplicates']}")
        if s["drop_reasons"]:
            print(f"    Drops   :")
            for r, c in sorted(s["drop_reasons"].items(), key=lambda x: -x[1]):
                print(f"      {c:>4}× {r}")


# ──────────────────────────────────────────────────────────────────────────────
#  Collate  — variable-length graphs → per-sample list
# ──────────────────────────────────────────────────────────────────────────────
def collate_graph_samples(batch: List[GraphSample]) -> List[GraphSample]:
    """
    Simple collate: returns the batch as-is (a list).
    Each sample is processed individually by the model since graph sizes vary.
    The training loop iterates over items in the batch.
    """
    return batch


# ──────────────────────────────────────────────────────────────────────────────
#  Quick test
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    data_dir = sys.argv[1] if len(sys.argv) > 1 else "training/spec_sessions"
    ds = GraphDataset(data_dir, split="all")
    ds.print_stats()

    if len(ds) > 0:
        s = ds[0]
        print(f"\n  Sample[0]:")
        print(f"    goal       = {s.goal!r}")
        print(f"    nodes      = {len(s.nodes)}")
        print(f"    edges      = {len(s.edges)}")
        print(f"    action_id  = {s.action_id}")
        print(f"    element_idx= {s.element_idx}")
        print(f"    success    = {s.success}")
        print(f"    weight     = {s.weight}")
