from __future__ import annotations

import hashlib

import numpy as np

from sim.floor_profile import FloorProfile, GeologicalFeature
from sim.generation import generate_floor


def _test_profile() -> FloorProfile:
    return FloorProfile(
        name="Determinism Test",
        width=32,
        height=24,
        seed=2026,
        base_composition="limestone",
        features=[
            GeologicalFeature(type="crystal_node", region="NE", size="small", count=1),
            GeologicalFeature(type="mycelium_patch", region="SW", size="small", count=1),
        ],
        seed_producers=["mana_moss"],
        initial_creatures={"slime": 2},
    )


def _field_summary(field_map) -> dict[str, tuple[float, float, float]]:
    out: dict[str, tuple[float, float, float]] = {}
    for name, arr in field_map.fields.items():
        if name in ("light", "tremor"):
            continue
        f = arr.astype(np.float64)
        out[name] = (float(np.min(f)), float(np.max(f)), float(np.mean(f)))
    return out


def test_tilemap_hash_identical_for_same_profile() -> None:
    p = _test_profile()
    w1 = generate_floor(p)
    w2 = generate_floor(p)
    h1 = hashlib.sha256(w1.tilemap.composition.tobytes()).hexdigest()
    h2 = hashlib.sha256(w2.tilemap.composition.tobytes()).hexdigest()
    assert h1 == h2


def test_field_summaries_match_for_same_profile() -> None:
    p = _test_profile()
    w1 = generate_floor(p)
    w2 = generate_floor(p)
    s1 = _field_summary(w1.field_map)
    s2 = _field_summary(w2.field_map)
    assert s1.keys() == s2.keys()
    for k in s1:
        np.testing.assert_allclose(s1[k], s2[k], rtol=1e-6, atol=1e-5)
