from __future__ import annotations

import os
import time

import pytest

from app.llm_smoke import build_stressed_llm_world, evaluate_smoke, summarize_adaptation_events
from sim.constants import POPULATION_SCAN_INTERVAL
from sim.llm_adapter import OllamaLlmAdapter, ollama_model_available, poll_llm_completions, request_timeout_sec
from sim.tick import tick


@pytest.mark.integration
def test_live_ollama_selection_path_non_blocking() -> None:
    if os.environ.get("OLLAMA_TEST") != "1":
        pytest.skip("set OLLAMA_TEST=1 to run live Ollama integration")

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    if not ollama_model_available(base_url, model):
        pytest.skip(f"ollama model {model!r} unavailable at {base_url}")

    world = build_stressed_llm_world(seed=101)
    world.llm_enabled = True
    world.llm_adapter = OllamaLlmAdapter(base_url=base_url, model=model)

    for _ in range(POPULATION_SCAN_INTERVAL + 80):
        tick(world, 1.0)

    deadline = time.perf_counter() + request_timeout_sec(world) + 15.0
    while world.pending_llm and time.perf_counter() < deadline:
        poll_llm_completions(world)
        time.sleep(0.2)

    counts = summarize_adaptation_events(world.adaptation_events)
    passed, issues = evaluate_smoke(world, counts)
    assert passed, issues
