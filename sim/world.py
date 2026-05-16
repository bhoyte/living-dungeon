"""Runtime simulation container: maps, fields, RNG, and spawn bookkeeping."""

from __future__ import annotations

from dataclasses import dataclass, field

from typing import TYPE_CHECKING

from numpy.random import Generator as RNG

if TYPE_CHECKING:
    from sim.authored_subtree import AuthoredSubtreeRecord, PendingAuthoredRecord
    from sim.llm_adapter import LlmAdapter, LlmCircuitState, PendingLlmJob

from sim.fields import FieldMap
from sim.floor_profile import FloorProfile
from sim.organisms import Organism, initial_energy_for_species, species_data
from sim.adaptation_cache import CacheEntry
from sim.trophic import TrophicLedger
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
    organisms: list[Organism] = field(default_factory=list)
    organism_ids_in_tick_order: list[int] = field(default_factory=list)
    organism_positions: dict[int, tuple[int, int]] = field(default_factory=dict)
    contract_events: list[dict] = field(default_factory=list)
    tick: int = 0
    trophic_ledger: TrophicLedger = field(default_factory=TrophicLedger)
    adaptation_cache: dict[str, CacheEntry] = field(default_factory=dict)
    adaptation_events: list[dict] = field(default_factory=list)
    llm_enabled: bool = False
    llm_adapter: LlmAdapter | None = None
    pending_llm: dict[str, PendingLlmJob] = field(default_factory=dict)
    llm_circuits: dict[str, LlmCircuitState] = field(default_factory=dict)
    authored_subtrees: dict[str, AuthoredSubtreeRecord] = field(default_factory=dict)
    authored_pending: dict[str, PendingAuthoredRecord] = field(default_factory=dict)
    authored_auto_approve: bool = False
    _next_organism_id: int = 1

    def add_organism(self, species_id: str, pos: tuple[int, int]) -> Organism:
        from sim.organisms import attach_behavior_tree

        data = species_data(species_id).model_copy(deep=True)
        org = Organism(
            id=self._next_organism_id,
            data=data,
            pos=pos,
            energy=initial_energy_for_species(species_id),
        )
        self._next_organism_id += 1
        self.organisms.append(org)
        attach_behavior_tree(org)
        return org

    def spawn_organism(self, species_id: str, pos: tuple[int, int]) -> Organism:
        x, y = pos
        self.producer_spawns.append((species_id, x, y))
        return self.add_organism(species_id, (x, y))

    def spawn_creature(self, species_id: str, pos: tuple[int, int]) -> Organism:
        x, y = pos
        self.creature_spawns.append((species_id, x, y))
        return self.add_organism(species_id, (x, y))
