"""Dormancy subtree: rest when energy is low."""

from __future__ import annotations

import py_trees

from sim.behavior import CheckInternalBehaviour, RestBehaviour


def build_dormancy_tree() -> py_trees.composites.Sequence:
    return py_trees.composites.Sequence(
        name="dormancy",
        memory=False,
        children=[
            CheckInternalBehaviour("energy", "<", 0.65),
            RestBehaviour(name="Rest"),
        ],
    )
