from __future__ import annotations

import numpy as np

from sim.constants import (
    ENERGY_EPSILON,
    ENERGY_MIN,
    FOOD_CONSUMER_GAIN,
    FOOD_PREY_COST,
)
from sim.fields import FieldMap
from sim.floor_profile import FloorProfile
from sim.generation import generate_floor
from sim.organisms import species_data
from sim.tick import tick
from sim.tilemap import TileMap
from sim.trophic import try_consume_organism
from sim.world import World


def _trophic_profile(**kwargs) -> FloorProfile:
    defaults = dict(
        name="Trophic Loop",
        width=32,
        height=24,
        seed=77,
        features=[],
        seed_producers=["mana_moss"],
        initial_creatures={"slime": 3},
    )
    defaults.update(kwargs)
    return FloorProfile(**defaults)


def test_feeding_transfer_within_epsilon() -> None:
    profile = FloorProfile(name="Feed", width=16, height=16, seed=1, bsp_max_room_size=8, features=[])
    tilemap = TileMap(16, 16)
    tilemap.cache_derived()
    world = World(
        rng=np.random.default_rng(1),
        floor_profile=profile,
        tilemap=tilemap,
        field_map=FieldMap(tilemap),
    )
    moss = world.add_organism("mana_moss", (4, 4))
    slime = world.add_organism("slime", (5, 4))
    moss.energy = 0.50
    slime.energy = 0.40
    before = moss.energy + slime.energy

    ok = try_consume_organism(slime, moss, world)
    assert ok
    assert abs(slime.energy - (0.40 + FOOD_CONSUMER_GAIN)) < ENERGY_EPSILON + 1e-6
    assert abs(moss.energy - (0.50 - FOOD_PREY_COST)) < ENERGY_EPSILON + 1e-6
    after = moss.energy + slime.energy
    assert before - after >= FOOD_PREY_COST - FOOD_CONSUMER_GAIN - ENERGY_EPSILON


def test_no_negative_organism_energy_after_ticks() -> None:
    world = generate_floor(_trophic_profile(seed=42))
    for _ in range(600):
        tick(world, 1.0)
    for org in world.organisms:
        assert org.energy >= ENERGY_MIN - 1e-9
        assert org.energy <= 1.0 + 1e-9


def test_non_zero_population_over_600_ticks() -> None:
    world = generate_floor(_trophic_profile(seed=99))
    for _ in range(600):
        tick(world, 1.0)
    alive = [o for o in world.organisms if o.alive]
    assert len(alive) > 0
    assert any(o.data.species_id == "slime" for o in alive)


def test_closed_loop_deterministic() -> None:
    p = _trophic_profile(seed=2026)
    w1 = generate_floor(p)
    w2 = generate_floor(p)

    def snapshot(world: World) -> tuple:
        return (
            sorted((o.id, o.pos, round(o.energy, 5), o.alive, o.data.species_id) for o in world.organisms),
            round(float(world.field_map.fields["corpse"].sum()), 5),
            round(float(world.field_map.fields["sweet"].sum()), 5),
        )

    for _ in range(300):
        tick(w1, 1.0)
        tick(w2, 1.0)
    assert snapshot(w1) == snapshot(w2)


def test_death_deposits_corpse_field() -> None:
    profile = FloorProfile(name="Death", width=16, height=16, seed=3, bsp_max_room_size=8, features=[])
    tilemap = TileMap(16, 16)
    tilemap.cache_derived()
    world = World(
        rng=np.random.default_rng(3),
        floor_profile=profile,
        tilemap=tilemap,
        field_map=FieldMap(tilemap),
    )
    moss = world.add_organism("mana_moss", (2, 2))
    moss.energy = 0.01
    x, y = moss.pos
    before = float(world.field_map.fields["corpse"][y, x])
    from sim.death import step_death_and_cleanup

    step_death_and_cleanup(world)
    after = float(world.field_map.fields["corpse"][y, x])
    assert after > before
    assert moss not in world.organisms


def test_mana_moss_species_is_producer() -> None:
    moss = species_data("mana_moss")
    assert moss.trophic_level == 0
    assert "photosynthesis" in moss.traits
