"""Floor generation: BSP rooms, composition painting, fields, warm-up, seeding."""

from __future__ import annotations

import tcod.bsp
import tcod.random
import numpy as np
import opensimplex

from sim.fields import FieldMap
from sim.floor_profile import FloorProfile, GeologicalFeature
from sim.systems.field_step import step as reaction_step
from sim.systems.light_cast import collect_static_light_sources
from sim.systems.producer_seeding import seed_producer
from sim.tilemap import TileComp, TileMap
from sim.world import World

WARMUP_TICKS = 30
WARMUP_DT = 1.0

_WALL_TMP = TileComp.WALL_STONE
_FLOOR_TMP = TileComp.FLOOR_STONE

_BASE_WALL: dict[str, TileComp] = {
    "limestone": TileComp.WALL_LIMESTONE,
    "stone": TileComp.WALL_STONE,
    "bone": TileComp.WALL_STONE,
}
_BASE_FLOOR: dict[str, TileComp] = {
    "limestone": TileComp.FLOOR_LIMESTONE,
    "stone": TileComp.FLOOR_STONE,
    "bone": TileComp.FLOOR_BONE,
}


def paint_base_composition(tilemap: TileMap, base: str) -> None:
    """Replace temporary carve markers with profile wall/floor compositions."""
    wall_tgt = _BASE_WALL[base]
    floor_tgt = _BASE_FLOOR[base]
    comp = tilemap.composition
    comp[comp == _WALL_TMP] = wall_tgt
    comp[comp == _FLOOR_TMP] = floor_tgt


def _region_xy_bounds(region: str, w: int, h: int) -> tuple[int, int, int, int]:
    mx, my = w // 2, h // 2
    if region == "NE":
        return (mx, w - 1, 0, max(0, my - 1))
    if region == "NW":
        return (0, max(0, mx - 1), 0, max(0, my - 1))
    if region == "SE":
        return (mx, w - 1, my, h - 1)
    if region == "SW":
        return (0, max(0, mx - 1), my, h - 1)
    if region == "C":
        qx, qy = w // 4, h // 4
        return (qx, w - 1 - qx, qy, h - 1 - qy)
    if region == "edge":
        return (0, w - 1, 0, h - 1)
    return (0, w - 1, 0, h - 1)


def _size_radius(feature: GeologicalFeature) -> int:
    return {"small": 2, "medium": 3, "large": 5}[feature.size]


def _random_floor_in_region(
    tilemap: TileMap,
    rng: np.random.Generator,
    x0: int,
    x1: int,
    y0: int,
    y1: int,
) -> tuple[int, int] | None:
    floor_mask = ~tilemap.is_wall()
    comp = tilemap.composition
    h, w = comp.shape
    xs = np.arange(w)
    ys = np.arange(h)
    xx, yy = np.meshgrid(xs, ys, indexing="xy")
    m = (
        floor_mask
        & (xx >= x0)
        & (xx <= x1)
        & (yy >= y0)
        & (yy <= y1)
    )
    idx = np.argwhere(m)
    if len(idx) == 0:
        return None
    pick = int(rng.choice(len(idx)))
    y, x = int(idx[pick, 0]), int(idx[pick, 1])
    return (y, x)


def place_feature(
    tilemap: TileMap,
    feature: GeologicalFeature,
    rng: np.random.Generator,
    profile: FloorProfile,
) -> None:
    w, h = profile.width, profile.height
    x0, x1, y0, y1 = _region_xy_bounds(feature.region, w, h)
    cyx = _random_floor_in_region(tilemap, rng, x0, x1, y0, y1)
    if cyx is None:
        return
    cy, cx = cyx
    r = _size_radius(feature)

    comp = tilemap.composition

    if feature.type == "crystal_node":
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy > r * r:
                    continue
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w:
                    if dx * dx + dy * dy <= (r - 1) * (r - 1):
                        comp[ny, nx] = TileComp.FLOOR_CRYSTAL
                    else:
                        comp[ny, nx] = TileComp.WALL_CRYSTAL

    elif feature.type == "water_channel":
        x_start = max(1, x0)
        x_end = min(w - 2, x1)
        for nx in range(x_start, x_end + 1):
            if 0 <= cy < h:
                comp[cy, nx] = TileComp.SHALLOW_WATER

    elif feature.type == "mycelium_patch":
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w and not tilemap.is_wall()[ny, nx]:
                    comp[ny, nx] = TileComp.FLOOR_MYCELIUM

    elif feature.type == "bone_deposit":
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w and not tilemap.is_wall()[ny, nx]:
                    comp[ny, nx] = TileComp.FLOOR_BONE

    elif feature.type == "acid_pool":
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy > r * r:
                    continue
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w and not tilemap.is_wall()[ny, nx]:
                    comp[ny, nx] = TileComp.ACID_POOL

    elif feature.type == "sand_basin":
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w and not tilemap.is_wall()[ny, nx]:
                    comp[ny, nx] = TileComp.FLOOR_SAND


def bsp_carve(
    tilemap: TileMap,
    profile: FloorProfile,
    rng_tcod: tcod.random.Random,
) -> list[tuple[int, int]]:
    w, h = profile.width, profile.height
    tilemap.composition[:, :] = _WALL_TMP

    root = tcod.bsp.BSP(0, 0, w, h)
    depth = max(4, min(8, (w * h) // 400))
    root.split_recursive(
        depth,
        profile.bsp_min_room_size,
        profile.bsp_min_room_size,
        1.25,
        1.25,
        rng_tcod,
    )

    centers: list[tuple[int, int]] = []
    for node in root.pre_order():
        if node.children:
            continue
        nw, nh = int(node.width), int(node.height)
        if nw < 4 or nh < 4:
            continue
        rx = int(node.x) + 1
        ry = int(node.y) + 1
        rw, rh = nw - 2, nh - 2
        if rw < 2 or rh < 2:
            continue
        tilemap.composition[ry : ry + rh, rx : rx + rw] = _FLOOR_TMP
        cx = rx + rw // 2
        cy = ry + rh // 2
        centers.append((cx, cy))
    return centers


def connect_rooms(tilemap: TileMap, centers: list[tuple[int, int]]) -> None:
    if len(centers) < 2:
        return
    h, w = tilemap.composition.shape
    for (x1, y1), (x2, y2) in zip(centers, centers[1:], strict=False):
        x, y = x1, y1
        while x != x2:
            if x2 > x:
                x += 1
            elif x2 < x:
                x -= 1
            else:
                break
            if 0 <= y < h and 0 <= x < w and tilemap.composition[y, x] == _WALL_TMP:
                tilemap.composition[y, x] = _FLOOR_TMP
        while y != y2:
            if y2 > y:
                y += 1
            elif y2 < y:
                y -= 1
            else:
                break
            if 0 <= y < h and 0 <= x < w and tilemap.composition[y, x] == _WALL_TMP:
                tilemap.composition[y, x] = _FLOOR_TMP


def seed_initial_fields(world: World, profile: FloorProfile) -> None:
    opensimplex.seed(profile.seed)
    w, h = world.tilemap.w, world.tilemap.h
    xs = np.arange(w, dtype=np.float64) / 12.0
    ys = np.arange(h, dtype=np.float64) / 12.0

    if profile.pocket_noise == "worley":
        try:
            from pyfastnoiselite.pyfastnoiselite import (
                CellularDistanceFunction,
                CellularReturnType,
                FastNoiseLite,
                NoiseType,
            )

            n = FastNoiseLite(seed=profile.seed)
            n.noise_type = NoiseType.NoiseType_Cellular
            n.cellular_distance_function = (
                CellularDistanceFunction.CellularDistanceFunction_Euclidean
            )
            n.cellular_return_type = CellularReturnType.CellularReturnType_Distance2Sub
            xx, yy = np.meshgrid(np.arange(w), np.arange(h), indexing="xy")
            mana_noise = np.vectorize(lambda x, y: n.get_noise(x * 1.2, y * 1.2))(xx, yy).astype(
                np.float32
            )
            mana_noise = (mana_noise + 1.0) / 2.0
        except ImportError:
            mana_noise = ((opensimplex.noise2array(xs, ys).astype(np.float32) + 1.0) / 2.0)
    else:
        mana_noise = (opensimplex.noise2array(xs, ys).astype(np.float32) + 1.0) / 2.0

    world.field_map.fields["mana_geo"][:] = mana_noise * 0.10

    noise_h = opensimplex.noise2array(xs + 100.0, ys + 100.0).astype(np.float32)
    world.field_map.fields["humidity"][:] = np.clip(
        profile.base_humidity + noise_h * 0.10, 0.0, 1.0
    ).astype(np.float32)
    world.field_map.fields["temperature"][:] = np.float32(profile.base_temperature)
    world.field_map.fields["mana_aether"][:] = np.float32(profile.base_mana_aether)


def random_passable_tile(world: World, rng: np.random.Generator) -> tuple[int, int]:
    passable = ~world.tilemap.is_wall()
    idx = np.argwhere(passable)
    if len(idx) == 0:
        raise RuntimeError("No passable tiles for spawn.")
    pick = int(rng.choice(len(idx)))
    y, x = int(idx[pick, 0]), int(idx[pick, 1])
    return (x, y)


def generate_floor(profile: FloorProfile) -> World:
    rng = np.random.default_rng(profile.seed)
    rng_tcod = tcod.random.Random(seed=profile.seed)

    tilemap = TileMap(profile.width, profile.height)
    centers = bsp_carve(tilemap, profile, rng_tcod)
    connect_rooms(tilemap, centers)

    paint_base_composition(tilemap, profile.base_composition)
    tilemap.cache_derived()

    for feature in profile.features:
        for _ in range(feature.count):
            place_feature(tilemap, feature, rng, profile)

    tilemap.cache_derived()

    field_map = FieldMap(
        tilemap,
        baselines={
            "temperature": profile.base_temperature,
            "humidity": profile.base_humidity,
            "mana_aether": profile.base_mana_aether,
        },
    )

    world = World(
        rng=rng,
        floor_profile=profile,
        tilemap=tilemap,
        field_map=field_map,
        static_light_sources=collect_static_light_sources(tilemap),
    )

    seed_initial_fields(world, profile)

    for _ in range(WARMUP_TICKS):
        world.field_map.step(WARMUP_DT)
        reaction_step(world, WARMUP_DT)

    for sp in profile.seed_producers:
        seed_producer(world, sp)

    for sp, n in profile.initial_creatures.items():
        for _ in range(n):
            world.spawn_creature(sp, random_passable_tile(world, rng))

    return world
