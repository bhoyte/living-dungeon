# Living Dungeon

Design and specs live under [`docs/README.md`](docs/README.md) (ecosystem-first layout: `docs/canon/`, `docs/spec/`, `docs/reference/`, `docs/phase2/`, `docs/research/`).

Evaluation prompts for doc review: [`eval-prompts/`](eval-prompts/).

## Tooling

Activate the project virtual environment if you use one (for example `.venv-living-dungeon`), then from the repo root:

**Headless run** (writes `run_meta.json`, `telemetry.jsonl`, `field_summary.json`; add `--snapshot-npz` for a field dump):

```powershell
python -m app.headless --profile data/floors/shallow_delve.json --ticks 600 --seed 42 --out runs/run-001
```

**ASCII heatmap** from a saved snapshot (requires `--snapshot-npz` on the run above):

```powershell
python -m app.heatmap_viewer --npz runs/run-001/fields_snapshot.npz --field mana_geo
```

**Parameter sweep** (writes one subfolder per seed/tick pair plus `sweep_summary.csv`):

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
