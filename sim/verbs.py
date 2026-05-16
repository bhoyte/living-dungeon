"""Fixed verb and condition manifest (v1, locked)."""

from __future__ import annotations

VERBS: dict[str, list[str]] = {
    "Locomote": ["target"],
    "Interact": ["target"],
    "Emit": ["substance"],
    "Construct": ["object"],
    "Rest": [],
    "Hide": [],
}

CONDITIONS: dict[str, list[str]] = {
    "QuerySense": ["sense_type", "target_type"],
    "CheckInternal": ["stat", "op", "threshold"],
    "CheckEnv": ["tile_or_var", "op", "value"],
    "CheckCooldown": ["key"],
}

ALLOWED_CHECKENV_OPS = frozenset({"==", "!=", ">", ">=", "<", "<=", "in", "not_in"})
ALLOWED_SENSE_MODALITIES = frozenset({"sight", "smell"})
ALLOWED_SENSE_TARGETS = frozenset(
    {"predator", "prey", "food", "safety", "resource_mana"}
)
