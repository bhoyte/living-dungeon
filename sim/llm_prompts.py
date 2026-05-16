"""Prompt builders for live Ollama slow-path calls."""

from __future__ import annotations

import json

from sim.adaptation import Cluster
from sim.authored_subtree import MAX_AUTHORED_DEPTH, MAX_AUTHORED_NODES
from sim.behavior import LOCOMOTE_TARGETS
from sim.subtrees import SUBTREE_LIBRARY
from sim.verbs import CONDITIONS, VERBS


def build_pick_existing_prompt(cluster: Cluster) -> str:
    keys = ", ".join(sorted(SUBTREE_LIBRARY))
    pressure = cluster.aggregate_pressure().dominant()
    return (
        f"Pick one subtree key for species {cluster.species_id} under {pressure} pressure.\n"
        f"Reply JSON only: {{\"use_existing\": true, \"subtree_key\": \"<key>\", "
        f"\"confidence\": 0.0, \"rationale\": \"...\"}}\n"
        f"Allowed keys: {keys}"
    )


def build_author_subtree_prompt(cluster: Cluster) -> str:
    pressure = cluster.aggregate_pressure().dominant()
    verbs = ", ".join(sorted(VERBS))
    conditions = ", ".join(sorted(CONDITIONS))
    composites = "Sequence, Selector"
    locomote = ", ".join(sorted(LOCOMOTE_TARGETS))
    example = {
        "use_existing": False,
        "subtree_key": None,
        "authored": {
            "name": "famine_forage_cycle",
            "description": "seek food when energy is low",
            "tree": {
                "type": "Sequence",
                "args": [],
                "children": [
                    {"type": "CheckInternal", "args": ["energy", "<", 0.5], "children": []},
                    {"type": "QuerySense", "args": ["smell", "food"], "children": []},
                    {"type": "Locomote", "args": ["food"], "children": []},
                    {"type": "Interact", "args": ["food"], "children": []},
                ],
            },
        },
        "confidence": 0.85,
        "rationale": "conserve then forage under famine",
    }
    return (
        f"Author a new behavior subtree for species {cluster.species_id} under {pressure} pressure.\n"
        "Do NOT invent node types. Use only the manifest below.\n"
        f"Composites: {composites}\n"
        f"Verbs: {verbs}\n"
        f"Conditions: {conditions}\n"
        f"Locomote targets: {locomote}\n"
        f"Interact targets: food, prey, corpse, producer, nest\n"
        f"Emit substances: scent, spore, alarm\n"
        f"Max tree depth: {MAX_AUTHORED_DEPTH}, max nodes: {MAX_AUTHORED_NODES}\n"
        "Subtree name: lowercase alphanumeric and underscores only.\n"
        "Reply JSON only with this shape (use_existing must be false):\n"
        f"{json.dumps(example, indent=2)}"
    )


def parse_llm_json_payload(text: str) -> dict:
    """Parse model JSON, tolerating a single top-level object in a string."""
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise TypeError("LLM JSON root must be an object")
    return payload
