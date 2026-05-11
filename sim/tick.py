"""Single tick orchestration: fields → reactions → special recomputes."""

from __future__ import annotations

from sim.systems.field_step import step as reaction_step
from sim.systems.light_cast import cast_light
from sim.systems.tremor_cast import cast_tremor
from sim.world import World


def tick(world: World, dt: float) -> None:
    world.field_map.step(dt)
    reaction_step(world, dt)
    cast_light(world)
    cast_tremor(world)
