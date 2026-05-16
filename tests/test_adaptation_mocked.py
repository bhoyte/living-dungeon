from __future__ import annotations

import numpy as np

from sim.adaptation import (
    AdaptationResponse,
    Cluster,
    cluster_signature,
    detect_clusters,
    ingest_adaptation,
    mock_adaptation_provider,
    validate_adaptation_response,
    _maybe_demote,
    _maybe_invalidate,
    _maybe_promote,
)
from sim.adaptation_cache import CacheEntry
from sim.constants import (
    CACHE_INVALIDATE_FAILURES,
    CACHE_PROMOTE_MIN_SAMPLES,
    CACHE_PROMOTE_MIN_STRESS_REDUCTION,
    CACHE_PROMOTE_MIN_SUCCESS_RATE,
    CLUSTER_STRESS_THRESHOLD,
    POPULATION_SCAN_INTERVAL,
)
from sim.epigenome import AdaptationMarkers
from sim.fields import FieldMap
from sim.floor_profile import FloorProfile
from sim.generation import generate_floor
from sim.tick import tick
from sim.tilemap import TileMap
from sim.world import World


def _stressed_cluster_world(n_slimes: int = 4) -> World:
    profile = FloorProfile(
        name="Adapt",
        width=24,
        height=18,
        seed=31,
        features=[],
        seed_producers=[],
        initial_creatures={"slime": n_slimes},
    )
    world = generate_floor(profile)
    for org in world.organisms:
        if org.data.species_id == "slime":
            org.energy = 0.25
            org.stress = CLUSTER_STRESS_THRESHOLD + 0.05
            org.extensions["markers"] = AdaptationMarkers(starvation=0.9, predation=0.1)
    return world


def test_signature_generation_is_deterministic() -> None:
    world1 = _stressed_cluster_world()
    world2 = _stressed_cluster_world()
    c1 = detect_clusters(world1)[0]
    c2 = detect_clusters(world2)[0]
    assert cluster_signature(c1, world1) == cluster_signature(c2, world2)


def test_invalid_adaptation_payload_rejected_without_cache_pollution() -> None:
    profile = FloorProfile(name="X", width=16, height=16, seed=1, bsp_max_room_size=8, features=[])
    tilemap = TileMap(16, 16)
    tilemap.cache_derived()
    world = World(
        rng=np.random.default_rng(1),
        floor_profile=profile,
        tilemap=tilemap,
        field_map=FieldMap(tilemap),
    )
    cluster = Cluster(species_id="slime", members=[])
    bad = AdaptationResponse(subtree_key="not_a_real_subtree")
    assert validate_adaptation_response(bad) is False
    assert ingest_adaptation(world, cluster, "sig000", bad) is False
    assert "sig000" not in world.adaptation_cache


def test_cache_lifecycle_promote_demote_invalidate() -> None:
    entry = CacheEntry(signature="abc", subtree_key="dormancy", state="candidate")
    entry.sample_count = CACHE_PROMOTE_MIN_SAMPLES
    entry.success_rate = CACHE_PROMOTE_MIN_SUCCESS_RATE
    entry.stress_reduction = CACHE_PROMOTE_MIN_STRESS_REDUCTION + 0.01
    _maybe_promote(entry)
    assert entry.state == "promoted"

    entry.success_rate = 0.1
    entry.sample_count = CACHE_PROMOTE_MIN_SAMPLES + 1
    _maybe_demote(entry)
    assert entry.state == "demoted"

    entry.consecutive_failures = CACHE_INVALIDATE_FAILURES
    _maybe_invalidate(entry)
    assert entry.state == "invalidated"


def test_mocked_end_to_end_adaptation_loop() -> None:
    world = _stressed_cluster_world(n_slimes=4)
    assert len(detect_clusters(world)) == 1

    for t in range(1, POPULATION_SCAN_INTERVAL + 1):
        tick(world, 1.0)

    assert len(world.adaptation_cache) >= 1
    assert any(e["event_name"] == "adaptation.cache.insert" for e in world.adaptation_events)

    cluster = detect_clusters(world)[0]
    sig = cluster_signature(cluster, world)
    entry = world.adaptation_cache[sig]
    assert entry.subtree_key in ("dormancy", "scatter_and_hide", "aggressive_foraging", "migration_up")

    for member in cluster.members:
        assert member.extensions.get("adaptation_subtree_key") == entry.subtree_key

    events_before = len(world.adaptation_events)
    for _ in range(POPULATION_SCAN_INTERVAL):
        tick(world, 1.0)
    hits = [e for e in world.adaptation_events[events_before:] if e["event_name"] == "adaptation.cache.hit"]
    assert len(hits) >= 1 or any(
        e["event_name"] in ("adaptation.cache.insert", "adaptation.cache.reinsert")
        for e in world.adaptation_events[events_before:]
    )


def test_mock_provider_maps_starvation_to_dormancy() -> None:
    cluster = Cluster(
        species_id="slime",
        members=[],
    )
    world = _stressed_cluster_world()
    cluster.members = [o for o in world.organisms if o.data.species_id == "slime"][:3]
    for m in cluster.members:
        m.extensions["markers"] = AdaptationMarkers(starvation=0.95, predation=0.0, abundance=0.0)
    resp = mock_adaptation_provider(cluster, world)
    assert resp.subtree_key == "dormancy"
