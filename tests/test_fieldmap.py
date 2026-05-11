from __future__ import annotations

import numpy as np
import pytest

from sim.fields import FIELD_CONFIG, FieldMap, MAX_DIFFUSE_MIX
from sim.tilemap import TileComp, TileMap


def _tiny_tilemap() -> TileMap:
    tm = TileMap(8, 8)
    tm.composition[:, :] = TileComp.FLOOR_STONE
    tm.cache_derived()
    return tm


def _summarize(field_map: FieldMap) -> dict[str, tuple[float, float, float]]:
    out: dict[str, tuple[float, float, float]] = {}
    for name, arr in field_map.fields.items():
        out[name] = (float(np.min(arr)), float(np.max(arr)), float(np.mean(arr)))
    return out


def test_deterministic_repeat_same_seed() -> None:
    tm = _tiny_tilemap()
    baselines = {"temperature": 14.0, "humidity": 0.5}
    seed = 42
    steps, dt = 40, 0.05

    def run_once() -> dict[str, tuple[float, float, float]]:
        rng = np.random.default_rng(seed)
        fm = FieldMap(tm, baselines=baselines)
        for name, arr in fm.fields.items():
            cfg = FIELD_CONFIG[name]
            if cfg.is_special:
                continue
            lo, hi = cfg.clamp_lo + 0.05, cfg.clamp_hi - 0.05
            if hi <= lo:
                lo, hi = cfg.clamp_lo, cfg.clamp_hi
            fm.fields[name][:] = rng.uniform(lo, hi, size=arr.shape).astype(np.float32)

        for _ in range(steps):
            fm.step(dt)
        return _summarize(fm)

    a = run_once()
    b = run_once()
    assert a == b


def test_no_nan_or_inf_after_many_steps() -> None:
    tm = _tiny_tilemap()
    fm = FieldMap(tm, baselines={"temperature": 12.0, "humidity": 0.45})
    rng = np.random.default_rng(1)
    for name, arr in fm.fields.items():
        if FIELD_CONFIG[name].is_special:
            continue
        fm.fields[name][:] = rng.uniform(0.0, 1.0, size=arr.shape).astype(np.float32)
    fm.fields["temperature"][:] = rng.uniform(-10.0, 30.0, size=fm.fields["temperature"].shape).astype(
        np.float32
    )

    for _ in range(200):
        fm.step(0.1)

    for name, arr in fm.fields.items():
        if FIELD_CONFIG[name].is_special:
            continue
        assert np.all(np.isfinite(arr)), name


def test_values_respect_clamps() -> None:
    tm = _tiny_tilemap()
    fm = FieldMap(tm)
    rng = np.random.default_rng(7)
    for name, arr in fm.fields.items():
        cfg = FIELD_CONFIG[name]
        if cfg.is_special:
            continue
        fm.fields[name][:] = rng.uniform(cfg.clamp_lo - 5.0, cfg.clamp_hi + 5.0, size=arr.shape).astype(
            np.float32
        )

    for _ in range(100):
        fm.step(0.02)

    for name, arr in fm.fields.items():
        cfg = FIELD_CONFIG[name]
        if cfg.is_special:
            continue
        assert np.all(arr >= cfg.clamp_lo - 1e-4), name
        assert np.all(arr <= cfg.clamp_hi + 1e-4), name


def test_uniform_field_decays_toward_baseline_monotone_mean() -> None:
    """Uniform tile-sourced field on stone (zero sources): decay pulls mean toward baseline."""
    tm = _tiny_tilemap()
    fm = FieldMap(tm, baselines={"humidity": 0.5})
    fm.fields["humidity"][:] = 0.9

    means: list[float] = []
    for _ in range(20):
        fm.step(0.1)
        means.append(float(np.mean(fm.fields["humidity"])))

    for a, b in zip(means[:-1], means[1:], strict=True):
        assert b <= a + 1e-5


def test_diffusion_kernel_never_negative_center() -> None:
    for r in [0.2, 0.9, 1.5]:
        k = FieldMap._kernel(r)
        assert k[1, 1] >= 0.0
        assert np.isclose(k.sum(), 1.0, rtol=1e-5)
        assert float(k[1, 1]) <= 1.0


@pytest.mark.parametrize("rate", [0.95, 1.2, 2.0])
def test_kernel_rate_clamped(rate: float) -> None:
    k = FieldMap._kernel(rate)
    assert k[1, 1] >= 1.0 - MAX_DIFFUSE_MIX
