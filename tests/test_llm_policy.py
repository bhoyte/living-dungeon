from __future__ import annotations

import time

from sim.adaptation import (
    AdaptationResponse,
    cluster_signature,
    detect_clusters,
    validate_adaptation_full,
    validate_adaptation_schema,
)
from sim.adaptation_cache import CacheEntry
from sim.constants import (
    CLUSTER_STRESS_THRESHOLD,
    LLM_CIRCUIT_FAILURE_THRESHOLD,
    LLM_REQUEST_TIMEOUT_SEC,
    POPULATION_SCAN_INTERVAL,
)
from sim.epigenome import AdaptationMarkers
from sim.floor_profile import FloorProfile
from sim.generation import generate_floor
from sim.llm_adapter import (
    LlmCircuitState,
    StubLlmAdapter,
    enqueue_llm_request,
    poll_llm_completions,
)
from sim.tick import tick
from sim.world import World


def _stressed_world(n: int = 4, *, seed: int = 88) -> World:
    profile = FloorProfile(
        name="LLM",
        width=24,
        height=18,
        seed=seed,
        features=[],
        seed_producers=[],
        initial_creatures={"slime": n},
    )
    world = generate_floor(profile)
    for org in world.organisms:
        if org.data.species_id == "slime":
            org.energy = 0.22
            org.stress = CLUSTER_STRESS_THRESHOLD + 0.08
            org.extensions["markers"] = AdaptationMarkers(starvation=0.92, predation=0.05)
    return world


def test_semantic_validation_rejects_pressure_mismatch() -> None:
    world = _stressed_world(seed=87)
    cluster = detect_clusters(world)[0]
    resp = AdaptationResponse(subtree_key="aggressive_foraging")
    assert validate_adaptation_schema(resp)
    assert validate_adaptation_full(resp, cluster) is False


def test_timeout_does_not_block_tick() -> None:
    world = _stressed_world()
    world.llm_enabled = True
    world.llm_adapter = StubLlmAdapter(delay_sec=LLM_REQUEST_TIMEOUT_SEC + 2.0)

    start = time.perf_counter()
    for _ in range(5):
        tick(world, 1.0)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0
    assert world.tick == 5


def test_circuit_opens_after_repeated_failures() -> None:
    circuit = LlmCircuitState()
    for t in range(LLM_CIRCUIT_FAILURE_THRESHOLD):
        circuit.record_failure(t)
    assert circuit.is_open(LLM_CIRCUIT_FAILURE_THRESHOLD)
    assert circuit.consecutive_failures >= LLM_CIRCUIT_FAILURE_THRESHOLD


def test_cache_hit_bypasses_llm_enqueue() -> None:
    world = _stressed_world()
    world.llm_enabled = True
    world.llm_adapter = StubLlmAdapter(
        response=AdaptationResponse(subtree_key="dormancy", confidence=1.0)
    )
    for t in range(1, POPULATION_SCAN_INTERVAL):
        tick(world, 1.0)
    cluster = detect_clusters(world)[0]
    sig = cluster_signature(cluster, world)
    world.adaptation_cache[sig] = CacheEntry(
        signature=sig,
        subtree_key="dormancy",
        state="promoted",
        sample_count=10,
        success_rate=0.9,
    )
    tick(world, 1.0)

    started = [e for e in world.adaptation_events if e["event_name"] == "llm.request.started"]
    assert len(started) == 0
    assert any(e["event_name"] == "adaptation.cache.hit" for e in world.adaptation_events)


def test_live_path_completes_without_blocking_ticks() -> None:
    profile = FloorProfile(
        name="LLM Live",
        width=24,
        height=18,
        seed=91,
        features=[],
        seed_producers=["mana_moss"],
        initial_creatures={"slime": 4},
    )
    world = generate_floor(profile)
    for org in world.organisms:
        if org.data.species_id == "slime":
            org.energy = 0.35
            org.stress = CLUSTER_STRESS_THRESHOLD + 0.08
            org.extensions["markers"] = AdaptationMarkers(starvation=0.92, predation=0.05)
    world.llm_enabled = True
    world.llm_adapter = StubLlmAdapter(
        response=AdaptationResponse(subtree_key="dormancy", confidence=0.9),
    )

    for t in range(1, POPULATION_SCAN_INTERVAL + 20):
        tick(world, 1.0)

    completed = [e for e in world.adaptation_events if e["event_name"] == "llm.request.completed"]
    assert len(completed) >= 1
    assert len(world.pending_llm) == 0


def test_invalid_llm_payload_rejected_with_no_cache_insert() -> None:
    world = _stressed_world(seed=92)
    cluster = detect_clusters(world)[0]
    sig = cluster_signature(cluster, world)
    world.llm_enabled = True
    world.llm_adapter = StubLlmAdapter(
        response=AdaptationResponse(subtree_key="not_in_library", confidence=0.5),
    )
    enqueue_llm_request(world, cluster, sig)
    for _ in range(20):
        poll_llm_completions(world)
        world.tick += 1
    assert sig not in world.adaptation_cache or world.adaptation_cache[sig].subtree_key != "not_in_library"


def test_mocked_path_still_passes_when_llm_disabled() -> None:
    world = _stressed_world(seed=93)
    assert world.llm_enabled is False
    for _ in range(POPULATION_SCAN_INTERVAL):
        tick(world, 1.0)
    assert len(world.adaptation_cache) >= 1
    assert not any(e["event_name"] == "llm.request.started" for e in world.adaptation_events)
