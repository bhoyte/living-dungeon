# Living Dungeon Spec (Phase-2: Creatures + Adaptation)

Status: Active, Deferred to Phase-2  
Effective date: 2026-05-07  
Owner: Systems + Design  
Scope: Normative implementation specification for post-ecosystem creature integration

---

## 0) Governance and scope

This file defines phase-2 implementation targets and requirements.

Activation trigger:

- Phase-2 work begins only after ecosystem-first phase acceptance gates in `docs/canon/ecosystem-roadmap.md` are satisfied.

Standards:

1. Normative requirements use RFC 2119 terms (`MUST`, `SHOULD`, `MAY`).

---

## 1) Product intent and non-negotiables

This phase defines creature and adaptation systems that layer on top of an already-stable dungeon ecosystem. Behavior emerges from local constraints (energy, fields, stress, senses). The LLM remains rare, asynchronous, and never part of the per-tick control loop.

The following are mandatory for phase-2:

1. One organism runtime model (`Organism`) with data-model differentiation (`OrganismData`).
2. Deterministic, testable headless tick as the primary artifact.
3. Tiered cognition: reflex and subtree cache first; LLM only for slow-path adaptation.
4. Fixed verb/condition manifest for v1. LLM cannot invent runtime primitives.
5. Closed trophic loop gate after ecosystem baseline is accepted.
6. Sim/render separation: simulation MUST NOT import renderer.

Out of scope for v1:

- ECS migration (candidate post-v1).
- Dynamic lineage UI and broad speciation feature set.
- Advanced V2 chemistry/explosive chain-reaction field mechanics.

---

## 2) Canonical architecture decisions

### 2.1 Architecture mode

v1 architecture is systems-of-functions over explicit world state. ECS is deferred.

### 2.2 Environment model migration decision

`FieldMap` is the active architecture target. `StigmergyMap` is deprecated and MUST NOT be used as a primary abstraction.

Required mapping:

| Deprecated | Canonical |
|---|---|
| `StigmergyMap.grids["sweet"]` | `FieldMap["sweet"]` |
| `StigmergyMap.grids["alarm"]` | `FieldMap["alarm"]` |
| `StigmergyMap.grids["corpse"]` | `FieldMap["corpse"]` |
| `StigmergyMap.grids["spore"]` | `FieldMap["spore"]` |

Rule:

- Geological and stigmergy fields share one storage/update pipeline (`FieldMap`) with per-field parameters.

### 2.3 Tick order

Per tick, execute in this order:

1. Spatial index build
2. Light update (special field path)
3. Field diffusion/decay/sources/sinks
4. Field reactions (quiet v1 reactions)
5. Sensing
6. Behavior (`py_trees`)
7. Metabolism
8. Epigenome update
9. Population adaptation/caching pipeline
10. Reproduction
11. Death and cleanup

Any change to this order MUST include an updated rationale and test updates.

---

## 3) Compatibility and interface contracts

This section resolves prior contract drift around `EnvView`, `CheckEnv`, and `QuerySense`.

### 3.1 `EnvView` contract (normative)

`EnvView` MUST include:

- `floor: int`
- `tile: str`
- `fields: dict[str, float]`
- `tile_props: dict[str, float | bool | str]`
- `light: float`
- `mana: float` (compat alias; derived from `fields.mana_geo`)

Rules:

- `mana` is compatibility-only and SHOULD be removed post-v1 when all callsites use `fields`.
- Missing fields MUST default to a documented safe value, never implicit `None`.

### 3.2 `CheckEnv` contract

Signature:

- `CheckEnv(path: str, op: str, value: Any) -> bool`

Allowed `path` forms:

- `tile.composition`
- `tile.<property>`
- `fields.<field_name>`
- `env.light`
- `env.mana` (deprecated alias to `fields.mana_geo`)

Operators:

- `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`

Failure behavior:

- Invalid path or op returns `FAILURE` and emits debug event; does not crash tick.

### 3.3 `QuerySense` contract

Signature:

- `QuerySense(modality: str, target: str) -> SenseResult`

Allowed modalities in v1:

- `sight`, `smell`

Target resolution matrix (normative v1 mapping):

| `target` token | Selection pipeline | Data source |
|---|---|---|
| `predator` | nearest hostile entity in LOS/range | entity index + sight/smell channels |
| `prey` | nearest edible entity in LOS/range | entity index + sight/smell channels |
| `food` | nearest valid food source for caller trophic profile | entity index, then `fields.sweet` gradient fallback |
| `safety` | nearest tile that lowers threat score | tile scan + `fields.alarm` inverse gradient |
| `resource_mana` | strongest reachable `fields.mana_geo` gradient | `fields.mana_geo` |

Resolution order:

1. If both sight and smell produce candidates for same token, choose higher confidence candidate.
2. If confidence ties, choose smallest distance.
3. If distance ties, choose lowest stable `target_id`.
4. If no entity candidate exists for `food`/`resource_mana`, fallback to field gradient result.
5. If token is unknown, return `success=false` and emit telemetry event.

Required result fields:

- `success: bool`
- `target_id: int | None`
- `distance: float | None`
- `gradient: tuple[float, float] | None`

Tie-breakers:

1. Highest confidence
2. Smallest distance
3. Lowest stable `target_id` (deterministic fallback)

Timeout/failure:

- On unavailable sense data, return `success=false`; do not throw.

### 3.4 Transition policy

During migration:

- Old callsites MAY continue using deprecated names only via explicit alias table.
- Alias table MUST be centralized and versioned.
- New features MUST use the terms defined in this document.
- `StigmergyMap` read-only adapter MAY exist only through Sprint 6; adapter writes are prohibited immediately.
- All adapter paths MUST be removed before Sprint 7 acceptance.

---

## 4) v1 defaults (versioned constants)

Version: `v1-defaults-2026-05-07`

These constants are locked for pre-Sprint-1 and can change only through explicit revision.

- Logical tick rate: `1 Hz`
- Render frame rate target: `60 FPS` (non-normative for simulation correctness)
- Organism energy domain: `[0.0, 1.0]`
- Cluster trigger stress threshold: `0.70`
- Cluster min size: `3`
- Stress marker decay when pressure absent: `0.02 / sec`
- Epigenome fade time constant: `tau ~= 60 sec`
- Pigmentation delta clamp (if used): per channel `[-0.15, +0.15]`, total clamped `[0,1]`
- LLM request budget per cluster request: `5 sec timeout`
- LLM retry max attempts: `2`
- Circuit-open threshold: `3` consecutive failed requests per cluster signature
- Circuit cooldown before retry: `60 sec`

Field defaults (starter set; tune via telemetry only):

- `sweet`: decay `0.050`, diffuse `0.150`
- `alarm`: decay `0.080`, diffuse `0.200`
- `corpse`: decay `0.010`, diffuse `0.050`
- `spore`: decay `0.020`, diffuse `0.100`

All constants MUST be referenced from a single shared source in implementation.

### 4.1 Determinism and numeric tolerance policy

Required test protocol for deterministic gates:

- Seed policy: all deterministic tests MUST set explicit world + RNG seeds and log them.
- Run length: deterministic gate tests MUST run at least 100 ticks unless a stricter gate overrides.
- Float comparisons MUST use explicit epsilon values (no raw equality checks).

Default epsilon policy:

| Metric | Epsilon |
|---|---|
| Energy conservation assertions | `1e-3` |
| Field value drift comparisons | `1e-4` |
| Gradient direction comparisons | `1e-3` |
| Population count stability checks | exact integer equality unless explicitly range-bounded |

---

## 5) LLM and safety policy (normative)

### 5.1 Invocation policy

- LLM calls are cluster-level, asynchronous, and rare.
- Tick loop MUST remain deterministic and non-blocking while LLM work is in flight.

### 5.2 Validation policy

Validation is two-layer, never single-layer:

1. Schema validation (shape/type; e.g., pydantic)
2. Semantic validation (domain constraints and compatibility)

Semantic validation MUST enforce:

- Verb exists in manifest.
- Conditions use allowed args/operators.
- Trait prerequisites are satisfied.
- No mutation exceeds configured safety bounds.

Invalid outputs MUST be rejected without side effects.

### 5.3 Failure policy

On timeout or invalid response:

- Keep cluster running with fallback subtree (for example `dormancy`).
- Emit structured telemetry.
- Apply retry policy with bounded attempts.
- Open circuit if repeated failures exceed threshold.

Defaults:

- Retry attempts: `2` per request before fallback lock-in.
- Circuit open: after `3` consecutive failures for same signature.
- Circuit close/retry window: `60 sec` cooldown.

### 5.4 Telemetry schema (required fields)

Required event names:

- `llm.request.started`
- `llm.request.completed`
- `llm.request.failed`
- `contract.checkenv.invalid_path_or_op`
- `contract.querysense.unknown_target`

Required fields on every event:

- `event_name`
- `tick`
- `floor`
- `species_or_cluster_id`
- `signature` (if applicable)
- `severity`
- `message`
- `correlation_id`

---

## 6) Cache lifecycle policy

Subtree cache entries MUST be outcome-scored. "Cache forever" is prohibited.

Each entry tracks:

- success rate over window
- stress reduction delta
- survival impact
- sample count
- last-seen tick

Lifecycle:

1. Promote entry when outcomes are positive with sufficient samples.
2. Demote entry when metrics trend below threshold.
3. Invalidate entry when sustained underperformance or policy violations occur.
4. Re-query slow path after demotion/invalidation under novel or unresolved signatures.

---

## 7) Phase-2 roadmap and gates

This roadmap begins after the ecosystem-first phase is declared stable.

| Phase-2 Sprint | Deliverable | Gate |
|---|---|---|
| 1 | Core organism data/runtime, headless tick wiring against existing `FieldMap`/tile APIs | Tests pass for deterministic 100-tick run and distinct organism stat outputs |
| 2 | Fixed verbs/conditions, one species BT, metabolism/death loop on controlled floor | 600-tick test proves wander/eat/starve/die behavior without renderer |
| 3 | Closed trophic loop (producer-consumer-decomposer) with assertable energy accounting | 10-minute simulation keeps population non-zero and energy accounting within tolerance |
| 4 | Epigenome/fade behavior and visible phenotype deltas | Famine/recovery/fade dynamics pass assertions |
| 5 | End-to-end adaptation pipeline without live LLM (mocked path) | Signature generation, injection, and evaluation loop proven headless |
| 6 | Live LLM subtree selection (existing library only), async non-blocking | Cache hit on repeated signature; mocked and live-path tests both pass |
| 7 | Controlled LLM subtree authoring with approval and policy gates | One authored subtree is validated, adopted, and survives acceptance checks |

Roadmap rules:

- Ecosystem-first phase gates MUST complete before Phase-2 Sprint 1 starts.
- Phase-2 Sprint 5 MUST complete before Phase-2 Sprint 6.

---

## 8) Canon change log and deprecations

### Added decisions

- `FieldMap` replaces standalone `StigmergyMap`.
- Unified contract definitions for `EnvView`, `CheckEnv`, `QuerySense`.
- Explicit validation stack (schema + semantic).
- Explicit cache lifecycle policy.
- Unified sprint gate table with 4A/4B split.

### Deprecated

- Any language implying indefinite cache retention.
- Any language implying schema-only LLM safety.
- Any roadmap rows that conflict with §7.

---

## 9) Related documents

- `docs/canon/charter.md`: canonical authority order and current phase objective.
- `docs/spec/ecosystem-v2.md`: active ecosystem-first implementation spec.
- `docs/reference/north-star.md`: design rationale and worked examples.
- `docs/spec/ecosystem-legacy-v1.md`: archived environment rationale and tuning notes.
