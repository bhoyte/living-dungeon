# Living Dungeon

A **dungeon-first** simulation: the floor is treated as a living substrate—static geology, evolving environmental fields, and sessile ecology—before full creature AI. The goal is **deterministic, headless, testable** behavior so tuning and design stay evidence-based.

## What this repo contains

| Area | Role |
|------|------|
| [`sim/`](sim/) | Core simulation: tile map, fields, generation, reactions, light/tremor, telemetry, save/load checkpoints. **No GUI**; `sim` must not import `app` (enforced by [import-linter](https://import-linter.readthedocs.io/en/stable/)). |
| [`app/`](app/) | CLI and tooling: headless runs, heatmaps, sweeps, markdown reports. |
| [`tests/`](tests/) | Pytest suite: substrate, fields, reactions, generation determinism, headless artifacts, save/load round-trip, long-run stability. |
| [`data/floors/`](data/floors/) | Example floor profiles (JSON) consumed by generation. |
| [`docs/`](docs/) | Canon, specs, phase-2 creatures spec, build playbooks, and research. |

**Implemented today:** ecosystem pipeline from profile → generated `TileMap` → `FieldMap` (12 fields) → quiet reactions → tcod light + tremor → producer seeding from field masks → headless runs with telemetry → optional NPZ snapshots → checkpoint save/load → CI (ruff, pytest, import boundaries).

**Deferred (phase 2):** mobile creatures, behavior trees, LLM adaptation—see [`docs/phase2/creatures-spec-v1.md`](docs/phase2/creatures-spec-v1.md) and the step-by-step [`docs/phase2/creatures-build-playbook.md`](docs/phase2/creatures-build-playbook.md).

## Documentation map

Start here for **reading order** and folder roles: [`docs/README.md`](docs/README.md).

| Doc | Purpose |
|-----|---------|
| [`docs/canon/charter.md`](docs/canon/charter.md) | Dungeon-first direction and phase gates. |
| [`docs/spec/ecosystem-v2.md`](docs/spec/ecosystem-v2.md) | Active ecosystem implementation spec. |
| [`docs/ecosystem-build-playbook.md`](docs/ecosystem-build-playbook.md) | Hands-on guide from bootstrap through telemetry (phase 1). |
| [`docs/canon/ecosystem-roadmap.md`](docs/canon/ecosystem-roadmap.md) | Sprint-style ecosystem roadmap. |
| [`docs/phase2/creatures-spec-v1.md`](docs/phase2/creatures-spec-v1.md) | Normative phase-2 creatures + adaptation contract. |
| [`docs/phase2/creatures-build-playbook.md`](docs/phase2/creatures-build-playbook.md) | Phase-2 implementation playbook. |
| [`docs/reference/north-star.md`](docs/reference/north-star.md) | Vision and rationale (non-binding vs canon). |

**Doc-first runnable commands** are summarized under “Running the Sim” in [`docs/README.md`](docs/README.md) and duplicated below for convenience.

## Requirements and setup

- **Python 3.11+**
- Create a venv and install deps (from repo root):

```powershell
python -m venv .venv-living-dungeon
.\.venv-living-dungeon\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
```

If you prefer not to use editable install, use the dependency list in [`pyproject.toml`](pyproject.toml) (numpy, scipy, pydantic, tcod, opensimplex, pytest, ruff, import-linter).

**Import linter:** run `lint-imports` only from the activated venv (the `lint-imports` console script is installed there).

## Architecture (high level)

1. **`FloorProfile`** (JSON) describes width, height, seed, baselines, BSP params, geological features, and seed lists.
2. **`generate_floor`** builds a **`World`**: BSP rooms + corridors, composition painting, cached tile derivatives, `FieldMap`, noise seeding, warmup ticks, producer placement, optional creature spawn records.
3. **`tick(world, dt)`** each step: field diffusion/decay/sources/sinks → quiet reactions (R1–R5) → **light** (tcod FOV) → **tremor** (event-driven).
4. **`app.headless`** runs N ticks and writes **`run_meta.json`**, **`telemetry.jsonl`**, **`field_summary.json`**, optional **`fields_snapshot.npz`** under `runs/`.
5. **`sim.io`** checkpoints: JSON metadata + compressed field arrays for save/load round-trips.

Continuous integration: [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs ruff, pytest, and import-linter on push and PR.

## Tooling

Activate the project virtual environment (for example `.venv-living-dungeon`), then from the repo root:

**Headless run** (writes `run_meta.json`, `telemetry.jsonl`, `field_summary.json`; add `--snapshot-npz` for a field dump):

```powershell
python -m app.headless --profile data/floors/shallow_delve.json --ticks 600 --seed 42 --out runs/run-001
```

**ASCII heatmap** from a saved snapshot (requires `--snapshot-npz` on the run above):

```powershell
python -m app.heatmap_viewer --npz runs/run-001/fields_snapshot.npz --field mana_geo
```

**Parameter sweep** (one subfolder per seed/tick pair plus `sweep_summary.csv`):

```powershell
python -m app.sweep_runner --profile data/floors/shallow_delve.json --seeds 1,2,3 --ticks 200,600 --out runs/sweeps/batch-01
```

**Markdown report** from a completed run directory:

```powershell
python -m app.run_report --run-dir runs/run-001
```

**Local checks** (same steps as CI):

```powershell
python -m ruff check .
python -m pytest -q
lint-imports
```

## Other repo roots

- **Design review prompts:** [`eval-prompts/`](eval-prompts/)

## License

Add a `LICENSE` file when you choose a license for the project.
