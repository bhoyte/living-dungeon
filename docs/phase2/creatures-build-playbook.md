# Living Dungeon Creatures Build Playbook (Phase-2, Beginner-Friendly, Step-by-Step)

This guide is the implementation manual for adding creatures and adaptation **after** the ecosystem core is stable.

It follows `docs/phase2/creatures-spec-v1.md` and mirrors the practical, step-by-step format of the ecosystem playbook.

---

## 0) Read This First

### Activation gate (must be true before starting)

Begin this playbook only when ecosystem phase acceptance is satisfied:

- deterministic generation/simulation
- stable 12-field updates
- reactions + special fields running headless
- producer seeding from field conditions
- save/load round-trip and long-run stability passing
- telemetry artifacts emitted and usable

This gate is defined in:

- `docs/canon/ecosystem-roadmap.md`
- `docs/phase2/creatures-spec-v1.md`

### Phase-2 goal

Add creature runtime behavior on top of the existing world model while keeping:

- deterministic tick behavior
- strict simulation/render separation
- fixed verb/condition contracts
- LLM as rare, asynchronous slow-path only (not in per-tick hot loop)

---

## 1) What You Will Build (High-Level Roadmap)

By the end, you should be able to:

1. spawn organisms into the existing `World`
2. run a deterministic creature tick loop in headless mode
3. execute one species behavior tree through fixed verbs/conditions
4. run metabolism, reproduction, death, and cleanup safely
5. emit telemetry suitable for debugging behavior + adaptation
6. run mock adaptation pipeline gates before live LLM integration

---

## 2) Canon Docs To Keep Open

Primary:

1. `docs/phase2/creatures-spec-v1.md`
2. `docs/spec/ecosystem-v2.md`
3. `docs/canon/charter.md`
4. `docs/canon/ecosystem-roadmap.md`

Support:

- `docs/reference/north-star.md`

When these disagree, follow authority order from `docs/README.md`.

---

## 3) Non-Negotiable Contracts (Do Not Drift)

From `creatures-spec-v1.md`, keep these hard rules:

1. one runtime model (`Organism`) + data differentiation (`OrganismData`)
2. `FieldMap` is canonical; no new primary `StigmergyMap`
3. tick order is fixed (spatial index to death/cleanup sequence)
4. contract-safe environment queries (`EnvView`, `CheckEnv`, `QuerySense`)
5. fixed manifest for verbs/conditions in v1
6. LLM path is asynchronous and strictly validated (schema + semantic)

If you change contracts, update tests and rationale in the same PR.

---

## 4) Proposed File Layout for Phase-2

Create these as needed:

```text
sim/
├── organisms.py               # OrganismData, Organism, species/runtime containers
├── behavior.py                # py_trees wiring + fixed verb/condition adapters
├── sensing.py                 # EnvView, QuerySense, confidence + tie-break rules
├── metabolism.py              # energy/stress updates from fields + environment
├── reproduction.py            # asexual/mating gates (v1 minimal)
├── death.py                   # death conditions + corpse field deposition hooks
├── adaptation.py              # signature, cache lifecycle, fallback logic
├── llm_adapter.py             # async LLM interface + validation + circuit policy
├── constants.py               # v1 defaults (single source of truth)
└── tick.py                    # extend orchestrator with creature pipeline stages

tests/
├── test_organisms_core.py
├── test_behavior_contracts.py
├── test_metabolism_loop.py
├── test_population_loop.py
├── test_adaptation_mocked.py
└── test_llm_policy.py
```

Note: names can vary, but responsibilities should remain separated.

---

## 5) Tick Order You Must Preserve

Per `creatures-spec-v1.md`:

1. spatial index build
2. light update
3. field diffusion/decay/sources/sinks
4. field reactions
5. sensing
6. behavior (`py_trees`)
7. metabolism
8. epigenome update
9. population adaptation/caching pipeline
10. reproduction
11. death and cleanup

Why this matters:

- behavior must read up-to-date environment
- metabolism must apply after chosen action
- adaptation must inspect resulting outcomes, not stale pre-action state

---

## 6) Sprint-by-Sprint Build Plan

Use the same Sprint 1–7 sequence as the phase-2 spec.

## 6.1 Sprint 1 — Organism Core + Tick Wiring

Implement:

- `OrganismData` + `Organism` structures
- `World` storage for live organisms (not only spawn logs)
- deterministic organism IDs and update order
- baseline headless 100-tick run with static actions

Tests:

- same seed => same organism ordering and state after 100 ticks
- no crash with empty population
- no sim-render imports from `sim`

Definition of done:

- deterministic 100-tick test passes

## 6.2 Sprint 2 — Fixed Verbs/Conditions + One Species BT

Implement:

- manifest-locked verbs and conditions
- one starter species behavior tree
- `CheckEnv` and `QuerySense` contract-safe wrappers
- fallback behavior when conditions/sense queries fail

Tests:

- invalid paths/operators fail safely (no tick crash)
- unknown target token in `QuerySense` returns `success=false`
- deterministic tie-break behavior (confidence, distance, stable ID)

Definition of done:

- 600-tick headless behavior loop is stable

## 6.3 Sprint 3 — Closed Trophic Loop (Creature Side)

Implement:

- energy gain/loss from interactions with existing fields
- producer-consumer-decomposer links (minimal v1 loop)
- death deposits into ecosystem channels already in place

Tests:

- energy accounting within epsilon (`1e-3`)
- non-zero population for configured scenario window
- no negative energy out of clamped domain

Definition of done:

- closed-loop simulation passes gate assertions

## 6.4 Sprint 4 — Epigenome / Adaptation Markers (No Live LLM Yet)

Implement:

- stress marker updates + fade constants
- bounded phenotype deltas (if visible traits are used)
- deterministic marker transitions under scripted pressure/recovery

Tests:

- famine/recovery/fade behavior follows expected directionality
- bounds are enforced

Definition of done:

- adaptive markers evolve without violating safety bounds

## 6.5 Sprint 5 — Mocked Adaptation Pipeline

Implement:

- signature generation from cluster/environment context
- cache insert/promote/demote/invalidate lifecycle
- fallback subtree routing
- mocked adaptation output ingestion

Tests:

- deterministic signature generation
- lifecycle transitions follow policy thresholds
- invalid adaptation payload rejected with no side effects

Definition of done:

- end-to-end mocked adaptation loop passes

## 6.6 Sprint 6 — Live LLM Selection Path (Async, Non-Blocking)

Implement:

- async request path + timeout budget
- retry + circuit-open/cooldown policy
- strict schema + semantic validation
- safe fallback path while requests are in flight

Tests:

- timeouts never block tick
- repeated failures open circuit
- cache hit path bypasses unnecessary calls

Definition of done:

- live + mocked paths both pass acceptance tests

## 6.7 Sprint 7 — Controlled LLM Authored Subtree

Implement:

- approval gate for authored subtree adoption
- manifest + semantic validation enforcement
- rollout with safety bounds and rollback path

Tests:

- at least one authored subtree adopted safely
- rejection path emits required telemetry and keeps sim stable

Definition of done:

- authored subtree survives acceptance checks in headless run

---

## 7) Determinism and Numeric Policy (Use Everywhere)

Follow defaults from `creatures-spec-v1.md`:

- all deterministic tests must set explicit seeds
- minimum 100 ticks for deterministic gates unless stricter gate exists
- float comparisons use explicit epsilon (never raw equality)

Recommended baseline epsilons:

- energy conservation: `1e-3`
- field drift comparisons: `1e-4`
- gradient direction checks: `1e-3`
- population counts: exact integer equality unless explicitly range-bounded

---

## 8) LLM Safety Checklist (Before Any Live Calls)

Do not enable live adaptation until all are true:

1. schema validation implemented
2. semantic validation implemented
3. manifest lock enforced (no invented runtime primitives)
4. timeout/retry/circuit policy active
5. fallback subtree path active
6. required telemetry events emitted

Minimum required event names:

- `llm.request.started`
- `llm.request.completed`
- `llm.request.failed`
- `contract.checkenv.invalid_path_or_op`
- `contract.querysense.unknown_target`

---

## 9) Daily Execution Template (Practical)

At start of session:

1. activate env
2. run current tests
3. pick one small vertical slice (single subsystem + tests)

During implementation:

1. code the smallest deterministic behavior
2. add/expand tests immediately
3. run `ruff`, `pytest`, `lint-imports`
4. run one headless scenario and inspect telemetry

At end of session:

1. record what changed
2. record seed + command used for verification
3. leave one clear next step

---

## 10) Common Phase-2 Failure Modes

1. mixing contracts and implementation changes in one step
   - fix: lock contract tests first
2. hidden nondeterminism in iteration order
   - fix: stable sort and seed all RNG usage
3. coupling behavior directly to renderer assumptions
   - fix: keep all sim data headless and typed
4. letting LLM output bypass semantic checks
   - fix: reject + fallback, always
5. overcomplicating first species
   - fix: one species, one tree, one reliable loop first

---

## 11) Definition of Done (Phase-2 v1)

Phase-2 v1 is complete when all are true:

1. deterministic creature tick pipeline passes target runs
2. one species behavior loop is stable and contract-safe
3. trophic loop assertions pass with bounded energy accounting
4. adaptation cache lifecycle is measurable and test-covered
5. live LLM path is non-blocking, validated, and safely fallback-able
6. telemetry explains behavior and failure events without ambiguity

Only then move to larger species variety, ECS migration, or advanced chemistry.

---

## 12) Suggested First Commands

```powershell
python -m pytest -q
python -m ruff check .
lint-imports
python -m app.headless --profile data/floors/shallow_delve.json --ticks 600 --seed 42 --out runs/phase2-baseline
```

Use this baseline before every major phase-2 slice so regressions are obvious.

