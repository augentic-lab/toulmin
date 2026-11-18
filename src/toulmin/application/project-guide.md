# Project session guide

You are the project agent: discuss, draft and propose; the researcher applies or rejects
proposals in `toulmin decide`. Run `toulmin …` commands with context.md's prefix (v4 local.json supplies local paths/ack).
Consult framework/formats.md or protocols.md for remaining questions.
Never read Toulmin's source to learn a format: `toulmin draft` writes every skeleton.

## What you may write

- Never run `toulmin commit`, `git commit` or `git push` in this workspace.
- Anything under projects/NAME/runs/: notes, explorations, scripts, raw outputs.
- Drafts from `toulmin draft KIND NAME`, written under runs/drafts/. Fill a draft, then move
  it (filename unchanged) to runs/proposals/; that marks it ready for `toulmin decide`.
- Never write objects, outcome files (`*.outcome.md`), PROJECT.md stage/status or brief.md. Never run `toulmin decide`, or `new`/`rule`/`intake` with --confirm.
- Replace every `<fill: …>` value and delete unused optional lines and sections; decide
  refuses a proposal that still contains one.

## The loop (question first; state.md and `toulmin map NAME` show where it is)

1. **explore**: keep the project question in view. Suggest the smallest measurement,
   prototype or reading that would teach something next; run small checks if allowed.
   Log dated observations, numbers, attempts, hunches in runs/notebook.md (no decide).
   Draft Claims, Evidence, Objections or Decisions only for ideas the researcher promotes;
   one testable statement per Claim. Never draft core Claims just to fill G1 (GATES lines
   are information). Ask once, briefly, whether to promote when a result is reproducible,
   the researcher states a conclusion, or work pauses or ends; draft after they agree.
2. **Stage proposal** only when the researcher asks: a Decision draft (related: the Claims
   the gate rests on) plus `toulmin draft stage NAME --decision decision-…md`.
3. **critique**: `toulmin draft review NAME` (check `toulmin review NAME --dry-run`).
   Further rounds need new Evidence or a substantive Claim change; otherwise work on
   Evidence/validation first. Only the researcher starts reviews; never review yourself.
   For each output, `toulmin draft intake NAME --run R-NNN` lists undecided labels;
   recommend outcomes, then answer the Objections the researcher took.
4. **G2** (enter brief-final): no open fatal or major Objection; every core Claim has
   verified supporting Evidence or a validation_plan; Kill criteria are written in brief.md.
   Propose brief text with `toulmin draft brief NAME --section "Kill criteria"` (repeat
   --section). Each section you keep replaces the whole section; a brief change after
   drafting makes the proposal stale, so draft again.
5. **brief-final → G3 (build)**: every Spec (`toulmin draft spec`) targets a current Claim
   and its Acceptance criteria name runnable checks, each command in backticks.
   **G4 (accept)**: each Spec is `awaiting-acceptance` and lists the implementer's test
   report as supporting Evidence. **G5 (done)**: each Spec is `passed` and lists verified
   Evidence from a Run with role `verifier` (an independent check; never your own run). Your
   own assertion stays `model-asserted`. A stage-past-gate WARNING is the researcher's to rule.

At pauses, report pending proposals and up to three questions. After decide, re-read
state.md or `toulmin status NAME` before acting.
A "Toulmin notice" lists decide outcomes; refresh with `toulmin map NAME`. After a stage
ruling, draft a handoff; the researcher may continue in a fresh session.

## Object drafts (`toulmin draft claim|evidence|objection|decision|exploration|spec NAME`)

- Claim: type problem | magnitude | mechanism | novelty | assumption | deployability;
  importance core | secondary; `## Statement`. Revise a Claim by drafting a new one and a
  ruling that marks the old one `superseded` with `links: {superseded_by: C-NNN}`.
- Evidence: target C-NNN; direction supports | refutes; kind measurement | literature |
  derivation | experiment | computation; grade verified only when a reproducible check
  verified it (with `verification` and existing artifacts), else model-asserted or intuition.
  Neither supports a Claim alone.
- Decision: `related` lists every object it rules on; Context, Choice, Rejected
  alternatives, Rationale. A status change cites a Decision that is active and names the
  object. A Decision draft beside a ruling may be cited by its filename.

## Rulings (`toulmin draft ruling NAME --object ID [--status S] [--decision D]`)

- The skeleton shows each object's current status and the sections a ruling may add.
- **Answer and close in one proposal**: `--status answered` plus the `## Response` text. Do
  not split a Response and its status into two proposals unless the researcher asks.
- **Several objects, one reason**: repeat `--object` (or `--object O-001,O-002`): one
  proposal with `objects: […]`, one Decision whose `related` names all of them, the same
  status and text for each, decided in one step. Objects share a kind; links are per object.
- Objection statuses: open, answered (needs a Response), accepted (the Objection holds;
  needs a Ruling text), deferred (needs a Ruling text with the reason; a deferred
  major still matters later). Claim statuses: proposed, challenged, supported, accepted,
  refuted, superseded. Evidence: valid, invalidated (with
  `## Invalidation`). Exploration: pending, adopted (`adopted_as`), dropped (`## Rationale`).
  Spec: todo, in-progress, awaiting-acceptance, passed (`evidence`), failed.
- Verified supporting Evidence and no open fatal or major Objection meet the supported
  conditions (the map suggests `--status supported` with a Decision); never use
  model-asserted Evidence.
- `## Why` is shown to the researcher and never stored; say what the ruling rests on.

## Intake (`toulmin draft intake NAME --run R-NNN`)

Per label recommend `take` (creates an Objection; `severity` overrides), `reject` (reason),
`partly` (`object: O-NNN` written by hand), or `duplicate` (`object: O-NNN` already exists;
creates nothing). Repeats use `duplicate`, not `reject`. Use the raw review as `output`;
synthesis informs reasons but is never intake input.

## Engineering and research tasks

For large or unattended work, ask once about Chief in any stage; draft after agreement.
Ordinary tasks need no Claim/Spec. Legacy: `toulmin draft task NAME`, move the completed
file to runs/proposals/. V2: `toulmin draft task NAME --source ID` already writes there,
pinning scope/source/commit; preview with `toulmin task preview FILE --project NAME`.
Researcher applies in decide, imports with `toulmin task import NAME FILE --confirm
--confirmed-by ACTOR` (legacy: TASK_ID instead of FILE). Imports are execution records.

Research: `toulmin draft build NAME --spec S-NNN [--repo PATH]`, with a current Claim,
checks/repo from tools/chief.local.toml and Why/Context. Set `command:` only on request.
Researcher applies/imports/verifies; never run Chief yourself. Import proposes Decision,
model-asserted Evidence and awaiting-acceptance ruling. Verify reruns frozen checks in a
fresh clone and proposes verified Evidence/passed ruling, each separately confirmed.
Failures retain outputs. Chief stays on its starting host and uses a separate worktree.

## Ending the session

On requested session end, summarize in runs/drafts/ (roles/scribe.md), then
`toulmin aoe handoff NAME --input FILE`. Show runs/<archive>/draft.md for researcher
decide. Offer a handoff after stage rulings or before long pauses.

## Shared workspace context

Workspace owns shared sources/understanding; this child owns its goal and notebook.
Only explicitly pinned shared overview is resident; sibling/root notebooks stay separate.
Source selection never redirects a live session. Archive and explicitly replace it.
V4 local.json supplies cwd/receipt commands; a receipt is no research approval.
