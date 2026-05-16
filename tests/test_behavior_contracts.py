from __future__ import annotations

import numpy as np

from sim.fields import FieldMap
from sim.floor_profile import FloorProfile
from sim.generation import generate_floor
from sim.sensing import (
    SenseCandidate,
    check_env,
    pick_sense_candidate,
    query_sense,
)
from sim.tick import tick
from sim.tilemap import TileMap
from sim.world import World


def _minimal_world() -> World:
    profile = FloorProfile(
        name="Contract",
        width=20,
        height=16,
        seed=11,
        bsp_max_room_size=10,
        features=[],
    )
    tilemap = TileMap(20, 16)
    tilemap.cache_derived()
    return World(
        rng=np.random.default_rng(11),
        floor_profile=profile,
        tilemap=tilemap,
        field_map=FieldMap(tilemap),
    )


def test_checkenv_invalid_path_fails_without_crash() -> None:
    world = _minimal_world()
    org = world.add_organism("slime", (5, 5))
    ok = check_env(org, world, "tile.nonexistent_prop", "==", True)
    assert ok is False
    assert any(
        e["event_name"] == "contract.checkenv.invalid_path_or_op"
        for e in world.contract_events
    )


def test_checkenv_invalid_op_fails_without_crash() -> None:
    world = _minimal_world()
    org = world.add_organism("slime", (5, 5))
    ok = check_env(org, world, "env.light", "??", 0.0)
    assert ok is False
    assert world.contract_events


def test_querysense_unknown_target_returns_failure() -> None:
    world = _minimal_world()
    org = world.add_organism("slime", (5, 5))
    result = query_sense(org, world, "smell", "unknown_token")
    assert result.success is False
    assert any(
        e["event_name"] == "contract.querysense.unknown_target"
        for e in world.contract_events
    )


def test_querysense_tie_break_is_deterministic() -> None:
    candidates = [
        SenseCandidate(target_id=3, distance=10.0, confidence=0.8),
        SenseCandidate(target_id=1, distance=10.0, confidence=0.8),
        SenseCandidate(target_id=2, distance=12.0, confidence=0.9),
    ]
    best = pick_sense_candidate(candidates)
    assert best is not None
    assert best.target_id == 2  # highest confidence

    tied = [
        SenseCandidate(target_id=5, distance=8.0, confidence=0.7),
        SenseCandidate(target_id=2, distance=10.0, confidence=0.7),
        SenseCandidate(target_id=9, distance=8.0, confidence=0.7),
    ]
    best_tied = pick_sense_candidate(tied)
    assert best_tied is not None
    assert best_tied.target_id == 5  # smallest distance, then lowest id


def test_600_tick_headless_behavior_loop_is_stable() -> None:
    profile = FloorProfile(
        name="BT Stability",
        width=32,
        height=24,
        seed=42,
        features=[],
        seed_producers=["mana_moss"],
        initial_creatures={"slime": 4},
    )
    w1 = generate_floor(profile)
    w2 = generate_floor(profile)

    def snapshot(world: World) -> list[tuple]:
        return sorted(
            (o.id, o.pos, round(o.energy, 4), round(o.stress, 4), o.alive)
            for o in world.organisms
        )

    for _ in range(600):
        tick(w1, 1.0)
        tick(w2, 1.0)

    assert snapshot(w1) == snapshot(w2)
    assert len([o for o in w1.organisms if o.alive]) > 0
    assert w1.tick == 600


def test_slime_has_behavior_tree_attached() -> None:
    world = _minimal_world()
    org = world.add_organism("slime", (2, 2))
    assert "bt_root" in org.extensions
    assert org.extensions["bt_root"].name == "slime_root"
