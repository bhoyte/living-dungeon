"""One-command live Ollama adaptation smoke test with pass/fail summary."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sim.constants import CLUSTER_STRESS_THRESHOLD, POPULATION_SCAN_INTERVAL
from sim.epigenome import AdaptationMarkers
from sim.floor_profile import FloorProfile
from sim.generation import generate_floor
from sim.llm_adapter import OllamaLlmAdapter, ollama_model_available
from sim.tick import tick
from sim.world import World


def summarize_adaptation_events(events: list[dict]) -> dict[str, int]:
    return dict(Counter(e.get("event_name", "") for e in events))


def build_stressed_llm_world(
    *,
    seed: int,
    slime_count: int = 4,
    starvation: float = 0.0,
) -> World:
    """Floor with enough stressed slimes to trigger the population adaptation scan."""
    profile = FloorProfile(
        name="LLM Smoke",
        width=24,
        height=18,
        seed=seed,
        features=[],
        seed_producers=["mana_moss"],
        initial_creatures={"slime": slime_count},
    )
    world = generate_floor(profile)
    for org in world.organisms:
        if org.data.species_id != "slime":
            continue
        org.energy = 0.3
        org.stress = CLUSTER_STRESS_THRESHOLD + 0.1
        org.extensions["markers"] = AdaptationMarkers(
            starvation=starvation,
            predation=0.0,
            abundance=0.0,
        )
    return world


def evaluate_smoke(world: World, counts: dict[str, int]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if counts.get("llm.request.started", 0) < 1:
        issues.append("missing llm.request.started")
    if counts.get("llm.request.completed", 0) < 1:
        issues.append("missing llm.request.completed")
    if world.pending_llm:
        issues.append(f"pending_llm not drained ({len(world.pending_llm)} jobs)")
    if not world.adaptation_cache:
        issues.append("adaptation_cache empty after run")
    return len(issues) == 0, issues


def print_smoke_report(
    *,
    passed: bool,
    issues: list[str],
    counts: dict[str, int],
    world: World,
    ticks_run: int,
    model: str,
    base_url: str,
) -> None:
    status = "PASS" if passed else "FAIL"
    print(f"\nLLM smoke: {status}")
    print(f"  ollama: {base_url}  model: {model}")
    print(f"  ticks: {ticks_run}  organisms alive: {sum(1 for o in world.organisms if o.alive)}")
    print(f"  cache entries: {len(world.adaptation_cache)}  pending jobs: {len(world.pending_llm)}")
    if world.adaptation_cache:
        for sig, entry in world.adaptation_cache.items():
            print(f"    cache[{sig[:8]}…] -> {entry.subtree_key} ({entry.state})")
    llm_names = sorted(k for k in counts if k.startswith("llm.") or k.startswith("adaptation."))
    if llm_names:
        print("  events:")
        for name in llm_names:
            print(f"    {name}: {counts[name]}")
    if issues:
        print("  issues:")
        for issue in issues:
            print(f"    - {issue}")


def run_llm_smoke(args: argparse.Namespace) -> int:
    base_url = args.ollama_url
    model = args.ollama_model

    if not ollama_model_available(base_url, model):
        print(
            f"llm_smoke: Ollama model {model!r} not available at {base_url}",
            file=sys.stderr,
        )
        print("  hint: ollama serve && ollama pull " + model, file=sys.stderr)
        return 2

    world = build_stressed_llm_world(seed=args.seed, slime_count=args.slimes, starvation=args.starvation)
    world.llm_enabled = True
    world.llm_adapter = OllamaLlmAdapter(base_url=base_url, model=model)

    for _ in range(args.ticks):
        tick(world, args.dt)

    counts = summarize_adaptation_events(world.adaptation_events)
    passed, issues = evaluate_smoke(world, counts)
    print_smoke_report(
        passed=passed,
        issues=issues,
        counts=counts,
        world=world,
        ticks_run=args.ticks,
        model=model,
        base_url=base_url,
    )

    if args.out:
        out_dir = Path(args.out).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "passed": passed,
            "issues": issues,
            "event_counts": counts,
            "ollama_url": base_url,
            "ollama_model": model,
            "ticks": args.ticks,
            "seed": args.seed,
        }
        (out_dir / "llm_smoke_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        events_path = out_dir / "adaptation_events.jsonl"
        with events_path.open("w", encoding="utf-8") as fh:
            for event in world.adaptation_events:
                fh.write(json.dumps(event, separators=(",", ":")))
                fh.write("\n")
        print(f"  wrote: {out_dir}")

    return 0 if passed else 1


def build_parser() -> argparse.ArgumentParser:
    default_ticks = POPULATION_SCAN_INTERVAL + 80
    p = argparse.ArgumentParser(
        description="Run a stressed floor with live Ollama adaptation and print pass/fail.",
    )
    p.add_argument("--ticks", type=int, default=default_ticks, help="Simulation ticks to run")
    p.add_argument("--seed", type=int, default=101, help="Floor generation seed")
    p.add_argument("--slimes", type=int, default=4, help="Initial slime count (need >= 3 for cluster)")
    p.add_argument(
        "--starvation",
        type=float,
        default=0.0,
        help="Starvation marker (0 keeps dominant pressure 'none' for broader subtree picks)",
    )
    p.add_argument("--dt", type=float, default=1.0, help="Simulation timestep per tick")
    p.add_argument("--ollama-url", type=str, default="http://127.0.0.1:11434")
    p.add_argument("--ollama-model", type=str, default="llama3.2")
    p.add_argument("--out", type=str, default="", help="Optional output directory for event dump")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_llm_smoke(args)
    except Exception as exc:
        print(f"llm_smoke failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
