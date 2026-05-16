from __future__ import annotations

import json

import pytest

from sim.adaptation import Cluster, detect_clusters
from sim.authored_subtree import LlmAdaptationResult
from sim.epigenome import AdaptationMarkers
from sim.floor_profile import FloorProfile
from sim.generation import generate_floor
from sim.llm_prompts import (
    build_author_subtree_prompt,
    build_pick_existing_prompt,
    parse_llm_json_payload,
)


def _cluster() -> Cluster:
    profile = FloorProfile(
        name="Prompt",
        width=20,
        height=16,
        seed=1,
        features=[],
        initial_creatures={"slime": 3},
    )
    world = generate_floor(profile)
    for org in world.organisms:
        org.extensions["markers"] = AdaptationMarkers(starvation=0.9)
    return detect_clusters(world)[0]


def test_build_pick_existing_prompt_lists_library_keys() -> None:
    prompt = build_pick_existing_prompt(_cluster())
    assert "dormancy" in prompt
    assert "use_existing" in prompt


def test_build_author_subtree_prompt_includes_manifest() -> None:
    prompt = build_author_subtree_prompt(_cluster())
    assert "Sequence" in prompt
    assert "CheckInternal" in prompt
    assert "use_existing" in prompt
    assert "famine_forage_cycle" in prompt


def test_parse_llm_json_payload_authored_shape() -> None:
    raw = json.dumps(
        {
            "use_existing": False,
            "authored": {
                "name": "test_cycle",
                "description": "x",
                "tree": {"type": "Rest", "args": [], "children": []},
            },
            "confidence": 0.5,
            "rationale": "test",
        }
    )
    result = LlmAdaptationResult.model_validate(parse_llm_json_payload(raw))
    assert result.use_existing is False
    assert result.authored is not None
    assert result.authored.name == "test_cycle"


def test_parse_llm_json_payload_rejects_non_object() -> None:
    with pytest.raises(TypeError):
        parse_llm_json_payload("[1,2,3]")
