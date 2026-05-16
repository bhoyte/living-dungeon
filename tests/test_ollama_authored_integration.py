from __future__ import annotations

import os

import pytest

from app.llm_authored_smoke import evaluate_authored_smoke
from app.llm_smoke import build_stressed_llm_world, summarize_adaptation_events
from sim.constants import POPULATION_SCAN_INTERVAL
import time

from sim.llm_adapter import OllamaLlmAdapter, ollama_model_available, poll_llm_completions, request_timeout_sec
from sim.tick import tick


@pytest.mark.integration
def test_live_ollama_authored_subtree_adopted() -> None:
    if os.environ.get("OLLAMA_AUTHORED_TEST") != "1":
        pytest.skip("set OLLAMA_AUTHORED_TEST=1 to run live authored Ollama integration")

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    if not ollama_model_available(base_url, model):
        pytest.skip(f"ollama model {model!r} unavailable at {base_url}")

    world = build_stressed_llm_world(seed=201, starvation=0.93)
    world.llm_enabled = True
    world.authored_auto_approve = True
    world.llm_adapter = OllamaLlmAdapter(base_url=base_url, model=model, mode="author")

    for _ in range(POPULATION_SCAN_INTERVAL + 100):
        tick(world, 1.0)

    deadline = time.perf_counter() + request_timeout_sec(world) + 15.0
    while world.pending_llm and time.perf_counter() < deadline:
        poll_llm_completions(world)
        time.sleep(0.2)

    counts = summarize_adaptation_events(world.adaptation_events)
    passed, issues = evaluate_authored_smoke(world, counts)
    assert passed, issues
