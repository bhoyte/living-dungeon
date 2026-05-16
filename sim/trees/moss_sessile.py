"""Sessile producer tree: Rest only (mana moss)."""

from __future__ import annotations

import py_trees

from sim.behavior import RestBehaviour


def build_moss_sessile_tree() -> py_trees.composites.Sequence:
    return py_trees.composites.Sequence(
        name="moss_root",
        memory=False,
        children=[RestBehaviour(name="Rest")],
    )
