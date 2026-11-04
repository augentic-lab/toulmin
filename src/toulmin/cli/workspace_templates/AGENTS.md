# Toulmin research workspace

This repository is the researcher's shared research workspace: a common direction, exploration
records, shared resource descriptions and, when confirmed, child projects. Read
framework/principles.md, framework/workspace-formats.md, framework/formats.md and
framework/protocols.md when the task needs their details. Decisions belong to the researcher.

## Scopes

Every session has exactly one scope, stated in its context: the **Workspace** or one
**Project: NAME**. Scope is recorded data, not filesystem isolation; stay inside your scope's
records and read others only when the researcher asks.

| Scope | Resident inputs | Your outputs |
| --- | --- | --- |
| Workspace | this file, WORKSPACE.md, the applied sessions/ record named by its last_handoff | root runs/ |
| Project: NAME | this file, WORKSPACE.md (read-only charter), projects/NAME/PROJECT.md, brief.md, its applied handoff | projects/NAME/runs/ |

Never substitute an unconfirmed draft, an activity record or an orphan session file for the
applied handoff. Independent task sessions follow their role's input list instead
(`toulmin inputs <project> <role>`); reviewers never load handoffs or discussion history.

## Workspace sessions

- Explore freely; no approval is needed to write in root runs/. Record a bounded exploration
  as runs/<UTC stamp>-activity-<32 hex>/activity.md. Keep the researcher's corrections in
  their own words, and state capture coverage honestly (full, selected, summary or unknown,
  with limits). You see part of the conversation; never claim a complete transcript.
- WORKSPACE.md and shared/resources/ change only through a reviewed packet: write a change
  input under runs/drafts/, run `toulmin workspace propose`, show the packet's diff and the
  exact apply/reject commands, and let the researcher decide. Never apply, reject or hand-edit
  them yourself. A registered resource is a located description, never Evidence.
- A child project is created only from a reviewed packet: write a creation input under
  runs/drafts/ (question, scope, unresolved assumptions and the initial Brief), run `toulmin
  project propose NAME --input FILE`, show the packet and the exact create/reject commands, and
  let the researcher decide. Never create project directories by hand or force a first Claim.
- Creating a child starts no session. Opening it is a separate `toulmin aoe open NAME` step in
  its own session; this workspace session continues. Do not work on a project's objects here.

## Research rules

- Write maintained documentation and handoff notes in English. Preserve original source
  quotations and raw outputs; use the user's language in conversation.
- Files are the source of truth. Preserve claims, evidence, objections, rejected approaches
  and decisions with their origins. Do not erase failure history.
- Archive AI research output in the session scope's runs/ first. Only after explicit
  researcher confirmation may a draft enter a formal object directory. A confirmation field
  records authorization; an AI cannot authorize itself by signing a name.
- Only the researcher rules on object status or project stage. Condition checks report facts
  and suggestions; they never advance a gate.
- Revise a Claim by superseding it, never by rewriting its Statement. Evidence grades remain
  verified, model-asserted and intuition; the latter two cannot alone satisfy supported.
- Keep generation separate from evaluation. Independent review needs fresh sessions.
- Keep WORKSPACE.md and PROJECT.md within 40 lines. In workspace files, qualify object
  references with their project.

## Exit protocol

1. Save raw output in the scope's runs/ with its provenance; unknown session IDs or durations
   stay null. Never invent values or results.
2. When the researcher asks to end the session, save a structured summary under the scope's
   runs/drafts/ and generate a handoff draft: `toulmin aoe handoff --workspace --input FILE`
   for the workspace (Done, Confirmed changes, Pending ideas, Open questions; next step in
   metadata), or `toulmin aoe handoff NAME --input FILE` for a project (see roles/scribe.md).
3. Show the returned draft.md path. Only that generated draft is the --apply input, never a
   change input, packet or summary. The researcher applies it with explicit confirmation;
   writing or closing a session is not approval. Pending ideas stay pending.
4. Push or commit only when the researcher asks; report failures truthfully and keep files.

Anything not written to a file did not happen.
