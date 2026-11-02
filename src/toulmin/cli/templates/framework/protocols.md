# L2 skeleton protocols v1

This document refines design sections 6–8 to unify draft permissions, human rulings and stage mappings.
CLI use, Python calls and manual editing follow the same protocol. T1 provides the read-order function; T2–T5 implement init, new, status and handoff. Stage acceptance is an explicit researcher ruling on recorded trial evidence.

## Entry and exit

1. Read the workbench AGENTS.md.
2. Read projects/<project>/PROJECT.md, then the sessions file named by last_handoff. State explicitly when a new project has no handoff.
3. State the session's single task, role, inputs and output location. Read only relevant objects, not the project's entire discussion history.
4. After the task, archive research drafts/raw output in runs, recording model, role, inputs, time and the session ID if available.
5. Draft a handoff. After researcher review and confirmation, write sessions and update PROJECT's recent decisions/next_step/last_handoff. Stage changes require a separate explicit ruling.
6. Inspect the diff and commit with related object IDs in the message. Do not push automatically. If identity or permissions are missing, preserve the content and report the failure.

The PROJECT/last_handoff read order above applies to interactive work/resumption. Independent task sessions give priority to their role's input/exclusion list:
reviewers load only AGENTS, the role contract and specified brief/Claims, never handoffs or discussion history. T5 makes this exception explicit to resolve the conflict between general entry rules and review independence.

Research workbench session state lives in PROJECT + sessions; this software development repository uses PROGRESS + TODO. Do not mix the two.

## Permissions and confirmation

Reviewers read the brief, relevant claims and their role contract, excluding creation discussions and other reviewers' output. They never rewrite objects.
Read-only model sessions emit research drafts through terminal output, which the operator saves in runs. Read-only does not require the model to write archive files itself.
Research drafts from scribes, expanders and development leads also go to runs first; sessions/explorations/specs in the role table are their destinations after confirmation.
Implementers change only the authorized code repository and archive test reports first. They must not revise acceptance criteria or rule passed themselves.

Human invocation of new or explicit confirmation parameters records confirmed_by; model-derived content must also identify a traceable Run.
Confirmation fields are not authentication. A model must not supply a researcher's name as if that grants authorization. Merely reading a draft is not confirmation.
Initial object creation differs from changes to stored status: the skeleton has no automatic ruling and never adopts model suggestions automatically.
When manually changing an existing status or project stage, the researcher creates a Decision and links the changed objects/PROJECT.recent_decisions.

Draft skeletons (U1): `toulmin draft <kind> <project>` writes a commented skeleton to `runs/drafts/<kind>-<UTC>[-name].md`, never overwriting and never creating a formal object.
Skeleton values that need human input contain `<fill: ...>`. Intake rejects any draft whose header values or body still contain that marker, reporting the field, so an unedited skeleton cannot become an object.
A default confirmer may come from the operator's `TOULMIN_ACTOR` environment variable when `--confirmed-by` is omitted; it is local operator configuration, not workbench state. `--confirm` remains mandatory.
This L2 change adds a draft location and an intake precondition only; object fields and the v1 format are unchanged.

Confirmed rulings (U2): `toulmin rule <project> <ID>` records the researcher's explicit choice on one object in that project; it never selects a status itself.
Every status change requires `--decision` naming an active Decision whose `related` list includes the object; the reference is appended to the object's `decisions` once. Run outcomes are immutable.
Text from `--response`, `--ruling` or `--section Invalidation|Rationale=FILE` is added to that section: an empty section is filled, a nonempty one keeps its text and gains the new text after a blank line, and a missing reason section is appended. Nothing is deleted.
Text alone (for example a Response without a status change) needs no Decision. The result must pass the same formats.md conditional rules as any stored object, or nothing is written.
The update preserves YAML comments, field order and every other body byte, holds the project creation lock, refuses to write if the file changed meanwhile, and replaces the file atomically. Afterwards the command prints status notices for the object and its target Claim.
Reference fields that some statuses need (Exploration adopted_as, Decision superseded_by, Spec evidence) are still edited by hand; rule reports them as missing rather than inventing values.
This L2 change adds a write path for researcher rulings only; object fields and the v1 format are unchanged.

Claim revision (R1): revise a Claim by superseding it. Create the successor with new, write a Decision whose `related` lists both Claims, then run `rule <old> --status superseded --superseded-by <new> --decision <D>`.
The successor must be a current (non-superseded) Claim in the same project. `superseded` is final for rule; correct a mistake by hand with a Decision. Fix typos in place; supersede whenever a change could alter what existing Evidence or Objections mean.
Nothing is retargeted: open Objections stay open until ruled (usually accepted, "claim revised") or re-raised against the successor, and Evidence on the old Claim does not count for the successor.
status lists revision chains under `Superseded:`, leaves superseded Claims out of condition checks, and adds notices for every dependent Objection, Evidence, Spec, adopted Exploration and brief reference. Cycles and foreign successors are data errors.
rule also sets other status-required links with a Decision: `--superseded-by` (Claim or Decision), `--adopted-as` (Exploration) and `--evidence` (Spec, appended). It never replaces or removes an existing link.

Review intake (C1): `toulmin intake <project> <raw-output> --take LABEL[:SEVERITY] --reject LABEL=REASON --partly LABEL=O-NNN --confirm` applies the researcher's choices for drafts in one archived review (formats.md, review draft blocks).
Nothing is taken by default; unlisted drafts stay pending and status reports them once an intake record exists. The raw output must belong to exactly one archived Run. Every choice is validated (labels, targets, severities, reasons, partly sources, confirmation) before any write.
Under the project creation lock, each taken draft becomes an open Objection and its outcome is appended to intake.md atomically. A replay reports `already-<outcome>` for recorded labels, never changes an outcome, and reuses an Objection created from the same draft before an interruption instead of creating another.
The intake does not rule on anything: Objection status, Claim status and gates still change only through rule with a Decision. This L2 change adds a write path for confirmed drafts; object fields and v1 are unchanged.

Role inputs (C2): `toulmin inputs <project> <role> [--claim C-NNN]...` prints the files a session of that role receives, resolved from its manifest: literal paths must exist, wildcard matches are regular files (no symlinks, no dotfiles) in natural order, and duplicates appear once.
Superseded Claims are left out and named on stderr. An explicit `--claim` selection replaces the full Claim set; every selected Claim must be current and inside the manifest. `toulmin draft run <project> --role <role> [--claim ...]` writes the same list into the Run draft's role and input_files.
Personas (`reviewer-skeptic`, `reviewer-industry`, `reviewer-theorist`, `reviewer-why-not-x`) extend roles/reviewer.md and include it in their inputs; the synthesizer's raw review outputs are named per invocation, not in its manifest. This L2 change computes inputs only; it invokes no model.

## Claim conditions and stored status

- has_open_objection: at least one open Objection targets the Claim.
- eligible_for_supported: at least one valid + verified + supports Evidence item exists, with no open fatal/major Objection.
- An open minor objection may coexist with eligible_for_supported. status reports both facts without choosing challenged or supported.
- accepted requires supported conditions and a researcher Decision; refuted requires a researcher Decision explaining refuting evidence/accepted objections.
- refutes Evidence does not count as support. invalidated Evidence does not participate. model-asserted/intuition alone cannot satisfy support conditions.
- An accepted Claim that loses evidence retains its historical status and receives an inconsistency notice, never an automatic downgrade. Unmet status conditions are ruling diagnostics; syntax errors, illegal statuses and broken references are data errors.

## Stages and gates

Explore → G1 → Critique → G2 → Brief final → G3 → Build → G4 → Accept → G5 → Done.
Spec is an artifact prepared before G3, not a separate stage. G1–G5 conditions follow the table in design section 7.
Record G2's missing-evidence plan as a minimal validation experiment in Claim.validation_plan, not a nonexistent pending Claim status.
Skeleton status reports facts and conditions without automatic gate decisions; handoff does not advance stages.

## Four command contracts

All project commands accept `--root <research-root>`, defaulting to the current directory. Supply project explicitly; never guess by scanning.
Success exits 0, data/file/conflict errors exit 1, and argument-usage errors exit 2. Suggestions or pending-ruling notices alone do not make valid data fail.
Errors go to stderr and results to stdout. By default, commands request no network access, invoke no models and make no Git commits.

| Command | Input and output | Write boundary |
| --- | --- | --- |
| init <root> --project <name> | Initialize templates/project and a Git repository, without committing | Create missing items; identical templates are unchanged and conflicts rejected; adding another project does not rewrite global files |
| new <type> <project> | Complete draft and human confirmation; return new ID/path | Create one formal object only; archive AI drafts first and reject existing targets; no placeholder “valid objects” |
| status <project> | PROJECT, relevant objects and explicit brief references; return summary/diagnostics | Entirely read-only, including no cache/index writes or mtime updates |
| handoff <project> | Generate a reviewable draft from supplied session content | Write only runs by default; --apply <draft> writes sessions and non-ruling PROJECT fields only after confirmation |

init preflights every planned target before writing. Existing files must match their templates; otherwise report a conflict and write none of the planned files.
Other projects are outside the plan and retain their changes; global templates still undergo conflict checks. Even mtime is unchanged for identical files.
Publish complete files exclusively and roll back this invocation's additions on ordinary I/O failure. Forced termination does not guarantee transaction completion; inspect remaining files before retrying.
Reject all directory symlinks; the only planned link is CLAUDE.md → AGENTS.md. Git is used only for local init, without commits or model calls.
Gemini settings use `context.fileName`; see the [official configuration reference](https://geminicli.com/docs/reference/configuration/).

T3's new interface takes a complete Markdown draft file (--input, relative to --root), requiring --confirm and --confirmed-by.
Missing confirmation, incomplete data or invalid references causes failure and preserves the draft. Create only initial statuses; Runs must explicitly specify completed/failed and failed records are retained.
If a project creation lock exists, retry after operator coordination rather than removing it automatically. After forced termination, inspect complete objects, temporary files and the lock before deciding how to recover.
This refines the L2 intake implementation without changing human ruling authority or entry/exit order.

T4's status reads only the selected project's PROJECT, seven object directories and brief, validating those records' direct references.
For external-project references, load only the explicitly targeted objects; do not scan other objects or discover incoming evidence/objections from other projects. Condition counts use valid records in the selected project only.
Sort open objections by fatal/major/minor then numeric ID; sort Claims by numeric ID. Present the two conditions independently without rewriting status or stage.
Any data/layout/reference error or creation lock causes exit 1 and unknown conditions. Readable statuses and partial counts remain visible, but counts do not represent the complete network.
On valid data, a mismatch between conditions and stored status is only a pending-ruling notice and exits 0. Create no caches, indexes or temporary files, and do not modify Git.
Check literal [[reference]] markers in brief, reporting invalid/missing/unclosed references. Skip fenced code and examples indented by four spaces/a tab.
This is reference-integrity checking, not proof of scientific correctness or semantic consistency between prose and the network.
This L2 revision clarifies scope and incomplete-data reporting without changing fields, human ruling authority or gates.

handoff saves the raw PROJECT byte digest when generating a draft. If the digest differs before application, refuse to overwrite and require a new draft based on the current file.
Application preserves Goal/Constraints and other body content/metadata, adds this session's existing Decision references, and updates next_step and last_handoff. Changing stage is forbidden.
Without input, handoff explicitly records unknown content rather than inferring session activity. --input accepts a complete human/model summary and still creates only a runs draft.
Application and recovery require --apply <root-relative-draft-path> --confirmed-by <researcher> --confirm; confirmation is an operator declaration, not authentication.
Persist the first confirmed payload, confirmer and time in .handoff-pending/ before writing. Recovery of the same draft reuses that intent without changing confirmation records.
Retire the recovery journal only after publishing the complete session and atomically replacing PROJECT. After forced termination, rerun the same --apply command. Different drafts, corrupt journals or external PROJECT edits cause explicit errors and preserve the files.
Repeated application returns only a record linked into current handoff history. Even with a newer handoff, it never reverts state; an orphan session's existence alone cannot prove completed application.
status checks last_handoff and its archived draft; replay validates the traversed application history. Changes to those records/drafts cause errors, without scanning unrelated history.
The two-file update is not one filesystem-atomic operation. While pending, status reports incomplete data rather than definite conditions.
Hash checks provide optimistic concurrency protection. Pause manual PROJECT editing during application; external editors do not participate in handoff's POSIX write lock.
T5 handoff writes require POSIX flock, hard links, atomic rename and file/directory fsync, with no models, networking or automatic Git commits.
This L2 change defines input differences between interactive and independent sessions and executable confirmation/recovery/replay protocols, preserving human authority over gates.

## Stage acceptance

Pass command integration tests first. Then run a research idea through Claim writing → independent manual review → confirmed Objection → handoff → a fresh session that recovers state from files alone.
The researcher decides what trial evidence suffices and rules on acceptance. Stage 2 was accepted on an agent-run trial with fresh-context sessions; record what any accepted trial did not cover. Implementation-session self-tests do not count as independent review.
