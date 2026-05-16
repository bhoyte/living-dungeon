"""Headless telemetry: tick records with field extrema and anomaly flags."""

from __future__ import annotations

from typing import Any

import numpy as np

from sim.fields import FIELD_CONFIG, FieldMap
from sim.tilemap import TileMap
from sim.world import World


def field_extrema(field_map: FieldMap) -> dict[str, dict[str, float]]:
    """Per-field min / max (+ mean for dashboards)."""
    out: dict[str, dict[str, float]] = {}
    for name, arr in field_map.fields.items():
        out[name] = {
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "mean": float(np.mean(arr)),
        }
    return out


def _clamp_violations(name: str, arr: np.ndarray) -> np.ndarray | None:
    cfg = FIELD_CONFIG.get(name)
    if cfg is None or cfg.is_special:
        mask = (arr < 0.0) | (arr > 1.0)
        if np.any(mask):
            return mask
        return None
    return (arr < cfg.clamp_lo - 1e-4) | (arr > cfg.clamp_hi + 1e-4)


def anomaly_flags(field_map: FieldMap) -> dict[str, Any]:
    flags: dict[str, Any] = {
        "non_finite": [],
        "out_of_band": [],
    }
    for name, arr in field_map.fields.items():
        if not np.all(np.isfinite(arr)):
            flags["non_finite"].append(name)
        viol = _clamp_violations(name, arr)
        if viol is not None and np.any(viol):
            flags["out_of_band"].append(name)
    flags["dirty"] = bool(flags["non_finite"] or flags["out_of_band"])
    return flags


def tick_record(
    tick_index: int,
    world: World,
    *,
    profile_name: str,
    resolved_seed: int,
) -> dict[str, Any]:
    fm = world.field_map
    return {
        "tick": tick_index,
        "seed": resolved_seed,
        "profile_name": profile_name,
        "depth_index": world.floor_profile.depth_index,
        "fields": field_extrema(fm),
        "anomalies": anomaly_flags(fm),
        "producer_spawns": len(world.producer_spawns),
        "creature_spawns": len(world.creature_spawns),
        "organism_count": len(world.organisms),
    }


def tilemap_checksum(tilemap: TileMap) -> str:
    import hashlib

    return hashlib.sha256(tilemap.composition.tobytes()).hexdigest()
