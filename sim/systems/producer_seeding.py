"""Sessile producer placement from field masks + tile constraints."""

from __future__ import annotations

import numpy as np

from sim.world import World


def seed_mana_moss(world: World, density: float = 0.15) -> int:
    """Place live mana moss organisms on suitable tiles."""
    f = world.field_map.fields
    tilemap = world.tilemap
    walls = tilemap.is_wall()
    candidate = (f["mana_geo"] > 0.40) & (f["humidity"] > 0.30) & (~walls)
    rng = world.rng
    candidates = np.argwhere(candidate)
    n = int(len(candidates) * density)
    if n == 0:
        return 0
    n = min(n, len(candidates))
    chosen = rng.choice(len(candidates), size=n, replace=False)
    for idx in chosen:
        y, x = int(candidates[idx, 0]), int(candidates[idx, 1])
        world.spawn_organism("mana_moss", (x, y))
    return n


def seed_producer(world: World, name: str) -> int:
    if name == "mana_moss":
        return seed_mana_moss(world)
    return 0
