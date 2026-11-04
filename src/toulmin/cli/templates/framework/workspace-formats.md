# Workspace-first file contract (WI1)

Status: contract frozen in WI1 on 2026-11-04 from the accepted WS1 state design, WS2 operation
scheme and WS3 acceptance plan. Implemented so far: sections 2.1, 4 and 12 (init, WI2), and
sections 5–7 with the section 10 journal for workspace changes (WI3). Workspace handoffs, child
creation, bindings and adoption are not implemented; WI4–WI7 add them in order, and until a
release note says a command exists, do not create those files by hand. WS3 acceptance cases
remain NOT RUN.

This contract is additive. The seven object types, PROJECT.md, brief.md, project handoffs,
review manifests and every other rule in [formats.md](formats.md) are unchanged (project
object v1). Nothing here is an eighth object type, a global ID namespace or a scientific status.

## 1. Common rules

- Encoding, the restricted YAML header subset, quoted RFC 3339 UTC timestamps and portable
  root-relative paths follow formats.md. Every header has integer `schema_version: 1` (bindings:
  section 11). Unknown fields, unknown versions and missing required fields are errors; nothing
  is migrated or repaired on read. Workspace records have no `extensions` field in version 1.
- Digests are lowercase 64-hex SHA-256 over exact file bytes. `tree-v1` digests (section 6)
  cover directories. A digest proves byte identity, never correctness.
- Archive directories are `YYYYMMDDTHHMMSSZ-<kind>-<32 lowercase hex>` with kind `proposal`,
  `project`, `handoff`, `adoption` or `aoe-context`; the hex part is random, not a digest. Agent-
  written activity archives may use any name allowed for Run archives in formats.md.
- Root `runs/` and `sessions/` hold workspace records only. They never contain `R-NNN.md`
  objects; such a file at the root is reported as misplaced and never loaded as an object.
  Qualified references (`scheduling/C-001`) keep their syntax and meaning. Workspace documents
  may contain `[[project/X-NNN]]` markers; unqualified markers are errors there because the
  workspace has no objects of its own. Markers are checked for syntax and existence only.
- Limits: WORKSPACE.md 40 lines; any single snapshot, input or after image 1,000,000 bytes.
  A larger source is recorded by path and digest with `snapshot: null`; nothing is truncated.
- Absent knowledge is `null`, never a guess: unknown model, native session, provider identity
  and capture coverage stay null or `unknown` and are displayed as unknown.
- Examples in sections 4–9 form one consistent fixture (the WS3 "Serving Research" workspace):
  every digest was computed from the bytes shown, and every header parses with the toolkit's
  restricted YAML reader. The rejected receipt, binding and adoption examples are illustrative.
- Authority vocabulary. *Confirmed*: published by an operation whose receipt or applied record
  names a researcher (section 13). *Pending*: a sealed proposal with no disposition. *Draft*:
  any unconfirmed file under `runs/`. Confirmation fields record an authorization declaration,
  not authentication, as elsewhere in Toulmin.

## 2. Scope

A scope is the research unit a session, draft or record belongs to. Its serialized form is a
mapping, mirroring `source`:

| Scope | Serialized | Display | Record directory | Default draft location |
| --- | --- | --- | --- | --- |
| Workspace | `{kind: workspace}` | `Workspace` | root | `runs/` |
| Child project | `{kind: project, project: scheduling}` | `Project: scheduling` | `projects/scheduling/` | `projects/scheduling/runs/` |

`project` follows the project-name rule; `kind` has no other values in version 1. Scope lives in
L1 as plain data; L2 plans inputs from it; neither imports a CLI or provider module. Every
generated draft, packet, binding and context manifest carries its scope, and a record is
refused by an operation for another scope (F02). A command argument cannot redirect a record.

### 2.1 Root classification (read-only)

Readers classify `--root` without writing, in this order:

| State | Rule | Readers report |
| --- | --- | --- |
| missing | directory absent | the path; `init ROOT` creates a workspace |
| empty | no entries, or only `.git` | uninitialized |
| workspace | `WORKSPACE.md` is a regular file (valid or not) | identity, or its validation errors |
| incomplete-init | no `WORKSPACE.md`; every entry is an unmodified template path; `projects/` empty | rerun `init ROOT` |
| legacy | no `WORKSPACE.md`; `AGENTS.md`, `framework/formats.md` and `projects/` exist and the root is not incomplete-init | "workspace state not configured", its projects, and `workspace adopt ROOT` |
| unrelated | anything else | not a Toulmin workbench; nothing is initialized |

A pending journal (section 10) is reported in every state. A malformed WORKSPACE.md is a data
error; valid child projects stay inspectable through project commands (F12).

### 2.2 Selection in L3 commands

- In the `aoe` group and workspace commands, omitting PROJECT selects the workspace even when
  exactly one child exists. `--workspace` is an explicit spelling of the same choice; giving both
  PROJECT and `--workspace` is a usage error (exit 2). Last-used scope, the only child, the AoE
  profile and native history never select a scope (F11).
- `--root` names the shared workbench and defaults to the current directory. Parents are never
  searched. If the current directory is `<root>/projects/<name>` (or inside it) and is not
  itself a workbench, the error names the probable root and the exact `--root` correction.
- Every result prints the resolved root and scope first. Read/open commands never initialize.

## 3. Layout

```text
WORKSPACE.md                                  confirmed charter (section 4)
runs/drafts/                                  free drafts and operation inputs (unconfirmed)
runs/<activity>/activity.md                   exploration records (section 5)
runs/<stamp>-proposal-<hex>/                  workspace change packets (section 7)
runs/<stamp>-project-<hex>/                   child creation packets (section 9)
runs/<stamp>-handoff-<hex>/                   workspace handoff drafts (section 8)
runs/<stamp>-adoption-<hex>/                  adoption records (section 12)
runs/<stamp>-aoe-context-<hex>/               workspace context snapshots (section 11)
sessions/<stamp>-<sha256>.md                  applied workspace handoffs (section 8)
shared/resources/<name>.md                    resource descriptions (section 6)
shared/data/, shared/code/                    optional material; layout not prescribed
.workspace-pending/                           publication journal (section 10; git-ignored)
.aoe/binding.json                             workspace native binding (section 11)
projects/<name>/                              unchanged project v1 layout, plus
  runs/creation/                              creation provenance of reviewed children
```

## 4. WORKSPACE.md

The short confirmed charter. Header fields, in this order:

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | `1` | |
| `name` | string, one line, at most 80 characters | display identity, not a research claim |
| `charter_revision` | integer >= 0 | count of applied charter changes |
| `charter_receipt` | receipt path or null | receipt of the latest charter change; null iff revision is 0 |
| `next_step` | string or null | recorded next step from the latest workspace handoff (historical guidance) |
| `last_handoff` | session filename or null | latest applied workspace handoff in `sessions/` |

Body: optional prose before the first heading, then any of the level-two sections `Direction`,
`Constraints`, `Focus`, in that order, each nonempty. Other level-two sections are errors. A
missing `Direction` section is the only representation of an absent direction and is shown as
"No confirmed direction yet". Focus may name projects and qualified object markers.
Project lists, stages, counts, resource inventories and profile content are never stored here.

Initial file written by `init ROOT` or adoption (`next_step` and `last_handoff` start null; no
section exists, so the direction is absent):

````markdown
---
schema_version: 1
name: "Serving Research"
charter_revision: 0
charter_receipt: null
next_step: null
last_handoff: null
---
No confirmed direction yet. Change this charter only through a reviewed workspace proposal.
````

After the charter change of section 7 (revision 1):

````markdown
---
schema_version: 1
name: "Serving Research"
charter_revision: 1
charter_receipt: runs/20261104T101500Z-proposal-a41c9e07d3b24f5e9b6c8d7e1f203a4b/receipt.md
next_step: null
last_handoff: null
---
## Direction
Understand how request scheduling policy affects tail latency on a single serving node.

## Constraints
Use local synthetic or recorded traces until a measurement plan is agreed.
````

After the workspace handoff of section 8 (only `next_step` and `last_handoff` differ):

````markdown
---
schema_version: 1
name: "Serving Research"
charter_revision: 1
charter_receipt: runs/20261104T101500Z-proposal-a41c9e07d3b24f5e9b6c8d7e1f203a4b/receipt.md
next_step: "Propose the scheduling child: question, single-queue scope and initial Brief."
last_handoff: 20261104T113500Z-e20af3052161408966e4e0a6be2eb445b6dc2f98a3315ad1bb4a852df0d99584.md
---
## Direction
Understand how request scheduling policy affects tail latency on a single serving node.

## Constraints
Use local synthetic or recorded traces until a measurement plan is agreed.
````

Permitted changes (all other bytes stay identical):

| Operation | May change |
| --- | --- |
| `init ROOT [--name]`, adoption | create the initial file only |
| workspace change apply | `name`, `charter_revision` (+1), `charter_receipt`, the three sections; body regenerated in canonical order |
| workspace handoff apply | `next_step`, `last_handoff` |
| child creation, project handoff, review, AoE operations | nothing |

Manual editing. The researcher may edit the charter by hand; that edit is their own
authorization but has no receipt. Readers then report "charter differs from its last receipt"
when the charter-owned parts (`name`, `charter_revision`, `charter_receipt` and the body) differ
from the receipted after image and no journal explains it; handoff fields are not compared,
because a workspace handoff changes them legitimately. The content is still shown, labeled as
edited outside a receipt. Agents must not hand-edit this file;
they prepare a proposal. Any edit makes pending proposals and drafts based on the old bytes stale.

## 5. Activity records and drafts (unconfirmed)

Agents save exploration output in the current scope's `runs/` without any approval. Files
under `runs/drafts/` are free-form inputs and scratch. An activity archive groups one bounded
activity: optional raw material plus `activity.md`:

| Field | Type | Meaning |
| --- | --- | --- |
| `kind` | `workspace-activity` | |
| `scope` | scope | must be `{kind: workspace}` under root `runs/` |
| `created` | timestamp | |
| `purpose` | string | |
| `recorded_by` | `{kind: human, actor}` or `{kind: agent, role, agent, model, session_id}` | `agent`, `model`, `session_id` are nullable provenance strings |
| `capture` | `{coverage, complete, limits}` | coverage `full`, `selected`, `summary` or `unknown`; `complete` false for interrupted capture; `limits` required unless coverage is full and complete |
| `sources` | list of `{path, url, sha256, note}` | exactly one of path/url; sha256 nullable |

Body: `Summary` required; `Researcher feedback` and `Open ideas` optional. A summary is never
labeled as a full transcript; missing turns are never invented (F14).

````markdown
---
schema_version: 1
kind: workspace-activity
scope: {kind: workspace}
created: "2026-11-04T09:30:00Z"
purpose: "Discuss request scheduling and tail latency; inspect the synthetic trace."
recorded_by: {kind: agent, role: explorer, agent: codex, model: null, session_id: null}
capture: {coverage: selected, complete: true, limits: "Selected researcher messages and the final agent summary; tool output omitted."}
sources:
  - {path: shared/data/synthetic-queue-trace/trace.csv, sha256: 7655c221b895982f51cb8e73ffbfa0675e05f6609e8ab54946d2fb28c12a8400, url: null, note: "Synthetic trace supplied by the researcher."}
---
## Summary
Scheduling policy may dominate p99 latency under bursty arrivals. The trace is synthetic.

## Researcher feedback
Correction: limit the first study to a single queue on one node; multi-node routing is out of scope.

## Open ideas
- Caching as a later direction (unconfirmed; not a project).
````

Activity records may be revised freely. Proposals snapshot what they cite, so a later edit
changes nothing already proposed but makes that proposal stale (section 7.4).

## 6. Shared resource descriptions

`shared/resources/<name>.md` (`name` follows the project-name rule) registers one located,
versioned resource for reuse. It is a confirmed description, not Evidence, and never supports
or upgrades a Claim.

| Field | Type | Meaning |
| --- | --- | --- |
| `resource` | string | equals the filename stem |
| `title` | string | |
| `status` | `active` or `withdrawn` | withdrawal keeps the file and its history |
| `kind` | `data`, `code`, `document` or `other` | |
| `location` | `{path, url}` | exactly one non-null |
| `version` | `{method, sha256, revision}` | see below |
| `origin` | string | how the material was obtained or generated |
| `revision` | integer >= 1 | description revision |
| `previous_sha256` | digest or null | bytes of the previous description; null iff revision 1 |
| `receipt` | receipt path | the applied change that published this revision |

Body: `Purpose` and `Limitations` required and nonempty; `Notes` optional.

- `location.path` is root-relative and must exist when proposed and applied. It may not lie in
  `sessions/`, `shared/resources/`, journal or `.aoe` directories, or a project's seven formal
  object directories. `location.url` is http/https and is never fetched.
- `version.method` is `file` (path is a regular file; sha256 of its bytes), `tree-v1` (path is a
  directory) or `external` (url). Path locations require `sha256`; `external` requires `sha256`
  or `revision`. `revision` is an opaque string such as a Git commit. A working tree's path
  alone is never a version.
- `tree-v1`: walk the directory recursively; every entry must be a regular file or directory
  (symlinks and special files are errors); empty directories are ignored. For each file emit
  `<sha256>  <path relative to the directory>\n`; sort lines by the UTF-8 bytes of the path;
  the digest is SHA-256 of the concatenation.
- Previous revisions remain recoverable: each revising receipt's packet retains the exact
  before and after images. Old pins keep their own digests (below).

````markdown
---
schema_version: 1
resource: synthetic-queue-trace
title: "Synthetic single-queue request trace"
status: active
kind: data
location: {path: shared/data/synthetic-queue-trace, url: null}
version: {method: tree-v1, sha256: 8a1e96927975330167f8c5bdd4c4fa142ed55b3f0f69249c143908b299fd7336, revision: null}
origin: "Generated by the researcher for the WS3 fixture; synthetic."
revision: 1
previous_sha256: null
receipt: runs/20261104T101500Z-proposal-a41c9e07d3b24f5e9b6c8d7e1f203a4b/receipt.md
---
## Purpose
Exercise queueing discussions and tooling on a small, reproducible input.

## Limitations
Synthetic and tiny; insufficient to establish any performance result.
````

Pins. A record that relies on a registered resource pins it as
`{resource, revision, description_sha256, path, url, method, sha256}`. A pin is checked by
recomputing the material digest (path locations) and comparing the description's current
bytes. Missing material, a different digest or a newer description revision is reported as a
broken or stale pin; the latest content is never substituted (F13). External material is
checked only against its description, offline. A pinned record keeps `path`/`method`/`sha256`
so it stays meaningful after the description is revised or withdrawn.

## 7. Workspace changes: input → packet → receipt

Only two target kinds exist: `WORKSPACE.md` (replace) and `shared/resources/<name>.md`
(create or replace). A packet cannot name any other path, project file or material.

### 7.1 Input (`workspace propose --input FILE`)

A draft under root `runs/drafts/`, written by the agent or researcher:

| Field | Type | Meaning |
| --- | --- | --- |
| `kind` | `workspace-change-input` | |
| `scope` | `{kind: workspace}` | |
| `supersedes` | packet directory or null | the pending packet this revises |
| `sources` | list of `{path, coverage}` or `{url, coverage}` | material the change rests on |
| `pins` | list of `{resource, revision, sha256}` | existing resources the change relies on |
| `changes` | nonempty list | at most one `charter` entry and one entry per resource |

A `charter` change has optional `name` and optional `sections`, a mapping whose keys are
`Direction`, `Constraints`, `Focus`: a string sets the section, `null` removes it, an absent key
keeps it. A `resource` change has `resource`, `action` (`register` when the description is
absent, `revise` when present) and the description fields of section 6 except `resource`,
`revision`, `previous_sha256` and `receipt`, plus `purpose`, `limitations` and optional `notes`
body strings. `register` requires all of them; `revise` copies omitted fields from the current
revision. Body: `Question` and `Unresolved assumptions` required; the latter may say "None.".

````markdown
---
schema_version: 1
kind: workspace-change-input
scope: {kind: workspace}
supersedes: runs/20261104T100000Z-proposal-0d9e8c7b6a5f4e3d2c1b0a9f8e7d6c5b
sources:
  - {path: runs/20261104T093000Z-activity-6b1f0c2e9a4d4e7f8c3b2a1d0e9f8a7b/activity.md, coverage: selected}
pins: []
changes:
  - target: charter
    sections:
      Direction: "Understand how request scheduling policy affects tail latency on a single serving node."
      Constraints: "Use local synthetic or recorded traces until a measurement plan is agreed."
  - target: resource
    resource: synthetic-queue-trace
    action: register
    title: "Synthetic single-queue request trace"
    status: active
    kind: data
    location: {path: shared/data/synthetic-queue-trace, url: null}
    version: {method: tree-v1, sha256: 8a1e96927975330167f8c5bdd4c4fa142ed55b3f0f69249c143908b299fd7336, revision: null}
    origin: "Generated by the researcher for the WS3 fixture; synthetic."
    purpose: "Exercise queueing discussions and tooling on a small, reproducible input."
    limitations: "Synthetic and tiny; insufficient to establish any performance result."
---
## Question
Adopt the single-node scheduling direction and register the synthetic trace for reuse?

## Unresolved assumptions
- The trace's burst pattern resembles production arrivals (unverified).
````

### 7.2 Packet

Propose validates the input, reads current targets, computes after images and publishes one
complete archive by renaming a dot-prefixed staging directory in `runs/`:

```text
runs/20261104T101500Z-proposal-a41c9e07d3b24f5e9b6c8d7e1f203a4b/
  packet.md        review packet (below)
  input.md         exact input bytes
  sources/N.EXT    exact snapshots of local sources (N in `sources` order, original suffix)
  targets/N.md     exact after images, in `targets` order
  seal             SHA-256 of packet.md, then LF
```

`packet.md` header: `kind: workspace-change`, `scope`, `created`, `input {path, sha256,
snapshot}`, `supersedes`, `sources` (each `{path, url, sha256, snapshot, coverage}`), `pins`
(full pin form), and `targets` (each `{path, before_sha256, after_sha256, after}`;
`before_sha256` null means the target must be absent). The receipt path is always
`<packet directory>/receipt.md`, so after images can name it before approval. Body, generated
deterministically: `Question`, `Changes` (one unified diff per target, fenced with one more
backtick than the longest backtick run inside), `Sources` (with coverage), `Unresolved
assumptions`, and `Not changed`, which states that no project, Claim, Evidence, Decision, stage
or handoff changes.

````markdown
---
schema_version: 1
kind: workspace-change
scope: {kind: workspace}
created: "2026-11-04T10:15:00Z"
input: {path: runs/drafts/workspace-direction.md, sha256: 682d1163e972dc56dd3c8267d2461ad2b303eac37eb2dd9d236a0b25680a8d30, snapshot: input.md}
supersedes: runs/20261104T100000Z-proposal-0d9e8c7b6a5f4e3d2c1b0a9f8e7d6c5b
sources:
  - {path: runs/20261104T093000Z-activity-6b1f0c2e9a4d4e7f8c3b2a1d0e9f8a7b/activity.md, url: null, sha256: 470842d3f25bd50a518a3e223a348fc86a0d410174075c8d419dd044fa3447ed, snapshot: sources/1.md, coverage: selected}
pins: []
targets:
  - {path: WORKSPACE.md, before_sha256: 3a9d405abca38945ad12898f8e3b61c79e012bc310671de496ac8e4d366d6793, after_sha256: e2921083e133609ce433901d0224e4d67d57fad657f5f1417bbeb5b039440d2a, after: targets/1.md}
  - {path: shared/resources/synthetic-queue-trace.md, before_sha256: null, after_sha256: 0f3a9c8324cc380693fabbca95b48f2cda80f913fd1cbd46143cac509e3175d2, after: targets/2.md}
---
## Question
Adopt the single-node scheduling direction and register the synthetic trace for reuse?

## Changes
```diff
--- a/WORKSPACE.md
+++ b/WORKSPACE.md
@@ -1,9 +1,13 @@
 ---
 schema_version: 1
 name: "Serving Research"
-charter_revision: 0
-charter_receipt: null
+charter_revision: 1
+charter_receipt: runs/20261104T101500Z-proposal-a41c9e07d3b24f5e9b6c8d7e1f203a4b/receipt.md
 next_step: null
 last_handoff: null
 ---
-No confirmed direction yet. Change this charter only through a reviewed workspace proposal.
+## Direction
+Understand how request scheduling policy affects tail latency on a single serving node.
+
+## Constraints
+Use local synthetic or recorded traces until a measurement plan is agreed.
```

```diff
--- a/shared/resources/synthetic-queue-trace.md
+++ b/shared/resources/synthetic-queue-trace.md
@@ -0,0 +1,18 @@
+---
+schema_version: 1
+resource: synthetic-queue-trace
+title: "Synthetic single-queue request trace"
+status: active
+kind: data
+location: {path: shared/data/synthetic-queue-trace, url: null}
+version: {method: tree-v1, sha256: 8a1e96927975330167f8c5bdd4c4fa142ed55b3f0f69249c143908b299fd7336, revision: null}
+origin: "Generated by the researcher for the WS3 fixture; synthetic."
+revision: 1
+previous_sha256: null
+receipt: runs/20261104T101500Z-proposal-a41c9e07d3b24f5e9b6c8d7e1f203a4b/receipt.md
+---
+## Purpose
+Exercise queueing discussions and tooling on a small, reproducible input.
+
+## Limitations
+Synthetic and tiny; insufficient to establish any performance result.
```

## Sources
- runs/20261104T093000Z-activity-6b1f0c2e9a4d4e7f8c3b2a1d0e9f8a7b/activity.md (selected messages; complete capture of that selection)

## Unresolved assumptions
- The trace's burst pattern resembles production arrivals (unverified).

## Not changed
No project, Claim, Evidence, Decision, stage or handoff is created or changed. A
registered resource is not Evidence for any Claim.
````

Binding preview to confirmation. The packet, its subfiles and its seal are written once and never
rewritten. Preview (apply without `--confirm`, or the propose output) verifies the seal and
every listed digest, then renders this same packet: its path, scope, question, diffs, sources,
assumptions, the first 16 hex digits of the seal and the exact apply command. Apply verifies the
same seal and digests, so what was previewed is what is applied; any edit after propose makes
the packet invalid ("packet changed after preview; propose again"). A revised proposal is a new
packet with `supersedes`, never an edited one.

### 7.3 Derived dispositions

Determined from files only, never from directory names, prose or session files:

| Disposition | Rule |
| --- | --- |
| invalid | seal, digest or schema check fails (data error; never repaired) |
| incomplete | the journal names this packet |
| applied / rejected | `receipt.md` with that disposition is valid for this packet's seal |
| superseded | another valid packet names it in `supersedes` and it has no receipt |
| pending | none of the above |

A packet has at most one successor; `supersedes` must name a pending packet of the same kind.
Applied sources stay inspectable and are never listed as unresolved work.

### 7.4 Apply (`workspace apply --draft PACKET --confirmed-by ACTOR --confirm`)

Checks, all before writing, in this order:
1. The root is a workspace; no journal exists for another record (else finish that first).
2. PACKET is `runs/<stamp>-proposal-<hex>/` (or its packet.md) under the root, `kind:
   workspace-change`, `scope: {kind: workspace}`, with a valid seal and digests (F02).
3. A valid receipt → return it unchanged (idempotent replay, exit 0), whatever actor is given now.
   A journal for this packet → recovery (section 10).
4. `--confirm` and an actor (`--confirmed-by` or `TOULMIN_ACTOR`); `--confirmed-by` without
   `--confirm` is refused with nothing written (F01). Optional captured approval text.
5. Not superseded or rejected.
6. Every target's current bytes match `before_sha256` (absent when null); every local source
   still matches its digest; every pin and every registered or revised resource's material
   matches (F03, F13). Unrelated files, other resources and child projects are not compared.

Publication: journal → targets → receipt → retire journal (section 10). The receipt is created
exclusively in the packet directory:

| Field | Type | Meaning |
| --- | --- | --- |
| `kind` | `workspace-receipt` | shared by change, creation and adoption records |
| `record` | path | the packet (or adoption plan) this disposes of |
| `record_sha256` | digest | equals the seal |
| `disposition` | `applied` or `rejected` | |
| `actor`, `at` | string, timestamp | from the journal's first confirmation |
| `approval_text` | string or null | the researcher's captured approval, when supplied |
| `reason` | string or null | required for rejected, null for applied |
| `results` | list of `{path, before_sha256, after_sha256}` | published files; empty for rejected |

Body: the fixed sentence shown in the example.

````markdown
---
schema_version: 1
kind: workspace-receipt
record: runs/20261104T101500Z-proposal-a41c9e07d3b24f5e9b6c8d7e1f203a4b/packet.md
record_sha256: 24c921f88c515268b33de5f2df45f2e1ee677206aa9a456ef04315b2568cca20
disposition: applied
actor: "Tianchi YU"
at: "2026-11-04T10:20:00Z"
approval_text: "Approve this packet: direction, constraints and the trace registration."
reason: null
results:
  - {path: WORKSPACE.md, before_sha256: 3a9d405abca38945ad12898f8e3b61c79e012bc310671de496ac8e4d366d6793, after_sha256: e2921083e133609ce433901d0224e4d67d57fad657f5f1417bbeb5b039440d2a}
  - {path: shared/resources/synthetic-queue-trace.md, before_sha256: null, after_sha256: 0f3a9c8324cc380693fabbca95b48f2cda80f913fd1cbd46143cac509e3175d2}
---
Confirmation receipt. It records an administrative approval, not scientific support.
````

### 7.5 Reject (`workspace reject --draft PACKET --reason TEXT --confirmed-by ACTOR --confirm`)

Allowed for a pending packet only. Writes one receipt exclusively; no other file changes.
Repeating it returns the existing rejected receipt; rejecting an applied packet is refused.
Rejection is final: revise by proposing a new packet without `supersedes`.

````markdown
---
schema_version: 1
kind: workspace-receipt
record: runs/20261104T104500Z-proposal-9a8b7c6d5e4f40312a1b2c3d4e5f6a7b/packet.md
record_sha256: 4c1f0e3d2b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f3e
disposition: rejected
actor: "Tianchi YU"
at: "2026-11-04T10:50:00Z"
approval_text: null
reason: "Caching is not a shared direction yet; keep it as an open idea."
results: []
---
Confirmation receipt. It records an administrative approval, not scientific support.
````

## 8. Workspace handoff: input → draft → applied record

The project handoff contract in formats.md is unchanged. The workspace form mirrors it.

Input (`aoe handoff --workspace --input FILE`): `kind: workspace-handoff-input`, optional
`session_id`, optional `next_step`, optional `confirmed_changes` (applied receipt paths from
this session). Body sections `Done`, `Confirmed changes`, `Pending ideas`, `Open questions`, all
required and nonempty ("None." is allowed); `Next step` is forbidden. A research proposal, a
change input or a project summary given here is refused with the expected kind named (F02).
Without `next_step`, the current WORKSPACE value is inherited; if that is null, input is refused.

````markdown
---
schema_version: 1
kind: workspace-handoff-input
session_id: null
next_step: "Propose the scheduling child: question, single-queue scope and initial Brief."
---
## Done
Discussed scheduling versus tail latency; corrected the scope to a single node.

## Confirmed changes
Direction, constraints and the synthetic trace registration were approved in this session.

## Pending ideas
- Caching as a later direction (unconfirmed).

## Open questions
- Which recorded trace could replace the synthetic one?
````

Draft: `runs/<stamp>-handoff-<hex>/draft.md` plus `seal` (as in 7.2), written once. Header: `kind:
workspace-handoff`, `scope`, `created` (sub-second, as for project handoffs), `input {path,
sha256}`, `session_id`, `base_workspace_sha256` (exact WORKSPACE.md bytes when drafted),
`confirmed_changes`, `next_step`. Body: the four input sections plus `Next step` with the fixed
text `See metadata next_step.` Generation writes nothing else.

````markdown
---
schema_version: 1
kind: workspace-handoff
scope: {kind: workspace}
created: "2026-11-04T11:30:00.412Z"
input: {path: runs/drafts/workspace-handoff.md, sha256: ef86101f8794e9f97f4b238c0f751fd6ebf9ebd86e3a74ca990b4ad61c7dd786}
session_id: null
base_workspace_sha256: e2921083e133609ce433901d0224e4d67d57fad657f5f1417bbeb5b039440d2a
confirmed_changes: [runs/20261104T101500Z-proposal-a41c9e07d3b24f5e9b6c8d7e1f203a4b/receipt.md]
next_step: "Propose the scheduling child: question, single-queue scope and initial Brief."
---
## Done
Discussed scheduling versus tail latency; corrected the scope to a single node.

## Confirmed changes
Direction, constraints and the synthetic trace registration were approved in this session.

## Pending ideas
- Caching as a later direction (unconfirmed).

## Open questions
- Which recorded trace could replace the synthetic one?

## Next step
See metadata next_step.
````

Apply (`aoe handoff --workspace --apply DRAFT --confirmed-by ACTOR --confirm`) checks seal and
kind; returns the record if `WORKSPACE.last_handoff` or its `previous_handoff` chain already
names this draft digest; resumes a journal for it; then requires `base_workspace_sha256` to
match the current file and every `confirmed_changes` receipt to be valid and applied. It
publishes `sessions/<UTC>-<full draft sha256>.md` exclusively, then patches only `next_step`
and `last_handoff`. The record keeps every draft field and the body and adds `source_draft`,
`source_sha256`, `applied_by`, `applied_at`, `workspace_sha256` (WORKSPACE.md after this
application) and `previous_handoff`:

````markdown
---
schema_version: 1
kind: workspace-handoff
scope: {kind: workspace}
created: "2026-11-04T11:30:00.412Z"
input: {path: runs/drafts/workspace-handoff.md, sha256: ef86101f8794e9f97f4b238c0f751fd6ebf9ebd86e3a74ca990b4ad61c7dd786}
session_id: null
base_workspace_sha256: e2921083e133609ce433901d0224e4d67d57fad657f5f1417bbeb5b039440d2a
confirmed_changes: [runs/20261104T101500Z-proposal-a41c9e07d3b24f5e9b6c8d7e1f203a4b/receipt.md]
next_step: "Propose the scheduling child: question, single-queue scope and initial Brief."
source_draft: runs/20261104T113000Z-handoff-5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b/draft.md
source_sha256: e20af3052161408966e4e0a6be2eb445b6dc2f98a3315ad1bb4a852df0d99584
applied_by: "Tianchi YU"
applied_at: "2026-11-04T11:35:00.108Z"
workspace_sha256: 35d49825b6c722d158a52df64586f2e9c5828c9a4ddca9d82e3ea43cf7179bc4
previous_handoff: null
---
## Done
Discussed scheduling versus tail latency; corrected the scope to a single node.

## Confirmed changes
Direction, constraints and the synthetic trace registration were approved in this session.

## Pending ideas
- Caching as a later direction (unconfirmed).

## Open questions
- Which recorded trace could replace the synthetic one?

## Next step
See metadata next_step.
````

A handoff never applies a direction, resource or child; pending ideas remain pending. An
unapplied draft whose base no longer matches is shown as stale, not pending. Closing or archiving
a native session confirms nothing; recovery reads only the latest applied record (F10). An
orphan session record without a chain link or journal is an error and is preserved.

## 9. Child creation: input → packet → project → receipt

Input (`project propose NAME --input FILE`), under root `runs/drafts/`:

| Field | Type | Meaning |
| --- | --- | --- |
| `kind` | `project-creation-input` | |
| `project` | project name | equals NAME |
| `supersedes` | creation packet or null | |
| `question`, `motivation`, `goal`, `constraints`, `next_step` | strings | `goal`/`constraints` become PROJECT Goal/Constraints |
| `included` | nonempty list of strings | |
| `excluded`, `assumptions`, `open_questions` | lists of strings, may be empty | assumptions are unresolved by definition |
| `sources` | as in 7.1 | selected workspace material carried forward |
| `pins` | as in 7.1 | resource versions carried forward |
| `relationships` | list of `{project, note}` | existing projects only |

Body: the initial Brief, verbatim (nonempty; only qualified markers to existing projects).
The input has no Claim, Decision or display-name field, and no methodology is required.

````markdown
---
schema_version: 1
kind: project-creation-input
project: scheduling
supersedes: null
question: "Does queue scheduling policy on one serving node explain most p99 latency under bursty arrivals?"
motivation: "The workspace direction prioritizes single-node tail latency."
included: ["One request queue on one node", "Replay of registered traces"]
excluded: ["Multi-node routing", "Caching (open workspace idea)"]
assumptions: ["Bursty arrivals dominate p99 (unverified)"]
open_questions: ["Which recorded trace can replace the synthetic one?"]
goal: "Determine whether the scheduling policy on a single node explains most p99 latency under bursty arrivals."
constraints: "Single queue on one node; synthetic or recorded traces only until a measurement plan is agreed."
next_step: "Write the first proposed Claim or refine the Brief."
sources:
  - {path: runs/20261104T093000Z-activity-6b1f0c2e9a4d4e7f8c3b2a1d0e9f8a7b/activity.md, coverage: selected}
  - {path: sessions/20261104T113500Z-e20af3052161408966e4e0a6be2eb445b6dc2f98a3315ad1bb4a852df0d99584.md, coverage: full}
pins:
  - {resource: synthetic-queue-trace, revision: 1, sha256: 8a1e96927975330167f8c5bdd4c4fa142ed55b3f0f69249c143908b299fd7336}
relationships: []
---
# Research brief: scheduling

Approved initial framing; hypotheses below are unproven.

## Problem
Does the queue scheduling policy on one serving node explain most p99 latency under bursts?

## Why now

## Magnitude
Unknown; no measurement yet.

## Closest prior work

## Objections and responses

## Kill criteria

## Minimal validation experiment
Replay the registered synthetic trace under FIFO and one size-aware policy.
````

Packet: `runs/<stamp>-project-<hex>/` with `packet.md`, `input.md`, `sources/N.EXT`,
`targets/PROJECT.md`, `targets/brief.md` and `seal`, sealed and previewed exactly as in 7.2.
Header: `kind: project-creation`, `scope: {kind: workspace}`, `created`, `project`, `input`,
`supersedes`, `sources`, `pins` (full form), `relationships`, `targets` (only `path`,
`after_sha256`, `after`; the project directory must be absent). Body: `Question`, `Scope`,
`Files to create`, `Carried inputs`, `Unresolved assumptions`, `Not changed`. Propose refuses an
occupied name, an invalid generated PROJECT.md (40-line limit) or a missing related project.

````markdown
---
schema_version: 1
kind: project-creation
scope: {kind: workspace}
created: "2026-11-04T14:00:00Z"
project: scheduling
input: {path: runs/drafts/project-scheduling.md, sha256: f2085f55cf335e111a7065b28b0b602440e9e9c233cba68defec86c27575a430, snapshot: input.md}
supersedes: null
sources:
  - {path: runs/20261104T093000Z-activity-6b1f0c2e9a4d4e7f8c3b2a1d0e9f8a7b/activity.md, url: null, sha256: 470842d3f25bd50a518a3e223a348fc86a0d410174075c8d419dd044fa3447ed, snapshot: sources/1.md, coverage: selected}
  - {path: sessions/20261104T113500Z-e20af3052161408966e4e0a6be2eb445b6dc2f98a3315ad1bb4a852df0d99584.md, url: null, sha256: d6c1c673cf3d79625b681a7e8d549bd152fc1fed679afd10b27d13da5af94422, snapshot: sources/2.md, coverage: full}
pins:
  - {resource: synthetic-queue-trace, revision: 1, description_sha256: 0f3a9c8324cc380693fabbca95b48f2cda80f913fd1cbd46143cac509e3175d2, path: shared/data/synthetic-queue-trace, method: tree-v1, sha256: 8a1e96927975330167f8c5bdd4c4fa142ed55b3f0f69249c143908b299fd7336}
relationships: []
targets:
  - {path: projects/scheduling/PROJECT.md, after_sha256: 91d5995efec8fec013dad123aec45ac34f45d6f8391b9366d02230ca6fac8697, after: targets/PROJECT.md}
  - {path: projects/scheduling/brief.md, after_sha256: 044f5f9b6b858a6095a48ec0af0c07c5f1fb4ef9f494a82fe8b8e4dd443e0b31, after: targets/brief.md}
---
## Question
Does queue scheduling policy on one serving node explain most p99 latency under bursty arrivals?

## Scope
Included: one request queue on one node; replay of registered traces.
Excluded: multi-node routing; caching (open workspace idea).

## Files to create
projects/scheduling/ with PROJECT.md and brief.md (shown in targets/), the seven empty object
directories, runs/, sessions/ and runs/creation/ (provenance written at confirmation).

## Carried inputs
- runs/20261104T093000Z-activity-6b1f0c2e9a4d4e7f8c3b2a1d0e9f8a7b/activity.md (selected)
- sessions/20261104T113500Z-e20af3052161408966e4e0a6be2eb445b6dc2f98a3315ad1bb4a852df0d99584.md (full)
- synthetic-queue-trace revision 1 (tree-v1 8a1e969279753301…)

## Unresolved assumptions
- Bursty arrivals dominate p99 (unverified).

## Not changed
No Claim, Evidence or Decision is created. WORKSPACE.md and other projects are unchanged.
No native session is started.
````

Generated PROJECT.md (stage explore, no decisions, no handoff):

````markdown
---
schema_version: 1
project: scheduling
stage: explore
recent_decisions: []
next_step: "Write the first proposed Claim or refine the Brief."
last_handoff: null
---
## Goal
Determine whether the scheduling policy on a single node explains most p99 latency under bursty arrivals.

## Constraints
Single queue on one node; synthetic or recorded traces only until a measurement plan is agreed.
````

Preview: `project create NAME --from PACKET` without `--confirm`. Apply adds `--confirmed-by
ACTOR --confirm`. NAME must equal the packet's `project`. Checks follow 7.4 with the target rule
"`projects/NAME` absent". A different packet for an occupied name is refused, never replacing the
existing project (F04). Publication builds the complete child in `projects/.creating-<hex>/`
(hex from the packet directory): PROJECT.md and brief.md from the after images, the seven object
directories plus `runs/` and `sessions/` with `.gitkeep` files, and `runs/creation/` containing
copies of `packet.md`, `seal` and `sources/N.EXT` and the record below. It then renames the
staging directory to `projects/NAME` in one step and publishes the workspace receipt (`results`
list the three generated documents). WORKSPACE.md, other projects and original workspace
records are untouched.

`runs/creation/creation.md` (written at confirmation, so it carries the actor):

````markdown
---
schema_version: 1
kind: project-creation-record
project: scheduling
packet: runs/20261104T140000Z-project-c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8/packet.md
packet_sha256: bd91c7ebfcc06a6367195db4cf910190e116a8588ebb2edacf79e7ddff28f156
confirmed_by: {actor: "Tianchi YU", at: "2026-11-04T14:10:00Z"}
question: "Does queue scheduling policy on one serving node explain most p99 latency under bursty arrivals?"
motivation: "The workspace direction prioritizes single-node tail latency."
included: ["One request queue on one node", "Replay of registered traces"]
excluded: ["Multi-node routing", "Caching (open workspace idea)"]
assumptions: ["Bursty arrivals dominate p99 (unverified)"]
open_questions: ["Which recorded trace can replace the synthetic one?"]
sources:
  - {path: runs/20261104T093000Z-activity-6b1f0c2e9a4d4e7f8c3b2a1d0e9f8a7b/activity.md, url: null, sha256: 470842d3f25bd50a518a3e223a348fc86a0d410174075c8d419dd044fa3447ed, snapshot: sources/1.md, coverage: selected}
  - {path: sessions/20261104T113500Z-e20af3052161408966e4e0a6be2eb445b6dc2f98a3315ad1bb4a852df0d99584.md, url: null, sha256: d6c1c673cf3d79625b681a7e8d549bd152fc1fed679afd10b27d13da5af94422, snapshot: sources/2.md, coverage: full}
pins:
  - {resource: synthetic-queue-trace, revision: 1, description_sha256: 0f3a9c8324cc380693fabbca95b48f2cda80f913fd1cbd46143cac509e3175d2, path: shared/data/synthetic-queue-trace, method: tree-v1, sha256: 8a1e96927975330167f8c5bdd4c4fa142ed55b3f0f69249c143908b299fd7336}
relationships: []
---
Creation provenance for this project. Assumptions listed above are unresolved, not findings.
````

Idempotency: replay with a receipt returns it; a child whose `creation.md` names this packet's
seal but has no receipt is finished by recovery, never created twice. Native launch is separate:
the result prints `aoe open NAME --root ROOT`; a requested create-and-enter runs it as a second
step under the same authorization, and a failed launch leaves the child valid (F06).

## 10. Publication journal and recovery

One journal per workspace root serializes workspace changes, workspace handoffs, child creation
and adoption, under a POSIX advisory lock keyed by the root (as for project handoffs). Project
handoffs and object writers keep their own locks and are unaffected.

`.workspace-pending/` contains `intent.md` and `before/N`, `after/N` images. Intent header:
`operation` (`workspace-change`, `workspace-handoff`, `project-create` or `adoption`), `record`,
`record_sha256`, `actor`, `at`, `approval_text`, `targets` (each `{path, before_sha256,
after_sha256}`), and for `project-create` also `staging`. All files are written and synced in a
`.workspace-prepare-*` directory, then renamed into place; the rename is the commit point.

| Crash point | Visible state | Rerun of the same command |
| --- | --- | --- |
| before the journal rename | nothing applied; a prepare remnant may exist | ordinary apply; remnants are reported, not trusted |
| journal, no target written | incomplete | publishes every target |
| some targets written | incomplete | each target must equal its before or after image |
| targets written, no receipt/record | incomplete | publishes the receipt or session record |
| receipt written, journal present | incomplete | verifies, then retires the journal |
| retired, cleanup interrupted | complete | `.workspace-completed-*` remnants are ignored and removed |

Ignored by Git: `.workspace-pending/`, `.workspace-prepare-*/`, `.workspace-completed-*/` and
`projects/.creating-*/`. Readers that list projects skip dot-prefixed names and report a
staging directory named by the journal. For `project-create`, the staging directory may contain
only expected files with expected bytes;
the child is not openable as healthy while the journal exists, and status shows it as
"creation incomplete". Recovery reuses the journal's actor, time and approval text; a different
`--confirmed-by` on the rerun is reported and ignored. A target or staging file matching neither
image is an external edit: everything is preserved, nothing is rolled back, and the error names
the file and both images. There is no automatic abandon: the researcher restores one image by
hand, then reruns. Readers show completed, pending and failed effects separately.

## 11. Native binding and context scope (L3)

Bindings, snapshots and receipts are L3 operational records with no research authority.

Binding version 2 (JSON), written for every new binding:

| Field | Meaning |
| --- | --- |
| `schema_version` | `2` |
| `scope` | `{"kind": "workspace"}` or `{"kind": "project", "project": NAME}` |
| `title` | native session title at creation: `Workspace: <name>` or `Project: NAME \| <workspace name>` |
| `root`, `profile`, `agent`, `session_id`, `provider_session_id`, `context`, `token`, `fingerprint`, `manifest_sha256`, `delivery`, `known_ids`, `message` | as in version 1 |

Location: workspace `.aoe/binding.json`; project `projects/NAME/.aoe/binding.json`. A workspace
session's path must be the root; a project session's path is the root or its directory.
`context` must lie in that scope's `runs/`. Example:

```json
{
  "schema_version": 2,
  "scope": {"kind": "workspace"},
  "title": "Workspace: Serving Research",
  "root": "/home/researcher/serving",
  "profile": "toulmin-trial",
  "agent": "codex",
  "session_id": "0f1e2d3c4b5a6978",
  "provider_session_id": null,
  "context": "runs/20261104T120000Z-aoe-context-7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a29",
  "token": "7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a29",
  "fingerprint": "b7e3c1d9a5f2e8c4b6a0d3f1e9c7b5a3d1f0e8c6b4a2d0f9e7c5b3a1d9f8e6c4",
  "manifest_sha256": "c4d2e0f8a6b4c2e0d8f6a4b2c0e8d6f4a2b0c8e6d4f2a0b8c6e4d2f0a8b6c4e2",
  "delivery": "prepared",
  "known_ids": [],
  "message": "Context prepared; not yet sent"
}
```

Version 1 compatibility. Existing project bindings stay valid where they are, are updated in
version 1 form, keep the legacy creation-recovery title `Toulmin: NAME`, and are never converted
or reinterpreted as workspace bindings. Only an explicit `bind --replace` or `open
--new-session` within the same scope writes version 2. Missing workspace binding means no
workspace session yet. One `(profile, session_id)` may appear in at most one binding of the
workbench, across both versions and all scopes (F08); all bindings share the existing writer lock.

Context manifest and receipt version 2 add `scope` to the version 1 fields; version 1 archives
remain valid for version 1 bindings and are never rewritten. A version 2 binding requires a
version 2 manifest. `aoe ack` must name the same scope as the manifest, binding and token (F09).

Resident inputs and freshness:

| Scope | Resident snapshots | Fingerprint also covers |
| --- | --- | --- |
| Workspace | AGENTS.md, WORKSPACE.md, latest applied workspace handoff | that handoff's source draft; every resource description; each root packet's seal and disposition; the journal; each child's name, validity and stage |
| Child (workspace root) | AOE3 set (AGENTS, PROJECT, Brief, latest child handoff) plus WORKSPACE.md and `runs/creation/creation.md` when present | the AOE3 project fingerprint inputs |
| Child (legacy root) | exactly the AOE3 set | exactly the AOE3 fingerprint |

The child receives the workspace charter, not workspace discussion, sibling histories or
creation sources (read on demand). Independent review manifests are unchanged. Adoption adds
WORKSPACE.md to child inputs, so existing acknowledged child contexts become stale; that is
expected and reported, not an error.

## 12. Initialization and legacy adoption

`init ROOT [--name NAME]` (no `--project`): allowed on missing, empty and incomplete-init roots.
It creates the common templates, `projects/`, `runs/drafts/`, `sessions/` and
`shared/resources/` (each with `.gitkeep`) and the Git repository as today, and publishes
WORKSPACE.md last, so its presence means setup finished. On a workspace root it reports the
identity and writes nothing, without comparing edited templates. On legacy roots it refuses and
points to adoption (a legacy-looking root without projects, such as an interrupted init whose
templates were edited, is refused with the modified entries listed); on unrelated roots it
refuses and lists unexpected entries. `init ROOT
--project NAME` keeps its documented behavior on legacy and empty roots, and is refused on a
workspace root (use `project propose`/`create`).

Adoption (`workspace adopt ROOT`) is read-only for recognized legacy roots. It prints a plan and
its digest, the SHA-256 of the plan bytes. The plan contains no time or absolute path.
Schematic example (angle brackets mark digests computed at preview):

````markdown
---
schema_version: 1
kind: adoption-plan
name: "Serving Research"
creates:
  - {path: WORKSPACE.md, sha256: 3a9d405abca38945ad12898f8e3b61c79e012bc310671de496ac8e4d366d6793}
  - {path: framework/workspace-formats.md, sha256: <digest of the packaged contract>}
edits:
  - {path: .gitignore, before_sha256: <current digest>, after_sha256: <digest after edit>}
absent: [WORKSPACE.md, runs, sessions, shared/resources, .aoe/binding.json]
conflicts: []
---
## Changes
(unified diff per created or edited file, fenced as in 7.2)

## Not changed
Projects, objects, references, handoffs, bindings, context archives, tools/models.toml,
roles, global/profile.md and Git history.
````

Rules: `runs/`, `sessions/` and `shared/resources/` must be absent or empty, otherwise they are
conflicts (existing root data is never reclassified). AGENTS.md: if byte-identical to a released
template (the package lists their digests) it is replaced by the current one; if customized, the plan appends the template's
`## Workspace and project scopes` section unless a section of that name exists, which is a
conflict. `.gitignore` gains only missing journal patterns. A differing
`framework/workspace-formats.md` is a conflict. WORKSPACE.md starts as in section 4, direction
absent. A plan with conflicts cannot be confirmed.

`workspace adopt ROOT --plan-digest DIGEST --confirmed-by ACTOR --confirm` recomputes the plan;
DIGEST must equal it in full or by a unique prefix of at least 16 hex digits, else nothing is
written (stale plan). Publication uses the journal, then writes `runs/<stamp>-adoption-<hex>/`
with `plan.md` (exact plan bytes), `seal` and a `workspace-receipt` whose `record_sha256` is the
plan digest. No model, binding, context receipt or old handoff is created. Repeating with the
same digest returns that receipt; any other adopt on a workspace root reports it is configured.

## 13. Operation matrix

| Operation | Input | Output | May change | Authorization meaning | Repeat |
| --- | --- | --- | --- | --- | --- |
| init ROOT | name | workspace scaffold | new files only | administrative setup, no direction | no-op |
| activity / drafts | agent or researcher text | files in scope `runs/` | those files | none needed | free edits |
| workspace propose | change input | sealed packet | packet directory only | none; nothing confirmed | new packet each time |
| workspace apply | packet + actor + confirm | receipt | listed targets | researcher approved this exact packet | returns receipt |
| workspace reject | packet + reason + actor + confirm | receipt | none | disposition only | returns receipt |
| aoe handoff --workspace --input | handoff input | sealed draft | draft directory only | none | new draft each time |
| aoe handoff --workspace --apply | draft + actor + confirm | session record | `sessions/`, WORKSPACE `next_step`/`last_handoff` | summary accurately records the session | returns record |
| project propose | creation input | sealed packet | packet directory only | none | new packet each time |
| project create (confirm) | packet + actor + confirm | child + receipt | `projects/NAME` (new), receipt | approved question, scope and initial framing, not their truth | returns receipt |
| project reject | packet + reason + actor + confirm | receipt | none | disposition only | returns receipt |
| workspace adopt (confirm) | plan digest + actor + confirm | adoption record | planned files only | approved this exact plan | returns receipt |
| aoe open/bind/refresh/ack | scope | binding, snapshot, receipt | `.aoe/`, scope `runs/` context archives | none; operational | reuses unchanged context |

Preview forms (`apply`/`create` without `--confirm`, `adopt` without a digest) write nothing and
exit 0. One explicit approval may cover a listed bundle; the operator does not ask again for the
same exact content, and never records an approval the researcher did not give.

## 14. Errors

Every validation error names the root-relative path, the field and, when known, the line, as in
formats.md, and every refusal ends with the next safe action. Data, conflict and refusal errors
exit 1; usage errors exit 2. Required content:

| Condition | Message content | Next action |
| --- | --- | --- |
| no `--confirm` with actor | not applied; confirmation missing | rerun with `--confirm` after review |
| wrong kind or scope | expected artifact and scope, actual ones | the command that generates the expected artifact |
| seal or digest mismatch | packet/draft changed after preview | propose or draft again |
| stale target or source | path, expected and current digest | preview the refreshed proposal |
| broken pin | resource, revision, failing check | restore the material or propose a new revision |
| occupied target | path and who owns it | choose another name or inspect the existing record |
| superseded / rejected | successor or receipt path | use the successor, or propose anew |
| journal for another record | operation and record | rerun that operation's command |
| external edit during recovery | file, before and after digests | restore one image, then rerun |
| legacy or unrelated root | classification | `workspace adopt ROOT` or another directory |
| PROJECT with `--workspace` | conflicting selectors (exit 2) | choose one |

## 15. Invalid examples

Each variant changes one thing in a valid example above.

| Variant | Error |
| --- | --- |
| WORKSPACE.md with `charter_revision: 0` and a `charter_receipt` path | `charter_receipt`: must be null at revision 0 |
| WORKSPACE.md with an empty `## Direction` section | `body.Direction`: required content empty |
| WORKSPACE.md with `## Goal` | `body.Goal`: unknown workspace section |
| WORKSPACE.md containing `[[C-001]]` | unqualified reference in workspace scope |
| activity.md with `coverage: summary` and `limits: null` | `capture.limits`: required unless full and complete |
| resource description with both `path` and `url` | `location`: exactly one of path or url |
| resource description with `method: file` on a directory | `version.method`: path is a directory; use tree-v1 |
| change input targeting `projects/scheduling/brief.md` | `changes[0].target`: only charter and resource changes |
| packet.md edited after propose | seal mismatch; propose again |
| packet whose `supersedes` names an applied packet | `supersedes`: predecessor is not pending |
| receipt with `disposition: rejected` and `reason: null` | `reason`: required for rejected |
| handoff input with a `## Next step` section | `body.Next step`: generated; use metadata next_step |
| creation input with `included: []` | `included`: at least one item |
| creation input whose Brief contains `[[C-001]]` | unqualified reference; the child has no objects yet |
| binding version 2 at `.aoe/binding.json` with project scope | scope does not match binding location |
| version 2 binding whose context manifest is version 1 | manifest version does not match binding |
| `R-001.md` in root `runs/` | misplaced Run object; workspace records have no object IDs |

## 16. Acceptance traceability

The contract supplies behavior for every WS3 case; no case is passed by this document.

| Cases | Sections |
| --- | --- |
| A01 empty start | 2.1, 4, 12 |
| A02, A09 native entry, two scopes | 2, 11 |
| A03 exploration and correction | 5, 7.1, 7.3 |
| A04 direction and resource | 4, 6, 7 |
| A05, A06 workspace handoff and fresh recovery | 8, 11 |
| A07, A08 child proposal and creation | 9, 10 |
| A10 scope switching, child handoff | 2.2, 8, 11; project handoff unchanged |
| F01 missing confirmation | 7.4, 9, 12, 14 |
| F02 wrong artifact or scope | 2, 7.4, 8 |
| F03 stale inputs, unrelated edits | 7.4, 8, 9 |
| F04 repeats and occupied targets | 7.4, 7.5, 8, 9, 12 |
| F05 interrupted publication | 10 |
| F06 launch failure after creation | 9 |
| F07 native readiness | 11 (AOE3 delivery states unchanged) |
| F08 binding identity | 11 |
| F09 tampered or stale receipts | 11 |
| F10 unconfirmed closure | 8 |
| F11 scope and root selection | 2.2 |
| F12 malformed, legacy, conflicting roots | 2.1, 12 |
| F13 pinned resource failure | 6, 7.4, 9 |
| F14 partial capture, unknown identity | 1, 5 |
| L01 legacy adoption | 11, 12 |

## 17. Compatibility

- Project object v1, PROJECT.md, brief.md, project handoff drafts and records, review and
  intake files, UI1/UI2/UI-N1 archives and AOE3 version 1 bindings and context archives are
  unchanged and remain readable. No existing file is migrated; no migration script is needed.
- Older Toulmin builds ignore WORKSPACE.md and root records, reject version 2 bindings as an
  unknown version, and can open children as ordinary projects.
- Every change in this contract is additive auxiliary storage plus L2 rules for new operations.
  The meaning of scientific support, rulings and gates does not change.
