from __future__ import annotations

import numpy as np

from sim.constants import (
    DEFAULT_METABOLISM_DRAIN_PER_TICK,
    ENERGY_MAX,
    ENERGY_MIN,
)
from sim.fields import FieldMap
from sim.floor_profile import FloorProfile
from sim.metabolism import step_metabolism
from sim.organisms import Organism
from sim.tilemap import TileMap
from sim.world import World


def _world_with_slime(energy: float) -> tuple[World, Organism]:
    profile = FloorProfile(name="Met", width=12, height=12, seed=3, features=[])
    tilemap = TileMap(12, 12)
    tilemap.cache_derived()
    world = World(
        rng=np.random.default_rng(3),
        floor_profile=profile,
        tilemap=tilemap,
        field_map=FieldMap(tilemap),
    )
    org = world.add_organism("slime", (5, 5))
    org.energy = energy
    world.organism_ids_in_tick_order = [org.id]
    return world, org


def test_clamp_energy_bounds() -> None:
    _, org = _world_with_slime(1.5)
    org.clamp_energy()
    assert org.energy == ENERGY_MAX

    org.energy = -0.2
    org.clamp_energy()
    assert org.energy == ENERGY_MIN


def test_metabolism_drains_consumer_energy() -> None:
    world, org = _world_with_slime(0.80)
    before = org.energy
    step_metabolism(world, 1.0)
    expected_drain = DEFAULT_METABOLISM_DRAIN_PER_TICK * org.data.stat("metabolism")
    assert org.energy == before - expected_drain
    assert ENERGY_MIN <= org.energy <= ENERGY_MAX


def test_metabolism_clamps_after_extreme_drain() -> None:
    world, org = _world_with_slime(0.001)
    for _ in range(50):
        step_metabolism(world, 1.0)
    assert org.energy >= ENERGY_MIN
    assert org.energy <= ENERGY_MAX
