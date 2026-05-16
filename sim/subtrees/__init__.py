"""Hardcoded v1 subtree library (LLM picks from these keys)."""

from __future__ import annotations

import py_trees

from sim.subtrees.aggressive_foraging import build_aggressive_foraging_tree
from sim.subtrees.dormancy import build_dormancy_tree
from sim.subtrees.migration_up import build_migration_up_tree
from sim.subtrees.scatter_and_hide import build_scatter_and_hide_tree

SUBTREE_LIBRARY: dict[str, str] = {
    "aggressive_foraging": "rush remaining food, ignore mild threats",
    "scatter_and_hide": "split, seek camouflage tile, Hide",
    "dormancy": "Rest in safe tile, drop metabolism",
    "migration_up": "Locomote toward staircase, then ascend",
}

_BUILDERS: dict[str, object] = {
    "aggressive_foraging": build_aggressive_foraging_tree,
    "scatter_and_hide": build_scatter_and_hide_tree,
    "dormancy": build_dormancy_tree,
    "migration_up": build_migration_up_tree,
}

_DYNAMIC_BUILDERS: dict[str, object] = {}


def register_dynamic_subtree(
    name: str,
    builder: object,
    *,
    description: str,
) -> None:
    _DYNAMIC_BUILDERS[name] = builder
    SUBTREE_LIBRARY[name] = description


def unregister_dynamic_subtree(name: str) -> None:
    _DYNAMIC_BUILDERS.pop(name, None)
    SUBTREE_LIBRARY.pop(name, None)


def build_subtree(key: str) -> py_trees.behaviour.Behaviour:
    if key in _DYNAMIC_BUILDERS:
        return _DYNAMIC_BUILDERS[key]()  # type: ignore[operator]
    if key not in _BUILDERS:
        raise KeyError(f"Unknown subtree key: {key!r}")
    builder = _BUILDERS[key]
    return builder()  # type: ignore[operator]
