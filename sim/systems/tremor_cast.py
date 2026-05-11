"""Recompute tremor field from per-tick events via weighted propagation."""

from __future__ import annotations

from heapq import heappop, heappush
from typing import Protocol

import numpy as np

from sim.fields import FieldMap
from sim.tilemap import TileMap


class HasTremorCast(Protocol):
    tilemap: TileMap
    field_map: FieldMap
    tremor_events_this_tick: list[tuple[int, int, float]]
    """(tile_y, tile_x, intensity). Consumed and cleared each cast."""


def cast_tremor(world: HasTremorCast) -> np.ndarray:
    h, w = world.tilemap.h, world.tilemap.w
    absorption = world.tilemap.source_field("sound_absorption")
    tremor = np.zeros((h, w), dtype=np.float32)

    for start_y, start_x, intensity in world.tremor_events_this_tick:
        visited = np.zeros((h, w), dtype=np.bool_)
        heap: list[tuple[float, int, int]] = [(-float(intensity), start_y, start_x)]
        while heap:
            neg_i, cy, cx = heappop(heap)
            if visited[cy, cx]:
                continue
            visited[cy, cx] = True
            cur_i = -neg_i
            tremor[cy, cx] += np.float32(cur_i)
            remaining = cur_i - float(absorption[cy, cx])
            if remaining < 0.02:
                continue
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx]:
                    heappush(heap, (-remaining, ny, nx))

    world.tremor_events_this_tick.clear()
    out = np.clip(tremor, 0.0, 1.0).astype(np.float32)
    world.field_map.fields["tremor"][:] = out
    return out
