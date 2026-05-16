"""Organism data models, species registry, and runtime instances."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from sim.constants import (
    DEFAULT_CREATURE_ENERGY,
    DEFAULT_PRODUCER_ENERGY,
    ENERGY_MAX,
    ENERGY_MIN,
)

Sense = Literal["sight", "smell", "tremorsense", "thermal"]
StaticAction = Literal["rest", "hold"]


class Genome(BaseModel):
    size: float = 1.0
    speed: float = 50.0
    metabolism: float = 1.0
    perception_range: float = 100.0
    aggression: float = 0.5
    pigmentation: tuple[float, float, float] = (0.4, 0.7, 0.4)


class Epigenome(BaseModel):
    size_mult: float = 1.0
    speed_mult: float = 1.0
    metabolism_mult: float = 1.0
    perception_mult: float = 1.0
    aggression_mult: float = 1.0


class SenseChannel(BaseModel):
    range: float = 0.0
    acuity: float = 0.0


class OrganismData(BaseModel):
    species_id: str
    trophic_level: int = Field(ge=0, le=3)
    base_genome: Genome
    epigenome: Epigenome = Field(default_factory=Epigenome)
    traits: list[str] = Field(default_factory=list)
    senses: dict[Sense, SenseChannel] = Field(default_factory=dict)

    def stat(self, name: str) -> float:
        base = getattr(self.base_genome, name)
        mult = getattr(self.epigenome, f"{name}_mult", 1.0)
        return float(base) * float(mult)


@dataclass
class Organism:
    id: int
    data: OrganismData
    pos: tuple[int, int]
    energy: float = DEFAULT_CREATURE_ENERGY
    stress: float = 0.0
    age_ticks: int = 0
    alive: bool = True
    static_action: StaticAction = "rest"
    extensions: dict[str, object] = field(default_factory=dict)

    def clamp_energy(self) -> None:
        self.energy = max(ENERGY_MIN, min(ENERGY_MAX, self.energy))


SPECIES: dict[str, OrganismData] = {
    "slime": OrganismData(
        species_id="slime",
        trophic_level=2,
        base_genome=Genome(
            size=1.0,
            speed=40.0,
            metabolism=1.0,
            perception_range=80.0,
            aggression=0.4,
            pigmentation=(0.35, 0.65, 0.35),
        ),
        senses={
            "sight": SenseChannel(range=80.0, acuity=0.7),
            "smell": SenseChannel(range=50.0, acuity=0.6),
        },
        traits=["acidic_touch"],
    ),
    "mana_moss": OrganismData(
        species_id="mana_moss",
        trophic_level=0,
        base_genome=Genome(
            size=0.6,
            speed=0.0,
            metabolism=0.5,
            perception_range=0.0,
            aggression=0.0,
            pigmentation=(0.2, 0.55, 0.3),
        ),
        traits=["photosynthesis", "sweet_scent"],
        senses={},
    ),
    "scout_slime": OrganismData(
        species_id="scout_slime",
        trophic_level=2,
        base_genome=Genome(
            size=0.8,
            speed=90.0,
            metabolism=1.4,
            perception_range=120.0,
            aggression=0.25,
            pigmentation=(0.5, 0.75, 0.9),
        ),
        senses={
            "sight": SenseChannel(range=120.0, acuity=0.85),
            "smell": SenseChannel(range=30.0, acuity=0.4),
        },
        traits=[],
    ),
}


def species_data(species_id: str) -> OrganismData:
    try:
        return SPECIES[species_id]
    except KeyError as exc:
        raise KeyError(f"Unknown species_id: {species_id!r}") from exc


def attach_behavior_tree(org: Organism) -> None:
    if org.data.species_id in ("slime", "scout_slime"):
        from sim.trees.slime_forager import build_slime_forager_tree

        org.extensions["bt_root"] = build_slime_forager_tree()
    elif org.data.species_id == "mana_moss":
        from sim.trees.moss_sessile import build_moss_sessile_tree

        org.extensions["bt_root"] = build_moss_sessile_tree()


def initial_energy_for_species(species_id: str) -> float:
    if species_id == "mana_moss":
        return DEFAULT_PRODUCER_ENERGY
    return DEFAULT_CREATURE_ENERGY
