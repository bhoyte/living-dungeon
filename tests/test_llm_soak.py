from __future__ import annotations

from app.llm_soak import GateThresholds, SoakResult, aggregate_results, evaluate_gate, parse_int_list


def test_parse_int_list_parses_csv() -> None:
    assert parse_int_list("1, 2,3") == [1, 2, 3]


def test_parse_int_list_rejects_empty() -> None:
    try:
        parse_int_list(" , ")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_aggregate_results_summarizes_modes_and_failures() -> None:
    rows = [
        SoakResult(
            mode="pick",
            seed=1,
            passed=True,
            duration_sec=1.2,
            issues=[],
            event_counts={"llm.request.completed": 1},
            adaptation_cache_entries=1,
            authored_subtree_entries=0,
            organisms_alive=4,
        ),
        SoakResult(
            mode="authored",
            seed=2,
            passed=False,
            duration_sec=2.4,
            issues=["missing authored.approved"],
            event_counts={"authored.rejected": 1},
            adaptation_cache_entries=0,
            authored_subtree_entries=0,
            organisms_alive=4,
        ),
    ]
    summary = aggregate_results(rows)
    assert summary["total_runs"] == 2
    assert summary["passed_runs"] == 1
    assert summary["failed_runs"] == 1
    assert summary["by_mode"]["pick"]["passed"] == 1
    assert summary["by_mode"]["authored"]["failed"] == 1
    assert summary["failure_reasons"]["missing authored.approved"] == 1
    assert summary["event_totals"]["llm.request.completed"] == 1
    assert summary["event_totals"]["authored.rejected"] == 1


def test_evaluate_gate_passes_when_thresholds_met() -> None:
    summary = {
        "pass_rate": 1.0,
        "duration_sec_mean": 5.0,
        "duration_sec_max": 8.0,
        "by_mode": {"pick": {"total": 1, "passed": 1, "failed": 0}},
    }
    passed, violations = evaluate_gate(
        summary,
        GateThresholds(min_pass_rate=0.9, max_mean_duration_sec=10.0, max_duration_sec=12.0),
    )
    assert passed
    assert violations == []


def test_evaluate_gate_fails_on_low_pass_rate() -> None:
    summary = {"pass_rate": 0.5, "duration_sec_mean": 1.0, "duration_sec_max": 2.0, "by_mode": {}}
    passed, violations = evaluate_gate(summary, GateThresholds(min_pass_rate=0.9))
    assert not passed
    assert any("pass_rate" in v for v in violations)


def test_evaluate_gate_fails_on_mode_pass_rate() -> None:
    summary = {
        "pass_rate": 1.0,
        "duration_sec_mean": 1.0,
        "duration_sec_max": 1.0,
        "by_mode": {
            "pick": {"total": 2, "passed": 2, "failed": 0},
            "authored": {"total": 2, "passed": 0, "failed": 2},
        },
    }
    passed, violations = evaluate_gate(
        summary,
        GateThresholds(min_pass_rate=0.0, min_mode_pass_rate=0.8),
    )
    assert not passed
    assert any("mode 'authored'" in v for v in violations)
