"""Headless CLI: load profile → generate floor → simulate → write telemetry artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from sim.floor_profile import FloorProfile
from sim.generation import generate_floor
from sim.telemetry import field_extrema, tick_record, tilemap_checksum
from sim.tick import tick


def load_profile(path: Path) -> FloorProfile:
    data = json.loads(path.read_text(encoding="utf-8"))
    return FloorProfile.model_validate(data)


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, separators=(",", ":"), sort_keys=False))
        fh.write("\n")


def write_summary(path: Path, world, *, ticks_run: int, dt: float) -> None:
    payload = {
        "ticks_simulated": ticks_run,
        "dt_per_tick": dt,
        "fields": field_extrema(world.field_map),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_headless(args: argparse.Namespace) -> Path:
    profile_path = Path(args.profile).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    profile = load_profile(profile_path)
    resolved_seed = int(args.seed if args.seed is not None else profile.seed)
    data = profile.model_dump()
    data["seed"] = resolved_seed
    profile = FloorProfile.model_validate(data)

    world = generate_floor(profile)

    meta = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "profile_path": str(profile_path),
        "profile_name": profile.name,
        "depth_index": profile.depth_index,
        "resolved_seed": resolved_seed,
        "width": profile.width,
        "height": profile.height,
        "ticks_requested": args.ticks,
        "dt_per_tick": args.dt,
        "tilemap_checksum_sha256": tilemap_checksum(world.tilemap),
        "producer_placements_recorded": len(world.producer_spawns),
        "creature_spawns_recorded": len(world.creature_spawns),
    }
    (out_dir / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    telemetry_path = out_dir / "telemetry.jsonl"
    if telemetry_path.exists():
        telemetry_path.unlink()

    for i in range(args.ticks):
        tick(world, args.dt)
        rec = tick_record(
            i + 1,
            world,
            profile_name=profile.name,
            resolved_seed=resolved_seed,
        )
        append_jsonl(telemetry_path, rec)

    write_summary(out_dir / "field_summary.json", world, ticks_run=args.ticks, dt=args.dt)

    if args.snapshot_npz:
        arrays = {f"field_{k}": v for k, v in world.field_map.fields.items()}
        npz_path = out_dir / "fields_snapshot.npz"
        np.savez_compressed(npz_path, **arrays)

    return out_dir


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Headless dungeon ecosystem simulation.")
    p.add_argument("--profile", type=str, required=True, help="Path to floor profile JSON")
    p.add_argument("--ticks", type=int, required=True, help="Simulation ticks after generation")
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Override profile seed (determinism / A-B testing)",
    )
    p.add_argument("--out", type=str, required=True, help="Output directory under runs/")
    p.add_argument(
        "--dt",
        type=float,
        default=1.0,
        help="Simulation timestep per tick (seconds scale; passed to FieldMap.step)",
    )
    p.add_argument(
        "--snapshot-npz",
        action="store_true",
        help="Write compressed fields_snapshot.npz at end",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run_headless(args)
    except Exception as e:
        print(f"headless failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
