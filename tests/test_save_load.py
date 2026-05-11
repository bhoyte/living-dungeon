from __future__ import annotations

import numpy as np

from sim.floor_profile import FloorProfile, GeologicalFeature
from sim.generation import generate_floor
from sim.io import load_checkpoint, save_checkpoint
from sim.tick import tick


def _profile_for_roundtrip() -> FloorProfile:
    return FloorProfile(
        name="Roundtrip",
        width=30,
        height=22,
        seed=1234,
        base_composition="limestone",
        features=[
            GeologicalFeature(type="crystal_node", region="NE", size="small", count=1),
            GeologicalFeature(type="water_channel", region="C", size="small", count=1),
        ],
        seed_producers=[],
        initial_creatures={},
    )


def test_save_load_roundtrip_matches_uninterrupted_baseline(tmp_path) -> None:
    profile = _profile_for_roundtrip()

    baseline = generate_floor(profile)
    for _ in range(300):
        tick(baseline, 1.0)

    interrupted = generate_floor(profile)
    for _ in range(200):
        tick(interrupted, 1.0)

    ckpt_dir = save_checkpoint(interrupted, tmp_path / "checkpoint", tick_index=200)
    loaded, tick_index = load_checkpoint(ckpt_dir)
    assert tick_index == 200

    for _ in range(100):
        tick(loaded, 1.0)

    for name in baseline.field_map.fields:
        np.testing.assert_allclose(
            loaded.field_map.fields[name],
            baseline.field_map.fields[name],
            rtol=1e-5,
            atol=1e-6,
        )
