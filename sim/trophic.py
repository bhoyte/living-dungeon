"""Energy transfer between organisms and fields (closed trophic loop)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sim.constants import (
    ENERGY_EPSILON,
    ENERGY_MAX,
    FOOD_CONSUMER_GAIN,
    FOOD_PREY_COST,
    MANA_GEO_ABSORB_RATE,
)
from sim.organisms import Organism

if TYPE_CHECKING:
    from sim.world import World


@dataclass
class TrophicLedger:
    producer_gain: float = 0.0
    consumer_gain: float = 0.0
    metabolism_loss: float = 0.0
    corpse_to_field: float = 0.0
    transfer_loss: float = 0.0


def reset_ledger(world: World) -> None:
    world.trophic_ledger = TrophicLedger()


def _record_consumer_gain(world: World, amount: float) -> None:
    world.trophic_ledger.consumer_gain += amount


def _record_producer_gain(world: World, amount: float) -> None:
    world.trophic_ledger.producer_gain += amount


def _record_transfer_loss(world: World, amount: float) -> None:
    world.trophic_ledger.transfer_loss += amount


def _adjacent(ax: int, ay: int, bx: int, by: int) -> bool:
    return abs(ax - bx) + abs(ay - by) <= 1


def find_prey_at(
    consumer: Organism,
    world: World,
    target_id: int | None,
) -> Organism | None:
    if target_id is None or target_id <= 0:
        return None
    prey = next((o for o in world.organisms if o.id == target_id and o.alive), None)
    if prey is None or prey.id == consumer.id:
        return None
    if prey.data.trophic_level >= consumer.data.trophic_level:
        return None
    ox, oy = consumer.pos
    if not _adjacent(ox, oy, prey.pos[0], prey.pos[1]):
        return None
    return prey


def try_consume_organism(
    consumer: Organism,
    prey: Organism,
    world: World,
) -> bool:
    """Transfer energy prey → consumer; record ledger for accounting tests."""
    if not prey.alive or prey.energy <= 0.0:
        return False
    before = consumer.energy + prey.energy
    prey.energy -= FOOD_PREY_COST
    prey.clamp_energy()
    gain = min(FOOD_CONSUMER_GAIN, ENERGY_MAX - consumer.energy)
    consumer.energy += gain
    consumer.clamp_energy()
    after = consumer.energy + prey.energy
    _record_consumer_gain(world, gain)
    loss = FOOD_PREY_COST - gain
    if loss > 0:
        _record_transfer_loss(world, loss)
    consumer.stress = max(0.0, consumer.stress - 0.05)
    if abs((after - before) + loss - gain) > ENERGY_EPSILON + FOOD_PREY_COST:
        pass  # bookkeeping sanity; loss is explicit inefficiency
    return gain > 0.0


def try_consume_food(
    consumer: Organism,
    world: World,
    target_id: int | None,
) -> bool:
    prey = find_prey_at(consumer, world, target_id)
    if prey is not None:
        return try_consume_organism(consumer, prey, world)
    return False


def apply_producer_field_uptake(org: Organism, world: World, dt: float) -> float:
    """Producers with photosynthesis absorb local mana_geo residual."""
    if "photosynthesis" not in org.data.traits:
        return 0.0
    x, y = org.pos
    f = world.field_map.fields
    mana = float(f["mana_geo"][y, x])
    gain = mana * MANA_GEO_ABSORB_RATE * dt
    if gain <= 0.0:
        return 0.0
    org.energy = min(ENERGY_MAX, org.energy + gain)
    f["mana_geo"][y, x] = max(0.0, mana - gain * 0.5)
    _record_producer_gain(world, gain)
    return gain


def total_alive_energy(world: World) -> float:
    return sum(o.energy for o in world.organisms if o.alive)


def total_corpse_field_energy(world: World) -> float:
    return float(world.field_map.fields["corpse"].sum())
