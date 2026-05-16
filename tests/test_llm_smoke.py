from __future__ import annotations

from dataclasses import dataclass, field

from app.llm_smoke import evaluate_smoke, summarize_adaptation_events


@dataclass
class _SmokeWorldStub:
    pending_llm: dict = field(default_factory=dict)
    adaptation_cache: dict = field(default_factory=dict)


def test_summarize_adaptation_events_counts_names() -> None:
    events = [
        {"event_name": "llm.request.started"},
        {"event_name": "llm.request.completed"},
        {"event_name": "adaptation.cache.insert"},
    ]
    counts = summarize_adaptation_events(events)
    assert counts["llm.request.started"] == 1
    assert counts["llm.request.completed"] == 1
    assert counts["adaptation.cache.insert"] == 1


def test_evaluate_smoke_passes_when_criteria_met() -> None:
    world = _SmokeWorldStub(adaptation_cache={"sig": object()})
    counts = {
        "llm.request.started": 1,
        "llm.request.completed": 1,
        "adaptation.cache.insert": 1,
    }
    passed, issues = evaluate_smoke(world, counts)  # type: ignore[arg-type]
    assert passed
    assert issues == []


def test_evaluate_smoke_fails_when_completion_missing() -> None:
    world = _SmokeWorldStub(adaptation_cache={"sig": object()})
    counts = {"llm.request.started": 1}
    passed, issues = evaluate_smoke(world, counts)  # type: ignore[arg-type]
    assert not passed
    assert "missing llm.request.completed" in issues
