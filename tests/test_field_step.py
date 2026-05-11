from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from sim.fields import FieldMap
from sim.systems.field_step import step
from sim.tilemap import TileComp, TileMap


def _world_with_maps() -> SimpleNamespace:
    tm = TileMap(8, 8)
    tm.composition[:, :] = TileComp.FLOOR_STONE
    tm.cache_derived()
    fm = FieldMap(tm)
    return SimpleNamespace(tilemap=tm, field_map=fm)


def test_r1_decomposition_increases_acidity_and_mana_geo_and_reduces_corpse() -> None:
    w = _world_with_maps()
    f = w.field_map.fields
    f["corpse"][:, :] = 0.2
    f["acidity"][:, :] = 0.1
    f["mana_geo"][:, :] = 0.05
    before_corpse = f["corpse"].copy()
    before_acid = f["acidity"].copy()
    before_geo = f["mana_geo"].copy()

    step(w, dt=1.0)

    assert float(np.sum(f["corpse"])) < float(np.sum(before_corpse))
    assert float(np.sum(f["acidity"])) > float(np.sum(before_acid))
    assert float(np.sum(f["mana_geo"])) > float(np.sum(before_geo))


def test_r2_mana_geo_bleeds_to_aether() -> None:
    w = _world_with_maps()
    f = w.field_map.fields
    f["mana_geo"][:, :] = 0.5
    f["mana_aether"][:, :] = 0.0

    step(w, dt=1.0)

    assert float(np.min(f["mana_aether"])) > 0.0
    expected = f["mana_geo"] * 0.002 * 1.0
    np.testing.assert_allclose(f["mana_aether"], expected, rtol=1e-5, atol=1e-6)


def test_r5_clamps_reacted_fields() -> None:
    w = _world_with_maps()
    f = w.field_map.fields
    f["mana_geo"][:, :] = 2.0
    f["mana_aether"][:, :] = 2.0
    f["humidity"][:, :] = 2.0
    f["acidity"][:, :] = 2.0
    f["corpse"][:, :] = 2.0

    step(w, dt=0.01)

    for name in ("mana_geo", "mana_aether", "humidity", "acidity", "corpse"):
        assert np.all(f[name] >= 0.0) and np.all(f[name] <= 1.0), name


def test_r3_hot_dries_humidity() -> None:
    w = _world_with_maps()
    f = w.field_map.fields
    f["temperature"][:, :] = 35.0
    f["humidity"][:, :] = 0.8

    step(w, dt=1.0)

    assert float(np.mean(f["humidity"])) < 0.8


def test_r4_dew_adds_acidity() -> None:
    w = _world_with_maps()
    f = w.field_map.fields
    f["temperature"][:, :] = 5.0
    f["humidity"][:, :] = 0.8
    f["acidity"][:, :] = 0.1

    before = float(np.sum(f["acidity"]))
    step(w, dt=1.0)
    assert float(np.sum(f["acidity"])) > before
