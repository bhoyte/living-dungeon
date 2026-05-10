# Dungeon-First Charter

Status: Active  
Effective date: 2026-05-09  
Owner: Systems + Design  
Scope: Canonical direction for current build phase

---

## Why this charter exists

The project direction is now explicit: the dungeon itself is the first-class organism. Creature simulation remains important, but is intentionally deferred so environmental intelligence can emerge from substrate dynamics first.

This charter resolves prior ambiguity where multiple documents presented themselves as canonical.

## Current phase objective

Deliver a humming, immersive, measurable dungeon ecosystem with no creature runtime dependency.

Success means:

- Dynamic fields evolve coherently over time.
- Geological composition materially changes field behavior.
- Producer ecology can be seeded and sustained by field conditions.
- Generation and environment updates are deterministic under seed control.
- Instrumentation can explain why a region behaves as it does.

## Non-goals for this phase

- No mobile creature runtime loops as a delivery gate.
- No behavior trees as required path-to-done.
- No LLM-driven species adaptation in phase-1 acceptance criteria.

These systems are phase-2 work and must not drive architecture decisions that weaken phase-1 ecosystem integrity.

## Authority and precedence

When documents conflict, precedence is:

1. This charter (`docs/canon/charter.md`)
2. `docs/spec/ecosystem-v2.md`
3. `docs/canon/ecosystem-roadmap.md`
4. `docs/phase2/creatures-spec-v1.md`
5. `docs/reference/north-star.md`
6. Research and addendum documents under `docs/reference/` and `docs/research/`

## Compatibility policy

- Preserve existing docs and examples; do not delete context.
- Reframe creature-centric language as phase-2 where needed.
- Keep module boundaries compatible with future creature integration.
- Prefer additive edits over destructive rewrites.
