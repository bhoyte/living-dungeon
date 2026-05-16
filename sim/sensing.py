"""EnvView, CheckEnv, QuerySense contract implementations."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel

from sim.organisms import Organism
from sim.tilemap import TILE_PROPS, TileComp
from sim.verbs import ALLOWED_CHECKENV_OPS, ALLOWED_SENSE_MODALITIES, ALLOWED_SENSE_TARGETS
from sim.world import World

FIELD_DEFAULT = 0.0


class EnvView(BaseModel):
    floor: int
    tile: str
    fields: dict[str, float]
    tile_props: dict[str, float | bool | str]
    light: float
    mana: float


class SenseResult(BaseModel):
    success: bool
    target_id: int | None = None
    distance: float | None = None
    gradient: tuple[float, float] | None = None
    confidence: float = 0.0


class SenseCandidate(BaseModel):
    target_id: int
    distance: float
    confidence: float
    gradient: tuple[float, float] | None = None


def emit_contract_event(
    world: World,
    event_name: str,
    *,
    message: str,
    severity: str = "debug",
    species_or_cluster_id: str = "",
) -> None:
    world.contract_events.append(
        {
            "event_name": event_name,
            "tick": world.tick,
            "floor": world.floor_profile.depth_index,
            "species_or_cluster_id": species_or_cluster_id,
            "severity": severity,
            "message": message,
            "correlation_id": f"{world.tick}:{event_name}:{len(world.contract_events)}",
        }
    )


def build_env_view(org: Organism, world: World) -> EnvView:
    x, y = org.pos
    tilemap = world.tilemap
    h, w = tilemap.h, tilemap.w
    x = max(0, min(w - 1, x))
    y = max(0, min(h - 1, y))
    comp = TileComp(int(tilemap.composition[y, x]))
    props = TILE_PROPS[comp]
    fields = {
        name: float(world.field_map.fields[name][y, x]) for name in world.field_map.fields
    }
    mana = fields.get("mana_geo", FIELD_DEFAULT)
    return EnvView(
        floor=world.floor_profile.depth_index,
        tile=comp.name,
        fields=fields,
        tile_props={
            "is_wall": props.is_wall,
            "is_passable": props.is_passable,
            "is_transparent": props.is_transparent,
            "traction": props.traction,
            "porosity": props.porosity,
        },
        light=fields.get("light", FIELD_DEFAULT),
        mana=mana,
    )


def _compare(op: str, left: Any, right: Any) -> bool:
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == "in":
        return left in right
    if op == "not_in":
        return left not in right
    return False


def _resolve_env_value(org: Organism, world: World, path: str) -> Any | None:
    env = build_env_view(org, world)
    if path == "tile.composition":
        return env.tile
    if path.startswith("tile."):
        key = path.split(".", 1)[1]
        if key in env.tile_props:
            return env.tile_props[key]
        return None
    if path.startswith("fields."):
        key = path.split(".", 1)[1]
        return env.fields.get(key, FIELD_DEFAULT)
    if path == "env.light":
        return env.light
    if path == "env.mana":
        return env.mana
    return None


def check_env(
    org: Organism,
    world: World,
    path: str,
    op: str,
    value: Any,
) -> bool:
    if op not in ALLOWED_CHECKENV_OPS:
        emit_contract_event(
            world,
            "contract.checkenv.invalid_path_or_op",
            message=f"invalid op {op!r}",
            species_or_cluster_id=org.data.species_id,
        )
        return False
    resolved = _resolve_env_value(org, world, path)
    if resolved is None:
        emit_contract_event(
            world,
            "contract.checkenv.invalid_path_or_op",
            message=f"invalid path {path!r}",
            species_or_cluster_id=org.data.species_id,
        )
        return False
    return _compare(op, resolved, value)


def _dist(ax: int, ay: int, bx: int, by: int) -> float:
    return math.hypot(float(bx - ax), float(by - ay))


def _channel_range(org: Organism, modality: str) -> float:
    channel = org.data.senses.get(modality)  # type: ignore[arg-type]
    if channel is None:
        return 0.0
    return float(channel.range)


def _channel_confidence(org: Organism, modality: str) -> float:
    channel = org.data.senses.get(modality)  # type: ignore[arg-type]
    if channel is None:
        return 0.0
    return float(channel.acuity)


def _field_gradient(
    world: World, field_name: str, x: int, y: int
) -> tuple[float, float]:
    arr = world.field_map.fields[field_name]
    h, w = arr.shape
    gx = float(arr[y, min(x + 1, w - 1)] - arr[y, max(x - 1, 0)])
    gy = float(arr[min(y + 1, h - 1), x] - arr[max(y - 1, 0), x])
    return (gx, gy)


def _entity_candidates(
    org: Organism,
    world: World,
    target: str,
    modality: str,
) -> list[SenseCandidate]:
    ox, oy = org.pos
    sense_range = _channel_range(org, modality)
    if sense_range <= 0.0:
        return []
    conf_base = _channel_confidence(org, modality)
    out: list[SenseCandidate] = []

    for other in world.organisms:
        if not other.alive or other.id == org.id:
            continue
        dist = _dist(ox, oy, other.pos[0], other.pos[1])
        if dist > sense_range:
            continue
        if target == "predator" and other.data.trophic_level <= org.data.trophic_level:
            continue
        if target == "prey" and other.data.trophic_level >= org.data.trophic_level:
            continue
        if target == "food" and other.data.trophic_level > 1:
            continue
        out.append(
            SenseCandidate(
                target_id=other.id,
                distance=dist,
                confidence=conf_base,
            )
        )

    for idx, (species_id, px, py) in enumerate(world.producer_spawns):
        if target not in ("food", "prey"):
            continue
        dist = _dist(ox, oy, px, py)
        if dist > sense_range:
            continue
        virtual_id = -(idx + 1)
        out.append(
            SenseCandidate(
                target_id=virtual_id,
                distance=dist,
                confidence=conf_base * (0.9 if species_id == "mana_moss" else 0.7),
            )
        )

    return out


def pick_sense_candidate(candidates: list[SenseCandidate]) -> SenseCandidate | None:
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda c: (-c.confidence, c.distance, c.target_id),
    )


def query_sense(
    org: Organism,
    world: World,
    modality: str,
    target: str,
) -> SenseResult:
    if target not in ALLOWED_SENSE_TARGETS:
        emit_contract_event(
            world,
            "contract.querysense.unknown_target",
            message=f"unknown target {target!r}",
            species_or_cluster_id=org.data.species_id,
        )
        return SenseResult(success=False)

    if modality not in ALLOWED_SENSE_MODALITIES:
        return SenseResult(success=False)

    ox, oy = org.pos
    candidates: list[SenseCandidate] = []

    if target in ("predator", "prey", "food"):
        for mod in ("sight", "smell"):
            if modality != mod:
                continue
            candidates.extend(_entity_candidates(org, world, target, mod))

    if target == "safety":
        gx, gy = _field_gradient(world, "alarm", ox, oy)
        mag = math.hypot(gx, gy)
        if mag > 1e-6:
            return SenseResult(
                success=True,
                target_id=None,
                distance=0.0,
                gradient=(-gx / mag, -gy / mag),
                confidence=0.5,
            )
        return SenseResult(success=False)

    if target == "resource_mana":
        gx, gy = _field_gradient(world, "mana_geo", ox, oy)
        mag = math.hypot(gx, gy)
        if mag > 1e-6:
            return SenseResult(
                success=True,
                target_id=None,
                distance=0.0,
                gradient=(gx / mag, gy / mag),
                confidence=0.6,
            )
        return SenseResult(success=False)

    best = pick_sense_candidate(candidates)
    if best is not None:
        return SenseResult(
            success=True,
            target_id=best.target_id,
            distance=best.distance,
            gradient=best.gradient,
            confidence=best.confidence,
        )

    if target == "food":
        gx, gy = _field_gradient(world, "sweet", ox, oy)
        mag = math.hypot(gx, gy)
        if mag > 1e-6:
            return SenseResult(
                success=True,
                target_id=None,
                distance=None,
                gradient=(gx / mag, gy / mag),
                confidence=0.4,
            )

    return SenseResult(success=False)


def merge_modalities(
    org: Organism,
    world: World,
    target: str,
) -> SenseResult:
    """Resolve sight+smell per spec: higher confidence, then distance, then id."""
    candidates: list[SenseCandidate] = []
    for mod in ("sight", "smell"):
        for c in _entity_candidates(org, world, target, mod):
            c.confidence = _channel_confidence(org, mod)
            candidates.append(c)
    best = pick_sense_candidate(candidates)
    if best is None:
        return query_sense(org, world, "smell", target)
    return SenseResult(
        success=True,
        target_id=best.target_id,
        distance=best.distance,
        gradient=best.gradient,
        confidence=best.confidence,
    )
