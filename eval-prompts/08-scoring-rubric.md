# Optional Scoring Rubric (Cross-Agent Calibration)

Use this rubric if you want scores to be more comparable across specialist agents.

## Scale Definitions

- `9-10`: Excellent; no material blockers in this dimension.
- `7-8`: Strong; minor-to-moderate issues, all tractable.
- `5-6`: Mixed; at least one high-impact gap requiring pre-merge changes.
- `3-4`: Weak; multiple high-impact blockers and unclear path to safe merge.
- `0-2`: Unmergeable in this dimension without major rework.

## Severity Guide

- `Critical`: Merge should halt until fixed.
- `High`: Must be fixed pre-merge unless explicitly accepted risk.
- `Medium`: Should be fixed soon; can merge if tracked.
- `Low`: Polish or optimization.

## Score Drivers

Agents should weigh:
- Correctness and consistency in the assigned dimension.
- Potential downstream rework caused by unresolved issues.
- Risk of contributor misinterpretation after merge.

## Merge Readiness Mapping

- Score `8-10` + no unresolved Critical/High blockers -> `GO`
- Score `5-7` or any unresolved High blocker -> `GO-WITH-CHANGES`
- Score `0-4` or any unresolved Critical blocker -> `NO-GO`
