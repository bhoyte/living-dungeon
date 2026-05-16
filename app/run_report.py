"""Generate a markdown report from a headless run directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_telemetry(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _event_count_lines(meta: dict, key: str, heading: str) -> list[str]:
    counts = meta.get(key) or {}
    if not counts:
        return []
    lines = [heading]
    for name in sorted(counts):
        lines.append(f"- `{name}`: `{counts[name]}`")
    lines.append("")
    return lines


def build_report(run_dir: Path) -> str:
    meta = load_json(run_dir / "run_meta.json")
    summary = load_json(run_dir / "field_summary.json")
    telemetry = load_telemetry(run_dir / "telemetry.jsonl")
    adaptation_events_path = run_dir / "adaptation_events.jsonl"

    anomaly_ticks = [row["tick"] for row in telemetry if row.get("anomalies", {}).get("dirty")]
    last = telemetry[-1] if telemetry else {"fields": {}}

    lines: list[str] = []
    lines.append(f"# Run Report: {meta.get('profile_name', 'unknown')}")
    lines.append("")
    lines.append("## Metadata")
    lines.append(f"- Seed: `{meta.get('resolved_seed')}`")
    lines.append(f"- Size: `{meta.get('width')}x{meta.get('height')}`")
    lines.append(f"- Ticks requested: `{meta.get('ticks_requested')}`")
    lines.append(f"- Tick dt: `{meta.get('dt_per_tick')}`")
    lines.append(f"- Tilemap checksum: `{meta.get('tilemap_checksum_sha256')}`")
    lines.append("")

    if meta.get("final_organism_count") is not None:
        lines.append(f"- Final organisms: `{meta.get('final_organism_count')}`")
    lines.append("")

    lines.extend(_event_count_lines(meta, "adaptation_event_counts", "## Adaptation events (summary)"))
    lines.extend(_event_count_lines(meta, "contract_event_counts", "## Contract events (summary)"))

    if adaptation_events_path.is_file():
        event_rows = load_telemetry(adaptation_events_path)
        lines.append("## Adaptation events (jsonl)")
        lines.append(f"- Rows in `adaptation_events.jsonl`: `{len(event_rows)}`")
        lines.append("")

    lines.append("## Stability")
    lines.append(f"- Telemetry rows: `{len(telemetry)}`")
    lines.append(f"- Anomaly ticks: `{len(anomaly_ticks)}`")
    if anomaly_ticks:
        preview = ", ".join(str(x) for x in anomaly_ticks[:10])
        lines.append(f"- First anomaly ticks: `{preview}`")
    else:
        lines.append("- No anomaly flags observed.")
    lines.append("")

    lines.append("## Field Means (final summary)")
    for fname, stats in summary.get("fields", {}).items():
        lines.append(
            f"- `{fname}`: min={stats.get('min', 0):.4f}, "
            f"max={stats.get('max', 0):.4f}, mean={stats.get('mean', 0):.4f}"
        )
    lines.append("")

    lines.append("## Last Tick Snapshot")
    for fname, stats in last.get("fields", {}).items():
        lines.append(
            f"- `{fname}`: min={stats.get('min', 0):.4f}, "
            f"max={stats.get('max', 0):.4f}, mean={stats.get('mean', 0):.4f}"
        )

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a markdown report from a run directory")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out", default=None, help="Output markdown path; defaults to <run-dir>/report.md")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    out = Path(args.out) if args.out else (run_dir / "report.md")
    out.write_text(build_report(run_dir), encoding="utf-8")
    print(f"Wrote report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
