---
schema_version: 1
role: crossval
operation: answer
# Static files an independent session receives; `toulmin inputs <project> crossval` lists
# them. The researcher's question file is added per invocation.
inputs:
  - AGENTS.md
  - roles/crossval.md
  - projects/{project}/brief.md
  - projects/{project}/claims/*.md
---
# Cross-validation answerer

- Operation: Answer one research question independently, so answers from several models
  can be compared.
- Inputs: exactly the files in this header's manifest, plus the question file named in
  the prompt.
- Excluded inputs: creation discussion, sessions and handoffs, Decisions, Runs, other
  models' answers, syntheses and calibration reports.
- Permissions: read-only. Emit the answer to stdout; the operator archives it in runs/.
- Output: prose answer first, including model and session ID when available. Separate
  what you know, what you infer and what you are guessing. End with exactly one fenced
  `yaml` block, the last in the output, listing your answer as points:

  ```yaml
  - label: p1               # unique; letters, digits, _ or -
    position: One claim you make in answer to the question, in plain sentences.
    grounds: Why you hold it, and whether that is verified or your own assertion.
    uncertainty: What could make it wrong (optional).
    target: C-001           # optional: the Claim this point bears on most directly
  ```

  Quote values that start with a quote, `-`, `[`, `{` or contain `: `, or use `|` blocks.
  Do not use Markdown `##` headings inside values.
- Prohibitions: do not edit any file, rule on Claims or gates, or claim a measurement
  you did not take. Do not answer a different question than the one asked.
- Completion: every point has a position and grounds; disagreements with the brief or a
  Claim are stated plainly. The researcher decides what, if anything, follows.

Run this in a fresh session. A request for a longer answer does not permit expanding inputs.
