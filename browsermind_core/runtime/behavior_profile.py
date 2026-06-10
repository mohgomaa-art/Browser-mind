"""
behavior_profile.py — Human-like and fast automation behavior tuning.
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class BehaviorProfile:
    """
    Controls timing, retry, and interaction style for ExecutionEngine.

    Two canonical profiles:
      BehaviorProfile.fast()  — CI/batch: minimal delays, no randomness
      BehaviorProfile.human() — scrape-resistant sites: randomised delays
    """
    # Delays in milliseconds
    pre_action_delay_ms: float = 0.0
    post_action_delay_ms: float = 50.0
    between_keys_delay_ms: float = 0.0

    # Timeouts
    element_timeout_ms: int = 10_000
    navigation_timeout_ms: int = 30_000

    # Interaction style
    use_human_cursor: bool = False
    randomise_delays: bool = False
    click_position_jitter: int = 0   # pixels of random offset from element centre

    # Retry policy
    max_action_retries: int = 2
    retry_delay_ms: int = 500

    @classmethod
    def fast(cls) -> "BehaviorProfile":
        return cls(
            pre_action_delay_ms=0.0,
            post_action_delay_ms=50.0,
            between_keys_delay_ms=0.0,
            element_timeout_ms=10_000,
            navigation_timeout_ms=30_000,
            use_human_cursor=False,
            randomise_delays=False,
            click_position_jitter=0,
            max_action_retries=2,
            retry_delay_ms=500,
        )

    @classmethod
    def human(cls) -> "BehaviorProfile":
        return cls(
            pre_action_delay_ms=200.0,
            post_action_delay_ms=300.0,
            between_keys_delay_ms=80.0,
            element_timeout_ms=15_000,
            navigation_timeout_ms=30_000,
            use_human_cursor=True,
            randomise_delays=True,
            click_position_jitter=3,
            max_action_retries=3,
            retry_delay_ms=800,
        )

    def jittered_pre_delay(self) -> float:
        if not self.randomise_delays or self.pre_action_delay_ms <= 0:
            return self.pre_action_delay_ms
        return self.pre_action_delay_ms * (0.7 + random.random() * 0.6)

    def jittered_post_delay(self) -> float:
        if not self.randomise_delays or self.post_action_delay_ms <= 0:
            return self.post_action_delay_ms
        return self.post_action_delay_ms * (0.7 + random.random() * 0.6)

    def key_delay(self) -> float:
        if not self.randomise_delays or self.between_keys_delay_ms <= 0:
            return self.between_keys_delay_ms
        return self.between_keys_delay_ms * (0.5 + random.random() * 1.0)
