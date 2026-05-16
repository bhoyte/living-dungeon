from __future__ import annotations

import numpy as np

from sim.constants import MAX_POPULATION_PER_SPECIES, REPRODUCTION_ENERGY_THRESHOLD
from sim.fields import FieldMap
from sim.floor_profile import FloorProfile
from sim.generation import generate_floor
from sim.reproduction import step_reproduction
from sim.tick import tick
from sim.tilemap import TileMap
from sim.world import World


def _isolated_slime_world(*, seed: int = 11, energy: float = 0.92, stress: float = 0.1) -> World:
    profile = FloorProfile(
        name="Repro",
        width=16,
        height=16,
        seed=seed,
        bsp_max_room_size=8,
        features=[],
    )
    tilemap = TileMap(16, 16)
    tilemap.cache_derived()
    world = World(
        rng=np.random.default_rng(seed),
        floor_profile=profile,
        tilemap=tilemap,
        field_map=FieldMap(tilemap),
    )
    slime = world.add_organism("slime", (8, 8))
    slime.energy = energy
    slime.stress = stress
    world.organism_ids_in_tick_order = [slime.id]
    world.organism_positions = {slime.id: slime.pos}
    return world


def test_reproduction_spawns_offspring_when_gates_pass() -> None:
    world = _isolated_slime_world()
    assert len(world.organisms) == 1
    step_reproduction(world, 1.0)
    assert len(world.organisms) == 2
    parent, child = sorted(world.organisms, key=lambda o: o.id)
    assert parent.data.species_id == "slime"
    assert child.data.species_id == "slime"
    assert child.id != parent.id
    assert abs(parent.pos[0] - child.pos[0]) + abs(parent.pos[1] - child.pos[1]) == 1
    assert child.energy > 0.0
    assert parent.energy < REPRODUCTION_ENERGY_THRESHOLD


def test_reproduction_skips_producers() -> None:
    world = _isolated_slime_world(seed=12)
    world.organisms.clear()
    moss = world.add_organism("mana_moss", (4, 4))
    moss.energy = 0.95
    moss.stress = 0.0
    world.organism_ids_in_tick_order = [moss.id]
    world.organism_positions = {moss.id: moss.pos}
    step_reproduction(world, 1.0)
    assert len(world.organisms) == 1


def test_reproduction_deterministic_with_seed() -> None:
    w1 = _isolated_slime_world(seed=77)
    w2 = _isolated_slime_world(seed=77)
    step_reproduction(w1, 1.0)
    step_reproduction(w2, 1.0)

    def snap(world: World) -> list[tuple]:
        return sorted(
            (
                o.id,
                o.pos,
                round(o.energy, 5),
                round(o.stress, 5),
                tuple(round(c, 4) for c in o.data.base_genome.pigmentation),
            )
            for o in world.organisms
        )

    assert snap(w1) == snap(w2)


def test_reproduction_respects_species_cap() -> None:
    world = _isolated_slime_world(seed=5, energy=0.99, stress=0.0)
    world.organisms.clear()
    world.organism_positions.clear()
    for i in range(MAX_POPULATION_PER_SPECIES):
        x = 2 + (i % 12)
        y = 2 + (i // 12)
        org = world.add_organism("slime", (x, y))
        org.energy = 0.99
        org.stress = 0.0
        world.organism_positions[org.id] = org.pos
    before = len(world.organisms)
    step_reproduction(world, 1.0)
    assert len(world.organisms) == before


def test_tick_reproduction_no_explosion_beyond_cap() -> None:
    profile = FloorProfile(
        name="Pop Cap",
        width=24,
        height=18,
        seed=2026,
        features=[],
        seed_producers=[],
        initial_creatures={"slime": 6},
    )
    world = generate_floor(profile)
    for org in world.organisms:
        if org.data.species_id == "slime":
            org.energy = 0.95
            org.stress = 0.05
    for _ in range(400):
        tick(world, 1.0)
    for species_id in ("slime", "scout_slime"):
        count = sum(1 for o in world.organisms if o.alive and o.data.species_id == species_id)
        assert count <= MAX_POPULATION_PER_SPECIES
