"""Multi-seed live Ollama reliability runner for pick/authored modes."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.llm_authored_smoke import evaluate_authored_smoke
from app.llm_smoke import build_stressed_llm_world, evaluate_smoke, summarize_adaptation_events
from sim.llm_adapter import OllamaLlmAdapter, ollama_model_available, poll_llm_completions, request_timeout_sec
from sim.tick import tick


@dataclass
class SoakResult:
    mode: str
    seed: int
    passed: bool
    duration_sec: float
    issues: list[str]
    event_counts: dict[str, int]
    adaptation_cache_entries: int
    authored_subtree_entries: int
    organisms_alive: int


def parse_int_list(raw: str) -> list[int]:
    values = [int(x.strip()) for x in raw.split(",") if x.strip()]
    if not values:
        raise ValueError("at least one seed is required")
    return values


def _drain_pending(world, grace_sec: float = 15.0) -> None:
    deadline = time.perf_counter() + request_timeout_sec(world) + grace_sec
    while world.pending_llm and time.perf_counter() < deadline:
        poll_llm_completions(world)
        time.sleep(0.2)


def run_single_pick(*, seed: int, ticks: int, dt: float, base_url: str, model: str) -> SoakResult:
    started = time.perf_counter()
    world = build_stressed_llm_world(seed=seed, starvation=0.0)
    world.llm_enabled = True
    world.llm_adapter = OllamaLlmAdapter(base_url=base_url, model=model, mode="pick")
    for _ in range(ticks):
        tick(world, dt)
    _drain_pending(world)
    counts = summarize_adaptation_events(world.adaptation_events)
    passed, issues = evaluate_smoke(world, counts)
    return SoakResult(
        mode="pick",
        seed=seed,
        passed=passed,
        duration_sec=time.perf_counter() - started,
        issues=issues,
        event_counts=counts,
        adaptation_cache_entries=len(world.adaptation_cache),
        authored_subtree_entries=len(world.authored_subtrees),
        organisms_alive=sum(1 for o in world.organisms if o.alive),
    )


def run_single_authored(*, seed: int, ticks: int, dt: float, base_url: str, model: str) -> SoakResult:
    started = time.perf_counter()
    world = build_stressed_llm_world(seed=seed, starvation=0.93)
    world.llm_enabled = True
    world.authored_auto_approve = True
    world.llm_adapter = OllamaLlmAdapter(base_url=base_url, model=model, mode="author")
    for _ in range(ticks):
        tick(world, dt)
    _drain_pending(world)
    counts = summarize_adaptation_events(world.adaptation_events)
    passed, issues = evaluate_authored_smoke(world, counts)
    return SoakResult(
        mode="authored",
        seed=seed,
        passed=passed,
        duration_sec=time.perf_counter() - started,
        issues=issues,
        event_counts=counts,
        adaptation_cache_entries=len(world.adaptation_cache),
        authored_subtree_entries=len(world.authored_subtrees),
        organisms_alive=sum(1 for o in world.organisms if o.alive),
    )


@dataclass
class GateThresholds:
    min_pass_rate: float = 0.9
    max_mean_duration_sec: float | None = None
    max_duration_sec: float | None = None
    min_mode_pass_rate: float | None = None


def evaluate_gate(summary: dict, thresholds: GateThresholds) -> tuple[bool, list[str]]:
    """Return (passed, violations) for aggregate soak metrics."""
    violations: list[str] = []
    pass_rate = float(summary.get("pass_rate", 0.0))
    if pass_rate < thresholds.min_pass_rate:
        violations.append(
            f"pass_rate {pass_rate:.1%} below minimum {thresholds.min_pass_rate:.1%}"
        )

    mean_dur = float(summary.get("duration_sec_mean", 0.0))
    if thresholds.max_mean_duration_sec is not None and mean_dur > thresholds.max_mean_duration_sec:
        violations.append(
            f"mean duration {mean_dur:.2f}s exceeds max {thresholds.max_mean_duration_sec:.2f}s"
        )

    max_dur = float(summary.get("duration_sec_max", 0.0))
    if thresholds.max_duration_sec is not None and max_dur > thresholds.max_duration_sec:
        violations.append(
            f"max duration {max_dur:.2f}s exceeds max {thresholds.max_duration_sec:.2f}s"
        )

    if thresholds.min_mode_pass_rate is not None:
        by_mode = summary.get("by_mode", {})
        for mode, stats in sorted(by_mode.items()):
            total = int(stats.get("total", 0))
            if total == 0:
                continue
            mode_rate = int(stats.get("passed", 0)) / total
            if mode_rate < thresholds.min_mode_pass_rate:
                violations.append(
                    f"mode {mode!r} pass_rate {mode_rate:.1%} below minimum "
                    f"{thresholds.min_mode_pass_rate:.1%}"
                )

    return len(violations) == 0, violations


def aggregate_results(results: list[SoakResult]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    durations = [r.duration_sec for r in results]
    event_totals: Counter[str] = Counter()
    failure_reasons: Counter[str] = Counter()
    by_mode: dict[str, dict[str, int]] = {}
    for r in results:
        event_totals.update(r.event_counts)
        if not r.passed:
            failure_reasons.update(r.issues)
        stats = by_mode.setdefault(r.mode, {"total": 0, "passed": 0, "failed": 0})
        stats["total"] += 1
        if r.passed:
            stats["passed"] += 1
        else:
            stats["failed"] += 1
    return {
        "total_runs": total,
        "passed_runs": passed,
        "failed_runs": total - passed,
        "pass_rate": (passed / total) if total else 0.0,
        "duration_sec_mean": statistics.mean(durations) if durations else 0.0,
        "duration_sec_max": max(durations) if durations else 0.0,
        "by_mode": by_mode,
        "event_totals": dict(event_totals),
        "failure_reasons": dict(failure_reasons),
    }


def _print_results(results: list[SoakResult], summary: dict, *, gate: dict | None = None) -> None:
    print("\nLLM soak results:")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(
            f"  [{status}] mode={r.mode} seed={r.seed} "
            f"dur={r.duration_sec:.2f}s alive={r.organisms_alive} "
            f"cache={r.adaptation_cache_entries} authored={r.authored_subtree_entries}"
        )
        if not r.passed:
            for issue in r.issues:
                print(f"    - {issue}")

    print("\nSoak summary:")
    print(
        f"  pass_rate={summary['pass_rate']:.1%} "
        f"({summary['passed_runs']}/{summary['total_runs']}) "
        f"mean_dur={summary['duration_sec_mean']:.2f}s max_dur={summary['duration_sec_max']:.2f}s"
    )
    for mode, stats in sorted(summary["by_mode"].items()):
        print(f"  mode={mode}: {stats['passed']}/{stats['total']} passed")
    if summary["failure_reasons"]:
        print("  top failure reasons:")
        for reason, count in sorted(summary["failure_reasons"].items(), key=lambda kv: (-kv[1], kv[0]))[:6]:
            print(f"    - {reason}: {count}")

    if gate is not None:
        status = "PASS" if gate.get("passed") else "FAIL"
        print(f"\nGate: {status}")
        for key, value in gate.get("thresholds", {}).items():
            if value is not None:
                print(f"  threshold {key}={value}")
        for violation in gate.get("violations", []):
            print(f"  - {violation}")


def _write_outputs(
    *,
    out_dir: Path,
    results: list[SoakResult],
    summary: dict,
    base_url: str,
    model: str,
    gate: dict | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "llm_soak_results.jsonl").write_text(
        "\n".join(json.dumps(asdict(r), separators=(",", ":")) for r in results) + "\n",
        encoding="utf-8",
    )
    meta = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "ollama_url": base_url,
        "ollama_model": model,
        "summary": summary,
        "gate": gate,
    }
    (out_dir / "llm_soak_summary.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\nWrote soak artifacts: {out_dir}")


def run_soak(args: argparse.Namespace) -> int:
    seeds = parse_int_list(args.seeds)
    base_url = args.ollama_url
    model = args.ollama_model
    if not ollama_model_available(base_url, model):
        print(f"llm_soak: Ollama model {model!r} not available at {base_url}", file=sys.stderr)
        if args.skip_if_unavailable:
            print("  skip_if_unavailable: exiting 0", file=sys.stderr)
            return 0
        return 2

    modes = ["pick", "authored"] if args.mode == "both" else [args.mode]
    results: list[SoakResult] = []
    for mode in modes:
        for seed in seeds:
            print(f"Running mode={mode} seed={seed}...")
            if mode == "pick":
                results.append(
                    run_single_pick(seed=seed, ticks=args.ticks, dt=args.dt, base_url=base_url, model=model)
                )
            else:
                results.append(
                    run_single_authored(
                        seed=seed,
                        ticks=args.authored_ticks,
                        dt=args.dt,
                        base_url=base_url,
                        model=model,
                    )
                )

    summary = aggregate_results(results)
    gate_report: dict | None = None
    if args.gate:
        thresholds = GateThresholds(
            min_pass_rate=args.min_pass_rate,
            max_mean_duration_sec=args.max_mean_duration_sec,
            max_duration_sec=args.max_duration_sec,
            min_mode_pass_rate=args.min_mode_pass_rate,
        )
        gate_passed, violations = evaluate_gate(summary, thresholds)
        gate_report = {
            "passed": gate_passed,
            "violations": violations,
            "thresholds": {
                "min_pass_rate": thresholds.min_pass_rate,
                "max_mean_duration_sec": thresholds.max_mean_duration_sec,
                "max_duration_sec": thresholds.max_duration_sec,
                "min_mode_pass_rate": thresholds.min_mode_pass_rate,
            },
        }
        summary["gate"] = gate_report

    _print_results(results, summary, gate=gate_report)
    if args.out:
        _write_outputs(
            out_dir=Path(args.out).resolve(),
            results=results,
            summary=summary,
            base_url=base_url,
            model=model,
            gate=gate_report,
        )

    run_ok = summary["failed_runs"] == 0
    gate_ok = gate_report is None or gate_report.get("passed", False)
    return 0 if run_ok and gate_ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run repeated live Ollama reliability checks across seeds/modes.",
    )
    p.add_argument("--mode", choices=["pick", "authored", "both"], default="both")
    p.add_argument("--seeds", type=str, default="101,102,103")
    p.add_argument("--ticks", type=int, default=110, help="Ticks for pick-mode runs")
    p.add_argument("--authored-ticks", type=int, default=130, help="Ticks for authored-mode runs")
    p.add_argument("--dt", type=float, default=1.0)
    p.add_argument("--ollama-url", type=str, default="http://127.0.0.1:11434")
    p.add_argument("--ollama-model", type=str, default="llama3.2")
    p.add_argument("--out", type=str, default="", help="Optional output directory for soak artifacts")
    p.add_argument(
        "--gate",
        action="store_true",
        help="Enforce aggregate pass-rate and duration thresholds (for nightly/CI)",
    )
    p.add_argument(
        "--min-pass-rate",
        type=float,
        default=0.9,
        help="Minimum overall pass rate when --gate is set (default 0.9)",
    )
    p.add_argument(
        "--min-mode-pass-rate",
        type=float,
        default=None,
        help="Optional per-mode minimum pass rate when --gate is set",
    )
    p.add_argument(
        "--max-mean-duration-sec",
        type=float,
        default=None,
        help="Optional maximum mean run duration when --gate is set",
    )
    p.add_argument(
        "--max-duration-sec",
        type=float,
        default=None,
        help="Optional maximum single-run duration when --gate is set",
    )
    p.add_argument(
        "--skip-if-unavailable",
        action="store_true",
        help="Exit 0 when Ollama/model is unavailable (useful for optional CI jobs)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_soak(args)
    except Exception as exc:
        print(f"llm_soak failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
