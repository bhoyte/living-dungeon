# Living Dungeon — documentation map

Ecosystem-first build order:

1. Dungeon substrate (`TileMap`, `FieldMap`, generation, sessile ecology).
2. Headless validation and telemetry.
3. Creatures and LLM adaptation (phase-2), only after environment APIs are stable.

## Directory layout

```text
docs/
├── README.md                      ← you are here
├── canon/                         ← direction + gates (short, authoritative)
│   ├── charter.md
│   └── ecosystem-roadmap.md
├── spec/                          ← implementation specs
│   ├── ecosystem-v2.md            ← active phase-1 dungeon spec
│   └── ecosystem-legacy-v1.md     ← archived predecessor spec
├── reference/                     ← vision + optional tooling menus
│   ├── north-star.md
│   └── tech-options-addendum.md
├── phase2/                        ← creature + adaptation docs
│   ├── creatures-spec-v1.md       ← normative phase-2 specification
│   └── creatures-build-playbook.md← step-by-step implementation guide
└── research/                      ← non-normative research atlas
    └── complexity-atlas.md
```

`eval-prompts/` stays at repo root for review workflows.

## Running the Sim

If you are reading docs first and want runnable commands (headless run, heatmap viewer, sweep runner, run report, local checks), use the root [`README.md`](../README.md) **Tooling** section.

## Canonical reading order

1. [`canon/charter.md`](canon/charter.md) — project direction and authority order  
2. [`spec/ecosystem-v2.md`](spec/ecosystem-v2.md) — primary phase-1 implementation spec  
3. [`canon/ecosystem-roadmap.md`](canon/ecosystem-roadmap.md) — ecosystem sprint gates  
4. [`phase2/creatures-spec-v1.md`](phase2/creatures-spec-v1.md) — phase-2 creatures + adaptation normative contract  
5. [`phase2/creatures-build-playbook.md`](phase2/creatures-build-playbook.md) — practical phase-2 implementation sequence  
6. [`reference/north-star.md`](reference/north-star.md) — vision, rationale, worked examples  

## Document roles

| Path | Role |
|------|------|
| `spec/ecosystem-v2.md` | Active implementation canon for ecosystem-first phase-1 |
| `spec/ecosystem-legacy-v1.md` | Archived v1 environment spec (historical tuning) |
| `phase2/creatures-spec-v1.md` | Phase-2 normative spec; not phase-1 scope |
| `phase2/creatures-build-playbook.md` | Step-by-step implementation guide for phase-2 execution |
| `reference/north-star.md` | Vision and design rationale; defers to canon + spec for sequencing |
| `reference/tech-options-addendum.md` | Post–phase-1 optional tech menu |
| `research/complexity-atlas.md` | Broad survey / bibliography, non-normative |

## Authority order when documents conflict

1. `canon/charter.md`  
2. `spec/ecosystem-v2.md`  
3. `canon/ecosystem-roadmap.md`  
4. `phase2/creatures-spec-v1.md`  
5. `reference/north-star.md`  
6. Everything under `reference/` and `research/` as non-binding input  

## Path migration (repo layout, 2026-05)

| Old path | New path |
|----------|----------|
| `docs/canon/00-dungeon-first-charter.md` | `docs/canon/charter.md` |
| `docs/canon/01-ecosystem-roadmap.md` | `docs/canon/ecosystem-roadmap.md` |
| `docs/dungeon-environment-v2.md` | `docs/spec/ecosystem-v2.md` |
| `docs/dungeon-environment.md` | `docs/spec/ecosystem-legacy-v1.md` |
| `docs/north-star.md` | `docs/reference/north-star.md` |
| `docs/dungeon-environment-addendum.md` | `docs/reference/tech-options-addendum.md` |
| `docs/legacy/living-spec-v1.md` | `docs/phase2/creatures-spec-v1.md` |
| `Dungeon-Complexity-Research-Expanded.md` (repo root) | `docs/research/complexity-atlas.md` |