from __future__ import annotations

import numpy as np

from sim.constants import (
    EPIGENOME_MULT_MAX,
    EPIGENOME_MULT_MIN,
    EPIGENOME_TAU_SEC,
    FAMINE_ENERGY_THRESHOLD,
)
from sim.epigenome import (
    AdaptationMarkers,
    epigenome_snapshot,
    step_epigenome,
    update_epigenome,
    update_stress_from_markers,
    update_stress_markers,
    update_visible_pigmentation,
)
from sim.fields import FieldMap
from sim.floor_profile import FloorProfile
from sim.organisms import Organism
from sim.tilemap import TileMap
from sim.world import World


def _world_with_slime(energy: float = 0.8) -> tuple[World, Organism]:
    profile = FloorProfile(
        name="Epi",
        width=16,
        height=16,
        seed=5,
        bsp_max_room_size=8,
        features=[],
    )
    tilemap = TileMap(16, 16)
    tilemap.cache_derived()
    world = World(
        rng=np.random.default_rng(5),
        floor_profile=profile,
        tilemap=tilemap,
        field_map=FieldMap(tilemap),
    )
    org = world.add_organism("slime", (4, 4))
    org.energy = energy
    world.organism_ids_in_tick_order = [org.id]
    return world, org


def test_organisms_have_independent_epigenome_copies() -> None:
    world, _ = _world_with_slime()
    a = world.add_organism("slime", (2, 2))
    b = world.add_organism("slime", (6, 6))
    a.data.epigenome.metabolism_mult = 0.90
    assert b.data.epigenome.metabolism_mult == 1.0


def test_famine_increases_stress_and_shifts_epigenome() -> None:
    world, org = _world_with_slime(energy=0.25)
    stress_before = org.stress
    snap_before = epigenome_snapshot(org)

    for _ in range(80):
        org.energy = 0.20
        markers = update_stress_markers(org, world, dt=1.0)
        update_stress_from_markers(org, markers, dt=1.0)
        update_epigenome(org, markers, dt=1.0)

    assert org.stress > stress_before
    snap_after = epigenome_snapshot(org)
    assert snap_after["metabolism_mult"] < snap_before["metabolism_mult"]
    assert snap_after["size_mult"] < snap_before["size_mult"]


def test_recovery_decreases_stress() -> None:
    world, org = _world_with_slime(energy=0.2)
    for _ in range(60):
        org.energy = 0.18
        markers = update_stress_markers(org, world, dt=1.0)
        update_stress_from_markers(org, markers, dt=1.0)
        update_epigenome(org, markers, dt=1.0)
    stressed = org.stress

    for _ in range(80):
        org.energy = 0.90
        org.stress = min(1.0, org.stress)
        markers = update_stress_markers(org, world, dt=1.0)
        update_stress_from_markers(org, markers, dt=1.0)
        update_epigenome(org, markers, dt=1.0)

    assert org.stress < stressed


def test_epigenome_fades_toward_neutral_after_pressure_removed() -> None:
    world, org = _world_with_slime(energy=0.2)
    for _ in range(100):
        org.energy = 0.15
        markers = update_stress_markers(org, world, dt=1.0)
        update_stress_from_markers(org, markers, dt=1.0)
        update_epigenome(org, markers, dt=1.0)

    for _ in range(int(EPIGENOME_TAU_SEC * 4)):
        org.energy = 0.92
        markers = update_stress_markers(org, world, dt=1.0)
        update_stress_from_markers(org, markers, dt=1.0)
        update_epigenome(org, markers, dt=1.0)

    snap = epigenome_snapshot(org)
    for value in snap.values():
        assert EPIGENOME_MULT_MIN <= value <= EPIGENOME_MULT_MAX
        assert abs(value - 1.0) < 0.08


def test_epigenome_bounds_enforced_under_extreme_pressure() -> None:
    world, org = _world_with_slime(energy=0.1)
    markers = AdaptationMarkers(starvation=1.0, predation=1.0, abundance=1.0)
    for _ in range(500):
        update_epigenome(org, markers, dt=1.0)
    snap = epigenome_snapshot(org)
    for value in snap.values():
        assert EPIGENOME_MULT_MIN <= value <= EPIGENOME_MULT_MAX


def test_pigmentation_stays_in_unit_interval() -> None:
    world, org = _world_with_slime()
    org.data.epigenome.aggression_mult = EPIGENOME_MULT_MAX
    org.data.epigenome.metabolism_mult = EPIGENOME_MULT_MIN
    org.data.epigenome.size_mult = EPIGENOME_MULT_MAX
    visible = update_visible_pigmentation(org)
    assert all(0.0 <= c <= 1.0 for c in visible)


def test_deterministic_marker_transitions_scripted() -> None:
    world1, org1 = _world_with_slime(energy=FAMINE_ENERGY_THRESHOLD - 0.05)
    world2, org2 = _world_with_slime(energy=FAMINE_ENERGY_THRESHOLD - 0.05)

    for _ in range(120):
        step_epigenome(world1, 1.0)
        step_epigenome(world2, 1.0)

    assert epigenome_snapshot(org1) == epigenome_snapshot(org2)
    assert round(org1.stress, 5) == round(org2.stress, 5)
