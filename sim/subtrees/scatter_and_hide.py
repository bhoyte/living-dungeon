"""Scatter and hide subtree: flee under stress."""

from __future__ import annotations

import py_trees

from sim.behavior import CheckInternalBehaviour, HideBehaviour, LocomoteBehaviour


def build_scatter_and_hide_tree() -> py_trees.composites.Sequence:
    return py_trees.composites.Sequence(
        name="scatter_and_hide",
        memory=False,
        children=[
            CheckInternalBehaviour("stress", ">", 0.50),
            LocomoteBehaviour("safety"),
            HideBehaviour(name="Hide"),
        ],
    )
