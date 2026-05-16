"""Organism tick stages: spatial order and aging."""

from __future__ import annotations

from sim.world import World


def build_spatial_index(world: World) -> None:
    """Deterministic tick order and position index (stable sort by organism id)."""
    world.organism_ids_in_tick_order = sorted(o.id for o in world.organisms if o.alive)
    world.organism_positions = {o.id: o.pos for o in world.organisms if o.alive}


def step_aging(world: World) -> None:
    by_id = {o.id: o for o in world.organisms}
    for org_id in world.organism_ids_in_tick_order:
        org = by_id.get(org_id)
        if org is not None and org.alive:
            org.age_ticks += 1
