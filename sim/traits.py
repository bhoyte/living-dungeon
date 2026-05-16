"""Trait codex (v1 starter)."""

from __future__ import annotations

TRAIT_CODEX: dict[str, dict[str, object]] = {
    "photosynthesis": {
        "cost": 1,
        "grants": "passive_energy_in_light",
        "prereq": None,
    },
    "carnivore": {
        "cost": 1,
        "grants": "energy_from_corpses",
        "prereq": None,
    },
    "acidic_touch": {
        "cost": 1,
        "grants": "damage_on_contact",
        "prereq": None,
    },
    "sweet_scent": {
        "cost": 1,
        "grants": "emit_lure_pheromone",
        "prereq": None,
    },
    "camouflage": {
        "cost": 2,
        "grants": "perception_penalty_to_observers",
        "prereq": None,
    },
    "echolocation": {
        "cost": 2,
        "grants": "tremorsense_range_+150",
        "prereq": None,
    },
}
