# Framework changes

- Guide freshness (2026-11-18): an updated agent guide makes project contexts stale, so
  `toulmin aoe refresh NAME` delivers it. Existing project sessions show stale once.

## R10/R11 — 2026-11-18

- Critique continues in the current coordinator; handoff/replacement is optional.
- Optional named profiles show exact requested model/effort, coverage, synthesis and total.
- Optional review-request v1 profile/synthesizer fields: existing data needs no migration;
  older readers reject these new fields. No scientific object/gate schema changed.
- Total cap now includes synthesis; fresh templates allow nine for eight reviews + one
  synthesis. Existing settings are never rewritten: explicitly adjust an old cap if needed.
- Additive archived review-plan provenance and read-only profile calibration.

- Readable views (2026-11-18): researcher wording in `status`, folded repeats and optional
  provenance in `map --full`, terminal-only colour (`NO_COLOR` respected), and the project card
  on every AoE project screen. Display only.

- Summary-first decide (2026-11-18): proposals and build requests show a short summary; `v`
  views all of it, `decide --full` prints everything. Application is unchanged.

- Project card (2026-11-18): `toulmin map` and `toulmin open` lead with a derived project
  card (question, Claim states, grouped doubts, waiting items, next moves); `map --full` keeps
  the earlier view. Labels cut at word boundaries; terminal-only wrapping. No format change.

- Existing-project onboarding (2026-11-17, O1–O5): additive source catalogs/local bindings,
  reviewed onboarding and overview/source-change packets, engineering task requests and
  ordinary execution imports, and migration assessment receipts. Native source sessions
  use v3 bindings; v1/v2 readers remain supported. No scientific object or stage schema
  changes. Exact notebook.md is an informal log, excluded from formal Run parsing.
  See the repository docs/onboarding.md for compatibility and operational limits.

- Workspace removal (2026-11-17): `toulmin workspaces remove` previews and, after the folder
  name is typed, removes a workspace (sessions to AoE's trash, optional archive). No format
  change.

- P0 question-first guidance (2026-11-14): project agents start from the question and the
  smallest next measurement, log observations in runs/notebook.md and draft objects only for
  ideas the researcher promotes; the map's explore row suggests a measurement instead of
  missing core Claims. No schema, gate or stage change.
  Follow-up: the agent briefly asks whether to promote a reproducible result, a stated
  conclusion or work at a pause, and drafts only after the researcher agrees.
  Second follow-up: for a large or long unattended task the agent asks whether to hand it to
  Chief (Spec, then build request) in any stage.

- Worker launch command (2026-11-13): build requests accept optional `command`, a bare
  program name on PATH that Chief uses to launch the worker (e.g. a model-router wrapper).
  It reaches the frozen contract only when set, decide previews it, and imported Runs name
  `<tool> via <command>`. Additive schema_version 1; older builds refuse requests with it.

- C5-F1/F2 (2026-11-12): further-round suggestions need later-created current Claims or
  non-invalidated Evidence; previews advise when nothing changed without blocking apply.
  Duplicate intake links an existing local Objection without creating one; decide adds
  duplicate choices and calibration counts them separately, excluding them from adoption
  and rejection rates. Additive schema_version 1; old records need no migration, while
  older builds refuse duplicate outcomes. Independent reviewer inputs remain unchanged.

- S5 follow-ups: readiness names a native CLI update menu as "the CLI update prompt"
  (choose Skip or update in AoE). protocols.md S5 adds the recovery recipe when two clones
  created the same object ID. No recorded schema changes.
- S4: status/open show offline git state and decide warns before writing when behind,
  diverged or in a git operation. Researcher-only `toulmin commit` previews paths and a
  deterministic message, commits only with --confirm, honors identity/hooks and never
  pushes. Active transactions and machine-local files refuse before staging. No recorded
  schema changes; workspace agents never commit or push.

## v1 — Skeleton

- Data and protocols follow formats.md and protocols.md. No older persisted objects to migrate.
- AI research output is archived before confirmed intake. Handoff changes non-ruling fields only.
- Stages: explore, critique, brief-final, build, accept, done. Specs are prepared before Build.
- Record future L2 changes here. L1 changes require impact assessment and migration of existing data.
- Handoff drafts require explicit confirmation before recoverable session/PROJECT updates;
  content digests and previous_handoff identify applied history without an index.
- Independent roles follow their input exclusions; interactive resident context must not
  cause reviewers to load handoffs or discussion history.
- 2026-11-02 (L2 note): stage acceptance is a researcher ruling on recorded trial evidence,
  not necessarily a human two-day trial. No object format or command behavior changed.
- U1 (L2 note): `toulmin draft` writes skeletons to runs/drafts/; intake rejects unfilled
  `<fill: ...>` placeholders; `TOULMIN_ACTOR` may supply the default confirmer. v1 unchanged.
- U2 (L2 note): `toulmin rule` records a confirmed status change, Response or Ruling. Status
  changes need an active Decision naming the object; text is appended, never deleted.
- U3 (presentation only): generated headers follow contract field order without folding;
  object timestamps use whole seconds. Older files stay valid; no migration.
- R1 (L1, additive within v1): Claim status `superseded` with `superseded_by`; rule sets it
  and the other status-required links. Older builds reject the new status; no migration.
- C1 (L1/L2, additive within v1): reviews end with a fenced yaml draft block; `toulmin intake`
  takes chosen drafts in as Objections and appends outcomes to intake.md beside the raw
  output. Object fields unchanged; no migration.
- C2 (L1/L2, additive): role files for independent sessions carry an input manifest;
  `toulmin inputs` and `draft run --role` compute input_files. Adds four reviewer personas
  and the synthesizer contract. Object formats unchanged; no migration.
- C3 (L2/L3): `toulmin review` runs read-only headless reviews (Claude Code, Codex) per
  persona x model, archives prompt/output/log and records completed or failed Runs.
  Configuration in tools/models.toml. Object formats unchanged; no migration.
  Codex runs from a review-only CODEX_HOME; review refuses a home with global
  instructions or without a login (preflight, no quota).
- C4 (L1/L2/L3, additive): `toulmin synthesize` (rotated synthesizer over named Runs) and
  `toulmin crossval` (one question to each model, then synthesis); crossval role template;
  point and group blocks. Synthesis never creates objects. No migration.

## UI1 — Optional terminal workspace

- Q25–Q29 approve a Python/Textual interface with researcher-controlled assisted authoring.
- UI1 adds project create/open and versioned auxiliary setup archives under runs/setup/.
  Existing object fields/version are unchanged; no existing research data needs migration.
- Setup recovery preserves exact before/after files and conflicts. Opening projects never
  rewrites workbench templates. Conversation and review UI actions remain later work.

## WI1 — Workspace-first file contracts (not implemented)

- workspace-formats.md freezes additive formats for WORKSPACE.md, activity records, shared
  resource descriptions, sealed change and child-creation packets, receipts, workspace
  handoffs, the publication journal, scope-aware bindings (version 2) and legacy adoption.
- Project object v1, project handoffs and AOE3 version 1 bindings are unchanged; no migration.
  No command reads or writes the new files yet; later releases implement them in order.

## WI2 — Project-free workspace and offline status

- `toulmin init ROOT [--name]` creates a workspace without a project: WORKSPACE.md (no confirmed
  direction), empty projects/, runs/drafts/, sessions/ and shared/resources/. `status` without
  PROJECT shows the workspace. `init --project` is refused on workspace roots only.
- Additive: project object v1 and existing workbenches are unchanged; no migration.

## WI3 — Reviewed workspace changes and shared resources

- `toulmin workspace propose --input F` freezes a sealed review packet; `workspace apply --draft
  P` previews it, and with `--confirm` and an actor publishes WORKSPACE.md or
  shared/resources/ descriptions plus a receipt. `workspace reject` records a final rejection.
- Interrupted applies leave `.workspace-pending/`; rerunning the same apply finishes it.
- Additive: project object v1 and existing workbenches are unchanged; no migration.

## WI4 — Workspace handoffs

- `toulmin aoe handoff --workspace --input SUMMARY` seals a handoff draft; `--apply DRAFT
  --confirmed-by ACTOR --confirm` records `sessions/<stamp>-<digest>.md` and changes only
  WORKSPACE.md `next_step` and `last_handoff`. Without `--confirm` it previews.
- Status shows pending, stale and incomplete handoff drafts and reports orphan session records.
- `aoe handoff PROJECT` is unchanged. Additive: no migration.

## WI5 — Workspace and project native sessions

- On a workspace root, `toulmin aoe open|bind|status|refresh|ack` without PROJECT (or with
  `--workspace`) manage the workspace session; with PROJECT, that project's session. Each scope
  has its own binding and context; one native session never serves two scopes.
- New bindings on workspace roots are version 2; existing version 1 bindings are kept until an
  explicit `bind --replace` or `open --new-session`. Legacy workbenches are unchanged.
- New workspaces get scope-aware research instructions in AGENTS.md.

## WI6 — Reviewed child creation

- `toulmin project propose NAME --input F` seals a creation packet (question, scope, initial
  Brief and generated PROJECT.md, carried sources and pins). `project create NAME --from P`
  previews it, and with `--confirmed-by ACTOR --confirm` publishes the complete child (explore
  stage, empty collections, `runs/creation/` provenance) plus a receipt. `project reject`
  records a final rejection.
- No Claim or Decision is created and no native session is started; open the child with
  `toulmin aoe open NAME`. An occupied name is refused; an interrupted create finishes when
  rerun. `aoe open --new-session` may retry a launch that left no AoE session.
- Additive: existing projects and workbenches are unchanged; no migration.

## WI7 — Previewed adoption of existing workbenches

- `toulmin workspace adopt ROOT [--name N]` previews the exact additive plan and its digest;
  `--plan-digest D --confirmed-by ACTOR --confirm` applies that unchanged plan: WORKSPACE.md,
  empty record locations, journal ignore patterns, the workspace contract and scope
  instructions (pristine AGENTS.md replaced, customized AGENTS.md gains one section).
- Projects, objects, handoffs, bindings, context archives, configuration and history are
  unchanged; no model or session is started. Conflicts and stale digests write nothing; an
  interrupted adoption finishes when rerun with the same digest.
- Existing project native contexts become stale after adoption (they gain WORKSPACE.md).
- WX2 (L3 only): user preferences in `~/.config/toulmin/config.toml` (actor, AoE profile,
  agent, attach), `--root` discovery from the current directory and `toulmin open`. Nothing in
  a workbench changes; the configured actor supplies attribution only, never confirmation.
- WX4 (L3; one L2 presentation line): `toulmin decide` decides pending workspace changes,
  child creations and handoff drafts one at a time in the researcher's terminal, through the
  same functions as their own commands. Workspace AGENTS.md guidance points to it. No format
  change; existing commands are unchanged.
- WX3 (L3 only): `aoe status`/`open` show the model the native session log reports (name and
  effort only). Display provenance; nothing is written and no behavior depends on it.
- W8 (L2 read-only helper; L3 text): handoff previews warn when workspace changes applied since
  the last handoff are not cited by the summary. Warning only; no format or behavior change.
- WX6 (L3 only): a user-level list of known workspaces outside every workbench lets `toulmin
  open` offer and `open --in NAME` open workspaces elsewhere; `toulmin workspaces` lists,
  forgets and scans AoE sessions. No research file or format change.
- W7 (L3 text): native contexts name commands the agent runs with the serving interpreter
  (`<python> -m toulmin …`), so they work without `toulmin` on the agent's PATH. No format change.
- H2 (L2 read-only): `status PROJECT` reports G1/G2 readiness item by item from files. It never
  changes stage or status. No format change.
- H6 (presentation and guidance): the project state card shows GATES and a stage-aware next
  suggestion; project contexts and the workspace AGENTS.md describe the research loop. No
  format change; the agent still never confirms anything.
- H3 (L1 additive, L2, L3): ready object drafts and ruling proposals go under
  projects/NAME/runs/proposals/ and are decided in `toulmin decide`; each decision is an
  `<stem>.outcome.md` record beside the proposal (rejections keep the reason). `new` and
  `rule` gain a write-nothing preview. Existing files unchanged; no migration.
- H4 (L1 additive, L2, L3): review-round requests (`review-…`) and intake recommendations
  (`intake-…`) under runs/proposals/ are decided in `toulmin decide`: a round starts only on
  the researcher's apply and is followed by synthesis; intake is chosen label by label.
  Existing files and commands unchanged; no migration.
- H5 (L1 additive, L2, L3): Brief proposals (`brief-…`, section replacements against a
  recorded brief.md digest) and stage proposals (`stage-…`, backed by an active Decision) are
  decided in `toulmin decide`. A stage proposal is the first path that writes PROJECT.md
  `stage`, only on the researcher's apply. Formats unchanged; no migration.
- H5 follow-up (L1 presentation only): header edits (`rule`, handoffs, stage rulings) write
  None as `null`, as the templates do, instead of a blank value. Both parse to null; a blank
  value already in a file becomes `null` the next time that header is edited. No migration.
- C5 (L2 read-only, L3): `toulmin calibration` derives adoption of review drafts per model,
  role and operation from Runs, intake.md and Objections; `--write` regenerates
  global/calibration/calibration.md. Formats unchanged.
- V2 (L2 read-only, L3): `toulmin map [--watch]` shows stage, next gate, pending decisions,
  suggested moves and the argument tree from files; one rule table (`next_moves`) now also
  writes the state card's suggested ACTIONS. Formats unchanged.
- R1 (L1 additive, L2, L3): `toulmin draft` writes prefilled ruling, intake, review, Brief and
  stage proposal drafts; a ruling proposal may name `objects` (one ruling for several objects
  of one kind); decide refuses proposals with unfilled placeholders. Existing files unchanged.
- R2 (L3 text, template): project contexts carry `guide.md`, a compact guide to the loop and
  the `toulmin draft` proposal commands; the workspace AGENTS.md project steps name them.
  Formats unchanged.
- R2 follow-up (template text): the workspace AGENTS.md opening sends agents to the session
  context (guide.md, `toulmin draft`) before the framework files. Formats unchanged.
- R3/R4 (L2 rule row, L3): decide ends with each decided project's next moves and may send its
  bound session a one-line notice; after a stage ruling it suggests a handoff and a fresh
  session, and the rule table asks for a handoff while the stage is newer than the last one.
  Formats unchanged.
- R5 (L2 read-only, L3): gate readiness covers G3–G5 (Spec→current Claim and runnable
  acceptance criteria; implementer test Evidence; verified Evidence from a `verifier` Run on
  passed Specs); G2 names deferred fatal/major Objections as advice; status, card and map warn
  when the stage is past a gate that does not hold. Formats unchanged; the Spec skeleton and
  example put acceptance commands in backticks.
- R6 (L1 additive archive file, L2, L3): independent sessions that report token usage leave
  `usage.json` beside output.md; rounds print per-session and total tokens; calibration adds a
  token table; `aoe status` shows the native session's token totals from its own log. Run
  fields unchanged; older archives need no migration.
- R5 follow-up (L2 rule row): the suggested moves ask the agent to propose supported rulings
  for Claims that meet the supported conditions and have no pending ruling. Formats unchanged.

- R8 B2 (L1 additive, L2, L3): build-request proposals, prefilled `draft build`, full
  contract/check/G3 preview and researcher-confirmed `chief new` through decide. Freeze checks
  and archive startup/output with interrupted recovery; no Spec status change. Existing
  objects unchanged; no migration. Chief import/verify and map integration remain deferred.

- R8 B3 (L1 additive, L2, L3): read-only Chief facts in map/cards and shared next moves;
  confirmed done/abandoned imports archive results and record implementer Runs. Recoverable
  imports draft a Decision, model-asserted Evidence and a ruling; decide rescans and resolves
  applied Evidence filenames in links. No automatic Spec/stage change or independent acceptance.
  Existing object v1 unchanged; no migration. Verification remains B4.

- R8 B4 (L1 additive, L2, L3): researcher-confirmed deterministic verification in disposable
  clones at imported heads, using archived frozen checks and per-check process-group timeouts.
  Journal immutable checkpoints, verifier Runs and proposed Decision → verified Evidence → passed
  rulings; decide rescans. Failed/timed-out checks produce no proposals and suggest return or
  re-request. No automatic gate/status changes; existing object v1 unchanged, no migration.

- R8 B5 trial corrections: explicit folder-trust/kickoff guidance, compact Chief task names,
  running-task advice and per-Spec G4 suppression. Import bounded, nonsymlink progress from
  Chief's task copy or `.chief/progress.md`, recording the source. Verify distinguishes
  Toulmin Python and records the check shell/PATH. Existing archives and recovery remain valid.

- R8 B6 corrections: manual kickoff guidance after folder trust, interrupted recovery and
  startup; needs-you distinguishes an absent kickoff_at from inbox attention using key
  presence only. Add version-asserting check hints to the guide/build skeleton. No automatic
  kickoff or version probes; existing archives and object schemas remain valid.

- S2: ignore native bindings and tools/*.local.toml; merge chief.local.toml overrides with
  portable Chief settings and expand repository/home tildes. Status/open add offline,
  nonblocking migration advice; WI7 plans include machine-local ignore patterns. Missing
  dataset browsing already degrades gracefully; strict apply/pin checks are unchanged.
  Existing records/configurations remain compatible; migration steps are printed, never run.

- S3: resolve verification repositories by the pinned commit, preferring the archived path
  then the current project mapping; archive/preview the path and reason without rewriting
  frozen checks. Pending journals retain their chosen path; old journals still resume.
  Build intents record the starting host; foreign-host recovery refuses, and missing local
  tasks show where Chief must continue. No remote command, transfer or object-schema change.
