# L2 skeleton protocols v1

This document refines design sections 6–8 to unify draft permissions, human rulings and stage mappings.
CLI use, Python calls and manual editing follow the same protocol. T1 provides the read-order function; T2–T5 implement init, new, status and handoff. Stage acceptance still requires a real research project's manual trial.

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

Pass command integration tests first. Then use a real research idea for Claim writing → independent manual review → confirmed Objection → handoff → a fresh session the next day.
Automation can simulate restarts, but cannot replace a real two-day trial or final researcher acceptance. Implementation-session self-tests do not count as independent review.
