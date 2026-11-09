# Toulmin research workspace

This repository is the researcher's shared research workspace: a common direction, exploration
records, shared resource descriptions and, when confirmed, child projects. Read
framework/principles.md, framework/workspace-formats.md, framework/formats.md and
framework/protocols.md when the task needs their details. Decisions belong to the researcher.

## Workspace and project scopes

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
Details: framework/workspace-formats.md.

### Workspace sessions

- Explore freely; no approval is needed to write in root runs/. Record a bounded exploration
  as runs/<UTC stamp>-activity-<32 hex>/activity.md. Keep the researcher's corrections in
  their own words, and state capture coverage honestly (full, selected, summary or unknown,
  with limits). You see part of the conversation; never claim a complete transcript.
- WORKSPACE.md and shared/resources/ change only through a reviewed packet: write a change
  input under runs/drafts/, run `toulmin workspace propose`, show the packet's diff, and say it
  awaits the researcher's decision (`toulmin decide` in their own terminal). Never apply,
  reject or hand-edit them yourself. A registered resource is a located description, never
  Evidence. When discussion settles a direction, constraint or resource, offer to prepare such
  a proposal; do not wait to be asked.
- A child project is created only from a reviewed packet: write a creation input under
  runs/drafts/ (question, scope, unresolved assumptions and the initial Brief), run `toulmin
  project propose NAME --input FILE`, show the packet and say it awaits `toulmin decide`.
  Never create project directories by hand or force a first Claim.
- Creating a child starts no session. Opening it is a separate `toulmin aoe open NAME` step in
  its own session; this workspace session continues. Do not work on a project's objects here.
- End a workspace session with a summary under runs/drafts/ and `toulmin aoe handoff
  --workspace --input FILE` (Done, Confirmed changes, Pending ideas, Open questions; next step
  in metadata). Show the generated draft.md; only the researcher applies it (`toulmin decide`).

### Project sessions

Follow the research loop; `toulmin status NAME` and the GATES lines of the state card show
which conditions of G1 (enter critique) and G2 (enter brief-final) hold.

1. Draft the core Claims G1 asks for — the problem exists, its magnitude, the mechanism works,
   novelty — and key assumptions with `toulmin draft KIND NAME`; state Evidence grades honestly
   and put needed experiments in validation_plan.
2. Mark a complete object draft ready by moving it, filename unchanged, to
   projects/NAME/runs/proposals/; propose a status change or Response/Ruling text as a
   Decision draft plus a `ruling-…` proposal there (framework/protocols.md, H3). The
   researcher decides them with `toulmin decide`; you never create objects or write outcomes.
3. Request an independent review round (`review-…` proposal, after checking
   `toulmin review NAME --dry-run`) and recommend an outcome for every draft label of each
   review output (`intake-…` proposal). Only the researcher's apply in `toulmin decide` starts
   a round (it uses quota) or records an intake outcome; you never run a confirming command
   or review your own work. Answer open Objections with Responses, Evidence, superseding
   Claims or validation plans.
4. Propose brief.md sections that cite objects, including Kill criteria and the minimal
   validation experiment, as a `brief-…` proposal drafted against the current brief.md.
5. Stage changes are the researcher's ruling. When a gate's conditions hold, say so and put a
   Decision draft plus a `stage-…` proposal in proposals/ for `toulmin decide`; never edit
   PROJECT.md stage or status fields.

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
   change input, packet or summary. The researcher applies it with explicit confirmation
   (`toulmin decide` decides every pending item in one pass); writing or closing a session
   is not approval. Pending ideas stay pending.
4. Push or commit only when the researcher asks; report failures truthfully and keep files.

Anything not written to a file did not happen.
