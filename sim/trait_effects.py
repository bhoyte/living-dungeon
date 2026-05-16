"""Per-tick trait hooks (field emission and passive gain)."""

from __future__ import annotations

from sim.constants import PHOTOSYNTHESIS_RATE, SWEET_EMIT_RATE
from sim.organisms import Organism
from sim.trophic import _record_producer_gain
from sim.world import World


def apply_trait_metabolism_effects(org: Organism, world: World, dt: float) -> None:
    x, y = org.pos
    f = world.field_map.fields

    if "photosynthesis" in org.data.traits:
        light = float(f["light"][y, x])
        gain = light * PHOTOSYNTHESIS_RATE * dt
        if gain > 0.0:
            from sim.constants import ENERGY_MAX

            org.energy = min(ENERGY_MAX, org.energy + gain)
            _record_producer_gain(world, gain)

    if "sweet_scent" in org.data.traits and org.alive:
        f["sweet"][y, x] = min(1.0, float(f["sweet"][y, x]) + SWEET_EMIT_RATE * dt)

    if "carnivore" in org.data.traits and org.energy < 0.35:
        corpse = float(f["corpse"][y, x])
        if corpse > 0.05:
            from sim.constants import ENERGY_MAX
            from sim.trophic import _record_consumer_gain

            bite = min(0.08 * dt, corpse, 0.15)
            org.energy = min(ENERGY_MAX, org.energy + bite)
            f["corpse"][y, x] = corpse - bite
            _record_consumer_gain(world, bite)
