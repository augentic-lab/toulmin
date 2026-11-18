# Existing projects and source directories

**Current implementation and accepted next design.** The commands below describe the
released project-scoped onboarding behavior. On 2026-11-18 the researcher approved
[workspace-first onboarding](workspace-onboarding-design.md): intake and understanding
belong to the workspace. The accepted design supports new workspace only, new workspace
plus one explicitly requested project, and a new project in a selected existing workspace.
These design changes are not implemented and do not modify existing workspace/project data.

Onboarding creates an independent research workspace linked to local code or
project directories. It does not move, copy, initialize Git in, or change those
source directories. Git and ordinary directories are supported. The new research
child starts in `explore`, with an initial Brief and no Claim or Decision.

```sh
toulmin onboard /path/to/project --root /path/to/research --project prototype --init
toulmin decide --root /path/to/research
toulmin open prototype --root /path/to/research
```

`--init` explicitly authorizes the existing workspace initializer when the chosen
research root is missing or empty. An unrelated nonempty directory is refused.
For an existing research workspace, omit `--init`. Research and source directories
must be distinct and must not contain one another; source directory symlinks are
refused. No native session starts until the researcher separately opens it.

The first command prepares a sealed onboarding packet under root `runs/`; the
researcher applies or rejects the whole packet in `decide`. Child creation reuses
the existing project-creation contract and receipt. The generated underlying
creation cannot be applied independently: its source association and research
context belong to the same reviewed publication. Interruptions retain the existing
workspace journal; reapply the same decision to finish. An unexpected edit stops
recovery and preserves the journal rather than repairing or overwriting the edit.

## Source catalog and local paths

`sources.toml` is tracked, additive workspace data, with this version-1 shape:

```toml
schema_version = 1

[[sources]]
id = "source-example"
project = "prototype"
kind = "git"
role = "working"
identity = "git:ROOT-COMMIT-LIST-SHA256"
```

`kind` is `git` or `directory`; `role` is `working` or `reference`. Each
`(id, project)` association is unique. Multiple projects may share the same source
ID, provided its kind and identity agree. Each project has at most one working
source. Source IDs do not encode source paths. Git identity hashes the repository's
root commit list, allowing later commits and dirty working trees; repositories
need at least one commit. A separate clone can also receive a separate logical
source ID, for example when used as a distinct reference or development direction.

Absolute paths and filesystem identities exist only in ignored
`tools/sources.local.toml`:

```toml
schema_version = 1

[bindings]

[bindings.source-example]
path = "/this/machine/project"
filesystem = "DEVICE:INODE"
```

On another machine, or after moving/replacing a source directory, bind it explicitly:

```sh
toulmin source list --root /path/to/research
toulmin source bind source-example /new/local/path --root /path/to/research
```

Binding verifies the identity and non-overlap rules and changes only local mapping
data. Missing or replaced paths produce actionable errors; they never silently
fall back to a different checkout. A non-Git source has an initial bounded textual
content fingerprint, which an explicit rebind must reproduce. Ordinary opens check
its stored filesystem identity rather than requiring its contents to remain
unchanged. A changed non-Git directory therefore remains usable in place, while a
move/rebind after content changes may require restoring its original fingerprint
or onboarding a new source explicitly. Empty or text-free non-Git directories have
weaker content identities; the stored local filesystem identity still detects
replacement of the bound folder.

## Read-only discovery and its limits

Onboarding archives a bounded inventory and selected text files, never executes
source scripts, and preserves dirty and untracked source files. It skips source
symlinks, conventional secret/credential files, generated/dependency directories,
ignored files, nonregular files, binary content and large text files. Conventional
name checks are a practical exclusion rule, not a secret scanner; review the
packet's archived inventory before confirmation.

The inventory is limited to 400 files, 512,000 textual bytes and 32,000 bytes per
text file. Directory traversal and Git command output are separately bounded.
Inventory records include observed Git HEAD/status when available, file digests,
coverage and truncation. A missing inventory item does not establish absence.
These are onboarding snapshots, not a live synchronization service or formal
Evidence. Confirmed inventory files are available as historical context in native
project sessions. No source absolute path is saved into tracked packet images;
sealed pending local-binding images stay in ignored `tools/*.local.toml` files.

## Reference and working directions

The initial source is working unless an existing target is selected:

```sh
toulmin onboard /old/prototype --work-at /new/direction \
  --root /path/to/research --project prototype
```

This links `/old/prototype` as reference and `/new/direction` as working. It does
not create or populate the target. Add later directions through another reviewed
source-association packet:

```sh
toulmin source add /new/direction --project prototype --working \
  --rationale "Continue implementation in the new direction" --root /path/to/research
toulmin decide --root /path/to/research
```

Omit `--working` to add a reference. Adding a new working source demotes existing
working associations in that project to reference, after confirmation. To choose
among already associated sources:

```sh
toulmin source working prototype source-example "Return to the original checkout" \
  --root /path/to/research
toulmin decide --root /path/to/research
```

These policies do not copy, synchronize or delete files and are not filesystem
access controls. Follow each source repository's own instructions when editing.

## Structural overview

An optional confirmed `projects/NAME/overview.md` holds structural understanding:
components, entry points, current implementation, checks, known gaps and links to
code or documents. Goal and constraints remain in `PROJECT.md`; next steps remain
under the existing handoff protocol. `--overview FILE` proposes an initial overview
within onboarding. Later overview updates are reviewed separately, with frozen
before/after images and researcher receipts; optional Goal/Constraints changes are
published atomically in the same decision. Stages and scientific rulings cannot
be changed through an overview proposal. The proposal archive retains its exact
history and rejects stale targets.

## Compatibility and validation status

All files are additive. Existing workspaces without `sources.toml` keep their
legacy behavior. Existing object, Brief, charter and creation schemas are unchanged;
no migration script is required. The source catalog and local bindings have strict
version-1 validation; malformed files are reported without silent repair. Existing
workspace ignore rules already cover `tools/*.local.toml` and the publication
journal. Do not manually add local mapping or pending local-image files to Git.

Temporary-fixture automated tests cover inventory safety, dirty preservation,
reviewed creation, source sharing, missing paths, explicit rebind, stale/tampered
packets, interruption/recovery, overview history and source-direction changes.
These tests are technical evidence, not researcher usability acceptance or a live
provider acceptance ruling.

## Native sessions and migration records

A linked project opens directly at its working source; Toulmin supplies the research
workspace with the native CLI's additional-directory option. Existing native permissions
remain in force unless the researcher explicitly selects the project-local Codex
workspace-write launch policy below. A source session uses a v3 binding: v2 fields plus `cwd`, `source_id`,
`source_identity` and `cwd_identity` (filesystem device/inode). Old v1/v2 sessions keep
their old shape when no working source is selected. Changing the source or replacing the
checkout requires an explicit session replacement; refresh never silently redirects it.
Cross-profile live-session checks prevent Toulmin from starting a second writer on the
same checkout. This is coordination, not filesystem isolation.

### Codex permissions for code and research records

The first **new** external-source Codex session offers a one-time choice in your
interactive terminal. It names both directories: the working source (native cwd)
and the research workspace (`--add-dir`). Answering yes saves `workspace-write`,
requesting write access to both; no or Enter saves `inherit`, preserving native
settings. Canceling the question creates neither a policy nor a session.
The question holds no workspace or checkout lock. Before saving or launching,
Toulmin reacquires the locks and rechecks the binding/session, source catalog,
directory identities and local policy. If another operation changed them while
you were choosing, this open refuses without overwriting that operation's choice
or creating a duplicate session; retry `open` against the current state.

Without an interactive terminal, an unknown or stale choice stops before launch
and prints the two paths and these explicit options:

```sh
toulmin open prototype --root /path/to/research --agent codex \
  --codex-sandbox workspace-write
# Or retain native settings, including restrictive settings that may reject --add-dir:
toulmin open prototype --root /path/to/research --agent codex \
  --codex-sandbox inherit
```

Both options also work with `toulmin aoe open`. Once selected, omit the flag:
`toulmin open prototype --root /path/to/research`. Reusing an existing binding
keeps its actual native arguments, including manually configured ones. An explicit
permission flag on a bound session is refused: a saved preference does not prove
what permissions that existing session has. To select another launch policy,
inspect and archive the old session yourself in AoE, then explicitly replace it:

```sh
toulmin open prototype --root /path/to/research --agent codex \
  --new-session --codex-sandbox workspace-write
```

Replacing a live session is refused. With no permission flag, `--new-session` uses
the saved choice for that project and directory pair. An opted-in launch forwards
`--sandbox workspace-write --add-dir /path/to/research` through AoE's persisted
`--extra-args`. AoE retains these arguments for subsequent native resume/restart;
Toulmin does not restart or reconfigure an existing session to change permissions.
The source cwd is never redirected. Sibling projects do not inherit this choice.

Choices are local execution settings in ignored `tools/native.local.toml`, outside
formal research objects and context archives. For example, the CLI generates:

```toml
schema_version = 1

[projects.prototype]
sandbox = "workspace-write" # or "inherit"
records_root = "/path/to/research"
records_identity = "DEVICE:INODE"
source_id = "source-example"
source_identity = "git:ROOT-COMMIT-LIST-SHA256"
cwd = "/path/to/code"
cwd_identity = "DEVICE:INODE"
```

Prefer the CLI to construct these identity fields. Moving or replacing either
directory, or selecting another working source, makes the saved choice stale;
review the displayed paths and choose again explicitly or in the terminal. Existing
source and binding guards still require explicit session replacement. Malformed,
unknown-version and symlinked policy files are refused without repair or overwrite.
Correct an invalid file before retrying. Do not commit or share this machine-local
file; existing `tools/*.local.toml` ignore rules already cover it.

This changes no global Codex or AoE settings, approval policy, trust entries or
research rulings. Native trust/update prompts still require your input. Managed
restrictions can refuse `workspace-write`; Toulmin reports the refusal, including
errors above blank rows in a dead pane, and never retries with broader access.
Inspect the native/managed configuration before another explicit replacement.
Startup and attaching are not context delivery: resolve prompts yourself, then run
the printed `toulmin aoe refresh` command and check the context-read receipt separately.

Claude, non-source sessions and v1/v2/v3 binding formats remain compatible. Existing
bindings need no migration. Direct Python application callers retain inherited
native behavior when no policy or choice callback exists; a saved policy is applied
only when creating a session. Automated fixtures cover policy/recovery behavior;
installed-provider resume/restart and researcher usability acceptance remain pending.

Use `toulmin draft overview NAME`, fill the draft, and run the printed `toulmin overview`
proposal command. Confirm it with `decide`. An applied overview and source snapshot are
restored with the applied handoff; the latest 8 KiB of notebook text is labeled unconfirmed
and explicitly marked when truncated. The source card shows observed Git state separately
from the catalog's version. Archived source inventories remain historical snapshots.

`migration draft NAME` creates an editable batch description under runs/drafts. Record
source/target IDs and versions, selected items, differences, check outputs and the outcome
(`passed`, `failed` or `partial`). `migration record NAME --input FILE` previews it;
`--confirm --confirmed-by NAME` publishes an immutable receipt keyed by the input digest.
Repetition does not duplicate the receipt. It neither runs checks nor grants a verified
Evidence grade, and it never copies or deletes source material.

The implementation trial on 2026-11-17 created disposable Codex and Claude AoE sessions at
the correct external directories. Codex exited because its effective permission settings
refused `--add-dir`; Claude awaited its native folder-trust choice. Neither provider trial
reached context acknowledgment or a development/handoff cycle. No trust prompts were
accepted automatically and no permission defaults were changed. Both test sessions were
moved to AoE trash; full native usability acceptance remains pending. For Codex, use the
project-local `--codex-sandbox workspace-write` choice above on a new/replacement launch; for
Claude, review its folder trust prompt in AoE before refreshing the prepared context.
