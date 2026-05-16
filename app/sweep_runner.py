"""Run scripted headless sweeps over seeds/ticks and save a compact CSV summary."""

from __future__ import annotations

import argparse
import csv
import json
from argparse import Namespace
from pathlib import Path

from app.headless import run_headless


def parse_int_list(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def run_sweep(profile: Path, seeds: list[int], ticks: list[int], out_root: Path, dt: float) -> Path:
    out_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []

    for seed in seeds:
        for tick_count in ticks:
            run_dir = out_root / f"seed-{seed}_ticks-{tick_count}"
            run_headless(
                Namespace(
                    profile=str(profile),
                    ticks=tick_count,
                    seed=seed,
                    out=str(run_dir),
                    dt=dt,
                    snapshot_npz=False,
                    enable_llm=False,
                    llm_authored=False,
                    ollama_url="http://127.0.0.1:11434",
                    ollama_model="llama3.2",
                    dump_adaptation_events=False,
                )
            )

            summary = json.loads((run_dir / "field_summary.json").read_text(encoding="utf-8"))
            fields = summary.get("fields", {})
            rows.append(
                {
                    "seed": seed,
                    "ticks": tick_count,
                    "mana_geo_mean": fields.get("mana_geo", {}).get("mean"),
                    "humidity_mean": fields.get("humidity", {}).get("mean"),
                    "temperature_mean": fields.get("temperature", {}).get("mean"),
                    "acidity_mean": fields.get("acidity", {}).get("mean"),
                    "run_dir": str(run_dir),
                }
            )

    csv_path = out_root / "sweep_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "seed",
                "ticks",
                "mana_geo_mean",
                "humidity_mean",
                "temperature_mean",
                "acidity_mean",
                "run_dir",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    return csv_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run parameter sweeps for headless ecosystem runs")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--seeds", required=True, help="Comma-separated seeds, e.g. 1,2,3")
    parser.add_argument("--ticks", required=True, help="Comma-separated tick counts, e.g. 200,600")
    parser.add_argument("--out", required=True, help="Output directory for sweep runs")
    parser.add_argument("--dt", type=float, default=1.0)
    args = parser.parse_args(argv)

    csv_path = run_sweep(
        Path(args.profile),
        parse_int_list(args.seeds),
        parse_int_list(args.ticks),
        Path(args.out),
        args.dt,
    )
    print(f"Wrote sweep summary: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
