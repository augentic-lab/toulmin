# Workspace-first onboarding of existing repositories

Status: product direction accepted by the researcher on 2026-11-18; documentation only.
This supersedes O's initial-one-child onboarding default for future development.
The current executable behavior remains documented in [onboarding.md](onboarding.md).
Implementation, exact serialized contracts and live acceptance are not completed.

## Accepted purpose and user journey

A repository is an existing body of work, not automatically a research question.
Onboarding first establishes a workspace where the researcher and agent can understand
its history, structure, working state and intended future. Projects emerge only when
an independent goal, scope and acceptance criteria warrant separate tracking.
Ordinary discussion, maintenance and engineering may continue at workspace scope.
There is no requirement to create a project, invent Claims or satisfy research gates
before doing this work. Research gates still apply to research projects using them.
L0 principles and researcher confirmation of formal research judgments remain intact.

1. Initialize a separate records workspace and inspect an existing source read-only.
2. Prepare a workspace-scoped source/understanding proposal under root `runs/`.
3. Researcher confirms it through `decide`; no child directory or project state appears.
4. Open the workspace conversation, review observed facts and ask about the user's intent.
5. Keep exploratory discussion in workspace records; propose understanding/goal checkpoints
   when needed and wait for researcher confirmation before changing confirmed context.
6. Either continue a bounded workspace task, or propose one or more projects with explicit
   goals, scope, acceptance criteria and references to relevant shared sources.
7. Create a project only after confirmation; opening its session is a separate action.

No onboarding step starts a native session, executes source scripts, copies source code,
or establishes scientific conclusions automatically.

## Ownership and confirmation boundaries

| Information | Owner and update boundary |
| --- | --- |
| Overall purpose, constraints and next step | Workspace charter; reviewed changes |
| Structural overview and known gaps | Workspace confirmed understanding; reviewed snapshots |
| Code/data source identity and shared availability | Workspace source registry; reviewed registration |
| Local source path, checkout identity, native settings | Ignored machine-local configuration; explicit binding/permission choice |
| Exploratory notes and raw agent output | Root `runs/`; unconfirmed and provenance-preserving |
| Workspace handoff | Existing workspace handoff protocol and researcher confirmation |
| Independent goal, scope, acceptance criteria | Project charter/Brief after reviewed child creation |
| Project source use and working-directory selection | Explicit project-to-workspace-source references |
| Claims, Evidence, Objections and research stage | Existing project object/ruling protocols |

A shared source is registered once at workspace scope; projects reference its logical
identity without copying code or transferring ownership. Source availability is distinct
from selecting a session's writable working directory. A workspace/project may explicitly
select one working source and several references; multiple plausible working sources
require selection, never an arbitrary first-match or last-used-project fallback.
Project task contracts pin their relevant source versions; a workspace engineering task
can do the same without introducing a placeholder project, Claim or Spec.

A confirmed overview records approved context, not proof that historical findings are
correct. Preserve coverage, uncertainty and source snapshots. Agent notes never silently
become confirmed understanding or formal Evidence.

## Proposed implementation surfaces, not released commands or file formats

- Extend onboarding to workspace scope without requiring `--project`. Keep explicit
  project onboarding as a supported compatibility path, never the automatic default.
- Reuse `WORKSPACE.md` for workspace intent, existing root proposals/receipts/journal for
  confirmation, and root `runs/` for exploration. Freeze overview/note paths and exact
  schemas in WO2 before implementation; paths in this paragraph are architectural homes.
- Separate logical source definitions from scope associations. Current `sources.toml` v1
  combines them in `(id, project)` entries and cannot express project-free ownership.
  Define a versioned additive contract; do not use an invented/sentinel project name.
- Extend workspace context/status/map with confirmed understanding, sources, recent
  unconfirmed notes, handoff and available actions. With zero projects, lead with project
  understanding and possible work, not missing project research gates.
- Extend external-source cwd, identity pins, checkout conflict guards and explicit native
  permissions to workspace scope. AoE manages sessions; Chief manages worker execution.
  Never redirect a live session when selecting a source or creating a project.
- Extend bounded engineering drafts/submission/result records to workspace scope through
  existing confirmation and Chief boundaries; do not build a second scheduler.
- Project creation may link workspace understanding and source references after review.
  It must not move/copy history, create a second checkout or auto-start a competing writer.

## Compatibility, scope and dependencies

The researcher explicitly excluded modifications to already created workspaces/projects
from this task. Do not delete, rename, flatten, reparent or migrate Weekly-Projects or any
other real workspace. Existing project overviews, IDs, source entries, proposals, receipts,
bindings and handoffs retain their recorded meaning and remain usable.

WO2 must specify readers for existing v1 source catalogs and native v1/v2/v3 bindings,
new-format version handling and compatibility fixtures. Existing files must not be
rewritten on status/open. Do not ship a mandatory data migration. If any later design
requires rewriting old data, that needs a separately authorized previewed migration with
preserved provenance before it can be required; this design authorizes no such operation.

Current O1–O5 completion records remain historical implementation facts. This design
changes the future default, not the acceptance status of those older implementations.
The Chief task `o3-general-codex-permission-co` remains limited to its existing permission
contract; do not amend it or interrupt active research/development sessions for this work.
Reuse its eventual permission mechanism through an explicit scope-aware extension later.

## Planned work and executable acceptance scenarios

All implementation checks below are NOT RUN; task tracking is in TODO.md (WO1–WO5).

- WO2: freeze data/protocol/command contracts and an old/new compatibility matrix; examples
  must represent a workspace with sources and zero projects without a sentinel child.
- WO3: in a temporary code/records pair, onboarding preview and confirmed apply leave
  `projects/` empty, register the workspace source and understanding, and leave the source
  byte-for-byte unchanged. Stale/tampered/interrupted apply rejects or recovers safely.
- WO4: fake-AoE tests open/restore a source-backed workspace at its explicit cwd, with
  proper context/permission arguments and identity/conflict checks. Workspace status/map
  show useful next actions without demanding Claims. Workspace task preview/confirmation
  and result import preserve scope, source version and ordinary-Run semantics.
- WO5: a reviewed child proposal creates exactly the requested child and source references;
  workspace history stays in place and code stays unchanged. Regression fixtures retain
  old source catalogs, native bindings, receipts and legacy project onboarding behavior.
  Conduct a separate disposable live journey: zero-project intake, discussion/checkpoint,
  a small workspace task, then optional child creation and next-session restoration.
  Researcher usability acceptance remains an explicit ruling, separate from automated tests.
