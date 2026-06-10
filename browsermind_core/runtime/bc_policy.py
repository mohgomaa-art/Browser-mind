"""BC policy inference adapter.

Loads ``bc_v2_checkpoint.pt`` once per process and exposes a single
``predict(role, action, step_seq) -> {action_id, action_probs, strategy_id,
strategy_probs}`` call. Imported lazily by the resolver so the runtime never
crashes when torch/the checkpoint is missing.

Closing the loop: the resolver consults the model to bias its strategy ladder
(e.g. try ``primary_semantic`` first when the model predicts it). Logged to
the OutcomeLedger so future training iterations measure the model's effect.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional


_DEFAULT_CHECKPOINT = "bc_v2_checkpoint.pt"


class BCPolicyAdapter:
    def __init__(self, checkpoint_path: Optional[str] = None):
        self.checkpoint_path = checkpoint_path or os.environ.get(
            "BROWSERMIND_BC_CHECKPOINT", _DEFAULT_CHECKPOINT
        )
        self._model = None
        self._vocabs: Dict[str, Dict[str, int]] = {}
        self._inv_action: List[str] = []
        self._inv_strategy: List[str] = []
        self._inv_site: List[str] = []
        self._device = None
        self._load_attempted = False
        self._stats = {"calls": 0, "errors": 0}

    @property
    def ready(self) -> bool:
        if not self._load_attempted:
            self._try_load()
        return self._model is not None

    @property
    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    # ------------------------------------------------------------------ load

    def _try_load(self) -> None:
        self._load_attempted = True
        try:
            import torch  # noqa: F401
        except ImportError:
            return
        path = Path(self.checkpoint_path)
        if not path.exists():
            return
        try:
            from train_bc_v2 import (
                BCPolicyV2, ACTION_VOCAB, STRATEGY_VOCAB, ROLE_VOCAB,
            )
            import torch
            ckpt = torch.load(str(path), map_location="cpu", weights_only=False)
            cfg = ckpt.get("config") or {}
            model = BCPolicyV2(
                embed_dim=cfg.get("embed_dim", 64),
                hidden=cfg.get("hidden", 128),
            )
            model.load_state_dict(ckpt["model_state"])
            model.eval()
            self._model = model
            self._device = torch.device("cpu")
            self._vocabs = ckpt.get("vocabs") or {
                "action": ACTION_VOCAB,
                "strategy": STRATEGY_VOCAB,
                "role": ROLE_VOCAB,
            }
            self._inv_action = _invert(self._vocabs["action"])
            self._inv_strategy = _invert(self._vocabs["strategy"])
            self._inv_site = _invert(self._vocabs.get("site", {}))
            print(f"  [BCPolicy] loaded {self.checkpoint_path}  "
                  f"action_acc={ckpt.get('action_acc', 0.0):.3f}"
                  f"  site_aware={'site' in self._vocabs}")
        except Exception as e:
            print(f"  [BCPolicy] load failed: {type(e).__name__}: {e}")
            self._model = None

    # ------------------------------------------------------------------ predict

    def predict(
        self,
        role: Optional[str],
        action: Optional[str],
        step_seq: int = 0,
        env_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return predicted action + strategy for one step. Dict on success, {} otherwise."""
        if not self.ready:
            return {}
        try:
            import torch
            r = self._vocabs["role"].get(
                (role or "").lower(), self._vocabs["role"].get("unknown", 0)
            )
            a = self._vocabs["action"].get(
                (action or "").lower(), self._vocabs["action"].get("unknown", 0)
            )
            site_vocab = self._vocabs.get("site", {})
            site_id = site_vocab.get((env_key or "").lower(), site_vocab.get("unknown", 0)) if site_vocab else None
            with torch.no_grad():
                site_tensor = torch.tensor([site_id], dtype=torch.long) if site_id is not None else None
                out = self._model(
                    torch.tensor([r], dtype=torch.long),
                    torch.tensor([a], dtype=torch.long),
                    torch.tensor([min(int(step_seq), 50)], dtype=torch.float32),
                    site_tensor,
                )
                a_logits = out["action_logits"][0]
                s_logits = out["strategy_logits"][0]
                a_probs = torch.softmax(a_logits, dim=-1).tolist()
                s_probs = torch.softmax(s_logits, dim=-1).tolist()
                a_id = int(torch.argmax(a_logits).item())
                s_id = int(torch.argmax(s_logits).item())
            self._stats["calls"] += 1
            return {
                "action_id": a_id,
                "action_label": self._inv_action[a_id] if a_id < len(self._inv_action) else "unknown",
                "action_probs": a_probs,
                "strategy_id": s_id,
                "strategy_label": self._inv_strategy[s_id] if s_id < len(self._inv_strategy) else "unknown",
                "strategy_probs": s_probs,
            }
        except Exception as e:
            self._stats["errors"] += 1
            print(f"  [BCPolicy] predict failed: {type(e).__name__}: {e}")
            return {}


def _invert(vocab: Dict[str, int]) -> List[str]:
    out = [""] * (max(vocab.values()) + 1) if vocab else []
    for k, v in vocab.items():
        if 0 <= v < len(out):
            out[v] = k
    return out


_SINGLETON: Optional[BCPolicyAdapter] = None


def shared() -> BCPolicyAdapter:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = BCPolicyAdapter()
    return _SINGLETON
