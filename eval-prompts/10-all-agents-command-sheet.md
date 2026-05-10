# All-Agents Command Sheet (Copy-Ready)

Use these blocks for fast launch. Each block is self-contained and references the prompt files in `eval-prompts/`.

Input/Output setup (fill these before each run):

- `<canonical-doc>`
- `<supporting-doc-1>`
- `<supporting-doc-2>` (optional context)
- `<supporting-doc-3>` (optional context)
- `<run-output-folder>` (example: `docs/reports/runs/2026-05-08-a/`)

---

## Agent 01 - Strategic Alignment

```text
Task: Evaluate `<canonical-doc>` (normative), `<supporting-doc-1>`, and optional context docs (`<supporting-doc-2>`, `<supporting-doc-3>`) for Strategic Alignment and Purpose Coherence.

Read and follow:
- eval-prompts/00-shared-base.md
- eval-prompts/01-strategic-alignment.md
- eval-prompts/08-scoring-rubric.md (optional but recommended)

Return only the final structured report.
Save as: <run-output-folder>/report-01-strategic-alignment.md
```

## Agent 02 - Canon Consistency

```text
Task: Evaluate `<canonical-doc>` (normative), `<supporting-doc-1>`, and optional context docs (`<supporting-doc-2>`, `<supporting-doc-3>`) for Internal Consistency, Canon, and Cross-Doc Contradictions.

Read and follow:
- eval-prompts/00-shared-base.md
- eval-prompts/02-canon-consistency.md
- eval-prompts/08-scoring-rubric.md (optional but recommended)

Return only the final structured report.
Save as: <run-output-folder>/report-02-canon-consistency.md
```

## Agent 03 - Systems and Playability

```text
Task: Evaluate `<canonical-doc>` (normative), `<supporting-doc-1>`, and optional context docs (`<supporting-doc-2>`, `<supporting-doc-3>`) for Mechanics, Systems, and Playability Logic.

Read and follow:
- eval-prompts/00-shared-base.md
- eval-prompts/03-systems-playability.md
- eval-prompts/08-scoring-rubric.md (optional but recommended)

Return only the final structured report.
Save as: <run-output-folder>/report-03-systems-playability.md
```

## Agent 04 - Narrative and UX Clarity

```text
Task: Evaluate `<canonical-doc>` (normative), `<supporting-doc-1>`, and optional context docs (`<supporting-doc-2>`, `<supporting-doc-3>`) for Narrative Clarity, Information Architecture, and Readability.

Read and follow:
- eval-prompts/00-shared-base.md
- eval-prompts/04-narrative-ux-clarity.md
- eval-prompts/08-scoring-rubric.md (optional but recommended)

Return only the final structured report.
Save as: <run-output-folder>/report-04-narrative-ux-clarity.md
```

## Agent 05 - Feasibility and Scope

```text
Task: Evaluate `<canonical-doc>` (normative), `<supporting-doc-1>`, and optional context docs (`<supporting-doc-2>`, `<supporting-doc-3>`) for Implementation Feasibility, Scope, and Operational Risk.

Read and follow:
- eval-prompts/00-shared-base.md
- eval-prompts/05-feasibility-scope.md
- eval-prompts/08-scoring-rubric.md (optional but recommended)

Return only the final structured report.
Save as: <run-output-folder>/report-05-feasibility-scope.md
```

## Agent 06 - Red Team

```text
Task: Evaluate `<canonical-doc>` (normative), `<supporting-doc-1>`, and optional context docs (`<supporting-doc-2>`, `<supporting-doc-3>`) using a Red-Team Critique (Failure Modes and Stress Test).

Read and follow:
- eval-prompts/00-shared-base.md
- eval-prompts/06-red-team.md
- eval-prompts/08-scoring-rubric.md (optional but recommended)

Return only the final structured report.
Save as: <run-output-folder>/report-06-red-team.md
```

## Lead Synthesizer - Final Combined Report

```text
Task: Synthesize six specialist reports into one merge decision.

Read and follow:
- eval-prompts/07-lead-synthesis.md

Inputs:
- <run-output-folder>/report-01-strategic-alignment.md
- <run-output-folder>/report-02-canon-consistency.md
- <run-output-folder>/report-03-systems-playability.md
- <run-output-folder>/report-04-narrative-ux-clarity.md
- <run-output-folder>/report-05-feasibility-scope.md
- <run-output-folder>/report-06-red-team.md

Return only the final structured report.
Save as: <run-output-folder>/report-final-combined-eval.md
```
