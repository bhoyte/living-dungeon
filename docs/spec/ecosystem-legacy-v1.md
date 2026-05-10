# Dungeon Environment Specification (Legacy v1)

> Archived predecessor to `docs/spec/ecosystem-v2.md`.  
> Keep for rationale and historical tuning notes only.  
> Not authoritative for current implementation ordering.

> Previous note retained for historical context: this was the companion to `docs/reference/north-star.md` and proposed replacing parts of it.

---

## 0. Why this document exists

We caught ourselves doing what most LLM-gamedev projects do: obsessing over the agent and treating the world as a stage. In a Dungeon Meshi–style ecosystem the dungeon is not a stage. It is a metabolism. Creatures are expressions of it. Pull the dungeon out from under them and they stop making sense.

This document defines the dungeon's anatomy in four layers, in dependency order:

1. **Static substrate** — `TileMap`. The skeleton. Tile composition, walls, geometry. Doesn't change tick to tick.
2. **Dynamic fields** — `FieldMap`. The bloodstream. Eleven scalar fields evolving every tick: mana, temperature, humidity, acidity, light, scent.
3. **Sessile biology** — Producers (moss, fungi, root mats). Placed by field conditions. Slow growth and decay.
4. **Mobile biology** — Creatures. The `Organism` from north-star. The thing we used to start with, now correctly at the top of the stack.

Layers below do not know about layers above. A field doesn't know which creature is consuming it; it sees only a sink term in its tile. A tile doesn't know what fields depend on it; it just exposes a composition. This is the seam that keeps the system testable.

---

## 1. Stack additions

Three new dependencies on top of north-star §13:

| Package | Role |
|---|---|
| `tcod` | BSP/CA room generation; FOV/LOS for sight-based senses and light field |
| `opensimplex` | Noise-based seeding of initial field conditions |
| `scipy` | `ndimage.convolve` for diffusion; `spatial.KDTree` for radius queries |

`numba` and `taichi` stay out. `esper` and `tcod-ecs` stay out (see §8 for the explicit adoption trigger).

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

Reference table for what each composition does. Lives as a dict keyed by `TileComp`:

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
    TileComp.WALL_STONE:      TileProps(is_wall=True, is_passable=False, is_transparent=False, traction=0.0),
    TileComp.WALL_LIMESTONE:  TileProps(is_wall=True, is_passable=False, is_transparent=False, traction=0.0, acidity_sink=0.005),
    TileComp.WALL_CRYSTAL:    TileProps(is_wall=True, is_passable=False, is_transparent=False, traction=0.0, mana_geo_src=0.020, light_src=0.30),

    TileComp.FLOOR_STONE:     TileProps(),
    TileComp.FLOOR_LIMESTONE: TileProps(porosity=0.6, acidity_sink=0.008),
    TileComp.FLOOR_CRYSTAL:   TileProps(mana_geo_src=0.030, light_src=0.40),
    TileComp.FLOOR_WET_CLAY:  TileProps(porosity=0.85, humidity_src=0.010, traction=0.85),
    TileComp.FLOOR_SAND:      TileProps(porosity=0.20, traction=0.70, humidity_sink=0.012),
    TileComp.FLOOR_BONE:      TileProps(porosity=0.45, acidity_sink=0.004),
    TileComp.FLOOR_MYCELIUM:  TileProps(porosity=0.70, mana_geo_sink=0.010, spore_src=0.005, acidity_src=0.002),

    TileComp.SHALLOW_WATER:   TileProps(traction=0.6, mana_aqua_src=0.020, humidity_src=0.030, ceiling_height=3),
    TileComp.DEEP_WATER:      TileProps(is_passable=False, mana_aqua_src=0.040, humidity_src=0.040),
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

    def is_wall(self) -> np.ndarray:
        # bool mask, used by FieldMap for boundaries and tcod for FOV
        return np.array([[TILE_PROPS[TileComp(self.composition[y, x])].is_wall
                          for x in range(self.w)] for y in range(self.h)], dtype=bool)
        # NOTE: cache this. Recomputed only when composition changes (rare).

    def transparency(self) -> np.ndarray:
        # bool mask for tcod.map.compute_fov
        ...

    def source_field(self, attr: str) -> np.ndarray:
        """Return a (h, w) float32 array of TileProps[attr] per tile."""
        out = np.zeros((self.h, self.w), dtype=np.float32)
        for comp, props in TILE_PROPS.items():
            mask = self.composition == comp
            out[mask] = getattr(props, attr)
        return out
        # Computed once at floor generation, cached, used by FieldMap.step every tick.
```

The expensive bits (`is_wall`, `transparency`, every `source_field("mana_geo_src")` etc.) are computed once at generation and cached as numpy arrays. `FieldMap` reads the cached source/sink arrays each tick — zero per-tile Python.

---

## 3. Dynamic fields — `FieldMap`

The dungeon's metabolism. Eleven scalar fields, all `float32`, all on the same grid resolution (unified — no multi-resolution in v1). All updated each tick.

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
| 8 | `sweet` | stigmergy | `Emit("sweet")` | — | 0.050 | 0.150 | [0,1] | constant 0 |
| 9 | `alarm` | stigmergy | death events, attack events | — | 0.080 | 0.200 | [0,1] | constant 0 |
| 10 | `corpse` | stigmergy | death events | carnivore `Interact`, decomposition | 0.010 | 0.050 | [0,1] | constant 0 |
| 11 | `spore` | stigmergy | mycelium tiles, mature producer death | — | 0.020 | 0.100 | [0,1] | constant 0 |

The 7 geological fields evolve slowly and reach quasi-equilibrium. The 4 stigmergy fields are fast, creature-driven, and decay to zero quickly. Same data structure, different parameters.

### 3.2 Light is special

Every other field uses `scipy.ndimage.convolve` for diffusion. Light does not. Light is **recomputed each tick from sources via tcod FOV**, then attenuated by distance. This is correct because:

- Light doesn't diffuse around corners. It travels in straight lines until blocked by a wall.
- Walls fully occlude rather than partially diffuse.
- tcod's `compute_fov` is a single C call per source and is the right algorithm.

```python
# sim/systems/light_cast.py (sketch)
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
    # ...

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
    diffuse:       float        # 0 = none, ~0.2 = strong
    clamp_lo:      float = 0.0
    clamp_hi:      float = 1.0
    boundary_mode: str   = "constant"   # passed to scipy
    boundary_val:  float = 0.0
    is_special:    bool  = False        # True for light (skip generic step)

FIELD_CONFIG: dict[str, FieldConfig] = {
    "mana_geo":    FieldConfig(decay=0.001, diffuse=0.020),
    "mana_aether": FieldConfig(decay=0.005, diffuse=0.080),
    "mana_aqua":   FieldConfig(decay=0.003, diffuse=0.050),
    "temperature": FieldConfig(decay=0.010, diffuse=0.040, clamp_lo=-20, clamp_hi=60),  # boundary_val set per-floor
    "humidity":    FieldConfig(decay=0.008, diffuse=0.060),                              # boundary_val set per-floor
    "acidity":     FieldConfig(decay=0.005, diffuse=0.030),
    "light":       FieldConfig(decay=0.0,   diffuse=0.0, is_special=True),
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
        # Precompute source / sink fields (static) from tilemap
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
        # Per-floor baselines (e.g., humidity equilibrium)
        self.baselines = baselines or {}

    def step(self, dt: float):
        for name, cfg in FIELD_CONFIG.items():
            if cfg.is_special:
                continue                                     # light handled by light_cast
            f = self.fields[name]

            # 1. Apply tile source/sink (static contributions per tick)
            if name in self.tile_sources:
                f += self.tile_sources[name] * dt
            if name in self.tile_sinks:
                f -= self.tile_sinks[name] * dt

            # 2. Decay (toward baseline, default 0)
            baseline = self.baselines.get(name, cfg.boundary_val)
            f += (baseline - f) * cfg.decay * dt

            # 3. Diffuse (scipy convolution; gaussian approximation via uniform kernel
            #    weighted by diffuse rate; in practice we use a small fixed kernel)
            if cfg.diffuse > 0:
                kernel = self._kernel(cfg.diffuse)
                f[:] = ndi.convolve(f, kernel, mode=cfg.boundary_mode, cval=cfg.boundary_val)

            # 4. Clamp
            np.clip(f, cfg.clamp_lo, cfg.clamp_hi, out=f)

    @staticmethod
    def _kernel(rate: float) -> np.ndarray:
        # 3x3 kernel: center keeps (1 - rate*8/9), neighbors share rate
        e, c = rate / 9.0, 1.0 - rate * 8.0 / 9.0
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

---

## 4. Quiet v1 reactions

Inter-field reactions live in `sim/systems/field_step.py` and run **after** `FieldMap.step()` each tick. Per your call, v1 ships only "quiet" reactions — diffusion, decay, decomposition, basic coupling. No combustion. No explosions. No flammability cascade. Save the spicy stuff for v2 once the quiet system is stable.

Each reaction is 2–4 lines of boolean-masked numpy:

```python
# sim/systems/field_step.py
import numpy as np

def step(world, dt: float):
    f = world.field_map.fields

    # ----- R1: corpse decomposition -----
    # Decomposing corpses release acidity and a small amount of mana_geo back into the substrate.
    decomp_mask = f["corpse"] > 0.05
    decomp_amt  = np.where(decomp_mask, f["corpse"] * 0.020 * dt, 0.0).astype(np.float32)
    f["acidity"]  += decomp_amt * 0.5
    f["mana_geo"] += decomp_amt * 0.3
    f["corpse"]   -= decomp_amt

    # ----- R2: mana_geo → mana_aether bleed -----
    # The atmosphere always carries some fraction of the geological mana around it.
    f["mana_aether"] += f["mana_geo"] * 0.002 * dt

    # ----- R3: heat-driven evaporation -----
    # Above 30°C, humidity evaporates faster than it accumulates.
    hot_mask = f["temperature"] > 30.0
    f["humidity"][hot_mask] -= 0.015 * dt

    # ----- R4: cold-humid acidity (cave dew) -----
    # Cold humid pockets accumulate slight acidity from condensed minerals.
    dew_mask = (f["temperature"] < 8.0) & (f["humidity"] > 0.7)
    f["acidity"][dew_mask] += 0.001 * dt

    # ----- R5: re-clamp after reactions -----
    for name in ("mana_geo", "mana_aether", "humidity", "acidity", "corpse"):
        np.clip(f[name], 0.0, 1.0, out=f[name])
```

That's the complete v1 reaction set. Five reactions. 25 lines of substance. Each one a single-pass boolean-mask numpy op, runs in microseconds for a 60×40 grid.

These are the minimum needed to close the trophic loop and produce the dungeon-as-organism feel:

- **R1** is the decomposition cycle — corpses don't just vanish, they feed the substrate.
- **R2** is what makes flying creatures viable on a stone-mana floor — the atmosphere bleeds enough mana from the rock to support them.
- **R3** explains why humid floors and hot floors look different — and why a fire-making creature would dry out a region.
- **R4** is flavor with a real consequence: cold humid corners become slightly acidic, which is a niche.
- **R5** keeps the system numerically clean.

### Adding reactions later

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
| `echolocation` | — | — | passive | grants `tremorsense` channel range +150 |

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

These are baked into the relevant systems (`metabolism.step`, `behavior.step` for sense modulation). They are not something the LLM can grant or revoke — they are universal physics.

### Adding a trait

Each new trait must populate this table before it ships. A trait with no field interactions is suspicious; either it's actually a passive stat modifier (which belongs in `Genome`, not `traits`), or its field interactions weren't thought through.

---

## 6. Producer placement (sessile biology)

Producers are placed by the environment, not authored. The placement rule fires once at floor generation and again at slow intervals (post-v1, for regrowth).

```python
# sim/systems/producer_seeding.py
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
    # Sample density fraction of candidate tiles (random)
    rng = world.rng
    candidates = np.argwhere(candidate)
    n = int(len(candidates) * density)
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

It eats `mana_geo` via the `photosynthesis` trait hook. It emits `sweet` via the `sweet_scent` trait hook. When it dies (energy drops, or grazed to death), it deposits `corpse` which decays into `mana_geo` via R1. Closed loop.

Other producers (`crystal_fungus`, `bone_lichen`) follow the same pattern with different placement rules. Not in v1.

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

Rebuilt every tick because organisms move every tick. KDTree construction on N=200 points is ~0.5 ms on a laptop — far cheaper than the queries it enables.

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
    spatial, light_cast, field_step, sense, behavior,
    metabolism, epigenome, population, reproduction, death,
)

def step(world, dt: float):
    spatial.step(world)         # 1. rebuild KDTree
    light_cast.step(world)      # 2. recompute light field via tcod FOV
    world.field_map.step(dt)    # 3. fields diffuse + decay (FieldMap.step)
    field_step.step(world, dt)  # 4. inter-field reactions (R1..R5)
    sense.step(world)           # 5. cache sense results per organism
    behavior.step(world, dt)    # 6. py_trees tick per organism
    metabolism.step(world, dt)  # 7. energy drain, environmental modifiers
    epigenome.step(world, dt)   # 8. stress → epigenome multiplier shifts
    population.step(world, dt)  # 9. cluster scan + subtree injection (every N ticks)
    reproduction.step(world, dt)# 10. spawn offspring with drifted genome
    death.step(world)           # 11. handle deaths, deposit corpse field
    world.tick += 1
```

This order is load-bearing. In particular:

- **Spatial → light → fields → sense → behavior** is the read-side chain. Behavior reads the world fresh from this tick's senses, which read this tick's fields, which were diffused this tick from the previous tick's deposits. No stale reads.
- **Behavior → metabolism → epigenome** is the write-side chain on the organism. Behavior may set `Locomote` actions which `metabolism` charges energy for; `epigenome` reads the resulting stress.
- **Population → reproduction → death** is the lifecycle tail. Population runs the slow LLM/cache pipeline; reproduction reads outcomes; death cleans up.

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

    # caches reset each tick
    sense_cache: dict[int, "SenseResults"] = field(default_factory=dict)

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
    # placement hints; concrete geometry chosen by the generator
    region:  Literal["NE", "NW", "SE", "SW", "C", "edge", "any"] = "any"
    size:    Literal["small", "medium", "large"] = "medium"
    count:   int = 1

class FloorProfile(BaseModel):
    name:                 str
    depth_index:          int = Field(ge=0)
    width:                int = 60
    height:               int = 40
    seed:                 int = 0

    base_temperature:     float = 12.0      # °C
    base_humidity:        float = 0.45      # 0..1
    base_mana_aether:     float = 0.10      # 0..1 atmospheric mana floor

    base_composition:     Literal["stone", "limestone", "bone"] = "limestone"
    bsp_max_room_size:    int = 12
    bsp_min_room_size:    int = 5

    features:             list[GeologicalFeature] = []

    # post-generation hooks
    seed_producers:       list[str] = ["mana_moss"]
    initial_creatures:    dict[str, int] = {}    # species_id -> count

    # dungeon-master influence (post-v1 — unused in Sprint 1 runs but already in schema)
    dm_influence_strength: float = 0.0
    dm_bias:               dict = {}              # e.g. {"prefer_predators": 0.3}
```

### Floor 1 — "Shallow Delve"

The v1 profile, used by the paper prototype:

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

    # 1. Skeleton: tcod BSP for rooms, carve walls/floors
    tilemap = TileMap(profile.width, profile.height)
    rooms = bsp_carve(tilemap, profile.bsp_min_room_size, profile.bsp_max_room_size, rng)
    connect_rooms(tilemap, rooms, rng)

    # 2. Substrate: assign tile compositions
    paint_base_composition(tilemap, profile.base_composition)
    for feature in profile.features:
        place_feature(tilemap, feature, rng)         # crystal_node → WALL_CRYSTAL/FLOOR_CRYSTAL cluster, etc.

    # 3. Cache static derived arrays
    tilemap.cache_derived()                          # is_wall, transparency, source/sink fields

    # 4. World scaffolding
    world = World(rng=rng, floor_profile=profile, tilemap=tilemap)
    world.field_map = FieldMap(tilemap, baselines={
        "temperature": profile.base_temperature,
        "humidity":    profile.base_humidity,
        "mana_aether": profile.base_mana_aether,
    })
    world.static_light_sources = collect_light_sources(tilemap)

    # 5. Seed initial fields with opensimplex variation (pockets, gradients, naturalism)
    seed_initial_fields(world, profile)

    # 6. Warm-up: run 30 simulated seconds with no creatures so fields reach quasi-equilibrium
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


def seed_initial_fields(world, profile):
    w, h = world.tilemap.w, world.tilemap.h
    xs = np.arange(w) / 12.0
    ys = np.arange(h) / 12.0

    # mana_geo: noise-scaled around tile sources (the static source field already concentrates near crystals;
    # noise adds organic-feeling variation on top)
    noise = opensimplex.noise2array(xs, ys).astype(np.float32)
    base_mana = (noise + 1.0) / 2.0 * 0.10
    world.field_map.fields["mana_geo"][:] = base_mana

    # humidity: biased toward profile.base_humidity, varied by noise
    noise_h = opensimplex.noise2array(xs + 100, ys + 100).astype(np.float32)
    world.field_map.fields["humidity"][:] = np.clip(profile.base_humidity + noise_h * 0.10, 0, 1)

    # temperature: starts uniform at baseline; tile sources will modulate over warm-up
    world.field_map.fields["temperature"][:] = profile.base_temperature

    # mana_aether: starts uniform low; will be filled by R2 during warm-up
    world.field_map.fields["mana_aether"][:] = profile.base_mana_aether
```

Each helper (`bsp_carve`, `connect_rooms`, `paint_base_composition`, `place_feature`, `collect_light_sources`, `seed_producer`, `spawn_creature`, `random_passable_tile`) is a small named function, ~10–40 lines each. Total generation pipeline is ~400 lines. Manageable for one developer and a weekend.

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

- `mana_geo` field: peaks near 0.85 at crystal node centers, decays radially to ~0.05 at floor edges. Mycelium patch shows a visible *depression* in mana_geo because mycelium tiles consume it.
- `mana_aether`: builds to ~0.18 floor-wide due to R2 bleed; slightly higher (~0.25) over crystal clusters.
- `humidity`: 0.45 baseline. Climbs to ~0.75 in the 5-tile band around the water channel; drops to ~0.35 in a small dry pocket created by a stray sand tile (if any).
- `temperature`: uniform 12°C — no heat sources on this floor.
- `acidity`: near zero. The mycelium patch shows a tiny ~0.04 hotspot from `acidity_src`.
- `light`: 0.0 over most of the floor; ~0.30–0.45 near crystal clusters, falling off with distance per tcod FOV.
- All stigmergy fields: zero.

**Producer seeding (step 7):**

Mana moss placement rule: `(mana_geo > 0.4) & (humidity > 0.3) & ~walls`. Where does that AND-mask succeed?
- **Around the SW crystal cluster**: yes — high mana_geo, and the SW area is near the water channel so humidity is elevated. Strong mask region, ~12 candidate tiles. At density 0.15, ~2 patches placed (rounded) in v1 — but bumping density to 0.5 or seeding a "small" patch type per candidate gives ~6 patches.
- **Around the NE crystal cluster**: marginal. High mana_geo but the NE area is dry (humidity ~0.4–0.5). Mask succeeds in maybe 3 tiles, possibly 1 patch placed.
- **Central water channel**: very high humidity but mana_geo is low away from crystal nodes. Mask fails.
- **Mycelium patch**: actively low mana_geo. Mask fails (correct — mycelium *competes* with mana moss for substrate).

Result: ~7 mana moss patches, asymmetrically distributed, concentrated near the SW crystal-water intersection. **This is the dungeon's geology authoring its own biology.** No human placed any moss.

**Creature spawning (step 8):**

8 slimes scattered randomly across passable tiles. They have no a priori knowledge of where moss is. They wander, follow `sweet` gradients (which moss patches now emit per the `sweet_scent` trait), and converge on the SW region.

By tick 200, the slime population is concentrated in the SW corner. Energy is balanced. Equilibrium holds.

This is what "Floor 1, t=0:00, equilibrium" in north-star §9.2 actually means now — and why the equilibrium is meaningful rather than asserted.

---

## 12. Updates to `reference/north-star.md`

Once this spec is accepted, `docs/reference/north-star.md` needs the following edits. None of them are large.

**§3.5 (StateSnapshot):** add `tile_props` to `EnvView`:

```python
class EnvView(BaseModel):
    floor:    int
    tile:     str               # composition enum name
    traction: float
    light:    float
    fields:   dict[str, float]  # {"mana_geo": 0.62, "humidity": 0.71, "acidity": 0.03, ...}
```

The BT can `CheckEnv("tile.composition", "==", "FLOOR_CRYSTAL")` or `CheckEnv("fields.mana_geo", ">", 0.5)`.

**§7 (Stigmergy):** replace entirely with a one-paragraph cross-reference to this document. `StigmergyMap` no longer exists; it's a subset of `FieldMap`.

**§8 (Sprint roadmap):** Sprint 1 expands very slightly: in addition to `OrganismData` + `Organism` + tick loop, build `TileMap`, `TileComp` enum, `TILE_PROPS`, and `FloorProfile` schema. Still ~250 lines, still headless, still pytest-asserted.

Sprint 3 (closed trophic loop) explicitly uses the producer-seeding rule from §6 of this doc rather than hardcoded moss positions. The "energy in = energy out within 5%" assertion now traces through the field-mediated metabolism.

Sprint 4 wires `FieldMap`, `field_step` reactions, `tcod` FOV light, and `KDTree` spatial queries — and a pygame `surfarray` overlay for visualizing one field at a time. Sprint 4 gate becomes "field gradients visible, blind species behaves differently from sighted, scent-following works, heatmap shows mana_geo concentrated near crystal nodes."

**§9 (Paper prototype):** rewrite §9.1 setup: instead of "12 Mana Moss patches at static positions," reference Floor 1 profile and the post-generation state from §11 of this doc. The trace itself doesn't change — it's just that the equilibrium it starts from is now generated rather than asserted.

**§13 (Project layout):** update the tree:

```
sim/
├── tilemap.py             (TileComp, TileProps, TileMap, TILE_PROPS)
├── fields.py              (FieldConfig, FieldMap)
├── floor_profile.py       (FloorProfile, GeologicalFeature)
├── generation.py          (generate_floor + helpers)
└── systems/
    ├── spatial.py         (KDTree rebuild)
    ├── light_cast.py      (tcod FOV)
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

## 13. Sprint integration

Where does each piece of this spec land in the existing roadmap?

| Sprint | This spec adds |
|---|---|
| **0** | This document reviewed; `data/floors/shallow_delve.json` written by hand |
| **1** | `TileComp`, `TileProps`, `TILE_PROPS`, `TileMap`, `FloorProfile` schema. Static only. No fields yet. Pytest: load profile, build empty `TileMap`, assert composition counts |
| **2** | Single producer (mana_moss) + verbs/conditions on a hardcoded floor. No field engine yet — moss is hand-placed, photosynthesis just adds energy at a flat rate. Trade-off: defer fields to Sprint 4 to keep Sprint 2's gate small |
| **3** | Closed loop on hardcoded floor. Corpses → mana via a placeholder rule (no FieldMap yet) |
| **4** | **Big sprint.** `FieldMap` (all 11 fields), reactions R1..R5, tcod light, KDTree, generation pipeline (`generate_floor`), `seed_mana_moss`. Floor 1 worked example becomes the test. Pygame `surfarray` overlay added. Trait↔field hooks (photosynthesis, sweet_scent) wired |
| **5** | Stress + epigenome integrate cleanly; environmental constraints on metabolism (heat, cold, acidity) come online here |
| **6+** | Unchanged from north-star |

Sprint 4 carries most of this document's complexity. That's correct — it's the sprint where the dungeon becomes alive. Everything before is scaffolding; everything after is biology compounding on top of an already-living substrate.

Sprint 4 is the sprint to be most careful about. Estimated 2–3 weekends for a solo dev, mostly because the Floor 1 worked example needs to actually reproduce as described. Budget for tuning the rate constants in §3.1 — they're first-pass and you'll discover the mana_geo decay is too fast or the humidity diffusion is too slow once you watch it run.

---

## 14. Open questions to answer before Sprint 4

1. **Tick rate for fields.** Diffusion at 1 Hz is fine. But do we want geological fields (mana, temperature, humidity) on a slower clock (e.g., every 4th tick) for performance? **Recommendation: no, keep unified at 1 Hz; revisit only if profiling shows >5ms in `field_map.step`.**
2. **Field heatmap colormaps** for the pygame overlay. Pick a default and a per-field override. **Recommendation: viridis default; magma for temperature; cubehelix for mana_geo.**
3. **Producer reproduction.** When does a moss patch spawn another? On energy threshold? On contact with a sufficiently high-mana_geo neighbor tile? **Recommendation: when `energy > 0.9` AND a random adjacent tile satisfies the seed rule. Spawn a child with drifted genome.**
4. **Boundary baselines for closed-system fields.** `mana_geo` boundary 0 means corners of the floor are mana-zero. Is that right or should it tend toward a global baseline? **Recommendation: 0 for v1. The floor isn't supposed to be uniform.**
5. **Save/load of FieldMap.** Numpy `.npz` per floor, alongside the organism JSON snapshot. **Recommendation: yes; pydantic for organisms, numpy savez for fields.**

Defaults stand unless you flag one. None block work before Sprint 4 begins.
