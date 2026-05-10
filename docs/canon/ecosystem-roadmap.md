# Ecosystem-First Roadmap

Status: Active  
Effective date: 2026-05-09  
Scope: Delivery gates for dungeon-first implementation

---

## Sprint plan

| Sprint | Deliverable | Gate |
|---|---|---|
| 0 | Canon alignment: authority order, doc statuses, seed policy | All docs agree on ecosystem-first precedence |
| 1 | `TileMap`, `TileComp`, `TileProps`, deterministic floor loading | Reproducible tile composition counts by seed |
| 2 | `FieldMap` core (diffuse/decay/source/sink), no creatures | Field update invariants pass on fixed fixtures |
| 3 | Light/tremor/scent channels, quiet reactions R1..R5 | Deterministic gradients and reaction assertions |
| 4 | Generation pipeline + profile-driven seeding of sessile producers | Same seed yields equivalent floor + field summary |
| 5 | Ecology tuning + telemetry: stability, oscillation, collapse diagnostics | 10-minute headless run within declared metric bounds |
| 6 | Multi-floor substrate continuity and save/load | Deterministic restore of tile + field snapshots |
| 7 | Introduce creatures behind environment API contracts | Creature integration does not violate field invariants |

## Hard rules

- Creature work is explicitly deferred until Sprint 7.
- LLM mutation/adaptation work remains out of scope until phase-2 planning.
- Every sprint must ship at least one headless regression test.

## Acceptance metrics (phase-1)

- Determinism: repeated seed runs stay within declared numeric tolerance.
- Explainability: each hotspot can be traced to tile/field/proxy source terms.
- Stability: no unbounded field explosion under nominal parameter ranges.
- Immersion signals: visible macro-patterns (pockets, flows, gradients, decay basins) emerge from local rules.
