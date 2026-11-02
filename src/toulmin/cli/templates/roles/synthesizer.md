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
  the Runs named for this round. The prompt lists every item to group as `R-NNN/label`.
- Excluded inputs: creation discussion, sessions and handoffs, Decisions, Runs outside
  this round, earlier syntheses, intake records and calibration reports.
- Permissions: read-only. Emit the synthesis to stdout; the operator archives it in runs/.
- Output: prose first, in this order:
  1. Disagreements: items that reach opposite conclusions or differ by more than one
     severity level on the same point. State what each side assumes.
  2. Agreements: the same point raised independently in several Runs.
  3. Singletons: points raised in one Run only.
  Cite every item as `R-NNN/label`. Then end with exactly one fenced `yaml` block, the
  last in the output, listing every group:

  ```yaml
  - group: g1
    kind: disagreement      # disagreement, agreement or singleton
    drafts: [R-002/draft-1, R-003/draft-4]
    target: C-001           # optional: the Claim the group concerns, if exactly one
    note: What differs, and what the researcher would need to decide it.
  ```

  Every listed item appears in exactly one group. A singleton cites one item; an
  agreement or disagreement cites items from at least two Runs.
- Prohibitions: do not add objections of your own, merge items into new wording that
  hides a disagreement, rank reviewers, rule on drafts, or edit any file.
- Completion: every item is accounted for; disagreements come first and are stated so
  the researcher can rule on them. Intake still uses the original Run and label
  (`toulmin intake` on that Run's output.md), never this synthesis.

Run this in a fresh session. The synthesizer rotates between models across rounds.
