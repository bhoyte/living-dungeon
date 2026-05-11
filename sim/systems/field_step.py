"""Quiet v1 field reactions (R1–R5). Runs after FieldMap.step each tick."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from sim.fields import FieldMap


class HasFieldMap(Protocol):
    field_map: FieldMap


def step(world: HasFieldMap, dt: float) -> None:
    f = world.field_map.fields

    # ----- R1: corpse decomposition -----
    decomp_mask = f["corpse"] > 0.05
    decomp_amt = np.where(decomp_mask, f["corpse"] * 0.020 * dt, 0.0).astype(np.float32)
    f["acidity"] += decomp_amt * 0.5
    f["mana_geo"] += decomp_amt * 0.3
    f["corpse"] -= decomp_amt

    # ----- R2: mana_geo → mana_aether bleed -----
    f["mana_aether"] += f["mana_geo"] * 0.002 * dt

    # ----- R3: heat-driven evaporation -----
    hot_mask = f["temperature"] > 30.0
    f["humidity"][hot_mask] -= 0.015 * dt

    # ----- R4: cold-humid acidity (cave dew) -----
    dew_mask = (f["temperature"] < 8.0) & (f["humidity"] > 0.7)
    f["acidity"][dew_mask] += 0.001 * dt

    # ----- R5: re-clamp -----
    for name in ("mana_geo", "mana_aether", "humidity", "acidity", "corpse"):
        np.clip(f[name], 0.0, 1.0, out=f[name])
