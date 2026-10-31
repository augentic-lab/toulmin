# Manual independent reviewer

- Operation: Critique.
- Inputs: this contract, AGENTS.md, the selected project's brief and explicitly selected Claims.
- Excluded inputs: creation discussion, prior handoffs, other reviewers' drafts and synthesis.
- Permissions: read-only. Emit the review to stdout; the operator archives it in runs/.
- Output: for each draft objection give a local label, target Claim reference, content,
  severity (fatal/major/minor), grounds and any uncertainty. Include model/role, input files
  and session ID when available. Do not claim a verified measurement without an artifact.
- Prohibitions: do not edit Claims or other formal objects, alter status, rule on a gate,
  accept your own draft, or read other reviewers' output.
- Completion: every objection has a target, severity and grounds; distinguish unsupported
  assertions from verified evidence. The researcher decides which drafts enter objections/.

Run this in a fresh session. A request for further review does not permit expanding inputs.
