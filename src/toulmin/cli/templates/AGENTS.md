# Toulmin research workbench

This repository is the researcher's file-based project state. Read framework/principles.md,
framework/formats.md and framework/protocols.md when the task needs their details.
Models are invoked manually, or headlessly by `toulmin review`, `synthesize` and
`crossval` for read-only work archived in runs/ (tools/models.toml).
Decisions belong to the researcher.

## Entry protocol

1. Read this file.
2. For interactive work, read projects/<project>/PROJECT.md and the applied sessions file
   named by last_handoff; a new project has none. Never substitute an unconfirmed draft.
   For independent task sessions, the role's explicit input/exclusion list takes priority:
   reviewers must not load handoffs or discussion history, or other unapproved inputs.
3. State one task, role, required inputs and output location for this session.
4. Load only the relevant objects. Reviewers read brief and claims, not creation history
   or other reviewers' outputs. Independent roles (roles/reviewer*.md, synthesizer.md,
   crossval.md) receive exactly the files `toulmin inputs <project> <role>` lists; see
   roles/scribe.md for handoffs.

## Research rules

- Write maintained documentation and handoff notes in English. Preserve original source
  quotations and raw outputs; use the user's language in conversation.
- Files are the source of truth. Preserve claims, evidence, objections, rejected approaches
  and decisions with their origins. Do not erase failure history.
- Archive AI research output in projects/<project>/runs/ first. The operator saves stdout
  from read-only reviews and records a Run with model, role, inputs, output and session ID.
- Only after explicit researcher confirmation may a draft enter a formal object directory.
  A confirmation field records authorization; an AI cannot authorize itself by signing a name.
- Only the researcher rules on object status or project stage. Record the Decision and its
  rationale, then apply it with `toulmin rule` (or by hand). Condition checks report facts
  and suggestions; they never advance a gate.
- Revise a Claim by superseding it with a new Claim, never by rewriting its Statement;
  keep Objections and Evidence on the wording they addressed. Fix typos in place.
- Evidence grades remain verified, model-asserted and intuition. The latter two cannot
  alone satisfy supported. Invalidated evidence never counts as support.
- Keep generation separate from evaluation. Independent review and acceptance need fresh
  sessions. An implementer's tests do not constitute independent acceptance.
- Keep PROJECT.md within 40 lines. Write the brief by hand; use [[C-001]] references.
  Generated summary views are disposable, not another hand-maintained source of truth.
- Prefer open text formats and tool-independent protocols. L1 format changes require an
  impact assessment and migration for existing objects; L2 changes require a change note.

## Exit protocol

1. Save raw output in runs/ and record its provenance; object drafts go in runs/drafts/
   (`toulmin draft` writes a skeleton). Unknown session IDs or duration remain null;
   never invent values or results.
2. Draft a handoff with work done, decisions/pending decisions, open questions, next step
   and session ID. See roles/scribe.md. Do not treat writing a draft as approval.
3. After researcher review, apply it to sessions/ and update PROJECT.md recent_decisions,
   next_step and last_handoff. Handoff never changes stage or object status.
   The operator uses handoff --apply with explicit confirmation; retry the same draft
   after an interrupted application. Do not discard a pending recovery journal.
4. Inspect the diff and commit with related object IDs. Report identity/permission failures
   truthfully and retain files. Push only when explicitly requested.

Anything not written to a file did not happen.
