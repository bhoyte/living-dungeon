"""LLM-authored subtree validation, approval gate, registry, and rollback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import py_trees
from pydantic import BaseModel, Field, model_validator

from sim.behavior import (
    LOCOMOTE_TARGETS,
    CheckCooldownBehaviour,
    CheckEnvBehaviour,
    CheckInternalBehaviour,
    HideBehaviour,
    InteractBehaviour,
    LocomoteBehaviour,
    QuerySenseBehaviour,
    RestBehaviour,
)
from sim.constants import FALLBACK_SUBTREE_KEY
from sim.verbs import CONDITIONS, VERBS

if TYPE_CHECKING:
    from sim.adaptation import Cluster
    from sim.world import World

COMPOSITE_TYPES = frozenset({"Sequence", "Selector"})
LEAF_VERBS = frozenset(VERBS.keys())
LEAF_CONDITIONS = frozenset(CONDITIONS.keys())
ALLOWED_NODE_TYPES = COMPOSITE_TYPES | LEAF_VERBS | LEAF_CONDITIONS

MAX_AUTHORED_DEPTH = 6
MAX_AUTHORED_NODES = 14
AUTHORED_ROLLOUT_TICKS = 120


class TreeNodeSpec(BaseModel):
    type: str
    args: list[Any] = Field(default_factory=list)
    children: list[TreeNodeSpec] = Field(default_factory=list)


class AuthoredSubtreeSpec(BaseModel):
    name: str = Field(min_length=1, max_length=48)
    tree: TreeNodeSpec
    description: str = ""


class LlmAdaptationResult(BaseModel):
    """Pick-existing or author-new result from slow path."""

    use_existing: bool = True
    subtree_key: str | None = None
    authored: AuthoredSubtreeSpec | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""

    @model_validator(mode="after")
    def _exclusive_payload(self) -> LlmAdaptationResult:
        if self.use_existing:
            if not self.subtree_key:
                raise ValueError("subtree_key required when use_existing is true")
            if self.authored is not None:
                raise ValueError("authored must be null when use_existing is true")
        elif self.authored is None:
            raise ValueError("authored required when use_existing is false")
        return self


@dataclass
class AuthoredSubtreeRecord:
    spec: AuthoredSubtreeSpec
    signature: str
    approved_tick: int
    state: Literal["approved", "rolled_back"] = "approved"
    rollout_until_tick: int = 0


@dataclass
class PendingAuthoredRecord:
    spec: AuthoredSubtreeSpec
    signature: str
    requested_tick: int


def normalize_llm_result(result: LlmAdaptationResult | Any) -> LlmAdaptationResult:
    if isinstance(result, LlmAdaptationResult):
        return result
    from sim.adaptation import AdaptationResponse

    if isinstance(result, AdaptationResponse):
        return LlmAdaptationResult(
            use_existing=True,
            subtree_key=result.subtree_key,
            confidence=result.confidence,
            rationale=result.rationale,
        )
    raise TypeError(f"Unsupported LLM result type: {type(result)!r}")


def _count_nodes(node: TreeNodeSpec, depth: int = 1) -> tuple[int, int]:
    total = 1
    max_depth = depth
    for child in node.children:
        child_count, child_depth = _count_nodes(child, depth + 1)
        total += child_count
        max_depth = max(max_depth, child_depth)
    return total, max_depth


def sanitize_tree_node(node: TreeNodeSpec) -> TreeNodeSpec:
    """Normalize common LLM slop before manifest validation."""
    if node.type in COMPOSITE_TYPES:
        return TreeNodeSpec(
            type=node.type,
            args=[],
            children=[sanitize_tree_node(c) for c in node.children],
        )
    return TreeNodeSpec(type=node.type, args=list(node.args), children=[])


def sanitize_authored_spec(spec: AuthoredSubtreeSpec) -> AuthoredSubtreeSpec:
    return AuthoredSubtreeSpec(
        name=spec.name.strip(),
        description=spec.description,
        tree=sanitize_tree_node(spec.tree),
    )


def validate_manifest(node: TreeNodeSpec) -> list[str]:
    errors: list[str] = []
    if node.type not in ALLOWED_NODE_TYPES:
        errors.append(f"unknown node type {node.type!r}")
        return errors

    if node.type in COMPOSITE_TYPES:
        if node.args:
            errors.append(f"{node.type} must not have args")
        if not node.children:
            errors.append(f"{node.type} requires children")
        for child in node.children:
            errors.extend(validate_manifest(child))
        return errors

    if node.type in LEAF_VERBS:
        if node.children:
            errors.append(f"verb {node.type} must not have children")
        if node.type == "Locomote":
            if len(node.args) != 1 or str(node.args[0]) not in LOCOMOTE_TARGETS:
                errors.append(f"Locomote target must be one of {sorted(LOCOMOTE_TARGETS)}")
        elif node.type == "Interact":
            if len(node.args) != 1:
                errors.append("Interact requires one target arg")
        elif node.type == "Emit":
            if len(node.args) != 1 or str(node.args[0]) not in ("scent", "spore", "alarm"):
                errors.append("Emit substance must be scent, spore, or alarm")
        elif node.type == "Construct":
            if len(node.args) != 1:
                errors.append("Construct requires one object arg")
        return errors

    if node.type in LEAF_CONDITIONS:
        if node.children:
            errors.append(f"condition {node.type} must not have children")
        if node.type == "CheckInternal" and len(node.args) != 3:
            errors.append("CheckInternal requires stat, op, threshold")
        elif node.type == "CheckEnv" and len(node.args) != 3:
            errors.append("CheckEnv requires path, op, value")
        elif node.type == "QuerySense" and len(node.args) != 2:
            errors.append("QuerySense requires sense_type, target_type")
        elif node.type == "CheckCooldown" and len(node.args) != 1:
            errors.append("CheckCooldown requires key")
        return errors

    return errors


def validate_authored_semantic(spec: AuthoredSubtreeSpec, cluster: Cluster) -> list[str]:
    errors = validate_manifest(spec.tree)
    if errors:
        return errors
    total, depth = _count_nodes(spec.tree)
    if depth > MAX_AUTHORED_DEPTH:
        errors.append(f"tree depth {depth} exceeds max {MAX_AUTHORED_DEPTH}")
    if total > MAX_AUTHORED_NODES:
        errors.append(f"tree node count {total} exceeds max {MAX_AUTHORED_NODES}")
    if not spec.name.replace("_", "").isalnum():
        errors.append("subtree name must be alphanumeric with underscores")
    pressure = cluster.aggregate_pressure().dominant()
    if pressure == "starvation" and spec.name.startswith("predator_"):
        errors.append("name incompatible with starvation pressure")
    return errors


def build_behaviour(node: TreeNodeSpec) -> py_trees.behaviour.Behaviour:
    if node.type == "Sequence":
        return py_trees.composites.Sequence(
            name="Sequence",
            memory=False,
            children=[build_behaviour(c) for c in node.children],
        )
    if node.type == "Selector":
        return py_trees.composites.Selector(
            name="Selector",
            memory=False,
            children=[build_behaviour(c) for c in node.children],
        )
    if node.type == "CheckInternal":
        stat, op, threshold = node.args
        return CheckInternalBehaviour(str(stat), str(op), float(threshold))
    if node.type == "CheckEnv":
        path, op, value = node.args
        return CheckEnvBehaviour(str(path), str(op), value)
    if node.type == "CheckCooldown":
        return CheckCooldownBehaviour(str(node.args[0]))
    if node.type == "QuerySense":
        sense_type, target_type = node.args
        merge = str(target_type) == "food"
        return QuerySenseBehaviour(str(sense_type), str(target_type), merge=merge)
    if node.type == "Locomote":
        return LocomoteBehaviour(str(node.args[0]))
    if node.type == "Interact":
        return InteractBehaviour(str(node.args[0]))
    if node.type == "Rest":
        return RestBehaviour(name="Rest")
    if node.type == "Hide":
        return HideBehaviour(name="Hide")
    raise ValueError(f"cannot build node type {node.type!r}")


def build_authored_tree(spec: AuthoredSubtreeSpec) -> py_trees.behaviour.Behaviour:
    root = build_behaviour(spec.tree)
    root.name = spec.name
    return root


def register_authored_builder(spec: AuthoredSubtreeSpec) -> None:
    from sim.subtrees import register_dynamic_subtree

    def _builder() -> py_trees.behaviour.Behaviour:
        return build_authored_tree(spec)

    register_dynamic_subtree(
        spec.name,
        _builder,
        description=spec.description or f"authored:{spec.name}",
    )


def emit_authored_event(
    world: World,
    event_name: str,
    *,
    message: str,
    signature: str = "",
    species_id: str = "",
    severity: str = "info",
) -> None:
    world.adaptation_events.append(
        {
            "event_name": event_name,
            "tick": world.tick,
            "floor": world.floor_profile.depth_index,
            "species_or_cluster_id": species_id,
            "signature": signature,
            "severity": severity,
            "message": message,
            "correlation_id": f"{world.tick}:{event_name}:{len(world.adaptation_events)}",
        }
    )


def approve_authored_subtree(
    world: World,
    spec: AuthoredSubtreeSpec,
    signature: str,
) -> bool:
    register_authored_builder(spec)
    world.authored_subtrees[spec.name] = AuthoredSubtreeRecord(
        spec=spec,
        signature=signature,
        approved_tick=world.tick,
        rollout_until_tick=world.tick + AUTHORED_ROLLOUT_TICKS,
    )
    world.authored_pending.pop(signature, None)
    emit_authored_event(
        world,
        "authored.approved",
        message=f"approved {spec.name}",
        signature=signature,
        species_id="",
    )
    return True


def rollback_authored_subtree(world: World, name: str) -> bool:
    from sim.subtrees import unregister_dynamic_subtree

    record = world.authored_subtrees.get(name)
    if record is None or record.state == "rolled_back":
        return False
    unregister_dynamic_subtree(name)
    record.state = "rolled_back"
    emit_authored_event(
        world,
        "authored.rolled_back",
        message=f"rolled back {name}",
        signature=record.signature,
    )
    return True


def ingest_authored_subtree(
    world: World,
    cluster: Cluster,
    signature: str,
    spec: AuthoredSubtreeSpec,
) -> bool:
    spec = sanitize_authored_spec(spec)
    errors = validate_authored_semantic(spec, cluster)
    if errors:
        emit_authored_event(
            world,
            "authored.rejected",
            message="; ".join(errors),
            signature=signature,
            species_id=cluster.species_id,
            severity="warning",
        )
        return False

    if world.authored_auto_approve:
        approve_authored_subtree(world, spec, signature)
        from sim.adaptation import AdaptationResponse, ingest_adaptation

        ingest_adaptation(
            world,
            cluster,
            signature,
            AdaptationResponse(subtree_key=spec.name, confidence=1.0, rationale="authored auto-approved"),
        )
        return True

    world.authored_pending[signature] = PendingAuthoredRecord(
        spec=spec,
        signature=signature,
        requested_tick=world.tick,
    )
    emit_authored_event(
        world,
        "authored.pending",
        message=f"awaiting approval: {spec.name}",
        signature=signature,
        species_id=cluster.species_id,
    )
    from sim.adaptation import inject_subtree_for_cluster

    inject_subtree_for_cluster(cluster, FALLBACK_SUBTREE_KEY)
    return False


def check_authored_rollbacks(world: World) -> None:
    for name, record in list(world.authored_subtrees.items()):
        if record.state != "approved":
            continue
        if world.tick >= record.rollout_until_tick:
            rollback_authored_subtree(world, name)
