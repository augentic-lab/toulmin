# Toulmin user guide: the research workflow

This guide explains how a researcher works with Toulmin day to day: what to do, in what
order and why. It describes the question-first workflow introduced in 2026-11 (P0). For
installation and the command reference see [README.md](../README.md); for the rules behind
the workflow see [design.md](design.md) and [protocols.md](protocols.md).

## 1. The idea in one paragraph

You think and work with an AI agent in a terminal session. Toulmin keeps what you learn in
plain files and changes the confirmed files only when you decide. The agent proposes; you
confirm in `toulmin decide`. You do not need to plan Claims up front: start from a simple
question, work on it, and turn results into formal records when they are worth keeping.

## 2. Setup

1. Create a workspace in a new, empty directory: `toulmin open` and answer `y`. It
   initializes a git repository and opens a workspace session.
2. In that session, describe the question, constraints, what you already know and the
   metric you care about most. These few sentences steer everything that follows.
3. When a direction is concrete, ask the agent to make it a child project. It drafts a
   creation proposal; apply it in `toulmin decide`; then run `toulmin open NAME` from the
   workspace root to open the project's own session.

Initial project state: `PROJECT.md` has `stage: explore`, a goal and constraints; `brief.md`
holds a first outline from the creation proposal (question, motivation, scale, known
counterarguments, kill criteria, smallest validating experiment), all still hypotheses. The
`claims/`, `evidence/`, `objections/` and `decisions/` folders are empty.

Keep two terminals: the agent session (in AoE), where you think and work, and your own
terminal for `toulmin decide`, `toulmin map NAME` and `toulmin commit`.

`toulmin map NAME` (and `toulmin open NAME`) shows the project card: the question, one line
per Claim (✓ supported or ready to rule, ? fatal/major doubts open, · no verified Evidence
yet), the main open doubts grouped by Claim, what waits in `decide` and up to three next moves.
`toulmin map NAME --full` shows the gates, the whole argument tree and sources.

## 3. The working loop

```text
question → smallest measurement or prototype → observation (notebook) → Claim + Evidence
   ↑                                                                        │
   └──── optional: independent review → Objections → discuss / measure → ruling
```

1. **Start from the question and just work.** The agent suggests the smallest next
   measurement, prototype or reading and logs dated observations, numbers, attempts and
   hunches in `runs/notebook.md`. None of this needs `decide`.
2. **Promote what is worth keeping.** When a result is reproducible, when you state a
   conclusion, or when work pauses or ends, the agent asks once whether to promote it. If
   you agree, it drafts a Claim (one testable statement) and the Evidence for it; you apply
   them in `decide`. You can also ask for promotion at any time.
   - Evidence is `verified` only when it can be re-checked: it names a method and the raw
     files under `runs/`. `model-asserted` and `intuition` Evidence can never support a
     Claim on their own.
3. **Optionally look for mistakes.** Keep discussing in the current project conversation.
   Ask the agent to plan with `toulmin review NAME --dry-run`, then prepare a request with
   `toulmin draft review NAME`. The plan starts no review. Apply the request in your own
   `toulmin decide` to authorize quota-consuming independent model sessions. Reviewers and
   synthesis use fresh isolated sessions with restricted inputs; the project agent remains
   your coordinator. The agent then recommends intake for each finding; findings you take
   become Objections. In explore the map does not suggest reviews, so ask when you want one.
4. **Deal with Objections.** Discuss them, and add measurements and Evidence where needed.
   Each Objection ends in one of three states:
   - **answered**: a Response addresses it;
   - **accepted**: it holds; the Claim is then superseded by a revised Claim or refuted;
   - **deferred**: set aside with a reason; a deferred major Objection still matters later.
5. **Settle the Claim.** With verified supporting Evidence and no open fatal or major
   Objection, the map suggests a `supported` ruling; the agent drafts it with a Decision
   and you apply both. A review is not required for this step.
6. **Go back to the question.** There may be one Claim or many; take them one at a time. A
   project is finished when its question is answered, not when every Claim is supported. A
   refuted Claim is a valid result.

### How the three objects relate

- **Claim**: a testable statement; the centre of the network.
- **Evidence**: supports or refutes one Claim (`target`, `direction`), with a kind and grade.
- **Objection**: challenges a Claim or its reasoning, with severity fatal, major or minor.

### When Decisions and the Brief are written

- **Decisions** are written throughout. Every formal status change cites one: an Objection
  ruling, a supported or superseded Claim, a passed Spec, a stage change. Important scope
  or direction choices are recorded as Decisions too. The agent drafts them together with
  the ruling; you apply them in `decide`.
- **brief.md** starts at project creation and is revised section by section through Brief
  proposals, for example to fix kill criteria or to write down the current answer. It
  changes when you ask.

### Stages and gates

`stage` (explore → critique → brief-final → build → accept → done) and gates G1–G5 still
exist, but they are information, not tasks. The agent does not draft Claims to fill a gate
and does not propose a stage change on its own; ask when you want to move on.

After you approve entry into critique, continue in the same project conversation: review
dry-run → review request draft → approval in `toulmin decide`. A handoff, manual archive or
replacement coordinator session is not required to prepare or start independent review.
Choose a handoff and a fresh coordinator only when you want to manage a long conversation
or pause work. Nothing archives automatically. Plain `toulmin open NAME` may resume the
existing binding; use `--new-session` only for an explicit replacement.

## 4. Large tasks: handing work to Chief

Do small implementation and measurements in the session. For a large task that should run
unattended for a long time, use AoE Chief. The agent asks once whether to hand such a task to
Chief; this is possible in any stage.

Ordinary workspace engineering uses scoped tasks without a Claim, Spec or gate; see
[existing repository work](#existing-projects-and-gradual-rebuilding). The scientific build
route below remains available when implementation is intended to test a project Claim.

### Where the work lives

| | Small task (in the session) | Chief task |
| --- | --- | --- |
| Code | `projects/NAME/runs/<timestamp>-<name>/` | a separate code git repository, outside the project directory |
| Working directory | selected source checkout for source-backed scopes; records root otherwise; source repository rules govern code | Chief creates a worktree and branch `chief/<task_id>` per task; the AoE `[worktree] path_template` decides the location (by default beside the repository) |
| Records | raw output in `runs/`, observations in `runs/notebook.md` | archived under `runs/<timestamp>-build-S-NNN/` on import |

Register the code repository in the workspace's machine-local `tools/chief.local.toml`:

```toml
[repos]
my-project = "/path/to/code-repository"
```

Do not put the code repository inside the workspace; that nests one git repository in
another. If a small script will be reused or extended by Chief later, put it in the code
repository from the start and keep only outputs in `runs/`.

### Steps for a scientific build

1. **A Claim exists.** A Spec must target a current Claim.
2. **Spec** (`S-NNN`): which Claim it serves, what to implement (Requirements) and when it is
   done (Acceptance criteria as commands that run on this machine). The agent drafts it; you
   apply it in `decide`.
3. **Build request**: the agent drafts it. To run the worker through another launcher (for
   example a wrapper for a different model), say so; the agent then sets `command:`.
4. **Start**: `toulmin decide` shows the frozen contract (and the worker launch command, if
   set); apply it with `a`. Handle any native trust prompt, then use Chief's manual kickoff
   guidance. Submission alone does not guarantee a worker has started.
5. **While it runs**: answer worker questions and permission prompts through `chief inbox`.
6. **Accept in Chief**: when the task is ready to accept, `chief close TASK_ID`; use
   `chief nudge` to ask for more work.
7. **Import**: in `decide` (or `toulmin build import NAME S-NNN --confirm`). Toulmin archives
   the commit, diff, review and progress, records an implementer Run and drafts a Decision,
   model-asserted Evidence and an awaiting-acceptance ruling for the Spec. Apply each.
8. **Verify** (optional, recommended): in `decide`. Toulmin makes a temporary clone outside
   the workspace at the imported commit, reruns the frozen checks in order as you (without
   network isolation), records `output.md`, `environment.txt` and `verify.json` under
   `runs/<timestamp>-verify-S-NNN/` and deletes the clone. Only if every check passes does
   it draft a Decision, verified Evidence and a passed ruling. A failure leaves only records.

A passed Spec does not finish the project: it adds verified Evidence to its Claim. Whether
the question is answered is your call (formally G5 plus your stage ruling).

Chief also works directly with `chief new`, but then its results do not enter Toulmin's
records.

## 5. Routine per session

| When | What |
| --- | --- |
| Start | `toulmin open` (anywhere; it lists known workspaces) or `toulmin open --in WORKSPACE NAME`; if the git line says `behind`, `git pull --ff-only` first |
| During work | the agent says at natural pauses how many items wait and which (at most three) need real thought; run `toulmin decide` |
| After a Toulmin update | when the session is idle, `toulmin aoe refresh NAME` delivers the new guidance |
| Long conversation | optionally: handoff → `decide` → archive the old AoE session → `toulmin open NAME --new-session` |
| End | `toulmin commit` (preview; check for large files) → `toulmin commit --confirm` → `git push` if you use a remote |
| Retire a workspace | `toulmin workspaces remove NAME` (preview), then add `--archive FILE.tar.gz --confirm` |

Large re-downloadable files (for example upstream source archives) belong in `.gitignore`;
record their URL and checksum in `runs/` instead.

## 6. Keeping the load low

- Give facts before asking for responses: one line such as "no production profile" or "the
  main metric is X" replaces paragraphs of conditional text.
- Ask for length limits, for example "each response under 150 words".
- Spend attention by severity: read fatal and major findings in full; minor items and
  duplicates can follow the recommendation once the reason is sound. Do not let "as
  recommended" become a habit.
- One review round per question is usually enough; run another after new data. Without new
  material, `decide` warns that a round will likely repeat.

## 7. Boundaries that do not change

- The agent only proposes. Every formal change is applied by you in `decide` or with
  `--confirm`; agreeing in chat records nothing.
- The agent does not commit, push or change the stage.
- Model output lands in `runs/` first; condition checks report, they never change status.

## 8. Not yet built

From the workflow redesign (P1–P4): a four-part living document (question, answer, doubts,
next experiment), checkpoint-style `decide` that confirms a batch at once, gates on
individual conclusions, and entering review without rolling the session over by hand.

## Existing projects and gradual rebuilding

Keep code and Git history in place and create separate research records:

```sh
toulmin onboard SOURCE --root ROOT --init
toulmin decide --workspace --root ROOT
toulmin open --workspace --root ROOT
```

This starts with zero projects. Add explicit `--project NAME [--project-input FILE]` for one
independent goal during intake. For C, select an existing workspace with --root and omit
--init; do not infer a child from its source basename or the workspace's sole project.
Review source identities, inventory limits, source roles and exact overview before apply.

Shared understanding/sources, discussion, maintenance and ordinary engineering belong to
the workspace. Distinguish file facts, the researcher's account and model guesses. Append
unconfirmed dated notes with `toulmin workspace note --input ENTRY --root ROOT`; propose
shared checkpoints using `draft overview --workspace` and `overview --workspace`. A fresh
session restores confirmed context and a labeled bounded notebook excerpt, never a complete
transcript. Code follows source repository rules; research records follow scoped decisions.

For substantial ordinary engineering use `toulmin draft task --workspace --source ID
--root ROOT`. Fill Goal/Scope/checks/protected paths/budget, preview with `toulmin task preview
--workspace FILE --root ROOT`, then review in `toulmin decide --workspace`. Chief uses a
separate worktree. `toulmin task import --workspace FILE --root ROOT` previews the result;
`--confirm --confirmed-by ACTOR` records an operational workspace Run with no formal ID.
No Claim/Spec is required and delivery is not scientific acceptance. Project v2 tasks use
`draft task NAME --source ID` and `task import NAME FILE`; legacy v1 tasks retain their
project draft/proposals and `task import NAME TASK_ID` paths. The Claim/Spec build route
remains available for research experiments.

Later `toulmin project propose NAME --input FILE --source ID [--working-source ID]
--root ROOT` derives a reviewed independent child without moving history/code or opening
another writer. Without --working-source it links references only. Explicitly pinned shared
context can carry into the child; root notebook and sibling histories are not inherited.

For a new direction, --work-at TARGET uses an already existing separate working repository
and retains SOURCE as reference. Neither is copied/synchronized by Toulmin. C changes only
the new child's selection; it preserves existing workspace/project working choices. Adapt
one module/dataset at a time and preserve raw source version, failed batches and checks.
An explicit child may additionally use `migration draft NAME` / `migration record NAME
--input FILE --confirm`; these record an assessment and never execute its checks.

After moving/cloning records, `toulmin source bind ID PATH --root ROOT` previews a local
mapping; --confirm replaces only that entry after identity/writer checks. It never changes
source selection or redirects a native session. Source selection, native permissions, Chief
kickoff and scientific approval stay separate. See [onboarding](onboarding.md) for exact
commands/recovery/legacy conversion and the [pending supervisor live trial](workspace-onboarding-acceptance.md).

## Explicit review profiles (R11)

For a bounded round, configure tools/models.toml and preview `toulmin review NAME
--profile hypothesis --dry-run`, then draft the request with the same profile and
confirm in decide. The total cap includes the independent synthesis. See
[review profiles](review-profiles.md) for configuration, identity/availability limits
and calibration. Existing legacy direct reviews stay review-only by default.
