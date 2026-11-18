# Existing repositories: workspace-first onboarding

A repository is a body of work, not automatically a research question. Keep its code
in place and create a separate records workspace. Overall understanding and shared
logical sources belong to the workspace; projects are optional independent goals with
explicit scope and acceptance criteria. Discussion, maintenance and ordinary engineering
need no placeholder child, Claim, Spec or research gate.

## Three explicit modes

```sh
# A: new workspace only; zero projects
 toulmin onboard /code/service --root /records/service-research --init
# B: new workspace plus exactly one explicitly requested project
 toulmin onboard /code/service --root /records/service-research --init \
   --project latency --project-input /drafts/latency.md
# C: new project in an explicitly selected EXISTING workspace; checked reuse
 toulmin onboard /code/service --root /records/existing --project latency \
   --project-input /drafts/latency.md --source-id source-main
```

The leading spaces are typography. `--root` is mandatory for intake; cwd, registry,
source name and native history never select it. `--init` permits only a missing/empty
root or `.git` alone. It refuses an initialized or unrelated nonempty root. Without
`--init`, select an existing workspace and a new `--project`; requesting an existing,
empty, corrupt or staged child name refuses. There is no continue-existing fallback.
Opening an existing project is `toulmin open NAME --root ROOT`.

Each command inspects the source read-only and shows a sealed root packet. No source
scripts, hooks, model, native session, copy, move or scientific ruling runs during
intake. Review its exact inventories, uncertainty, proposed overview, source roles,
child framing and diffs, then use `toulmin decide --workspace --root ROOT` in your own
terminal. Explicit initialization remains if you reject; source registration, confirmed
understanding and children appear only after apply. Intake itself grants no write access.

`--project-input` is the unchanged v1 project-creation input (workspace-formats section 9).
Its project name must agree; included/excluded scope and the initial Brief's minimal
validation experiment frame acceptance. Omitting this input for an explicit requested
child retains the provisional compatibility framing, shown in full for review. Omitting
`--project` creates no child; neither a sole child nor source basename supplies one.

## Understanding and source roles

### Large repositories and component-focused inspection (MI1)

Always pass the Git root as SOURCE. To inventory a component, add repeated literal
`--include PATH` prefixes in priority order and optional `--exclude PATH` prefixes:

```sh
toulmin onboard /code/monorepo --root /records/component-research --init \
  --include component/README.md --include component/src --include component/tests \
  --exclude component/tests/generated
```

Paths must exist inside SOURCE; they are not globs or Git pathspec expressions. The
immutable revision-2 source definition retains this policy for later observations,
overview updates, native context and task checks. Omitted flags inherit the registered
policy; explicitly different flags refuse. Old revision-1 definitions/hashes stay valid.
Older Toulmin readers reject revision-2 definitions and must be upgraded before opening
these records. New fields do not rewrite existing workspaces or archived snapshots.

Selection bounds inventory only: source identity, native cwd, Chief repo and global
Git cleanliness remain rooted at the whole repository. Include priority and truncation
are recorded; large filenames are streamed under fixed budgets. This does not copy code,
select a branch, create a child or restrict write permissions. Explicit inspection flags
with `--work-at`, directory sources and exclude-only selections are refused in this slice.
See [scope and acceptance](monorepo-onboarding.md).

`WORKSPACE.md` stays the 40-line confirmed charter. Root `overview.md` is a separately
receipted structural checkpoint: Structure, Entry points, Current behavior, Checks and
Known gaps, with exact source pins, coverage and limits. Root `runs/notebook.md` is an
append-only unconfirmed working log, never formal Evidence or a complete transcript.
Corrections append a new dated entry rather than rewriting prior observations. Prepare
one entry using the contract's timestamp/title, Source/snapshot, Author/model/native
session, Coverage, Limits, Observation and Next measurement shape, then append under
the workspace writer lock:

```sh
toulmin workspace note --root ROOT --input ENTRY.md
```

Historical hand-written notes remain readable as opaque Markdown.

A/B prepare a provisional workspace overview if none is supplied. Use `--workspace-overview
FILE` for its body, and optional `--charter-input FILE` for reviewed charter fields. In A,
`--overview FILE` aliases the workspace body. For an explicit child in B/C, the old
`--overview FILE` still means child overview; `--project-overview FILE` is its alias.
C never changes unrelated root charter/overview bytes; it archives a provisional note.
Later understanding is a separate operation:

```sh
toulmin draft overview --workspace --root ROOT
# Fill its body, then inspect exactly the sources named here:
toulmin overview --workspace --input FILE --source source-main \
  --rationale "Reviewed current structure and known gaps" --root ROOT
toulmin decide --workspace --root ROOT
```

New catalogs use v2 definitions and scope associations. Each source is registered once
at workspace scope; projects reference it. Working/reference selects cwd, not permissions.
No working selection is valid portable state, but a scope with references cannot launch
at an arbitrary reference or fall back to the records directory. With no associations,
source-free sessions retain the records-root behavior.

Confirmed source rebind, for v1 and v2 catalogs, checks live/unknown writers across every profile at the selected
source's old/new canonical checkout and saved old device/inode. An unrelated source's writer
does not block a distinct rebind. Local coordination cannot isolate arbitrary external
writers; selection, launch permission and rebind remain separate actions. Preview and
`aoe status --offline` read files without constructing a native client, even when a saved
binding exists. V1 catalogs, source identities and project roles are not converted by bind.

A/B initially select SOURCE working at workspace and requested-child scope. `--work-at
TARGET` instead selects TARGET working and SOURCE reference, using existing non-overlapping
directories only. In C, it sets these roles only for the NEW child. Newly registered
sources get workspace references; old workspace working selection (including absence),
old child roles/files and unrelated root context stay unchanged.

```sh
toulmin source list --workspace --root ROOT
toulmin source add /code/fork --workspace --register-source source-fork \
  --rationale "A deliberate separate checkout" --root ROOT
toulmin decide --workspace --root ROOT
toulmin source working --workspace source-fork --rationale "Continue here" --root ROOT
toulmin decide --workspace --root ROOT
```

Use `--source-id ID` for exact checked reuse or `--register-source ID` for a distinct
checkout, with corresponding `--working-source-id`/`--register-working-source` for
`--work-at`. Matching upstream names alone never merge identities. Saved path and device/
inode collisions, nested roots, symlinks, traversal and Git subdirectories refuse.
Missing/stale mappings require explicit binding; intake never silently rebinds:

```sh
toulmin source bind source-main /new/local/checkout --root ROOT       # preview only
toulmin source bind source-main /new/local/checkout --root ROOT --confirm
```

Git identity retains the v1 root-commit-list algorithm; HEAD/dirty files are observations.
An ordinary directory keeps its initial anchor identity during in-place use. A moved or
replaced edited directory must reproduce its original anchors to bind the old ID. If it
cannot, preserve old provenance, independently prepare a distinct path AND device/inode,
register a reviewed new source as reference, then separately propose its working selection.
A retained old inode or saved-path collision still refuses; Toulmin never copies, re-anchors
or removes the old definition/binding to bypass this boundary.

Discovery remains bounded: 400 files, 512,000 read bytes, 32,000 bytes per text file and
3,200 candidates; escaped inventories/images are capped at 1,000,000 bytes. Credential
filename patterns, symlinks, generated/ignored/dependency material and nonregular files
are excluded. Binary/oversize entries may have size only. These filters are not a secret
scanner; omissions do not establish absence, and dirty snapshots are not complete trees.

## Conversations and local permissions

```sh
toulmin open --workspace --root ROOT
# For a new external-source Codex scope without a terminal, explicitly choose once:
toulmin open --workspace --root ROOT --codex-sandbox workspace-write
# Or preserve native settings:
toulmin open --workspace --root ROOT --codex-sandbox inherit
```

The existing permission mechanism now supports workspace scope in the same ignored
`tools/native.local.toml`: old project-only files remain v1; adding a workspace intent
uses v2 with an explicit workspace table and retained project choices. Choices never
transfer between scopes. Registration, native folder trust, permissions, Chief kickoff
and scientific acceptance are separate authorizations. No global Codex/AoE settings,
full-access flag or trust autoaccept is added. The interactive choice holds no locks;
checkout/root/scope state is revalidated under ordered locks before any save/launch.

Source-backed new/replacement sessions on v2 catalogs use native binding v4. Portable
tracked context snapshots exclude local paths; ignored scope `.aoe/contexts/TOKEN/`
holds local.json, manifest.json and the context-read receipt. Read both the delivered
context and the announced local.json, then run its exact ack command. Submitted is not
acknowledged; acknowledged is not scientific approval. Old v1/v2/v3 bindings, manifests
and archives stay in their original formats/locations, with same-version explicit refresh.

Changing selection, checkout identity or records location never redirects an existing
session. Inspect/archive the old session, then explicitly `open --new-session` or scoped
`aoe bind --replace`. Old contexts and replaced v4 bindings remain archived. Missing/
uncertain cross-profile session state refuses a new writer; a live writer at the same
path or device/inode conflicts across scopes/profiles. This local coordination cannot
isolate arbitrary external or cross-machine writers. Native trust/update prompts require
your action; no broader-access retry is attempted. Resolve them, run the printed scoped
`aoe refresh` command, then check acknowledgment separately.

Explicit `--workspace` wins in open/status/map/draft. Bare open from a child's records
directory retains child inference only with cwd root discovery; explicit-root open without
a project stays workspace. Bare map retains its existing records-directory inference,
including with explicit root. Bare status stays workspace. A linked source checkout,
sole child or history never supplies a child argument.

## Workspace engineering and later projects

```sh
toulmin draft task --workspace --source source-main --name parser-helper --root ROOT
# Fill Goal/Scope, checks, protection, budget and launcher choices in the returned FILE.
toulmin task preview --workspace FILE --root ROOT
toulmin decide --workspace --root ROOT
# After Chief reports done/abandoned; this first command only previews:
toulmin task import --workspace FILE --root ROOT
toulmin task import --workspace FILE --root ROOT --confirm --confirmed-by ACTOR
```

V2 task requests pin scope, source definition/catalog, bounded inventory and full baseline
commit. They contain no absolute repo path; the ignored local export supplies that only
at Chief launch. A clean Git source and matching pin/baseline are required before submission.
An explicitly named reference source is allowed and does not change native working selection.
An applying outcome and exact frozen export precede `chief new`; retry reconciles the SAME
ID, home, host, repo, base and contract. An uncertain attempted launch without a visible
matching task stays applying for inspection; it never blindly creates a second task.
Submission adds no scheduler or automatic kickoff. Resolve Chief's native trust prompt
and use its existing kickoff/watch supervision.

Workspace imports create an operational `runs/...-task-...-result/run.md`, with no root
formal Run IDs. Failed/abandoned output and raw provenance remain archived; machine-path
bearing raw artifacts stay ignored under `.aoe/task-results/`. Portable records retain
hashes and local-availability limits. Project v2 imports use ordinary project Run IDs;
legacy project v1 task/import semantics remain supported. No import merges, pushes,
executes checks, creates scientific Evidence or changes gates. Worker results are not
independent acceptance.

Later derive one reviewed child without repeating intake or moving history/code:

```sh
toulmin project propose throughput --input runs/drafts/project-throughput.md \
  --source source-main --working-source source-main --root ROOT
toulmin decide --workspace --root ROOT
# A separate explicit open; creating the child starts no writer:
toulmin open throughput --root ROOT
```

Without `--working-source`, every named source is reference; the workspace selection is
never inherited. Without source flags, legacy unlinked child creation remains unchanged.
A creation input can explicitly carry root overview.md by its source reference/digest;
child contexts restore that frozen understanding, never a sibling history or root notebook.

## Decisions, recovery and compatibility

Noninteractive decide lists pending items and writes no decisions. The unified queue
remains available; `--workspace` filters root publications/tasks and `--project NAME`
filters an existing child. No bulk yes, pipe-driven approval or environment default is
added for new v2 packets. Authorized operators can approve exactly one reviewed seal:

```sh
toulmin workspace apply PACKET --expect-seal SHA --confirmed-by ACTOR --confirm --root ROOT
toulmin workspace reject PACKET --expect-seal SHA --confirmed-by ACTOR \
  --reason "Revise scope" --confirm --root ROOT
```

Without confirmation, apply previews without writes. The v1 `workspace apply/reject
--draft PACKET` forms remain supported. A declared actor is authorization provenance,
not authentication or a researcher usability ruling.

Publication reuses v1 child creation/receipts and the existing forward-only journal.
Child archive plus ownership marker become visible together, then the outer seal; a
missing/damaged marker cannot bypass sealed ownership. Before journal commit, no confirmed
target changes. After commit, replay the exact apply to finish the approved images with
the original actor/time. During the journal, the child is unusable and source-backed
writers refuse. Reads never recover. Unexpected staged/published files or bytes matching
neither before nor after stop all further writes and preserve the journal/images.
Replay after later legitimate changes never restores older target bytes.

V1 catalogs remain readable/writable on their old project path. Workspace source work
or C stops at v1 and points to a separate opt-in operation:

```sh
toulmin source upgrade --root ROOT          # proposal, never automatic conversion
toulmin decide --workspace --root ROOT
```

Conversion preserves exact legacy bytes in its sealed packet, old projects/roles/local
mapping, and adds workspace references only. Pending v1 source packets must be decided
first. Unknown/damaged active formats fail explicitly and never fall back to legacy
artifacts. Opaque legacy identities remain usable under v1; a value not representable
by strict v2 definitions refuses conversion rather than rewriting its provenance.
No mandatory migration or automatic downgrade is introduced.

Automated fake-service checks are technical evidence. Live A/B/C/native/engineering
journeys belong to the supervisor and remain separate from researcher usability
acceptance. See the frozen workspace-onboarding-contract.md for exact schemas and
workspace-onboarding-acceptance.md for the pending live trial recipe.
