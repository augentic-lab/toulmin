# L1 file contract v1

Status: skeleton contract frozen in T1, following TODO.md Q1–Q9 recommendations and the user's authorization to continue.
This document defines the v1 format. T1 implements IDs, references and session read order; T3 implements file encoding/decoding, object fields and direct-reference validation.
English machine fields are authoritative. Neither Python classes nor the CLI may redefine their meaning.

## Files and identifiers

- Use UTF-8 and LF. The first line of an object file must be `---`; the next standalone `---` line ends the YAML header. All remaining bytes form the Markdown body, which must not be rearranged when read or written back.
- The YAML header is a mapping accepting only strings, booleans, integers, finite floats, null, lists and string-keyed mappings. Reject duplicate keys, explicit tags, anchors/aliases, merge keys and multi-document headers. Never construct Python objects.
- Every object requires integer `schema_version: 1`; booleans do not count as integers. Reject unknown versions without automatic migration. Reject unknown fields; custom data belongs only in optional `extensions` mappings with `namespace.name` keys.
- Date/time fields are quoted RFC 3339 strings with time zones; generated values use UTC `Z`. Do not rely on YAML date conversion. Example: `"2026-10-31T10:00:00Z"`.
  Since U3, generated object timestamps use second precision and generated headers list fields in this contract's order without line folding. Handoff draft/record timestamps keep sub-second precision because drafts are identified by content digest. Readers accept fractional seconds and any key order, so older files need no migration.
- Project names consist of lowercase ASCII letter/digit segments separated by single hyphens, such as `tail-latency`. Slashes, dots, spaces and empty segments are forbidden.
- Number each of the seven object types within its project, starting at 1 with at least three digits: `C-001`, `C-999`, `C-1000`. Reject aliases such as `C-1`, `C-000` and `C-0001`.
- Filenames must be the ID plus `.md` in the corresponding type directory. Deletion is not a normal operation: retain old objects and do not recycle used IDs. Concurrent creation must allocate exclusively or fail with an explicit conflict.
- References use `C-001` or `other-project/C-001`. Resolve the former within the current project and the latter within the same workbench root. Absolute paths, `..` and symlink escapes are forbidden.
- Machine-recorded file paths are relative to the workbench root and use `/` separators. External sources use separate URL fields, never local-path fields.
- Do not maintain a duplicate ID index in object files. Repository validation checks reference existence/type and source-file existence; string parsing alone does not.

| kind (new argument) | Prefix / directory | Initial status | Readable statuses |
| --- | --- | --- | --- |
| claim | C / claims | proposed | proposed, challenged, supported, accepted, refuted |
| evidence | E / evidence | valid | valid, invalidated |
| objection | O / objections | open | open, answered, accepted, deferred |
| decision | D / decisions | active | active, superseded |
| exploration | X / explorations | pending | pending, adopted, dropped |
| spec | S / specs | todo | todo, in-progress, awaiting-acceptance, passed, failed |
| run | R / runs | Explicit completed or failed | completed, failed |

The ID prefix and directory determine the object type; do not add a metadata `kind`. Evidence's `kind` field refers specifically to the evidence category.
Archive Runs after the manual model session ends; never invent running/completed outcomes. Raw output goes in `runs/YYYYMMDDTHHMMSSZ-name/` (valid UTC timestamp, ASCII alphanumeric/underscore/hyphen name); Run metadata goes in `runs/R-001.md`.
Drafts use only Run-local labels and receive object IDs upon confirmed intake into formal directories.

## Common fields and provenance

Every object requires `schema_version`, `id`, `status`, `created`, `source` and `confirmed_by`.
All non-Run objects may have `decisions` (a list of Decision references, empty by default). All objects may have `extensions`.

`source` must be exactly one of the following forms, without mixed or missing fields:

- Human-authored/human-archived: `{kind: human, actor: "Tianchi YU"}`; actor is a nonempty attribution.
- Derived from a model Run: `{kind: run, ref: R-001, path: "projects/demo/runs/20261031T100000Z-review/output.md"}`.
  ref must identify a Run; path must exist under that Run.output. Trace model, role and session through the Run rather than duplicating fields that could drift.

`confirmed_by` is `{actor: "Tianchi YU", at: "2026-10-31T11:00:00Z"}`, recording human confirmation of intake, not authentication.
Runs themselves are archived by a human, so their source must be human and cannot self-reference. Run metadata records model, role and session_id.
All strings must be nonempty after trimming, except explicitly permitted empty sections and null fields. Validate each list element against its specified type.

## Type-specific fields and body

Use the unique level-two headings specified below. Required sections must contain nonempty content; section names are case-sensitive and must not repeat.
Store Claim statements, Objection content and similar body content only once, never again in metadata. The program does not infer that a conclusion is established from free text.

| Type | Additional required metadata | Optional or conditional fields | Required body sections |
| --- | --- | --- | --- |
| Claim | `type`, `importance` | `tags: list[str]`, empty by default; `validation_plan: str`; `decisions` | `Statement` |
| Evidence | `target: Claim reference`, `direction`, `kind`, `grade`, `provenance` | `verification` required when grade=verified | `Material`; also `Invalidation` when invalidated |
| Objection | `target: Claim reference`, `severity` | `decisions` | `Content`; retain `Response` and `Ruling`, initially allowed to be empty |
| Decision | Nonempty `related: list[object reference]` | `superseded_by: Decision reference` required when superseded | `Context`, `Choice`, `Rejected alternatives`, `Rationale` |
| Exploration | `lens: str` | `adopted_as: Claim reference` required when adopted | `Content`; also `Rationale` when dropped |
| Spec | `target: Claim reference` | `evidence: list[Evidence reference]`, empty by default, nonempty when passed | `Requirements`, `Acceptance criteria` |
| Run | `model: str`, `role: str`, `input_files: list[str]`, `output: str`, `session_id: str or null`, `duration_seconds: nonnegative number or null` | input_files may be empty; use null for unknown session/duration, never guesses | `Summary`; also `Failure` when failed |

Enums and nested fields:

- Claim.type: problem, magnitude, mechanism, novelty, assumption, deployability. Use tags for workload/hardware rather than adding types.
- Claim.importance: core, secondary. Represent G2's pending validation with a nonempty `validation_plan`, not a new pending Claim.status.
- Evidence.direction: supports, refutes; kind: measurement, literature, derivation, experiment, computation; grade: verified, model-asserted, intuition.
- Objection.severity: fatal, major, minor.
- Evidence.provenance: a nonempty list of records, each with a nonempty `description` and exactly one of `path` or `url`. Paths must exist. URLs must use http/https; the skeleton does not verify their content over the network.
- Evidence.verification: `{method: str, result: str, artifacts: list[str]}`; artifacts must be nonempty and files must exist. Structural completeness proves only that a verification record was supplied, not that the scientific conclusion is correct. The researcher still confirms the evidence grade.

Conditional rules: answered Objections require a nonempty Response; accepted/deferred require a nonempty Ruling, and accepted also requires a Decision reference.
Accepted/refuted Claims must reference at least one Decision; a refutation decision should explain the refuting evidence or accepted objection.
Superseded Decisions retain their old body. Never automatically delete invalidated evidence or rejected explorations.

## PROJECT.md and brief

PROJECT's YAML header requires `schema_version: 1`, `project`, `stage`, `recent_decisions: list[Decision reference]`, `next_step: str` and `last_handoff: str or null`.
Stage values: explore, critique, brief-final, build, accept, done. Template defaults: explore, recent_decisions=[], last_handoff=null.
The body requires `Goal` and `Constraints`. Keep the file within 40 lines; report excess length rather than truncating handwritten content.
`last_handoff` is a filename under sessions, pointing only to a confirmed applied handoff, never a draft. Retain an abandoned project's stage and record the reason in a Decision; do not invent an abandoned stage.

Write the brief by hand, with Problem, Why now, Magnitude, Closest prior work, Objections and responses, Kill criteria and Minimal validation experiment sections.
Explicit object references use `[[C-001]]` or `[[other-project/E-001]]`. Check only these markers' syntax and object existence; markers in code blocks are not references.
Other Markdown links and natural language fall outside the skeleton's consistency checks.

## Handoff drafts and applied records

Drafts are not an eighth research object type. Save them in separate archive directories under runs, with schema_version, project, session_id (null if unknown), created,
`base_project_sha256`, `recent_decisions` and `next_step`. Body sections: Done, Decisions, Open questions, Next step.
recent_decisions may reference only existing researcher decisions; an empty list means no new decisions are included. next_step is the sole next-step text applied to PROJECT; the body Next step points to that field to avoid duplicate facts.
Draft directories use runs/YYYYMMDDTHHMMSSZ-handoff-<random-value>/, with filename draft.md.
Applied records retain every draft field and the body, adding source_draft (root-relative path), source_sha256, applied_by, applied_at, project_sha256 and previous_handoff (previous handoff filename, null for the first).
source_sha256 hashes the original draft's complete bytes. project_sha256 hashes PROJECT at application time for historical traceability; later manual edits need not match it.
After application, PROJECT.last_handoff points to sessions/YYYYMMDDTHHMMSSZ-<full-draft-SHA256>.md; the UTC time is the first confirmed application time.
Identify repeated application by the full content digest. Even when a later handoff exists, never rewrite the old record or revert PROJECT.
Replay must also find the record through PROJECT.last_handoff/previous_handoff. An orphan session does not prove both public files were updated; without a recovery intent, preserve the files and report an error.
T5 replaces the previously planned random session suffix with a content digest to locate applied records without an index. No existing formal handoff data needs migration; object v1 fields/version are unchanged.

Input summaries permit only optional session_id, recent_decisions and next_step metadata; the body requires Done, Decisions and Open questions.
The command adds the sole Next step section with fixed text `See metadata next_step.`. Without input, the first three sections explicitly record unknown information, session_id=null,
recent_decisions=[], and next_step inherits the current PROJECT value. This does not assert that the session actually made no decisions.

## Handoff recovery records (internal files)

Before application, save complete before.md, after.md, session.md, draft.md and intent.md under the project's .handoff-pending/.
The intent header contains schema_version, project, session_filename and the four images' <name>_sha256 values. These are recovery records, not an eighth research object type.
Write and fsync each complete file before publishing the journal, then publish the session and atomically replace PROJECT. Only recent_decisions, next_step and last_handoff may change; the body and other fields must match.
Recovery checks checksums and current PROJECT bytes, accepting only the exact before or after image. Otherwise preserve every recovery record and report a conflict.
After both public files are complete, atomically rename the journal to retire it before cleanup, so interrupted cleanup cannot leave a partial pending journal. The research workbench .gitignore excludes journals.
POSIX flock coordinates handoff writers using a lock file in the system temporary directory. Process death releases the lock automatically; retain the file to avoid inode races.
POSIX file/directory synchronization is a local implementation requirement of L1 file storage. Models and protocols depend on no specific CLI.

## Errors and compatibility

Syntax/field errors must include the file path and field name, with a line number when available. Never skip corrupt files and then declare the entire project valid.
Reading permits all valid stored statuses; new creates only initial statuses (Runs must explicitly state their outcome). The researcher rules on status changes and records a Decision.
Do not import old drafts lacking schema_version. This repository has no persisted v0 research objects, so no data migration script is needed for this revision. Future version changes require an impact assessment and migration scripts for existing data.

T3 implementation notes: new takes a draft inside the workbench, containing source, type-specific fields and body, without id, created or confirmed_by.
schema_version may be omitted or set to 1; status may be omitted except for Run outcomes. new permits only initial statuses.
Intake assigns an ID and UTC creation time and records the confirmer without changing the original draft. Explicit --confirm and --confirmed-by record an authorization declaration, not authentication.
A project-level temporary directory lock coordinates creation. Fail explicitly if it exists; do not delete another session's lock. After fsync, publish the complete file through an exclusive hard link, never overwriting existing objects.
new validates the candidate's direct references and Run source, without recursively traversing a potentially cyclic network. Whole-project diagnostics belong to T4. Submitting the same draft again allocates a new ID without overwriting prior records.
This clarification covers only the draft interface and archive naming, without changing existing object fields/version. No actual research data in the repository needs migration.

See [format-examples.md](format-examples.md) for seven valid examples and an invalid variant of each.
