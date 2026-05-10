# Dungeon Environment Addendum (Phase-3+ Options)

> Companion to `docs/spec/ecosystem-v2.md` as a future-options catalog.  
> This document is intentionally non-normative during ecosystem-first phase-1 and creature phase-2. It collects tools and concepts for later adoption when baseline systems are stable.
>
> Treat this as a menu, not a roadmap. Each section ends with an "**Adopt when**" rule so you can pick what's actually needed and skip what isn't. Adopting all of this at once would be a different (and probably worse) project; adopting the right two or three at the right moment is the goal.

---

## Table of Contents

1. [Architecture pivots](#1-architecture-pivots)
   - 1.1 [`esper` — ECS for Python](#11-esper--ecs-for-python)
   - 1.2 [`tcod-ecs` — ECS with grid integration](#12-tcod-ecs--ecs-with-grid-integration)
   - 1.3 [`mesa` — agent-based modeling framework](#13-mesa--agent-based-modeling-framework)
   - 1.4 [`Griddly` — high-performance grid-world engine](#14-griddly--high-performance-grid-world-engine)
2. [Performance ceiling-raisers](#2-performance-ceiling-raisers)
   - 2.1 [`numba` — JIT for the hot path](#21-numba--jit-for-the-hot-path)
   - 2.2 [`taichi` — GPU-parallel fields](#22-taichi--gpu-parallel-fields)
   - 2.3 [`cython` and `nim` — when JIT isn't enough](#23-cython-and-nim--when-jit-isnt-enough)
   - 2.4 [Storage: `zarr`, `hdf5`, `msgpack`](#24-storage-zarr-hdf5-msgpack)
3. [The "loud" simulation reactions](#3-the-loud-simulation-reactions)
   - 3.1 [Combustion, freezing, corrosion](#31-combustion-freezing-corrosion)
   - 3.2 [Falling-sand particle physics](#32-falling-sand-particle-physics)
   - 3.3 [`cellpylib` and bespoke CA](#33-cellpylib-and-bespoke-ca)
   - 3.4 [Differentiable physics with `difftaichi`](#34-differentiable-physics-with-difftaichi)
4. [Generation beyond BSP](#4-generation-beyond-bsp)
   - 4.1 [Wave Function Collapse — full integration](#41-wave-function-collapse--full-integration)
   - 4.2 [Voronoi + Lloyd relaxation regions](#42-voronoi--lloyd-relaxation-regions)
   - 4.3 [Constraint-based generation: ASP / SAT / SMT](#43-constraint-based-generation-asp--sat--smt)
   - 4.4 [Cyclic and graph-grammar dungeons](#44-cyclic-and-graph-grammar-dungeons)
5. [ML-driven generation and AI](#5-ml-driven-generation-and-ai)
   - 5.1 [`gym-pcgrl` — generator as RL agent](#51-gym-pcgrl--generator-as-rl-agent)
   - 5.2 [`pyribs` / MAP-Elites — quality diversity](#52-pyribs--map-elites--quality-diversity)
   - 5.3 [Diffusion / GAN dungeons](#53-diffusion--gan-dungeons)
   - 5.4 [Trained creature AI: `stable-baselines3`, `RLlib`, PettingZoo](#54-trained-creature-ai-stable-baselines3-rllib-pettingzoo)
6. [Decision-making beyond behavior trees](#6-decision-making-beyond-behavior-trees)
   - 6.1 [GOAP — Goal-Oriented Action Planning](#61-goap--goal-oriented-action-planning)
   - 6.2 [Utility AI](#62-utility-ai)
   - 6.3 [HTN — Hierarchical Task Networks](#63-htn--hierarchical-task-networks)
   - 6.4 [Hybrid: BT root + GOAP/Utility leaves](#64-hybrid-bt-root--goaputility-leaves)
7. [Multi-floor, Z-axis, and large-world architecture](#7-multi-floor-z-axis-and-large-world-architecture)
8. [LLM agent stacks for the DungeonMaster](#8-llm-agent-stacks-for-the-dungeonmaster)
9. [Open-source dungeon AI projects worth studying](#9-open-source-dungeon-ai-projects-worth-studying)
10. [Adoption roadmap — the menu, ordered](#10-adoption-roadmap--the-menu-ordered)
11. [Further reading](#11-further-reading)

---

## 1. Architecture pivots

These are the framework-level alternatives to "systems-of-functions over a `World` dataclass." Pick at most one of {esper, tcod-ecs, mesa, Griddly} — they overlap.

### 1.1 `esper` — ECS for Python

```bash
pip install esper
```

[`benmoran56/esper`](https://github.com/benmoran56/esper) is the lightweight, MIT-licensed, performance-focused ECS used by most modern Python roguelikes. Components are dataclasses; systems are classes with a `process()` method that iterates over entities matching a component signature.

**What you gain:**
- Sparse, queryable entity state. "All organisms with `Flammable` and `Wet` components" is a single `world.get_components(Flammable, Wet)` call.
- Trivial component composition. Adding a `Bioluminescent` component to one organism doesn't bloat the others.
- A migration path that's mechanical from your current `Organism` design — `data` (genome), `pos`, `energy`, `stress`, `bt`, `extensions` map cleanly to components.

**What it costs:**
- A real refactor. Every system that currently iterates `world.organisms` becomes a component query.
- A small per-query overhead (microseconds) — irrelevant unless N > 5000.
- Discipline: components must stay data-only. Logic in components is the path back to "fat object" hell.

**Sketch:**
```python
import esper
from dataclasses import dataclass

@dataclass
class Position: x: int; y: int
@dataclass
class Energy: value: float; max: float
@dataclass
class Photosynthesizer: rate: float
@dataclass
class TempSensitive: comfort_min: float; comfort_max: float

class PhotosynthesisSystem(esper.Processor):
    def process(self, dt: float, field_map):
        for ent, (pos, energy, photo) in self.world.get_components(Position, Energy, Photosynthesizer):
            light = field_map.fields["light"][pos.y, pos.x]
            mana  = field_map.fields["mana_geo"][pos.y, pos.x]
            if light > 0.20 and mana > 0.05:
                drain = min(photo.rate * dt, mana)
                field_map.fields["mana_geo"][pos.y, pos.x] -= drain
                energy.value = min(energy.max, energy.value + drain * 2.5)
```

**Adopt when:** organism count is sustained above ~500 and `behavior.step` shows up in your profiler, OR you find yourself filtering `world.organisms` with the same predicate in three or more systems.

### 1.2 `tcod-ecs` — ECS with grid integration

`tcod-ecs` is a different ECS with first-class spatial queries (entities-at-tile, entities-in-radius) baked in. If your sim is fundamentally grid-shaped — and yours is — `tcod-ecs` saves you from maintaining a separate `KDTree` for spatial lookups.

**Trade-off vs. `esper`:** smaller community, narrower API, but tighter integration with the rest of the `tcod` stack you already use.

**Adopt when:** you've decided to ECS-ify, *and* most of your queries are spatial ("things in this tile / radius") rather than archetype ("all flying carnivores").

### 1.3 `mesa` — agent-based modeling framework

```bash
pip install mesa
```

[Mesa 3.4](https://www.reddit.com/r/Python/comments/1puriem/mesa_340_agentbased_modeling_now_with_universal/) (Dec 2025) added universal space and reactive observables. It's an entire ABM framework: agent scheduling, data collection, browser-based visualization, statistical analysis, n-dimensional spaces.

**This is a different category of tool than ECS.** ECS is an architecture. Mesa is a *research framework* for studying emergent behavior. Use Mesa when you want to:
- Run thousands of headless evolutionary experiments and produce statistical reports.
- Visualize population dynamics, food webs, faction wars in a browser without writing visualization code.
- Compare runs systematically (parameter sweeps, calibration).

**What it costs:**
- Heavyweight. Mesa wants to own the simulation loop.
- Less control than rolling your own. The schedulers and data-collectors do a lot for you, which is great until you need them to do something different.

**Adopt when:** you need to *publish results about* the dungeon, not just run it. If you ever say "I want to know whether trait X causes population bottlenecks under conditions Y across 1000 seeds," that's Mesa.

### 1.4 `Griddly` — high-performance grid-world engine

[Griddly docs](https://griddly.readthedocs.io). C++-backed grid-world engine with Gym/PettingZoo/RLlib bindings. Levels and rules defined in a YAML-based "GDY" format. Scales to thousands of agents at hundreds of frames per second.

**This is the right tool if** your endgame is RL-trained creatures or training a generator-as-agent (PCGRL — see §5.1) at scale. For a hand-crafted simulation it's overkill — you'd be fighting the YAML to express things your Python would say more naturally.

**Adopt when:** you're committed to RL as the primary AI substrate and need performance Python can't reach.

---

## 2. Performance ceiling-raisers

The base spec stays vectorized in NumPy and is fast enough for 60×40 floors with N ≤ 200. These are the levers when that stops being true.

### 2.1 `numba` — JIT for the hot path

```bash
pip install numba
```

`@njit(parallel=True, fastmath=True)` typically delivers 10–100× speedups on tight numerical loops that NumPy can't vectorize cleanly. The canonical case is **cellular automata with neighbor lookups** — falling-sand updates, Conway-style rules, anything where every cell reads its 8 neighbors and decides what to do. NumPy fancy-indexing those is awkward; numba just compiles the obvious double-loop to native code.

**Important caveat:** numba's [own docs warn](https://stackoverflow.com/questions/70311592/numba-np-convolve-really-slow) that wrapping `np.convolve` or other already-optimized NumPy calls in `@njit` can be *slower*, not faster. Numba helps where NumPy can't, not where NumPy already shines.

**Practical performance hierarchy for our sim:**

| Operation | Best tool | Why |
|---|---|---|
| Field diffusion (3×3 convolution over whole grid) | `scipy.ndimage.convolve` | already C-backed |
| Per-tile boolean masks | NumPy | already C-backed |
| Cellular automata with state-dependent neighbor rules | `numba` `@njit(parallel=True)` | NumPy can't express it cleanly |
| Falling-sand multi-pass updates | `numba` or `taichi` | per-cell branching logic |
| KDTree queries | `scipy.spatial.cKDTree` | already C-backed |
| Dijkstra goal maps on 60×40 | `scipy.sparse.csgraph.dijkstra` | already C-backed |
| Dijkstra goal maps on 500×500 | `numba` with priority queue | scipy starts to feel it |

**Adopt when:** profiling shows a Python-level loop in the hot path that you can't vectorize.

### 2.2 `taichi` — GPU-parallel fields

```bash
pip install taichi
```

Taichi is a Python-embedded DSL that compiles to GPU (or CPU SIMD) kernels. The mental model is "Halide for numerical Python" — you write `@ti.kernel` functions, taichi parallelizes them across thread blocks. The [Fields tutorial](https://docs.taichi-lang.org/docs/field) shows a 640×480 grid filled in a single parallel kernel.

**The killer use cases for our sim:**
- **Realistic fluid simulation.** Stable-fluids on a 500×500 grid runs at 60+ FPS on a mid-tier GPU. SciPy convolutions cap out around 200×200 at 30 FPS.
- **Heat diffusion at high resolution.** Same story — taichi turns "I can't afford to run this every tick" into "this is free."
- **Falling-sand at scale.** Noita-grade material physics on a full screen.

**The catch:** taichi kernels can't call most Python. Data has to flow through `ti.field` and `ti.Vector.field` structures. You're writing in a sublanguage. The integration boundary with your Python sim is the work.

**Adopt when:** you decide fields should be 500×500+ and updated at >30 FPS, OR you commit to a real falling-sand layer.

### 2.3 `cython` and `nim` — when JIT isn't enough

If you have a single hot function and you need bare-metal speed without taichi's DSL constraints, `cython` (compile-time annotated Python) and Nim's `nimporter` (write Nim, import from Python) are both options. Niche; skip unless you have a specific bottleneck JIT can't crack.

### 2.4 Storage: `zarr`, `hdf5`, `msgpack`

The base spec uses `numpy.savez_compressed` per floor. That's fine to a point.

| Format | When to use |
|---|---|
| `pickle` | Quick prototypes, single-machine, single-Python-version |
| `numpy.savez_compressed` | Field state for one floor; the v1 default |
| `zarr` | Multi-floor persistent worlds with chunked, lazy loading. Edit one chunk without rewriting the file. The right answer for "100 floors, each 200×200×12 channels, evolving over real time" |
| `h5py` / HDF5 | Same niche as zarr, more mature, less Python-native |
| `msgpack` | Cross-language interop (e.g., a Rust client reading the world state) |
| `polars` / `parquet` | Telemetry dumps for analysis — not the world state itself |

**Adopt zarr when:** total world state exceeds ~100 MB or you want partial reads (a debugger that loads only the visible floor).

---

## 3. The "loud" simulation reactions

The base spec ships R1–R5 (decomposition, mana bleed, evaporation, dew, clamp). Here's the v2+ menu.

### 3.1 Combustion, freezing, corrosion

These are still 2–10 lines of vectorized NumPy each. The reason they were deferred isn't that they're hard — it's that they create cascading consequences that need to be tuned together.

```python
# ----- R6: combustion -----
# heat × mana_aether × flammability → temperature spike + mana consumption
combustion_mask = (
    (f["temperature"] > 80.0)
    & (f["mana_aether"] > 0.30)
    & (tilemap.flammability > 0.40)        # new TileProps column
)
ignition = np.where(combustion_mask, 0.20 * dt, 0.0).astype(np.float32)
f["temperature"]  += ignition * 50.0         # heat spike
f["mana_aether"]  -= ignition * 0.5          # consumed
f["humidity"]     -= ignition * 0.3          # boiled off

# ----- R7: freezing -----
# below 0°C, water tiles turn into traversable ice (composition mutation)
freeze_mask = (f["temperature"] < 0.0) & (tilemap.composition == TileComp.SHALLOW_WATER)
tilemap.composition[freeze_mask] = TileComp.FLOOR_ICE
tilemap.cache_derived()                       # recompute static arrays

# ----- R8: acid corrosion -----
# high acidity dissolves limestone walls slowly into floor over time
corrode_mask = (f["acidity"] > 0.7) & (tilemap.composition == TileComp.WALL_LIMESTONE)
corrosion_progress[corrode_mask] += 0.001 * dt
dissolved = corrosion_progress > 1.0
tilemap.composition[dissolved] = TileComp.FLOOR_LIMESTONE
corrosion_progress[dissolved] = 0.0
```

**The new dimension this opens:** `TileMap.composition` becomes mutable. The base spec assumed it's set at generation and never changes. Once it can change, every cached array (`is_wall`, `transparency`, source/sink fields) needs an invalidation strategy.

The clean answer is a `dirty_tiles: set[tuple[int,int]]` and a `cache_derived(dirty_only=True)` path that re-fills only the affected indices. Cheap.

**Adopt when:** you want player or DM-driven world deformation. Without it, the dungeon is a stage that erodes; with it, it's a stage that fights back.

### 3.2 Falling-sand particle physics

This is the Noita track. Every tile is a *particle type* (sand, water, lava, gas, steam, ash) with rules for what it falls through, displaces, or reacts with. The classic [Noita-style implementation in Python](https://mcgillij.dev/noita-falling-everything-in-python.html) shows how a couple hundred lines of pixel-array logic gets you sand, water, gas, and basic phase changes.

**Architectural decision:** falling-sand wants its own grid, separate from `TileMap.composition`. Composition is the *room geometry* (walls, water *channels*); particles live on top, in a `ParticleMap` updated every tick. The two interact through tile properties: walls block particle movement, water tiles spawn water particles continuously.

**Sketch:**
```python
class ParticleType(IntEnum):
    EMPTY = 0
    SAND  = 1
    WATER = 2
    LAVA  = 3
    STEAM = 4
    ASH   = 5

class ParticleMap:
    def __init__(self, w, h):
        self.particles = np.zeros((h, w), dtype=np.int8)
        self.velocity_y = np.zeros((h, w), dtype=np.float32)

    @numba.njit(parallel=False)  # falling-sand needs sequential bottom-up
    def step(particles, vy, walls):
        h, w = particles.shape
        # Bottom-up pass: each particle decides what to do
        for y in range(h - 2, -1, -1):
            for x in range(w):
                p = particles[y, x]
                if p == 0 or walls[y, x]:
                    continue
                if p == ParticleType.SAND:
                    if particles[y+1, x] == 0:
                        particles[y+1, x] = p; particles[y, x] = 0
                    elif x > 0 and particles[y+1, x-1] == 0:
                        particles[y+1, x-1] = p; particles[y, x] = 0
                    elif x < w-1 and particles[y+1, x+1] == 0:
                        particles[y+1, x+1] = p; particles[y, x] = 0
                # ... water, lava, steam, gases
```

**Reaction tables** — a dict `(type_a, type_b) → (type_a', type_b', heat_delta)` — are where the simulation becomes a *game*. Water + lava → stone + steam + cooling. Fire + flammable wood → fire + ash. Bone + acid → bone (corroded) + acid (weaker).

**Performance:** vectorized falling-sand is genuinely hard because the update is order-dependent. `numba` is the right tool. `taichi` is the right tool when you go beyond 256×256.

**Adopt when:** you want the "Noita feeling" — physically present materials that the player can manipulate, that interact with each other, that surprise you. It's a *huge* design dimension expansion.

### 3.3 `cellpylib` and bespoke CA

```bash
pip install cellpylib
```

[`cellpylib`](https://cellpylib.org) is a clean library for n-state, n-dimensional cellular automata with arbitrary rules. Use it for:
- Plant/fungal growth that respects substrate conditions.
- Disease/infection spread through a population (separate from your fields layer — this is creature-on-creature).
- Procedural cave erosion patterns at generation time.

For a sim like ours, hand-rolled NumPy CA in `field_step.py` is usually the right answer. `cellpylib` shines when you want to *experiment* with rule families — its API makes it cheap to try variations.

### 3.4 Differentiable physics with `difftaichi`

[`difftaichi`](https://github.com/taichi-dev/difftaichi) — now upstream in `taichi` — gives you autograd for physics simulations. You can compute `∂loss/∂parameters` through your fluid sim, your heat diffusion, your population dynamics.

**Concrete use cases for our sim:**
- **Auto-tuning rate constants.** Define a "good equilibrium" loss (e.g., "moss population should stabilize at 7 ± 1 patches after 200 ticks") and gradient-descend the diffusion rates and trait constants until it holds. The base spec's "first-pass numbers, tune from telemetry" plan becomes "first-pass numbers, autodiff to optimal."
- **Inverse design.** Given a desired emergent behavior, find tile compositions and field initial conditions that produce it.
- **Trained creature physics.** Couple with an RL outer loop: the creature learns *its own physical parameters* (not just its policy).

This is genuinely cutting-edge for game simulation. Most projects don't reach for it because the gradient propagation requires careful kernel design — every operation must be differentiable. But for a research-flavored project that wants to *publish* about emergent ecosystems, it's a compelling tool.

**Adopt when:** you're tuning constants by hand and finding it doesn't converge, OR when you want the project to be a research artifact.

---

## 4. Generation beyond BSP

### 4.1 Wave Function Collapse — full integration

The v2 spec sketched WFC as a post-v1 painter. Here's the full integration.

WFC takes a small *example* — a tiny hand-authored arrangement — and generates new arrangements that respect the same local adjacency rules. The output *feels* hand-authored even though it's procedural. It's the most under-used technique in Python game dev.

**Two libraries:**
- `wfc_2019f` — the reference Python port; CPU-only, supports overlapping and tiled models.
- `wfc-python` — a more recent fork with cleaner API.
- The Rust [`fast-wfc`](https://github.com/math-fehr/fast-wfc) with Python bindings is much faster if performance matters.

**Two integration patterns for our sim:**

1. **WFC as the geometry generator** — replace BSP entirely. Author one or two example floors by hand, WFC generates infinite variations. Best for visually rich, hand-authored-feeling dungeons.

2. **WFC as the composition painter** — keep BSP for the room/corridor structure, use WFC to fill `TileComp` values with naturalistic patterns (limestone bands, mycelium spreading along corridor walls but not into rooms). This is the v2 spec's `wfc_painter.py` slot.

The canonical educational source is [Boris the Brave's WFC writeups](https://www.boristhebrave.com/all-posts/) — they cover constraint propagation, backtracking, and the various variants (overlapping vs. tiled, 2D vs. 3D).

**Adopt when:** "BSP-shaped" rooms feel too geometric and you want emergent layouts.

### 4.2 Voronoi + Lloyd relaxation regions

```python
from scipy.spatial import Voronoi
```

Voronoi partitions a 2D plane into convex cells around seed points. Lloyd's algorithm iteratively relaxes the seeds toward their cell centroids, producing more even spacing. The result is naturalistic biome regions — irregular, organic, but well-spaced.

**Use cases:**
- **Biome partitioning** for floors with multiple ecological zones (mycelium grove + crystal cavern + acid pool, with fuzzy boundaries).
- **Cave systems** — Voronoi cells with random open/closed states produce convincing connected caves.
- **Faction territories** — each Voronoi cell starts owned by one faction; territory shifts via simulation.

This is a 30-line addition. Worth keeping in your back pocket.

### 4.3 Constraint-based generation: ASP / SAT / SMT

Three tools for the same problem: "I have hard constraints I need *guaranteed* to hold." Examples: every key precedes its lock, every region is reachable from start, exactly one boss room, no cyclic dependencies in the puzzle graph.

| Tool | Strength | Library |
|---|---|---|
| Answer Set Programming (Clingo) | Most expressive for combinatorial generation; declarative | [`clyngor`](https://pypi.org/project/clyngor/) |
| SAT | Fast for binary constraints | `python-sat` |
| SMT | Handles arithmetic constraints (e.g., "boss room area > 50 tiles") | `z3-solver` |

**The ASP pattern for dungeons:**
```prolog
% Every cell has exactly one composition.
1 { tile(X,Y,Comp) : composition(Comp) } 1 :- cell(X,Y).

% Crystal nodes must be at least 8 cells apart.
:- tile(X1,Y1,crystal_node), tile(X2,Y2,crystal_node),
   (X1,Y1) != (X2,Y2),
   |X1-X2| + |Y1-Y2| < 8.

% Every floor cell must be reachable from the entrance.
reachable(X,Y) :- entrance(X,Y).
reachable(X,Y) :- reachable(X',Y'), adj((X',Y'),(X,Y)), passable(X,Y).
:- cell(X,Y), passable(X,Y), not reachable(X,Y).
```

Clingo solves this in milliseconds for 60×40. Heavy machinery, but unmatched when you have *non-negotiable* properties.

**Adopt when:** you have constraints that simply must hold and you're tired of post-validation rejection-sampling generation runs.

### 4.4 Cyclic and graph-grammar dungeons

Joris Dormans' work (cited in the base spec's §9.2) generates dungeons by first building an *abstract mission graph* with cycles (loops are what makes Zelda dungeons interesting), then realizing it as concrete geometry. Mark Brown's *Boss Keys* video series is the design-side companion.

**Implementation pattern:**
1. Define a graph grammar — production rules like "expand any node into a sub-pattern of [key→lock→reward]."
2. Apply rules until you hit a target complexity.
3. Use `networkx` to validate the result (solvability, key ordering).
4. Lay out concrete rooms via force-directed placement, then carve corridors.

The best Python reference is [Boris the Brave's lock-and-key writeups](https://www.boristhebrave.com/2021/02/27/lock-and-key-dungeons/). For graph grammars specifically, search "graph rewriting Python" — there's no dominant library, most projects roll their own with `networkx` as the substrate.

**Adopt when:** you want metroidvania-style intentional traversal logic, not just "rooms connected by corridors."

---

## 5. ML-driven generation and AI

### 5.1 `gym-pcgrl` — generator as RL agent

[`amidos2006/gym-pcgrl`](https://github.com/amidos2006/gym-pcgrl) frames level generation itself as a reinforcement learning problem. The agent is the *generator* — it learns a policy that edits the level toward a reward signal (e.g., "playable, has a path of length > 30, contains 3-5 enemies").

**Three representations** for how the agent edits the map:
- **narrow** — pick a tile, decide its new value.
- **turtle** — move a cursor around the map, edit the cell under it.
- **wide** — pick any (x, y, new_value) at once.

[The PCGRL paper (Khalifa et al., 2020)](https://arxiv.org/abs/2001.09212) is the canonical reference. The library trains with stable-baselines PPO out of the box.

**For our sim:** the natural fit is *not* generating geometry from scratch (BSP+WFC is fine for that) but **generating tile compositions to satisfy ecological invariants**. Train a generator that, given a BSP skeleton, paints `TileComp` values such that the post-warm-up field state supports the desired creature populations. The reward is "after 200 ticks, slime population is in [5, 15] AND mana_moss patches are in [4, 10]."

**Adopt when:** you want generators that produce interesting ecosystems, not just interesting geometry.

### 5.2 `pyribs` / MAP-Elites — quality diversity

```bash
pip install ribs
```

[`pyribs`](https://pyribs.org) implements MAP-Elites and CMA-ME — quality diversity algorithms. Instead of generating one "best" dungeon, they generate an *archive* of diverse high-quality dungeons across behavioral dimensions.

**The key concept:** define **behavior characteristics** (BCs) — measurable properties you want to vary. For our sim, plausible BCs include:
- Total room count (5 to 25)
- Loop ratio (linear vs. cyclic, 0 to 1)
- Mean mana_geo at equilibrium (0.05 to 0.85)
- Predator:producer ratio (0 to 5)
- Floor "danger" (mean tremor + alarm, post-ecology)

The archive is a 2D or N-D grid where each cell holds the highest-quality dungeon found *at that combination of BCs*. The output is not "the best dungeon" but "a curated atlas of diverse dungeons."

**For our sim:** this is how you avoid every floor feeling the same. Generate a 10×10 archive, sample from it for each new floor, and the player sees variety they wouldn't have gotten from random seeds.

**Reference:** [Tjanaka et al., "pyribs: A Bare-Bones Python Library for Quality Diversity Optimization" (2023)](https://arxiv.org/pdf/2303.00191).

**Adopt when:** replayability and variety matter more than absolute peak quality of any one floor.

### 5.3 Diffusion / GAN dungeons

Active research area. Levels-as-images works for tile-based games (treat the map as a multi-channel image, train a DDPM/GAN over a corpus of hand-authored maps). The state of the art is improving fast but no single Python library has emerged as the "this is the one to use" — most published work is per-paper PyTorch code.

**For our sim, today:** probably skip. Revisit in 12 months — a drop-in library is likely.

If you want to experiment now, [G-PCGRL (2024)](https://arxiv.org/pdf/2407.10483) extends PCGRL to graph-structured outputs, which is closer to our mission-graph use case than image-based diffusion.

### 5.4 Trained creature AI: `stable-baselines3`, `RLlib`, PettingZoo

Once you have an RL-friendly environment (your World wrapped in a Gym interface), you can *train creatures* rather than authoring their behavior trees.

**Stack:**
- `stable-baselines3` — best ergonomics, single-agent RL (PPO, SAC, DQN, etc.).
- `RLlib` (Ray) — multi-agent, distributed training, the right answer when you want *all 200 organisms learning simultaneously*.
- `PettingZoo` — the multi-agent Gym standard. Your environment exposes a PettingZoo interface; agents see partial observations, take actions, share rewards.

**For our sim:**
- Producers don't need RL — they're sessile, BT-driven Rest-only.
- Consumers (slimes, predators) *could* be RL-trained, with reward = energy gained over time, plus shaping for "don't die." This is genuinely interesting because the creature learns to use the field gradients you've built — `sweet`-following emerges from training, not from authored BT logic.
- Apex predators / boss creatures in deeper floors might be the first place to deploy this — the design space for hand-authored boss BTs is limited; trained policies can be more interesting.

**The hybrid pattern:** keep BTs as the default substrate (cheap, deterministic, debuggable), use RL only for organisms where the BT space is exhausted.

**Adopt when:** you've hit "I can't author a behavior tree that does what I want" three or more times for the same creature class.

---

## 6. Decision-making beyond behavior trees

The base spec uses `py_trees`. Behavior trees are the right default — composable, debuggable, well-understood. Here are the alternatives, with the rule of when each beats BTs.

### 6.1 GOAP — Goal-Oriented Action Planning

GOAP gives each agent a list of available *actions* with preconditions and effects, plus a current *goal*. The agent runs an A*-style planner over the action space to find a sequence that achieves the goal. The classic gamedev case study is F.E.A.R.'s soldiers, who plan flanking maneuvers dynamically.

**Python libraries:** `goap` (multiple PyPI packages, all small). Easier to roll your own — the algorithm is ~150 lines.

**For our sim:**
- Field-aware preconditions are powerful. An action `DrinkWater` has precondition `water_tile_within_5_tiles AND humidity > 0.3`. The planner naturally chains `Locomote → DrinkWater` when the creature is thirsty, without you authoring that chain.
- Action effects can include field deltas — `Attack` consumes target energy AND emits tremor, planner accounts for both.

**Cost:** higher per-tick CPU than BTs (planning is search). Mitigations: cache plans, replan only when state changes meaningfully, use planning horizons of 3–5 actions.

**Adopt when:** authoring BTs becomes a bottleneck — you have 20+ creatures and the BTs are mostly copy-paste with small variations.

### 6.2 Utility AI

Each possible action has a *utility score* computed from the world state. The agent picks the highest-scoring action. No planning, no search — just a scoring function per action.

```python
def score_eat_moss(creature, world):
    if creature.energy > 0.8: return 0.0
    nearest = nearest_moss(creature, world)
    if nearest is None or nearest.distance > 10: return 0.0
    hunger = 1.0 - creature.energy
    threat = world.field_map.fields["alarm"][creature.y, creature.x]
    return hunger * (1.0 - 0.5 * threat)
```

**Strengths over BT:** more responsive to gradient changes ("I was going to eat, but a tremor just spiked, switch to flee"). Easier to tune than BTs because each behavior is a single function.

**Weaknesses:** no memory of plans, no multi-step reasoning. A utility AI doesn't *plan* a flanking maneuver — it'll just do whichever action scores highest right now, which might be inconsistent.

**Adopt when:** your creatures need to be highly *reactive* to changing field conditions. Particularly natural for our sim because every action's utility can read directly from `field_map`.

### 6.3 HTN — Hierarchical Task Networks

HTN is GOAP's bigger sibling. Tasks decompose into subtasks via *methods*; planning is recursive task expansion. Used in commercial games for high-level strategic AI.

**Python:** `pyhop` (lightweight, classic HTN). Niche.

**Adopt when:** you have multi-level objectives that BTs and GOAP can't express cleanly. For creature-level AI in our sim, almost never; for *DungeonMaster* AI (which has goals like "make this floor harder" decomposing into "spawn predator → buff acidity → reduce mana"), HTN is more natural than BTs.

### 6.4 Hybrid: BT root + GOAP/Utility leaves

The pragmatic answer for most projects: **keep BTs as the structural substrate**, but use GOAP or Utility AI inside specific leaf nodes for the decisions BTs handle poorly.

```
Selector (BT root)
├── Sequence: Threat response (BT — well-defined sequence)
├── Sequence: Reproduce (BT — well-defined sequence)
└── UtilityNode: Default activity
    ├── Score: eat_moss
    ├── Score: drink_water
    ├── Score: explore
    ├── Score: rest
    └── (pick highest)
```

This is what most production game AI actually looks like. The BT gives you legible high-level structure; the utility/GOAP nodes give you reactivity where it matters.

**Adopt when:** always, eventually. Start with pure BTs, retrofit utility nodes where authoring becomes painful.

---

## 7. Multi-floor, Z-axis, and large-world architecture

The base spec treats each floor as isolated. Real dungeons have inter-floor effects.

**Patterns:**

1. **List of independent floors with explicit transitions** — simplest. Each floor has its own `World`. Stairs are special tiles that teleport the player. This is what most roguelikes do.

2. **Single 3D field array `(z, h, w, channels)`** — same `(h, w)` per floor, allows physics to flow between floors via vertical convolution. Hot floors heat the floor above; toxic gas rises through stair shafts. The diffusion kernel becomes 3×3×3.

3. **Hybrid — independent geometry, coupled fields** — each floor has its own `TileMap` (different shapes), but field exchanges happen via *portal pairs* on stair tiles. A small amount of every field is exchanged each tick between the two ends of each portal. Gives you inter-floor physics without forcing uniform geometry.

**Persistence:** with multi-floor, you'll cross 100 MB total state. Switch to `zarr` (§2.4). Floor `z` becomes its own zarr group; only the active floor's chunks live in RAM.

**Streaming:** for *huge* worlds (hundreds of floors), only the player's current floor and its neighbors are simulated at full resolution. Distant floors get a coarse "abstract simulation" — population counts, total mana, average temperature — that updates in O(1) per floor per tick. Players don't notice; the world feels alive without the cost.

**Adopt when:** the campaign design has more than ~10 floors and the player is supposed to feel they exist concurrently.

---

## 8. LLM agent stacks for the DungeonMaster

The base spec's §15 sketched the boundary-translator pattern. Here's the filled-out version.

**Recommended stack:**

| Layer | Tool | Role |
|---|---|---|
| Local serving | `ollama` | One-line install, OpenAI-compatible REST API. Default for offline development |
| Hosted serving | OpenAI / Anthropic SDKs over `httpx` | When latency or quality requires frontier models |
| High-throughput serving | `vllm` | Self-hosted, GPU-backed, batch inference at scale |
| Direct in-process | `llama-cpp-python` | Embedded, lowest latency, no IPC |
| Agent orchestration | `langgraph` | State-machine over LLM calls. Nodes for perception, narration, adjudication. The right abstraction for a multi-step DM |
| Function calling | `pydantic-ai` or `instructor` | Force structured output (your `SpellIntent` schema). Both wrap the major SDKs and validate against pydantic models |
| Vector memory | `chromadb` (simple), `qdrant` or `lancedb` (production) | Long-running campaign memory keyed by tick + region |
| Prompt engineering / evals | `dspy` | When you want to *optimize* the DM prompts against a reward signal rather than hand-tune them |

**The four-node LangGraph for the DM:**

```python
# sim/dm/graph.py (sketch)
from langgraph.graph import StateGraph

def perception(state):
    """Read structured slice of world around focal area."""
    digest = WorldDigest.from_world(state.world, state.focus_xy, radius=10)
    return {**state, "digest": digest}

def narration(state):
    """Turn digest + recent action log into prose for the player."""
    prose = llm.invoke(NARRATION_PROMPT.format(
        digest=state.digest, recent=state.action_log[-5:]
    ))
    return {**state, "prose": prose}

def adjudication(state):
    """Parse player input, validate, emit SpellIntent or refuse."""
    intent = llm.invoke(ADJUDICATION_PROMPT, response_model=SpellIntent | Refusal)
    return {**state, "intent": intent}

def world_update(state):
    """Deterministic — apply intent to world. Not LLM."""
    if isinstance(state.intent, SpellIntent):
        dm_spell.step(state.world, state.intent)
    return state

g = StateGraph(DMState)
g.add_node("perception", perception)
g.add_node("narration", narration)
g.add_node("adjudication", adjudication)
g.add_node("world_update", world_update)
g.add_edge("perception", "narration")
g.add_edge("narration", "adjudication")
g.add_edge("adjudication", "world_update")
g.set_entry_point("perception")
```

**Cost control:** narration runs every player turn. Adjudication runs only when the player issues a command. Perception reads from cached slices that update on tick — don't re-extract every prompt. With a small local model (Llama 3.1 8B via ollama) and ~500-token prompts, you can keep DM cost near zero.

**Adopt when:** you want the LLM in the loop. The architecture above is independent of *which* model you use, so you can prototype on local Llama and swap to Claude/GPT for production.

---

## 9. Open-source dungeon AI projects worth studying

Less for code reuse, more for "how have other people solved adjacent problems."

| Project | Stack | What to steal |
|---|---|---|
| [`UTSAVS26/DungeonLM`](https://github.com/UTSAVS26/DungeonLM) | OpenAI GPT + Streamlit | JSON save format for LLM-driven worlds; prompt structure for dynamic world gen |
| [`fedefreak92/dungeon-master-ai-project`](https://github.com/fedefreak92/dungeon-master-ai-project) | Python FSM + GPT | The FSM-as-RPG-engine substrate; clean separation between rules and narration |
| [`Laszlobeer/Dungeo_ai`](https://github.com/Laszlobeer/Dungeo_ai) | Ollama + AllTalk TTS | Local-first architecture; voice narration patterns |
| [`ai-dungeon-cli`](https://pypi.org/project/ai-dungeon-cli/) | Wraps play.aidungeon.io | UX reference — what an LLM-driven adventure feels like as a CLI |
| [`amidos2006/gym-pcgrl`](https://github.com/amidos2006/gym-pcgrl) | Stable-baselines + Gym | Reference implementation of generator-as-RL-agent |
| [`AtTheMatinee/dungeon-generation`](https://github.com/AtTheMatinee/dungeon-generation) | Pure Python | Every classical dungeon algorithm in one annotated file. Best educational repo on the topic |
| [`mxgmn/WaveFunctionCollapse`](https://github.com/mxgmn/WaveFunctionCollapse) | Reference WFC | The original; read it before using a port |
| [`BooleanCube/falling-sand-sim`](https://github.com/BooleanCube/falling-sand-sim) | Pygame + NumPy | Compact falling-sand reference |
| [`taichi-dev/difftaichi`](https://github.com/taichi-dev/difftaichi) | Taichi | 10 differentiable physics simulations — start here for autograd-through-sim |

---

## 10. Adoption roadmap — the menu, ordered

If I had to pick an order to adopt these, optimizing for "biggest design payoff per integration cost":

**Tier 1 — high-payoff, low-cost (do these first):**
1. **Worley noise + WFC painter** for naturalistic generation (already covered in v2 spec, just enable).
2. **Hybrid BT + Utility AI** for creature decisions — keep py_trees, retrofit utility leaves.
3. **`numba` JIT** on the one or two slowest hot paths your profiler flags.
4. **Loud reactions (R6–R8)** — combustion, freezing, corrosion. Adds emergent drama at low integration cost.

**Tier 2 — bigger lift, transformative (pick 1–2):**
5. **Falling-sand particle layer** — fundamentally expands the design space; "Noita feeling."
6. **`esper` ECS migration** — when organism count or system complexity demands it.
7. **`networkx` mission graphs** — for intentional traversal logic in deeper floors.
8. **Multi-floor 3D field architecture** — when the campaign has >10 floors.

**Tier 3 — research-flavored, optional (only if the goals call for them):**
9. **`pyribs` MAP-Elites** — for curated dungeon variety.
10. **`gym-pcgrl` ecological generators** — for generators that produce healthy ecosystems, not just geometry.
11. **`taichi` GPU fields** — when grids exceed 500×500.
12. **`difftaichi` autodiff tuning** — for parameter optimization or research outputs.
13. **`mesa` for headless experiments** — when results need to be published or compared statistically.
14. **`stable-baselines3` / RLlib trained creatures** — when authoring behaviors is exhausted.

**Tier 4 — DM-layer (entirely separate workstream):**
15. **`ollama` + `langgraph` + `pydantic-ai`** for the boundary-translator DM.
16. **`chromadb` / `lancedb`** for campaign memory.
17. **`dspy`** for prompt optimization once the DM is stable.

Note that this list reaches 17 items. Do not adopt all 17. Adopt 3 from Tier 1, 1 from Tier 2, decide whether Tier 3 matches your project's identity, and whether the DM layer is part of the v2 vision or a v3 thing.

---

## 11. Further reading

### Foundational

- Boris the Brave's [complete blog](https://www.boristhebrave.com/all-posts/) — WFC, lock-and-key, dungeon math, constraint propagation. The single highest-density PCG resource on the internet.
- Brian Walker, ["The Incredible Power of Dijkstra Maps"](http://www.roguebasin.com/index.php/The_Incredible_Power_of_Dijkstra_Maps) — already cited in v2 spec; re-cited because every system in §6 above benefits from understanding Dijkstra maps deeply.
- [RogueBasin](http://www.roguebasin.com/) — the wiki of every roguelike algorithm.
- [Grid Sage Games dev blog](https://www.gridsagegames.com/blog/) — Cogmind dev's writeups on procedural layouts at scale.

### Papers

- Khalifa et al., [PCGRL: Procedural Content Generation via Reinforcement Learning](https://arxiv.org/abs/2001.09212), 2020.
- Tjanaka et al., [pyribs: A Bare-Bones Python Library for Quality Diversity Optimization](https://arxiv.org/pdf/2303.00191), 2023.
- [G-PCGRL: Procedural Graph Data Generation via Reinforcement Learning](https://arxiv.org/pdf/2407.10483), 2024.
- Hu et al., [DiffTaichi: Differentiable Programming for Physical Simulation](https://arxiv.org/abs/1910.00935), 2019.

### Game design

- Joris Dormans, *Procedural Generation in Game Design* (book — chapter on cyclic generation is mandatory reading).
- Mark Brown, *Boss Keys* YouTube series — the canonical analysis of intentional dungeon flow.
- Tarn & Zach Adams, [Dwarf Fortress dev blog](http://www.bay12games.com/dwarves/) — the gold standard for "world simulation as game."
- [PCG Workshop paper database](https://www.pcgworkshop.com/database.php) — searchable academic PCG.

### Library docs / tutorials

- [Taichi Differentiable Programming docs](https://docs.taichi-lang.org/docs/differentiable_programming) — start here for autograd-through-physics.
- [Mesa user guide](https://mesa.readthedocs.io) — agent-based modeling reference.
- [Griddly docs](https://griddly.readthedocs.io) — RL on grid worlds.
- [esper README](https://github.com/benmoran56/esper) — terse, clean ECS.
- [LangGraph docs](https://langchain-ai.github.io/langgraph/) — state-machine LLM agents.
- [pyribs tutorials](https://docs.pyribs.org) — quality diversity worked examples.

### Practical

- [Falling Everything in Python](https://mcgillij.dev/noita-falling-everything-in-python.html) — tractable falling-sand walkthrough.
- [BT vs. GOAP vs. Utility AI](https://tonogameconsultants.com/game-ai-planning/) — modern comparison of decision architectures.
- [Numba performance tips](https://numba.pydata.org/numba-doc/dev/user/performance-tips.html) — what JIT actually accelerates and what it doesn't.

---

*Compiled May 2026 as an addendum to the dungeon environment specs (now `docs/spec/ecosystem-legacy-v1.md` / `docs/spec/ecosystem-v2.md`). Tools and library versions current at compile time; the LLM/agent ecosystem in §8 changes monthly, the simulation-side libraries in §1–§4 are stable.*
