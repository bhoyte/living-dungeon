"""Recompute light field from static tile emitters via tcod FOV."""

from __future__ import annotations

from typing import Protocol

import numpy as np
import tcod

from sim.fields import FieldMap
from sim.tilemap import TileMap


class HasLightCast(Protocol):
    tilemap: TileMap
    field_map: FieldMap
    static_light_sources: list[tuple[int, int, float, int]]
    """(tile_y, tile_x, intensity, radius) per emitter."""


def collect_static_light_sources(tilemap: TileMap, default_radius: int = 12) -> list[tuple[int, int, float, int]]:
    """Scan cached light_src for emitters (typically called once at generation)."""
    src = tilemap.source_field("light_src")
    ys, xs = np.nonzero(src > 0.0)
    out: list[tuple[int, int, float, int]] = []
    for y, x in zip(ys.tolist(), xs.tolist(), strict=True):
        iy, ix = int(y), int(x)
        out.append((iy, ix, float(src[iy, ix]), default_radius))
    return out


def cast_light(world: HasLightCast) -> np.ndarray:
    h, w = world.tilemap.h, world.tilemap.w
    transparency = world.tilemap.transparency()
    light = np.zeros((h, w), dtype=np.float32)

    for y, x, intensity, radius in world.static_light_sources:
        # tcod expects POV as (row, col) for this API.
        fov = tcod.map.compute_fov(transparency, (y, x), radius=int(radius))
        yy, xx = np.ogrid[:h, :w]
        dist = np.hypot(xx - x, yy - y)
        atten = np.clip(1.0 - dist / max(radius, 1), 0.0, 1.0).astype(np.float32)
        np.add(light, np.where(fov, intensity * atten, 0.0), out=light)

    out = np.clip(light, 0.0, 1.0).astype(np.float32)
    world.field_map.fields["light"][:] = out
    return out
