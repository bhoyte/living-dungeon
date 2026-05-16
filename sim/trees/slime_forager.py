"""cave_slime / slime base forager tree (Sprint 2 target)."""

from __future__ import annotations

import py_trees

from sim.behavior import (
    CheckEnvBehaviour,
    CheckInternalBehaviour,
    InteractBehaviour,
    LocomoteBehaviour,
    QuerySenseBehaviour,
)


def build_slime_forager_tree() -> py_trees.composites.Selector:
    """BT-1 cave_slime: flee → forage → adaptation slot → wander."""
    return py_trees.composites.Selector(
        name="slime_root",
        memory=False,
        children=[
            py_trees.composites.Sequence(
                name="stress_response",
                memory=False,
                children=[
                    CheckInternalBehaviour("stress", ">", 0.65),
                    LocomoteBehaviour("safety"),
                ],
            ),
            py_trees.composites.Sequence(
                name="hunger_forage",
                memory=False,
                children=[
                    CheckInternalBehaviour("energy", "<", 0.5),
                    py_trees.composites.Selector(
                        name="find_food",
                        memory=False,
                        children=[
                            py_trees.composites.Sequence(
                                name="entity_food",
                                memory=False,
                                children=[
                                    QuerySenseBehaviour("smell", "food", merge=True),
                                    LocomoteBehaviour("food"),
                                ],
                            ),
                            py_trees.composites.Sequence(
                                name="field_food",
                                memory=False,
                                children=[
                                    CheckEnvBehaviour("fields.sweet", ">", 0.1),
                                    LocomoteBehaviour("up_gradient"),
                                ],
                            ),
                        ],
                    ),
                    InteractBehaviour("food"),
                ],
            ),
            py_trees.behaviours.Failure(name="AdaptationSlot"),
            LocomoteBehaviour("wander"),
        ],
    )
