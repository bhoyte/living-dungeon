# Agent Launch Template

Copy/paste this when launching each specialist evaluator:

---

Context:
You are evaluating a caller-provided document set:
- `<canonical-doc>` (normative source)
- `<supporting-doc-1>`
- `<supporting-doc-2>` (optional context)
- `<supporting-doc-3>` (optional context)

Instructions:
1) Follow the shared base prompt exactly.
2) Follow the assigned specialist prompt exactly.
3) Return only the report in the required format.
4) Use quotes from the docs as evidence.
5) Do not rewrite the source docs.

[Paste `00-shared-base.md` here]

[Paste one specialist prompt (`01` to `06`) here]

---

Then save output as:
- `<report-output-path>`
