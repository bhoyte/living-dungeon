from __future__ import annotations

import numpy as np
import scipy.ndimage as ndi
from pydantic import BaseModel

from sim.tilemap import TileMap

MAX_DIFFUSE_MIX = 0.9


class FieldConfig(BaseModel):
    decay: float
    diffuse: float
    clamp_lo: float = 0.0
    clamp_hi: float = 1.0
    boundary_mode: str = "constant"
    boundary_val: float = 0.0
    is_special: bool = False


FIELD_CONFIG: dict[str, FieldConfig] = {
    "mana_geo": FieldConfig(decay=0.001, diffuse=0.020),
    "mana_aether": FieldConfig(decay=0.005, diffuse=0.080),
    "mana_aqua": FieldConfig(decay=0.003, diffuse=0.050),
    "temperature": FieldConfig(decay=0.010, diffuse=0.040, clamp_lo=-20.0, clamp_hi=60.0),
    "humidity": FieldConfig(decay=0.008, diffuse=0.060),
    "acidity": FieldConfig(decay=0.005, diffuse=0.030),
    "light": FieldConfig(decay=0.0, diffuse=0.0, is_special=True),
    "tremor": FieldConfig(decay=0.0, diffuse=0.0, is_special=True),
    "sweet": FieldConfig(decay=0.050, diffuse=0.150),
    "alarm": FieldConfig(decay=0.080, diffuse=0.200),
    "corpse": FieldConfig(decay=0.010, diffuse=0.050),
    "spore": FieldConfig(decay=0.020, diffuse=0.100),
}


class FieldMap:
    """Scalar fields on the tile grid. Per-tick updates are fully vectorized."""

    def __init__(
        self,
        tilemap: TileMap,
        baselines: dict[str, float] | None = None,
    ) -> None:
        self.tilemap = tilemap
        h, w = tilemap.h, tilemap.w
        default_baselines: dict[str, float] = {"temperature": 12.0, "humidity": 0.45}
        self.baselines: dict[str, float] = {**default_baselines, **(baselines or {})}

        self.fields: dict[str, np.ndarray] = {
            name: np.zeros((h, w), dtype=np.float32) for name in FIELD_CONFIG
        }
        self.tile_sources = {
            "mana_geo": tilemap.source_field("mana_geo_src"),
            "mana_aqua": tilemap.source_field("mana_aqua_src"),
            "humidity": tilemap.source_field("humidity_src"),
            "acidity": tilemap.source_field("acidity_src"),
            "spore": tilemap.source_field("spore_src"),
        }
        self.tile_sinks = {
            "mana_geo": tilemap.source_field("mana_geo_sink"),
            "humidity": tilemap.source_field("humidity_sink"),
            "acidity": tilemap.source_field("acidity_sink"),
        }

    def _decay_baseline(self, name: str, cfg: FieldConfig) -> float:
        return self.baselines.get(name, cfg.boundary_val)

    def _convolve_cval(self, name: str, cfg: FieldConfig) -> float:
        if name == "temperature":
            return float(self.baselines.get("temperature", 12.0))
        if name == "humidity":
            return float(self.baselines.get("humidity", 0.45))
        return cfg.boundary_val

    def step(self, dt: float) -> None:
        for name, cfg in FIELD_CONFIG.items():
            if cfg.is_special:
                continue
            f = self.fields[name]

            if name in self.tile_sources:
                np.add(f, self.tile_sources[name] * dt, out=f)
            if name in self.tile_sinks:
                np.subtract(f, self.tile_sinks[name] * dt, out=f)

            baseline = self._decay_baseline(name, cfg)
            np.add(f, (baseline - f) * (cfg.decay * dt), out=f)

            if cfg.diffuse > 0:
                kernel = self._kernel(cfg.diffuse)
                cval = self._convolve_cval(name, cfg)
                f[:] = ndi.convolve(
                    f,
                    kernel,
                    mode=cfg.boundary_mode,
                    cval=cval,
                )

            np.clip(f, cfg.clamp_lo, cfg.clamp_hi, out=f)

    @staticmethod
    def _kernel(rate: float) -> np.ndarray:
        rate = min(float(rate), MAX_DIFFUSE_MIX)
        e = rate / 8.0
        c = 1.0 - rate
        return np.array([[e, e, e], [e, c, e], [e, e, e]], dtype=np.float32)

    def deposit(self, x: int, y: int, name: str, amount: float) -> None:
        self.fields[name][y, x] += amount

    def sample(self, x: int, y: int, name: str) -> float:
        return float(self.fields[name][y, x])

    def gradient(self, x: int, y: int, name: str) -> tuple[float, float]:
        f = self.fields[name]
        h, w = f.shape
        yy0, yy1 = max(0, y - 1), min(h, y + 2)
        xx0, xx1 = max(0, x - 1), min(w, x + 2)
        patch = f[yy0:yy1, xx0:xx1]
        gy, gx = np.gradient(patch)
        return float(gx.mean()), float(gy.mean())
