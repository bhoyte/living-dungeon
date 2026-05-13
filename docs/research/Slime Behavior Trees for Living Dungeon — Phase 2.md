# Slime Behavior Trees for Living Dungeon — Phase 2

## Overview

This document proposes a behavior tree (BT) architecture for slime creatures in the Living Dungeon project, designed to slot cleanly into the `creatures-build-playbook.md` Phase-2 build plan and the `creatures-spec-v1.md` contracts. All trees are expressed using the project's **fixed verb manifest** (`Locomote`, `Interact`, `Emit`, `Construct`, `Rest`, `Hide`) and **four condition nodes** (`QuerySense`, `CheckInternal`, `CheckEnv`, `CheckCooldown`), wired through `py_trees` with an `AdaptationSlot` for runtime subtree injection[^1][^2]. No new verbs or primitives are invented — every behavior below is expressible from the existing manifest.

The slime archetypes are drawn from two traditions that complement each other well:

- **D&D / tabletop ooze tradition** (Gray Ooze, Gelatinous Cube, Black Pudding, Ochre Jelly): low-intelligence, sensory-driven, ambush-and-dissolve predators with amorphous, resilient bodies[^3][^4][^5].
- **Isekai anime slime tradition** (*That Time I Got Reincarnated as a Slime*, *Re:Monster*): slimes as ascendant beings capable of predation, absorption, mimicry, and evolutionary growth triggered by environmental pressure[^6][^7][^8].

The two traditions map naturally onto the project's **tiered cognition model**: D&D slime reflexes live at Tier 0 (base BT, every tick), while isekai-style adaptive behaviors emerge at Tier 2–3 (subtree injection, LLM slow path) via the `AdaptationSlot` after the cluster stress threshold is crossed[^6][^8].

***

## Trait Codex Additions (Slime-Specific)

The North Star doc specifies 6 starter traits, explicitly inviting reactive growth. The following traits add slime-native behaviors while each carrying a real Python hook in `sim/trait_effects.py`.

| Trait Key | Cost | Grants | Prerequisite | D&D Inspiration | Isekai Inspiration |
|---|---|---|---|---|---|
| `acidic_touch` | 1 | `damage_on_contact` + corrodes metal armor on `Interact` | None | Gray Ooze pseudopod, Black Pudding[^4][^5] | — |
| `amorphous` | 1 | `can_pass_through_narrow_tiles` — bypasses wall adjacency checks | None | All oozes[^3] | Rimuru body morphing[^8] |
| `false_appearance` | 1 | `perception_penalty_to_observers` when `Rest` on wet/dark tile | None | Gray Ooze false appearance[^4] | Aqua Slime tile mimicry[^7] |
| `split_on_damage` | 2 | On reaching `energy < 0.25`, spawn one child organism at half stats | None | Ochre Jelly lightning split[^3] | Re:Monster self-replication[^7] |
| `predation_absorption` | 2 | `energy_from_corpses` + copies one trait from consumed entity (LLM slow path) | `acidic_touch` | Gelatinous Cube engulf[^3] | Rimuru Predation/Gluttony[^6] |
| `sweet_scent` | 1 | `emit_lure_pheromone` into `fields.sweet` | None | — | Lure behavior for passive foraging[^7] |
| `tremorsense_core` | 2 | `tremorsense_range_+120` | None | Gelatinous Cube blindsight 60 ft.[^3] | — |
| `spore_burst` | 2 | On death, emit spike into `fields.spore` | None | Decomposer loop deposit | Re:Monster Gray Slime fluid control[^7] |
| `lava_mimicry` | 3 | `false_appearance` on lava/fire tiles + heat immunity | `false_appearance` | — | Re:Monster Lava Slime ambush[^7] |
| `infused_restoration` | 2 | Passive: restore `energy += fields.mana_geo * 0.02 / tick` | None | — | Re:Monster infused liquid restoration[^7] |

All traits follow the `TRAIT_CODEX` schema: `{"cost": N, "grants": "...", "prereq": "..."}`. The LLM may only grant traits already present in this codex. Traits with `prereq` enforce the semantic validation layer before any adoption[^6].

***

## Slime Species Definitions (`OrganismData` Templates)

Each species is a `species_id` key differentiated by its `base_genome`, `traits`, and `senses`. No subclasses are added — the runtime `Organism` class handles all of them[^6].

### 1. `cave_slime` — The Starter Species (Sprint 2)

The project's canonical first species, analogous to the paper prototype slime in the North Star document. This is the species to stabilize before adding any other.

```python
OrganismData(
    species_id    = "cave_slime",
    trophic_level = 2,
    base_genome   = Genome(
        size             = 0.8,
        speed            = 22.0,
        metabolism       = 0.9,
        perception_range = 80.0,
        aggression       = 0.35,
        pigmentation     = (0.3, 0.65, 0.3),   # green-grey
    ),
    traits  = ["acidic_touch"],
    senses  = {
        "sight": SenseChannel(range=80.0,  acuity=0.7),
        "smell": SenseChannel(range=120.0, acuity=0.9),
    },
)
```

**Behavior profile:** Chemosensory-primary forager. Wanders by smell gradient, eats moss on contact. Flees on high stress. This is the organism that should run 600 ticks stably before anything else is wired in.

***

### 2. `gray_ooze` — Ambush Predator

Modeled on D&D Gray Ooze: motionless camouflage, slow pursuer, metal-corroding pseudopod[^4][^5].

```python
OrganismData(
    species_id    = "gray_ooze",
    trophic_level = 2,
    base_genome   = Genome(
        size             = 1.1,
        speed            = 10.0,       # very slow
        metabolism       = 0.7,        # low cost = patient ambusher
        perception_range = 60.0,
        aggression       = 0.6,
        pigmentation     = (0.45, 0.45, 0.45),
    ),
    traits  = ["acidic_touch", "false_appearance"],
    senses  = {
        "sight":       SenseChannel(range=0.0,   acuity=0.0),   # blind
        "tremorsense": SenseChannel(range=60.0,  acuity=0.85),
    },
)
```

**Behavior profile:** Lies still disguised as wet rock. Waits for prey in tremor range. Slow relentless pursuit once triggered. No flight behavior — retreats only when forced by energy threshold.

***

### 3. `gelatinous_cube` — Floor Sweeper

The classic dungeon cleaner: mindless, transparent, engulfs anything that doesn't move[^3][^5].

```python
OrganismData(
    species_id    = "gelatinous_cube",
    trophic_level = 2,
    base_genome   = Genome(
        size             = 2.5,        # large
        speed            = 8.0,
        metabolism       = 1.3,        # large body = high burn
        perception_range = 60.0,
        aggression       = 0.85,
        pigmentation     = (0.85, 0.95, 0.85),  # near-transparent
    ),
    traits  = ["acidic_touch", "tremorsense_core", "predation_absorption"],
    senses  = {
        "tremorsense": SenseChannel(range=60.0, acuity=1.0),
        "sight":       SenseChannel(range=0.0,  acuity=0.0),
    },
)
```

**Behavior profile:** Methodical floor patrol. Engulfs prey via `Interact(prey)` with `predation_absorption` effect. Deposits dissolved remains into `fields.corpse`. No avoidance behavior — just slow inevitable advance.

***

### 4. `black_pudding` — Splitter

The black pudding is a mid-tier threat known for splitting when struck and dissolving organic material[^3][^5].

```python
OrganismData(
    species_id    = "black_pudding",
    trophic_level = 2,
    base_genome   = Genome(
        size             = 1.6,
        speed            = 15.0,
        metabolism       = 1.1,
        perception_range = 60.0,
        aggression       = 0.75,
        pigmentation     = (0.1, 0.05, 0.05),  # near-black
    ),
    traits  = ["acidic_touch", "amorphous", "split_on_damage"],
    senses  = {
        "tremorsense": SenseChannel(range=60.0, acuity=0.9),
        "sight":       SenseChannel(range=0.0,  acuity=0.0),
    },
)
```

**Behavior profile:** Aggressive melee. When energy drops below 0.25 (proxy for injury), `split_on_damage` spawns a child. Children inherit reduced stats. No coordination between splits — each acts independently. Creates escalating swarm scenarios if unchecked.

***

### 5. `ochre_jelly` — Reactive Chaser

The ochre jelly is the most mobile and reactive of the classic oozes, with the highest intelligence (still minimal)[^3][^5].

```python
OrganismData(
    species_id    = "ochre_jelly",
    trophic_level = 2,
    base_genome   = Genome(
        size             = 1.3,
        speed            = 30.0,       # notably faster than other oozes
        metabolism       = 1.0,
        perception_range = 90.0,
        aggression       = 0.6,
        pigmentation     = (0.8, 0.65, 0.1),   # yellow-orange
    ),
    traits  = ["acidic_touch", "amorphous"],
    senses  = {
        "sight":       SenseChannel(range=90.0,  acuity=0.6),
        "tremorsense": SenseChannel(range=60.0,  acuity=0.75),
    },
)
```

**Behavior profile:** Active pursuit hunter. Unlike other ooze archetypes, actually gives chase. Will split on heavy damage. The most suitable candidate for the `aggressive_foraging` subtree injection under predation pressure.

***

### 6. `proto_slime` — Isekai Ascendant (Adaptation Showcase Species)

The flagship isekai-style organism. Starts weak, gains traits through `predation_absorption`. Designed to demonstrate the full Tier 0→3 cognition pipeline. Inspired by Rimuru's early-game predation loop and Re:Monster's absorption mechanics[^6][^8][^7].

```python
OrganismData(
    species_id    = "proto_slime",
    trophic_level = 1,               # starts as scavenger
    base_genome   = Genome(
        size             = 0.6,
        speed            = 18.0,
        metabolism       = 0.8,
        perception_range = 100.0,
        aggression       = 0.3,
        pigmentation     = (0.4, 0.75, 0.9),   # translucent blue
    ),
    traits  = ["predation_absorption"],          # the seed trait
    senses  = {
        "sight": SenseChannel(range=100.0, acuity=0.85),
        "smell": SenseChannel(range=140.0, acuity=0.95),
    },
)
```

**Behavior profile:** Cautious early-game. Heavy reliance on smell to avoid predators and find food. Once a kill is made, `predation_absorption` queues a trait-copy request through the LLM slow path. Demonstrated epigenetic drift: under prolonged predation pressure, `aggression_mult` and `speed_mult` climb while `size_mult` drops (smaller profile, harder to hit).

***

## Base Behavior Trees

All trees are expressed as `py_trees` `Selector` / `Sequence` compositions. Each tree includes an **`AdaptationSlot`** — a named `py_trees.behaviours.Dummy` node that the `PopulationManager` can replace at runtime via subtree injection.

### BT-1: `cave_slime` Base Tree (Sprint 2 Target)

This is the tree to implement first and run for 600 ticks deterministically[^6].

```
Selector [root]
├── Sequence [stress_response]               # Priority 1: flee if stressed
│   ├── CheckInternal(stress, >, 0.65)
│   └── Locomote(safety)                     # toward fields.alarm inverse gradient
│
├── Sequence [hunger_forage]                 # Priority 2: eat if hungry
│   ├── CheckInternal(energy, <, 0.5)
│   ├── Selector [find_food]
│   │   ├── Sequence [entity_food]
│   │   │   ├── QuerySense(smell, food)
│   │   │   └── Locomote(food)
│   │   └── Sequence [field_food]            # fallback: follow sweet gradient
│   │       ├── CheckEnv(fields.sweet, >, 0.1)
│   │       └── Locomote(up_gradient)
│   └── Interact(food)                       # eat on contact
│
├── [AdaptationSlot]                         # injected by PopulationManager
│
└── Locomote(wander)                         # Priority 4: idle wander
```

**Sprint 2 test assertion:** `cave_slime` wanders, smells moss, locomotes toward it, eats, repeats. Starves when moss is absent. Dies and deposits to `fields.corpse`. All asserted in pytest without renderer.

***

### BT-2: `gray_ooze` Base Tree (Ambush Archetype)

```
Selector [root]
├── Sequence [hunt_sequence]                 # tremorsense-triggered pursuit
│   ├── QuerySense(tremorsense, prey)
│   ├── Selector [pursue_or_wait]
│   │   ├── Sequence [close_range_attack]    # prey within strike distance
│   │   │   ├── CheckInternal(distance_to_prey, <, 15.0)
│   │   │   └── Interact(prey)
│   │   └── Locomote(prey)                   # slow pursuit
│
├── Sequence [ambush_wait]                   # idle disguised
│   ├── CheckEnv(tile.wet, ==, true)         # valid ambush tile
│   ├── CheckInternal(energy, >, 0.4)        # not desperate
│   └── Rest()                               # false_appearance activates during Rest
│
├── [AdaptationSlot]
│
└── Locomote(wander)                         # no valid ambush tile found
```

**Key mechanic:** `false_appearance` trait effect fires whenever the organism is in `Rest` state on a wet/dark tile, applying a `perception_penalty` to observers in `QuerySense`. This is pure trait dispatch — no BT change needed[^4][^5].

***

### BT-3: `gelatinous_cube` Base Tree (Floor Patrol Archetype)

```
Selector [root]
├── Sequence [engulf]                        # always-on predator
│   ├── QuerySense(tremorsense, prey)
│   ├── Locomote(prey)
│   └── Interact(prey)                       # predation_absorption fires here
│
├── Sequence [corpse_scavenge]               # eat leftover field deposits
│   ├── CheckEnv(fields.corpse, >, 0.15)
│   ├── Locomote(up_gradient)
│   └── Interact(corpse_field)
│
├── [AdaptationSlot]
│
└── Locomote(patrol)                         # systematic grid sweep
```

**Note:** `patrol` is a specialized `Locomote` target that moves in a grid-sweep pattern. Implemented as a `Locomote(fixed_waypoint_cycle)` target selector seeded from the organism's starting position. No new verb needed — the waypoint list is state on the `Organism` instance[^3].

***

### BT-4: `black_pudding` Base Tree (Splitter Archetype)

```
Selector [root]
├── Sequence [split_behavior]                # energy proxy for injury
│   ├── CheckInternal(energy, <, 0.25)
│   ├── CheckCooldown(split_cooldown)        # prevent infinite splits
│   └── Interact(split)                      # split_on_damage hook fires
│
├── Sequence [attack]
│   ├── QuerySense(tremorsense, prey)
│   └── Sequence [chase_eat]
│       ├── Locomote(prey)
│       └── Interact(prey)
│
├── [AdaptationSlot]
│
└── Locomote(wander)
```

**Split telemetry:** `Interact(split)` must emit a `creature.split` telemetry event with `parent_id`, `child_id`, `floor`, `tick`. This feeds the population manager's energy accounting assertions and ensures the energy conservation epsilon (`1e-3`) holds across splits[^6].

***

### BT-5: `proto_slime` Base Tree (Isekai Ascendant Archetype)

This is the most complex base tree, reflecting the *proto_slime*'s higher intelligence and isekai-inspired awareness. It introduces a **curiosity node** — the organism investigates novel entities before attacking, which is the mechanism that triggers the LLM absorption path[^6][^8].

```
Selector [root]
├── Sequence [survival_priority]             # life above all
│   ├── CheckInternal(energy, <, 0.2)
│   ├── CheckInternal(stress, >, 0.8)
│   └── Locomote(safety)
│
├── Sequence [predation_loop]                # core absorption behavior
│   ├── CheckInternal(energy, <, 0.6)
│   ├── QuerySense(sight, prey)
│   ├── Locomote(prey)
│   └── Interact(prey)                       # predation_absorption hook → LLM queue
│
├── Sequence [scavenge]
│   ├── CheckEnv(fields.corpse, >, 0.1)
│   ├── Locomote(up_gradient)
│   └── Interact(corpse_field)
│
├── Sequence [mana_harvest]                  # infused_restoration ambient recharge
│   ├── CheckInternal(energy, <, 0.8)
│   ├── CheckEnv(fields.mana_geo, >, 0.3)
│   └── Rest()                               # infused_restoration applies during Rest
│
├── [AdaptationSlot]                         # receives isekai-style evolved subtrees
│
└── Locomote(wander)
```

**Absorption LLM path:** When `Interact(prey)` succeeds and `predation_absorption` is in `traits`, the `PopulationManager` queues a trait-copy request at the next cluster scan. The BT itself does not change — the `AdaptationSlot` may receive an upgraded subtree that uses a newly granted trait in subsequent ticks.

***

## Subtree Library Additions

These extend the 4 hardcoded subtrees from the North Star (`aggressive_foraging`, `scatter_and_hide`, `dormancy`, `migration_up`) with slime-native behaviors. Each is a named `py_trees` builder function in `sim/subtrees/`[^6].

### `ST-5: ooze_ambush_lock`

> Triggered for ooze clusters that have a viable ambush tile nearby and have experienced recent starvation pressure.

```
Sequence [ooze_ambush_lock]
├── CheckEnv(tile.wet, ==, true)
├── Emit(substance=alarm)                    # suppress nearby foragers from area
└── Rest()                                   # false_appearance active
```

**Cluster context:** `pressure.starvation > 0.5 AND floor.wet_tile_density > 0.3`

***

### `ST-6: split_surge`

> Triggered for `black_pudding` clusters under heavy predation — deliberately trigger splits to flood the floor with sub-puddings.

```
Selector [split_surge]
├── Sequence [trigger_split]
│   ├── CheckInternal(energy, >, 0.5)        # only split when healthy enough
│   └── Interact(split)
└── Locomote(prey)
```

**Cluster context:** `pressure.predation > 0.7 AND species == "black_pudding"`

***

### `ST-7: absorption_sprint`

> Injected into `proto_slime` clusters under abundance pressure — maximize absorption events to accelerate trait acquisition.

```
Sequence [absorption_sprint]
├── CheckInternal(energy, >, 0.6)
├── QuerySense(sight, prey)
├── Locomote(prey)
└── Interact(prey)
```

**Cluster context:** `pressure.abundance > 0.6`

***

### `ST-8: mana_bloom_feed`

> Injected when floor `mana_geo` spikes — organisms with `infused_restoration` cluster around mana sources for passive gain.

```
Sequence [mana_bloom_feed]
├── CheckEnv(fields.mana_geo, >, 0.5)
├── QuerySense(smell, resource_mana)
├── Locomote(resource_mana)
└── Rest()
```

**Cluster context:** `floor.mana_geo_avg > 0.45`

***

### `ST-9: dissolve_and_scatter`

> For clusters facing an overwhelming predator — organisms attempt to dissolve into the environment by resting in tile types that conceal them, emitting false trails.

```
Sequence [dissolve_and_scatter]
├── Emit(substance=sweet)                    # false trail to confuse predator
├── Selector [find_cover]
│   ├── Sequence [wet_tile]
│   │   ├── CheckEnv(tile.wet, ==, true)
│   │   └── Hide()
│   └── Hide()                               # fallback to any concealment
└── Rest()
```

**Cluster context:** `pressure.predation > 0.85`

***

## Trait–Field–Behavior Interaction Matrix

This matrix shows how slime traits interact with the existing `FieldMap` fields, clarifying what each trait reads or writes per tick[^6].

| Trait | Reads Field | Writes Field | Verb Dispatched | Epigenome Effect |
|---|---|---|---|---|
| `acidic_touch` | — | `acidity` (+0.02 on contact) | `Interact` damage | `aggression_mult` +0.05 on kill |
| `amorphous` | `tile.narrow` | — | `Locomote` bypass | None |
| `false_appearance` | `tile.wet`, `light` | — | `Rest` (state) | None |
| `split_on_damage` | — | spawns child organism | `Interact(split)` | Child inherits `epigenome` snapshot |
| `predation_absorption` | — | `fields.corpse` (from consumed entity) | `Interact` | `size_mult` +0.1 after absorption |
| `sweet_scent` | — | `fields.sweet` (+0.3/tick) | `Emit(sweet)` | None |
| `tremorsense_core` | `tremor` field | — | `QuerySense(tremorsense)` | `perception_mult` +0.05 under famine |
| `spore_burst` | — | `fields.spore` (+0.5 on death) | Death hook | — |
| `infused_restoration` | `fields.mana_geo` | — | `Rest` passive | `metabolism_mult` -0.05 under abundance |
| `lava_mimicry` | `tile.lava` | — | `Rest` (false appearance) | None |

***

## Epigenome Pressure Response Map

Each pressure vector component (from `EvolutionaryPressure`) produces specific epigenome drift in slime organisms, following the existing `tau ≈ 60 sec` fade policy[^6].

| Pressure Type | Dominant Species Response | `speed_mult` | `metabolism_mult` | `size_mult` | `aggression_mult` |
|---|---|---|---|---|---|
| `starvation` | Shrink body, slow metabolism, scout wider | +0.05 | -0.08 | -0.10 | +0.05 |
| `predation` | Speed burst, smaller profile | +0.15 | +0.10 | -0.05 | -0.10 |
| `abundance` | Grow, store energy, reduce motion | -0.05 | -0.05 | +0.10 | -0.05 |
| `isolation` | Speed up, seek gradient | +0.10 | +0.05 | 0 | 0 |

All deltas are per-event, clamped per-channel to `[-0.15, +0.15]` per the v1 constants. Epigenome resets toward `1.0` at `0.02 / sec` when pressure is absent[^6].

***

## Implementation Sprint Mapping

| Sprint | Slime Deliverable | Gate |
|---|---|---|
| 2 | `cave_slime` with BT-1; `acidic_touch` + `sweet_scent` traits wired | 600-tick headless: wander, forage, eat, starve, die — asserted in pytest |
| 3 | Closed trophic loop with `spore_burst` on death feeding `fields.spore` → producer seeding | Energy accounting within `1e-3`; population non-zero in 10-minute run |
| 4 | `gray_ooze` (BT-2) + `black_pudding` (BT-4); `false_appearance` + `split_on_damage` wired | `false_appearance` demonstrably reduces `QuerySense` success rate; `split_on_damage` produces valid child organisms |
| 5 | Epigenome pressure response map active; pigmentation tween from `aggression_mult` drift | Predation pressure visibly changes `black_pudding` pigmentation over 60 seconds |
| 6 | `gelatinous_cube` (BT-3) + ST-5/ST-6 subtrees; `PopulationManager` injects `ooze_ambush_lock` under starvation | Stressed cluster receives `ooze_ambush_lock`; observable in telemetry AND in `fields.alarm` emission |
| 7 | `proto_slime` (BT-5) + `predation_absorption` LLM path; ST-7/ST-8 | LLM trait-copy request generated, validated, cached; second encounter hits cache; mocked Ollama test passes |
| 8+ | `lava_mimicry`, `gelatinous_cube` patrol AI, speciation events for `proto_slime` | — |

***

## LLM Prompt Template Additions

Two new prompt templates are proposed for the `ai/prompts.py` module, extending the v1 `starvation` and `predation` templates[^6].

### `absorption_event` Template

**Trigger condition:** `proto_slime` cluster has at least one successful `predation_absorption` interaction and has no prior trait-grant cached for the consumed species.

```
{base_system_prompt}

Context type: absorption_event
Consumed species: {consumed_species_id}
Consumer traits: {consumer.traits}
Consumer trophic level: {consumer.trophic_level}
Available traits to grant: {TRAIT_CODEX}
Absorbed entity genome snapshot: {consumed_genome}

Bias: grant the trait from TRAIT_CODEX that most plausibly derives from
the consumed entity's genome profile. Prefer traits the consumer does NOT
already have. Do not exceed trait cost budget: {remaining_cost_budget}.
```

### `ooze_colony` Template

**Trigger condition:** cluster of 3+ ooze-type organisms (`gray_ooze`, `black_pudding`) with `pressure.starvation > 0.6` on a floor with low light.

```
{base_system_prompt}

Context type: ooze_colony
Floor light level: {floor.light}
Wet tile density: {floor.wet_tile_density}
Cluster species: {cluster.species_distribution}
Available subtrees: {SUBTREE_LIBRARY}

Bias: prefer subtrees that leverage low-light and wet-tile conditions.
Dormancy and ambush subtrees are appropriate. Aggressive foraging is
inappropriate unless starvation is severe (>0.8).
```

***

## Field Config Additions

Two new fields are proposed for `FIELD_CONFIG` in `sim/fields.py` to support slime-specific emission behaviors[^6].

```python
"acid":  FieldConfig(decay=0.060, diffuse=0.080),   # deposited by acidic_touch kills
"lure":  FieldConfig(decay=0.040, diffuse=0.180),   # deposited by sweet_scent emit
```

- `fields.acid`: deposited at contact-kill sites; read by `CheckEnv` for environmental hazard detection by other species.
- `fields.lure`: deposited by `sweet_scent` emission; read as an alternative `food` gradient by prey organisms walking into the trap.

Both conform to the existing `FieldMap.step()` pipeline — no architectural change, only new config entries.

***

## Non-Negotiable Contract Compliance Notes

- **No new verbs or conditions** are introduced. All behaviors compose from the 6 verbs and 4 conditions in the manifest.
- **`FieldMap` is canonical.** All field reads and writes go through `FieldMap`, not `StigmergyMap`.
- **Tick order preserved.** Trait effects that read fields (e.g., `infused_restoration` reading `mana_geo`) fire during the **metabolism** tick stage (step 7), after behavior (step 6). Field writes from `Emit` fire during step 6 so they are visible to other organisms in the next tick's sensing step.
- **LLM is slow path only.** The `predation_absorption` trait-grant request is queued via `PopulationManager` — it never blocks the tick loop. The organism runs its base BT with existing traits while the request is in flight.
- **Sim never imports renderer.** All slime color/pigmentation values are data fields on `Epigenome`; the renderer reads them during its own frame — the simulation never calls into `render/`[^6].

---

## References

1. [Behavior tree (artificial intelligence, robotics and control) - Wikipedia](https://en.wikipedia.org/wiki/Behavior_tree_(artificial_intelligence,_robotics_and_control))

2. [Behavior trees for AI: How they work](https://www.gamedeveloper.com/programming/behavior-trees-for-ai-how-they-work) - An introduction to Behavior Trees, with examples and in-depth descriptions, as well as some tips on ...

3. [Dissecting the 5E D&D Ooze Creature Type - Nerdarchy](https://nerdarchy.com/dissecting-the-5e-dd-ooze-creature-type/) - This thing takes people, swallows their memories and then sends copies of them out to trick their fr...

4. [Gray Ooze | D&D 5th Edition on Roll20 Compendium](https://roll20.net/compendium/dnd5e/Gray%20Ooze) - Skills Stealth +2 ; Damage Resistance Acid, Cold, Fire ; Condition Immunities Blinded, Charmed, Deaf...

5. [Ooze Tactics - The Monsters Know What They're Doing](https://www.themonstersknow.com/ooze-tactics/) - The gray ooze begins with 22 hp, and its predatory behavior is interrupted when it's reduced to 8 hp...

6. [Arts](https://that-time-i-got-reincarnated-as-a-slime.fandom.com/wiki/Rimuru_Tempest/Abilities_and_Gear) - Physical Attack Nullification Pain Nullification Natural Effects Nullification Abnormal Condition Nu...

7. [Slime | Re:Monster Wiki - Fandom](https://re-monster.fandom.com/wiki/Slime) - Slimes are Monsters with an inconsistent form, resembling a blob. They are considered troublesome op...

8. [Rimuru Tempest - Tensei Shitara Slime Datta Ken Wiki - Fandom](https://tensura.fandom.com/wiki/Rimuru_Tempest) - Rimuru is an eccentric and childish person by nature but this shouldn't be mistaken for immaturity a...

