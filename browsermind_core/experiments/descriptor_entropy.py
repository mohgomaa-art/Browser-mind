"""Descriptor entropy instrumentation."""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict

from browsermind_core.experiments.reliability_telemetry import telemetry_event


DESCRIPTOR_FIELDS = (
    "role",
    "name",
    "accessible_name",
    "text_content",
    "placeholder",
    "container_label",
    "container_data_test",
    "true_role",
    "true_name",
    "true_container",
    "true_target",
)


def shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    counts = Counter(text)
    length = len(text)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def descriptor_entropy(descriptor: Dict[str, Any]) -> Dict[str, Any]:
    """Return per-descriptor entropy without modifying the descriptor."""
    parts = []
    for field in DESCRIPTOR_FIELDS:
        value = descriptor.get(field)
        if value:
            parts.append(str(value))
    joined = " | ".join(parts)
    entropy = shannon_entropy(joined)
    return {
        "schema": "browsermind.descriptor_entropy.v1",
        "fields": [field for field in DESCRIPTOR_FIELDS if descriptor.get(field)],
        "length": len(joined),
        "entropy_bits_per_char": round(entropy, 4),
        "entropy_bits_total": round(entropy * len(joined), 4) if joined else 0.0,
        "low_entropy": bool(joined and entropy < 2.0),
    }


def descriptor_entropy_telemetry(descriptor: Dict[str, Any]) -> Dict[str, Any]:
    return telemetry_event(
        component="descriptor_entropy",
        event_type="descriptor_scored",
        phase="phase1_measurement",
        data=descriptor_entropy(descriptor),
    ).to_mutation_payload()
