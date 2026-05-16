from __future__ import annotations

from sim.adaptation import (
    cluster_signature,
    detect_clusters,
    inject_subtree_for_cluster,
)
from sim.authored_subtree import (
    AuthoredSubtreeSpec,
    TreeNodeSpec,
    approve_authored_subtree,
    ingest_authored_subtree,
    rollback_authored_subtree,
    sanitize_authored_spec,
    validate_authored_semantic,
)
from sim.constants import CLUSTER_STRESS_THRESHOLD
from sim.epigenome import AdaptationMarkers
from sim.floor_profile import FloorProfile
from sim.generation import generate_floor
from sim.subtrees import SUBTREE_LIBRARY, build_subtree
from sim.tick import tick


def _famine_forage_spec() -> AuthoredSubtreeSpec:
    return AuthoredSubtreeSpec(
        name="famine_forage_cycle",
        description="seek food when energy is low",
        tree=TreeNodeSpec(
            type="Sequence",
            children=[
                TreeNodeSpec(type="CheckInternal", args=["energy", "<", 0.55]),
                TreeNodeSpec(type="QuerySense", args=["smell", "food"]),
                TreeNodeSpec(type="Locomote", args=["food"]),
                TreeNodeSpec(type="Interact", args=["food"]),
            ],
        ),
    )


def _stressed_world(*, seed: int = 55) -> object:
    profile = FloorProfile(
        name="Authored",
        width=28,
        height=20,
        seed=seed,
        features=[],
        seed_producers=["mana_moss"],
        initial_creatures={"slime": 4},
    )
    world = generate_floor(profile)
    for org in world.organisms:
        if org.data.species_id == "slime":
            org.energy = 0.28
            org.stress = CLUSTER_STRESS_THRESHOLD + 0.06
            org.extensions["markers"] = AdaptationMarkers(starvation=0.93, predation=0.05)
    return world


def test_valid_authored_subtree_adopted_headless() -> None:
    world = _stressed_world()
    world.authored_auto_approve = True
    cluster = detect_clusters(world)[0]
    sig = cluster_signature(cluster, world)
    spec = _famine_forage_spec()
    assert validate_authored_semantic(spec, cluster) == []

    assert ingest_authored_subtree(world, cluster, sig, spec)
    assert spec.name in world.authored_subtrees
    assert spec.name in SUBTREE_LIBRARY
    tree = build_subtree(spec.name)
    assert tree.name == spec.name

    for _ in range(100):
        tick(world, 1.0)

    assert any(o.alive for o in world.organisms if o.data.species_id == "slime")
    assert any(e["event_name"] == "authored.approved" for e in world.adaptation_events)


def test_invalid_authored_rejected_keeps_sim_stable() -> None:
    world = _stressed_world(seed=56)
    cluster = detect_clusters(world)[0]
    sig = cluster_signature(cluster, world)
    bad = AuthoredSubtreeSpec(
        name="illegal_fly",
        tree=TreeNodeSpec(type="Fly", args=[]),
    )
    assert ingest_authored_subtree(world, cluster, sig, bad) is False
    assert any(e["event_name"] == "authored.rejected" for e in world.adaptation_events)
    assert "illegal_fly" not in world.authored_subtrees

    for _ in range(100):
        tick(world, 1.0)
    assert world.tick == 100


def test_rollback_unregisters_authored_subtree() -> None:
    world = _stressed_world(seed=57)
    cluster = detect_clusters(world)[0]
    sig = cluster_signature(cluster, world)
    spec = _famine_forage_spec()
    approve_authored_subtree(world, spec, sig)
    inject_subtree_for_cluster(cluster, spec.name)
    assert spec.name in SUBTREE_LIBRARY

    assert rollback_authored_subtree(world, spec.name)
    assert spec.name not in SUBTREE_LIBRARY
    assert world.authored_subtrees[spec.name].state == "rolled_back"
    assert any(e["event_name"] == "authored.rolled_back" for e in world.adaptation_events)


def test_sanitize_strips_composite_args() -> None:
    raw = AuthoredSubtreeSpec(
        name="bad_selector",
        tree=TreeNodeSpec(
            type="Selector",
            args=["oops"],
            children=[TreeNodeSpec(type="Rest")],
        ),
    )
    clean = sanitize_authored_spec(raw)
    assert clean.tree.args == []
    assert validate_authored_semantic(clean, detect_clusters(_stressed_world())[0]) == []


def test_pending_authored_uses_fallback_until_approved() -> None:
    world = _stressed_world(seed=58)
    world.authored_auto_approve = False
    cluster = detect_clusters(world)[0]
    sig = cluster_signature(cluster, world)
    spec = _famine_forage_spec()

    assert ingest_authored_subtree(world, cluster, sig, spec) is False
    assert sig in world.authored_pending
    assert any(e["event_name"] == "authored.pending" for e in world.adaptation_events)
    for member in cluster.members:
        assert member.extensions.get("adaptation_subtree_key") == "dormancy"
