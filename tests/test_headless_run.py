from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import numpy as np

from app.headless import run_headless
from sim.telemetry import anomaly_flags, tick_record


def test_telemetry_tick_record_shape() -> None:
    from sim.floor_profile import FloorProfile
    from sim.generation import generate_floor

    p = FloorProfile(
        name="T",
        width=20,
        height=16,
        seed=0,
        features=[],
        seed_producers=[],
        initial_creatures={},
    )
    world = generate_floor(p)
    rec = tick_record(1, world, profile_name=p.name, resolved_seed=p.seed)
    assert rec["tick"] == 1
    assert rec["profile_name"] == "T"
    assert "mana_geo" in rec["fields"]
    assert "min" in rec["fields"]["mana_geo"]
    anomalies = rec["anomalies"]
    assert isinstance(anomalies["dirty"], bool)
    assert anomaly_flags(world.field_map)["dirty"] == anomalies["dirty"]


def test_run_headless_writes_artifacts(tmp_path: Path) -> None:
    profile = {
        "name": "CLI Test",
        "width": 28,
        "height": 20,
        "seed": 123,
        "base_composition": "limestone",
        "features": [],
        "seed_producers": [],
        "initial_creatures": {},
    }
    prof_path = tmp_path / "p.json"
    prof_path.write_text(json.dumps(profile), encoding="utf-8")
    out = tmp_path / "run1"
    run_headless(
        Namespace(
            profile=str(prof_path),
            ticks=3,
            seed=None,
            out=str(out),
            dt=1.0,
            snapshot_npz=True,
        )
    )

    assert (out / "run_meta.json").is_file()
    assert (out / "telemetry.jsonl").is_file()
    assert (out / "field_summary.json").is_file()
    assert (out / "fields_snapshot.npz").is_file()

    lines = (out / "telemetry.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    first = json.loads(lines[0])
    assert first["tick"] == 1
    assert "anomalies" in first

    meta = json.loads((out / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["resolved_seed"] == 123
    assert meta["ticks_requested"] == 3

    npz = np.load(out / "fields_snapshot.npz")
    assert "field_mana_geo" in npz.files
