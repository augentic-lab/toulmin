# Manual scribe

- Operation: Hand off.
- Inputs: this session's output, relevant objects and decisions, PROJECT.md and its last_handoff.
- Excluded inputs: unrelated projects and unneeded discussion archives.
- Permissions: write a draft in runs/ only; the researcher confirms application to sessions/
  and PROJECT.md non-ruling fields.
- Output: work done, decisions/pending decisions, open questions, suggested next step and
  session ID (null when unavailable). Reference original outputs and existing Decision IDs.
- Prohibitions: inventing outcomes/IDs, changing stage or object status, calling a draft
  approved, altering goals/constraints, or overwriting a PROJECT changed since drafting.
- Completion: the next session can identify current state and next step using only files.
  The draft remains pending until researcher review; inspect the diff before committing.

To supply a summary to handoff --input, use YAML next_step, recent_decisions and session_id
(null if unknown), and Markdown sections Done, Decisions and Open questions. Do not add a
Next step section: the command adds a pointer to the metadata, keeping one source of truth.
Unknown work or decisions must be labelled unknown, never invented. Only reference existing
researcher Decisions. The handoff command neither invokes a model nor makes a new ruling.
