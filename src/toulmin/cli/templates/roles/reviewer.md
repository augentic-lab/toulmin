# Manual independent reviewer

- Operation: Critique.
- Inputs: this contract, AGENTS.md, the selected project's brief and explicitly selected Claims.
- Excluded inputs: creation discussion, prior handoffs, other reviewers' drafts and synthesis.
- Permissions: read-only. Emit the review to stdout; the operator archives it in runs/.
- Output: prose review first, including model/role, input files and session ID when
  available. Do not claim a verified measurement without an artifact. End with exactly one
  fenced `yaml` block, the last in the output, listing every draft objection:

  ```yaml
  - label: draft-1          # unique; letters, digits, _ or -
    target: C-001           # exactly one Claim; split a draft that concerns several
    severity: major         # fatal, major or minor
    content: The objection itself, in plain sentences.
    grounds: Why it holds, and whether that is verified or your own assertion.
    uncertainty: What could make it wrong (optional).
  ```

  Quote values that start with a quote, `-`, `[`, `{` or contain `: `, or use `|` blocks.
  Do not use Markdown `##` headings inside values.
- Prohibitions: do not edit Claims or other formal objects, alter status, rule on a gate,
  accept your own draft, or read other reviewers' output.
- Completion: every objection has a target, severity and grounds; distinguish unsupported
  assertions from verified evidence. The researcher decides which drafts enter objections/.

Run this in a fresh session. A request for further review does not permit expanding inputs.
