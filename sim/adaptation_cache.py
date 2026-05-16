"""Adaptation cache types (no sim imports to avoid cycles)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CacheState = Literal["candidate", "promoted", "demoted", "invalidated"]


@dataclass
class CacheEntry:
    signature: str
    subtree_key: str
    state: CacheState = "candidate"
    success_rate: float = 0.0
    stress_reduction: float = 0.0
    survival_impact: float = 0.0
    sample_count: int = 0
    last_seen_tick: int = 0
    consecutive_failures: int = 0
    stress_before: float = 0.0
