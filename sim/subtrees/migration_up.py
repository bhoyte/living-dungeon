"""Migration placeholder: wander until stair logic exists."""

from __future__ import annotations

import py_trees

from sim.behavior import LocomoteBehaviour


def build_migration_up_tree() -> py_trees.composites.Sequence:
    return py_trees.composites.Sequence(
        name="migration_up",
        memory=False,
        children=[LocomoteBehaviour("wander")],
    )
