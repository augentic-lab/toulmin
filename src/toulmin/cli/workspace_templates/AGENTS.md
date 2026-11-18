# Toulmin research workspace

This repository is the researcher's shared research workspace: a common direction, exploration
records, shared resource descriptions and, when confirmed, child projects. Decisions belong to
the researcher. Start from your session context: a project session's guide.md and
`toulmin draft` skeletons cover routine work. Open framework/principles.md,
framework/workspace-formats.md, framework/formats.md or framework/protocols.md only for a
question they leave open, and read only the section you need.

## Workspace and project scopes

Every session has exactly one scope, stated in its context: the **Workspace** or one
**Project: NAME**. Scope is recorded data, not filesystem isolation; stay inside your scope's
records and read others only when the researcher asks.

| Scope | Resident inputs | Your outputs |
| --- | --- | --- |
| Workspace | this file, WORKSPACE.md, confirmed root overview.md, sources.toml, applied handoff and labeled bounded notebook excerpt | root runs/ |
| Project: NAME | this file, WORKSPACE.md, its charter/Brief/overview/handoff; shared overview only when explicitly pinned in its creation | projects/NAME/runs/ |

Never substitute an unconfirmed draft, an activity record or an orphan session file for the
applied handoff. Independent task sessions follow their role's input list instead
(`toulmin inputs <project> <role>`); reviewers never load handoffs or discussion history.
Details: framework/workspace-formats.md.

### Workspace sessions

Workspace discussion, maintenance and ordinary engineering require no child, Claim, Spec or
research gate. Overall repository understanding and shared logical sources belong here.
Read framework/onboarding.md for current workspace-first forms; exact v2 schemas are in
framework/workspace-onboarding-contract.md (its WO2 status labels are historical).

- Work question first. Append unconfirmed entries with `toulmin workspace note --input FILE`
  (workspace writer lock); never rewrite root runs/notebook.md observations: Source/snapshot, Author/model/session (unknown when unknown),
  Coverage, Limits, then Observation and Next measurement. Qualify [[project/C-001]] links.
- Offer a reviewed understanding checkpoint when useful: `toulmin draft overview --workspace`,
  fill its body, then `toulmin overview --workspace --input FILE --source ID --rationale TEXT`.
  This creates a proposal; the researcher decides it. Never hand-edit confirmed overview.md.
- For substantial engineering, offer `toulmin draft task --workspace --source ID`; fill its
  Goal/Scope/checks/protected paths/budget and show `toulmin task preview --workspace FILE`.
  The researcher uses `toulmin decide --workspace` to submit through Chief. No Spec/Claim is
  required and no scheduler/kickoff is implied. Imports are operational workspace Runs;
  do not promote them to scientific Evidence without a separate reviewed project workflow.
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
  project propose NAME --input FILE --source ID [--working-source ID]`, show the packet and say it awaits `toulmin decide --workspace`.
  Source flags link existing workspace definitions, never inherit a working choice or move
  workspace history/code. Never create project directories by hand or force a first Claim.
- Creating a child starts no session. Opening it is a separate `toulmin aoe open NAME` step in
  its own session; this workspace session continues. Do not work on a project's objects here.
- End a workspace session with a summary under runs/drafts/ and `toulmin aoe handoff
  --workspace --input FILE` (Done, Confirmed changes, Pending ideas, Open questions; next step
  in metadata). Show the generated draft.md; only the researcher applies it (`toulmin decide`).

### Project sessions

Work question first and formalize only what has hardened; `toulmin status NAME` and the
GATES lines of the state card show which conditions of G1 (enter critique) and G2 (enter
brief-final) hold. The guide.md in your
session context covers the loop and every proposal format; `toulmin draft KIND NAME` writes
each skeleton, so never read Toulmin's source to learn a format.

1. Start from the project question: suggest the smallest measurement, prototype or reading
   that would teach something next, and log dated observations in runs/notebook.md. Draft
   Claims, Evidence or Objections with `toulmin draft KIND NAME` only when the researcher asks
   to promote an idea; state Evidence grades honestly. G1/G2 lines are information, not tasks.
   Ask once, briefly, whether to promote when a result is reproducible, the researcher states
   a conclusion, or work pauses or ends; draft only after they agree.
   Do small implementation in the session; for a large or long unattended task, ask once
   whether to hand it to Chief (a Spec, then a build request), in any stage.
2. Mark a complete object draft ready by moving it, filename unchanged, to
   projects/NAME/runs/proposals/; propose a status change with its Response/Ruling text as a
   Decision draft plus one ruling proposal (`toulmin draft ruling NAME --object ID`; repeat
   --object for one ruling on several objects). The researcher decides them with
   `toulmin decide`; you never create objects or write outcomes.
3. Request an independent review round (`toulmin draft review NAME`, after checking
   `toulmin review NAME --dry-run`) and recommend an outcome for every draft label of each
   review output (`toulmin draft intake NAME --run R-NNN`). Only the researcher's apply in
   `toulmin decide` starts a round (it uses quota) or records an intake outcome; you never
   run a confirming command or review your own work. Answer open Objections with Responses,
   Evidence, superseding Claims or validation plans.
4. Propose brief.md sections that cite objects, including Kill criteria and the minimal
   validation experiment (`toulmin draft brief NAME --section NAME`).
5. Stage changes are the researcher's ruling. You may mention that a gate's conditions hold;
   draft a Decision plus a stage proposal (`toulmin draft stage NAME`) only when the
   researcher asks. Never edit PROJECT.md stage or status fields.

### Existing projects and external working sources

A project can describe an existing codebase without a first Claim or a forced starting
stage. Its optional overview.md is researcher-confirmed context; runs/notebook.md contains
unconfirmed working observations. Native recovery loads a bounded recent notebook excerpt,
never a complete transcript. Begin by discussing the project's current work and the smallest
useful next action. Offer a draft task for substantial development; confirmation creates a
bounded Chief task without requiring a Claim or Spec.

A workspace or project working source is a selection, not a permission grant. A registered working source is separate from shared resources and research records. When the
session context names an external code checkout as cwd, follow that repository's AGENTS.md
and development rules for code edits, tests and code commits. Keep all research outputs in
the selected scope's runs/ in this workspace and use --root for Toulmin commands. Read the
ignored local.json for actual v4 paths and its executable acknowledgment command.
This workspace's no-commit rule governs research records; it does not replace the external
repository's code commit policy. Preserve native permissions and resolve trust prompts in
the native CLI. Chief runs implementation in separate worktrees. A source-path or identity
change requires explicitly replacing the old native session; never silently change its cwd.

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
4. Agents never run `toulmin commit`, `git commit` or `git push` in this workspace.

Anything not written to a file did not happen.
