"""Organism energy drain and trait-driven field coupling."""

from __future__ import annotations

from sim.constants import DEFAULT_METABOLISM_DRAIN_PER_TICK
from sim.organisms import Organism
from sim.trait_effects import apply_trait_metabolism_effects
from sim.trophic import apply_producer_field_uptake
from sim.world import World


def _iter_tick_order(world: World) -> list[Organism]:
    by_id = {o.id: o for o in world.organisms}
    return [by_id[i] for i in world.organism_ids_in_tick_order if i in by_id]


def step_metabolism(world: World, dt: float) -> None:
    for org in _iter_tick_order(world):
        if not org.alive:
            continue
        drain = DEFAULT_METABOLISM_DRAIN_PER_TICK * org.data.stat("metabolism") * dt
        org.energy -= drain
        world.trophic_ledger.metabolism_loss += drain
        apply_trait_metabolism_effects(org, world, dt)
        if org.data.trophic_level == 0:
            apply_producer_field_uptake(org, world, dt)
        org.clamp_energy()
