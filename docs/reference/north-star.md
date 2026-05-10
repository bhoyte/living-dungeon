# Living Dungeon — North Star (Vision + Phase-2 Reference)

> Vision and rationale reference document.  
> Ecosystem-first phase-1 implementation canon is now `docs/spec/ecosystem-v2.md` and `docs/canon/charter.md`.  
> Creature architecture and LLM adaptation details in this file are phase-2 guidance.

> Previous note retained for historical context: this file replaced and reconciled `living-dungeon-ecosystem.md`, `species-behavior-through-physical-traits-2.md`, and `tree-graph-3.md`.

> **Stack decision (v1):** Pure-Python simulation core. Pygame for rendering only. No game engine. No Godot, no Bevy, no Rust. Engine-agnostic by construction so a future port is mechanical, not architectural.

---

## How to use this document now

- Use this file for vision, tone, and long-horizon design intent.
- Do not treat it as the active implementation authority for phase-1 sequencing.
- For current build order and gates, use `docs/README.md`, `docs/canon/charter.md`, and `docs/spec/ecosystem-v2.md`.

## 0. What we are building

A 2D Dungeon Meshi–style multi-floor dungeon where **every monster is a data-driven instance of one universal organism**, behavior emerges from local constraints (energy, scent, sight, stress), and a **local LLM is invoked rarely**, as an evolutionary catalyst — never a per-tick brain.

The player's role is initially **observation and intervention** (the "Dungeon Master / Lunatic Magician"). Direct player-character gameplay is post-v1.

### Non-negotiable principles

1. **One organism class, data-driven.** No `Goblin`, no `Slime` subclasses. Every creature is an instance of `Organism` differentiated by an `OrganismData` model.
2. **Bottom-up activation.** No global brain polls the world. Stress at the agent level triggers cluster-level events.
3. **Tiered cognition.** Reflex (every tick, free) → Hardcoded subtree library (fast path, hash lookup) → LLM (slow path, rare, cached).
4. **Polymorphic verbs.** A small fixed verb set; traits decide *how* a verb executes. The LLM never invents new verbs.
5. **Metabolic cost for complexity.** Bigger trees and bigger bodies cost more energy. Niches emerge from cost, not scripting.
6. **Closed trophic loops by construction.** Producer → consumer → decomposer → producer. Validated mathematically before any LLM touches it.
7. **Epigenetics as shock absorber.** Lifetime trauma changes a multiplier layer; the LLM only mints permanent changes after sustained pressure.
8. **Sim never imports the renderer.** The simulation is a library. Pygame imports the simulation, never the other way around. This is the rule that keeps the project honest.

### Out of scope for v1 (deferred, not abandoned)

- Rust / Bevy / WASM hot-swap / GNN routing. Premature. Revisit only if agent count exceeds ~2,000 sustained.
- Procedural skeleton rigs and shaders. Use colored shapes until Sprint 5.
- Full "Superpower Poster" trait codex. Start with 6 traits, grow reactively.
- Speciation events with dynamic naming, lineage ledger UI. Sprint 8+.
- Five evolutionary triggers (drift, relaxation, Red Queen, founder, HGT). Start with **drift only**; add others one per post-v1 sprint.
- Multi-process sim/render split. v1 is one process, fixed-timestep. Splitting is a 30-line change later.

---

## 1. Architecture in one picture

```
┌──────────────────────────────────────────────────────────────────┐
│  app/  (the only place that imports everything)                  │
│  ├── main.py                main loop, fixed-timestep            │
│  └── headless.py            sim-only entry point (CI, evo runs)  │
└────────────┬───────────────────────────┬─────────────────────────┘
             │ imports                   │ imports
             ▼                           ▼
┌──────────────────────────┐  ┌─────────────────────────────────────┐
│  render/  (pygame only)  │  │  ai/    (Ollama, validators)        │
│  ├── viewport.py         │  │  ├── client.py    httpx → Ollama    │
│  ├── debug_overlay.py    │  │  ├── schemas.py   pydantic models   │
│  └── stigmergy_view.py   │  │  ├── prompts.py   templates         │
│  surfarray heatmaps      │  │  └── validator.py firewall          │
│  pygame.draw.circle      │  └────────────────┬────────────────────┘
│  reads sim, never writes │                   │ imports
└──────────┬───────────────┘                   ▼
           │ imports             ┌──────────────────────────────────┐
           ▼                     │  sim/   (pure python + numpy)    │
┌──────────────────────────────  │  ├── organism.py     dataclass   │
│  sim/  ─────────────────────── │  ├── world.py        Floor       │
│   never imports pygame, never  │  ├── stigmergy.py    numpy grids │
│   imports anything that draws  │  ├── senses.py       SenseManager│
│                                │  ├── verbs.py        6 verbs     │
│                                │  ├── trees.py        py_trees BT │
│                                │  ├── population.py   PopMgr      │
│                                │  ├── pressure.py     vector      │
│                                │  ├── trophic.py      energy flow │
│                                │  └── tick.py         step()      │
│                                └──────────────────────────────────┘
```

Four folders. Strict dependency direction. Enforced by `import-linter` (see §13). If a sim test ever fails because pygame isn't available, the architecture has been violated and the import is reverted, no exceptions.

---

## 2. The four contracts

These are the only interfaces that matter. If a system isn't expressible through one of these, it's the wrong design.

### 2.1 Per-tick agent loop (no LLM)

```
get_state(organism, world) → StateSnapshot
decide(snapshot, tree)     → Verb + Target          # py_trees, deterministic
apply(verb, target, world) → world delta + stress delta
update_epigenome(organism) → multipliers shift if thresholds crossed
```

This runs every tick, every organism. **Zero LLM tokens, zero allocations beyond what py_trees requires.**

### 2.2 Stress cluster event (PopulationManager, every ~5s)

```
scan_stress_clusters(floor) → list[Cluster]
for cluster in clusters:
    context = build_context(cluster)
    sig     = signature(context)              # short hash
    if sig in fast_lookup:
        inject_subtree(cluster, fast_lookup[sig])  # done, no LLM
    else:
        queue_for_llm(context, sig)
```

### 2.3 LLM mutation request (rare, async, batched)

```
request   = LLMRequest(context, allowed_verbs, allowed_traits, subtree_library)
response  = await ollama.chat(strict_json_schema, request)
    parsed    = LLMResponse.model_validate(response)   # pydantic = the firewall
inject_subtree(cluster, parsed.subtree_key or parsed.new_subtree)
    fast_lookup[sig] = key                              # cache forever
```

While the call is in flight, the cluster runs `dormancy` as a placeholder so nothing freezes.

### 2.4 Speciation event (Sprint 8+, even rarer)

```
if cluster.epigenetic_marker_persisted_for(generations=10):
    request_baldwinization(species, marker)   # LLM bakes epigenome into base_genome
    fork_lineage(species, name=llm_proposed_name)
```

That's it. Every other system is plumbing for these four.

---

## 3. Data schemas (pydantic, the only schemas in the project)

These are the reference shapes. Lock them now; everything else conforms. Pydantic gives us free validation for the LLM firewall — no separate validator module.

### 3.1 OrganismData

```python
# sim/organism.py
from pydantic import BaseModel, Field
from typing import Literal

Sense = Literal["sight", "smell", "tremorsense", "thermal"]

class Genome(BaseModel):
    size:             float = 1.0     # body scale, affects collision + metabolism
    speed:            float = 50.0    # px/sec base
    metabolism:       float = 1.0     # energy drain multiplier
    perception_range: float = 100.0
    aggression:       float = 0.5     # 0..1 bias toward Interact vs Flee
    pigmentation:     tuple[float, float, float] = (0.4, 0.7, 0.4)

class Epigenome(BaseModel):
    # multipliers, default 1.0; tween toward 1.0 over time when pressure relieved
    size_mult:       float = 1.0
    speed_mult:      float = 1.0
    metabolism_mult: float = 1.0
    perception_mult: float = 1.0
    aggression_mult: float = 1.0

class SenseChannel(BaseModel):
    range: float = 0.0
    acuity: float = 0.0

class OrganismData(BaseModel):
    species_id:     str
    trophic_level:  int = Field(ge=0, le=3)   # 0 producer .. 3 apex
    base_genome:    Genome
    epigenome:      Epigenome = Epigenome()
    traits:         list[str] = []            # keys into trait_codex
    senses:         dict[Sense, SenseChannel] = {}

    def stat(self, name: str) -> float:
        base = getattr(self.base_genome, name)
        mult = getattr(self.epigenome, f"{name}_mult", 1.0)
        return base * mult
```

The runtime `Organism` is a separate dataclass holding mutable per-instance state (position, energy, stress, age) plus a reference to its shared `OrganismData`. Two slimes share genome data, hold their own positions and counters.

### 3.2 Trait codex (v1 starter — exactly 6 traits)

```python
# sim/traits.py
TRAIT_CODEX = {
    "photosynthesis":  {"cost": 1, "grants": "passive_energy_in_light", "prereq": None},
    "carnivore":       {"cost": 1, "grants": "energy_from_corpses",     "prereq": None},
    "acidic_touch":    {"cost": 1, "grants": "damage_on_contact",       "prereq": None},
    "sweet_scent":     {"cost": 1, "grants": "emit_lure_pheromone",     "prereq": None},
    "camouflage":      {"cost": 2, "grants": "perception_penalty_to_observers", "prereq": None},
    "echolocation":    {"cost": 2, "grants": "tremorsense_range_+150",  "prereq": None},
}
```

**Rule:** every trait has a real Python hook (a function in `sim/trait_effects.py`). No trait exists in the codex without a working effect. The LLM may only choose from this dict.

### 3.3 Verb manifest (locked at 6 verbs, 4 conditions)

```python
# sim/verbs.py
VERBS = {
    "Locomote":  ["target"],            # toward, away_from, wander, fixed point
    "Interact":  ["target"],            # dispatch on traits: eat, attack, mate, harvest
    "Emit":      ["substance"],         # scent, spore, alarm
    "Construct": ["object"],            # web, burrow, nest — gated by trait
    "Rest":      [],
    "Hide":      [],                    # seek tile/feature lowering perception
}

CONDITIONS = {
    "QuerySense":    ["sense_type", "target_type"],
    "CheckInternal": ["stat", "op", "threshold"],
    "CheckEnv":      ["tile_or_var", "op", "value"],
    "CheckCooldown": ["key"],
}
```

`Interact` and `Locomote` are polymorphic: a Mana Moss `Locomote` is a no-op + sets failure; a Slime `Locomote(prey)` crawls; a Flying Eye `Locomote(prey)` dives. Same verb, trait dispatches.

Each verb is a `py_trees.behaviour.Behaviour` subclass in `sim/trees.py`. Each condition is a `py_trees.behaviour.Behaviour` returning SUCCESS/FAILURE.

### 3.4 Subtree library (v1 starter — 4 hardcoded subtrees)

```python
# sim/subtrees/__init__.py
SUBTREE_LIBRARY = {
    "aggressive_foraging": "rush remaining food, ignore mild threats",
    "scatter_and_hide":    "split, seek camouflage tile, Hide",
    "dormancy":            "Rest in safe tile, drop metabolism",
    "migration_up":        "Locomote toward staircase, then ascend",
}
```

Each entry is a real `py_trees` tree builder function. The LLM picks from this dict 95% of the time.

### 3.5 StateSnapshot (what `get_state` returns)

```python
class StateSnapshot(BaseModel):
    self_:      "SelfView"
    perception: "PerceptionView"
    env:        "EnvView"

class SelfView(BaseModel):
    species: str
    energy:  float
    stress:  float
    traits:  list[str]

class VisibleEntity(BaseModel):
    id:      int
    species: str
    dist:    float
    bearing: float

class PerceptionView(BaseModel):
    visible: list[VisibleEntity]
    scents:  list[dict]   # {substance, gradient_xy}
    tremors: list[dict]

class EnvView(BaseModel):
    floor: int
    tile:  str
    light: float
    mana:  float
```

py_trees Behaviours read this off the blackboard. The LLM consumes the *aggregate* of many snapshots in a cluster context.

---

## 4. Cognition tiers (where compute goes)

| Tier | Frequency | Mechanism | Cost |
|---|---|---|---|
| **0. Reflex** | every tick | py_trees walks base BT, picks verb | free |
| **1. Epigenetic shift** | seconds–minutes | Stress thresholds tween epigenome multipliers | free |
| **2. Subtree injection (cached)** | every ~5–30s per cluster | PopulationManager hash lookup → swap AdaptationSlot | free |
| **3. LLM subtree pick** | minutes per cluster, novel context only | Ollama JSON call, choose from library | cheap, cached |
| **4. LLM subtree authoring** | rare, when library insufficient | Ollama JSON call, build new tree from verb manifest | medium, cached |
| **5. Speciation / Baldwinization** | per ~10 generations of marker persistence | LLM bakes epigenome into base_genome, names lineage | rare |

If you find yourself wanting to call the LLM at any tier finer than 3, you've designed the wrong thing. Push it down a tier.

---

## 5. The evolutionary pressure vector

The PopulationManager doesn't track a single `stress` scalar at the cluster level. It tracks a vector — adapted from `species-behavior-through-physical-traits-2.md`:

```python
class EvolutionaryPressure(BaseModel):
    predation:   float = 0.0            # share of recent deaths attributable to predator X
    starvation:  float = 0.0            # share of cluster below energy threshold
    abundance:   float = 0.0            # share of cluster at >95% energy with no threats
    isolation:   float = 0.0            # recent migration through a staircase
    nemesis_id:  str | None = None      # dominant cause of death, if any
```

The vector decides which **prompt template** is used. v1 ships with two templates: `starvation` and `predation`. Add the others one per post-v1 sprint.

---

## 6. LLM contract (the only place tokens get spent)

### 6.1 What the LLM is allowed to do

- **Pick** an existing subtree key from the library.
- **Author** a new subtree from the verb manifest (whitelisted verbs + conditions only).
- **Propose** genome deltas bounded by `±0.15` per stat.
- **Propose** one trait from `TRAIT_CODEX` (must already exist).
- **Name** a new sub-species (string only).

### 6.2 What the LLM is forbidden from doing

- Inventing verbs, conditions, traits, senses, tile types, or stats not already in schema.
- Returning prose outside the JSON envelope.
- Writing genome deltas above the bound.
- Selecting traits whose `prereq` the species doesn't satisfy.

The validator is a single pydantic model. Invalid responses raise `ValidationError`, the cluster falls back to the highest-confidence existing subtree, and the failure is logged. **No model output is ever fed into the simulation un-validated.**

```python
# ai/schemas.py — the entire firewall
from pydantic import BaseModel, Field, field_validator
from typing import Literal

class TreeNode(BaseModel):
    type: Literal[*VERBS.keys(), *CONDITIONS.keys(), "Sequence", "Selector"]
    args:     list = []
    children: list["TreeNode"] = []

class NewSubtree(BaseModel):
    name: str
    tree: TreeNode

class LLMResponse(BaseModel):
    use_existing: bool
    subtree_key:  str | None = None
    new_subtree:  NewSubtree | None = None
    genome_delta: dict[str, float | tuple[float, float, float]] = {}
    trait_grant:  str | None = None
    rationale:    str = ""

    @field_validator("subtree_key")
    @classmethod
    def must_exist(cls, v):
        if v is not None and v not in SUBTREE_LIBRARY:
            raise ValueError(f"unknown subtree {v}")
        return v

    @field_validator("trait_grant")
    @classmethod
    def must_be_in_codex(cls, v):
        if v is not None and v not in TRAIT_CODEX:
            raise ValueError(f"unknown trait {v}")
        return v

    @field_validator("genome_delta")
    @classmethod
    def bounded(cls, v):
        for k, val in v.items():
            if isinstance(val, (int, float)) and abs(val) > 0.15:
                raise ValueError(f"{k} delta {val} exceeds bound")
        return v
```

That model **is** the firewall. There is no other validator. The pydantic `ValidationError` raised on a bad response is caught at the call site and the cluster falls back gracefully.

### 6.3 Canonical system prompt

```
You are the Dungeon Core, a process that adapts species behavior in a closed
ecosystem. You output only valid JSON conforming to the provided schema.
You may only use the verbs, conditions, traits, and subtrees explicitly
listed. You will be terminated and ignored if you invent any token outside
those lists. Bias toward picking an existing subtree. Author a new one
only if no existing subtree plausibly addresses the pressure.
```

### 6.4 Canonical request envelope

```jsonc
{
  "pressure":         {"type": "predation", "nemesis": "flying_eye", "severity": 0.82},
  "species":          {"id": "slime", "traits": ["acidic_touch"], "genome": {...}, "senses": {...}},
  "cluster_size":     6,
  "floor_context":    {"index": 1, "light": 0.7, "resource_density": 0.55},
  "verb_manifest":    {/* §3.3 */},
  "trait_codex":      {/* §3.2 */},
  "subtree_library":  {"aggressive_foraging": "...", "scatter_and_hide": "...", "dormancy": "...", "migration_up": "..."}
}
```

### 6.5 Canonical response (pick existing)

```jsonc
{
  "use_existing":   true,
  "subtree_key":    "scatter_and_hide",
  "new_subtree":    null,
  "genome_delta":   {"pigmentation": [-0.1, -0.1, -0.1]},
  "trait_grant":    null,
  "rationale":      "Slimes lack tremorsense; visual predator hunts on sight. Darker pigmentation lowers detection."
}
```

### 6.6 Canonical response (author new)

```jsonc
{
  "use_existing":   false,
  "subtree_key":    null,
  "new_subtree":    {
    "name": "ambush_under_moss",
    "tree": {
      "type": "Sequence",
      "children": [
        {"type": "QuerySense",    "args": ["sight", "predator"]},
        {"type": "Locomote",      "args": ["nearest_moss_tile"]},
        {"type": "Hide"},
        {"type": "CheckInternal", "args": ["stress", "<", 0.4]}
      ]
    }
  },
  "genome_delta":   {"pigmentation": [-0.1, -0.1, -0.1]},
  "trait_grant":    null,
  "rationale":      "Use moss tiles as visual cover. Stay hidden until stress decays."
}
```

`rationale` is for the player UI and debug logs — the engine ignores it.

### 6.7 Local model choice

- **Ollama, `llama3.1:8b-instruct-q5_K_M`** as the default. Fast, JSON-mode friendly, fits 8GB VRAM.
- Fallback: `qwen2.5:7b-instruct`. Sometimes follows JSON schemas more reliably.
- Always invoke with `format="json"` and a short stop sequence. Hallucinated keys destroy the validator and waste retries.

### 6.8 Async, never blocking

The Ollama call is `await`ed in a background task; the sim tick never blocks. If the call exceeds a 5s budget, the cluster keeps running `dormancy` and the request is cancelled. This is critical for keeping the per-tick loop deterministic and testable.

---

## 7. Stigmergy and sensory modularity

### 7.1 StigmergyMap (numpy)

One per floor. Holds N scalar grids, one per substance: `sweet`, `alarm`, `corpse`, `spore`. Each grid is `tile_w × tile_h` `float32`, decay `λ` per second, diffuse to 8-neighbors at rate `ρ`.

```python
# sim/stigmergy.py
import numpy as np

class StigmergyMap:
    def __init__(self, w: int, h: int, substances: list[str], decay: float, diffuse: float):
        self.grids = {s: np.zeros((h, w), dtype=np.float32) for s in substances}
        self.decay = decay
        self.diffuse = diffuse

    def deposit(self, x: int, y: int, substance: str, amount: float):
        self.grids[substance][y, x] += amount

    def step(self, dt: float):
        # decay
        for g in self.grids.values():
            g *= (1.0 - self.decay * dt)
        # cheap 8-neighbor diffusion via convolution (scipy or hand-rolled)
        # left as one ndimage.uniform_filter call

    def sample(self, x: int, y: int, substance: str) -> tuple[float, tuple[float, float]]:
        g = self.grids[substance]
        v = g[y, x]
        gy, gx = np.gradient(g[max(0,y-1):y+2, max(0,x-1):x+2])
        return v, (float(gx.mean()), float(gy.mean()))
```

`Action_Emit(substance)` deposits. `QuerySense("smell", target_type)` reads the highest gradient matching `target_type → substance` (e.g., `prey → sweet`).

The renderer can visualize a grid as a heatmap with `pygame.surfarray.make_surface(grid_normalized_uint8)` — one of the few places pygame actually shines. **The renderer reads `StigmergyMap.grids` but never writes to them.**

### 7.2 SenseManager

```python
def query(organism, sense_type, target_type, world) -> SenseResult | None:
    channel = organism.data.senses.get(sense_type)
    if not channel or channel.range == 0:
        return None                     # FAILURE in BT terms
    ...
```

If the organism's sense range is 0, the call returns `None` immediately. **This is the single biggest source of niche differentiation.** Don't skip it.

---

## 8. Sprint roadmap with hard gates

You don't advance until the gate is met. No exceptions, no "I'll come back to it." Doing this properly is the whole game.

| Sprint | Deliverable | Hard gate |
|---|---|---|
| **0** | Paper prototype walkthrough (§9) internalized; schemas in §3 reviewed; project layout in §13 created | You can predict what the engine does for a novel scenario without hand-waving; `pytest` runs an empty test successfully |
| **1** | `OrganismData`, `Organism`, `Floor`. Headless tick loop. Two organism instances with distinct stat profiles. **No pygame, no AI.** | `pytest sim/` passes a test asserting the two organisms produce different `stat()` outputs and survive 100 ticks |
| **2** | 6 verbs + 4 conditions as py_trees Behaviours. One species (slime) with hand-written base BT. Energy + death | Pytest runs a 600-tick simulation: slime wanders, eats, starves, dies. Asserted in code, not by eyeballing |
| **3** | Producer (mana_moss, photosynthesis trait) + decomposer rule (corpses → mana over time). Closed trophic loop | 10-minute simulated run keeps population non-zero. Energy-in equals energy-out within 5%. Asserted in pytest |
| **4** | **First pygame work.** Bare viewport: `pygame.draw.circle` per organism, stigmergy heatmap via `surfarray`. StigmergyMap + SenseManager wired in. Blind species variant added | Visual run shows scent gradients; blind variant visibly behaves differently from sighted in pytest log AND on screen |
| **5** | Stress accumulation, epigenome layer with heritability and fade. Pigmentation tween visible on screen | Famine shrinks population (visible + asserted); recovery restores when fed; epigenome decays back over time |
| **6** | PopulationManager with cluster detection, signature hash, **3 hardcoded subtrees**, AdaptationSlot injection | Under famine, stressed cluster auto-receives `dormancy`; under predator, `scatter_and_hide`. Both observable and asserted |
| **7** | Ollama slow path. Existing-subtree-pick only. Pydantic validator. Cache. Async non-blocking | LLM picks an existing subtree for a novel context; cache hits on second occurrence; pytest with mocked Ollama still passes |
| **8** | LLM authors new subtrees from verb manifest. Manual approval queue (or auto-accept after N successful ticks) | One LLM-authored subtree runs, lowers cluster stress, is added to library, persists across runs |
| **9** | Multi-floor (3 floors), staircases, migration. DungeonMaster spells: famine, abundance, introduce_predator | Cascading population effects observable across floors when a spell fires |
| **10+** | Speciation (Baldwinization), lineage ledger UI, additional pressure types, sensory traits beyond v1 | — |

The critical structural decision: **Sprint 6 happens before Sprint 7.** The entire LLM-shaped pipeline must work end-to-end with hardcoded subtrees before a single token is spent. This is the difference between a 2-day Ollama integration and a 2-month rabbit hole.

The second critical structural decision: **pygame doesn't appear until Sprint 4.** Sprints 1–3 are headless and produce a real, testable simulation. If you find yourself wanting to add pygame earlier "just to see it," resist — every minute of pygame in Sprint 1–3 is a minute not spent on the simulation that will outlive any rendering choice.

---

## 9. Paper prototype — "First Famine, First Predator"

The rest of this doc is the worked example. If anything below cannot be expressed using the schemas and contracts above, the schemas are wrong and we revise them, not the example.

### 9.1 Scenario setup

- **Floor 1**, light 0.7, mana 0.6, resource_density 0.55, season "wet".
- **12 Mana Moss** patches (sessile, photosynthesis, sweet_scent). Static positions.
- **8 Slimes** (crawling, acidic_touch). Sighted (sight 100, smell 60). Aggression 0.4. Eat moss on contact via `Interact`.
- Initial energy: moss 100, slimes 80.
- t = 0..5 minutes (300 ticks at 1 Hz logical). Stable equilibrium expected.
- At **t = 5:00**, DungeonMaster casts `cast_introduce_predator(floor=1, species="flying_eye", count=3)`.
- **Flying Eye**: flight (ignores tile costs), speed 120, sight 180, carnivore. Aggression 0.85. No smell.

### 9.2 Tick-by-tick trace

We trace one slime, **slime_03**, from t=0 to roughly t=10:00. All values rounded.

**t = 0:00 — Equilibrium**

```python
get_state(slime_03, world)  # returns:
StateSnapshot(
  self_      = SelfView(species="slime", energy=0.80, stress=0.0, traits=["acidic_touch"]),
  perception = PerceptionView(
    visible = [VisibleEntity(id=7, species="moss", dist=42.0, bearing=0.6)],
    scents  = [{"substance": "sweet", "gradient": (0.4, 0.0)}],
    tremors = [],
  ),
  env        = EnvView(floor=1, tile="floor", light=0.7, mana=0.6),
)
```

```
base BT (Selector):
  1. CheckInternal(stress, >, 0.7)  → FAILURE
  2. CheckInternal(energy, <, 0.5)  → FAILURE   # not hungry yet
  3. wander → Locomote(random_walk) → SUCCESS
```

Slime wanders. Energy drains at `metabolism × 0.05 / sec`.

**t = 1:30 — Hungry, forages by smell**

```
self_.energy = 0.42
base BT:
  2. CheckInternal(energy, <, 0.5) → SUCCESS
     → Sequence:
        QuerySense(smell, food)   → SUCCESS, gradient (+0.3, +0.1)
        Locomote(up_gradient)     → SUCCESS
        Interact(moss_07)         → SUCCESS, +0.4 energy
on_critical_success(): stress -= 0.05
```

Slime now at 0.82 energy, stress 0.0. This loop runs cleanly through t=5:00.

**t = 5:00 — DungeonMaster spell fires**

```python
DungeonMaster.cast_introduce_predator(floor=1, species="flying_eye", count=3)
# → spawn 3 flying_eye instances at random positions
```

No slime perceives them yet.

**t = 5:24 — First contact, no kill**

```
slime_03 perception.visible: [flying_eye_01 dist=88, bearing=2.7]
base BT:
  1. CheckInternal(stress, >, 0.7)  → FAILURE   # stress is still 0
  2. CheckInternal(energy, <, 0.5)  → FAILURE
  3. # wander
```

**Slime_03 ignores the predator.** It has no innate threat condition in its base BT. This is correct — its base behavior was designed for a predator-free floor. Threat detection must come from adaptation, not prescience.

**t = 5:31 — slime_07 dies**

flying_eye_02 dives, kills slime_07. Death event broadcast to PopulationManager:

```python
population_mgr.on_death(slime_07, cause="predation", agent="flying_eye_02", pos=(412, 188))
```

Slimes within `cluster_radius=150` of the death (slime_03, slime_05, slime_08, slime_11) receive a perception event:

```python
slime_03.on_witness_event(type="kin_death", agent="flying_eye_02", dist=92)
# → stress += 0.20    (0.0 → 0.20)
```

**t = 5:31 — Epigenetic trigger check**

```python
update_epigenome(slime_03):
    if stress > 0.15:                                   # predation_trauma_threshold
        epigenome.speed_mult      = lerp(1.0, 1.2, 0.1) # 1.02
        epigenome.metabolism_mult = lerp(1.0, 1.15, 0.1)# 1.015
    # hyper-vigilance: faster but burns more energy
```

Speed and metabolism are now drifting upward. The slime is *visibly* getting twitchier over the next minute (Sprint 5+ — in Sprint 1–3 this is just a logged number).

**t = 5:31 to 6:45 — Two more deaths, stress accumulates**

slime_11 dies at 5:58, slime_05 dies at 6:31. Each death within cluster radius adds stress to survivors.

```
slime_03 stress trajectory:
  5:00   0.00
  5:31   0.20 (slime_07 death witnessed)
  5:58   0.38 (slime_11 death witnessed)
  6:31   0.55 (slime_05 death witnessed)
  6:45   0.62 (failed to flee a near-miss; on_critical_failure +0.10, decay -0.03)
  7:10   0.78
```

Epigenome at t=7:10:
```
speed_mult:      1.18  (clamped at trauma cap)
metabolism_mult: 1.14
size_mult:       1.0   (predation trauma doesn't shrink in our rules; only starvation does)
```

**t = 7:12 — PopulationManager scan fires**

```python
clusters = population_mgr.scan_stress_clusters(floor_1)
# stressed = [slime_03(0.78), slime_08(0.71), slime_12(0.82), slime_04(0.74)]
# spatial_cluster within radius 150 → cluster_A = [slime_03, slime_08, slime_12, slime_04]
# cluster_A.size = 4 ≥ min_cluster_size (3)
```

Build context:

```jsonc
{
  "pressure": {
    "type":     "predation",
    "nemesis":  "flying_eye",
    "severity": 0.76                      // mean cluster stress
  },
  "species": {
    "id":      "slime",
    "traits":  ["acidic_touch"],
    "genome":  {"size": 1.0, "speed": 50.0, "metabolism": 1.0,
                "perception_range": 100, "aggression": 0.4,
                "pigmentation": [0.4, 0.7, 0.4]},
    "senses":  {"sight": {"range": 100, "acuity": 1.0},
                "smell": {"range":  60, "acuity": 0.7},
                "tremorsense": {"range": 0, "acuity": 0.0},
                "thermal":     {"range": 0, "acuity": 0.0}}
  },
  "cluster_size": 4,
  "floor_context": {"index": 1, "light": 0.7, "resource_density": 0.55},
  "verb_manifest":   { /* §3.3 */ },
  "trait_codex":     { /* §3.2 */ },
  "subtree_library": { /* §3.4 */ }
}
```

Compute signature:

```python
sig = signature(context)   # hash("predation:flying_eye:slime:high")
sig in fast_lookup         # → False (novel)
```

**t = 7:12 — Slow path: Ollama call (async, non-blocking)**

While the call is in flight, cluster_A is injected with `dormancy` so behavior is sane during the wait. Total prompt ~1.2k tokens. Local Llama 3.1 8B Q5 returns in ~900ms:

```jsonc
{
  "use_existing":  true,
  "subtree_key":   "scatter_and_hide",
  "new_subtree":   null,
  "genome_delta":  {"pigmentation": [-0.10, -0.05, -0.10]},
  "trait_grant":   null,
  "rationale":     "Predator hunts visually from above; pack scatter reduces simultaneous-kill risk, hiding in moss tiles exploits cover. Slight darkening reduces aerial detection."
}
```

Pydantic validates:

- `use_existing=True` and `subtree_key="scatter_and_hide"` ∈ `SUBTREE_LIBRARY` ✓
- `genome_delta` keys ⊂ Genome fields; values within ±0.15 ✓
- `trait_grant` is None ✓

**Validation passed.**

**t = 7:13 — Inject + cache**

```python
for s in cluster_A:
    s.bt.adaptation_slot = SUBTREE_LIBRARY["scatter_and_hide"]
    s.tree_complexity_cost = estimate_complexity(scatter_and_hide) * 0.05  # +0.06/sec drain
    s.data.base_genome.pigmentation = clamp(... + delta)

fast_lookup[sig] = "scatter_and_hide"  # next time, no LLM
```

Slimes are now visibly darker green and run a different selector at the top of their tree:

```
adaptation_slot (scatter_and_hide):
  Selector:
    1. Sequence:
       QuerySense(sight, predator)        → SUCCESS
       Locomote(away_from + nearest_moss) → SUCCESS
       Hide                               → SUCCESS
       CheckInternal(stress, <, 0.4)      # exit when calm
    2. <falls through to base BT>
```

**t = 7:13 to 9:00 — Adapted behavior runs**

Outcomes (numbers chosen to illustrate, not predict):

- 2 of 4 slimes survive the next 90 seconds. Their stress decays to 0.3.
- 1 dies because the metabolic cost of the new subtree (+0.06/sec) tipped it into starvation while hiding.
- 1 dies because hiding in moss didn't help against flying_eye_03 which happened to land on the same moss patch.

**t = 9:00 — Fitness feedback**

```python
population_mgr.record_outcome(
    sig=sig,
    subtree="scatter_and_hide",
    survivors=2, deaths=2,
    mean_stress_drop=0.42,
)
```

If survival rate < threshold over multiple events, the cache entry is downgraded — next novel signature with this profile gets sent to the LLM again rather than served from cache. This is the only learning loop in v1; no GNN, no RL.

**t = 9:30 — Second cluster forms**

A different group of slimes (cluster_B), having witnessed deaths near the staircase, accumulates stress. PopulationManager fires again:

```python
sig_B = signature(context_B)              # SAME signature
fast_lookup[sig_B]                        # → "scatter_and_hide" (hit)
inject_subtree(cluster_B, "scatter_and_hide")  # 0 LLM tokens
```

This is the payoff of the cache. The first instance cost ~1.2k tokens; the second cost zero.

### 9.3 What this trace proves

Reading top to bottom:

1. **Reflex tier suffices for equilibrium.** The base BT runs for 5 minutes with no escalation.
2. **Epigenetics smooth the gap.** Between the first death and the cluster trigger, the slimes are *already* adapting (faster, more anxious) without any LLM call.
3. **PopulationManager only fires after sustained signal.** Stress crosses threshold, cluster size meets minimum, *then* a context is built.
4. **The signature cache is the real performance system.** First instance LLM-bound; subsequent identical pressure profiles are instant.
5. **Pydantic is the hallucination firewall.** The LLM cannot inject a verb that doesn't exist, a trait the species can't satisfy, or a genome change beyond the bound.
6. **Polymorphic verbs do the heavy lifting.** `Hide` works for slimes (find moss tile) and would work for goblins (find rock) without a single conditional in the BT.
7. **Failure is informative.** The slime that starved while hiding is correct behavior — it teaches the system that scatter_and_hide has a metabolic cost; if it underperforms it gets evicted from the cache.
8. **Async LLM keeps the tick deterministic.** While the Ollama call is in flight, the cluster runs `dormancy`. Sim time and wall time decouple cleanly.

### 9.4 What 10 generations later looks like (preview, Sprint 8+)

If predation pressure persists and `scatter_and_hide` keeps being injected, slimes inherit the darker pigmentation through reproduction (small drift each gen). At ~10 generations:

```python
population_mgr.observe(
    marker      = "darker pigmentation persisted via inheritance",
    generations = 10,
    fitness_under_marker > fitness_baseline,
)
# → trigger Baldwinization request
```

LLM is asked to bake the change in:

```jsonc
{
  "speciation": {
    "name":              "Shadow Slime",
    "parent":            "slime",
    "base_genome_patch": {"pigmentation": [0.2, 0.4, 0.2]},
    "traits_added":      ["camouflage"],
    "rationale":         "Sustained aerial predation has selected for visual cover. Codify."
  }
}
```

A new species_id is forked. The lineage ledger gains a node. The Slime population on Floor 1 now has both `slime` and `shadow_slime` lineages. **This is the moment the player sees the speciation event in the UI.** Until that moment, the simulation is a quietly humming ecology — which is the whole point.

---

## 10. Anti-patterns (things that will derail this project)

Hard rules. If you catch yourself doing any of these, stop and reread the principle.

| Anti-pattern | Why it kills the project | Correct move |
|---|---|---|
| Importing pygame anywhere under `sim/` | Couples sim to renderer; breaks headless tests; rebuilds the engine-fight you started this project to escape | Add `sim → render` to import-linter forbidden contracts; fail CI on violation |
| Render code mutating sim state | Sim becomes non-deterministic, untestable | Render is read-only over sim; if a render action implies a sim change, it goes through `app/` as an explicit command |
| Calling the LLM per organism per tick | Token cost explodes; emergence destroyed by central planner | PopulationManager + cluster + cache |
| Designing the full trait codex before coding | Design lock-in; never start | 6 traits, expand reactively |
| Adding pygame in Sprints 1–3 | Slows the only thing that matters: closed trophic loop | Headless until Sprint 4. No exceptions |
| Multiple species before stable single-species sim | Cascading bugs you can't isolate | One species, ten minutes stable, then add |
| Multi-floor before single-floor stable | Same | Same |
| GNN routing, custom Rust engine, multiprocessing | Premature; will not exist until v2 | Single-process Python with numpy hot paths |
| LLM authoring before LLM picking works | Validator and JSON schema not battle-tested | Pick from library first, author second |
| Letting the LLM write code or invent verbs | Hallucinations + crashes | Pydantic schema + whitelist; ValidationError = ignore |
| No fitness feedback on cached subtrees | Caches stale, ecosystem stuck on early-bad strategies | Track outcome per signature; downgrade poor performers |
| Treating epigenome as decoration | Lose the shock-absorber layer; LLM gets called too often | Epigenome must do real work between tier 0 and tier 3 |
| Synchronous Ollama calls in the tick loop | Sim freezes; tests become flaky | Always async; placeholder subtree (`dormancy`) while in flight |

---

## 11. Glossary

- **Base genome** — heritable floats per organism; mutate slowly via drift.
- **Epigenome** — multiplier layer on base genome; shifts in lifetime via stress; inherited; fades in absence of pressure.
- **Verb** — one of the 6 BT actions; same name everywhere; behavior depends on traits.
- **Trait** — entry in `TRAIT_CODEX`; grants a specific code-level effect.
- **Subtree** — small reusable BT plugged into the AdaptationSlot of a species' base tree.
- **Pressure vector** — multi-dimensional cluster-level signal driving prompt template selection.
- **Signature** — short hash of a context bucket; cache key for subtree decisions.
- **Speciation event** — Baldwinization moment; epigenetic marker becomes base genome; new species_id forked.
- **Stigmergy** — environmental information left by agents (scent, corpse, spore) that other agents can sense.
- **Polymorphic verb** — single named verb whose runtime behavior dispatches on the executing organism's traits.
- **AdaptationSlot** — designated swappable node inside the base BT for runtime subtree injection.
- **Sim** — `sim/` package; pure Python; never imports pygame.
- **Renderer** — `render/` package; pygame; reads sim, never writes.
- **Headless run** — sim executed with no renderer attached; what CI runs.

---

## 12. Open questions to resolve before Sprint 1

Don't write code under `sim/` until each of these has a one-line answer.

1. **Tick rate:** 1 Hz logical tick is the v1 default. Visual frame rate is 60 FPS rendering interpolated state. Confirm or override.
2. **Energy units and conversion rates:** pick once, stick to them. Recommend: 0.0–1.0 normalized for organisms; integer "calories" for moss/corpses convertible to organism energy via a fixed exchange rate.
3. **Cluster radius and min size:** starting values, tunable. Recommend: 150 units, 3 organisms.
4. **Stress threshold for trigger:** 0.7. Marker decay rate: 0.02 / sec when no stress events.
5. **Epigenome fade rate when pressure relieved:** exponential decay with τ ≈ 60 sec.
6. **Pigmentation delta semantics:** clamped to [0,1] per channel; LLM may shift each channel independently within ±0.15.
7. **Death broadcast radius:** equal to cluster_radius (150).
8. **Where does the LLM call live:** async background task, with `dormancy` injected as placeholder during flight; 5s budget.
9. **Save/load:** JSON snapshot of the floor each save tick; pydantic round-trips for free.
10. **Telemetry:** every LLM call logs request, response, validation verdict, and outcome over the next 60s of sim time. JSONL file under `runs/<timestamp>/`.

Recommended defaults: take all 10 as given unless you have a reason. Tune later from telemetry, not from intuition.

---

## 13. Project layout and dependency rules

```
living-dungeon/
├── pyproject.toml
├── .importlinter            # enforces dependency direction, see below
├── sim/
│   ├── __init__.py
│   ├── organism.py          # OrganismData, Organism, Genome, Epigenome
│   ├── world.py             # Floor, World, tile grid
│   ├── stigmergy.py         # numpy scalar grids
│   ├── senses.py            # SenseManager
│   ├── verbs.py             # 6 verbs as py_trees Behaviours
│   ├── conditions.py        # 4 conditions as py_trees Behaviours
│   ├── trees.py             # base tree builder, AdaptationSlot
│   ├── subtrees/            # the hardcoded subtree library
│   │   ├── __init__.py
│   │   ├── aggressive_foraging.py
│   │   ├── scatter_and_hide.py
│   │   ├── dormancy.py
│   │   └── migration_up.py
│   ├── traits.py            # TRAIT_CODEX + trait_effects
│   ├── trophic.py           # energy flow, decomposition
│   ├── pressure.py          # EvolutionaryPressure
│   ├── population.py        # PopulationManager, signatures, cache
│   └── tick.py              # step(world, dt)
├── ai/
│   ├── __init__.py
│   ├── client.py            # httpx → Ollama, async
│   ├── schemas.py           # LLMResponse pydantic = the firewall
│   ├── prompts.py           # system + per-pressure templates
│   └── adapter.py           # Ollama JSON → AdaptationSlot installation
├── render/
│   ├── __init__.py
│   ├── viewport.py          # pygame.draw.circle for organisms
│   ├── stigmergy_view.py    # surfarray heatmaps
│   └── debug_overlay.py     # stress/energy bars, cluster outlines
├── app/
│   ├── __init__.py
│   ├── main.py              # pygame loop, fixed-timestep
│   └── headless.py          # sim-only runner; CI uses this
├── tests/
│   ├── test_sim_*.py        # never import pygame
│   ├── test_ai_*.py         # mock Ollama with fixtures
│   └── test_render_*.py     # optional, pygame.HEADLESS via SDL_VIDEODRIVER=dummy
└── runs/                    # telemetry, logs, save snapshots
```

### Dependency rules (`.importlinter`)

```ini
[importlinter]
root_packages = sim ai render app

[importlinter:contract:sim_is_pure]
name = sim must not import pygame, render, ai, or app
type = forbidden
source_modules = sim
forbidden_modules = pygame render ai app

[importlinter:contract:ai_no_render]
name = ai must not import render or pygame
type = forbidden
source_modules = ai
forbidden_modules = pygame render

[importlinter:contract:render_no_writeback]
name = render must not import ai or app
type = forbidden
source_modules = render
forbidden_modules = ai app

[importlinter:contract:layered]
name = layered architecture
type = layers
layers =
    app
    render | ai
    sim
```

CI runs `lint-imports` on every commit. A violation fails the build. This is the cheapest, strongest guardrail in the project. Without it, in six months you'll find a `from pygame import Vector2` in `sim/organism.py` and the architecture is dead.

### Recommended dependencies

```toml
# pyproject.toml (excerpt)
[project]
dependencies = [
    "numpy>=1.26",
    "pydantic>=2.6",
    "py_trees>=2.2",
    "httpx>=0.27",
    "pygame-ce>=2.4",        # community edition; better-maintained than upstream pygame
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "import-linter>=2.0",
    "mypy>=1.8",
    "ruff>=0.4",
]
```

`pygame-ce` is preferable to plain `pygame` — same API, more active maintenance, faster bug fixes. Both work for v1; you can swap freely.

---

## 14. Why pygame is correct here (and where it ends)

Pygame's role in this project is small, well-defined, and cheap to replace later.

**What it gives us:**

- `pygame.draw.circle` and `pygame.draw.rect` for organisms and tiles. Sprint 4 visualization is ~100 lines.
- `pygame.surfarray.make_surface` to render the numpy stigmergy grid as a heatmap with no copy gymnastics. This is genuinely the cleanest path.
- `pygame.Rect`, event loop, fixed-timestep helpers via `pygame.time.Clock`. Standard fare.
- Mature, documented, well-known. The PDFs you have are sufficient — `pygame.draw`, `pygame.Surface`, `pygame.surfarray`, `pygame.sprite`, `pygame.time`, `pygame.event` are the only modules we'll use for a long time.

**What we deliberately don't use:**

- `pygame.sprite` group hierarchies for sim entities. Sprites are render-only adapters that read from `Organism` snapshots.
- Any pygame-native game-state container. The world lives in `sim/`, not in pygame.
- Pygame for input handling that drives sim logic directly. Input events go through `app/` as commands to the sim.

**When pygame stops being the right answer:**

- Above ~5,000 organisms on screen with stigmergy heatmaps. Profile first; numpy + dirty-rect updates will hold longer than you think.
- When you want polished 2D art with shaders, particles, audio, controllers. Move to [Arcade](https://api.arcade.academy/), [pyglet](https://pyglet.org/), or eventually a Godot/Bevy port. Because `sim/` is engine-agnostic, that port is mechanical.

This is the correct pragmatic answer for solo-dev iteration speed. Don't second-guess it.
