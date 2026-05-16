"""Death conditions, corpse deposition, and organism cleanup."""

from __future__ import annotations

from sim.constants import CORPSE_DEPOSIT_AMOUNT, DEATH_ENERGY_THRESHOLD, SPORE_ON_DEATH_AMOUNT
from sim.organisms import Organism
from sim.world import World


def step_death_and_cleanup(world: World) -> None:
    survivors: list[Organism] = []
    f = world.field_map.fields

    for org in world.organisms:
        if org.alive and org.energy <= DEATH_ENERGY_THRESHOLD:
            org.alive = False
            x, y = org.pos
            deposit = min(CORPSE_DEPOSIT_AMOUNT, 1.0 - float(f["corpse"][y, x]))
            f["corpse"][y, x] = float(f["corpse"][y, x]) + deposit
            world.trophic_ledger.corpse_to_field += deposit
            if org.data.trophic_level == 0:
                spore = min(SPORE_ON_DEATH_AMOUNT, 1.0 - float(f["spore"][y, x]))
                f["spore"][y, x] = float(f["spore"][y, x]) + spore

        if org.alive:
            survivors.append(org)

    world.organisms = survivors
    build_spatial_index_after_cleanup(world)


def build_spatial_index_after_cleanup(world: World) -> None:
    world.organism_ids_in_tick_order = sorted(o.id for o in world.organisms if o.alive)
    world.organism_positions = {o.id: o.pos for o in world.organisms if o.alive}
