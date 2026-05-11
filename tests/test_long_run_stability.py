from __future__ import annotations

import numpy as np

from sim.fields import FIELD_CONFIG
from sim.floor_profile import FloorProfile, GeologicalFeature
from sim.generation import generate_floor
from sim.telemetry import anomaly_flags, field_extrema
from sim.tick import tick


def _profile_for_long_run() -> FloorProfile:
    return FloorProfile(
        name="Long Run",
        width=40,
        height=28,
        seed=99,
        base_composition="limestone",
        features=[
            GeologicalFeature(type="crystal_node", region="NE", size="medium", count=1),
            GeologicalFeature(type="mycelium_patch", region="SW", size="small", count=1),
            GeologicalFeature(type="water_channel", region="C", size="medium", count=1),
        ],
        seed_producers=["mana_moss"],
        initial_creatures={},
    )


def test_long_run_stability_no_nan_inf_and_no_runaway() -> None:
    world = generate_floor(_profile_for_long_run())

    for _ in range(650):
        tick(world, 1.0)

    for name, arr in world.field_map.fields.items():
        assert np.all(np.isfinite(arr)), name
        cfg = FIELD_CONFIG[name]
        lo, hi = (0.0, 1.0) if cfg.is_special else (cfg.clamp_lo, cfg.clamp_hi)
        assert float(np.min(arr)) >= lo - 1e-4, name
        assert float(np.max(arr)) <= hi + 1e-4, name

    flags = anomaly_flags(world.field_map)
    assert flags["dirty"] is False

    summary = field_extrema(world.field_map)
    assert -20.0 <= summary["temperature"]["mean"] <= 60.0
    assert 0.0 <= summary["humidity"]["mean"] <= 1.0
    assert 0.0 <= summary["mana_geo"]["mean"] <= 1.0
