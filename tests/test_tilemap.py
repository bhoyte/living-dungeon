import numpy as np

from sim.tilemap import TileComp, TileMap


def _deterministic_map() -> TileMap:
    tilemap = TileMap(8, 8)

    tilemap.composition[:, :] = TileComp.FLOOR_STONE
    tilemap.composition[0, :] = TileComp.WALL_STONE
    tilemap.composition[:, 0] = TileComp.WALL_STONE
    tilemap.composition[1:3, 1:3] = TileComp.WALL_CRYSTAL
    tilemap.composition[4:6, 4:6] = TileComp.SHALLOW_WATER
    tilemap.composition[6, 6] = TileComp.FLOOR_MYCELIUM

    tilemap.cache_derived()
    return tilemap


def test_wall_and_passable_counts() -> None:
    tilemap = _deterministic_map()

    wall_count = int(np.count_nonzero(tilemap.is_wall()))
    passable_count = int(np.count_nonzero(tilemap.source_field("is_passable")))

    assert wall_count == 19
    assert passable_count == 45


def test_source_arrays_shape_and_dtype() -> None:
    tilemap = _deterministic_map()

    mana_geo_src = tilemap.source_field("mana_geo_src")
    is_wall = tilemap.is_wall()

    assert mana_geo_src.shape == (8, 8)
    assert is_wall.shape == (8, 8)
    assert mana_geo_src.dtype == np.float32
    assert is_wall.dtype == np.bool_


def test_cached_arrays_stable_on_repeated_reads() -> None:
    tilemap = _deterministic_map()

    first_wall = tilemap.is_wall()
    second_wall = tilemap.is_wall()
    first_mana_geo = tilemap.source_field("mana_geo_src")
    second_mana_geo = tilemap.source_field("mana_geo_src")

    assert first_wall is second_wall
    assert first_mana_geo is second_mana_geo
    np.testing.assert_array_equal(first_wall, second_wall)
    np.testing.assert_array_equal(first_mana_geo, second_mana_geo)
