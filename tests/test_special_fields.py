from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from sim.fields import FieldMap
from sim.systems.light_cast import cast_light, collect_static_light_sources
from sim.systems.tremor_cast import cast_tremor
from sim.tilemap import TileComp, TileMap


def _make_light_world() -> SimpleNamespace:
    tm = TileMap(16, 12)
    tm.composition[:, :] = TileComp.FLOOR_STONE
    tm.composition[8, 8] = TileComp.FLOOR_CRYSTAL
    tm.cache_derived()
    fm = FieldMap(tm)
    sources = collect_static_light_sources(tm, default_radius=8)
    return SimpleNamespace(tilemap=tm, field_map=fm, static_light_sources=sources)


def test_light_bounded_and_non_negative() -> None:
    w = _make_light_world()
    out = cast_light(w)

    assert out.shape == (12, 16)
    assert np.all(np.isfinite(out))
    assert np.all(out >= 0.0)
    assert np.all(out <= 1.0)
    assert float(np.max(out)) > 0.0


def test_light_writes_field_map() -> None:
    w = _make_light_world()
    out = cast_light(w)
    np.testing.assert_array_equal(w.field_map.fields["light"], out)


def test_tremor_deterministic_for_same_events() -> None:
    tm = TileMap(10, 10)
    tm.composition[:, :] = TileComp.FLOOR_STONE
    tm.cache_derived()

    def run_once() -> np.ndarray:
        fm = FieldMap(tm)
        w = SimpleNamespace(
            tilemap=tm,
            field_map=fm,
            tremor_events_this_tick=[(5, 5, 0.8), (2, 2, 0.4)],
        )
        return cast_tremor(w).copy()

    a = run_once()
    b = run_once()
    np.testing.assert_array_equal(a, b)
    assert np.all(np.isfinite(a))
    assert np.all(a >= 0.0) and np.all(a <= 1.0)


def test_tremor_clears_event_queue() -> None:
    tm = TileMap(6, 6)
    tm.composition[:, :] = TileComp.FLOOR_STONE
    tm.cache_derived()
    fm = FieldMap(tm)
    w = SimpleNamespace(
        tilemap=tm,
        field_map=fm,
        tremor_events_this_tick=[(3, 3, 1.0)],
    )
    cast_tremor(w)
    assert w.tremor_events_this_tick == []
