# Dungeon-First Ecosystem Specification (v2)

> Active implementation canon for ecosystem-first phase-1.  
> Companion to `docs/canon/charter.md`. Specifies the dungeon as a first-class organism: its geology, physiology, and metabolism, with creature systems intentionally deferred.
>
> **v2 changelog (vs. v1 of this doc):**
> - Added §3.5 — vectorization rules and a fix for the per-tile loop in `TileMap.is_wall`.
> - Added §3.6 — diffusion-kernel stability note; clamp the per-tick mixing fraction to keep the explicit scheme stable.
> - Added §4.6 — `tremor` field (acoustic / vibration) to make the `echolocation` trait load-bearing instead of a stub.
> - Added §6.5 — Dijkstra goal maps as the standard pattern for goal-directed creature navigation, decoupled from stigmergy diffusion.
> - Promoted Worley/cellular noise to first-class for cave-pocket fields (mana_geo, mana_aqua) — naturalistic clustering instead of smooth gradients.
> - Added §9.2 — optional mission graph layer (`networkx`) for lock-and-key flow on deeper floors, deferred but specified.
> - Added §10.5 — opt-in WFC tile painter as an alternative to the rule-based feature placer (post-v1).
> - Added §15 — boundary-translator pattern for the post-v1 LLM DungeonMaster, isolating the LLM from the simulation core.
> - Updated §14 open questions and §13 sprint table to reflect the above.

---

## Canon status

This is the active implementation spec for ecosystem-first phase-1.  
If this document conflicts with creature-focused guidance elsewhere, this document wins for phase-1 decisions.

## 0. Why this document exists

We caught ourselves doing what most LLM-gamedev projects do: obsessing over the agent and treating the world as a stage. In a Dungeon Meshi–style ecosystem the dungeon is not a stage. It is a metabolism. Creatures are expressions of it. Pull the dungeon out from under them and they stop making sense.

This document defines the dungeon's anatomy in four layers, in dependency order:

1. **Static substrate** — `TileMap`. The skeleton. Tile composition, walls, geometry. Doesn't change tick to tick.
2. **Dynamic fields** — `FieldMap`. The bloodstream. Twelve scalar fields evolving every tick: mana variants, temperature, humidity, acidity, light, tremor, scent variants.
3. **Sessile biology** — Producers (moss, fungi, root mats). Placed by field conditions. Slow growth and decay.
4. **Mobile biology** — Creatures. The `Organism` from north-star. The thing we used to start with, now correctly at the top of the stack.

Layers below do not know about layers above. A field doesn't know which creature is consuming it; it sees only a sink term in its tile. A tile doesn't know what fields depend on it; it just exposes a composition. This is the seam that keeps the system testable.

---

## 1. Stack additions

Three new dependencies on top of north-star §13, plus one optional:

| Package | Role | Required? |
|---|---|---|
| `tcod` | BSP/CA room generation; FOV/LOS for sight-based senses and light field | yes (v1) |
| `opensimplex` | Noise-based seeding of initial field conditions | yes (v1) |
| `scipy` | `ndimage.convolve` for diffusion; `spatial.KDTree` for radius queries; `ndimage.distance_transform_edt` for Dijkstra-style fields | yes (v1) |
| `pyfastnoiselite` | Worley/cellular noise for naturalistic cave-pocket mana fields | optional (v1, falls back to opensimplex) |
| `networkx` | Mission graphs / lock-and-key flow on deeper floors | post-v1 |

`numba` and `taichi` stay out. `esper` and `tcod-ecs` stay out (see §8 for the explicit adoption trigger). `mesa` stays out — we don't need a separate ABM framework; `Organism` + `py_trees` covers it.

`pyproject.toml` additions:

```toml
dependencies = [
    "numpy>=1.26",
    "scipy>=1.13",
    "pydantic>=2.6",
    "py_trees>=2.2",
    "httpx>=0.27",
    "tcod>=16.2",
    "opensimplex>=0.4",
    "pygame-ce>=2.4",
]

[project.optional-dependencies]
naturalism = ["pyfastnoiselite>=0.0.4"]   # Worley noise for cave-pocket fields
deep-floors = ["networkx>=3.2"]           # mission graphs (post-v1)
```

---

## 2. Static substrate — `TileMap`

A floor's skeleton. Per-tile static data, set at generation time, never modified during a run except by explicit DungeonMaster spells (collapse, transmute) which are post-v1.

### 2.1 Tile composition enum

```python
# sim/tilemap.py
from enum import IntEnum

class TileComp(IntEnum):
    # Walls (impassable, opaque)
    WALL_STONE       = 0
    WALL_LIMESTONE   = 1
    WALL_CRYSTAL     = 2     # luminescent, mana_geo source
    # Floors (passable)
    FLOOR_STONE      = 10    # neutral baseline
    FLOOR_LIMESTONE  = 11    # mild acidity buffer
    FLOOR_CRYSTAL    = 12    # mana_geo source, light source
    FLOOR_WET_CLAY   = 13    # humidity source, retains scent
    FLOOR_SAND       = 14    # low traction, humidity sink
    FLOOR_BONE       = 15    # mild acidity buffer
    FLOOR_MYCELIUM   = 16    # mana_geo sink, spore source, slight acidity source
    # Liquids
    SHALLOW_WATER    = 20    # mana_aqua source, humidity source
    DEEP_WATER       = 21    # mana_aqua source (stronger), impassable for non-aquatic
    ACID_POOL        = 22    # acidity source, mana_geo sink
```

This is the v1 set. Adding compositions is cheap; the generator just needs a placement rule and the per-composition properties get a new row.

### 2.2 Per-composition properties

Single source of truth for what each composition does. Lives as a dict keyed by `TileComp`:

```python
# sim/tilemap.py
from pydantic import BaseModel

class TileProps(BaseModel):
    is_wall:          bool   = False
    is_passable:      bool   = True
    is_transparent:   bool   = True   # for tcod FOV
    traction:         float  = 1.0    # locomotion speed multiplier
    porosity:         float  = 0.5    # humidity retention (1.0 = perfect retention)
    ceiling_height:   int    = 3      # tile units; gates flying creatures
    elevation:        float  = 0.0    # for fluid pooling later
    sound_absorption: float  = 0.05   # tremor field attenuation per tile traversed (§4.6)

    # Field source contributions (added per tick to the relevant field at this tile)
    mana_geo_src:     float  = 0.0
    mana_aqua_src:    float  = 0.0
    humidity_src:     float  = 0.0
    acidity_src:      float  = 0.0
    light_src:        float  = 0.0    # bioluminescent emission strength
    spore_src:        float  = 0.0

    # Field sink contributions (subtracted per tick)
    mana_geo_sink:    float  = 0.0
    humidity_sink:    float  = 0.0
    acidity_sink:     float  = 0.0    # buffering capacity

TILE_PROPS: dict[TileComp, TileProps] = {
    TileComp.WALL_STONE:      TileProps(is_wall=True, is_passable=False, is_transparent=False, traction=0.0, sound_absorption=0.40),
    TileComp.WALL_LIMESTONE:  TileProps(is_wall=True, is_passable=False, is_transparent=False, traction=0.0, sound_absorption=0.30, acidity_sink=0.005),
    TileComp.WALL_CRYSTAL:    TileProps(is_wall=True, is_passable=False, is_transparent=False, traction=0.0, sound_absorption=0.20, mana_geo_src=0.020, light_src=0.30),

    TileComp.FLOOR_STONE:     TileProps(),
    TileComp.FLOOR_LIMESTONE: TileProps(porosity=0.6, acidity_sink=0.008),
    TileComp.FLOOR_CRYSTAL:   TileProps(mana_geo_src=0.030, light_src=0.40),
    TileComp.FLOOR_WET_CLAY:  TileProps(porosity=0.85, humidity_src=0.010, traction=0.85, sound_absorption=0.15),
    TileComp.FLOOR_SAND:      TileProps(porosity=0.20, traction=0.70, humidity_sink=0.012, sound_absorption=0.20),
    TileComp.FLOOR_BONE:      TileProps(porosity=0.45, acidity_sink=0.004),
    TileComp.FLOOR_MYCELIUM:  TileProps(porosity=0.70, mana_geo_sink=0.010, spore_src=0.005, acidity_src=0.002, sound_absorption=0.25),

    TileComp.SHALLOW_WATER:   TileProps(traction=0.6, mana_aqua_src=0.020, humidity_src=0.030, ceiling_height=3, sound_absorption=0.10),
    TileComp.DEEP_WATER:      TileProps(is_passable=False, mana_aqua_src=0.040, humidity_src=0.040, sound_absorption=0.05),
    TileComp.ACID_POOL:       TileProps(traction=0.5, acidity_src=0.030, mana_geo_sink=0.005),
}
```

These numbers are first-pass. They will be tuned from telemetry once Sprint 4 is running. The point is the table exists, every composition has a row, and the field simulator reads source/sink terms from it without any if-else logic.

### 2.3 `TileMap` class

```python
# sim/tilemap.py
import numpy as np

class TileMap:
    """Static per-tile data for a floor. Set at generation, immutable thereafter (v1)."""

    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.composition = np.full((h, w), TileComp.FLOOR_STONE, dtype=np.int8)
        self._cache: dict[str, np.ndarray] = {}

    def cache_derived(self) -> None:
        """Call once after generation to precompute every static array.

        Reads composition exactly once per attribute. Subsequent calls to
        is_wall(), transparency(), source_field() return cached arrays.
        """
        for attr_name, dtype, default in [
            ("is_wall",          np.bool_,   False),
            ("is_passable",      np.bool_,   True),
            ("is_transparent",   np.bool_,   True),
            ("traction",         np.float32, 1.0),
            ("porosity",         np.float32, 0.5),
            ("sound_absorption", np.float32, 0.05),
            ("mana_geo_src",     np.float32, 0.0),
            ("mana_aqua_src",    np.float32, 0.0),
            ("humidity_src",     np.float32, 0.0),
            ("acidity_src",      np.float32, 0.0),
            ("light_src",        np.float32, 0.0),
            ("spore_src",        np.float32, 0.0),
            ("mana_geo_sink",    np.float32, 0.0),
            ("humidity_sink",    np.float32, 0.0),
            ("acidity_sink",     np.float32, 0.0),
        ]:
            arr = np.full((self.h, self.w), default, dtype=dtype)
            for comp, props in TILE_PROPS.items():
                mask = self.composition == comp
                if mask.any():
                    arr[mask] = getattr(props, attr_name)
            self._cache[attr_name] = arr

    def is_wall(self) -> np.ndarray:
        return self._cache["is_wall"]

    def transparency(self) -> np.ndarray:
        return self._cache["is_transparent"]

    def source_field(self, attr: str) -> np.ndarray:
        return self._cache[attr]
```

The expensive bits are computed once at generation via vectorized boolean masks (no per-tile Python). `FieldMap` reads the cached source/sink arrays each tick — zero per-tile work.

> **Vectorization rule.** No Python per-tile loops anywhere in `TileMap`, `FieldMap`, or any system that runs per tick. If you find yourself writing `for x in range(w): for y in range(h):`, stop and rewrite with `np.where`, boolean masks, or `np.meshgrid`. The original v1 spec had a per-tile loop in `is_wall`; v2 fixes it.

---

## 3. Dynamic fields — `FieldMap`

The dungeon's metabolism. Twelve scalar fields, all `float32`, all on the same grid resolution (unified — no multi-resolution in v1). All updated each tick.

### 3.1 Field roster

| # | Field | Class | Source | Sink | Decay (per sec) | Diffuse rate | Clamp | Boundary |
|---|---|---|---|---|---|---|---|---|
| 1 | `mana_geo` | geological | crystal tiles, corpse decomposition | photosynthesis trait, mycelium tiles | 0.001 | 0.020 | [0,1] | constant 0 |
| 2 | `mana_aether` | geological | bleed from `mana_geo` (rate 0.002) | flying-creature metabolism | 0.005 | 0.080 | [0,1] | constant 0 |
| 3 | `mana_aqua` | geological | water tiles | aquatic-creature metabolism | 0.003 | 0.050 | [0,1] | constant 0 |
| 4 | `temperature` | geological | floor baseline equilibrium | radiative loss | 0.010 → baseline | 0.040 | [-20, 60] | constant baseline |
| 5 | `humidity` | geological | water tiles, wet_clay | sand tiles, evaporation | 0.008 | 0.060 | [0,1] | constant baseline |
| 6 | `acidity` | geological | corpse decay, acid_pool, mycelium | limestone, bone tiles | 0.005 | 0.030 | [0,1] | constant 0 |
| 7 | `light` | geological | crystal tiles, light traits | walls (occlude) | recomputed each tick | **special: tcod FOV** | [0,1] | N/A |
| 8 | `tremor` | geological | locomotion events, attack events | distance × material absorption | recomputed each tick | **special: weighted Dijkstra** | [0,1] | N/A |
| 9 | `sweet` | stigmergy | `Emit("sweet")` | — | 0.050 | 0.150 | [0,1] | constant 0 |
| 10 | `alarm` | stigmergy | death events, attack events | — | 0.080 | 0.200 | [0,1] | constant 0 |
| 11 | `corpse` | stigmergy | death events | carnivore `Interact`, decomposition | 0.010 | 0.050 | [0,1] | constant 0 |
| 12 | `spore` | stigmergy | mycelium tiles, mature producer death | — | 0.020 | 0.100 | [0,1] | constant 0 |

The 7 geological fields evolve slowly and reach quasi-equilibrium. The 4 stigmergy fields are fast, creature-driven, and decay to zero quickly. Two fields (`light`, `tremor`) are *special* — they don't diffuse; they're recomputed per tick from sources (see §3.2 and §4.6).

### 3.2 Light is special

Every other diffusing field uses `scipy.ndimage.convolve`. Light does not. Light is **recomputed each tick from sources via tcod FOV**, then attenuated by distance. This is correct because:

- Light doesn't diffuse around corners. It travels in straight lines until blocked by a wall.
- Walls fully occlude rather than partially diffuse.
- tcod's `compute_fov` is a single C call per source and is the right algorithm.

```python
# sim/systems/light_cast.py
import tcod
import numpy as np

def cast_light(world) -> np.ndarray:
    h, w = world.tilemap.h, world.tilemap.w
    transparency = world.tilemap.transparency()
    light = np.zeros((h, w), dtype=np.float32)

    # Static tile sources
    for (y, x, intensity, radius) in world.static_light_sources:
        fov = tcod.map.compute_fov(transparency, (x, y), radius=int(radius))
        yy, xx = np.ogrid[:h, :w]
        dist = np.hypot(xx - x, yy - y)
        atten = np.clip(1.0 - dist / max(radius, 1.0), 0, 1).astype(np.float32)
        np.add(light, np.where(fov, intensity * atten, 0.0), out=light)

    # Dynamic creature light sources (organisms with bioluminescent trait, post-v1)
    return np.clip(light, 0.0, 1.0)
```

`world.static_light_sources` is computed once at generation by walking `tilemap.composition` and emitting one entry per `light_src > 0` tile. ~50 sources on a 60×40 floor; tcod handles all of them in single-digit milliseconds per tick.

### 3.3 `FieldMap` class

```python
# sim/fields.py
import numpy as np
import scipy.ndimage as ndi
from pydantic import BaseModel

class FieldConfig(BaseModel):
    decay:         float
    diffuse:       float        # 0 = none, ~0.2 = strong (clamped to <= 0.9 for stability)
    clamp_lo:      float = 0.0
    clamp_hi:      float = 1.0
    boundary_mode: str   = "constant"   # passed to scipy
    boundary_val:  float = 0.0
    is_special:    bool  = False        # True for light, tremor

FIELD_CONFIG: dict[str, FieldConfig] = {
    "mana_geo":    FieldConfig(decay=0.001, diffuse=0.020),
    "mana_aether": FieldConfig(decay=0.005, diffuse=0.080),
    "mana_aqua":   FieldConfig(decay=0.003, diffuse=0.050),
    "temperature": FieldConfig(decay=0.010, diffuse=0.040, clamp_lo=-20, clamp_hi=60),
    "humidity":    FieldConfig(decay=0.008, diffuse=0.060),
    "acidity":     FieldConfig(decay=0.005, diffuse=0.030),
    "light":       FieldConfig(decay=0.0,   diffuse=0.0, is_special=True),
    "tremor":      FieldConfig(decay=0.0,   diffuse=0.0, is_special=True),
    "sweet":       FieldConfig(decay=0.050, diffuse=0.150),
    "alarm":       FieldConfig(decay=0.080, diffuse=0.200),
    "corpse":      FieldConfig(decay=0.010, diffuse=0.050),
    "spore":       FieldConfig(decay=0.020, diffuse=0.100),
}

class FieldMap:
    def __init__(self, tilemap, baselines: dict[str, float] | None = None):
        self.tilemap = tilemap
        h, w = tilemap.h, tilemap.w
        self.fields: dict[str, np.ndarray] = {
            name: np.zeros((h, w), dtype=np.float32) for name in FIELD_CONFIG
        }
        self.tile_sources = {
            "mana_geo":  tilemap.source_field("mana_geo_src"),
            "mana_aqua": tilemap.source_field("mana_aqua_src"),
            "humidity":  tilemap.source_field("humidity_src"),
            "acidity":   tilemap.source_field("acidity_src"),
            "spore":     tilemap.source_field("spore_src"),
        }
        self.tile_sinks = {
            "mana_geo": tilemap.source_field("mana_geo_sink"),
            "humidity": tilemap.source_field("humidity_sink"),
            "acidity":  tilemap.source_field("acidity_sink"),
        }
        self.baselines = baselines or {}

    def step(self, dt: float):
        for name, cfg in FIELD_CONFIG.items():
            if cfg.is_special:
                continue
            f = self.fields[name]

            # 1. Apply tile source/sink
            if name in self.tile_sources:
                f += self.tile_sources[name] * dt
            if name in self.tile_sinks:
                f -= self.tile_sinks[name] * dt

            # 2. Decay toward baseline
            baseline = self.baselines.get(name, cfg.boundary_val)
            f += (baseline - f) * cfg.decay * dt

            # 3. Diffuse
            if cfg.diffuse > 0:
                kernel = self._kernel(cfg.diffuse)
                f[:] = ndi.convolve(f, kernel, mode=cfg.boundary_mode, cval=cfg.boundary_val)

            # 4. Clamp
            np.clip(f, cfg.clamp_lo, cfg.clamp_hi, out=f)

    @staticmethod
    def _kernel(rate: float) -> np.ndarray:
        # Mixing kernel: each tick, each tile gives `rate` of its value to neighbors
        # uniformly and keeps `1 - rate`. For numerical stability with explicit
        # forward-Euler diffusion on a 3x3 stencil, rate must stay below ~0.9.
        # See §3.6 for the full stability discussion.
        rate = min(rate, 0.9)
        e, c = rate / 8.0, 1.0 - rate
        return np.array([[e, e, e], [e, c, e], [e, e, e]], dtype=np.float32)

    def deposit(self, x: int, y: int, name: str, amount: float):
        self.fields[name][y, x] += amount

    def sample(self, x: int, y: int, name: str) -> float:
        return float(self.fields[name][y, x])

    def gradient(self, x: int, y: int, name: str) -> tuple[float, float]:
        f = self.fields[name]
        h, w = f.shape
        gy, gx = np.gradient(f[max(0,y-1):min(h,y+2), max(0,x-1):min(w,x+2)])
        return float(gx.mean()), float(gy.mean())
```

This is the entire field engine. ~80 lines of substance. Adding a new field is one `FIELD_CONFIG` entry and (optionally) source/sink columns in `TileProps`.

### 3.4 Boundary modes per field

Most fields use `mode="constant", cval=0.0` — fields go to zero outside the floor. Walls effectively absorb them. This is right for stigmergy (scent doesn't bounce off walls back at you) and for `mana_geo` (mana doesn't rebound from solid stone).

`temperature` and `humidity` use `mode="constant", cval=floor.baseline_temp` and similar — they're shaped by global floor conditions, not absent at boundaries. The baseline is set per-floor in the `FieldMap` constructor.

If we ever want `mana_aqua` to pool against walls instead of absorb (water physics), that's `mode="reflect"`. Not needed in v1.

### 3.5 Vectorization audit

Every per-tick code path **must** be vectorized. The audit checklist:

| Path | Op | Status |
|---|---|---|
| `TileMap.cache_derived` | one-time boolean-mask fill | ✓ vectorized |
| `FieldMap.step` per-field | `convolve` + element-wise | ✓ vectorized |
| `light_cast` per-source | `np.ogrid` + `np.where` | ✓ vectorized within source |
| `tremor_cast` (§4.6) | distance transform + mask | ✓ vectorized |
| `field_step` reactions | boolean masks | ✓ vectorized |
| `sense.step` per-organism | `KDTree.query_ball_point` | ✓ C-backed |
| `producer_seeding` | boolean mask + `rng.choice` | ✓ vectorized |

If you add a system, it goes in this table. If you can't make it vectorized and the per-tick cost is measurable, that's the trigger to revisit `numba` — not before.

### 3.6 Diffusion kernel stability

The v1 doc had a kernel of `[[r/9, r/9, r/9], [r/9, 1 - 8r/9, r/9], [r/9, r/9, r/9]]`. That kernel is correct (sums to 1) but goes negative for `r > 9/8 ≈ 1.125`, which silently produces non-physical oscillations.

v2 uses the cleaner mixing form: each tick, each tile gives away fraction `r` of its value, distributed uniformly over its 8 neighbors, and keeps `1 - r`. This is stable for any `r ∈ [0, 1]`, but practical values of `r > 0.9` start producing checkerboard artifacts on the explicit 3×3 stencil. Therefore:

- `_kernel` clamps `rate` to ≤ 0.9.
- The `diffuse` rate in `FIELD_CONFIG` represents *how much of a tile mixes per tick*, not a physical diffusion coefficient.
- Multiple convolution passes per tick are equivalent to a higher effective diffusion. If you want very fast diffusion, prefer 2 passes at `r=0.6` over 1 pass at `r=0.95`.

This is a small bug-fix vs. v1, not an architecture change.

---

## 4. Quiet v1 reactions

Inter-field reactions live in `sim/systems/field_step.py` and run **after** `FieldMap.step()` each tick. v1 ships only "quiet" reactions — diffusion, decay, decomposition, basic coupling. No combustion. No explosions. No flammability cascade.

Each reaction is 2–4 lines of boolean-masked numpy:

```python
# sim/systems/field_step.py
import numpy as np

def step(world, dt: float):
    f = world.field_map.fields

    # ----- R1: corpse decomposition -----
    decomp_mask = f["corpse"] > 0.05
    decomp_amt  = np.where(decomp_mask, f["corpse"] * 0.020 * dt, 0.0).astype(np.float32)
    f["acidity"]  += decomp_amt * 0.5
    f["mana_geo"] += decomp_amt * 0.3
    f["corpse"]   -= decomp_amt

    # ----- R2: mana_geo → mana_aether bleed -----
    f["mana_aether"] += f["mana_geo"] * 0.002 * dt

    # ----- R3: heat-driven evaporation -----
    hot_mask = f["temperature"] > 30.0
    f["humidity"][hot_mask] -= 0.015 * dt

    # ----- R4: cold-humid acidity (cave dew) -----
    dew_mask = (f["temperature"] < 8.0) & (f["humidity"] > 0.7)
    f["acidity"][dew_mask] += 0.001 * dt

    # ----- R5: re-clamp -----
    for name in ("mana_geo", "mana_aether", "humidity", "acidity", "corpse"):
        np.clip(f[name], 0.0, 1.0, out=f[name])
```

That's the complete v1 reaction set. Five reactions. ~25 lines of substance. Each a single-pass boolean-mask numpy op, runs in microseconds for a 60×40 grid.

These are the minimum needed to close the trophic loop and produce the dungeon-as-organism feel:

- **R1** — decomposition cycle. Corpses don't vanish; they feed the substrate.
- **R2** — what makes flying creatures viable on a stone-mana floor. The atmosphere bleeds enough mana from the rock to support them.
- **R3** — humid floors and hot floors look different. A fire-making creature would dry out a region.
- **R4** — flavor with consequences. Cold humid corners become slightly acidic, which is a niche.
- **R5** — keeps the system numerically clean.

### 4.1 Adding reactions later

Each new reaction is a numbered block in this function. Naming convention `# ----- Rn: short-name -----`. Document it in this file's reaction table. Don't add reactions speculatively.

| ID | Reaction | Status |
|---|---|---|
| R1 | corpse decomposition | v1 |
| R2 | mana_geo → mana_aether bleed | v1 |
| R3 | heat-driven evaporation | v1 |
| R4 | cold-humid dew → acidity | v1 |
| R5 | post-reaction clamp | v1 |
| — | mana combustion (heat × mana_aether → temperature spike) | v2+ |
| — | flammability + fire spread | v2+ |
| — | freezing (low temperature locks a tile, blocks fluid flow) | v2+ |
| — | acid corrosion (high acidity + organic corpse → dissolution) | v2+ |

### 4.6 Tremor field — the acoustic substrate

v1 of this doc had `echolocation` as a trait that "grants `tremorsense` channel range +150" but no `tremor` field for it to read from. v2 closes that loop.

`tremor` is a special (non-diffusing) field, recomputed each tick from instantaneous events: every `Locomote` action and every `Interact(attack)` deposits a tremor source at the actor's tile. Sound propagates from each source via a **weighted Dijkstra flood-fill** where the per-step cost is the destination tile's `sound_absorption`. The result is a tile-level intensity map that respects walls (which heavily absorb) and open chambers (which propagate further).

```python
# sim/systems/tremor_cast.py
import numpy as np
from heapq import heappush, heappop

def cast_tremor(world) -> np.ndarray:
    h, w = world.tilemap.h, world.tilemap.w
    absorption = world.tilemap.source_field("sound_absorption")
    tremor = np.zeros((h, w), dtype=np.float32)

    # Dijkstra from every event source, accumulating intensities
    for (y, x, intensity) in world.tremor_events_this_tick:
        # Single-source flood; intensity decays by `absorption[next]` per step
        visited = np.full((h, w), False)
        heap = [(-intensity, y, x)]   # max-heap via negation
        while heap:
            neg_i, cy, cx = heappop(heap)
            if visited[cy, cx]:
                continue
            visited[cy, cx] = True
            tremor[cy, cx] += -neg_i
            remaining = -neg_i - absorption[cy, cx]
            if remaining < 0.02:
                continue
            for dy, dx in ((-1,0),(1,0),(0,-1),(0,1)):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx]:
                    heappush(heap, (-remaining, ny, nx))

    world.tremor_events_this_tick.clear()
    return np.clip(tremor, 0.0, 1.0)
```

A 60×40 floor with ~30 events per tick floods in well under a millisecond. If profiling shows otherwise, switch to `scipy.sparse.csgraph.dijkstra` over a precomputed adjacency matrix — same algorithm, C-backed.

`echolocation` now has a real signal: organisms with the trait sample `tremor` at their tile and downstream within a radius, treating it the same way sighted organisms treat `light`-modulated sight. A blind cave creature in total darkness with `echolocation` is functionally equivalent to a sighted creature in moderate light.

This makes the `light < 0.10` darkness penalty in §5 mean something: it pushes design pressure toward non-visual sensing, and `tremor` is what those traits actually read.

---

## 5. Trait ↔ field interactions

Where biology meets metabolism. This table is the contract: every trait in `TRAIT_CODEX` must specify what fields it consumes, produces, or constrains. No silent dependencies.

| Trait | Consumes | Produces | Active condition | Effect when met |
|---|---|---|---|---|
| `photosynthesis` | `mana_geo` (0.04/sec at organism tile) | organism energy (+0.10/sec) | `light > 0.20` AND `mana_geo > 0.05` | gain energy |
| `carnivore` | `corpse` (via `Interact`) | — | `corpse > 0.10` at adjacent tile | `Interact` consumes 0.40 corpse, +0.30 energy |
| `acidic_touch` | — | `acidity` (+0.03 at attack target tile) | on successful `Interact(attack)` | small AoE acidity |
| `sweet_scent` | `mana_aether` (0.005/sec, tiny) | `sweet` (+0.30/sec at organism tile) | passive | emits lure |
| `camouflage` | — | — | `light < 0.40` | observers' `perception_range` × 0.5 vs this organism |
| `echolocation` | `tremor` (read-only) | — | passive | grants effective `perception_range` based on `tremor` at organism tile, independent of `light` |

### v1 environmental constraints on movement and metabolism

Beyond traits, the environment imposes universal rules on every organism:

| Condition | Effect |
|---|---|
| Tile `traction` | `Locomote` speed is multiplied by tile traction (sand and water slow you) |
| `temperature > 35°C` at organism tile | metabolism × 1.3 (faster drain) |
| `temperature < 0°C` at organism tile | speed × 0.6 (slowdown) |
| `acidity > 0.5` at organism tile | energy −0.05/sec unless trait `acid_resistance` (post-v1) |
| `light < 0.10` AND organism's `sight` is primary sense | `perception_range` × 0.4 |
| `mana_aether < 0.05` | flying-locomotion organisms (post-v1 trait) cannot `Locomote` |
| `Locomote` action | deposits `tremor` event at actor tile, intensity 0.15 |
| `Interact(attack)` action | deposits `tremor` event at actor tile, intensity 0.50 |

These are baked into the relevant systems (`metabolism.step`, `behavior.step` for sense modulation, `behavior.step` action handlers for tremor emission). They are not something the LLM can grant or revoke — they are universal physics.

### Adding a trait

Each new trait must populate this table before it ships. A trait with no field interactions is suspicious; either it's actually a passive stat modifier (which belongs in `Genome`, not `traits`), or its field interactions weren't thought through.

---

## 6. Producer placement (sessile biology)

Producers are placed by the environment, not authored. The placement rule fires once at floor generation and again at slow intervals (post-v1, for regrowth).

```python
# sim/systems/producer_seeding.py
import numpy as np

def seed_mana_moss(world, density: float = 0.15) -> int:
    """Place mana moss on tiles where field conditions support it."""
    f = world.field_map.fields
    tilemap = world.tilemap
    walls = tilemap.is_wall()
    candidate = (
        (f["mana_geo"] > 0.40)
        & (f["humidity"] > 0.30)
        & (~walls)
    )
    rng = world.rng
    candidates = np.argwhere(candidate)
    n = int(len(candidates) * density)
    if n == 0:
        return 0
    chosen = rng.choice(len(candidates), size=n, replace=False)
    for idx in chosen:
        y, x = candidates[idx]
        world.spawn_organism("mana_moss", (x, y))
    return n
```

Mana moss is an `Organism` with:
- `species_id = "mana_moss"`
- `trophic_level = 0`
- `traits = ["photosynthesis", "sweet_scent"]`
- base BT: a single behaviour that just executes `Rest` (sessile).
- `Genome.speed = 0`, `metabolism = 0.5`.

It eats `mana_geo` via the `photosynthesis` trait hook. It emits `sweet` via the `sweet_scent` trait hook. When it dies, it deposits `corpse` which decays into `mana_geo` via R1. Closed loop.

Other producers (`crystal_fungus`, `bone_lichen`) follow the same pattern with different placement rules. Not in v1.

### 6.5 Dijkstra goal maps for creature navigation

The stigmergy fields (`sweet`, `alarm`, `corpse`) are *diffusion* fields — they spread from sources and decay. They are good for "is there food nearby?" but bad for "what's the best path *to* the food, accounting for walls and hazards?"

For goal-directed navigation, we use **Dijkstra goal maps**: a flood-fill from a goal tile (or set of goal tiles) that gives every passable tile a distance value, optionally weighted by hazard fields. Creatures descend the gradient — implicit pathfinding without per-creature A*.

```python
# sim/systems/goal_map.py
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

def build_goal_map(world, goal_mask: np.ndarray, hazard_weights: dict[str, float] | None = None) -> np.ndarray:
    """Distance-from-goal for every passable tile, weighted by hazards.

    goal_mask: bool array, True at goal tiles.
    hazard_weights: e.g. {'acidity': 5.0, 'tremor': 2.0} adds field*weight to
                    the cost of stepping onto a tile.
    Returns a float32 array; np.inf for unreachable / impassable tiles.
    """
    h, w = world.tilemap.h, world.tilemap.w
    passable = ~world.tilemap.is_wall()
    base_cost = np.ones((h, w), dtype=np.float32)
    if hazard_weights:
        f = world.field_map.fields
        for fname, weight in hazard_weights.items():
            base_cost += weight * f[fname]
    base_cost[~passable] = np.inf

    # Build sparse 4-connected graph
    n = h * w
    rows, cols, data = [], [], []
    for dy, dx in ((-1,0),(1,0),(0,-1),(0,1)):
        # vectorized edge construction
        src_y, src_x = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
        dst_y, dst_x = src_y + dy, src_x + dx
        valid = (dst_y >= 0) & (dst_y < h) & (dst_x >= 0) & (dst_x < w)
        src = (src_y * w + src_x)[valid]
        dst = (dst_y * w + dst_x)[valid]
        cost = base_cost[dst_y[valid], dst_x[valid]]
        finite = np.isfinite(cost)
        rows.append(src[finite]); cols.append(dst[finite]); data.append(cost[finite])
    graph = csr_matrix((np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))

    # Multi-source Dijkstra from all goal tiles simultaneously
    sources = np.flatnonzero(goal_mask.ravel())
    dist = dijkstra(graph, indices=sources, min_only=True)
    return dist.reshape(h, w).astype(np.float32)
```

Standard uses on a typical floor:

| Goal | Hazard weights | Used by |
|---|---|---|
| `f["sweet"] > 0.05` | `{"alarm": 3.0}` | herbivore "find food, avoid danger" |
| `corpse_locations` | `{"tremor": 1.5}` | scavenger "find food, prefer quiet" |
| `f["alarm"] > 0.1`, *inverted* (descend = flee) | `{}` | prey flight response |
| `water_tiles` | `{}` | thirsty creatures |
| `home_nest_tile` | `{"acidity": 8.0}` | return-to-nest while avoiding acid |

Goal maps are built **on demand**, not every tick — they're cached and rebuilt only when their goal changes meaningfully (e.g., a moss patch dies, or alarm intensity crosses a threshold). For 60×40 floors, a single rebuild is ~2 ms with `scipy.sparse.csgraph.dijkstra`.

This is the standard roguelike pattern, formalized for our sim. Reference: [Brian Walker, "The Incredible Power of Dijkstra Maps"](http://www.roguebasin.com/index.php/The_Incredible_Power_of_Dijkstra_Maps).

The result: behaviors like "follow the sweet trail" become a one-line gradient descent on a precomputed map, not a per-tick A* call from each organism. This is what keeps `behavior.step` cheap as N grows.

---

## 7. Spatial indexing — `KDTree`

Built once per tick from organism positions. Used by every system that needs "what's near here."

```python
# sim/systems/spatial.py
from scipy.spatial import KDTree
import numpy as np

def step(world):
    if not world.organisms:
        world.kdtree = None
        return
    pos = np.array([o.pos for o in world.organisms], dtype=np.float32)
    world.kdtree = KDTree(pos)
    world.organism_ids_in_tree_order = [o.id for o in world.organisms]

def query_radius(world, pos, radius) -> list[int]:
    if world.kdtree is None:
        return []
    indices = world.kdtree.query_ball_point(pos, radius)
    return [world.organism_ids_in_tree_order[i] for i in indices]
```

Used by:
- `sense.step` — sight/smell/tremorsense queries.
- `population.step` — stress cluster detection.
- DungeonMaster spells with AoE.
- Death broadcast — alarm radius.

Rebuilt every tick. KDTree construction on N=200 points is ~0.5 ms on a laptop — far cheaper than the queries it enables.

**Do not attempt incremental KDTree updates.** scipy's KDTree is immutable. Use `cKDTree`-style rebuilds; they're plenty fast at our scale. If we ever exceed N=10,000, switch to a uniform spatial hash grid (which is also not premature optimization at that scale).

---

## 8. Architecture: systems-of-functions, not ECS (yet)

Each system is a module under `sim/systems/` with a `step(world, dt)` function. Systems are ordered explicitly. The world is the shared state; systems read and mutate it under a known protocol.

We do **not** adopt `esper` or `tcod-ecs` in v1. The full rationale lives in north-star §13's discussion; the operative rule is:

> Adopt `esper` (preferred) or `tcod-ecs` (if grid integration matters) when **any of the following** is true:
> 1. The `Organism.extensions` dict has more than 6 active keys and they're getting confused.
> 2. Multiple systems need the same filtered subset of organisms (e.g., "all flammable, wet, small organisms") and the filters are duplicated.
> 3. Organism count is sustained above 500 and per-frame iteration cost is measurable.
> 4. We want hot-reloadable systems for live tuning.
>
> Until then, plain functions over plain dataclasses. Component-shaped, framework-free.

Migration when triggered is mechanical because today's `Organism` is already component-shaped — `data` (genome), `pos`, `energy`, `stress`, `bt`, `extensions` map cleanly to ECS components.

### 8.1 Tick order

```python
# sim/tick.py
from sim.systems import (
    spatial, light_cast, tremor_cast, field_step, sense, behavior,
    metabolism, epigenome, population, reproduction, death,
)

def step(world, dt: float):
    spatial.step(world)             # 1. rebuild KDTree
    light_cast.step(world)          # 2. recompute light field via tcod FOV
    world.field_map.step(dt)        # 3. fields diffuse + decay
    tremor_cast.step(world)         # 4. propagate tremor events from prev tick
    field_step.step(world, dt)      # 5. inter-field reactions (R1..R5)
    sense.step(world)               # 6. cache sense results per organism
    behavior.step(world, dt)        # 7. py_trees tick; emits tremor events for next tick
    metabolism.step(world, dt)      # 8. energy drain, environmental modifiers
    epigenome.step(world, dt)       # 9. stress → epigenome multiplier shifts
    population.step(world, dt)      # 10. cluster scan + subtree injection
    reproduction.step(world, dt)    # 11. spawn offspring with drifted genome
    death.step(world)               # 12. handle deaths, deposit corpse field
    world.tick += 1
```

This order is load-bearing.

- **Spatial → light → fields → tremor → reactions → sense → behavior** is the read-side chain. Behavior reads the world fresh from this tick's senses, which read this tick's fields, which were diffused this tick from the previous tick's deposits.
- **Tremor is recomputed *before* sense** because echolocating organisms need this tick's tremor map. Tremor *events* are emitted by behavior (and queued for next tick); the tremor *field* shown at sense time is from the events queued at the end of the previous tick. This one-tick lag is intentional — it's how fast sound travels in our discretization, and it keeps the read/write phases cleanly separated.
- **Behavior → metabolism → epigenome** is the write-side chain on the organism.
- **Population → reproduction → death** is the lifecycle tail.

Changing this order without justification is a bug.

### 8.2 The world struct

```python
# sim/world.py
from dataclasses import dataclass, field
import numpy as np

@dataclass
class World:
    tick: int = 0
    rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng(0))

    # static
    floor_profile: "FloorProfile" = None
    tilemap: "TileMap" = None
    static_light_sources: list[tuple[int, int, float, float]] = field(default_factory=list)

    # dynamic
    field_map: "FieldMap" = None
    organisms: list["Organism"] = field(default_factory=list)
    kdtree = None
    organism_ids_in_tree_order: list[int] = field(default_factory=list)

    # per-tick event queues (cleared by their consumer)
    tremor_events_this_tick: list[tuple[int, int, float]] = field(default_factory=list)

    # caches reset each tick
    sense_cache: dict[int, "SenseResults"] = field(default_factory=dict)
    goal_map_cache: dict[str, np.ndarray] = field(default_factory=dict)

    # population manager state
    fast_lookup: dict[str, str] = field(default_factory=dict)
    pending_llm_signatures: set[str] = field(default_factory=set)
    cluster_history: list[dict] = field(default_factory=list)
```

Every system takes `world` and mutates it. No global state. Multiple worlds can coexist (useful for headless evolutionary runs).

---

## 9. `FloorProfile` — the procgen input

A `FloorProfile` is the design-time description of a floor. Generation reads a profile and produces a populated `World`. Profiles are JSON files under `data/floors/`.

```python
# sim/floor_profile.py
from pydantic import BaseModel, Field
from typing import Literal

class GeologicalFeature(BaseModel):
    type: Literal["crystal_node", "water_channel", "bone_deposit",
                  "mycelium_patch", "acid_pool", "sand_basin"]
    region:  Literal["NE", "NW", "SE", "SW", "C", "edge", "any"] = "any"
    size:    Literal["small", "medium", "large"] = "medium"
    count:   int = 1

class FloorProfile(BaseModel):
    name:                 str
    depth_index:          int = Field(ge=0)
    width:                int = 60
    height:               int = 40
    seed:                 int = 0

    base_temperature:     float = 12.0
    base_humidity:        float = 0.45
    base_mana_aether:     float = 0.10

    base_composition:     Literal["stone", "limestone", "bone"] = "limestone"
    bsp_max_room_size:    int = 12
    bsp_min_room_size:    int = 5

    # Naturalism control: which noise generator drives initial mana_geo / mana_aqua pockets.
    # 'simplex' = smooth gradients (v1 default).
    # 'worley'  = cellular pockets, more cave-like; requires pyfastnoiselite extra.
    pocket_noise:         Literal["simplex", "worley"] = "simplex"

    features:             list[GeologicalFeature] = []

    seed_producers:       list[str] = ["mana_moss"]
    initial_creatures:    dict[str, int] = {}

    # Mission graph (post-v1)
    mission_graph:        dict | None = None      # see §9.2

    # dungeon-master influence (post-v1)
    dm_influence_strength: float = 0.0
    dm_bias:               dict = {}
```

### 9.1 Floor 1 — "Shallow Delve"

The canonical v1 profile, used by the paper prototype:

```json
{
  "name": "Shallow Delve",
  "depth_index": 1,
  "width": 60,
  "height": 40,
  "seed": 1,
  "base_temperature": 12.0,
  "base_humidity": 0.45,
  "base_mana_aether": 0.10,
  "base_composition": "limestone",
  "bsp_max_room_size": 12,
  "bsp_min_room_size": 5,
  "pocket_noise": "simplex",
  "features": [
    {"type": "crystal_node",   "region": "NE", "size": "medium", "count": 1},
    {"type": "crystal_node",   "region": "SW", "size": "medium", "count": 1},
    {"type": "water_channel",  "region": "C",  "size": "medium", "count": 1},
    {"type": "mycelium_patch", "region": "SE", "size": "small",  "count": 1}
  ],
  "seed_producers": ["mana_moss"],
  "initial_creatures": {"slime": 8}
}
```

### 9.2 Mission graphs (post-v1, deferred but specified)

BSP gives us a tree of rooms. That's fine for shallow exploration but can't express **lock-and-key flow**: keyed doors, gates that require defeating a guardian, areas that gate behind a key found elsewhere. Once we want deeper floors with intentional traversal logic (Boss Keys-style design), we layer a **mission graph** on top of BSP.

```python
# sim/mission.py (post-v1 sketch)
import networkx as nx

def build_mission_graph(profile_spec: dict) -> nx.DiGraph:
    """
    Build a directed graph: nodes = abstract rooms, edges = traversal requirements.
    The generator then maps each abstract node onto a BSP room.
    """
    g = nx.DiGraph()
    g.add_node("entrance")
    g.add_node("key_room",  contains="key_A")
    g.add_node("locked",    requires="key_A")
    g.add_node("boss",      gates_via="locked")
    g.add_edge("entrance",  "key_room")
    g.add_edge("entrance",  "locked")     # visible but blocked
    g.add_edge("key_room",  "locked")
    g.add_edge("locked",    "boss")
    return g
```

Solvability validation is `nx.has_path(g, "entrance", "boss")` after pruning edges whose `requires` is not in the simulated player inventory at each step. The generator uses `nx.spring_layout` for prototyping placement, then a custom packer for production.

This is **not in v1**. We ship without it. But the schema field `mission_graph` reserves the slot so floor profiles can opt in later without migration. References: [Boris the Brave on lock-and-key dungeons](https://www.boristhebrave.com/2021/02/27/lock-and-key-dungeons/), Joris Dormans' cyclic generation.

---

## 10. Generation pipeline

```python
# sim/generation.py
import tcod
import opensimplex
import numpy as np

def generate_floor(profile: FloorProfile) -> World:
    rng = np.random.default_rng(profile.seed)
    opensimplex.seed(profile.seed)

    # 1. Skeleton: tcod BSP for rooms
    tilemap = TileMap(profile.width, profile.height)
    rooms = bsp_carve(tilemap, profile.bsp_min_room_size, profile.bsp_max_room_size, rng)
    connect_rooms(tilemap, rooms, rng)

    # 2. Substrate: assign tile compositions
    paint_base_composition(tilemap, profile.base_composition)
    for feature in profile.features:
        place_feature(tilemap, feature, rng)

    # 3. Cache static derived arrays (vectorized; see §2.3)
    tilemap.cache_derived()

    # 4. World scaffolding
    world = World(rng=rng, floor_profile=profile, tilemap=tilemap)
    world.field_map = FieldMap(tilemap, baselines={
        "temperature": profile.base_temperature,
        "humidity":    profile.base_humidity,
        "mana_aether": profile.base_mana_aether,
    })
    world.static_light_sources = collect_light_sources(tilemap)

    # 5. Seed initial fields with chosen noise
    seed_initial_fields(world, profile)

    # 6. Warm-up: 30s of field evolution with no creatures
    for _ in range(30):
        world.field_map.step(1.0)
        # field_step.step(world, 1.0)  # reactions

    # 7. Sessile biology
    for sp in profile.seed_producers:
        seed_producer(world, sp)

    # 8. Mobile biology
    for sp, n in profile.initial_creatures.items():
        for _ in range(n):
            spawn_creature(world, sp, random_passable_tile(world, rng))

    return world
```

### 10.1 Naturalistic noise — Simplex vs. Worley

```python
def seed_initial_fields(world, profile):
    w, h = world.tilemap.w, world.tilemap.h
    xs = np.arange(w) / 12.0
    ys = np.arange(h) / 12.0

    if profile.pocket_noise == "worley":
        try:
            from pyfastnoiselite.pyfastnoiselite import (
                FastNoiseLite, NoiseType, CellularDistanceFunction, CellularReturnType,
            )
            n = FastNoiseLite(seed=profile.seed)
            n.noise_type = NoiseType.NoiseType_Cellular
            n.cellular_distance_function = CellularDistanceFunction.CellularDistanceFunction_Euclidean
            n.cellular_return_type = CellularReturnType.CellularReturnType_Distance2Sub
            xx, yy = np.meshgrid(np.arange(w), np.arange(h), indexing="xy")
            mana_noise = np.vectorize(lambda x, y: n.get_noise(x * 1.2, y * 1.2))(xx, yy).astype(np.float32)
            mana_noise = (mana_noise + 1.0) / 2.0
        except ImportError:
            # Graceful fallback to simplex
            mana_noise = (opensimplex.noise2array(xs, ys).astype(np.float32) + 1.0) / 2.0
    else:
        mana_noise = (opensimplex.noise2array(xs, ys).astype(np.float32) + 1.0) / 2.0

    # Combine: tile sources concentrate mana near crystals; noise adds organic pockets
    world.field_map.fields["mana_geo"][:] = mana_noise * 0.10

    noise_h = opensimplex.noise2array(xs + 100, ys + 100).astype(np.float32)
    world.field_map.fields["humidity"][:] = np.clip(profile.base_humidity + noise_h * 0.10, 0, 1)
    world.field_map.fields["temperature"][:] = profile.base_temperature
    world.field_map.fields["mana_aether"][:] = profile.base_mana_aether
```

**Why Worley for mana.** Simplex noise produces smooth gradients — good for temperature and humidity, where the underlying physics actually is smooth. Worley (cellular) noise produces *clustered pockets* with sharp boundaries — closer to how mana is conceptually distributed in our dungeon (deposits, veins, hot spots). The visual difference is striking once you turn on the heatmap overlay: simplex gives you weather, Worley gives you geology. v1 default stays on simplex (zero added dependencies); profiles for deeper floors should opt into `"pocket_noise": "worley"`.

### 10.5 WFC tile painter (post-v1)

The current generator places features rule-based: `place_feature(tilemap, feature, rng)` looks at `feature.type` and stamps a hand-coded pattern (a crystal node = a small cluster of `WALL_CRYSTAL` and `FLOOR_CRYSTAL` in a roughly circular shape). This works fine for v1 and is fully deterministic. It does not produce surprising or hand-authored-feeling layouts.

When we want richer composition arrangements — limestone bands that respect a sedimentary feel, mycelium that grows along corridor walls but not into rooms, etc. — the right tool is **Wave Function Collapse**: define a small sample tile arrangement, and WFC generates new arrangements that respect the same adjacency rules.

This is a **post-v1 alternative painter**, opt-in per profile:

```python
# sim/wfc_painter.py (sketch)
def paint_via_wfc(tilemap, sample_path: str, rng):
    """Replace rule-based feature placement with WFC over a sample image."""
    # uses wfc-python or wfc_2019f; sample_path points to a small PNG/JSON
    # whose pixel-to-TileComp mapping is documented in data/wfc/<name>.toml
    ...
```

We don't ship this in v1 — we ship rule-based placement and the worked example in §11 assumes it. WFC is the right answer when rule-based becomes a bottleneck, and the integration point (the painter step in `generate_floor`) is already isolated. Reference implementation: [`mxgmn/WaveFunctionCollapse`](https://github.com/mxgmn/WaveFunctionCollapse); deep-dive tutorials at [Boris the Brave](https://www.boristhebrave.com/all-posts/).

---

## 11. Floor 1 worked example (post-generation)

After running `generate_floor(SHALLOW_DELVE_PROFILE)`:

**TileMap regions (60×40):**

- BSP yields ~10 rooms connected by corridors.
- Northeast 12×10 area: 2 walls + 6 floors of `WALL_CRYSTAL`/`FLOOR_CRYSTAL` clustered as a "node."
- Southwest 12×10 area: similar crystal cluster.
- Central horizontal band (y=18..21): 3-tile-wide `SHALLOW_WATER` channel cutting E to W.
- Southeast 6×6: small `FLOOR_MYCELIUM` patch.
- Everything else: `FLOOR_LIMESTONE` and `WALL_LIMESTONE`.

**After 30s warm-up (post step 6):**

- `mana_geo`: peaks near 0.85 at crystal node centers, decays radially to ~0.05 at floor edges. Mycelium patch shows a visible *depression* in mana_geo — mycelium tiles consume it.
- `mana_aether`: builds to ~0.18 floor-wide via R2 bleed; slightly higher (~0.25) over crystal clusters.
- `humidity`: 0.45 baseline. ~0.75 in the 5-tile band around the water channel; ~0.35 in dry pockets.
- `temperature`: uniform 12°C — no heat sources on this floor.
- `acidity`: near zero. Mycelium patch shows a tiny ~0.04 hotspot.
- `light`: 0.0 over most of the floor; ~0.30–0.45 near crystal clusters, falling off per tcod FOV.
- `tremor`: zero (no events yet).
- All stigmergy fields: zero.

**Producer seeding (step 7):**

Mana moss placement rule: `(mana_geo > 0.4) & (humidity > 0.3) & ~walls`.

- **SW crystal cluster**: high mana_geo and elevated humidity from water proximity → strong mask region, ~12 candidate tiles. At density 0.15, ~2 patches placed; at density 0.5, ~6.
- **NE crystal cluster**: marginal. High mana_geo but dry. Mask succeeds in ~3 tiles; possibly 1 patch.
- **Central water channel**: high humidity but low mana_geo. Mask fails.
- **Mycelium patch**: actively low mana_geo (consumed). Mask fails — correct: mycelium *competes* with mana moss.

Result: ~7 mana moss patches, asymmetrically distributed, concentrated near the SW crystal-water intersection. **The dungeon's geology authoring its own biology.** No human placed any moss.

**Creature spawning (step 8):**

8 slimes scattered randomly. They have no a priori knowledge of moss locations. They follow `sweet` gradients (which moss patches emit via `sweet_scent`) and converge on the SW region. Their `Locomote` actions deposit `tremor` events; a hypothetical echolocating predator on this floor would now have a signal to track.

By tick 200, the slime population is concentrated in the SW corner. Energy is balanced. Equilibrium holds.

This is what "Floor 1, t=0:00, equilibrium" in north-star §9.2 actually means — and why the equilibrium is meaningful rather than asserted.

---

## 12. Updates to `reference/north-star.md`

Once this spec is accepted, `docs/reference/north-star.md` needs the following edits.

**§3.5 (StateSnapshot):** add `tile_props` and the new fields to `EnvView`:

```python
class EnvView(BaseModel):
    floor:    int
    tile:     str
    traction: float
    light:    float
    tremor:   float
    fields:   dict[str, float]   # all twelve fields available, behavior reads what it cares about
```

The BT can `CheckEnv("tile.composition", "==", "FLOOR_CRYSTAL")` or `CheckEnv("fields.mana_geo", ">", 0.5)` or `CheckEnv("tremor", ">", 0.2)`.

**§7 (Stigmergy):** replace entirely with a one-paragraph cross-reference to this document. `StigmergyMap` no longer exists; it's a subset of `FieldMap`.

**§8 (Sprint roadmap):** Sprint 1 expands slightly: in addition to `OrganismData` + `Organism` + tick loop, build `TileMap`, `TileComp` enum, `TILE_PROPS`, and `FloorProfile` schema. Still ~250 lines, still headless, still pytest-asserted.

Sprint 3 (closed trophic loop) explicitly uses the producer-seeding rule from §6 of this doc rather than hardcoded moss positions.

Sprint 4 wires `FieldMap`, `field_step` reactions, `tcod` FOV light, **`tremor` cast**, **Dijkstra goal maps**, and `KDTree` spatial queries — and a pygame `surfarray` overlay for visualizing one field at a time. Sprint 4 gate becomes "field gradients visible, blind species behaves differently from sighted, scent-following works, heatmap shows mana_geo concentrated near crystal nodes, **echolocating species can find moving prey in darkness**."

**§9 (Paper prototype):** rewrite §9.1 setup to reference Floor 1 profile and the post-generation state from §11 of this doc. The trace itself doesn't change — equilibrium is now generated rather than asserted.

**§13 (Project layout):** update the tree:

```
sim/
├── tilemap.py             (TileComp, TileProps, TileMap, TILE_PROPS)
├── fields.py              (FieldConfig, FieldMap)
├── floor_profile.py       (FloorProfile, GeologicalFeature)
├── generation.py          (generate_floor + helpers)
├── mission.py             (post-v1: networkx mission graphs)
├── wfc_painter.py         (post-v1: WFC tile painter)
└── systems/
    ├── spatial.py         (KDTree rebuild)
    ├── light_cast.py      (tcod FOV)
    ├── tremor_cast.py     (Dijkstra acoustic flood)
    ├── goal_map.py        (Dijkstra goal maps for navigation)
    ├── field_step.py      (R1..R5 reactions)
    ├── sense.py
    ├── behavior.py
    ├── metabolism.py
    ├── epigenome.py
    ├── population.py
    ├── reproduction.py
    └── death.py
```

The `subtrees/` and `traits.py` and `verbs.py`/`conditions.py` and `tick.py` modules from north-star remain unchanged.

---

## 13. Sprint integration (ecosystem-first)

| Sprint | This spec adds |
|---|---|
| **0** | This document reviewed; `data/floors/shallow_delve.json` written by hand |
| **1** | `TileComp`, `TileProps`, `TILE_PROPS`, `TileMap`, `FloorProfile` schema. Static only. No fields yet. Pytest: load profile, build empty `TileMap`, assert composition counts |
| **2** | `FieldMap` core starts early: diffusion/decay/source/sink path validated with fixture tests. No creature runtime dependencies |
| **3** | Light/tremor integration, quiet reactions R1..R5, and telemetry hooks for field diagnostics |
| **4** | **Big sprint.** Generation pipeline (`generate_floor`), `seed_mana_moss`, profile-driven field seeding, KDTree support modules, and deterministic floor replay tests. Pygame `surfarray` overlay added (field-picker UI) |
| **5** | Ecology stabilization sprint: producer placement and spread tuned by field conditions; oscillation/collapse analysis and parameter hardening |
| **6** | Optional: Worley noise opt-in for naturalistic mana pockets on a "Crystal Caverns" profile; multi-floor substrate persistence begins |
| **7+** | Creature integration begins against stabilized environment APIs; mission graph layer (`networkx`) and WFC painter remain optional post-v1 layers |

Sprint 4 carries most of this document's complexity. That's correct — it's the sprint where the dungeon becomes visibly alive before creatures exist. Estimated 2–3 weekends for a solo dev. Budget for tuning the rate constants in §3.1 — they're first-pass and you'll discover the mana_geo decay is too fast or the humidity diffusion is too slow once you watch it run.

---

## 14. Open questions to answer before Sprint 4

1. **Tick rate for fields.** Diffusion at 1 Hz is fine. **Recommendation: keep unified at 1 Hz; revisit only if profiling shows >5ms in `field_map.step`.**
2. **Field heatmap colormaps** for the pygame overlay. **Recommendation: viridis default; magma for temperature; cubehelix for mana_geo; plasma for tremor.**
3. **Producer reproduction.** When does a moss patch spawn another? **Recommendation: when `energy > 0.9` AND a random adjacent tile satisfies the seed rule.**
4. **Boundary baselines for closed-system fields.** **Recommendation: 0 for v1.**
5. **Save/load of FieldMap.** Numpy `.npz` per floor, alongside the organism JSON snapshot. **Recommendation: yes; pydantic for organisms, `numpy.savez_compressed` for fields. If we ever go multi-floor with persistent state across hundreds of floors, switch to `zarr` for chunked lazy loading; not before.**
6. **Tremor event coalescing.** If 50 organisms move per tick, tremor cast runs 50 Dijkstras. **Recommendation: deduplicate events at the same tile, summing intensities. If profiling still shows >2ms, run one multi-source Dijkstra instead of N single-source ones.**
7. **Goal-map cache invalidation.** When does a cached goal map get rebuilt? **Recommendation: rebuild when (a) the goal mask changes by >5% of its tile count, or (b) >500 ticks since last rebuild. Cache keyed by `(goal_name, hazard_tuple)`.**
8. **Worley vs. Simplex default.** **Recommendation: ship simplex as v1 default; switch the canonical "Crystal Caverns" floor profile (Sprint 6+) to Worley to validate the integration.**

Defaults stand unless flagged. None block work before Sprint 4 begins.

---

## 15. The DungeonMaster boundary (post-v1, design constraint)

When the LLM-driven DungeonMaster comes online (post-v1), the architectural rule is:

> **The LLM never writes to `FieldMap.fields` or `TileMap.composition` directly.**
> The LLM emits structured *spell intents*; a deterministic `dm_spell.step(world, intent)` system applies them to the simulation.

This is the boundary-translator pattern: the LLM is a translator at the edges (player intent → spell intent, world state → narration), not a source of truth in the physics. Two reasons:

1. **Determinism.** The simulation must be reproducible from `(seed, profile, action_log)`. If the LLM mutates state, reproducibility dies.
2. **Stability.** Hallucinated mutations corrupt the field invariants R1..R5 depend on. Validating them in the boundary system is cheap; reasoning about LLM-induced corruption later is expensive.

Sketch of the architecture (post-v1, included here for forward compatibility):

```python
# sim/dm/intents.py
from pydantic import BaseModel

class SpellIntent(BaseModel):
    spell:   str
    target:  tuple[int, int]
    magnitude: float = 1.0
    # validated by dm_spell.step against a whitelist; rejected intents are logged

# sim/systems/dm_spell.py
def step(world, intent: SpellIntent):
    if intent.spell == "raise_temperature":
        x, y = intent.target
        world.field_map.fields["temperature"][y, x] += 5.0 * intent.magnitude
    elif intent.spell == "summon_corpse":
        ...
    else:
        world.dm_log.warn(f"unknown intent: {intent.spell}")
```

The LLM agent stack uses **LangGraph** (or equivalent state-machine framework over LLM calls) with separate nodes for:

- **Perception** — read structured slice of `world` around the focal area, produce `WorldDigest`.
- **Narration** — turn `WorldDigest` + recent action log into prose for the player.
- **Adjudication** — parse player input, validate, emit `SpellIntent` (or refuse).
- **World update** — `dm_spell.step(world, intent)` — deterministic, not LLM.

For local-only development, `ollama` is the recommended runtime; for hosted, OpenAI or Anthropic SDKs through `httpx` (already a dep). Long-running campaign memory uses a vector store (`chromadb` or `lancedb`) keyed by world tick + region.

This section is design guidance, not v1 scope. It exists so that when DM development starts, the seam is already cut in the right place.

---

## 16. Further reading

Curated references for the algorithms this spec leans on:

- **Dijkstra goal maps** — Brian Walker, ["The Incredible Power of Dijkstra Maps"](http://www.roguebasin.com/index.php/The_Incredible_Power_of_Dijkstra_Maps). The canonical writeup; everything in §6.5 derives from this.
- **Lock-and-key dungeons** — [Boris the Brave's deep-dive](https://www.boristhebrave.com/2021/02/27/lock-and-key-dungeons/), and Mark Brown's *Boss Keys* video series for the design intuition behind §9.2.
- **Wave Function Collapse** — [`mxgmn/WaveFunctionCollapse`](https://github.com/mxgmn/WaveFunctionCollapse) (the reference implementation) and [Boris the Brave's WFC tutorials](https://www.boristhebrave.com/all-posts/). Foundation for §10.5.
- **Roguelike dungeon algorithms catalog** — [`AtTheMatinee/dungeon-generation`](https://github.com/AtTheMatinee/dungeon-generation). BSP, drunkard's walk, cellular automata, Voronoi — every classical generator in one annotated file.
- **PCG Workshop paper database** — [pcgworkshop.com/database.php](https://www.pcgworkshop.com/database.php). For when "we should write a paper about this" stops being a joke.
- **Dwarf Fortress temperature model** — [DF wiki](https://dwarffortresswiki.org/index.php/DF2014:Temperature). Confirms our diffuse-toward-baseline approach matches the genre's prior art.
