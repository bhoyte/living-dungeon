"""Live Ollama authored-subtree smoke test (creatures playbook §6.7)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from app.llm_smoke import build_stressed_llm_world, summarize_adaptation_events
from sim.constants import POPULATION_SCAN_INTERVAL
from sim.llm_adapter import OllamaLlmAdapter, ollama_model_available, poll_llm_completions, request_timeout_sec
from sim.subtrees import SUBTREE_LIBRARY
from sim.tick import tick
from sim.world import World


def evaluate_authored_smoke(world: World, counts: dict[str, int]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if counts.get("llm.request.started", 0) < 1:
        issues.append("missing llm.request.started")
    if counts.get("llm.request.completed", 0) < 1:
        issues.append("missing llm.request.completed")
    if counts.get("authored.approved", 0) < 1:
        issues.append("missing authored.approved")
    if counts.get("authored.rejected", 0) > 0:
        issues.append("authored.rejected emitted (LLM tree failed validation)")
    if world.pending_llm:
        issues.append(f"pending_llm not drained ({len(world.pending_llm)} jobs)")
    if not world.authored_subtrees:
        issues.append("authored_subtrees empty after run")
    else:
        approved = [n for n, r in world.authored_subtrees.items() if r.state == "approved"]
        if not approved:
            issues.append("no approved authored subtree")
        for name in approved:
            if name not in SUBTREE_LIBRARY:
                issues.append(f"approved subtree {name!r} not in SUBTREE_LIBRARY")
    if not world.adaptation_cache:
        issues.append("adaptation_cache empty after run")
    return len(issues) == 0, issues


def print_authored_report(
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
    print(f"\nLLM authored smoke (§6.7): {status}")
    print(f"  ollama: {base_url}  model: {model}")
    print(f"  ticks: {ticks_run}  organisms alive: {sum(1 for o in world.organisms if o.alive)}")
    print(f"  authored: {len(world.authored_subtrees)}  cache: {len(world.adaptation_cache)}")
    for name, record in world.authored_subtrees.items():
        print(f"    {name} ({record.state})")
    event_names = sorted(
        k for k in counts if k.startswith("llm.") or k.startswith("authored.") or k.startswith("adaptation.")
    )
    if event_names:
        print("  events:")
        for name in event_names:
            print(f"    {name}: {counts[name]}")
    if issues:
        print("  issues:")
        for issue in issues:
            print(f"    - {issue}")


def run_authored_smoke(args: argparse.Namespace) -> int:
    base_url = args.ollama_url
    model = args.ollama_model

    if not ollama_model_available(base_url, model):
        print(
            f"llm_authored_smoke: Ollama model {model!r} not available at {base_url}",
            file=sys.stderr,
        )
        return 2

    world = build_stressed_llm_world(
        seed=args.seed,
        slime_count=args.slimes,
        starvation=args.starvation,
    )
    world.llm_enabled = True
    world.authored_auto_approve = True
    world.llm_adapter = OllamaLlmAdapter(base_url=base_url, model=model, mode="author")

    for _ in range(args.ticks):
        tick(world, args.dt)

    deadline = time.perf_counter() + request_timeout_sec(world) + 15.0
    while world.pending_llm and time.perf_counter() < deadline:
        poll_llm_completions(world)
        time.sleep(0.2)

    counts = summarize_adaptation_events(world.adaptation_events)
    passed, issues = evaluate_authored_smoke(world, counts)
    print_authored_report(
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
        authored_names = list(world.authored_subtrees.keys())
        meta = {
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "passed": passed,
            "issues": issues,
            "event_counts": counts,
            "authored_subtrees": authored_names,
            "ollama_url": base_url,
            "ollama_model": model,
            "ticks": args.ticks,
            "seed": args.seed,
        }
        (out_dir / "llm_authored_smoke_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        events_path = out_dir / "adaptation_events.jsonl"
        with events_path.open("w", encoding="utf-8") as fh:
            for event in world.adaptation_events:
                fh.write(json.dumps(event, separators=(",", ":")))
                fh.write("\n")
        if authored_names:
            record = world.authored_subtrees[authored_names[0]]
            (out_dir / "authored_spec.json").write_text(
                record.spec.model_dump_json(indent=2),
                encoding="utf-8",
            )
        print(f"  wrote: {out_dir}")

    return 0 if passed else 1


def build_parser() -> argparse.ArgumentParser:
    default_ticks = POPULATION_SCAN_INTERVAL + 100
    p = argparse.ArgumentParser(
        description="Live Ollama authored-subtree test with auto-approve (§6.7).",
    )
    p.add_argument("--ticks", type=int, default=default_ticks)
    p.add_argument("--seed", type=int, default=201)
    p.add_argument("--slimes", type=int, default=4)
    p.add_argument("--starvation", type=float, default=0.93, help="High starvation triggers famine pressure")
    p.add_argument("--dt", type=float, default=1.0)
    p.add_argument("--ollama-url", type=str, default="http://127.0.0.1:11434")
    p.add_argument("--ollama-model", type=str, default="llama3.2")
    p.add_argument("--out", type=str, default="")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_authored_smoke(args)
    except Exception as exc:
        print(f"llm_authored_smoke failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
