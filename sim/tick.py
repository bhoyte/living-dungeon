"""Single tick orchestration through creature trophic loop."""

from __future__ import annotations

from sim.adaptation import step_population_adaptation
from sim.behavior import step_behavior, step_sensing
from sim.death import step_death_and_cleanup
from sim.reproduction import step_reproduction
from sim.epigenome import step_epigenome
from sim.metabolism import step_metabolism
from sim.systems.field_step import step as reaction_step
from sim.systems.light_cast import cast_light
from sim.systems.organism_step import build_spatial_index, step_aging
from sim.systems.tremor_cast import cast_tremor
from sim.trophic import reset_ledger
from sim.world import World


def tick(world: World, dt: float) -> None:
    world.tick += 1
    world.contract_events.clear()
    from sim.authored_subtree import check_authored_rollbacks

    check_authored_rollbacks(world)
    reset_ledger(world)
    build_spatial_index(world)
    world.field_map.step(dt)
    reaction_step(world, dt)
    cast_light(world)
    cast_tremor(world)
    step_sensing(world)
    step_behavior(world)
    step_metabolism(world, dt)
    step_epigenome(world, dt)
    step_population_adaptation(world, dt)
    step_reproduction(world, dt)
    step_death_and_cleanup(world)
    step_aging(world)
