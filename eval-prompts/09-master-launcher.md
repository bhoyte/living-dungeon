# Master Launcher (6 Specialist Agents + 1 Lead Synthesizer)

Use this as your single orchestration brief. It defines all agent roles, expected outputs, and handoff format.

## Objective

Evaluate the canonical spec package on multiple dimensions without performing a direct rewrite:

- `<canonical-doc>` (normative)
- `<supporting-doc-1>`
- `<supporting-doc-2>` (optional context)
- `<supporting-doc-3>` (optional context)

Produce:
1) Six specialist reports (parallel)
2) One final combined report (lead synthesis)

## Shared Rules (Apply to all specialist agents)

- Use the full contents of `00-shared-base.md`.
- Use exactly one specialist prompt (`01` through `06`) per agent.
- Stay in assigned dimension.
- Cite evidence with short direct quotes.
- Separate blockers from improvements.
- Output must match required schema exactly.

## Specialist Agents to Launch in Parallel

1. **Agent A - Strategic Alignment**
   - Prompt file: `01-strategic-alignment.md`
   - Output file: `<report-output-path-01>`

2. **Agent B - Canon Consistency**
   - Prompt file: `02-canon-consistency.md`
   - Output file: `<report-output-path-02>`

3. **Agent C - Systems and Playability**
   - Prompt file: `03-systems-playability.md`
   - Output file: `<report-output-path-03>`

4. **Agent D - Narrative and UX Clarity**
   - Prompt file: `04-narrative-ux-clarity.md`
   - Output file: `<report-output-path-04>`

5. **Agent E - Feasibility and Scope**
   - Prompt file: `05-feasibility-scope.md`
   - Output file: `<report-output-path-05>`

6. **Agent F - Red Team**
   - Prompt file: `06-red-team.md`
   - Output file: `<report-output-path-06>`

## Launch Packet Template (Use per specialist agent)

Copy this block and swap only the specialist file reference:

---

You are evaluating:
- `<canonical-doc>` (normative source)
- `<supporting-doc-1>`
- `<supporting-doc-2>` (optional context)
- `<supporting-doc-3>` (optional context)

Instructions:
1) Follow `00-shared-base.md` exactly.
2) Follow `<specialist-file>.md` exactly.
3) Return only the structured report.
4) Include short quotes as evidence.
5) Do not rewrite full sections.

---

## Optional Calibration

For tighter cross-agent scoring consistency, provide:
- `08-scoring-rubric.md`

## Synthesis Step (Run after all six specialist reports complete)

Lead agent input:
- `07-lead-synthesis.md`
- All six specialist reports

Required final output:
- `<final-report-output-path>`

## Done Criteria

- All six specialist reports exist and follow the schema.
- The combined report includes:
  - Final status (`GO` / `GO-WITH-CHANGES` / `NO-GO`)
  - Ranked top risks
  - Unified pre-merge checklist
  - Unified post-merge checklist
  - Conflict resolution notes
  - Minimal merge plan
