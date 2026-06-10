"""Transfer Arena — cross-site capability transfer benchmark.

Answers the question: does a learned capability actually transfer to never-seen
environments, or is it site-specific memorisation?

Architecture
────────────
For each CapabilityFamily the Arena holds:
  training_envs   Sites seen during learning (capability priors were built here).
  test_envs       Sites never seen during learning (true transfer signal).

Benchmark logic
───────────────
Pull all workflow_instance OutcomeRecords from the ledger.
Split by environment_instance against the env group maps.
Compute success rate on training envs and test envs separately.
TransferScore.transfer_delta = test_rate - training_rate.

A capability "transfers" when test_rate ≥ training_rate - TRANSFER_TOLERANCE
(delta ≥ -0.10 by default). This tolerates a small performance gap attributable
to interface variation while still demanding real cross-site competence.

Design constraints
──────────────────
- No LLM in the evaluation path.
- No live browser required — runs purely on OutcomeLedger records.
- Deterministic: same ledger → same scores every time.
- Additive: adding more environments (training or test) to ARENA_CONFIGS does
  NOT break existing scores; it only changes which records fall into which group.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

TRANSFER_TOLERANCE: float = 0.10  # test_rate may be this far below training_rate and still pass


@dataclass
class TransferArenaConfig:
    """Defines the train/test split for one capability family."""
    family: str
    training_envs: List[str]   # known envs; priors should exist here
    test_envs: List[str]       # never-seen envs; true transfer signal
    outcome_types: List[str] = field(default_factory=lambda: ["replay_run"])
    # Optional: filter to records whose template_name contains one of these strings.
    # Empty list = no template filter.
    template_prefixes: List[str] = field(default_factory=list)


@dataclass
class TransferScore:
    """Result of one Transfer Arena evaluation run."""
    family: str
    training_envs: List[str]
    test_envs: List[str]
    training_total: int
    training_success: int
    test_total: int
    test_success: int

    @property
    def training_rate(self) -> Optional[float]:
        if self.training_total == 0:
            return None
        return round(self.training_success / self.training_total, 4)

    @property
    def test_rate(self) -> Optional[float]:
        if self.test_total == 0:
            return None
        return round(self.test_success / self.test_total, 4)

    @property
    def transfer_delta(self) -> Optional[float]:
        tr = self.training_rate
        te = self.test_rate
        if tr is None or te is None:
            return None
        return round(te - tr, 4)

    @property
    def is_transferring(self) -> Optional[bool]:
        """True iff test performance is within TRANSFER_TOLERANCE of training."""
        delta = self.transfer_delta
        if delta is None:
            return None
        return delta >= -TRANSFER_TOLERANCE

    def summary(self) -> str:
        tr = f"{self.training_rate:.2%}" if self.training_rate is not None else "n/a"
        te = f"{self.test_rate:.2%}" if self.test_rate is not None else "n/a"
        delta = f"{self.transfer_delta:+.2%}" if self.transfer_delta is not None else "n/a"
        verdict = (
            "TRANSFERS" if self.is_transferring
            else "MEMORISED" if self.is_transferring is False
            else "NO_DATA"
        )
        return (
            f"[TransferArena/{self.family}] "
            f"train={tr} ({self.training_success}/{self.training_total}) "
            f"test={te} ({self.test_success}/{self.test_total}) "
            f"delta={delta} verdict={verdict}"
        )


# ── Predefined arena configurations ──────────────────────────────────────────
#
# Training envs are sites where BrowserMind already has recorded executions.
# Test envs are structurally similar but never used for prior building.
# Add more environments freely — old scores remain valid.

ARENA_CONFIGS: Dict[str, TransferArenaConfig] = {
    "authentication": TransferArenaConfig(
        family="authentication",
        training_envs=["github", "google", "saucedemo"],
        test_envs=["gitlab", "huggingface", "discord", "bitbucket"],
        template_prefixes=["login", "sign_in", "auth", "account"],
    ),
    "search": TransferArenaConfig(
        family="search",
        training_envs=["amazon", "github", "duckduckgo"],
        test_envs=["ebay", "aliexpress", "etsy", "youtube"],
        template_prefixes=["search", "find", "query"],
    ),
    "community": TransferArenaConfig(
        family="community",
        training_envs=["reddit"],
        test_envs=["discourse", "xenForo", "phpbb", "lemmy"],
        template_prefixes=["post", "reply", "comment", "upvote", "subscribe"],
    ),
    "form_fill": TransferArenaConfig(
        family="form_fill",
        training_envs=["saucedemo", "the-internet.herokuapp.com"],
        test_envs=["automationpractice", "demoqa", "practice.automationtesting"],
        template_prefixes=["register", "checkout", "contact", "form"],
    ),
}


class TransferArena:
    """Evaluates cross-site transfer for a capability family using ledger records.

    No browser. No live execution. Purely post-hoc analysis of OutcomeLedger.
    """

    def __init__(self, configs: Optional[Dict[str, TransferArenaConfig]] = None):
        self.configs = configs or ARENA_CONFIGS

    def evaluate(self, family: str, ledger) -> TransferScore:
        """Compute TransferScore for the given family from ledger records.

        Args:
            family:  Key into ARENA_CONFIGS (or self.configs).
            ledger:  OutcomeLedger instance (or any object with .records attribute).

        Returns:
            TransferScore with populated counters and computed rates.
        """
        cfg = self.configs.get(family)
        if cfg is None:
            raise ValueError(f"No TransferArenaConfig for family={family!r}. "
                             f"Available: {list(self.configs)}")

        training_set = set(cfg.training_envs)
        test_set = set(cfg.test_envs)
        outcome_types = set(cfg.outcome_types)

        training_total = training_success = 0
        test_total = test_success = 0

        for r in getattr(ledger, "records", []):
            # Filter by scope and outcome_type
            if getattr(r, "scope", "") != "workflow_instance":
                continue
            if getattr(r, "outcome_type", "") not in outcome_types:
                continue

            env = getattr(r, "environment_instance", "") or ""

            # Optional template prefix filter
            if cfg.template_prefixes:
                tmpl = str((getattr(r, "metrics", {}) or {}).get("template_name", "") or "")
                if not any(tmpl.lower().startswith(p.lower()) for p in cfg.template_prefixes):
                    continue

            success = bool(getattr(r, "success", False))

            if env in training_set:
                training_total += 1
                if success:
                    training_success += 1
            elif env in test_set:
                test_total += 1
                if success:
                    test_success += 1

        return TransferScore(
            family=family,
            training_envs=list(cfg.training_envs),
            test_envs=list(cfg.test_envs),
            training_total=training_total,
            training_success=training_success,
            test_total=test_total,
            test_success=test_success,
        )

    def evaluate_all(self, ledger) -> Dict[str, TransferScore]:
        """Evaluate every configured family. Returns {family: TransferScore}."""
        return {family: self.evaluate(family, ledger) for family in self.configs}

    def report(self, ledger) -> str:
        """Human-readable transfer report across all families."""
        scores = self.evaluate_all(ledger)
        lines = ["=== Transfer Arena Report ==="]
        for score in scores.values():
            lines.append(score.summary())
        return "\n".join(lines)
