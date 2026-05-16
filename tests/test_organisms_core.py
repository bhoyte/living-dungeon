from __future__ import annotations

import pytest

from sim.floor_profile import FloorProfile
from sim.generation import generate_floor
from sim.organisms import Organism, species_data
from sim.tick import tick


def _organism_snapshot(world) -> list[tuple]:
    return [
        (
            o.id,
            o.pos,
            round(o.energy, 6),
            round(o.stress, 6),
            o.age_ticks,
            o.alive,
        )
        for o in sorted(world.organisms, key=lambda x: x.id)
    ]


def _profile_with_creatures(*, seed: int = 42, creatures: dict[str, int] | None = None) -> FloorProfile:
    return FloorProfile(
        name="Organism Test",
        width=24,
        height=18,
        seed=seed,
        features=[],
        seed_producers=[],
        initial_creatures=creatures if creatures is not None else {"slime": 2, "scout_slime": 1},
    )


def test_distinct_stat_outputs_for_different_species() -> None:
    slime = species_data("slime")
    scout = species_data("scout_slime")
    assert slime.stat("speed") != scout.stat("speed")
    assert slime.stat("metabolism") != scout.stat("metabolism")


def test_deterministic_organism_state_after_100_ticks() -> None:
    profile = _profile_with_creatures(seed=2026)
    w1 = generate_floor(profile)
    w2 = generate_floor(profile)
    assert _organism_snapshot(w1) == _organism_snapshot(w2)

    for _ in range(100):
        tick(w1, 1.0)
        tick(w2, 1.0)

    assert _organism_snapshot(w1) == _organism_snapshot(w2)
    assert len(w1.organism_ids_in_tick_order) == len(w1.organisms)
    assert w1.organism_ids_in_tick_order == sorted(o.id for o in w1.organisms if o.alive)


def test_empty_population_survives_100_ticks() -> None:
    profile = _profile_with_creatures(seed=7, creatures={})
    world = generate_floor(profile)
    assert world.organisms == []
    for _ in range(100):
        tick(world, 1.0)
    assert world.organisms == []


def test_organisms_survive_100_ticks_with_behavior_tree() -> None:
    profile = _profile_with_creatures(seed=99)
    world = generate_floor(profile)
    for _ in range(100):
        tick(world, 1.0)
    for org in world.organisms:
        assert org.alive
        assert org.energy > 0.5
        assert org.age_ticks == 100


def test_spawn_creature_registers_live_organism() -> None:
    import numpy as np

    from sim.fields import FieldMap
    from sim.tilemap import TileMap
    from sim.world import World

    profile = FloorProfile(
        name="Spawn",
        width=16,
        height=16,
        seed=1,
        bsp_max_room_size=8,
        features=[],
    )
    tilemap = TileMap(16, 16)
    tilemap.cache_derived()
    world = World(
        rng=np.random.default_rng(1),
        floor_profile=profile,
        tilemap=tilemap,
        field_map=FieldMap(tilemap),
    )
    org = world.spawn_creature("slime", (3, 4))
    assert isinstance(org, Organism)
    assert org.id == 1
    assert len(world.organisms) == 1
    assert world.creature_spawns == [("slime", 3, 4)]


def test_unknown_species_raises() -> None:
    import numpy as np

    from sim.fields import FieldMap
    from sim.tilemap import TileMap
    from sim.world import World

    profile = FloorProfile(
        name="X",
        width=16,
        height=16,
        seed=1,
        bsp_max_room_size=8,
        features=[],
    )
    tilemap = TileMap(16, 16)
    tilemap.cache_derived()
    world = World(
        rng=np.random.default_rng(1),
        floor_profile=profile,
        tilemap=tilemap,
        field_map=FieldMap(tilemap),
    )
    with pytest.raises(KeyError, match="unknown_species"):
        world.add_organism("unknown_species", (1, 1))
