"""py_trees verb/condition adapters and per-tick behavior stepping."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import py_trees
from py_trees.common import Status

from sim.organisms import Organism
from sim.sensing import SenseResult, check_env, merge_modalities, query_sense
from sim.world import World

LOCOMOTE_TARGETS = frozenset(
    {"wander", "safety", "food", "prey", "predator", "up_gradient"}
)


def _bb() -> py_trees.blackboard.Blackboard:
    return py_trees.blackboard.Blackboard()


class _ContractBehaviour(py_trees.behaviour.Behaviour):
    """Base behaviour that reads organism/world from the blackboard each tick."""

    def _ctx(self) -> tuple[Organism, World]:
        org: Organism = _bb().get("organism")
        world: World = _bb().get("world")
        return org, world


class CheckEnvBehaviour(_ContractBehaviour):
    def __init__(self, path: str, op: str, value: Any, name: str | None = None) -> None:
        super().__init__(name=name or f"CheckEnv({path})")
        self.path = path
        self.op = op
        self.value = value

    def update(self) -> Status:
        org, world = self._ctx()
        ok = check_env(org, world, self.path, self.op, self.value)
        return Status.SUCCESS if ok else Status.FAILURE


class CheckInternalBehaviour(_ContractBehaviour):
    def __init__(self, stat: str, op: str, threshold: float, name: str | None = None) -> None:
        super().__init__(name=name or f"CheckInternal({stat})")
        self.stat = stat
        self.op = op
        self.threshold = threshold

    def _read_stat(self, org: Organism, world: World) -> float | None:
        if self.stat == "energy":
            return org.energy
        if self.stat == "stress":
            return org.stress
        if self.stat == "distance_to_prey":
            result: SenseResult | None = org.extensions.get("last_sense")
            if result and result.distance is not None:
                return result.distance
            return None
        if self.stat in ("speed", "metabolism", "aggression", "size", "perception_range"):
            return org.data.stat(self.stat)
        return None

    def update(self) -> Status:
        org, world = self._ctx()
        value = self._read_stat(org, world)
        if value is None:
            return Status.FAILURE
        from sim.sensing import _compare

        ok = _compare(self.op, value, self.threshold)
        return Status.SUCCESS if ok else Status.FAILURE


class CheckCooldownBehaviour(_ContractBehaviour):
    def __init__(self, key: str, name: str | None = None) -> None:
        super().__init__(name=name or f"CheckCooldown({key})")
        self.key = str(key)

    def update(self) -> Status:
        org, world = self._ctx()
        cooldowns: dict = org.extensions.setdefault("cooldowns", {})
        ready_at = int(cooldowns.get(self.key, 0))
        return Status.SUCCESS if world.tick >= ready_at else Status.FAILURE


class QuerySenseBehaviour(_ContractBehaviour):
    def __init__(
        self,
        sense_type: str,
        target_type: str,
        *,
        merge: bool = False,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name or f"QuerySense({sense_type},{target_type})")
        self.sense_type = sense_type
        self.target_type = target_type
        self.merge = merge

    def update(self) -> Status:
        org, world = self._ctx()
        if self.merge:
            result = merge_modalities(org, world, self.target_type)
        else:
            result = query_sense(org, world, self.sense_type, self.target_type)
        org.extensions["last_sense"] = result
        _bb().set("sense_result", result)
        return Status.SUCCESS if result.success else Status.FAILURE


class LocomoteBehaviour(_ContractBehaviour):
    def __init__(self, target: str, name: str | None = None) -> None:
        super().__init__(name=name or f"Locomote({target})")
        self.target = target

    def update(self) -> Status:
        org, world = self._ctx()
        if self.target not in LOCOMOTE_TARGETS:
            return Status.FAILURE
        moved = _locomote(org, world, self.target)
        return Status.SUCCESS if moved else Status.FAILURE


class InteractBehaviour(_ContractBehaviour):
    def __init__(self, target: str, name: str | None = None) -> None:
        super().__init__(name=name or f"Interact({target})")
        self.target = target

    def update(self) -> Status:
        org, world = self._ctx()
        if _interact(org, world, self.target):
            return Status.SUCCESS
        return Status.FAILURE


class RestBehaviour(_ContractBehaviour):
    def update(self) -> Status:
        return Status.SUCCESS


class HideBehaviour(_ContractBehaviour):
    def update(self) -> Status:
        return Status.SUCCESS


def _passable_neighbors(world: World, x: int, y: int) -> list[tuple[int, int]]:
    tilemap = world.tilemap
    h, w = tilemap.h, tilemap.w
    passable = tilemap.is_wall()
    out: list[tuple[int, int]] = []
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < w and 0 <= ny < h and not passable[ny, nx]:
            out.append((nx, ny))
    return sorted(out)


def _step_toward(
    org: Organism,
    world: World,
    *,
    gx: float,
    gy: float,
) -> bool:
    x, y = org.pos
    neighbors = _passable_neighbors(world, x, y)
    if not neighbors:
        return False
    best = min(
        neighbors,
        key=lambda p: (
            -(gx * (p[0] - x) + gy * (p[1] - y)),
            p[0],
            p[1],
        ),
    )
    org.pos = best
    return True


def _target_position(org: Organism, world: World, result: SenseResult) -> tuple[float, float] | None:
    if result.target_id is not None and result.target_id > 0:
        pos = world.organism_positions.get(result.target_id)
        if pos:
            return float(pos[0]), float(pos[1])
    if result.target_id is not None and result.target_id < 0:
        idx = -result.target_id - 1
        if 0 <= idx < len(world.producer_spawns):
            _, px, py = world.producer_spawns[idx]
            return float(px), float(py)
    if result.gradient is not None:
        gx, gy = result.gradient
        return org.pos[0] + gx, org.pos[1] + gy
    return None


def _locomote(org: Organism, world: World, mode: str) -> bool:
    if org.data.stat("speed") <= 0.0:
        return True
    x, y = org.pos
    if mode == "wander":
        neighbors = _passable_neighbors(world, x, y)
        if not neighbors:
            return False
        rng = np.random.default_rng(world.floor_profile.seed + world.tick * 1009 + org.id)
        pick = int(rng.integers(0, len(neighbors)))
        org.pos = neighbors[pick]
        return True

    result: SenseResult | None = org.extensions.get("last_sense")

    if mode == "safety":
        from sim.sensing import _field_gradient

        gx, gy = _field_gradient(world, "alarm", x, y)
        mag = math.hypot(gx, gy)
        if mag < 1e-6:
            return _locomote(org, world, "wander")
        return _step_toward(org, world, gx=-gx / mag, gy=-gy / mag)

    if mode == "up_gradient":
        from sim.sensing import _field_gradient

        gx, gy = _field_gradient(world, "sweet", x, y)
        mag = math.hypot(gx, gy)
        if mag < 1e-6:
            return False
        return _step_toward(org, world, gx=gx / mag, gy=gy / mag)

    if result is None or not result.success:
        return _locomote(org, world, "wander")

    if result.gradient is not None and mode in ("food", "prey", "predator"):
        gx, gy = result.gradient
        if mode == "predator":
            gx, gy = -gx, -gy
        return _step_toward(org, world, gx=gx, gy=gy)

    target = _target_position(org, world, result)
    if target is None:
        return _locomote(org, world, "wander")
    tx, ty = target
    dx, dy = tx - x, ty - y
    mag = math.hypot(dx, dy)
    if mag < 1e-6:
        return True
    return _step_toward(org, world, gx=dx / mag, gy=dy / mag)


def _interact(org: Organism, world: World, target: str) -> bool:
    if target != "food":
        return False
    result: SenseResult | None = org.extensions.get("last_sense")
    if result is None or not result.success:
        return False
    from sim.trophic import try_consume_food

    return try_consume_food(org, world, result.target_id)


def step_sensing(world: World) -> None:
    """Pre-behavior perception cache (entity positions for this tick)."""
    world.organism_positions = {o.id: o.pos for o in world.organisms if o.alive}


def step_behavior(world: World) -> None:
    bb = _bb()
    for org_id in world.organism_ids_in_tick_order:
        org = next((o for o in world.organisms if o.id == org_id), None)
        if org is None or not org.alive:
            continue
        root = org.extensions.get("bt_root")
        if root is None:
            continue
        bb.set("organism", org)
        bb.set("world", world)
        bb.set("tick", world.tick)
        bb.set("sense_result", None)
        root.tick_once()
