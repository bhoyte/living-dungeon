"""Save/load helpers for simulation checkpoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from sim.fields import FIELD_CONFIG
from sim.floor_profile import FloorProfile
from sim.generation import generate_floor
from sim.world import World


def save_checkpoint(world: World, out_dir: str | Path, *, tick_index: int) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    meta: dict[str, Any] = {
        "tick_index": int(tick_index),
        "profile": world.floor_profile.model_dump(),
        "producer_spawns": world.producer_spawns,
        "creature_spawns": world.creature_spawns,
        "tremor_events_this_tick": world.tremor_events_this_tick,
        "static_light_sources": world.static_light_sources,
    }
    (out / "checkpoint_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    arrays = {f"field_{k}": v for k, v in world.field_map.fields.items()}
    np.savez_compressed(out / "checkpoint_fields.npz", **arrays)
    return out


def load_checkpoint(checkpoint_dir: str | Path) -> tuple[World, int]:
    ckpt = Path(checkpoint_dir)
    meta = json.loads((ckpt / "checkpoint_meta.json").read_text(encoding="utf-8"))

    profile = FloorProfile.model_validate(meta["profile"])
    world = generate_floor(profile)

    with np.load(ckpt / "checkpoint_fields.npz") as npz:
        for name in FIELD_CONFIG:
            key = f"field_{name}"
            if key not in npz:
                raise KeyError(f"Missing checkpoint field array: {key}")
            arr = np.asarray(npz[key], dtype=np.float32)
            if arr.shape != world.field_map.fields[name].shape:
                raise ValueError(
                    f"Checkpoint field shape mismatch for {name}: "
                    f"{arr.shape} != {world.field_map.fields[name].shape}"
                )
            world.field_map.fields[name][:] = arr

    world.producer_spawns = [tuple(x) for x in meta.get("producer_spawns", [])]
    world.creature_spawns = [tuple(x) for x in meta.get("creature_spawns", [])]
    world.tremor_events_this_tick = [tuple(x) for x in meta.get("tremor_events_this_tick", [])]
    world.static_light_sources = [tuple(x) for x in meta.get("static_light_sources", [])]

    return world, int(meta["tick_index"])
