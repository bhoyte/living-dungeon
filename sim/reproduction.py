"""Asexual consumer reproduction (v1 minimal, deterministic)."""

from __future__ import annotations

from sim.constants import (
    EPIGENOME_DRIFT_SCALE,
    EPIGENOME_INHERIT_BLEND,
    EPIGENOME_MULT_MAX,
    EPIGENOME_MULT_MIN,
    GENOME_DRIFT_SCALE,
    MAX_POPULATION_PER_SPECIES,
    REPRODUCTION_ENERGY_THRESHOLD,
    REPRODUCTION_OFFSPRING_ENERGY,
    REPRODUCTION_PARENT_ENERGY_COST,
    REPRODUCTION_STRESS_THRESHOLD,
)
from sim.organisms import Epigenome, Genome, Organism, attach_behavior_tree
from sim.world import World

_NEIGHBOR_DELTAS = ((0, -1), (0, 1), (-1, 0), (1, 0))


def _species_population(world: World, species_id: str) -> int:
    return sum(
        1 for o in world.organisms if o.alive and o.data.species_id == species_id
    )


def _passable_neighbors(world: World, x: int, y: int) -> list[tuple[int, int]]:
    tilemap = world.tilemap
    h, w = tilemap.h, tilemap.w
    walls = tilemap.is_wall()
    out: list[tuple[int, int]] = []
    for dx, dy in _NEIGHBOR_DELTAS:
        nx, ny = x + dx, y + dy
        if 0 <= nx < w and 0 <= ny < h and not walls[ny, nx]:
            out.append((nx, ny))
    return sorted(out)


def _free_spawn_tiles(world: World, parent: Organism) -> list[tuple[int, int]]:
    occupied = set(world.organism_positions.values())
    x, y = parent.pos
    return [pos for pos in _passable_neighbors(world, x, y) if pos not in occupied]


def _drift_genome(rng, genome: Genome) -> None:
    genome.size = max(0.1, genome.size + float(rng.uniform(-GENOME_DRIFT_SCALE, GENOME_DRIFT_SCALE)))
    genome.speed = max(1.0, genome.speed + float(rng.uniform(-GENOME_DRIFT_SCALE, GENOME_DRIFT_SCALE)) * 10.0)
    genome.metabolism = max(
        0.1,
        genome.metabolism + float(rng.uniform(-GENOME_DRIFT_SCALE, GENOME_DRIFT_SCALE)),
    )
    r, g, b = genome.pigmentation
    genome.pigmentation = (
        max(0.0, min(1.0, r + float(rng.uniform(-GENOME_DRIFT_SCALE, GENOME_DRIFT_SCALE)))),
        max(0.0, min(1.0, g + float(rng.uniform(-GENOME_DRIFT_SCALE, GENOME_DRIFT_SCALE)))),
        max(0.0, min(1.0, b + float(rng.uniform(-GENOME_DRIFT_SCALE, GENOME_DRIFT_SCALE)))),
    )


def _inherit_epigenome(rng, parent_epi: Epigenome, child_epi: Epigenome) -> None:
    blend = EPIGENOME_INHERIT_BLEND
    for field in (
        "size_mult",
        "speed_mult",
        "metabolism_mult",
        "perception_mult",
        "aggression_mult",
    ):
        inherited = blend * float(getattr(parent_epi, field)) + (1.0 - blend) * 1.0
        drift = float(rng.uniform(-EPIGENOME_DRIFT_SCALE, EPIGENOME_DRIFT_SCALE))
        value = max(EPIGENOME_MULT_MIN, min(EPIGENOME_MULT_MAX, inherited + drift))
        setattr(child_epi, field, value)


def _spawn_offspring(world: World, parent: Organism, pos: tuple[int, int]) -> Organism:
    data = parent.data.model_copy(deep=True)
    _drift_genome(world.rng, data.base_genome)
    _inherit_epigenome(world.rng, parent.data.epigenome, data.epigenome)
    org = Organism(
        id=world._next_organism_id,
        data=data,
        pos=pos,
        energy=REPRODUCTION_OFFSPRING_ENERGY,
        stress=max(0.0, parent.stress * 0.5),
    )
    world._next_organism_id += 1
    world.organisms.append(org)
    world.creature_spawns.append((data.species_id, pos[0], pos[1]))
    attach_behavior_tree(org)
    org.clamp_energy()
    world.organism_positions[org.id] = pos
    return org


def _can_reproduce(world: World, parent: Organism) -> bool:
    if not parent.alive or parent.data.trophic_level <= 0:
        return False
    if parent.energy < REPRODUCTION_ENERGY_THRESHOLD:
        return False
    if parent.stress > REPRODUCTION_STRESS_THRESHOLD:
        return False
    if _species_population(world, parent.data.species_id) >= MAX_POPULATION_PER_SPECIES:
        return False
    return bool(_free_spawn_tiles(world, parent))


def step_reproduction(world: World, dt: float) -> None:
    del dt  # v1 gates are per-tick thresholds; dt reserved for future rate scaling
    parents = sorted(
        (o for o in world.organisms if o.alive and o.data.trophic_level > 0),
        key=lambda o: o.id,
    )
    for parent in parents:
        if not _can_reproduce(world, parent):
            continue
        tiles = _free_spawn_tiles(world, parent)
        if not tiles:
            continue
        if _species_population(world, parent.data.species_id) >= MAX_POPULATION_PER_SPECIES:
            continue
        pick = int(world.rng.integers(0, len(tiles)))
        pos = tiles[pick]
        _spawn_offspring(world, parent, pos)
        parent.energy -= REPRODUCTION_PARENT_ENERGY_COST
        parent.clamp_energy()
