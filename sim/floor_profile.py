from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class GeologicalFeature(BaseModel):
    type: Literal[
        "crystal_node",
        "water_channel",
        "bone_deposit",
        "mycelium_patch",
        "acid_pool",
        "sand_basin",
    ]
    region: Literal["NE", "NW", "SE", "SW", "C", "edge", "any"] = "any"
    size: Literal["small", "medium", "large"] = "medium"
    count: int = Field(default=1, ge=1)


class FloorProfile(BaseModel):
    name: str
    depth_index: int = Field(default=0, ge=0)
    width: int = Field(default=60, ge=8)
    height: int = Field(default=40, ge=8)
    seed: int = 0

    base_temperature: float = 12.0
    base_humidity: float = Field(default=0.45, ge=0.0, le=1.0)
    base_mana_aether: float = Field(default=0.10, ge=0.0, le=1.0)

    base_composition: Literal["stone", "limestone", "bone"] = "limestone"
    bsp_max_room_size: int = Field(default=12, ge=3)
    bsp_min_room_size: int = Field(default=5, ge=3)
    pocket_noise: Literal["simplex", "worley"] = "simplex"

    features: list[GeologicalFeature] = Field(default_factory=list)
    seed_producers: list[str] = Field(default_factory=lambda: ["mana_moss"])
    initial_creatures: dict[str, int] = Field(default_factory=dict)

    mission_graph: dict | None = None
    dm_influence_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    dm_bias: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_generation_parameters(self) -> "FloorProfile":
        if self.bsp_min_room_size > self.bsp_max_room_size:
            raise ValueError("bsp_min_room_size cannot exceed bsp_max_room_size.")
        if self.bsp_max_room_size > min(self.width, self.height):
            raise ValueError("bsp_max_room_size must fit within map dimensions.")
        return self
