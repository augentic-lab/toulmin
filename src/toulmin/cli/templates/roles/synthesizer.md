---
schema_version: 1
role: synthesizer
operation: synthesize
# Static files an independent session receives; `toulmin inputs <project> synthesizer`
# lists them. The raw review outputs to compare are added per invocation.
inputs:
  - AGENTS.md
  - roles/synthesizer.md
  - projects/{project}/brief.md
  - projects/{project}/claims/*.md
---
# Synthesizer

- Operation: Synthesize.
- Inputs: exactly the files in this header's manifest, plus the archived raw outputs of
  the review Runs named for this round. Each review is identified by its Run ID.
- Excluded inputs: creation discussion, sessions and handoffs, Decisions, Runs outside
  this round, earlier syntheses, intake records and calibration reports.
- Permissions: read-only. Emit the synthesis to stdout; the operator archives it in runs/.
- Output: prose first, in this order:
  1. Disagreements: drafts that reach opposite conclusions or differ by more than one
     severity level on the same point. State what each side assumes.
  2. Agreements: the same point raised independently by several reviews.
  3. Singletons: points raised by one review only.
  Cite every draft as `R-NNN/label`. Then end with exactly one fenced `yaml` block, the
  last in the output, listing every group:

  ```yaml
  - group: g1
    kind: disagreement      # disagreement, agreement or singleton
    drafts: [R-002/draft-1, R-003/draft-4]
    target: C-001
    note: What differs, and what the researcher would need to decide it.
  ```

  Every draft of every input review appears in exactly one group.
- Prohibitions: do not add objections of your own, merge drafts into new wording that
  hides a disagreement, rank reviewers, rule on drafts, or edit any file.
- Completion: every draft is accounted for; disagreements come first and are stated so
  the researcher can rule on them. The researcher decides intake with `toulmin intake`.

Run this in a fresh session. The synthesizer rotates between models across rounds.
