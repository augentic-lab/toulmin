# Workspace onboarding contract (WO2)

Status: **WO2 implementation specification, not released runtime behavior**. Prepared
2026-11-18 against baseline `de55a1b0633ba7234587400d305cfba6a7413406` for independent
Chief review and researcher acceptance. WO2 remains pending researcher acceptance.
All WO3–WO5 implementation and live acceptance cases below are **NOT RUN**.

The researcher accepted the three modes in [the design](workspace-onboarding-design.md).
[Current onboarding](onboarding.md) describes existing O1–O5 behavior. This document
freezes the proposed formats, command forms and protocol changes for that design;
it does not authorize implementation, real-data conversion or source writes.
Existing contracts in [workspace formats](workspace-formats.md), [object formats](formats.md)
and [protocols](protocols.md) remain current until the corresponding implementation lands.

## Scope

| Mode | Explicit intent | Publication after researcher apply |
| --- | --- | --- |
| A | Repository → new workspace, no project argument | Workspace source definition, workspace association, confirmed overall understanding; zero children |
| B | Repository → new workspace, one requested project | A plus exactly that child's charter, Brief, creation provenance and source associations |
| C | Repository + explicitly selected existing workspace → one new project | Reuse or register source once, add exactly the requested child and its associations; preserve unrelated context and old children |

Workspace selection and optional child creation are independent. No source basename,
sole child, current source checkout, last-used scope or native history supplies a
missing project argument. Workspace discussion, maintenance and engineering require
no project, Claim, Spec or research gate. Projects express independent goals, scope
and acceptance criteria; scientific rulings retain the existing project protocols.

L1 validates bytes and ordinary scope/source/provenance values. L2 plans and publishes
workspace records using L1 only. Identity observations, Git execution, native launch,
Chief communication, terminal confirmation and provider permissions stay in L3
application/adapters/CLI. A tool/model name is provenance data in L1/L2, never a
vendor enum or control branch. The L2 change is necessary because reviewed source
ownership and transactional child creation now also exist without an initial child.
No scheduler, automatic session launch, script execution, network fetch, source copy,
automatic scientific approval or implicit writable permission is introduced.

### Common representation

All new documents use UTF-8, LF and root-relative portable paths, except explicitly
machine-local operational files. Restricted YAML follows [formats.md](formats.md).
Unknown or missing keys, duplicate keys, unknown versions, wrong scalar types
(including booleans for integers), traversal, symlinks and unexpected file types are
errors. Tables below list all allowed keys; optional keys are explicitly marked.
Nullable fields must be present with `null` in YAML/JSON. TOML has no null.

`Scope` is exactly `{kind: workspace}` or `{kind: project, project: NAME}`.
`NAME` matches `[a-z0-9]+(?:-[a-z0-9]+)*`; it is a single directory component.
Source IDs match `[a-z][a-z0-9-]{0,79}`. New generated IDs are
`source-` plus 16 random lowercase hex characters, with collision refusal/retry
before sealing, never overwrite. Human-supplied IDs obey the same uniqueness rules.
Time values are quoted RFC 3339 UTC strings. SHA-256 values are lowercase 64-hex over
exact file bytes. A nullable digest means an absent file, never an empty file.
A declaration of researcher confirmation records authorization, not authentication.

## Source catalog

### Tracked v2 schema

`sources.toml` version 2 separates definitions from scope associations. Its only
root keys are `schema_version` (integer 2), `definitions` (array of tables) and
`associations` (array of tables). Both arrays are required, including when empty.
Do not put local paths, remotes containing credentials, permissions or provider
settings here. Shared resource descriptions in `shared/resources/` remain distinct:
they describe research material, not native cwd/source registrations.

Each `definitions` entry has exactly these keys:

| Key | Type / constraint |
| --- | --- |
| `id` | Source ID, unique in this workspace |
| `definition_revision` | Integer 1 in this version; immutable after publication |
| `kind` | `git` or `directory` |
| `identity_method` | `git-roots-v1` for Git; `directory-anchors-v1` for ordinary directories |
| `identity` | `git:` or `directory:` followed by 64-hex, consistent with kind/method |

Definitions are immutable facts about registered logical sources, not live versions
of their contents. V2 has no edit/remove/retire operation for definitions. A changed
identity needs a newly reviewed source ID. Equal identities may occur for separate
clones/directions; equal upstream names or URLs do not establish identity or reuse.
A definition's SHA-256 is computed from canonical JSON of exactly its five fields,
sorted keys, `ensure_ascii=true`, separators `,` and `:`, UTF-8, with one final LF.
This is `definition_sha256`; it is not a hash of a TOML text fragment.

Each `associations` entry has exactly `scope` (Scope inline table), `source` (ID of
an existing definition), and `role` (`working` or `reference`). The pair
`(scope, source)` is unique. Each scope has at most one working association. Every
project scope names an existing healthy child or the single staged child in the
same publication. Every definition has a workspace association, initially reference
or working. Association absence removes no source from the local filesystem. Project association implies availability in that workspace, not
ownership by the child. All IDs and references are case-sensitive.

Role is selection, not filesystem authorization. Zero working sources is valid,
including a scope with only references. With associated sources but no working
selection, source-backed open/task submission refuses and names the selection
command; it does not choose the sole reference. With no associations at all, native
open retains the existing records-root cwd behavior. Multiple references are fine;
multiple working entries are invalid, not an invitation to pick the first.

Mode A/B initially selects SOURCE as workspace working; B selects the same source
for its new child. `--work-at TARGET` instead associates SOURCE as reference and
TARGET as working in both relevant new scopes. Both directories must already exist.
In C, the child gets the requested working/reference selection, but the workspace's
existing working selection is unchanged. A newly registered definition gets a
workspace **reference** association in C; reuse does not change its workspace role.
The researcher can separately propose a workspace working-source change.

Canonical writes sort definitions by ID and associations by `(kind, project-or-empty,
source)`. A C publication may reserialize the catalog, but must preserve every
pre-existing definition and association semantically, including every old role.
All old child files and unrelated charter/overview bytes remain byte-identical.

### Identities, snapshots and local binding

Retain the existing identity algorithms for old and new definitions:

- `git-roots-v1`: the current inspector's ordered root-commit list reachable from
  HEAD, lowercase object IDs separated by LF, with leading/trailing whitespace
  removed, encoded UTF-8 and hashed. Preserve the existing output order for v1
  identity comparisons; do not replace it with a new sorted algorithm. No commits
  is an error. Upstream name/URL, branch and HEAD are not logical identities.
- `directory-anchors-v1`: SHA-256 of the existing inspector's JSON encoding of
  lexicographically sorted `[relative_path, sha256]` textual anchors, ASCII escapes,
  default JSON separators, no final LF. Empty anchors are valid but weak; preview
  must state that limit. In-place edits do not change the registered identity.

These are data contracts; only L3 obtains the observations. No Git subprocess
belongs in core/protocol code. Rewritten unrelated Git ancestry can make a logical
identity no longer match; never silently replace it. A local folder's device/inode
is checkout identity, separate from logical identity and a content/version snapshot.

`tools/sources.local.toml` remains **version 1**, with exactly `schema_version = 1`
and `bindings` table. Each source-ID table has exactly `path` (nonempty absolute
string) and `filesystem` (nonempty string, as accepted by the v1 reader). New
bindings write `DEVICE:INODE`, decimal integers separated by `:`; preserve older
opaque filesystem strings on read and report them unavailable if they cannot
validate against the actual checkout.
Only IDs in the active catalog may be newly bound. Missing bindings are valid
portable state and must be displayed as unavailable, not reconstructed from history.
Unreferenced old local entries are reported; readers do not prune them.

All source/workspace paths must be distinct and non-overlapping in either ancestor
direction. Reject symlinks in any component and `..` before normalization. Reject
a Git subdirectory instead of its repository root. Newly established or rebound distinct source IDs may
not alias the same canonical path or device/inode, nor nest inside one another.
An equal checkout must reuse the existing ID. Preserve historical v1 local alias
entries on read; report their conflicts and refuse a new source-backed writer rather
than silently merge IDs or rewrite mappings during catalog conversion. Separate non-overlapping clones with
the same logical identity may deliberately get separate IDs. Git worktrees sharing
administrative storage are distinct checkouts only if their root paths and device/
inode differ; the common repository does not itself grant concurrent write safety.

Reuse during C requires equal kind/method/logical identity **and** an existing local
binding at the exact requested path and filesystem identity. For directory sources,
in-place content changes are permitted after checking the stored checkout identity;
the new inventory is a version observation, not a redefinition of identity. It
retains the registered identity field and records changed content via file hashes
and the snapshot digest; directory anchors are recomputed as identity only during
registration/rebind, never during ordinary in-place reuse. If a
catalog ID has no binding, or its binding is stale, an explicit `source bind` must
succeed first. The onboarding packet may not silently rebind it. If several logical
IDs are possible from identity alone, require `--source-id ID` for checked reuse,
or `--register-source ID` for a deliberately distinct checkout. A conflicting path
already owned by another ID always refuses; a flag cannot bypass it.

`source bind ID PATH` is an explicit local operation with before/after preview. It
requires logical identity match, validates overlap and no live writer at old/new
checkout, and replaces only the named local entry after terminal confirmation
(or explicit `--confirm` for noninteractive use). Directory rebind must reproduce
its initial anchor identity; changed content in a moved directory cannot be silently
blessed. Restore the original anchors or register a new source after review. Rebind
never moves files, changes scope selections or redirects an existing native session.

### Directory recovery without re-anchoring

Legitimate directory edits can make the original anchors impossible to reproduce
at a moved/replaced location. WO2 adds no re-anchor, identity-edit or collision
bypass operation. Preserve the original definition, binding and archived pins as
historical provenance; use a reviewed new source and explicit selection instead:

1. Identify the old source ID and archived snapshot, and inspect the intended new
   location read-only. If it still occupies the exact original bound path and
   device/inode, ordinary in-place use under the old ID remains valid; no rebind
   is needed just because its text changed. If rebind is needed and the original
   anchors differ, `source bind OLD_ID PATH` must refuse.
2. Choose a new ID and a genuinely separate, non-overlapping location whose path
   **and** device/inode do not collide with any saved local binding. An edited
   directory already moved/recreated at such a location can be used directly.
   Propose `toulmin source add PATH --workspace --register-source NEW_ID
   --rationale TEXT --root ROOT`, omitting `--working`. The rationale must link
   the old ID/snapshot and explain the legitimate edits; the new registration
   records its current anchors and inventory, not a rewritten old identity.
3. Review and apply that source-change packet in `toulmin decide --workspace
   --root ROOT`. It adds the new definition, local binding and workspace reference
   association; the old working selection and all old provenance stay unchanged.
4. Propose `toulmin source working --workspace NEW_ID --rationale TEXT --root ROOT`,
   then separately review/apply it in decide. This demotes only the workspace's
   previous working association to reference. For a child that also needs the new
   source, separately review its source-add/reuse association and its existing
   `source working NAME NEW_ID RATIONALE` proposal; no old child changes implicitly.
5. Inspect stale native bindings and use an explicit same-scope new/replacement
   session if opening at the new source is wanted. Selection never redirects a
   live session, widens permissions or changes old source snapshots.

**Collision boundary:** registration under a new ID at the same saved path or
filesystem identity still refuses, even when the old path is now missing or its
anchors changed. A move retaining the old device/inode is not automatically a new
checkout for this purpose. `--register-source` cannot bypass that guard. In that
case the researcher must either restore the original anchors and explicitly bind
the old ID, or independently prepare a distinct non-overlapping directory with a
different filesystem identity before step 2. Toulmin does not create/copy that
directory, clear the old binding, or infer a new identity. No source/file operation
is performed by this WO2 specification.

### Machine-local files

Ignore `tools/*.local.toml`, `.aoe/`, publication prepare/pending/completed paths and
`projects/.creating-*/` under existing ignore policy. Pending local image files use
`tools/wo-<packet-token>-before.local.toml` and
`tools/wo-<packet-token>-after.local.toml`; tracked packet metadata includes their
digests and root-relative names, never contents. Operational native/task archives
containing absolute paths are machine-local as specified below. No project-local
permission configuration filename or key is introduced by WO2.

### Source version pin

A reusable `SourcePin` has exactly these fields (JSON/restricted YAML data):

| Field | Type / meaning |
| --- | --- |
| `source` | Registered ID |
| `catalog_sha256` | Exact active catalog bytes used at preview |
| `definition_sha256` | Canonical definition digest |
| `identity` | Registered logical identity |
| `snapshot` | Workspace-relative inventory JSON path |
| `snapshot_sha256` | Exact inventory bytes |
| `head` | Full Git commit object ID (40 or 64 lowercase hex), or null for directory |

Definition revision and catalog schema are covered by those hashes. `head` pins a
version, not a checkout; local operations also pin path and filesystem identity.
Different later HEAD/dirty state does not alter a historical overview's pin. Fresh
submission must revalidate its own baseline and checkout. Snapshots never imply a
complete source tree, reproducible dirty state or permission to execute anything.

## Workspace understanding

### Homes and authority

| Home | Exact role |
| --- | --- |
| `WORKSPACE.md` | Existing v1 confirmed charter; **40 physical lines maximum including header and blanks** |
| `overview.md` | New workspace structural overview with v1 header below, only after reviewed apply |
| `runs/notebook.md` | Unconfirmed workspace working log, never a formal object or confirmed overview |
| `runs/<stamp>-onboard-<token>/inventory/<ID>.json` | Immutable bounded source observations archived with a proposal |
| `runs/<stamp>-understanding-<token>/` | Later overview/source-observation proposal with immutable evidence of what was reviewed |
| `projects/NAME/PROJECT.md`, `brief.md`, `overview.md`, `runs/notebook.md` | Existing project-specific homes; never repurposed for whole-repository understanding |

Charter body/fields/operations remain exactly [workspace formats §4](workspace-formats.md#4-workspacemd).
On A/B, an optional reviewed charter change can accompany intake; it increments
`charter_revision` and names the enclosing receipt exactly as a workspace change.
Without it, initial charter revision 0 and absent direction remain valid. On C,
charter changes are disallowed in the onboarding packet; propose them separately.
Overview does not duplicate the short charter, maintain a manual project index or
claim scientific support. Source definitions and files remain the source of truth.

`overview.md` header has exactly:

| Field | Type |
| --- | --- |
| `schema_version` | Integer 1 |
| `kind` | `workspace-overview` |
| `scope` | Workspace Scope only |
| `revision` | Integer >= 1, increment by exactly one from prior overview |
| `receipt` | Enclosing applied receipt path |
| `source` | Operational Author mapping defined below |
| `recorded_at` | UTC timestamp of proposal preparation, not confirmation time |
| `coverage` | Nonempty string describing inspected material and truncation |
| `limits` | Nonempty list of strings naming uncertainty and exclusions |
| `sources` | Nonempty array of SourcePin values |
| `supersedes` | Null for first overview; otherwise prior receipt path |

Operational `Author` is exactly `{kind: human, actor: NONEMPTY_TEXT}` or
`{kind: model, model: TEXT_OR_NULL, session_id: TEXT_OR_NULL}`. This is new
workspace provenance data, not a change to formal object `source` or the existing
workspace-change packet-source schema. Unknown author model/session stays null.

Body requires exactly level-two `Structure`, `Entry points`, `Current behavior`,
`Checks`, and `Known gaps`, in that order, all nonempty. Other level-two headings
are invalid; subordinate headings are allowed. Code references in prose use source
ID plus relative path and observed revision; local absolute paths are excluded.
Overview max 1,000,000 bytes. Its hash and exact before/after images are sealed;
its receipt is published in the same journal. No header status is necessary:
only a valid matching applied receipt makes it confirmed. A manually placed file
with no valid receipt is reported as unconfirmed/damaged and is not resident truth.

A's `--overview FILE` (or `--workspace-overview FILE`) and B's
`--workspace-overview FILE` supply the workspace **body**; the preparer attaches source pins,
coverage, limits and provenance from inspection/input. If absent, prepare an
explicit provisional body describing the bounded inventory and unknowns. Either
way the full generated overview is shown for confirmation. An agent's structural
analysis stays provisional until that apply. A/B confirmation must cover overview
and any optional charter change; it does not certify historical findings.

C never writes/replaces root `overview.md`. It archives its inventory and a
provisional workspace-level understanding note in packet notes.md (the notebook
format below, one or more entries with explicit author/coverage/limits), plus optional child
`overview.md` if explicitly requested through `--project-overview FILE`. The new
child's creation provenance links the packet's snapshots. A separate
`overview --workspace` proposal can later incorporate the note into shared
confirmed understanding. This keeps the accepted C preservation boundary exact.

### Notebook and observations

`runs/notebook.md` is ordinary Markdown without YAML front matter. It begins with
`# Workspace notebook` and a sentence stating that entries are unconfirmed. Append
entries using this fixed subsection shape; do not rewrite old observations:

```markdown
## 2026-11-18T10:00:00Z — Repository inventory
- Source: source-main; snapshot: runs/20261118T100000Z-onboard-0123456789abcdef0123456789abcdef/inventory/source-main.json
- Author: model; model: unknown; native session: unknown
- Coverage: selected textual files; generated files and credentials excluded
- Limits: bounded inspection; no scripts or tests executed

### Observation
The service has two entry points. This remains provisional.

### Next measurement
Read the request path and identify a minimal latency measurement.
```

Timestamp/title, the four metadata lines and the two nonempty subheadings are
required for new generated entries; hand-written historical notes remain readable
as opaque Markdown and cannot satisfy confirmed-context requirements. Corrections
are new timestamped entries referring to the original entry. Root notes must qualify
formal references, e.g. `[[latency/C-001]]`; workspace notes create no object IDs.
Notebook append is serialized by the workspace writer lock. It cannot block or
mutate a child notebook; project notes stay in that child's scope.

New inventory JSON version 2 has exactly `schema_version: 2`, `kind` (`git` or
`directory`), `identity`, `observed_at`, `head` (commit or null), `status` (bounded
Git status string or null), `files`, `truncated` (boolean), `read_bytes` (integer
>= 0), `limits`, `coverage` (nonempty string), `exclusions` (string list).
`limits` is exactly `{files: 400, bytes: 512000, file_bytes: 32000, candidates: 3200}`.
`files` is an array, unique by portable source-relative `path`, with exactly `path`
and `bytes` (integer >= 0), and either both `sha256` and `text` strings or neither.
Hashes cover observed raw bytes; lossy UTF-8 display is identified in `exclusions`.
A skipped/binary/oversize item may have only path/size; do not invent its hash.
No absolute path, credential value or source directory device/inode goes here.

Keep existing bounded read-only discovery exclusions: source symlinks, nonregular
files, credential/secret filename patterns, ignored material and generated/dependency
directories. Bound traversal, output and time independently; an inaccessible or
truncated scan reports its limits. Conventional filename filters are not a secret
scanner. Do not run hooks, scripts, package discovery or a model as part of intake.
Archived v1 inventories keep their old fields and are read as historical snapshots.
L3 Git discovery disables hooks, fsmonitor, optional writes and lazy fetch; it must
not execute repository-provided helpers or contact a remote during inspection.
The single-image/snapshot 1,000,000-byte limit also applies here: refuse an oversized
escaped inventory instead of truncating it after hashing.

### Update and confirmation rules

A fresh inventory/entry never edits a confirmed overview. Later understanding
updates freeze new pins, coverage, limits and full before/after images in an
`understanding-update` packet. Revision/receipt advance only on researcher apply;
rejection leaves overview/charter unchanged. No live synchronization or scheduled
refresh occurs. A changed source is shown as newer than its confirmed snapshot;
that is staleness of understanding, not invalidation of historical provenance.
Stale targets, missing snapshot bytes or altered receipts cause refusal, not
regeneration. Project overviews keep their existing separate update protocol.

## CLI

**All additions in this section are future WO3–WO5 command forms.** Existing forms
explicitly called compatible below remain supported. Do not put these additions
into current usage documentation before implementation.

### Intake and later derivation

```sh
# A: new workspace, deliberately no child
 toulmin onboard /code/service --root /records/service-research --init
# B: new workspace and exactly one requested child
 toulmin onboard /code/service --root /records/service-research --init \
   --project latency --project-input /drafts/latency.md
# C: explicitly chosen existing workspace and new child; checked source reuse
 toulmin onboard /code/service --root /records/existing --project latency \
   --project-input /drafts/latency.md --source-id source-main
# C: deliberately register a distinct checkout, never just merge by upstream
 toulmin onboard /code/fork --root /records/existing --project isolation \
   --project-input /drafts/isolation.md --register-source source-fork
# Later derivation: existing registered sources, no repeated intake or history move
 toulmin project propose throughput --root /records/existing \
   --input /drafts/throughput.md --source source-main --working-source source-main
 toulmin decide --workspace --root /records/existing
```

The initial leading space in shell examples is typography, not part of an argument.
Onboard `SOURCE` is required. `--root ROOT` is required for onboarding, including
C: no registry/cwd/native-history fallback selects its target. `--init` chooses a
new workspace (A/B) and permits only missing/empty roots, or `.git` alone; an already
initialized workspace is refused with instruction to omit `--init` for C. No
project and no `--init` on an existing workspace is a usage error: later workspace
sources use `source add --workspace`, not a fourth intake mode. Empty initialized
workspaces with zero children are valid C targets.

`--project NAME` is optional only with `--init`. It always means a **new** child,
never continue an old one. Duplicate name refuses even if the old child is corrupt,
empty or incomplete. `--project-input FILE` is the unchanged project-creation v1
input, whose `project` must match NAME. That input's included/excluded scope and
initial Brief `Minimal validation experiment` supply explicit acceptance framing;
no invented gate is required. Without `--project-input`, preserve existing explicit
child onboarding by generating its current provisional v1 input, then show every
question/scope/acceptance gap in preview for explicit review. Omitting the child
argument never takes this compatibility path. `--project-input` or
`--project-overview` without `--project` is exit 2.

`--workspace-overview FILE` is the workspace understanding body, accepted only A/B.
`--charter-input FILE` is an existing workspace-change input limited to charter
fields, accepted only A/B. Old `onboard --project ... --overview FILE` used a child
overview: preserve that spelling's old meaning when a project is specified, and
use new **`--workspace-overview FILE`** for B's workspace body. For A,
`--overview` and `--workspace-overview` are aliases (mutually exclusive). For C,
`--overview` remains a child-overview alias, and `--workspace-overview` refuses.
`--project-overview` and child-meaning `--overview` are mutually exclusive.
This deliberate alias rule preserves explicit-child commands without silently
reassigning their supplied text to workspace scope.

`--work-at PATH` keeps its current meaning: SOURCE becomes reference, PATH is the
working source; neither is created/copied. `--source-id ID` selects checked reuse
of SOURCE; `--register-source ID` requests new registration; these flags conflict.
For a second path `--work-at`, use corresponding `--working-source-id ID` or
`--register-working-source ID`; no positional guess. Without flags, reuse only an
exact checked checkout; otherwise generate one new ID. Missing/stale bindings or
identity-only matches produce explicit guidance, not an inferred rebind.
All flags select proposal contents only; none apply or launch anything.

`project propose NAME --input FILE [--source ID ...] [--working-source ID]`
adds reviewed v2 source associations to the unchanged child-creation input/packet.
Sources must already be registered and workspace-associated. Working ID must be
among repeated `--source` values. No working flag means all references, even with
one source; no flags means a legacy unlinked child. This command never inherits the
workspace working source. It links the current overview by digest/provenance pin
on request in the input; it never relocates workspace notes or copies code.

### Scope and operation forms

| Intent | Frozen form / behavior |
| --- | --- |
| Workspace native conversation | `toulmin open --workspace --root ROOT` |
| Explicit project conversation | `toulmin open NAME --root ROOT` (existing form) |
| Offline state | `toulmin status --workspace --root ROOT` or `toulmin status NAME --root ROOT` |
| Map | `toulmin map --workspace --root ROOT` or existing explicit project form |
| Workspace understanding draft | `toulmin draft overview --workspace --root ROOT` → `runs/drafts/overview-<stamp>-<token>.md` |
| Project understanding draft | Existing `toulmin draft overview NAME --root ROOT` |
| Workspace understanding proposal | `toulmin overview --workspace --input FILE --source ID ... --rationale TEXT --root ROOT` |
| Project understanding proposal | Existing `toulmin overview NAME --input FILE --rationale TEXT --root ROOT` |
| Register/reference source | `toulmin source add PATH --workspace --rationale TEXT --root ROOT [--working] [--source-id ID | --register-source ID]` |
| Project source add | Existing `toulmin source add PATH --project NAME ...`; also ensures workspace association when using v2 |
| Select workspace working source | `toulmin source working --workspace ID --rationale TEXT --root ROOT` |
| Select project working source | Existing `toulmin source working NAME ID RATIONALE --root ROOT` |
| Inspect sources | `toulmin source list --workspace --root ROOT` or `--project NAME`; no selector lists all definitions and associations |
| Explicit local bind | `toulmin source bind ID PATH --root ROOT [--confirm]` |
| Decide root proposals | `toulmin decide --workspace --root ROOT` |
| Decide child proposals only | `toulmin decide --project NAME --root ROOT` |
| Existing unified queue | `toulmin decide --root ROOT` still lists all scopes, each explicitly labeled; never infers a child |
| Engineering draft | `toulmin draft task --workspace --source ID --root ROOT [--name NAME]` or existing project draft form |
| Task preview/import | `toulmin task preview --workspace FILE --root ROOT`; `toulmin task import --workspace FILE --root ROOT` (import previews; `--confirm --confirmed-by ACTOR` applies) |
| New session after source change | Existing scoped `aoe open ... --new-session` / `aoe bind ... --replace` forms; `--workspace` explicitly selects workspace |

Preserve the existing records-directory convenience: bare `toulmin open` from
`ROOT/projects/NAME/` or below selects that child when the root is discovered from
cwd and neither a project nor explicit `--root`/`--in` is given. Bare `open` at the
workspace root stays workspace, regardless of zero, one or many children. Explicit
`--workspace` always selects workspace and suppresses child-directory inference,
including with root discovery. Explicit `open --root ROOT` or `--in` without a
project also selects workspace, preserving current explicit-root behavior.

At the recorded baseline, bare `status` already selects workspace even inside a
child records directory; it does **not** share bare `open`'s inference. Preserve
that behavior. Bare `map` retains its existing child-record-directory inference
when cwd lies inside the resolved root's child, including with explicit `--root`;
`map --workspace` suppresses it. Draft/overview/task workspace forms without a
project choose workspace. These are command-specific scope rules, not a general
inference from source location, a sole child or native history. Intake without
`--project` still creates no child. Explicit project arguments and low-level
legacy `aoe` forms remain supported. No removal of the existing bare-open
convenience is proposed or awaiting a new business decision in WO2.

Conflicting `--workspace` and project selectors are exit 2. Root resolution for
non-intake commands retains nearest-workbench search and explicit
`--root`/`--in NAME_OR_PATH` precedence where those forms exist; `--root` and `--in`
conflict. A linked source checkout never selects a child through its association.
If discovery finds no root, show a terminal picker only for an interactive `open`;
no sole-known-workspace auto-selection. Noninteractive missing/ambiguous roots
refuse without writing; `--in` name collision requires a full path. Status never
initializes.

Workspace decide includes C/new-child packets because those are workspace
publications, not decisions of a nonexistent child. A later workspace overview proposal requires one or more repeated `--source ID`
arguments naming workspace-associated definitions. It inspects exactly those
sources read-only and freezes their new SourcePins, coverage and limits with the
supplied body; it never silently includes all sources or infers them from a child.
Working-source selection is a
sealed source-change proposal: demote only the previous working association in the
explicit same scope, promote the selected associated ID, show both in preview.
It does not rebind or restart/retarget any session. Source registration alone grants
no writable access. Scientific stage/ruling commands keep project-only semantics.

### Errors, exits and noninteractive behavior

Exit 0 means a successful read, proposal, decision, replay, or noninteractive decide
listing; it never means researcher acceptance of the product. Exit 2 is invocation
ambiguity/invalid arguments. Exit 1 is a domain, state, I/O or operational refusal.
Diagnostics must name resolved root/scope (when known), offending file/path and
one actionable next step, without secret contents. No new retry/repair runs on read.

| Condition | Exit / required effect |
| --- | --- |
| Missing `--root` for intake, absent project in C, conflicting flags, unsafe project/source syntax | 2; no initialization or packet |
| Missing/ambiguous discovery root or registry name | 2; require root/path; noninteractive never picks |
| Missing/empty intake root without `--init`; existing root with `--init`; nonempty unrelated root | 1; no overwrite; `--init` cannot authorize unrelated content |
| Source path missing, source/workspace overlap, two-source overlap, symlink, reused checkout under new ID | 1; no packet or source writes |
| New project name already present, staged collision, duplicate explicit source ID | 1; preserve directory/catalog; new child name required |
| Multiple possible reuse IDs or no selected working source with references present | 2; require explicit ID/selection; never arbitrary choice |
| Two stored working associations, invalid schema/version/unknown field, damaged charter/catalog/receipt | 1; report invalid data, preserve bytes |
| Stale before image, changed inspected source, altered seal/image, substituted checkout | 1; no new publication; archive retained for a new proposal |
| Pending journal or external edit during recovery | 1 except confirmed replay of its exact operation; preserve journal/images |
| Missing local mapping, missing native session, changed cwd/source or permission intent | 1 for source-backed launch; offline state still shows unavailable/stale diagnostics |
| Operational lookup unavailable or launch outcome uncertain | 1; preserve applying intent, reconcile exact identity on retry |

Validate arguments, target root class, source separation and child name collision
before initialization. A/B initializer may create the normal empty records skeleton;
rejection later leaves that skeleton and archived proposal but no source registration,
confirmed overview or child. Failed inspection after init similarly preserves only
that explicit initialization, labeled separately. No all-or-nothing claim is made
about initialization itself. Failure before proposal publication removes only this
operation's uncommitted temporary files; never unrelated files.

Proposal/draft commands may run noninteractively and never apply. `decide` without
TTY lists the selected pending items and exits 0 with no decisions, preserving
current behavior. No `decide --yes`, bulk approve or pipe-driven implicit approval
is introduced. For deterministic fixture/authorized-operator use, new
`toulmin workspace apply PACKET --expect-seal SHA --confirmed-by ACTOR --confirm --root ROOT`
applies exactly one v2 packet; preview without `--confirm` is read-only.
`toulmin workspace reject PACKET --expect-seal SHA --confirmed-by ACTOR --reason TEXT --confirm --root ROOT`
rejects exactly one. These are declared operator approvals, not human usability
acceptance. Omitting actor/seal/reason when required is exit 2. No environment default
or terminal EOF supplies approval. Existing v1 apply/reject command forms remain.

## Proposals and receipts

### Packet layout and exact v2 envelope

New root packets live at `runs/<YYYYMMDDTHHMMSSZ>-<kind>-<32hex>/` where kind is
`onboard`, `understanding`, `source`, `derive`, or `catalog`. Mutable inputs stay in
`runs/drafts/`. New outer packets contain `packet.md` encoded as **JSON**, `seal`
(64-hex SHA-256 of exact packet bytes, followed by LF), `before/N`, `after/N`,
`inventory/ID.json` where applicable, and immutable `notes.md` if needed. Receipt is
`receipt.md` after disposition. No mutable queue index or manual catalog is added.

Keep JSON-in-`packet.md` deliberately: current onboarding/context-change packets
already use that filename for JSON, and existing discovery, receipt references and
journal records use its path. Renaming it would add a path compatibility change
without changing the protocol. Readers dispatch by packet family and declared
version, not by the `.md` suffix: this v2 outer envelope uses a JSON parser; the
unchanged v1 **child creation** `packet.md` uses the restricted YAML/Markdown
parser. Neither reader tries the other syntax as an automatic repair/fallback.

JSON canonicalization for new packet bytes: sorted keys, two-space indent,
`ensure_ascii=true`, one final LF. Every key in the following table is required;
there are no extension keys. Preparing an archive without its final valid seal
never queues an operation; incomplete preparation is reported as such. The numbered
preparation sequence below defines how a child and its ownership are sealed.

| Key | Type / constraint |
| --- | --- |
| `schema_version` | Integer 2 |
| `kind` | `workspace-onboarding` |
| `operation` | `onboarding`, `understanding-update`, `source-change`, `child-derive`, or `catalog-upgrade` |
| `scope` | Workspace Scope (all these publications are root operations) |
| `created` | UTC time |
| `origin` | Operational Author mapping as above |
| `mode` | `A`, `B`, `C` for onboarding; null for other operations |
| `project` | Null for A/non-child operations; new name for B/C/child-derive |
| `creation` | Null or `{path: ROOT_REL_PACKET_DIR, seal: SHA256}` referencing unchanged v1 creation packet |
| `catalog_version` | Integer 2 for these packets |
| `inputs` | Array of `{path: ROOT_REL_PATH, sha256: SHA256}`; exact raw input bytes remain archived or present |
| `preconditions` | Array of `{path: ROOT_REL_PATH, sha256: SHA256_OR_NULL}` covering read targets; no duplicate paths |
| `images` | Array of image specs below; no duplicate target paths |
| `inventories` | Array of `{source: ID, path: PACKET_REL_PATH, sha256: SHA256}` |
| `source_actions` | Array of `{source: ID, action: ACTION, definition_sha256: SHA256}` |
| `association_changes` | Array of `{scope: Scope, source: ID, before: ROLE_OR_NULL, after: ROLE}` |
| `notes` | Null or `{path: PACKET_REL_PATH, sha256: SHA256}` |
| `rationale` | Nonempty string displayed verbatim in preview |

`source_actions.action` is exactly `register` or `reuse`. `ROLE` is `working` or
`reference`. A v2 source-change cannot delete a definition or association.

Each image has exactly `path` (workspace-relative target), `before` (digest or
null), `after` (digest), `before_image` (root-relative image path or null), and
`after_image` (root-relative image path). Tracked images are `<packet>/before/N`
and `after/N`; local ones use the ignored paths defined above. An unchanged image
is omitted; a read dependency still appears in `preconditions`. All preconditions and image before bytes must match current targets at first
apply, under lock; after-image files must match their sealed digests. Packet
validation also cross-checks duplicate read/write dependencies for identical before
expectations. Recovery uses the journal's before-or-after rule instead. Paths/digests cover both input
content and generated output; a seal alone is not validation of a valid operation.

Packet structural validation recomputes hashes, parses the after catalog/overview/
child, recomputes semantic association deltas and compares to declared changes.
The explicit `images` list contains non-creation effects and optional child overview;
sealed v1 child targets are inherited through `creation`, not duplicated in images.
At apply, the unchanged v1 creation renderer derives the remaining child scaffold
and creation provenance from those sealed targets plus the confirming actor/time.
Its complete generated bytes are frozen in the journal before any publication.
The operation allow-list below applies to the union of explicit and inherited effects.
No caller may smuggle extra images/targets through JSON. Portable audit readers
can validate a disposed packet/receipt and tracked images without the original
machine-local images: show those effects as locally unavailable with their sealed
hashes. Pending apply and journal recovery require all local images and refuse if
they are missing; do not regenerate them from a different machine's paths. Mode A has null child and
creation, and no project images. B/C have exactly one creation reference matching
the project and the unchanged creation seal, and can create only that child.
An envelope pointing to another envelope or arbitrary existing child refuses.

Allowed targets by operation:

| Operation | Allowed targets / invariants |
| --- | --- |
| A onboarding | `sources.toml`, optional local mapping, `overview.md`, optional reviewed `WORKSPACE.md` charter image |
| B onboarding | A targets plus new child v1 creation files/provenance and optional child overview |
| C onboarding | Catalog/local additions or reuse, new child creation/provenance, optional new child overview; never root overview/charter or old child files |
| understanding-update | Root `overview.md` only; new observations/notes stay in packet; charter updates are separate existing workspace proposals |
| source-change | Catalog associations/new definitions and optional additive local entries; only explicitly selected scope roles may change |
| child-derive | New child files/provenance and catalog associations; unchanged definitions, local mapping, root overview and charter |
| catalog-upgrade | Active catalog only; legacy bytes are a sealed packet artifact as specified in Compatibility; no old scope selections or other data changes |

### Preparation order and authenticated ownership

For B/C/derive, enclosing packet owns child creation. Its input/targets and receipt
retain their existing v1 schemas in
[workspace formats §9](workspace-formats.md#9-child-creation-input--packet--project--receipt).
Prepare in this order under the workspace writer lock, without publishing any
confirmed source, overview or child:

1. Reserve the final outer directory and v1 creation directory names. Archive the
   bounded inventories, notes and external inputs under the outer directory,
   leaving it **unsealed**. Inventory/source references in the child input name
   those immutable archived paths/digests, never the future outer seal.
2. Build the v1 creation input, target images, `packet.md` and its normal v1 seal
   in a private preparation directory. Its final logical creation path is already
   known. The v1 seal covers its own packet/input/target/source hashes under the
   unchanged contract; it does not include the ownership marker or outer digest.
3. Write `onboarding` inside the private creation directory. Its exact UTF-8 bytes
   are the reserved outer root-relative directory name, **without a trailing LF**,
   preserving the existing marker representation. Publish the v1 archive and
   marker together by one directory rename, so a standalone sealed creation is
   never briefly visible without its marker. A crash now leaves an orphan owned
   creation, which queues/direct child commands report and refuse to apply alone.
4. Construct the outer v2 envelope: `creation.path`/`creation.seal` pin the child
   packet. Add the marker's final root-relative path and exact SHA-256 to **both**
   `inputs` and `preconditions`. Complete and hash all other input/image entries.
   Finally write outer `packet.md` and publish its valid outer `seal` last. Only
   this complete outer packet is offered for researcher apply/reject.

A and non-child operations omit steps 2–3 and have null `creation`; they still
archive observations before publishing the final outer seal. Private preparation
uses the existing ignored workspace prepare directories; incomplete preparation
is reported, not auto-applied or repaired by readers.

The **outer seal** authenticates the marker hash in inputs/preconditions and the
child seal in `creation`. At first apply, the marker must match both its pinned
bytes and this outer directory; recovery validates those same sealed dependencies
before any writes. There is no digest cycle: reserved directory-name bytes →
marker hash; inventories → v1 child seal; these independent hashes → outer seal.
Neither the marker nor v1 child packet contains the outer seal.

The generic queue and direct child-create path must also scan sealed outer
ownership references before applying any otherwise standalone v1 creation.
Ownership discovery first verifies the outer envelope's own bytes/seal and reads
its `creation` reference, independently of marker validation. A missing/changed
marker or child-seal mismatch then blocks application; it cannot cause the reader
to skip that outer owner as though no owner existed.
Deleting or redirecting a marker cannot make an already owned child independently
applicable: the sealed outer `creation` reference still owns it. Missing/mismatched
marker, multiple outer owners, or an orphan marker whose outer seal is absent is
an explicit integrity/incomplete-preparation refusal, not a different owner or a
new application route. Completed/rejected outer records retain ownership; a new
attempt requires a fresh child packet. An existing completed independent child
creation cannot be retroactively wrapped in onboarding. These are byte-integrity
checks, not authentication against an actor who rewrites and reseals all records.

### Preview, disposition and receipt

Preview resolves and prints root/scope, mode, source registration/reuse, both local
cwd candidates, every affected role, child name, Goal/Scope/acceptance framing,
overview coverage/limits, optional charter diff, exact target diffs and seal.
Show local paths only from local files on that machine. Show scientific authority,
source write permission and automatic launch as absent effects. Explain any
provisional project framing; do not hide an empty acceptance plan behind a default.

Reuse **unchanged v1 receipt** keys/validation from
[workspace formats §7](workspace-formats.md#7-workspace-changes-input--packet--receipt):
`schema_version: 1`, `kind: workspace-receipt`, `record`, `record_sha256`,
`disposition` (`applied` or `rejected`), `actor`, `at`, `approval_text`, `reason`,
`results` (array of `{path, before_sha256, after_sha256}`). `record` points to
`packet.md`; `record_sha256` equals its seal. Applied receipt requires nonempty
approval text, null reason and all effects; rejection requires nonempty reason,
null approval text and empty results. Confirmation time comes from apply and does
not overwrite preparation provenance. Validate the existing receipt schema rather
than inventing extra scope fields: the referenced sealed packet supplies scope.

B/C/derive produce both v1 creation receipt and outer receipt in the same journal.
The inner receipt results cover business effects (all explicit/inherited target
images); the outer receipt also covers the inner receipt image. Neither includes
its own digest, avoiding a circular hash. Reject has only the outer receipt; the
owned creation remains unoffered and cannot later be independently applied.
For an applied transaction,
creation provenance continues to refer to its existing creation packet/receipt.
A produces only the outer receipt; its results omit its own receipt image. Replay validates the matching receipt and its archived effect hashes, returns
the original actor/time/results and creates nothing. After journal retirement,
subsequent legitimate operations may have changed current targets; replay never
restores an old after image or requires current bytes to equal a historical result. Replaying rejected
packets reports rejection; a different result needs a new proposal/seal. Applied
packets cannot be rejected, rejected packets cannot be applied. Rejection changes
no catalog, local mappings, overview, charter or child. No refusal is called a
rejection unless the researcher actually chose rejection and a receipt exists.

### Preconditions, locks and publication

Seal all touched before bytes, the complete catalog even on reuse, WORKSPACE.md
identity, existing overview when used for derivation, child-name absence and all
creation inputs. Local mapping preconditions cover exact checked entries and
full before-file digest if writing it. Inspect source again before first durable
commit: same path, device/inode, kind and identity; Git HEAD/status and bounded
inventory observations must still match the preview. Compare a repeat scan using
the original observed_at and identical limits/order, so passage of time alone does
not change its bytes. A changing source requires a fresh
proposal. Once a durable journal exists, recovery forwards its already approved
images rather than rescanning a moving source into new output. If local source
changed after commit, finish records, mark unavailable/stale and refuse launch;
do not abandon half-publication or silently update its pin.

Lock acquisition order is fixed for every new writer: canonical checkout locks
(sorted path then filesystem identity), workspace root writer lock, child writer
locks in lexicographic project-name order, and the native-binding lock only if
needed. Locks are POSIX advisory locks in machine-local temporary/state storage,
keyed by canonical path/device/inode, not files written in source repositories.
Only acquire locks actually needed; no code may acquire a checkout lock while
holding the root lock. Source observations for preview are made outside locks and
fully revalidated inside locks at apply. Registration/rebind/selection writers
coordinate with native source launch and task submission via checkout locks.
Object-only writers keep child locks and never call back into root operations
while holding them. Local file access is serialized under the root lock.

Use the existing **journal v1 schema and operation vocabulary** from
[workspace formats §10](workspace-formats.md#10-publication-journal-and-recovery).
Non-child operations use `operation: workspace-change`; B/C/derive use
`operation: project-create` with `staging: projects/.creating-<32hex>`.
The envelope distinguishes the operation; no new journal field is necessary.
`intent.md` pins outer packet path/seal, original actor/time/approval and the
ordered full image set, including both receipts and local images. The commit point
is the fsynced prepare-directory rename to `.workspace-pending/`.

Before commit no confirmed target changes. With a child, stage **all** expected
child files and provenance in the private directory, verify exact bytes, then
rename to `projects/NAME`. Catalog/local/overview/charter effects and both receipts
finish from journal images. During any journal, affected records are incomplete:
all new source-backed open/task/decide writers refuse (except exact recovery);
status reports which effects are pending. An affected child is never usable
before every image and receipt matches and the journal retires. This preserves
logical atomicity despite filesystem writes occurring in sequence. Existing
unrelated child reads remain available; no command treats an incomplete catalog
as healthy. It is not a distributed transaction with Git or a remote service.

Recovery checks **all** target files and staged/published trees before writing:
each file equals its before or after image, or a still-missing staged target.
Unknown child files, extra directories, altered packet, changed actor overrides,
foreign journal or mismatched bytes refuse and preserve everything. No rollback,
automatic edit repair or forced abandon. Rerun the same confirmed operation;
retain its original actor/time. Explicit human restoration of one preserved image
may unblock recovery. A catalog rewrite racing the preview makes that packet
stale; regenerate instead of merging deltas behind the researcher's preview.
Retired `.workspace-completed-*` cleanup follows the current journal contract.

A C application must compare all pre-existing source/association entries and
validate its complete image target allow-list: no old child path may be an image.
Only the reviewed new definitions and associations may differ in the catalog.
Root WORKSPACE.md/overview.md preconditions ensure they have not changed when they
were used as context, and neither is a C image. Zero or many old children makes
no difference to selection. A child directory's existence is a conflict, never
a signal to add sources to that child. Duplicate-source reuse creates no second
definition, no duplicate association and no local-image rewrite if unchanged.

## Native context

### Source-backed scopes and v4 binding

Keep `.aoe/binding.json` for workspace and
`projects/NAME/.aoe/binding.json` for projects. An explicit new/replacement
source-backed workspace-first binding uses **v4**; source-free sessions keep v2,
legacy roots v1, and existing v3 bindings keep v3. No read converts them. The only open-time write permitted for an old binding is
its established same-version operational state/context update after an explicit
open/refresh request; an offline status writes nothing.
V4 allows either Scope and is distinct from project-only v3, so old readers fail
clearly instead of accepting new semantics under an old version.

V4 JSON has exactly these fields:

| Field | Type / rule |
| --- | --- |
| `schema_version` | Integer 4 |
| `scope` | Scope; no redundant `project` key |
| `title` | Nonempty string; existing scoped title and numbered replacement policy |
| `root` | Absolute canonical records-root path |
| `profile`, `agent` | Nonempty strings; adapter choice belongs to L3 |
| `session_id`, `provider_session_id` | String or null; unknown provider ID remains null |
| `context` | Scope's runs archive path or null |
| `token` | 32 lowercase hex or null |
| `fingerprint`, `manifest_sha256` | Digest or null |
| `delivery` | Existing `none`, `prepared`, `sending`, `submitted`, `uncertain`, `acknowledged` |
| `known_ids` | Array of distinct nonempty native session-ID strings |
| `message` | String, possibly empty |
| `cwd` | Absolute canonical selected checkout root |
| `source_id`, `source_identity` | Definition ID/logical identity matching selected working association |
| `cwd_identity` | Local `DEVICE:INODE` |
| `catalog_sha256`, `definition_sha256` | Pin catalog and selected definition at context preparation |

These source/identity fields are required/non-null. `delivery: none` requires
context/token/fingerprint/manifest digest null. Later delivery states require those
four values and a session ID. A binding's scope/location/root/cwd must agree with
the native session. One `(profile, session_id)` belongs to at most one scope across
all binding versions. Context state is operational, not evidence of complete
native conversation capture or scientific approval.

Manifest v4 has exactly `schema_version: 4`, `scope`, `token`, `fingerprint`,
`profile`, `session_id`, `provider_session_id`, `files` (archive-relative path →
SHA-256), and `working_source`. `working_source` has exactly `cwd`, `source_id`,
`identity`, `cwd_identity`, `catalog_sha256`, `definition_sha256`, all matching
binding. `files` covers all snapshots, context.md, guide.md, state.md and optional
notebook excerpt. Ack receipt v4 has exactly `schema_version: 4`, `scope`, `token`,
`fingerprint`, `session_id`, `provider_session_id`, `received_at` (UTC time),
`manifest_sha256`; fields must agree with binding/manifest. Wrong scope/token,
changed bytes or a stale pin cannot acknowledge delivery. Preparation/submission
alone is not receipt. Existing v1/v2/v3 manifest/ack shapes are unchanged.

Absolute native cwd/checkout metadata belongs in ignored `.aoe/` operational files
and **ignored** `.aoe/contexts/<token>/local.json`, not tracked overview/source
snapshots. For v4, manifest and ack live with the ignored local context archive;
`context` names `<scope-runs>/<stamp>-aoe-context-<token>`, whose tracked snapshots
exclude absolute local fields. Binding stores `manifest_sha256` for
`.aoe/contexts/<token>/manifest.json`; scope-specific .aoe is used for child scopes.
The manifest's `files` paths resolve relative to the tracked context archive;
local manifest/receipt cannot be mistaken for a portable historical record.
Existing v1/v2/v3 tracked archives stay exactly where they are; no retroactive move.
No API credential, native permission secret or provider log is copied into context.

### Resident inputs and freshness

Workspace resident inputs: root AGENTS.md, WORKSPACE.md, applied overview.md if
valid, current catalog, latest applied workspace handoff and a labeled bounded
notebook excerpt (last 20,000 UTF-8 bytes aligned to complete lines). Include a
compact `guide.md` explaining workspace/source/child boundaries, source repository
instructions, the explicit decision command and absence of project gates. Full
inventory archives/notes are referenced with pins, read on demand, not pasted as
complete knowledge. Project context keeps its existing resident charter/Brief/
overview/handoff/guide, plus workspace charter and the confirmed shared overview
only when pinned by its creation/understanding context. No sibling histories or
workspace notebook is injected into a child automatically.

Fingerprint adds exact relevant catalog/overview/notebook bytes, selection,
source/cwd identity, the permission mechanism's validated launch-intent fingerprint,
and L3 observed HEAD/dirty-status summary to existing scope inputs. Unknown/unavailable observations add explicit diagnostics; never reuse a
clean fingerprint after a failed scan. New source registration may stale an old
catalog pin without changing its cwd; refresh archives new context at the **same**
pinned checkout if selection/identity still agree. Source content change prompts
freshness advice, not an automatic overview rewrite or gate transition.

Selection change, source replacement, moved records root, missing session or
changed cwd cannot redirect the live binding. Show old and requested identities;
require explicit same-scope `open --new-session` or `bind --replace` and preserve
old context/binding history. No fallback to another checkout, another scope,
records cwd or sole child. Recovery rebuilds from files and latest applied handoff;
it never claims partial native logs are a complete transcript. Creating a child
never reuses or retargets its workspace session.

### Writer coordination and permission integration

Before starting/resuming a writer, L3 checks live AoE sessions across profiles and
workspace/project scopes by canonical cwd and checkout device/inode. A workspace
writer and project writer selecting the same checkout conflict even with different
logical source IDs or profile names. Distinct branch names do not waive a shared
checkout conflict. Hold the checkout lock through final check and launch/binding
publication. Read-only observations do not reserve a writer. If the adapter cannot
prove a conflicting session read-only, treat it as a possible writer and refuse.
Unknown cross-profile session state fails closed for new launch; offline reads
remain available. Do not kill, capture, send to or change the other session.

Chief workers use Chief-owned distinct worktrees; they do not acquire permission
to write the source checkout. Do not run a task on a live native writer's same
checkout. Coordination is not filesystem isolation and cannot stop arbitrary
external writers; state that limit in diagnostics. Locks are local, not a
cross-machine scheduler.

**Permission interface dependency:** WO4 must consume the explicit native
trust/permission mechanism delivered by `o3-general-codex-permission-co` after
integration. WO2 freezes only its caller input/output boundary: input is resolved
Scope, records root, selected source ID/definition digest, cwd/checkout identity,
and explicit researcher permission intent; output is a validated launch intent,
its stable fingerprint and an effective access summary, or a refusal. Persist/hash
its returned intent through that mechanism's own records. Any permission change
makes context stale and requires that mechanism's explicit reconfirmation/replacement
path. It may narrow access; source registration never widens it. No project-local
policy key, permission enum or provider flag is frozen here. Runtime integration
must align its storage/version details and workspace-scope support after that
worker delivers; if it lacks workspace scope, refuse source-backed workspace launch
until a reviewed extension exists. This dependency does not affect catalog,
understanding, scope or packet validity. Native folder trust, access approval,
onboarding confirmation, Chief kickoff and scientific acceptance remain separate
authorizations; none implies the others.

## Engineering tasks

### Scoped draft and confirmation

Workspace tasks live directly at `runs/proposals/task-<stamp>[-NAME].md`; project
tasks keep `projects/NAME/runs/proposals/`. New task request v2 uses the existing
v1 task fields plus explicit scope and source pin. Its exact required keys are
`schema_version: 2`, `kind: task-request`, `scope` (Scope), `source` (registered
Git source ID), `source_pin` (SourcePin), `baseline` (nonempty revision string,
not beginning `-`), `tool` (nonempty provenance string), `checks` (nonempty string
list), `protected` (portable repository-relative path list), `budget` (exactly
`rounds`: positive integer, `hours`: positive finite number), `test_first`
(boolean), `trust` (boolean). Optional keys: `task_id` (existing safe 1–128
character task ID) and `command` (existing bare-program-on-PATH name). Body requires
exactly nonempty `## Goal` and `## Scope` sections, no unfilled placeholders.

V2 forbids absolute `repo`; source mapping supplies it only at local export.
Source must be associated with this scope; it may be an explicitly named reference
source for a Chief worktree, but is never inferred. This choice does not change
native working-source selection. Project v1 requests with source/repo remain valid
under their old rules; workspace requests cannot pretend to be v1 project tasks.
The task draft preparer archives a bounded source inventory and constructs the
SourcePin using current active catalog bytes; no ad hoc pin is inferred from a
native conversation. Source pin freezes inspected context; at submission resolve `baseline` to a full
commit and show any difference from pin.head. A difference requires a new draft/pin,
not silent rebasing. Reject non-Git, dirty repository, missing/replaced mapping,
missing baseline, wrong scope or altered source identity before submission.

Workspace task ID default is `workspace-<proposal-stem>`; existing project default
is `<project>-<proposal-stem>`. Over 128 characters requires explicit task_id.
Chief task IDs are global to the configured Chief home: collisions refuse; no
automatic renamed duplicate. The researcher reviews Goal, Scope, baseline, source
pin, checks, protected paths, tool/command, budget and trust separately from any
scientific gate. `decide --workspace` offers workspace tasks; no Claim/Spec/status
preconditions or automatic research objects appear.

### Frozen export and recovery

Use the existing Chief adapter boundary: freeze `contract.json` with exactly
`repo` (local absolute resolved path), `name`, `goal`, `base_branch` (full commit),
`checks`, `protected`, `budget`, `tool`, `test_first`, optional `command`.
The goal includes Goal/Scope, frozen baseline, source ID/pins and instruction not
to change frozen checks/protected paths. No new scheduler fields. `trust` is the
existing explicit launcher option, not scientific permission; default false.
Supported tools are validated by the adapter, not an L1/L2 vendor enum.

Store task submission at `<scope-runs>/<stamp>-task-<proposal-sha-prefix12>/`.
Portable `submission.json` version 2 has exactly `schema_version: 2`,
`kind: task-submission`, `scope`, `proposal`, `proposal_sha256`, `source_pin`,
`baseline` (full commit), `task_id`, `contract_sha256` and `local_intent_sha256`.
The contract and local request/host/Chief-home/command fields stay under ignored
`tools/task-<full-proposal-sha>.local.toml`: keys `schema_version = 1`,
`host`, `chief_home`, `chief_command` (nonempty string array), `repo`,
`filesystem`, `contract_json` (string containing canonical Chief JSON).
This preserves exact frozen export without putting machine paths in tracked data.
`local_intent_sha256` hashes that file's complete bytes; contract_sha256 hashes the
canonical JSON string bytes (sorted keys, two-space indent, ASCII escapes, final LF).
Export a temporary contract file for Chief only from these verified frozen bytes.

Use the existing `.outcome.md` v1 decision shape (kind `proposal-outcome`) beside
the request: proposal/digest, disposition `applying`/`applied`/`failed`/`rejected`,
actor/time/approval/reason/result. Scope comes from the request; wrong-scope paths
refuse. Persist applying outcome and frozen export **before** `chief new`.
Under checkout → root → child lock order (child only for project), revalidate
preview/pin/local intent. External execution occurs in L3 only. Recovery queries
exact Chief task ID and compares repo, base and frozen contract before any retry.
An uncertain launcher response stays applying; an existing matching task is
reconciled without a second `new`. Different host/config/contract, missing applied
task or changed request refuses; never silently submit to another Chief home.
No terminal trust choice is synthesized. Existing manual-kickoff guidance remains;
submission does not schedule/guarantee a worker start.

### Ordinary Run/result import

Project result imports keep the ordinary formal v1 `R-NNN` object schema/path.
Existing project v1 requests/imports keep the existing `TaskImport` v1 artifact
contract. New project v2 requests use the scoped v2 import below and a portable
submission record, not a new research gate. Workspace has no formal object
namespace: import a **Run-shaped operational record** at
`runs/<stamp>-task-<proposal-sha-prefix12>-result/run.md`, never `runs/R-NNN.md`,
a sentinel project's Run or an eighth research object. This deliberate distinction
preserves [workspace formats §1](workspace-formats.md#1-common-rules).

Workspace `run.md` exact YAML header: `schema_version: 1`,
`kind: engineering-run`, `scope: {kind: workspace}`, `created` (import UTC time),
`status` (`completed` for done, `failed` for abandoned), `source`
(`{kind: human, actor: TEXT}` for confirming operator), `role: implementer`,
`model` (reported model string or null), `session_id` (reported native ID or null),
`duration_seconds` (nonnegative number or null), `input_files` (request and
submission paths), `output` (result archive path). Body requires `## Summary`,
and `## Failure` only when failed. Tool/command attribution is archived separately;
do not relabel tool name as a known model. It is an ordinary execution report,
not accepted scientific Evidence, verified code or a supported Claim.

Scoped `import.json` version 2 has exactly existing task-import v1 keys
`schema_version`, `kind`, `task_id`, `request`, `request_sha256`, `actor`, `at`,
`state`, `head`, `tool`, `command`, `session_id`, `files`, `disposition`, `run`,
plus `scope`, `source_pin`, `submission_sha256`. Version is 2; kind `task-import`;
state `done` or `abandoned`; disposition `applying` or `applied`; `run` null until
publication, then root-relative operational run.md path for workspace scope or
formal Run object ID for project scope. Existing project v1 `run` remains an object
ID and its artifact resolution stays unchanged. Required `files` artifacts: `task.md`, `commits.txt`, `diffstat.txt`,
`review.md`, `contract.json`; optional `progress.md`, `checks.json`, `events.jsonl`.
Each value is exact SHA-256 and changed/missing artifacts refuse. Machine-path-bearing
raw artifacts, especially contract.json, remain ignored at
`.aoe/task-results/<full-proposal-sha>/`; `files` resolves against that directory.
The portable run/import record retains digests and the local artifact availability
notice; missing artifacts on another machine make replay unavailable, never erase
the historical result. Apply the same raw-artifact privacy rule to new v2 project
submissions; do not move/rewrite existing v1 archives.

Import previews exact scope/task/request/pin/result HEAD/artifacts; explicit
researcher confirmation freezes them. Under root lock (then child lock for a
project), write archive/import applying, publish exact workspace run.md or the
ordinary project Run, then mark applied. Crash replay validates all
bytes and reuses that same path, never allocates a second Run. Wrong request,
source, contract, task ID or artifact refuses. No auto-merge, push, check execution
or scientific status change occurs during import. Chief's worker/self-test result
is not independent acceptance; optional future formal promotion still requires an
explicit project and the existing research protocols.

## Compatibility

### Old/new matrix

| Record | Future reader | Future writer / explicit boundary |
| --- | --- | --- |
| No catalog | Empty source set; existing unlinked behavior | New intake/source operation may create v2 |
| `sources.toml` v1 | Validate exact existing shape; group equal ID/kind/identity as in-memory definitions and retain each project/role; **do not invent workspace associations or working choice** | Existing v1 project commands/packets remain v1 until explicit conversion; v2 workspace writes require opt-in transaction below |
| `sources.toml` v2 | Strict definitions/associations above; unsupported versions refuse | Reviewed v2 operations only; old software refuses v2 rather than partially loading |
| Local mapping v1 | Existing exact path/filesystem schema | Same schema; new source entries and explicit bind only; no version bump |
| Native binding v1 | Existing project/root/title/context semantics on legacy roots | Same-version refresh/ack; explicit replacement chooses appropriate newer format |
| Native binding v2 | Existing source-free workspace/project semantics | Same-version refresh/ack at original records cwd; selection change requires explicit replacement |
| Native binding v3 | Existing **project-only** cwd/source/checkout pins | Same-version refresh/ack if cwd/identity/scope unchanged, including v2 catalog compatibility view; never reinterpret as workspace v3 |
| Native binding v4 | Explicit source-backed workspace or project scope and extra pins | New/replacement only; no read-time promotion from v1/v2/v3 |
| Native manifests/acks v1/v2/v3 | Match their binding version and original archive location | Old context files remain immutable; new v4 archives have the locations above |
| Project `overview.md` | Existing plain Markdown and reviewed context packets | Existing protocol, distinct from workspace overview schema |
| Project creation v1 / onboarding v1 / context-change v1 | Exact original target/receipt/seal semantics | Existing pending packets can finish under v1; enclosing v2 creations remain v1 with ownership marker |
| Workspace/project proposals and receipts | Existing versions unchanged, scope from record/location | Never rewrite history to v2; no read-time recovery |
| Workspace/project handoffs | Existing v1 applied records, charter limits and ID/reference rules | Existing handoff application; no moving workspace history into a child |
| Explicit project commands and bare entry | Existing explicit-child forms remain supported; bare open/map infer only from a child records directory under their current rules; bare status remains workspace | Preserve the current convenience, explicit-root open behavior and explicit --workspace override; no source-cwd/sole-child/history inference or unrelated breaking scope change |
| Task request/import v1 | Existing project-only semantics and formal Run IDs | Continue unchanged for legacy project tasks; new workspace tasks must use scoped v2 |

Readers never initialize, migrate, recover journals, prune mappings, upgrade
bindings or repair malformed files on open/status. Open may create/deliver its
explicitly requested native session/context but cannot rewrite format versions
as a side effect of reading them. Root data errors do not destroy old children;
explicit old project reads remain possible where they do not rely on the damaged
shared data. Source-backed launches fail rather than bypass damaged shared state.
A future reader must retain the original v1 identity algorithm and opaque old
source provenance even if a later algorithm is added.

At the recorded baseline, bare `open` infers the child from its records directory
when using cwd root discovery; bare `status` already shows workspace state there.
`map` has its own existing records-directory inference. WO2 preserves these
command-specific differences and adds an explicit workspace override, keeping the
three intake modes independent of existing entry convenience.
The [bare-entry examples](#bare-entry-compatibility) and W05-entry-compat case
below cover this boundary independently of A/B/C intake.

### Reviewed opt-in catalog conversion

A v1 catalog cannot express project-free source ownership. Introduce future
`toulmin source upgrade --root ROOT` to **propose**, not execute, conversion to v2.
Its sealed `catalog-upgrade` packet is applied only in decide or the exact confirmed
apply form. Never trigger it automatically from onboard/add/open/status. If C or
workspace source work encounters v1, stop with that command; do not merge conversion
into the C packet or revise old pending source operations behind the preview.

Preconditions: valid v1 catalog, no pending journal, no undecided sealed v1
onboarding/source-role/source-add packet referencing it, and preserved child names.
Other unrelated pending project proposals are allowed. The preview enumerates every
unique source definition, each existing project association and the new workspace
**reference** association per definition. It chooses no workspace working source,
changes no old project selection, bindings, source directories, charter or overview.

At proposal time, archive exact before bytes at
`runs/<stamp>-catalog-<token>/legacy/sources.v1.toml` and list that immutable copy in
inputs with its digest. It remains available even after rejection. Under root lock,
publish the after v2 catalog and receipt in the existing workspace-change journal;
the already sealed legacy artifact is a precondition, not an absent-before target. Definitions deduplicate by ID only after
checking kind/identity consistency. Add `definition_revision: 1` and matching
identity_method without changing stored identity. Identical identity under two
IDs remains two definitions. Local mapping v1 remains byte-identical. Preserve
original catalog digest in preconditions and receipt before digest. Forward recovery
is the same before/after-image contract; old source bytes are never overwritten.

Until apply, v1 is the active read/write path. After apply, v2 is active; exact
historical v1 bytes remain readable in the sealed legacy artifact for audit and
old packet validation. This is **not** silent fallback to historical state if v2
is damaged. Old installed software should refuse active v2; to use it unchanged,
retain the pre-conversion workspace checkout or inspect that artifact read-only.
No automatic downgrade/rollback is provided. Choosing conversion therefore means
using a v2-capable Toulmin for future writes; this compatibility consequence must
be in preview. No mandatory real-data migration, migration script or actual
conversion is part of WO2. Existing project-only v1 use can continue indefinitely.

## Examples

These examples describe **future fixtures**, not observations from a real workspace.
Every repeated 64-hex hash, 40-hex commit, device/inode, time, path and token below is
**illustrative, not computed or verified**. A fixture runner must generate real bytes
and recompute every dependent digest/seal before apply; placeholder hashes are
schema-shaped examples only. Invalid examples are syntactically valid TOML/YAML
so a parser can distinguish schema errors from serialization errors.

### Bare-entry compatibility

These future compatibility assertions preserve baseline command-specific selection;
they are not claims that a runtime trial was executed. Let W be a valid records
root and latency one of its children (zero/one/multiple-child variants are covered
in the acceptance matrix). No shell command below initializes or chooses a source.

| Cwd and command | Expected scope |
| --- | --- |
| W; `toulmin open` | Workspace, even with one child |
| W/projects/latency or below; `toulmin open` | Project latency via existing records-directory inference |
| W/projects/latency; `toulmin open --root W` | Workspace, preserving explicit-root open behavior |
| W/projects/latency; `toulmin open --workspace` | Workspace, explicit override |
| W/projects/latency; `toulmin status` | Workspace, as at the baseline; no child inference |
| W/projects/latency; `toulmin map` | Project latency via its existing records-directory rule |
| W/projects/latency; `toulmin map --workspace --root W` | Workspace, explicit override |
| An external linked source checkout; `toulmin open --root W` | Workspace, never the source's sole/last-associated child |

Without a resolvable records root, the external-source case requires explicit
selection as in CLI; source names/native history supply neither root nor project.
Intake with no `--project` still creates zero children; no bare-entry convenience
can supply an omitted intake project.

### A — New workspace only

The A command above, then researcher decide apply, yields zero project directories,
source-main workspace working, a confirmed root overview and its source snapshots.
The valid v2 catalog shape is:

```toml
schema_version = 2

[[definitions]]
id = "source-main"
definition_revision = 1
kind = "git"
identity_method = "git-roots-v1"
identity = "git:1111111111111111111111111111111111111111111111111111111111111111"

[[associations]]
scope = { kind = "workspace" }
source = "source-main"
role = "working"
```

Its local mapping remains v1 (ignored):

```toml
schema_version = 1

[bindings.source-main]
path = "/code/service"
filesystem = "2049:7001"
```

An empty valid v2 catalog is `schema_version = 2`, `definitions = []`,
`associations = []` on separate lines. It is valid portable state, not A's applied
result. No `project = "workspace"` or other sentinel association exists.

The initial charter can remain the existing valid nine-line v1 file:

```markdown
---
schema_version: 1
name: "Service research"
charter_revision: 0
charter_receipt: null
next_step: null
last_handoff: null
---
No confirmed direction yet. Change this charter only through a reviewed workspace proposal.
```

A workspace overview after apply (hashes illustrative) is:

```markdown
---
schema_version: 1
kind: workspace-overview
scope:
  kind: workspace
revision: 1
receipt: runs/20261118T100000Z-onboard-0123456789abcdef0123456789abcdef/receipt.md
source:
  kind: human
  actor: "Researcher"
recorded_at: "2026-11-18T10:00:00Z"
coverage: "Bounded inventory of selected text; source-main at observed HEAD"
limits:
  - "No source scripts or checks executed"
  - "Generated and credential files excluded; absence is not established"
sources:
  - source: source-main
    catalog_sha256: "2222222222222222222222222222222222222222222222222222222222222222"
    definition_sha256: "3333333333333333333333333333333333333333333333333333333333333333"
    identity: "git:1111111111111111111111111111111111111111111111111111111111111111"
    snapshot: runs/20261118T100000Z-onboard-0123456789abcdef0123456789abcdef/inventory/source-main.json
    snapshot_sha256: "4444444444444444444444444444444444444444444444444444444444444444"
    head: "5555555555555555555555555555555555555555"
supersedes: null
---
## Structure
source-main:src/service contains the request handlers at the pinned commit.
## Entry points
source-main:src/service/main.py is an observed entry point.
## Current behavior
Request processing is visible in the selected text; runtime behavior remains untested.
## Checks
No checks were run. Test instructions need inspection before execution.
## Known gaps
Performance limits and deployment dependencies remain unknown.
```

### B — New workspace plus one project

B starts from a fresh root, not A's already initialized root. Starting with A's
catalog shape, its final catalog **additionally** contains this association:

```toml
# Fragment appended to the A catalog, not a standalone catalog file.
[[associations]]
scope = { kind = "project", project = "latency" }
source = "source-main"
role = "working"
```

The unchanged v1 creation input for latency uses `question`, `included`, `excluded`,
`goal`, `constraints` and initial Brief with a concrete minimal validation
experiment (e.g. measure one request path under a fixed local trace). Preview
shows those actual input bytes. Exactly `projects/latency/` appears with v1
PROJECT.md/brief.md/creation provenance; no Claim or Decision is generated. The
workspace overview remains the owner of overall source understanding. `open
latency` is a later explicit action, never part of apply.

### C — Checked reuse and separate registration

C works identically when the target has zero children or many. For zero children,
use A's existing workspace and the C reuse command. It creates latency with the B
association, leaves the existing definition and local mapping untouched, and does
not change the workspace working association or overview/charter. With old children
latency/throughput, request `isolation`; neither old directory is a write target.
Requesting latency again refuses before packet creation, even if there is exactly
one child or the old latency project is damaged.

For a new separate checkout, this full final fixture registers source-fork once,
keeps the old child/selection and gives the new child its requested source:

```toml
schema_version = 2

[[definitions]]
id = "source-fork"
definition_revision = 1
kind = "git"
identity_method = "git-roots-v1"
identity = "git:1111111111111111111111111111111111111111111111111111111111111111"

[[definitions]]
id = "source-main"
definition_revision = 1
kind = "git"
identity_method = "git-roots-v1"
identity = "git:1111111111111111111111111111111111111111111111111111111111111111"

[[associations]]
scope = { kind = "project", project = "isolation" }
source = "source-fork"
role = "working"

[[associations]]
scope = { kind = "project", project = "latency" }
source = "source-main"
role = "working"

[[associations]]
scope = { kind = "workspace" }
source = "source-fork"
role = "reference"

[[associations]]
scope = { kind = "workspace" }
source = "source-main"
role = "working"
```

Equal illustrative Git identities deliberately show two separate clones, not a
merge by identity. Their ignored bindings point to `/code/fork` at `2049:7002`
and `/code/service` at `2049:7001`. If `/code/fork` actually aliases the old checkout,
registration refuses. If source-main's mapping is missing, `--source-id source-main`
refuses and asks for explicit bind; it cannot transfer that identity's old binding.

### Exact illustrative A envelope

**Every digest in the JSON below is illustrative and unverified, including its
catalog, definition, snapshot and image hashes.** They were not recomputed from
fixture bytes. Copying/parsing this JSON does not make it apply-ready; an executable
fixture must generate its referenced bytes and recompute all hashes and the seal.

This JSON demonstrates the entire v2 envelope with a minimal proposed overview.
For compactness `inputs` is empty (generated from the source inventory, no external
input); there is no child/charter change. Before hashes are null only for actually
absent target files. Local mapping images remain ignored. All image references
must exist with recomputed hashes in an executable fixture.

```json
{
  "association_changes": [
    {
      "after": "working",
      "before": null,
      "scope": {
        "kind": "workspace"
      },
      "source": "source-main"
    }
  ],
  "catalog_version": 2,
  "created": "2026-11-18T10:00:00Z",
  "creation": null,
  "images": [
    {
      "after": "2222222222222222222222222222222222222222222222222222222222222222",
      "after_image": "runs/20261118T100000Z-onboard-0123456789abcdef0123456789abcdef/after/1",
      "before": null,
      "before_image": null,
      "path": "sources.toml"
    },
    {
      "after": "7777777777777777777777777777777777777777777777777777777777777777",
      "after_image": "tools/wo-0123456789abcdef0123456789abcdef-after.local.toml",
      "before": null,
      "before_image": null,
      "path": "tools/sources.local.toml"
    },
    {
      "after": "8888888888888888888888888888888888888888888888888888888888888888",
      "after_image": "runs/20261118T100000Z-onboard-0123456789abcdef0123456789abcdef/after/3",
      "before": null,
      "before_image": null,
      "path": "overview.md"
    }
  ],
  "inputs": [],
  "inventories": [
    {
      "path": "inventory/source-main.json",
      "sha256": "4444444444444444444444444444444444444444444444444444444444444444",
      "source": "source-main"
    }
  ],
  "kind": "workspace-onboarding",
  "mode": "A",
  "notes": null,
  "operation": "onboarding",
  "origin": {
    "actor": "Researcher",
    "kind": "human"
  },
  "preconditions": [
    {
      "path": "WORKSPACE.md",
      "sha256": "6666666666666666666666666666666666666666666666666666666666666666"
    }
  ],
  "project": null,
  "rationale": "Understand the existing service before choosing any independent project.",
  "schema_version": 2,
  "scope": {
    "kind": "workspace"
  },
  "source_actions": [
    {
      "action": "register",
      "definition_sha256": "3333333333333333333333333333333333333333333333333333333333333333",
      "source": "source-main"
    }
  ]
}
```

A B envelope differs by mode/project/creation, a child association and exact v1
creation linkage; a C reuse envelope additionally omits root overview/charter images
and uses `action: reuse`. Its unchanged catalog still needs an image if adding a
child association; the old mapping has only a precondition, no image.

### Invalid schema and operation examples

This parses as TOML but is an invalid v2 definition because project/role belong in
associations, not definitions:

```toml
schema_version = 2
associations = []

[[definitions]]
id = "source-main"
definition_revision = 1
kind = "git"
identity_method = "git-roots-v1"
identity = "git:1111111111111111111111111111111111111111111111111111111111111111"
project = "workspace"
role = "working"
```

This association fragment is invalid when appended to A: workspace scope may not
carry a project key, even one naming a real child:

```toml
[[associations]]
scope = { kind = "workspace", project = "latency" }
source = "source-main"
role = "reference"
```

A valid directory definition uses `kind = "directory"`,
`identity_method = "directory-anchors-v1"` and a `directory:` digest. A Git kind
with directory identity is invalid. So are unknown schema_version 3, duplicate
`(scope, source)`, a missing source definition, two workspace working associations,
a project association naming a missing child, or a definition lacking workspace
association. These are domain errors, not repaired by open/status.

Invalid YAML header fragment (it parses, but may never describe a workspace overview):

```yaml
schema_version: 1
kind: workspace-overview
scope:
  kind: project
  project: latency
revision: 0
```

It has wrong scope, invalid revision and missing required fields; a parser success
cannot make it valid. An otherwise valid overview naming an unsealed notebook as
its receipt is also invalid. A 41-line WORKSPACE.md is invalid regardless of which
section causes the overflow. A workspace native v3 binding, or v4 whose manifest
scope/cwd differs from its binding, refuses. `onboard SOURCE --root EXISTING` without
project is not C; `onboard SOURCE --project latency --init` without root is not B.
Neither a sole child nor matching source basename resolves either error.

## Acceptance matrix

The following are **executable acceptance specifications for WO3–WO5**, not tests
run in WO2. Future automated cases use temporary code/records roots, local fixture
Git identities, deterministic generated packets, fake AoE/Chief and isolated user
config/state. No subscription CLI, network, real source or scheduler is required.
`apply(P)` below means the exact confirmed workspace apply command with P's
**computed** seal and `--confirmed-by FixtureOperator`; `reject(P)` uses the exact
reject form with a nonempty reason. The actor is an operator declaration, not a
researcher usability ruling. Hash-tree comparisons include file bytes and paths,
excluding explicitly volatile ignored operational files.

| ID / owner | Fixture and executable action | Required assertions | Status |
| --- | --- | --- | --- |
| W03-A / WO3 | Fresh committed Git repo S and missing W; run A; inspect P; apply(P) | Before apply no registration/child/overview; after apply zero children, one definition/workspace working association, confirmed root overview, v1 local mapping, no Claim/Spec/Decision, S tree unchanged | NOT RUN |
| W03-A-reject / WO3 | Fresh A; reject(P); replay rejection | Only initialized skeleton/archive/receipt remain; no catalog/local/overview/child; same rejection actor/time | NOT RUN |
| W03-B / WO3 | Fresh S/W; run B with concrete v1 project input; apply(P) twice | Exactly one requested child, one definition, two scope associations; two matching receipts; replay no extra writes/IDs; no native launch | NOT RUN |
| W03-B-legacy / WO3 | Existing explicit `onboard S --root W --project NAME --init --overview FILE` | Still proposed explicit child; FILE remains child overview; separate workspace overview generated/shown | NOT RUN |
| W03-C0 / WO3 | A-applied W with zero children; C with checked source ID; apply(P) | One new child; no duplicate definition/mapping; workspace working/charter/overview unchanged | NOT RUN |
| W03-Cmany / WO3 | W with two healthy children; C reuse under new name; hash old trees before/after | Exactly one added child; both old trees byte-identical; no changed old roles; root context unchanged | NOT RUN |
| W03-Cnew / WO3 | Existing W; new non-overlapping repo checkout T; C with register-source; apply(P) | One new definition/workspace reference/new child working association; old workspace working selection unchanged; no source copies | NOT RUN |
| W03-dup / WO3 | C requests an existing, corrupt, empty or staged child name (parameterized) | Exit 1 before packet; no source/local/child edits; no continue-existing fallback | NOT RUN |
| W03-root / WO3 | Missing root flag, ambiguous registry, unrelated nonempty W, existing W with init, empty W without init | Correct 2/1 exits per table; no accidental initialization/overwrite/source edits | NOT RUN |
| W03-source / WO3 | Parent/child overlaps, path symlink, Git subdirectory, alias device/inode under another ID | Exit 1; source bytes untouched; no sealed proposal claiming valid registration | NOT RUN |
| W03-identity / WO3 | Same upstream/different roots; equal roots/different checkouts; missing mapping; explicit mismatched ID | No upstream-only merge; checked exact reuse only; distinct registration allowed; missing bind/mismatch refuses | NOT RUN |
| W03-directory-recovery / WO3 | Edited/moved directory whose old anchors no longer match: bind old ID; register new ID at distinct path/device-inode as reference; apply; separately select working/apply; retry same-path and retained-inode variants | Old bind mismatch refuses; reviewed new definition/current anchors and two separate decisions succeed only at noncolliding location; old provenance preserved; same-path/old-inode collisions refuse; no re-anchor, copy or implicit child change | NOT RUN |
| W03-preparation-owner / WO3 | B/C/derive: interrupt after inventories, private v1 seal, public marker+child archive, and outer seal; then change/delete/redirect marker or attempt direct child create | No unowned sealed child becomes visible; outer-sealed marker input/precondition and creation reference validate; orphan/inconsistent ownership refuses; deleting marker never bypasses sealed outer ownership; no digest cycle | NOT RUN |
| W03-work-at / WO3 | A/B/C with non-overlapping SOURCE and TARGET, plus equal/nested invalid variants | Correct reference/working associations for new scopes; C old workspace working unchanged; invalid variants fail | NOT RUN |
| W03-tamper / WO3 | Edit seal, input, inventory, after image or creation ownership marker after preview | Exit 1; no publication; bytes retained for inspection | NOT RUN |
| W03-stale / WO3 | After preview edit catalog/charter/read overview/source HEAD/dirty bytes or replace checkout | First confirmed apply refuses; no partial targets; new proposal required | NOT RUN |
| W03-crash / WO3 | Inject crash before journal, after journal, during stage, after child rename, between catalog/local writes, before/after receipts, before retirement; replay exact apply | Before commit no effects; after commit recovery forwards identical images; child cannot open while journal exists; one final child/receipt | NOT RUN |
| W03-edit-recovery / WO3 | Crash mid-publication; add unexpected staged/published child file or edit target to neither image; retry | No further writes after global precheck; journal/all images retained; explicit actionable refusal | NOT RUN |
| W03-race / WO3 | Two packets share catalog before digest, or concurrent duplicate child creation; apply from coordinated fixture threads/processes | One serial success; other stale/conflict; no merged invisible preview changes or usable partial child | NOT RUN |
| W03-overview / WO3 | A generated/supplied overview then separate update, reject and apply; C note only; test 40/41-line charter | Coverage/limits/pins retained; revision only advances on apply; C never updates root overview/charter; charter limit enforced | NOT RUN |
| W03-schema / WO3 | Parse valid A/B/C TOML and malformed/unknown/duplicate/cross-scope cases above | Exact version/key/type/uniqueness errors; no automatic repair; canonical writes preserve semantics | NOT RUN |
| W04-zero / WO4 | A W with no children; fake native open/status/map/draft --workspace | Selected source cwd, useful understanding/notes/work actions; no missing Claim/gate demand or sentinel child | NOT RUN |
| W04-scope / WO4 | Zero/one/multiple children; explicit --workspace in open/status/map/draft from child records cwd (where present); bare entry at W root or explicit-root open from linked checkout | Explicit workspace always wins; workspace-root entry stays workspace; external source/sole child/history never selects a child; missing root refuses | NOT RUN |
| W04-v4 / WO4 | Fake source-backed workspace/project open, prepare/send/ack at valid pins; swap token/scope/cwd/manifest | Binding/manifest/ack v4 agree; wrong pins refuse; no falsely acknowledged delivery | NOT RUN |
| W04-stale / WO4 | Change source selection/mapping/checkout or move W after bind; refresh/recover | Stale notice/refusal; old session never redirected; explicit new/replacement at same requested scope; history preserved | NOT RUN |
| W04-writers / WO4 | Fake live writers across scopes/profiles at same path/device-inode; concurrent launch; lookup failure | Second writer refuses; serialized launch check; uncertainty refuses launch; no action sent to existing session | NOT RUN |
| W04-permission / WO4 | Integrate delivered permission mechanism with workspace input; test missing intent, narrowed intent and intent change | No registration-implied access; explicit permission preserved/reconfirmed; missing scope support refuses; no competing local policy key | NOT RUN |
| W04-context / WO4 | Inspect workspace/project resident inputs and stale fingerprints; append notebook; create child | Exact scope resident set and labeled unconfirmed excerpt; no sibling/private history; child creation does not redirect workspace binding | NOT RUN |
| W04-task / WO4 | Fill workspace v2 task, fake confirm/export; change pin/baseline/checks/config; simulate uncertain new | No Claim/Spec needed; frozen exact source/commit/scope/export; changes refuse; recovery queries same ID, no duplicate task/kickoff | NOT RUN |
| W04-import / WO4 | Fake done/abandoned task; preview/confirm import twice; crash between record/Run/applied; tamper artifact | One operational workspace run.md, no formal root IDs; exact pins/artifacts/result; failed state preserved; replay idempotent; no scientific promotion | NOT RUN |
| W05-derive / WO5 | A W with notes/overview and shared sources; later project propose with source/working flags; reject then new proposal/apply | Reviewed child only; references existing definitions/context; workspace history/source tree untouched; no automatic working inheritance/launch | NOT RUN |
| W05-entry-compat / WO5 | W with zero/one/multiple children: run bare open/status/map at W and inside each existing child records directory; repeat open with explicit root/--workspace, map with --workspace, and explicit-root open from external source | Preserve baseline bare-open discovered-root child inference and bare-map records-directory inference; bare status remains workspace; explicit --workspace always workspace; explicit-root open without project stays workspace; no source-cwd/sole-child/history inference | NOT RUN |
| W05-v1 / WO5 | Existing valid source catalog/local mapping v1, native v1/v2/v3, project overviews/proposals/receipts/handoffs; open/status/explicit child commands | Original read semantics and byte-identical old files; no read conversion or root/project reassignment; old archives validate | NOT RUN |
| W05-upgrade / WO5 | V1 workspace; propose upgrade, reject; propose/apply; crash/recover; include pending v1 source packet variant | Opt-in only; exact legacy artifact/digest; definitions dedup by ID; old child roles/trees/local bytes unchanged; workspace references only; pending conflict refuses | NOT RUN |
| W05-forward / WO5 | Unknown catalog/local/binding/overview versions and damaged active v2 with valid old artifact | Explicit invalid-data diagnostics; no partial parse or fallback to legacy; unrelated old child inspection still possible | NOT RUN |
| W05-interactive / WO5 | No-TTY decide/apply without confirm/bind; explicit seal/actor forms; multiple root/source candidates | Lists/no writes or correct refusal; explicit authorized-operator path deterministic; no implicit yes/sole-candidate project | NOT RUN |
| W05-live / WO5 | Later separately authorized disposable live A/B/C journeys, including C reuse, workspace-only engineering, later child derivation and fresh-session restoration | Record actual cwd/permission/delivery/result behavior and limitations; agent execution distinguished from researcher ruling | NOT RUN |
| W05-human / Researcher | Review specification and later recorded journeys | Separate explicit WO2 specification acceptance and subsequent usability ruling; no automated check substitutes for either | PENDING |

WO2 validation is document diff/reference/serialization/scope/whitespace checking
only. The external document checker does not validate schema semantics, protocol
completeness, security/isolation or usability. Chief's independent review must
assess cross-section consistency, recoverability, permission integration assumptions
and compatibility before researcher acceptance. WO3–WO5 runtime implementation,
any live model/AoE/Chief trial and real-data conversion remain outside this delivery.
