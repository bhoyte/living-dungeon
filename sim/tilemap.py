from __future__ import annotations

from enum import IntEnum

import numpy as np
from pydantic import BaseModel


class TileComp(IntEnum):
    # Walls
    WALL_STONE = 0
    WALL_LIMESTONE = 1
    WALL_CRYSTAL = 2
    # Floors
    FLOOR_STONE = 10
    FLOOR_LIMESTONE = 11
    FLOOR_CRYSTAL = 12
    FLOOR_WET_CLAY = 13
    FLOOR_SAND = 14
    FLOOR_BONE = 15
    FLOOR_MYCELIUM = 16
    # Liquids
    SHALLOW_WATER = 20
    DEEP_WATER = 21
    ACID_POOL = 22


class TileProps(BaseModel):
    is_wall: bool = False
    is_passable: bool = True
    is_transparent: bool = True
    traction: float = 1.0
    porosity: float = 0.5
    ceiling_height: int = 3
    elevation: float = 0.0
    sound_absorption: float = 0.05

    mana_geo_src: float = 0.0
    mana_aqua_src: float = 0.0
    humidity_src: float = 0.0
    acidity_src: float = 0.0
    light_src: float = 0.0
    spore_src: float = 0.0

    mana_geo_sink: float = 0.0
    humidity_sink: float = 0.0
    acidity_sink: float = 0.0


TILE_PROPS: dict[TileComp, TileProps] = {
    TileComp.WALL_STONE: TileProps(
        is_wall=True,
        is_passable=False,
        is_transparent=False,
        traction=0.0,
        sound_absorption=0.40,
    ),
    TileComp.WALL_LIMESTONE: TileProps(
        is_wall=True,
        is_passable=False,
        is_transparent=False,
        traction=0.0,
        sound_absorption=0.30,
        acidity_sink=0.005,
    ),
    TileComp.WALL_CRYSTAL: TileProps(
        is_wall=True,
        is_passable=False,
        is_transparent=False,
        traction=0.0,
        sound_absorption=0.20,
        mana_geo_src=0.020,
        light_src=0.30,
    ),
    TileComp.FLOOR_STONE: TileProps(),
    TileComp.FLOOR_LIMESTONE: TileProps(porosity=0.6, acidity_sink=0.008),
    TileComp.FLOOR_CRYSTAL: TileProps(mana_geo_src=0.030, light_src=0.40),
    TileComp.FLOOR_WET_CLAY: TileProps(
        porosity=0.85, humidity_src=0.010, traction=0.85, sound_absorption=0.15
    ),
    TileComp.FLOOR_SAND: TileProps(
        porosity=0.20, traction=0.70, humidity_sink=0.012, sound_absorption=0.20
    ),
    TileComp.FLOOR_BONE: TileProps(porosity=0.45, acidity_sink=0.004),
    TileComp.FLOOR_MYCELIUM: TileProps(
        porosity=0.70,
        mana_geo_sink=0.010,
        spore_src=0.005,
        acidity_src=0.002,
        sound_absorption=0.25,
    ),
    TileComp.SHALLOW_WATER: TileProps(
        traction=0.6,
        mana_aqua_src=0.020,
        humidity_src=0.030,
        ceiling_height=3,
        sound_absorption=0.10,
    ),
    TileComp.DEEP_WATER: TileProps(
        is_passable=False,
        mana_aqua_src=0.040,
        humidity_src=0.040,
        sound_absorption=0.05,
    ),
    TileComp.ACID_POOL: TileProps(traction=0.5, acidity_src=0.030, mana_geo_sink=0.005),
}


class TileMap:
    def __init__(self, w: int, h: int):
        if w <= 0 or h <= 0:
            raise ValueError("TileMap dimensions must be positive.")
        self.w, self.h = w, h
        self.composition = np.full((h, w), TileComp.FLOOR_STONE, dtype=np.int8)
        self._cache: dict[str, np.ndarray] = {}

    def cache_derived(self) -> None:
        for attr_name, dtype, default in [
            ("is_wall", np.bool_, False),
            ("is_passable", np.bool_, True),
            ("is_transparent", np.bool_, True),
            ("traction", np.float32, 1.0),
            ("porosity", np.float32, 0.5),
            ("sound_absorption", np.float32, 0.05),
            ("mana_geo_src", np.float32, 0.0),
            ("mana_aqua_src", np.float32, 0.0),
            ("humidity_src", np.float32, 0.0),
            ("acidity_src", np.float32, 0.0),
            ("light_src", np.float32, 0.0),
            ("spore_src", np.float32, 0.0),
            ("mana_geo_sink", np.float32, 0.0),
            ("humidity_sink", np.float32, 0.0),
            ("acidity_sink", np.float32, 0.0),
        ]:
            arr = np.full((self.h, self.w), default, dtype=dtype)
            for comp, props in TILE_PROPS.items():
                mask = self.composition == comp
                if np.any(mask):
                    arr[mask] = getattr(props, attr_name)
            self._cache[attr_name] = arr

    def _require_cached(self, attr_name: str) -> np.ndarray:
        if attr_name not in self._cache:
            raise RuntimeError(
                f"Missing cached attribute '{attr_name}'. Call cache_derived() first."
            )
        return self._cache[attr_name]

    def is_wall(self) -> np.ndarray:
        return self._require_cached("is_wall")

    def transparency(self) -> np.ndarray:
        return self._require_cached("is_transparent")

    def source_field(self, attr: str) -> np.ndarray:
        return self._require_cached(attr)
