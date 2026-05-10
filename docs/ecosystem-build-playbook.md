# Living Dungeon Ecosystem Build Playbook (Beginner-Friendly, Step-by-Step)

This guide is a hands-on implementation manual for building your dungeon ecosystem from zero code to a running headless simulation.

It is intentionally detailed and assumes you want hand-holding.

---

## 0) Read This First

### Project goal (current phase)

You are building the **dungeon ecosystem first**:

- static geology (`TileMap`)
- dynamic environmental metabolism (`FieldMap`)
- generation + seeded producers
- deterministic headless simulation + tests

You are **not** building full creature AI yet.

### Canon docs this playbook follows

1. `docs/canon/charter.md`
2. `docs/spec/ecosystem-v2.md`
3. `docs/canon/ecosystem-roadmap.md`
4. `docs/phase2/creatures-spec-v1.md` (later phase)
5. `docs/reference/north-star.md` (vision/rationale)

---

## 1) What You Will Build (High-Level Roadmap)

By the end, you should be able to run:

1. Load a floor profile JSON.
2. Generate a deterministic tile map.
3. Initialize 12 environmental fields.
4. Simulate field diffusion + decay + reactions for N ticks.
5. Seed sessile producers.
6. Output run summaries and verify deterministic tests.

If this works, your ecosystem core is "alive" enough to add creatures later.

---

## 2) External Resources (Use These Frequently)

These are trusted docs for tools this project uses:

- Python packaging (`pyproject.toml`): [Python Packaging User Guide](https://packaging.python.org/en/latest/)
- Pytest basics: [pytest docs](https://docs.pytest.org/en/stable/)
- NumPy basics: [NumPy user guide](https://numpy.org/doc/stable/user/)
- SciPy ndimage (diffusion kernels): [scipy.ndimage docs](https://docs.scipy.org/doc/scipy/reference/ndimage.html)
- SciPy spatial KDTree: [scipy.spatial docs](https://docs.scipy.org/doc/scipy/reference/spatial.html)
- python-tcod: [python-tcod docs](https://python-tcod.readthedocs.io/en/latest/)
- OpenSimplex package info: [opensimplex on PyPI](https://pypi.org/project/opensimplex/)
- Pydantic v2: [Pydantic docs](https://docs.pydantic.dev/latest/)
- Ruff linter/formatter: [Ruff docs](https://docs.astral.sh/ruff/)
- Import Linter: [import-linter docs](https://import-linter.readthedocs.io/en/stable/)
- Pygame CE (optional visualization): [pygame-ce docs](https://pyga.me/docs/)

Use these when stuck; do not guess APIs.

---

## 3) Preflight Checklist (Before Writing Code)

### You need

- Python 3.11+ installed
- A terminal (PowerShell is fine)
- Your editor open to repo root

### Verify Python

In PowerShell:

```powershell
python --version
```

You want Python 3.11+.

---

## 4) Repository Bootstrap (Day 1)

This section creates a stable base so you can iterate safely.

## 4.1 Create basic folders

Create these folders if missing:

```text
sim/
sim/systems/
app/
tests/
tests/fixtures/
data/floors/
runs/              # output artifacts (gitignored)
```

## 4.2 Create `pyproject.toml`

Start with dependencies aligned to `docs/spec/ecosystem-v2.md`.

Recommended minimal set:

- numpy
- scipy
- pydantic
- tcod
- opensimplex
- pytest
- ruff
- import-linter

Optional now:

- pygame-ce (if you want quick visual checks)
- pyfastnoiselite (for Worley later)

## 4.3 Add `.gitignore`

At minimum ignore:

- `.venv/`
- `__pycache__/`
- `.pytest_cache/`
- `.ruff_cache/`
- `runs/`
- `*.npz`

## 4.4 Install dependencies

If using pip:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install numpy scipy pydantic tcod opensimplex pytest ruff import-linter
```

## 4.5 Smoke-test tooling

```powershell
python -m pytest -q
python -m ruff check .
```

No tests yet is fine. You just want the commands to run.

---

## 5) Enforce Architecture Boundaries Early

This prevents messy refactors later.

Create `.importlinter` rules so:

- `sim` does **not** import `app`
- `sim` does **not** import rendering modules
- `sim` does **not** import future `ai` modules

Run boundary checks regularly while coding.

Why: your docs require simulation to remain headless and renderer-independent.

---

## 6) Phase 1 Implementation: Static Substrate (`TileMap`)

Files to implement first:

- `sim/tilemap.py`
- `sim/floor_profile.py`
- `tests/test_tilemap.py`

## 6.1 In `sim/tilemap.py` implement

1. `TileComp` enum (from `docs/spec/ecosystem-v2.md`)
2. `TileProps` model (pydantic or dataclass)
3. `TILE_PROPS` lookup table
4. `TileMap` class with:
   - `composition` grid
   - `cache_derived()`
   - cached accessors (`is_wall()`, `transparency()`, `source_field(attr)`)

Important: keep per-tick paths vectorized. Do not write nested Python tile loops in hot paths.

## 6.2 In `sim/floor_profile.py` implement

- `FloorProfile` schema
- validation for dimensions and generation parameters

## 6.3 Write tests

In `tests/test_tilemap.py`:

- create a small deterministic 8x8 map fixture
- set compositions manually
- assert:
  - wall count
  - passable count
  - source arrays shape/dtype
  - cache arrays are stable across repeated reads

Definition of done:

- `pytest` passes
- substrate arrays are reproducible and validated

---

## 7) Phase 2 Implementation: `FieldMap` Core

Files:

- `sim/fields.py`
- `tests/test_fieldmap.py`

## 7.1 Implement `FieldConfig`

Create config entries for the 12 fields from spec:

- names
- decay rates
- diffusion rates
- clamps
- boundary mode

## 7.2 Implement diffusion kernel safely

Follow the v2 kernel stability guidance:

- clamp diffusion mix rate (`r`) to safe range
- prevent negative center-weight artifacts

## 7.3 Implement `FieldMap.step(dt)`

Per field:

1. apply source terms
2. apply sink terms
3. diffuse (SciPy convolution)
4. decay
5. clamp to valid range

## 7.4 Tests

In `tests/test_fieldmap.py`:

- deterministic repeat test with fixed seed
- no `NaN` / `Inf`
- all values within expected clamp range
- basic monotonic sanity checks (for controlled fixtures)

Definition of done:

- two identical runs with same seed produce equivalent summaries

---

## 8) Phase 3: Reactions + Special Systems

Files:

- `sim/systems/field_step.py`
- `sim/systems/light_cast.py`
- `sim/systems/tremor_cast.py`
- `tests/test_field_step.py`
- `tests/test_special_fields.py`

## 8.1 `field_step.py`

Implement quiet reactions (R1..R5) from `docs/spec/ecosystem-v2.md`.

Use mask-based operations, not per-cell Python loops.

## 8.2 `light_cast.py`

Use `tcod` FOV to compute light field contribution.

Start simple:

- static emitters first
- no fancy attenuation model on day one

## 8.3 `tremor_cast.py`

Start with deterministic event input (tile + magnitude), then propagate into tremor field.

Optimization can come later (coalescing, multi-source shortest path).

## 8.4 Tests

- reaction directional checks (if corpse rises, mana_geo influence behaves as expected)
- light values remain bounded/non-negative
- tremor output deterministic for fixed event sequence

---

## 9) Phase 4: Generation Pipeline + Producers

Files:

- `sim/generation.py`
- `sim/systems/producer_seeding.py`
- `sim/world.py`
- `sim/tick.py`
- `tests/test_generation_determinism.py`

## 9.1 Implement generation in layers

Do this incrementally:

1. empty map
2. basic room/corridor carve
3. paint composition types
4. seed initial fields (noise + tile props)
5. warm-up ticks (field pre-equilibrium)

## 9.2 Implement producer seeding

Use field thresholds + tile constraints.

For v1 ecosystem phase:

- sessile producers only are enough
- mobile creatures can wait

## 9.3 Implement world + tick

`sim/world.py` should hold:

- tile map
- field map
- producer state
- seed + metadata

`sim/tick.py` orchestrates systems in fixed order.

## 9.4 Determinism test

Given same profile + seed:

- tile composition hash is identical
- key field summary stats are equivalent

---

## 10) Phase 5: Headless Runner + Telemetry

Files:

- `app/headless.py`
- `sim/telemetry.py`
- `tests/test_headless_run.py`

## 10.1 Build CLI runner

Example command target:

```powershell
python -m app.headless --profile data/floors/shallow_delve.json --ticks 600 --seed 42 --out runs/run-001
```

Output:

- run metadata JSON
- per-field summary JSON
- optional `.npz` snapshots
- telemetry/event log JSONL

## 10.2 Telemetry minimum

Log:

- tick index
- field extrema (min/max)
- anomaly flags
- seed/profile ids

This makes tuning objective instead of purely visual.

---

## 11) Phase 6: Save/Load + Long-Run Stability

Files:

- `sim/io.py` (or split modules)
- `tests/test_save_load.py`
- `tests/test_long_run_stability.py`

## 11.1 Save/load

- save fields as `numpy.savez_compressed`
- save metadata/profile with JSON

## 11.2 Round-trip test

1. run 200 ticks
2. save
3. load
4. run 100 more ticks
5. compare against uninterrupted 300 tick baseline (within epsilon)

## 11.3 Long-run test

Run 600+ ticks and assert:

- no `NaN`/`Inf`
- no runaway exploding fields beyond clamp
- summary metrics stay in expected range

---

## 12) Concrete 72-Hour Kickoff Plan

If you are overwhelmed, follow this exactly:

### Day 1

1. bootstrap folders + env + tooling
2. implement `tilemap.py` + tests
3. implement `floor_profile.py`

### Day 2

1. implement `fields.py`
2. add deterministic field tests
3. add reaction system stub

### Day 3

1. implement basic generation
2. wire `headless.py`
3. run 200-tick scenario and write summary output

If you complete this, you have a real ecosystem core.

---

## 13) When to Add "Bigger Tools" (No Guessing)

Only add these after hitting measurable pain:

- **Numba**: unavoidable Python loops show up hot in profiling
- **Taichi**: grids become very large and CPU updates are too slow
- **ECS (`esper`/`tcod-ecs`)**: entity filtering complexity and count justify architecture shift
- **Mesa**: you need ABM-style experiment orchestration and analytics

This keeps complexity proportional to your current stage.

---

## 14) Common Beginner Pitfalls (Read This Twice)

1. **Implementing too much at once**
   - Fix: one module + one test at a time.
2. **Skipping deterministic tests**
   - Fix: every new system gets at least one seeded test.
3. **Relying only on visuals**
   - Fix: always write numeric summaries to disk.
4. **Over-optimizing early**
   - Fix: first make it correct and measurable.
5. **Breaking architecture boundaries**
   - Fix: enforce import rules automatically.
6. **Changing many constants blindly**
   - Fix: tune one parameter family at a time.

---

## 15) Suggested "Definition of Done" for Ecosystem-First Phase

You can declare phase complete when all are true:

1. deterministic generation + simulation with fixed seeds
2. full field roster updates without instability
3. reactions and special fields run headless
4. producer seeding works from field conditions
5. save/load round-trip works
6. long-run stability tests pass
7. telemetry explains observed behavior

Then (and only then), start creature integration from `docs/phase2/creatures-spec-v1.md`.

---

## 16) Optional Nice-to-Haves After Core Is Running

- lightweight heatmap viewer
- scripted parameter sweep runner
- markdown run report generator
- CI workflow for lint + tests

Do these only after core tests are green.

---

## 17) Final Advice

When unsure, prefer:

- simpler system
- stronger test
- clearer telemetry

You are not behind. You are at the exact right stage to build this cleanly.

