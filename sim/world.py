"""Runtime simulation container: maps, fields, RNG, and spawn bookkeeping."""

from __future__ import annotations

from dataclasses import dataclass, field

from numpy.random import Generator as RNG

from sim.fields import FieldMap
from sim.floor_profile import FloorProfile
from sim.tilemap import TileMap


@dataclass
class World:
    rng: RNG
    floor_profile: FloorProfile
    tilemap: TileMap
    field_map: FieldMap
    static_light_sources: list[tuple[int, int, float, int]] = field(default_factory=list)
    tremor_events_this_tick: list[tuple[int, int, float]] = field(default_factory=list)
    producer_spawns: list[tuple[str, int, int]] = field(default_factory=list)
    creature_spawns: list[tuple[str, int, int]] = field(default_factory=list)

    def spawn_organism(self, species_id: str, pos: tuple[int, int]) -> None:
        x, y = pos
        self.producer_spawns.append((species_id, x, y))

    def spawn_creature(self, species_id: str, pos: tuple[int, int]) -> None:
        x, y = pos
        self.creature_spawns.append((species_id, x, y))
