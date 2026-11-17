# Workspace-first onboarding of existing repositories

Status: product direction accepted by the researcher on 2026-11-18; documentation only.
This supersedes O's mandatory initial-child assumption for future development.
The accepted refinement supports three explicit intake modes; workspace ownership
does not require postponing a requested project until a later session.
The current executable behavior remains documented in [onboarding.md](onboarding.md).
Implementation, exact serialized contracts and live acceptance are not completed.

## Accepted purpose and user journey

A repository is an existing body of work, not automatically a research question.
Onboarding first establishes a workspace where the researcher and agent can understand
its history, structure, working state and intended future. Projects are optional units
with independent goals, scope and acceptance criteria. A researcher with a clear goal
may create one during intake; others can explore first and create projects later.
Ordinary discussion, maintenance and engineering may continue at workspace scope.
There is no requirement to create a project, invent Claims or satisfy research gates
before doing this work. Research gates still apply to research projects using them.
L0 principles and researcher confirmation of formal research judgments remain intact.

### Three accepted entry modes

Workspace selection and project creation are independent explicit choices:

| Mode | Workspace action | Project action |
| --- | --- | --- |
| A: repository to new workspace | Initialize separate records; register source and overall understanding | None; explore or work at workspace scope |
| B: repository to new workspace and one project | Initialize separate records; register source and overall understanding | Create exactly one explicitly requested project and source association |
| C: repository plus existing workspace to new project | Use the explicitly selected workspace; register or reuse source | Create exactly one explicitly requested new project there |

Mode A is the project-free path when no child is requested. B is a first-class path,
not a deprecated compatibility shortcut. C never creates another workspace or selects a
workspace from ambiguous native/session history. An unrelated nonempty records directory
is still refused. Exact CLI flags and serialized forms are to be frozen in WO2.

### Shared preparation and confirmation

1. Resolve the requested workspace and explicit optional new-project intent. For C,
   require a valid existing workspace and reject an existing/conflicting project name.
2. Inspect the source read-only; prepare a scoped source/understanding proposal under
   root `runs/`. A and B explicitly authorize initializing a missing/empty records root.
3. For B/C, include the new project's goal, scope, acceptance criteria and association
   with a workspace-owned source in the same reviewed packet. Do not auto-start a session.
4. Researcher confirms through `decide`. A publishes no child or project state. B/C
   publish exactly the reviewed child and association with the source registration.
   Rejected/stale/tampered packets cannot leave a partially published usable child;
   use the existing journal/recovery model and idempotent receipts.
5. For C, reuse an already registered logical source only after identity/local-binding
   checks. Otherwise propose registration once. Matching upstream names alone must not
   merge different checkouts or identities. Do not change existing projects, working
   source selections or the workspace charter/overview as a side effect; any intentional
   revision of confirmed context requires a separate explicit reviewed change.
6. Open the chosen workspace or project conversation separately. Keep overall exploration
   in workspace records; project-specific work belongs to the explicitly selected child.
7. Workspace-only work may continue indefinitely. Later independent topics use the same
   reviewed project-creation path, linking shared sources without moving workspace history.

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

- Extend onboarding to workspace scope without requiring `--project`; support A/B/C as
  explicit first-class choices. Omitting a child request never infers one from the source
  directory name, an only child, a prior binding or session history.
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

This documentation task changes no real workspace/project. Future mode C may add a
reviewed source and new project to an explicitly chosen existing workspace; it must not
delete, rename, flatten, reparent or migrate existing projects. In particular, leave the
current Weekly-Projects trial untouched. Existing overviews, IDs, source entries, proposals,
receipts, bindings and handoffs retain their meaning and remain usable.

WO2 must specify readers for existing v1 source catalogs and native v1/v2/v3 bindings,
new-format version handling and compatibility fixtures. Existing files must not be
rewritten on status/open. Do not ship a mandatory data migration. If any later design
requires rewriting old data, that needs a separately authorized previewed migration with
preserved provenance before it can be required; this design authorizes no such operation.

Current O1–O5 completion records remain historical implementation facts. This design
removes mandatory child creation, without changing historical acceptance records.
The Chief task `o3-general-codex-permission-co` remains limited to its existing permission
contract; do not amend it or interrupt active research/development sessions for this work.
Reuse its eventual permission mechanism through an explicit scope-aware extension later.

## Planned work and executable acceptance scenarios

All implementation checks below are NOT RUN; task tracking is in TODO.md (WO1–WO5).

- WO2: freeze contracts and a matrix covering A/B/C, registered/unregistered sources,
  zero/multiple existing children, duplicate names, ambiguity and old-format readers.
  A must require no sentinel project; B/C must be explicit with no automatic scope choice.
- WO3: in temporary code/records fixtures, preview and confirm all three modes. A leaves
  `projects/` empty; B creates one requested child in a new workspace; C creates one in
  an existing workspace. For C, test reuse and new registration, unchanged old projects,
  unchanged unrelated workspace context and no duplicate source association. All modes
  leave source bytes unchanged and cover rejection, stale/tampered input, replay and
  interruption recovery without partial publication.
- WO4: fake-AoE tests open/restore explicit workspace/project scopes at their selected cwd,
  with context/permission arguments and identity/conflict guards. Project-free status/map
  offer useful actions without demanding Claims; bounded workspace tasks/results retain
  scope and pinned source versions. Creating a child never redirects a live session.
- WO5: later reviewed project derivation links shared source references without moving
  history/code. Regress old source catalogs, native bindings, receipts and explicit project
  onboarding. Run disposable live journeys for A/B/C, including source reuse in C, plus
  zero-project discussion/work, later child creation and next-session restoration.
  All scenarios are technical evidence; researcher usability acceptance is separate.
