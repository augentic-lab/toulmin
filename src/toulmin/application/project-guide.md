# Project session guide

Discuss, draft and propose; the researcher decides in `toulmin decide`. Use context.md's
command prefix (v4 local.json: local paths/ack). `toulmin draft` supplies skeletons;
consult framework/formats.md or protocols.md for formats. Never read Toulmin's source.

## What you may write

- Never run `toulmin commit`, `git commit` or `git push` in this workspace.
- Anything under projects/NAME/runs/: notes, explorations, scripts, raw outputs.
- `toulmin draft KIND NAME` writes runs/drafts/. Fill it, then move it with the same
  filename to runs/proposals/ for `toulmin decide`.
- Never write objects, outcome files (`*.outcome.md`), PROJECT.md stage/status or brief.md. Never run `toulmin decide`, or `new`/`rule`/`intake` with --confirm.
- Replace all `<fill: …>` values; delete unused optional lines/sections.

## The loop (question first; state.md and `toulmin map NAME` show where it is)

1. **explore**: suggest the smallest measurement, prototype or reading for the question;
   run allowed checks. Log dated observations, numbers and hunches in runs/notebook.md.
   Draft Claims, Evidence, Objections or Decisions only for ideas the researcher promotes;
   one testable statement per Claim. Never draft core Claims to fill G1. Ask once about
   promotion at reproducible results, stated conclusions or pauses; draft after agreement.
2. **Stage proposal** only when the researcher asks: a Decision draft (related: the Claims
   the gate rests on) plus `toulmin draft stage NAME --decision decision-…md`.
3. **critique**: keep this conversation as coordinator. First plan with
   `toulmin review NAME --dry-run`, then `toulmin draft review NAME`; the researcher
   starts the quota-consuming round by applying it in `toulmin decide`. No handoff,
   archive or replacement session is needed. Reviewers and synthesis run in fresh isolated
   sessions with restricted inputs; never perform their independent role here.
   Further rounds need new Evidence or a substantive Claim change; otherwise work on
   Evidence/validation first.
   For each output, `toulmin draft intake NAME --run R-NNN` lists undecided labels;
   recommend outcomes, then answer the Objections the researcher took.
4. **G2** (enter brief-final): no open fatal or major Objection; every core Claim has
   verified supporting Evidence or a validation_plan; Kill criteria are written in brief.md.
   Use `toulmin draft brief NAME --section "Kill criteria"` (repeat --section). Kept sections
   replace whole sections; redraft if the Brief changed.
5. **brief-final → G3 (build)**: every Spec (`toulmin draft spec`) targets a current Claim
   and its Acceptance criteria name runnable checks, each command in backticks.
   **G4 (accept)**: each Spec is `awaiting-acceptance` and lists the implementer's test
   report as supporting Evidence. **G5 (done)**: each Spec is `passed` and lists verified
   Evidence from a Run with role `verifier` (an independent check; never your own run). Your
   own assertion stays `model-asserted`. A stage-past-gate WARNING is the researcher's to rule.

At pauses report pending proposals and up to three questions. After decide refresh state.md
or `toulmin status NAME`.
A "Toulmin notice" lists decide outcomes; refresh with `toulmin map NAME` and
propose research work. Handoff/replacement stays optional; never archive automatically.

## Object drafts (`toulmin draft claim|evidence|objection|decision|exploration|spec NAME`)

- Claim: type problem | magnitude | mechanism | novelty | assumption | deployability;
  importance core | secondary; `## Statement`. Revise with a new Claim and an old-Claim
  `superseded` ruling, `links: {superseded_by: C-NNN}`.
- Evidence: target C-NNN; direction supports | refutes; kind measurement | literature |
  derivation | experiment | computation; grade verified only when a reproducible check
  verified it (with `verification` and existing artifacts), else model-asserted or intuition.
  Neither supports a Claim alone.
- Decision: Context, Choice, Rejected alternatives, Rationale; `related` names every ruled
  object. Rulings need an active Decision; a neighboring Decision draft is cited by filename.

## Rulings (`toulmin draft ruling NAME --object ID [--status S] [--decision D]`)

- Skeletons show current status and allowed sections.
- **Answer and close together**: `--status answered` plus `## Response`; split only on request.
- **Several objects, one reason**: repeat `--object` (or `--object O-001,O-002`): one
  `objects: […]` proposal and Decision naming all objects. Same kind, status and text;
  links are per object.
- Objection statuses: open, answered (needs a Response), accepted (the Objection holds;
  needs a Ruling text), deferred (needs a Ruling text with the reason; a deferred
  major still matters later). Claim statuses: proposed, challenged, supported, accepted,
  refuted, superseded. Evidence: valid, invalidated (with
  `## Invalidation`). Exploration: pending, adopted (`adopted_as`), dropped (`## Rationale`).
  Spec: todo, in-progress, awaiting-acceptance, passed (`evidence`), failed.
- Verified supporting Evidence and no open fatal or major Objection meet the supported
  conditions (the map suggests `--status supported` with a Decision); never use
  model-asserted Evidence.
- `## Why`: researcher-only rationale; never stored on the object.

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
Researcher decides and imports: `toulmin task import NAME FILE --confirm --confirmed-by
ACTOR` (legacy: TASK_ID for FILE). Imports record execution.

Research: `toulmin draft build NAME --spec S-NNN [--repo PATH]`, with a current Claim,
checks/repo from tools/chief.local.toml; Why/Context. Set `command:` only on request.
Researcher applies/imports/verifies; never run Chief yourself. Import proposes Decision,
model-asserted Evidence and awaiting-acceptance ruling. Verify reruns frozen checks in a
fresh clone and proposes verified Evidence/passed ruling, each separately confirmed.
Failures retain outputs. Chief stays on its starting host and uses a separate worktree.

## Ending the session

On requested end, summarize in runs/drafts/ (roles/scribe.md), then
`toulmin aoe handoff NAME --input FILE`; show runs/<archive>/draft.md for decide.
Offer a handoff at long pauses or requested context replacement.
Plain `toulmin open NAME` may resume the binding; `--new-session` explicitly replaces it.

## Shared workspace context

Workspace owns shared sources/understanding; this child owns its goal and notebook.
Only pinned shared overview is resident; sibling/root notebooks stay separate.
Source selection needs explicit archive/replacement; never redirect a live session.
V4 local.json supplies cwd/receipt commands; a receipt is no research approval.

Review profiles: `review NAME --profile NAME --dry-run`, then `draft review NAME
--profile NAME --synthesizer MODEL`. Inspect roles, exact models/effort and total
including synthesis in decide. See framework/review-profiles.md; defaults and
account availability are not measured facts.
