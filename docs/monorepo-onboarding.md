# MI1: bounded monorepo onboarding

The researcher authorized this minimal adaptation on 2026-11-18, followed by Mode A
preparation for an NPU race-analysis workspace. This document defines the implementation
scope; source registration and shared understanding still require review of the exact packet.

## Scope and command

Keep the actual Git root as source identity, checkout, native working directory and Chief
repository. Select an ordered set of literal repository-relative file/directory prefixes
for inventory using repeated `onboard --include PATH`, with optional repeated `--exclude
PATH`. These choices limit observation, not source writes, permissions or research meaning.
Branches remain ordinary Git history; this feature does not create projects from branches.

```sh
toulmin onboard /path/to/repository --root /path/to/records --init \
  --include component/README.md --include component/src --include component/tests \
  --exclude component/tests/generated
```

Prefixes are literal existing paths, not glob or Git-magic expressions. Include order
sets priority under the existing budgets. Paths must be relative, nonempty, normalized,
without traversal, symlinks, control characters or Git pathspec magic. Selected paths
must remain inside the repository. Exclusions need includes. Focused directory sources
and combining explicit inspection flags with `--work-at` are refused in this slice;
unfocused A/B/C and existing `--work-at` behavior remain available.

## Persistence and compatibility

The source catalog remains schema version 2. Existing definition revision 1 retains
exactly its existing fields, canonical hash and rendering. Git-only definition revision
2 adds `inspection = { include = [...], exclude = [...] }`. The definition remains
immutable under existing packet rules, and its hash binds the policy through existing
catalog, overview, native-context and task pins. Omitted flags inherit a registered
definition's policy; explicitly different flags refuse rather than silently revise it.
An existing unscoped definition is not silently promoted to a focused definition.

Inventory schema 2 stays unchanged. Its coverage/exclusions disclose literal selection,
priority and all truncation/budget limits; machine replay takes the policy from the pinned
definition, not parsed prose. Approval rescans use the sealed after-image definition.
Later understanding updates, status freshness, native context and task draft/approval use
the registered policy. Whole-repository task cleanliness checks remain whole-repository.

Old data requires no migration. Older readers reject revision-2 definitions explicitly;
they must not reinterpret them as unscoped sources. Old definition hashes and archived
inventories remain valid. No object, gate, native binding or task schema changes are needed.

## Bounded enumeration

Replace full-output `git ls-files` capture with NUL-record enumeration bounded by time,
candidate count and filename bytes. Stop and reap the process when a budget is reached;
retain complete observed records and report truncation. Preserve the 400-file, 512,000-byte
text, 32,000-byte per-file and 3,200-candidate limits. Keep independent Git time/output
bounds for identity and status. No remote, lazy fetch, hooks, fsmonitor, source scripts or
models run during inspection. Git discovery failure must not reinterpret a Git checkout
as an ordinary directory. Shared enumeration also fixes legacy binding inspection.

## Executable acceptance

1. Revision-1 catalog bytes/hashes and existing A/B/C tests remain unchanged. Strict
   revision-2 policies round-trip and reject malformed, escaping or unsupported selections.
2. A large synthetic Git tree whose filename list exceeds 2 MB yields a bounded inventory;
   explicit selection reaches the intended component and respects order/exclusions. Source
   bytes, branch and Git index are unchanged. Budget exhaustion is visible, not a full scan.
3. Mode A prepares a sealed packet with zero projects and root-based identity plus policy.
   Approval uses the same policy, rejects changed selected files/policy and creates no native
   session. Bad selections fail before initialization. Reuse inherits or rejects disagreement.
4. Understanding updates, status, fake native contexts and task preparation retain the same
   selection. Changes outside the selected files still affect global HEAD/dirty observations;
   a dirty repository cannot submit a Chief task merely because the changed file is excluded.
5. Run focused and full regression/static checks. Inspect the real TaPS source read-only,
   then initialize `/home/tianchi/workspace/npu-race-research` and prepare its Mode A packet
   with a bounded, explicitly qualified overview for researcher confirmation. Preserve the
   original repository, branches and code; no real benchmark or paid review is part of MI1.

## Real workspace framing

Goal supplied by the researcher: static race detection for NPU kernels, reusable tools
primary and publications secondary. Ascend is the current validation platform, not the
long-term scope limit. TaPS is the existing implementation. Include its README, current
design/limitations, CLI, core code and representative tests in that order; retain bulk
benchmarks/results as referenced assets. Start with zero projects, and derive independent
questions later. This is source/context onboarding, not authorization to refactor TaPS,
change implementation languages, implement a new engine or launch an evaluation campaign.

MI1 boundary checks: filename enumeration clears inherited Git pathspec switches so
selection stays literal. Legacy source-change packets accept only v1 catalogs and
cannot downgrade v2 definitions or discard inspection policy; legacy overview updates
remain compatible. No permission or source-selection authority is added.
