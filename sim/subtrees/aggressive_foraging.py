"""Aggressive foraging subtree: prioritize food when hungry."""

from __future__ import annotations

import py_trees

from sim.behavior import (
    CheckInternalBehaviour,
    InteractBehaviour,
    LocomoteBehaviour,
    QuerySenseBehaviour,
)


def build_aggressive_foraging_tree() -> py_trees.composites.Sequence:
    return py_trees.composites.Sequence(
        name="aggressive_foraging",
        memory=False,
        children=[
            CheckInternalBehaviour("energy", "<", 0.70),
            QuerySenseBehaviour("smell", "food", merge=True),
            LocomoteBehaviour("food"),
            InteractBehaviour("food"),
        ],
    )
