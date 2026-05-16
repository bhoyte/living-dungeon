"""Signature generation, subtree cache lifecycle, and mocked adaptation ingestion."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import py_trees
from pydantic import BaseModel, Field

from sim.adaptation_cache import CacheEntry
from sim.constants import (
    CACHE_DEMOTE_SUCCESS_RATE,
    CACHE_INVALIDATE_FAILURES,
    CACHE_PROMOTE_MIN_SAMPLES,
    CACHE_PROMOTE_MIN_STRESS_REDUCTION,
    CACHE_PROMOTE_MIN_SUCCESS_RATE,
    CLUSTER_MIN_SIZE,
    CLUSTER_STRESS_THRESHOLD,
    FALLBACK_SUBTREE_KEY,
    POPULATION_SCAN_INTERVAL,
)
from sim.epigenome import AdaptationMarkers
from sim.organisms import Organism

if TYPE_CHECKING:
    from sim.world import World


class EvolutionaryPressure(BaseModel):
    starvation: float = 0.0
    predation: float = 0.0
    abundance: float = 0.0
    isolation: float = 0.0
    nemesis_id: str | None = None

    def dominant(self) -> str:
        levels = {
            "starvation": self.starvation,
            "predation": self.predation,
            "abundance": self.abundance,
            "isolation": self.isolation,
        }
        name, value = max(levels.items(), key=lambda kv: kv[1])
        return name if value >= 0.15 else "none"


class AdaptationResponse(BaseModel):
    subtree_key: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""


@dataclass
class Cluster:
    species_id: str
    members: list[Organism] = field(default_factory=list)

    @property
    def mean_stress(self) -> float:
        if not self.members:
            return 0.0
        return sum(m.stress for m in self.members) / len(self.members)

    @property
    def mean_energy(self) -> float:
        if not self.members:
            return 0.0
        return sum(m.energy for m in self.members) / len(self.members)

    def aggregate_pressure(self) -> EvolutionaryPressure:
        starvation = predation = abundance = 0.0
        n = len(self.members)
        for m in self.members:
            markers: AdaptationMarkers = m.extensions.get("markers", AdaptationMarkers())
            if not isinstance(markers, AdaptationMarkers):
                markers = AdaptationMarkers()
            starvation += markers.starvation
            predation += markers.predation
            abundance += markers.abundance
        return EvolutionaryPressure(
            starvation=starvation / n,
            predation=predation / n,
            abundance=abundance / n,
        )


def _env_bucket(world: World, cluster: Cluster) -> str:
    lights: list[float] = []
    alarms: list[float] = []
    f = world.field_map.fields
    for m in cluster.members:
        x, y = m.pos
        lights.append(float(f["light"][y, x]))
        alarms.append(float(f["alarm"][y, x]))
    light_q = int(sum(lights) / len(lights) * 10) if lights else 0
    alarm_q = int(sum(alarms) / len(alarms) * 10) if alarms else 0
    return f"L{light_q}_A{alarm_q}"


def cluster_signature(cluster: Cluster, world: World) -> str:
    pressure = cluster.aggregate_pressure()
    payload = "|".join(
        [
            cluster.species_id,
            pressure.dominant(),
            str(world.floor_profile.depth_index),
            _env_bucket(world, cluster),
            f"E{int(cluster.mean_energy * 10)}",
            f"S{int(cluster.mean_stress * 10)}",
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def detect_clusters(world: World) -> list[Cluster]:
    by_species: dict[str, list[Organism]] = {}
    for org in world.organisms:
        if not org.alive or org.data.trophic_level == 0:
            continue
        by_species.setdefault(org.data.species_id, []).append(org)
    return [
        Cluster(species_id=species, members=members)
        for species, members in sorted(by_species.items())
        if len(members) >= CLUSTER_MIN_SIZE
    ]


PRESSURE_SUBTREE_ALLOWLIST: dict[str, set[str]] = {
    "starvation": {"dormancy", "migration_up"},
    "predation": {"scatter_and_hide", "dormancy"},
    "abundance": {"aggressive_foraging", "migration_up"},
    "none": {"dormancy", "scatter_and_hide", "aggressive_foraging", "migration_up"},
    "isolation": {"migration_up", "dormancy"},
}


def validate_adaptation_schema(response: AdaptationResponse) -> bool:
    from sim.subtrees import SUBTREE_LIBRARY

    return response.subtree_key in SUBTREE_LIBRARY


def validate_adaptation_semantic(
    response: AdaptationResponse,
    cluster: Cluster,
    world: World | None = None,
) -> bool:
    if not validate_adaptation_schema(response):
        return False
    if world is not None:
        authored = world.authored_subtrees.get(response.subtree_key)
        if authored is not None and authored.state == "approved":
            return True
    pressure = cluster.aggregate_pressure().dominant()
    allowed = PRESSURE_SUBTREE_ALLOWLIST.get(pressure, PRESSURE_SUBTREE_ALLOWLIST["none"])
    return response.subtree_key in allowed


def validate_adaptation_full(
    response: AdaptationResponse,
    cluster: Cluster,
    world: World | None = None,
) -> bool:
    return validate_adaptation_semantic(response, cluster, world)


def validate_adaptation_response(
    response: AdaptationResponse,
    cluster: Cluster | None = None,
    world: World | None = None,
) -> bool:
    if cluster is None:
        return validate_adaptation_schema(response)
    return validate_adaptation_full(response, cluster, world)


def mock_adaptation_provider(cluster: Cluster, world: World) -> AdaptationResponse:
    """Deterministic mock slow-path (no live LLM)."""
    pressure = cluster.aggregate_pressure()
    dominant = pressure.dominant()
    if dominant == "starvation":
        return AdaptationResponse(
            subtree_key="dormancy",
            confidence=0.85,
            rationale="mock: conserve energy under famine",
        )
    if dominant == "predation":
        return AdaptationResponse(
            subtree_key="scatter_and_hide",
            confidence=0.80,
            rationale="mock: flee and hide from threat",
        )
    if dominant == "abundance":
        return AdaptationResponse(
            subtree_key="aggressive_foraging",
            confidence=0.75,
            rationale="mock: exploit abundance",
        )
    return AdaptationResponse(
        subtree_key=FALLBACK_SUBTREE_KEY,
        confidence=0.5,
        rationale="mock: fallback",
    )


def emit_adaptation_event(
    world: World,
    event_name: str,
    *,
    message: str,
    signature: str = "",
    species_or_cluster_id: str = "",
    severity: str = "info",
) -> None:
    world.adaptation_events.append(
        {
            "event_name": event_name,
            "tick": world.tick,
            "floor": world.floor_profile.depth_index,
            "species_or_cluster_id": species_or_cluster_id,
            "signature": signature,
            "severity": severity,
            "message": message,
            "correlation_id": f"{world.tick}:{event_name}:{len(world.adaptation_events)}",
        }
    )


def replace_adaptation_slot(
    root: py_trees.behaviour.Behaviour,
    subtree: py_trees.behaviour.Behaviour,
) -> bool:
    if isinstance(root, py_trees.composites.Composite):
        for idx, child in enumerate(root.children):
            if child.name == "AdaptationSlot":
                subtree.name = "AdaptationSlot"
                root.children[idx] = subtree
                subtree.parent = root
                return True
            if replace_adaptation_slot(child, subtree):
                return True
    return False


def inject_subtree_for_cluster(cluster: Cluster, subtree_key: str) -> None:
    from sim.subtrees import build_subtree

    subtree = build_subtree(subtree_key)
    for member in cluster.members:
        member.extensions["adaptation_subtree_key"] = subtree_key
        root = member.extensions.get("bt_root")
        if root is not None:
            replace_adaptation_slot(root, subtree)
            member.extensions["_adaptation_applied_key"] = subtree_key


def record_outcome(entry: CacheEntry, cluster: Cluster, tick: int) -> None:
    if entry.sample_count == 0:
        entry.stress_before = cluster.mean_stress
        entry.sample_count = 1
        entry.last_seen_tick = tick
        return
    stress_delta = entry.stress_before - cluster.mean_stress
    entry.stress_reduction = max(0.0, 0.7 * entry.stress_reduction + 0.3 * stress_delta)
    if cluster.members:
        survived = sum(1 for m in cluster.members if m.alive) / len(cluster.members)
    else:
        survived = 1.0
    entry.survival_impact = max(0.0, 0.7 * entry.survival_impact + 0.3 * survived)
    success = 1.0 if stress_delta > 0.01 or cluster.mean_stress < CLUSTER_STRESS_THRESHOLD else 0.0
    entry.success_rate = (
        (entry.success_rate * (entry.sample_count - 1) + success) / entry.sample_count
    )
    entry.sample_count += 1
    entry.last_seen_tick = tick
    entry.stress_before = cluster.mean_stress
    if success < 0.5:
        entry.consecutive_failures += 1
    else:
        entry.consecutive_failures = 0


def _maybe_promote(entry: CacheEntry) -> None:
    if entry.state != "candidate":
        return
    if entry.sample_count < CACHE_PROMOTE_MIN_SAMPLES:
        return
    if entry.success_rate < CACHE_PROMOTE_MIN_SUCCESS_RATE:
        return
    if entry.stress_reduction < CACHE_PROMOTE_MIN_STRESS_REDUCTION:
        return
    entry.state = "promoted"


def _maybe_demote(entry: CacheEntry) -> None:
    if entry.state != "promoted":
        return
    if entry.sample_count < CACHE_PROMOTE_MIN_SAMPLES:
        return
    if entry.success_rate >= CACHE_DEMOTE_SUCCESS_RATE:
        return
    entry.state = "demoted"


def _maybe_invalidate(entry: CacheEntry) -> None:
    if entry.consecutive_failures >= CACHE_INVALIDATE_FAILURES:
        entry.state = "invalidated"


def ingest_adaptation(
    world: World,
    cluster: Cluster,
    signature: str,
    response: AdaptationResponse,
    *,
    from_cache: bool = False,
) -> bool:
    if not validate_adaptation_full(response, cluster, world):
        emit_adaptation_event(
            world,
            "adaptation.rejected",
            message=f"invalid subtree {response.subtree_key!r}",
            signature=signature,
            species_or_cluster_id=cluster.species_id,
            severity="warning",
        )
        inject_subtree_for_cluster(cluster, FALLBACK_SUBTREE_KEY)
        return False

    entry = world.adaptation_cache.get(signature)
    if entry is None:
        entry = CacheEntry(signature=signature, subtree_key=response.subtree_key)
        world.adaptation_cache[signature] = entry
        emit_adaptation_event(
            world,
            "adaptation.cache.insert",
            message=f"insert {response.subtree_key}",
            signature=signature,
            species_or_cluster_id=cluster.species_id,
        )
    elif entry.state == "invalidated" or entry.state == "demoted":
        entry.subtree_key = response.subtree_key
        entry.state = "candidate"
        entry.sample_count = 0
        entry.consecutive_failures = 0
        emit_adaptation_event(
            world,
            "adaptation.cache.reinsert",
            message=f"reinsert {response.subtree_key}",
            signature=signature,
            species_or_cluster_id=cluster.species_id,
        )
    elif from_cache:
        emit_adaptation_event(
            world,
            "adaptation.cache.hit",
            message=f"hit {entry.subtree_key}",
            signature=signature,
            species_or_cluster_id=cluster.species_id,
        )

    inject_subtree_for_cluster(cluster, response.subtree_key)
    record_outcome(entry, cluster, world.tick)
    _maybe_promote(entry)
    _maybe_demote(entry)
    _maybe_invalidate(entry)
    if entry.state == "promoted":
        emit_adaptation_event(
            world,
            "adaptation.cache.promote",
            message=f"promoted {entry.subtree_key}",
            signature=signature,
            species_or_cluster_id=cluster.species_id,
        )
    elif entry.state == "demoted":
        emit_adaptation_event(
            world,
            "adaptation.cache.demote",
            message=f"demoted {entry.subtree_key}",
            signature=signature,
            species_or_cluster_id=cluster.species_id,
        )
    elif entry.state == "invalidated":
        emit_adaptation_event(
            world,
            "adaptation.cache.invalidate",
            message=f"invalidated {entry.subtree_key}",
            signature=signature,
            species_or_cluster_id=cluster.species_id,
        )
    return True


def process_cluster_adaptation(world: World, cluster: Cluster) -> None:
    if cluster.mean_stress < CLUSTER_STRESS_THRESHOLD:
        return
    signature = cluster_signature(cluster, world)
    entry = world.adaptation_cache.get(signature)

    if entry is not None and entry.state == "promoted":
        response = AdaptationResponse(subtree_key=entry.subtree_key, confidence=1.0)
        ingest_adaptation(world, cluster, signature, response, from_cache=True)
        return

    if entry is not None and entry.state == "candidate":
        ingest_adaptation(
            world,
            cluster,
            signature,
            AdaptationResponse(subtree_key=entry.subtree_key),
            from_cache=True,
        )
        return

    if world.llm_enabled:
        from sim.llm_adapter import enqueue_llm_request, get_circuit

        if signature in world.pending_llm:
            inject_subtree_for_cluster(cluster, FALLBACK_SUBTREE_KEY)
            return

        circuit = get_circuit(world, signature)
        if circuit.is_open(world.tick):
            inject_subtree_for_cluster(cluster, FALLBACK_SUBTREE_KEY)
            emit_adaptation_event(
                world,
                "adaptation.fallback",
                message="circuit open; using dormancy",
                signature=signature,
                species_or_cluster_id=cluster.species_id,
            )
            return

        enqueue_llm_request(world, cluster, signature)
        inject_subtree_for_cluster(cluster, FALLBACK_SUBTREE_KEY)
        emit_adaptation_event(
            world,
            "adaptation.fallback",
            message="llm in flight; using dormancy",
            signature=signature,
            species_or_cluster_id=cluster.species_id,
        )
        return

    if entry is not None and entry.state in ("demoted", "invalidated"):
        response = mock_adaptation_provider(cluster, world)
        ingest_adaptation(world, cluster, signature, response)
        return

    response = mock_adaptation_provider(cluster, world)
    ingest_adaptation(world, cluster, signature, response)


def step_population_adaptation(world: World, dt: float) -> None:
    if world.llm_enabled:
        from sim.llm_adapter import poll_llm_completions

        poll_llm_completions(world)
    if world.tick % POPULATION_SCAN_INTERVAL != 0:
        return
    for cluster in detect_clusters(world):
        process_cluster_adaptation(world, cluster)
