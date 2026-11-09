# Project session guide

You are the project agent: you discuss, draft and propose. The researcher rules, applying or
rejecting every proposal in `toulmin decide` in their own terminal. This guide covers what a
project session needs. Run each `toulmin …` command below with the prefix context.md gives.
Open framework/formats.md or framework/protocols.md only for a question this guide leaves open.
Never read Toulmin's source code to learn a format: `toulmin draft` writes every skeleton.

## What you may write

- Anything under projects/NAME/runs/: notes, explorations, scripts, raw outputs.
- Drafts from `toulmin draft KIND NAME`, written under runs/drafts/. Fill a draft, then move
  it (filename unchanged) to runs/proposals/; that marks it ready for `toulmin decide`.
- Never write objects, outcome files (`*.outcome.md`), PROJECT.md stage/status fields or
  brief.md yourself. Never run `toulmin decide`, `new`, `rule` or `intake` with --confirm.
- Skeleton values look like `<fill: …>`. Replace every one, and delete the optional lines and
  sections you do not use. Decide refuses any proposal that still contains one.

## The loop (state.md ACTIONS and `toulmin map NAME` show where the project is)

1. **explore**: discuss and record explorations. Draft the core Claims G1 asks for: one each
   of type problem, magnitude, mechanism and novelty, `importance: core`, plus key
   assumptions. One testable statement per Claim. Put the experiment that would test it in
   `validation_plan`.
2. **Stage proposal** when a gate's items all hold: a Decision draft (related: the Claims the
   gate rests on) plus `toulmin draft stage NAME --decision decision-…md`.
3. **critique**: request a review round (`toulmin draft review NAME`, after checking
   `toulmin review NAME --dry-run`). The researcher's apply starts it; never start one
   yourself and never review your own work. When outputs arrive, write one intake
   recommendation per review Run: `toulmin draft intake NAME --run R-NNN` lists every
   undecided draft label. Then answer the Objections the researcher took (below).
4. **G2** (enter brief-final): no open fatal or major Objection; every core Claim has
   verified supporting Evidence or a validation_plan; Kill criteria are written in brief.md.
   Propose brief text with `toulmin draft brief NAME --section "Kill criteria"` (repeat
   --section). The skeleton carries brief.md's digest and the sections' current text. Edit
   the text; each section you keep replaces the whole section. A brief change after drafting
   makes the proposal stale; draft again then.
5. **brief-final, build, accept, done**: Specs (`toulmin draft spec`) carry Requirements and
   executable Acceptance criteria for a Claim. Evidence from a verifier's independent run
   counts as verified support; your own assertion stays `model-asserted`.

After the researcher decides, re-read state.md or run `toulmin status NAME` before you act.

## Object drafts (`toulmin draft claim|evidence|objection|decision|exploration|spec NAME`)

- Claim: type problem | magnitude | mechanism | novelty | assumption | deployability;
  importance core | secondary; `## Statement`. Revise a Claim by drafting a new one and a
  ruling that marks the old one `superseded` with `links: {superseded_by: C-NNN}`.
- Evidence: target C-NNN; direction supports | refutes; kind measurement | literature |
  derivation | experiment | computation; grade verified only when a reproducible check
  verified it (with `verification` and existing artifacts), else model-asserted or intuition.
  Those two never make a Claim supported on their own.
- Decision: `related` lists every object it rules on; Context, Choice, Rejected
  alternatives, Rationale. A status change cites a Decision that is active and names the
  object. A Decision draft beside a ruling may be cited by its filename.

## Rulings (`toulmin draft ruling NAME --object ID [--status S] [--decision D]`)

- The skeleton shows each object's current status and the sections a ruling may add
  (Objection: Response, Ruling; Evidence: Invalidation; Exploration: Rationale).
- **Answer and close in one proposal**: `--status answered` plus the `## Response` text. Do
  not split a Response and its status into two proposals unless the researcher asks.
- **Several objects, one reason**: repeat `--object` (or `--object O-001,O-002`). That gives
  one proposal with `objects: […]`, one Decision whose `related` names all of them, and the
  same status and text for each, all decided in one step. Objects must share a kind; links
  are per object.
- Objection statuses: open, answered (needs a Response), accepted (the Objection holds;
  needs a Ruling text), deferred (set aside; needs a Ruling text giving the reason; a
  deferred major still matters later). Claim statuses: proposed,
  challenged, supported, accepted, refuted, superseded. Evidence: valid, invalidated (with
  `## Invalidation`). Exploration: pending, adopted (`adopted_as`), dropped (`## Rationale`).
  Spec: todo, in-progress, awaiting-acceptance, passed (`evidence`), failed.
- `## Why` is shown to the researcher and never stored; say what the ruling rests on.

## Intake (`toulmin draft intake NAME --run R-NNN`)

Recommend one outcome per label: `take` (creates the Objection; add `severity` only to change
the reviewer's), `reject` (the reason is recorded), `partly` (name `object: O-NNN`, an
Objection you drafted by hand from the draft). Use the raw review output, never a synthesis,
as `output`. The synthesis groups agreements and disagreements to inform your reasons.

## Ending the session

Only when the researcher asks to end it: write a summary under runs/drafts/ (roles/scribe.md)
and run `toulmin aoe handoff NAME --input FILE`. Show the returned runs/<archive>/draft.md;
the researcher applies it in `toulmin decide`. A handoff keeps PROJECT.md's next step
current, so offer one after a stage ruling or before a long pause.
