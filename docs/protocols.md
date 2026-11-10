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
A default confirmer may come from the operator's `TOULMIN_ACTOR` environment variable, or else the `actor` of the user config file (WX2), when `--confirmed-by` is omitted; both are local operator configuration, not workbench state. `--confirm` remains mandatory.
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

Automated review (C3): `toulmin review <project> [--personas a,b] [--models x,y] [--claim C-NNN] [--dry-run] --confirm` runs one fresh headless session per persona × model pair. It plans everything first (manifests, critique roles only, configured models, executables on PATH, the max_runs cap, unused archive names, and each adapter's preflight) and starts nothing if any check fails. The Codex preflight refuses a `CODEX_HOME` that contains AGENTS.md or AGENTS.override.md (the operator's global instructions would join every session), that does not exist, or whose `codex login status` fails; the message gives the one-time login command. `--dry-run` prints the plan; without `--confirm` nothing runs.
Each session gets the same self-contained prompt (inputs inlined) in an empty temporary directory: Claude Code with no tools, safe mode and no session persistence; Codex in a read-only, ephemeral sandbox. Sessions never see one another's output. A non-zero exit, timeout (the process group is killed), unreadable or empty output becomes a failed Run; output without a valid draft block is a completed Run whose drafts are taken in by hand. Interrupting the command kills running sessions.
Runs are archived one at a time under the creation lock as sessions finish; the command exits 1 if any session failed. review never creates or changes Objections, statuses or gates: drafts enter only through intake. The L2 part (planning, prompts, archiving) invokes no model; adapters are L3.

Synthesis and cross-validation (C4): `toulmin synthesize <project> R-NNN R-NNN... [--model M] [--dry-run] --confirm` gives one fresh synthesizer session its static manifest plus exactly the raw outputs of the named Runs (at least two, all completed, all reviews or all crossval answers, each with a valid item block) and a list of every `R-NNN/label` to group.
The synthesizer model rotates deterministically (Q23): the next model in `[review] models` after the one named by the project's latest synthesis archive, or the first one; `--model` overrides it. The Run summary records which applied and why. An invalid group block leaves a completed Run flagged for manual comparison.
`toulmin crossval <project> <runs/drafts/question.md> [--models a,b] [--synthesizer M] [--no-synthesis] --confirm` asks each model the same question independently (role `crossval`, same prompt), then synthesizes the usable answers; with fewer than two, synthesis is skipped. The run cap counts the synthesis session.
Neither command creates or changes objects. Researchers take drafts in from the original review output a group cites; intake refuses synthesizer and crossval outputs. Both reuse the C3 planning, preflight and archiving, so nothing starts unless every check passes.

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
| init <root> [--name N] | WI2: a project-free workspace (templates, WORKSPACE.md published last, empty projects/ and record locations) and a Git repository, without committing | Missing, empty or incomplete-init roots only; an existing workspace is reported and left unchanged; legacy and unrelated roots are refused |
| init <root> --project <name> | Legacy route: initialize templates/project and a Git repository, without committing; refused on a workspace root | Create missing items; identical templates are unchanged and conflicts rejected; adding another project does not rewrite global files |
| new <type> <project> | Complete draft and human confirmation; return new ID/path | Create one formal object only; archive AI drafts first and reject existing targets; no placeholder “valid objects” |
| status <project> | PROJECT, relevant objects and explicit brief references; return summary/diagnostics | Entirely read-only, including no cache/index writes or mtime updates |
| status [--workspace] | WI2: without PROJECT, the workspace view: root, scope, charter (direction or its absence), recorded next step, last handoff, child stages, proposal dispositions and resource names | Read-only as above; never initializes; legacy roots report workspace state not configured |
| workspace propose --input F | WI3: validate a change input from root runs/drafts/ and freeze one sealed review packet (diffs, sources with coverage, pins, after images) | Writes only a new runs/<stamp>-proposal-<hex>/ directory; WORKSPACE.md and resources unchanged |
| workspace apply --draft P | WI3: preview without --confirm; with --confirm and an actor, publish the packet's after images and a receipt | Only the listed WORKSPACE.md/resource targets, via the root journal; replays return the receipt |
| workspace reject --draft P --reason R | WI3: record a final rejection for a pending packet (requires --confirm and an actor) | Writes only the packet's receipt.md |
| project propose NAME --input F | WI6: validate a creation input from root runs/drafts/ and freeze one sealed packet (question, scope, generated PROJECT.md and Brief, sources with coverage, pins) | Writes only a new runs/<stamp>-project-<hex>/ directory; no project directory |
| project create NAME --from P | WI6: preview without --confirm; with --confirm and an actor, publish the complete child and a receipt | Only the new projects/NAME (built in projects/.creating-<hex>, renamed once) and the packet's receipt.md, via the root journal; replays return the receipt; never starts a session |
| project reject NAME --from P --reason R | WI6: record a final rejection for a pending creation packet (requires --confirm and an actor) | Writes only the packet's receipt.md |
| workspace adopt ROOT [--name N] | WI7: preview the deterministic additive plan and its digest for a legacy workbench; with --plan-digest, --confirm and an actor, apply that unchanged plan | Preview: read-only. Confirm: only the planned workspace files and one runs/<stamp>-adoption-<hex>/ archive (plan, seal, receipt), via the root journal; never projects, bindings or contexts |
| aoe open/bind/status/refresh/ack [PROJECT \| --workspace] | WI5: without PROJECT on a workspace root, the workspace scope's native session, binding and context; with PROJECT, that child (AOE3 behavior, plus the read-only WORKSPACE.md on workspace roots) | Scope's binding (`.aoe/binding.json` or `projects/NAME/.aoe/binding.json`) and context archives in that scope's runs/ only; never research objects |
| aoe handoff [--workspace] --input F / --apply D | WI4: without PROJECT, seal a workspace handoff draft from a structured summary; apply previews without --confirm and, confirmed, records the session | Draft: one new runs/<stamp>-handoff-<hex>/ directory. Apply: one new sessions/ record and WORKSPACE.md next_step/last_handoff only, via the root journal; replays return the record |
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

## UI1 terminal project setup and inspection

Q25–Q29 authorize the Python/Textual interface and future archived exploration, brief proposals
and Claim extraction. UI1 implements only create/open, import preview, recovery and navigation;
no model is invoked and no research gate is advanced. Later views clearly state their availability.

The L3 workspace service reuses initialization and core validation. It validates typed input
before creating a project, archives an explicitly selected UTF-8 Markdown/text source unchanged,
and publishes a complete setup intent before initialization. Explicit Resume Setup completes
an interrupted scaffold and two-file setup using exact known images. It preserves conflicts
for inspection; process-death-safe locking coordinates setup writers for a workbench.
A failure before publishing the complete intent is a preparation failure, not a completed
research project. Retained pre-initialization remnants must be diagnosed before operator cleanup.
Opening a project is read-only and never runs init over edited templates. Project data errors
remain visible, as does incomplete setup. Navigation is independent of PROJECT.stage.

This L2 behavior note explains the UI1 setup contract and Q25–Q29 scope approval. Existing
confirmed object intake, rulings, handoff and review protocols remain authoritative. Model
conversation and automatic draft saving are specified in the subsequent slice below.

## UI2 conversation and confirmed Brief application

The researcher approved restoring the interactive workbench as the primary interface
on 2026-11-03. This implements Q25–Q28's exploration and Brief proposal permissions;
it does not approve Q30–Q31's broader scientific-workflow/stage-write scope.

- An explicit Send persists the message, frozen input files and exact prompt before
  starting one fresh tool invocation. Context includes AGENTS, PROJECT, saved Brief,
  the referenced last handoff when present, submitted conversation history, and an edited
  pending proposal labelled as an unconfirmed working draft. Failed
  partial answers are labelled incomplete and not reused as completed assistant answers.
  No silent truncation: requests over 100,000 characters are refused. Context selection
  and arbitrary file attachments are not implemented in this slice.
- The L3 application owns jobs independently of views; model execution stays out of
  L1/L2. Only one job per project is allowed. A process lease prevents another application
  from recovering a live request. Stop/confirmed Quit terminate and reap the corresponding
  subprocess group, preserving available output and recording failure. A stopped Textual
  worker alone would not satisfy this requirement. Adapters currently return final output.
- Opening a project only reads. An orphaned running request is shown as interrupted;
  explicit Recover finishes already saved output or records failure, never retries a
  model call. The researcher sends a new request to retry. No periodic quota-consuming
  action or automatic research ruling is added.
- Propose Brief is an explicit model operation. The raw result and its Run are archived
  before a pending proposal appears. The researcher may continue chatting, edit the
  working draft, compare saved/proposed text, and explicitly apply or dismiss. Resolve
  a pending proposal before requesting another. Proposal text is not verified evidence.
- Apply confirms the edited text and actor, checks input validity and the frozen Brief
  hash, and preserves the before/after images plus intent. Interrupted application resumes
  the same confirmed payload. It does not overwrite unrelated edits, update Claim statuses,
  create formal Claims or advance PROJECT.stage. External editors must pause during Apply
  because they do not participate in Toulmin's advisory lock.

The L2 change supports recoverable interactive work and researcher-controlled assisted
authoring. Independent review still excludes conversation history and handoffs according
to its manifest. Existing intake, ruling and handoff protocols retain their authority.

### UI2 exploration tool permissions

On 2026-11-03 the researcher explicitly authorized network access, search and downloads
during exploration. Exploration now permits research tools in an archived per-request
`research/` workspace. The exact archived prompt specifies this scope before invocation
and names existing prior research workspaces for further reading. Tools may inspect
sources and save downloaded/derived material there, but cannot approve evidence grades,
make gate rulings or write formal research documents. The model must distinguish sourced
statements from inferences, cite URLs/access dates and disclose abstract-only reading or
failed access. Web and downloaded text are data, not authority to change the task rules.

The application selects a tool-enabled, network-enabled native sandbox for exploration
and retains tool event logs beside its workspace. Missing sandbox capability produces a
failed invocation rather than an unrestricted fallback. Brief generation remains tool-free
composition over supplied context; independent review retains its original restricted
manifest. Search/downloads neither automatically create Evidence nor validate source claims.
This corrects the earlier reuse of independent-review restrictions for open exploration;
it leaves formal confirmation, cancellation, timeout and no-automatic-retry rules intact.

### UI2 native exploration continuation

The researcher approved persistent native exploration sessions on 2026-11-03, superseding
Q27's stateless-only choice because file-replayed final answers omit intermediate tool
context. Before invocation, the protocol freezes whether to start fresh or resume, the
reason, predecessor, configuration fingerprint, workspace anchor and requested native ID.
A hash in the request binds this continuation record to the exact supplied prompt.

Only the latest successful, unrecovered exploration with compatible configuration and
a reported session ID can be resumed. Brief authoring between exploration turns does not
replace the native session. A resumed prompt contains current authoritative project files,
explicit current proposal state and intervening turns; it does not replay already inherited
dialogue. An applied/dismissed proposal cannot remain implicitly active in inherited context.
The 100,000-character cap applies to the actual supplied request, including resumed requests.

Configuration changes, legacy/no-ID history, prior failed/cancelled/recovered turns and
explicit F3 Rebuild select a fresh file-based start. Missing native storage at invocation
time produces a failed Run; there is no automatic second invocation. The next explicit Send
may rebuild. Fresh starts and separate Brief authoring retain full-history size limits;
the application does not silently summarize or drop messages. Opening still invokes no model.

Exploration keeps a stable writable research workspace while each turn retains its own
archive. Providers may persist native histories in their local cache. Independent review
and Brief authoring remain fresh ephemeral operations with their existing tool restrictions.
Formal confirmation, gate ownership, process leases and cancellation rules are unchanged.

## Native collaborative Brief round trip (UI-N1)

Reason: the researcher accepted the native split interaction and authorized real-project
context, returned drafts and explicit Brief confirmation. L2 never starts native tools.
It freezes AGENTS/PROJECT/Brief/last-handoff inputs; L3 starts a separate native process
in research/, protects direct formal paths and owns process leases. Normal CLI exit
precedes durable closure, exact output freezing and one idempotent normal Run.
A model/provider ID not collected remains unknown, and a returned draft is not a transcript.

The researcher previews the frozen draft/diff and explicitly applies only a successful
valid proposal. Current Brief must match the frozen before image; durable application
intent and after image allow same-actor/text recovery. No stage/object status changes
are implicit. Failed/interrupted sessions retain partial drafts but cannot apply them.
Recovering an orphan is explicit, verifies no worker lease is live and never retries
a model. Saved-session inspection makes no model call. Corrupt/oversized output is
reported, not repaired or truncated. Open workspaces/material are not immutable Evidence.

This adds no independent-review privileges and makes no complete native provenance claim.
See docs/native-workspace.md in the development repository for launcher usage and limits.

## Current research state and external session entry (AOE3)

Reason: the delegated AOE2 trial found stale handoff suggestions, model-written action
history in place of available choices, and native session creation mistaken for readiness.
The read-only research workspace protocol derives current stored statuses, draft-file
inventory, pending review intake and available actions from files. The recorded next step
remains explicitly historical guidance. Invalid data is visible, never silently repaired.
Resident input planning includes AGENTS, PROJECT, Brief and only the latest applied handoff;
raw discussions and all historical handoffs are not loaded as resident context.

An L3 AoE adapter may bind native sessions and publish hashed context snapshots with a
separate context-read receipt. Prepared, submitted and acknowledged are distinct states.
A receipt grants no research authority; changed files or a replacement native conversation
require fresh context. Binding metadata and snapshots are auxiliary records, not a Run or
proof of a complete native transcript. Research output archival remains a separate protocol.
The adapter owns neither the native terminal nor Chief tasks, and does not answer native
permission prompts. Handoff drafting/application reuse the existing explicit-confirmation,
conflict and idempotency rules. Closing an external session cannot apply a handoff or gate.

## Workspace-first contracts (WI1; implemented in parts from WI2)

Reason: the researcher accepted the workspace-first state design, operation scheme and
acceptance plan (WS1–WS3) and authorized WI1 to freeze their file contracts before any writer
exists. [workspace-formats.md](workspace-formats.md) is the contract; WI2 and WI3 below
implement parts of it, and WS3 acceptance cases remain NOT RUN. The L2 rules it fixes for later tasks:
- Scope is explicit data (`{kind: workspace}` or a named child). Omitting PROJECT in the AoE and
  workspace commands selects the workspace; nothing is inferred from history or the only child.
- Changes to the workspace charter or shared resource descriptions go input → sealed packet →
  explicit apply or reject. Apply checks only the packet's targets, selected sources and pins,
  publishes only listed files, and is idempotent. Saving drafts needs no approval.
- A workspace handoff changes only WORKSPACE `next_step` and `last_handoff`. Confirming it
  approves the summary, not the ideas it quotes; no direction, resource or child is bundled.
- Child creation publishes one complete project (PROJECT, initial Brief, empty collections,
  creation provenance) from a reviewed packet, with no Claim and no native launch. Opening its
  conversation is a separate, retryable step.
- One journal per workspace root serializes these writes; recovery is forward-only and reruns
  the same command; external edits are preserved and refused, never rolled back.
- Legacy workbenches gain workspace state only by a previewed adoption plan confirmed by its
  digest. Project bindings version 1 and their context archives stay readable and unconverted.
Manual editing has the same authority as the commands: the researcher may hand-edit the
charter or a resource description (readers report it as unreceipted); agents prepare proposals
instead; packets, seals, receipts and applied records are never edited. Existing project
protocols above are unchanged.

### WI2 project-free initialization and workspace status

`init ROOT` without `--project` implements workspace-formats.md section 12, and `status`
without PROJECT the read-only workspace view (sections 2.1, 4 and 7.3). Status checks only what
determines a proposal's disposition (seal, receipt, successor, journal); packet schemas are
validated by the operations that consume them. A pending journal, malformed charter, invalid
child or tampered packet makes the view invalid (exit 1) without repairing anything. The legacy
`init --project` route and template project setup in the TUI are refused on workspace roots;
elsewhere they are unchanged. Workspace conversations, proposals, handoffs, child creation and
adoption were later tasks (WI3–WI7).

### WI3 reviewed workspace changes and resource descriptions

`workspace propose/apply/reject` implement workspace-formats.md sections 5–7 and the section 10
journal for one operation, `workspace-change`. Reasons for the L2 additions:
- Propose re-derives every after image from current files and refuses no-op, occupied or
  unregistered targets, missing or mismatched material and cited activity records whose
  coverage differs from the input; it runs no model and never fetches a URL. Local sources up to
  1,000,000 bytes are snapshotted as `sources/N<suffix>`; larger ones keep path and digest only.
- Apply checks, in the contract's order, the journal, the seal and frozen digests, an existing
  receipt (replayed unchanged, whatever actor is given), supersession, then the packet's own
  targets, sources, pins and registered material. Nothing else is compared, so edits to other
  files, resources or child projects never conflict. Preview takes no lock and writes nothing.
- Publication journals the before and after images and the receipt (as the last image), then
  writes forward. A rerun of the same apply finishes it with the first confirmation's actor,
  time and approval text; a file matching neither image stops recovery with every file kept.
  While a journal exists, other workspace proposals and applies are refused.
- Status validates resource descriptions and receipts, and notices a charter (owned parts only)
  or description that differs from its receipted after image. Material digests are checked by
  propose, apply and pins, not by status. The charter after image is rendered from the
  canonical field order rather than round-tripped, so untouched nulls stay `null`.

### WI4 workspace handoffs

`aoe handoff` without PROJECT (or with `--workspace`) implements workspace-formats.md section 8;
with PROJECT it is the unchanged project handoff. Reasons for the L2 additions:
- Drafting validates the summary (four required sections, no generated `Next step`, the
  expected kind named for change inputs, packets, project summaries and drafts), requires each
  cited `confirmed_changes` receipt to be applied, inherits or requires `next_step`, and
  publishes one sealed draft under the root lock. It needs no AoE client or model.
- Apply follows the contract order: another record's journal refuses; this draft's journal
  recovers forward with the first confirmation's actor and time; a draft already in the
  WORKSPACE `last_handoff`/`previous_handoff` chain returns its record; otherwise the base
  charter digest and cited receipts must still match. The charter patch replaces only the two
  continuity lines, so other fields, sections and quoting stay byte-identical.
- Entry planning reads only the applied chain (`latest_handoff`). Status shows each draft as
  pending, stale (base changed), applied, incomplete or invalid, lists only non-applied ones by
  default, and reports a session record outside the chain without a journal as an orphan error,
  preserved and never used as the latest handoff.

### WI5 two-scope native entry

The AoE group implements workspace-formats.md section 11. Reasons for the L3/L2 additions:
- Omitted PROJECT selects the workspace in open, bind, status, refresh, ack and handoff; PROJECT
  with `--workspace` is a usage error. Output starts with the resolved root and scope. A legacy
  root has no workspace scope, and its project bindings keep the exact AOE3 version 1 behavior.
- On workspace roots, new bindings are version 2 (scope and title), sessions are created at the
  root, a workspace session must be at the root, and one native session is bound to at most one
  scope across versions. Existing version 1 bindings are read and updated in place; explicit
  `bind --replace` or `open --new-session` writes version 2. Manifests and receipts carry the
  binding's version and, for version 2, its scope, so an ack for another scope is refused.
- The workspace state card and fingerprint (L2 `workspace_context`) cover the section 11
  inputs plus handoff draft dispositions. A child on a workspace root adds WORKSPACE.md and its
  creation record to the AOE3 inputs. Busy, trust-prompt, uncertain-creation and resend rules
  are unchanged and apply to both scopes.
- A workspace root's research AGENTS.md comes from a separate scope-aware template; the shared
  template used by legacy workbenches is unchanged, so their template checks still match.

### WI6 confirmed child creation

`project propose/create/reject` implement workspace-formats.md section 9 with the section 10
journal. Reasons for the L1/L2 additions:
- The creation packet is the complete review text: besides question and scope it embeds the
  generated PROJECT.md and the verbatim initial Brief, so preview and confirmation cover the
  same bytes. Included and excluded items are rendered verbatim as lists; related projects and
  open questions have their own lines (a clarification of the WI1 example, regenerated from
  code with all dependent digests).
- Create checks only what the packet relies on: `projects/NAME` absent (an occupied name names
  its creating packet and actor, and is never replaced), selected sources, pins, related
  projects and Brief markers. Shared rules, templates and workspace customizations are neither
  compared nor copied; unrelated edits never conflict.
- The `project-create` journal adds `staging`. The child is written in
  `projects/.creating-<hex>` and appears under its name in one rename; the receipt is the last
  image. Recovery accepts only expected files at their after images (discarding the writer's
  unfinished temporaries in staging) and keeps everything on any other content. While the
  journal exists the child shows as "creation incomplete" and cannot be opened.
- Creation never starts a native session; the result prints `aoe open NAME`. A launch that left
  no matching AoE session may be retried with an explicit `open --new-session`; any matching
  candidate still requires inspection, so a duplicate session is never created silently.

### WI7 previewed legacy adoption

`workspace adopt` implements workspace-formats.md section 12 with the section 10 journal
(operation `adoption`). Reasons for the L1/L2 additions:
- The plan is computed from current files only and rendered without time or absolute path, so
  its digest identifies what was previewed; confirmation recomputes it under the root lock and
  refuses any other digest. Conflicts are part of the plan and block confirmation.
- "Released" templates are recognized by digest from the packaged `released.json` (every shipped
  copy of the AGENTS templates and of the workspace contract), supplied by L3 as plain data; L2
  reads no package files. Pristine copies are replaced; a customized AGENTS.md receives only the
  template's scope section; an edited contract copy is a conflict (a clarification: an older
  pristine contract copy, present in workbenches initialized after WI1, is replaced).
- The workspace template's scope rules now form one `## Workspace and project scopes` section,
  so the appended text is exactly the template's.
- WORKSPACE.md is published after the archive and just before the receipt, so a crash leaves a
  legacy-classified root or an incomplete workspace, both reported with the digest to rerun.
  Project bindings (version 1) and their context archives are untouched; their contexts become
  stale because a child of a workspace root also receives WORKSPACE.md.

### WI8 native trial fixes (L3 only)

The live AoE trial changed no L1/L2 behavior. Recorded for the binding contract:
- Readiness scans for busy and dialog words only around the native input line, and treats dim
  composer text as a hint, because agent replies and Claude's suggested prompts otherwise
  refused every later delivery.
- AoE refuses a new session whose title and path match any existing session, archived or
  trashed ones included. A version 2 binding therefore records a numbered title such as
  `Workspace: NAME (2)` when the plain one is taken at the root; creation recovery matches the
  recorded title as before. Version 1 bindings keep `Toulmin: NAME` unchanged, so a legacy
  replacement still needs the old session renamed in AoE.
- A provider identity that AoE reports only after the first turn still resets the binding and
  sends one new context (researcher decision W1, 2026-11-04: keep the AOE3 rule).

### WX2 entry and preferences (L3 only)

After the partial WI8 researcher trial (observation O1: too many setup commands), the CLI gained
user preferences and a heuristic entry. No L1/L2 format or behavior changed.
- Preferences: `$XDG_CONFIG_HOME/toulmin/config.toml` (default `~/.config/toulmin/config.toml`)
  with `actor` and `[aoe] profile/agent/attach`. It is user configuration outside every
  workbench, never research data. Unknown keys or invalid values stop the command; nothing is
  repaired. Precedence: flag > saved binding > environment variable > config > default. Wherever
  a contract names `TOULMIN_ACTOR` as the actor default, the configured actor is a further
  fallback; it supplies attribution, never confirmation.
- Root discovery: an omitted `--root` means the nearest workspace or legacy workbench at or
  above the current directory, announced on stderr when it is not the current directory. An
  explicit `--root` is used as given. Discovery never selects a scope for `aoe` commands:
  omitting PROJECT still means the workspace.
- `toulmin open [NAME]` selects the scope (NAME, else the child directory you are in, else the
  workspace) and delegates to `aoe open`. On an empty or interrupted-init directory it
  initializes only after an explicit yes in a terminal; it refuses unrelated directories and
  asks for a project name on legacy workbenches. A new session's agent is the flag, else the
  replaced binding's, else the configured one, else codex; an existing binding keeps its own.

### WX4 one-pass decisions (L3, plus one L2 text line)

After the partial WI8 researcher trial (observation O3: per-item apply/handoff commands),
`toulmin decide` walks every pending item in the researcher's own terminal. No format changed.
- Inventory, in order: pending workspace change packets, pending child creation packets,
  pending workspace handoff drafts, then unapplied project handoff drafts whose base PROJECT.md
  is current. Handoff drafts already stale are counted, not offered.
- Each item shows its existing preview without the copy-paste command lines and is decided
  alone: apply, reject (packets only, with a recorded reason), skip or quit. Applying calls the
  same L2 function as the item's own command; packets record `approval_text: "toulmin decide:
  a"`. There is no bulk decision. An item that fails is reported and stays pending.
- A change packet and a workspace handoff draft both pin the whole WORKSPACE.md digest. When a
  change applied in the same run makes a pending handoff draft stale, decide drafts it again from
  the same summary (only if the summary's digest is unchanged) and shows the new draft with
  the W8 warning below. After a workspace handoff is applied, further
  workspace handoff drafts are skipped as superseded; the same holds per project.
- Like every confirming command, decide relies on being run by the researcher. It adds no
  enforcement and removes none; without a terminal it only lists items.
- Agent guidance (workspace AGENTS.md template, native context text) now says pending items
  await `toulmin decide` instead of listing apply/reject commands, and asks the agent to offer
  a charter proposal once discussion settles a direction, constraint or resource (O5). The L2
  workspace state card's action line names `toulmin decide`; this is presentation text only.

### WX3 model visibility (L3 only)

After the partial WI8 researcher trial (observation O2: how is the model chosen?), the binding
view shows which model answered. Toulmin still chooses only the native CLI.
- `adapters/provider_logs.py` reads the bound native conversation's own session log (Codex:
  the latest `turn_context`; Claude: the latest non-synthetic `assistant` message) and extracts
  only the model name and reasoning effort. It scans at most the last 16 MiB, ignores symlinks,
  accepts provider IDs and values only in conservative patterns, and reports "not yet reported"
  for anything missing or unrecognized.
- `aoe status`/`open` print `Model: … (reported by the <agent> session log)` under BINDING;
  `--json` carries the same report. It is display provenance, never a control branch, and is
  not written to bindings, contexts or research files.

### W8 uncited applied changes in a workspace handoff (L2 read-only, L3 text)

In the WI8 researcher trial a change was applied, and the agent then wrote a handoff summary with
`confirmed_changes: []` whose next step still asked to decide that change. Applying the handoff
copied the stale next step into WORKSPACE.md. Drafting only checks that cited receipts are
applied; nothing noticed an applied change that was omitted.
- L2 reason: `workspace_handoff.uncited_receipts(root, cited)` lists applied workspace change
  receipts later than the latest applied handoff (all of them before the first) that `cited`
  omits. It is read-only and reuses the receipt check that drafting applies to cited receipts;
  absent, rejected or unreadable receipts are not listed (workspace status reports damage).
- The handoff preview (draft output, `--apply` preview and `toulmin decide`) prints a warning
  naming them. It is a warning, never a refusal: the summary stays the agent's record, and the
  researcher may apply it knowingly. The native workspace context asks the agent to cite every
  such receipt and to draft again when warned. No format or command behavior changed.

### WX6 known workspaces (L3 only)

After the WI8 v2 trial (question 3: an earlier workspace in another folder was not recognized),
`toulmin open` can find workspaces outside the current directory tree. Accepted design:
`~/notes/toulmin/workspace-registry-design.md`. No research file or format changed.
- `$XDG_STATE_HOME/toulmin/workspaces.json` (default `~/.local/state/...`) lists absolute,
  normalized paths with the last seen name and last opened time (schema_version 1). It is a
  user-level cache outside every workbench: `init`, `open` and a confirmed `workspace adopt` add
  to it, read-only commands never write it, writes are atomic, and a damaged file is reported,
  never rewritten or repaired. A failed update is a notice; the command still succeeds.
- Recognition still comes from the folder: each listing re-reads WORKSPACE.md (or the legacy
  signature) and marks entries missing or damaged. The list never decides anything.
- With no workbench at or above the current directory and no explicit `--root`, `open` lists
  the known workspaces and asks which to open (`i` initializes an empty directory; default
  quit). Without a terminal it only lists. With an empty list the WX2 behavior is unchanged.
- `open --in NAME_OR_PATH [CHILD]` opens a known workspace by case-insensitive name or by path;
  an ambiguous name lists the candidates and stops. `toulmin workspaces` lists, `forget PATH`
  removes an entry without touching the folder, and `scan [--profile]` reads AoE's session list
  (read-only) and adds workspace roots, or roots of `projects/NAME` sessions.

### H2 gate readiness in status (L2 read-only)

Design: `~/notes/toulmin/project-research-loop-design.md` (H1, accepted with D1–D6). Before H2,
`status` reported per-Claim conditions only, so whether a project could enter critique or
brief-final had to be worked out by hand.
- L2 reason: `project_status` adds `gates`, a G1 and a G2 readiness report computed from the
  project files (design section 7). G1: a current (not superseded) core Claim of each type
  problem, magnitude, mechanism, novelty. G2: no open fatal or major Objection; every current
  core Claim has valid verified supporting Evidence or a nonempty `validation_plan`, and a
  refuted core Claim never qualifies; the brief.md "Kill criteria" section has content other
  than blanks and HTML comments (fenced code is opaque).
- Readiness is unknown while project data is invalid or brief.md is unreadable. It reads only
  files status already reads, writes nothing, and never changes stage or object status; the
  CLI labels it "readiness from files; the stage changes only by your ruling".
- No format change. Stage rulings through `toulmin decide` (D4) are a later slice.

### H6 project research loop guidance (L2 presentation, L3 text, template)

Design: `~/notes/toulmin/project-research-loop-design.md` (H-C). Project agents had the rules
but no loop, so when to draft Claims, propose a review round or recommend intake was left to
each session.
- L2 (presentation only): the project state card adds GATES (G1/G2 readiness from H2, one line
  each with the missing items) and one stage-aware ACTIONS line: at explore, draft the missing
  core Claims or, when G1 holds, note that the researcher may rule the stage change; at
  critique, the same for G2. Gates derive from files already in the fingerprint, so freshness
  is unchanged. The card never changes stage or status.
- L3 text: the project context describes the loop (explore, core Claims, objects created by
  the researcher, independent review rounds proposed with a `--dry-run` plan and started only
  by the researcher, intake recommendations per draft label, responses, rulings, Brief
  sections, stage changes as rulings). The agent's own commands (`draft`, `status`,
  `review --dry-run`) use the serving interpreter (W7); confirming commands are named for the
  researcher.
- The workspace AGENTS.md template gains "Project sessions" with the same loop;
  released.json is regenerated. No format change. Moving the researcher's confirmations into
  `toulmin decide` is H3–H5.

### H3 project proposals in decide (L1 additive, L2, L3)

Design: `~/notes/toulmin/project-research-loop-design.md` (H-A items 1 and 4; D1, D2). Before
H3 the researcher typed `new … --confirm` and `rule … --confirm` for each agent draft, and
nothing distinguished a ready draft from a scratch file.
- Location (D1): an agent marks an item ready by putting it directly under
  `projects/NAME/runs/proposals/`, named `KIND-YYYYMMDDTHHMMSSZ[-name].md`, where KIND is
  claim, evidence, objection, decision, exploration, spec or ruling. An object draft is moved
  there from runs/drafts/ with its filename unchanged. Other files there are not offered;
  the state card names them.
- Ruling proposal: header `schema_version: 1`, `kind: ruling-proposal`, `object` (an ID in
  the same project; since R1 `objects`, a list of two or more, may replace it), optional `status`, `decision` (D-NNN, or the filename of a decision
  draft in the same folder) and `links` (the fields `rule` may set); body `## Why` (required,
  shown to the researcher, never stored) plus any of Response, Ruling, Invalidation or
  Rationale, whose text is added to the object as `rule` adds it. At least one of status, a
  section text or a link is required.
- Outcome (D2): the decision is recorded beside the proposal as `<stem>.outcome.md`: header
  `schema_version: 1`, `kind: proposal-outcome`, `proposal`, `proposal_sha256`,
  `disposition` (applying, applied or rejected), `actor`, `at`, `approval_text`, `reason`
  (rejected only, required) and `result` (applied only: the created or ruled object ID). The
  proposal is never edited, moved or deleted.
- L2: `create_object` and `apply_ruling` gain a write-nothing `preview` mode (and
  `apply_ruling` direct section texts); confirmed behavior is unchanged. `project_proposals`
  lists undecided proposals (object drafts before rulings), previews, applies exactly the
  previewed bytes and rejects with a reason. Application first writes an `applying` outcome
  exclusively, so a second decider fails and an interrupted application is never repeated
  blindly: the next preview looks for the object (same body, created after the marker) or the
  ruling already on the object, and apply then only records it. A ruling whose decision draft
  is undecided or rejected is not applicable.
- L3: `toulmin decide` offers each project's proposals after workspace items and before
  project handoffs, with the predicted path or the status change, Decision, sections and
  links, and apply / reject (with a reason) / skip / quit. The state card lists PROPOSALS;
  project contexts and the workspace AGENTS.md tell the agent where to put ready items.
- Compatibility: additive. No existing file changes meaning; runs/proposals/ is new. `new`
  and `rule --confirm` still work as before. No migration.

### H4 review rounds and intake in decide (L1 additive, L2, L3)

Design: `~/notes/toulmin/project-research-loop-design.md` (H-A items 2 and 3; D3). Before H4
the researcher typed `review … --confirm`, `synthesize` and `intake --take/--reject` by hand
from the agent's suggestions.
- Review request `review-YYYYMMDDTHHMMSSZ[-name].md` in runs/proposals/: header
  `schema_version: 1`, `kind: review-request`, optional nonempty `personas`, `models` and
  `claims` lists (defaults as for `review`); body `## Why now` (required). Decide previews the
  `review --dry-run` plan (sessions, cap, inputs) plus the rotated synthesizer; only the
  researcher's apply starts it (D3). It plans and preflights again, writes the `applying`
  marker, runs the reviews, then synthesizes when two or more outputs completed with drafts.
  The outcome's `result` lists each Run and status (or why synthesis was skipped). An
  interrupted round is never started again: apply records the Runs archived since the marker.
- Intake recommendation `intake-YYYYMMDDTHHMMSSZ[-name].md`: header `schema_version: 1`,
  `kind: intake-recommendation`, `output` (a review Run's raw output, never a synthesis) and
  `recommendations`, one entry per draft label: `label`, `outcome` (take, reject, partly),
  `reason` (the agent's grounds; for reject the proposed recorded reason), `severity` (take
  only, to change it) and `object` (partly only, the hand-written Objection). Every label
  without an outcome in intake.md must be covered. Decide asks per label: as recommended,
  take, take with other severity, reject (reason; the proposed one is the default), skip or
  quit; the choices are recorded together through `intake_review` when the output's walk ends
  (quit records nothing for it). The recommendation is applied (`result`: the intake.md path)
  once every label has an outcome; skipped labels keep it pending.
- L2: `intake_review` gains a write-nothing preview; `output_state` reads an output's drafts
  and recorded outcomes; `project_proposals` validates both kinds and brackets review rounds
  with `begin_review`/`finish_review`. Inventory order: intake recommendations, object drafts,
  rulings, review requests (a new round after the revisions it should see).
- L3: `adapters/review` splits a decide round into `prepare_round` (plan, preflight, show) and
  `execute_round`; `review` and `synthesize` behave as before.
- Compatibility: additive; existing files and commands unchanged; no migration.
- Follow-up (2026-11-09, after a simulated run): decide shows beside each label where completed
  syntheses placed it (`synthesis_groups`, L2 read-only: group, kind, the other drafts, note),
  and counts a recommendation with labels still undecided as "Partly recorded", not Applied.

### H5 Brief and stage proposals in decide (L1 additive, L2, L3; first `stage` writer)

Design: `~/notes/toulmin/project-research-loop-design.md` (H-A items 5 and 6, H-D; D4 = b,
D5). Before H5 the Brief was edited by hand (model Brief proposals existed only in the
Textual/native interfaces) and no command wrote PROJECT.md `stage`.
- Brief proposal `brief-YYYYMMDDTHHMMSSZ[-name].md` in runs/proposals/: header
  `schema_version: 1`, `kind: brief-proposal`, `base_sha256` (quoted sha256 of brief.md when
  drafted); body `## Why` (required, never written) then one `## <brief section>` per section
  to replace, with its complete new text (nonempty; the section must exist once). Decide
  shows a unified diff and refuses the proposal once brief.md differs from `base_sha256`;
  `[[reference]]` errors in the result are problems. Apply writes brief.md exactly as
  previewed under the project writer lock and rechecks the digest first.
- Stage proposal `stage-YYYYMMDDTHHMMSSZ[-name].md`: header `schema_version: 1`,
  `kind: stage-proposal`, `from`, `to` (stages of formats.md, different), `decision` (D-NNN or
  a decision draft's filename in the same folder, resolved through its applied outcome);
  body `## Why`. It is refused unless PROJECT.md is at `from`, the Decision is active, and no
  handoff application is unfinished. Apply sets `stage` and appends the Decision to
  `recent_decisions`, exactly as the previewed PROJECT.md diff shows.
- L0/L2 discussion (D4 = b, accepted 2026-11-05): AGENTS.md forbids condition checks from
  changing stage on the researcher's behalf. A stage proposal is not a check: nothing changes
  until the researcher's apply, the backing Decision records the ruling and its reasons, and
  G1/G2 readiness is shown as advice only (a ruling may go ahead with conditions unmet, or
  move backwards). Agents still never write `stage`.
- Interrupted application: the `applying` marker precedes the write; the next preview treats
  a brief whose proposed sections are already in place, or a PROJECT.md already at `to` with
  the Decision recorded, as done and only records it.
- Inventory order: intake, object drafts, rulings, Brief, stage, review requests. A project
  handoff drafted before a stage ruling in the same run is reported as made stale by it.
- Compatibility: additive; PROJECT.md and brief.md formats unchanged; no migration.

### C5 calibration report (L2 read-only, L3)

Design §9 "Reliability calibration" and Q22: adoption rates come from the files, never from a
second store. `toulmin calibration [--project NAME] [--write]` reads every Run of the chosen
project (or of all projects), groups them by operation (review for `reviewer` roles,
synthesis, crossval, other), the model name each Run recorded and the role, and counts runs
completed/failed. For review Runs it counts the draft labels of the raw output and the
researcher's intake outcomes (taken, partly, rejected; the rest pending), the adoption rate
(taken + partly) / decided, and the current status of every Objection an intake outcome
created. Unreadable Runs, outputs without a draft block and missing Objections are listed
under "Not counted", never guessed. The report has no timestamps, so identical files give an
identical report; `--write` (re)writes `global/calibration/calibration.md` (or
`calibration-NAME.md`) and hand edits there do not survive regeneration. The command never
changes research files and makes no recommendation about role assignment; reading the rates
is the researcher's call. No format change.

### V2 research map and shared next moves (L2 read-only, L3)

Design: `~/notes/toulmin/research-map-design.md` (V1, decisions D1–D6 accepted 2026-11-09).
The loop is not enforced, so the researcher needs one view of where a project is and what can
happen next. `toulmin map [NAME] [--watch] [--claim C-NNN] [--ascii]` shows, from files only:
the stage track, the gate that leaves the current stage with its items (others as counts),
what waits on the researcher (the `toulmin decide` items of that project, review drafts
without an intake outcome), up to three suggested moves naming who would act, and the
argument tree (current Claims, core first, with their Evidence, Objections and their
Decisions, Specs and validation plans; superseded Claims collapsed to their chains; Decisions
attached to nothing listed apart). Without NAME it follows the current `projects/NAME`
directory, else shows the workspace: pending workspace decisions and one stage line, decide
count and first move per project. `--watch` polls file metadata (Run archives only at their
top level), recomputes only on change and writes nothing.
- L2 reason: `protocols/research_map.py` holds `next_moves`, the one rule table behind the map
  and the state card ACTIONS, so the researcher and the agent read the same suggestions. Rows,
  in order: invalid data (resolve errors, nothing else); pending proposals (`toulmin decide`);
  review outputs with undecided labels and no pending intake recommendation (recommend
  intake); open Objections without a pending ruling proposal, fatal/major first (respond);
  explore: missing core Claims, or G1 holds; critique: a review round when no completed review
  Run is newer than the newest current Claim, Kill criteria, remaining G2 items, or G2 holds;
  otherwise continue the discussion. A gate that holds is not offered for a stage ruling while
  any review draft is undecided, because those drafts may still become blocking Objections.
- The card's stage-aware ACTIONS line (H6) and its proposal, open-objection and review lines
  are replaced by "Suggested next" lines from the same table; the other ACTIONS lines and the
  fingerprint are unchanged (the moves derive from files already fingerprinted).
- Suggestions are advice: nothing changes stage, status or objects. No format change.

### R1 prefilled proposal drafts and batch rulings (L1 additive, L2, L3)

Review: `~/notes/toulmin/rdma-trial-review.md` (R1). In the test-toulmin-rdma trial the project
agent learned the proposal formats by reading this file (19 times) and Toulmin's source (51
times), because `toulmin draft` made skeletons only for objects and Runs. Deferring eleven
Objections with one reason took one Decision and eleven ruling proposals.
- L3: `toulmin draft KIND PROJECT` also takes the proposal kinds, each written under
  runs/drafts/ with the proposal filename, for the agent to fill and move to runs/proposals/:
  `ruling --object ID [--object ID…] [--status S] [--decision D]` (the current status of
  each object in a comment; status choices exclude it; the sections a ruling may add for that
  kind), `intake --run R-NNN|OUTPUT` (one recommendation per draft label still without an
  intake outcome, with each draft's target, severity and content in a comment), `review
  [--claim] [--persona] [--model]`, `brief --section NAME…` (the quoted `base_sha256` of
  brief.md and the sections' current text) and `stage [--to STAGE] [--decision D]` (`from`
  is the current stage; `to` defaults to the next). Options that do not belong to the kind
  are refused; nothing is written on refusal.
- L1 (additive): `core/proposal_skeletons.py` renders those skeletons from data the caller
  read. A ruling proposal may name `objects: [ID, ID, …]` (two or more distinct IDs of one
  kind) instead of `object`; the status, Decision and section texts apply to each, and
  `links` are refused with `objects` (a successor belongs to one object). Exactly one of
  `object` and `objects` is required.
- L2 reason: `protocols/drafting.write_proposal_draft` reads the files a skeleton needs and
  writes it as `write_draft` does (exclusive, never overwriting). `project_proposals` previews
  every object of a batch, applies them one after another (each file atomically) and records
  `result` as the comma-separated IDs; after an interruption the next preview lists the
  objects that already carry the ruling (`done`) and apply rules only the rest. The Decision
  must name every ruled object in `related`, as for one object. Decide refuses a ruling,
  intake, review, Brief or stage proposal that still contains a `<fill:` placeholder, so an
  unfinished skeleton can never write a placeholder into brief.md or a status.
- A Response and a status already fit one ruling proposal (`status` plus `## Response`); the
  ruling skeleton shows both, which is the intended path for "answer and close" in one step.
- Compatibility: additive. Existing proposals keep their meaning (none in the trial workspace
  contains a placeholder). An older Toulmin reports a batch proposal as invalid (no
  `object`) rather than misapplying it. No migration.

### R2 compact project-session guide (L3 text, template)

Review: `~/notes/toulmin/rdma-trial-review.md` (R2). The trial's project session read this file
(62 KB) 19 times; most of it is development history the agent does not need, and the formats
it did need were spread over the H3–H5 sections.
- `src/toulmin/application/project-guide.md` (about 6 KB): what a project agent may write,
  the loop stage by stage with the gate conditions, object-draft essentials, rulings (answer
  and close in one proposal; one ruling for several objects), intake and ending the session,
  each with its `toulmin draft` command (R1). It is copied into every project context archive
  as `guide.md` (listed in the manifest), so workspaces created earlier get it as well;
  context.md names it first. Workspace contexts do not carry it.
- The project context's loop text (H6) shrinks to the draft commands and the boundaries; the
  per-kind format paragraphs now live only in the guide and this file. The workspace AGENTS.md
  template's project steps name the draft commands and the guide (released.json regenerated,
  so earlier copies are still recognized).
- This file keeps the rules and their change history unchanged; framework/protocols.md remains
  its byte copy. No format change.

### R3/R4 decide closes the loop; session hygiene after a stage ruling (L2 rule row, L3)

Review: `~/notes/toulmin/rdma-trial-review.md` (R3, R4). In the trial the researcher returned to
the agent after every `toulmin decide` to ask "what next?", no handoff was ever applied, and
the one project session grew to 325k tokens of context across all stages.
- L3 (R3): `toulmin decide` ends with "Next for NAME" for every project it decided something
  in: the suggested moves of the shared rule table. For each such project with a bound
  session it asks whether to tell that session what was decided (`--notify`/`--no-notify`
  answer in advance). The notice is one line: what was applied or rejected (at most eight
  items), where the reasons are, the interpreter-qualified `map` command to refresh with, and
  "propose, never apply". `AoEWorkspace.notify` sends it only when the session is live and
  passes the readiness check (never into a busy session or over unfinished input); the
  binding, context and receipt are unchanged, and a refusal is reported with its reason.
- L3 (R4): applying a stage proposal in decide prints two suggestions: a handoff draft
  applied through decide (it updates PROJECT.md's next step), then a fresh session (`aoe -p
  PROFILE session archive ID`, then `toulmin open NAME --new-session`). A notice after a stage
  ruling asks the agent for that handoff draft. guide.md says what a notice means.
- L2 reason: `next_moves` gains a row after pending proposals: when an applied stage proposal
  (its outcome's `at`) is newer than the last applied handoff (the session record's UTC name),
  the agent prepares a handoff because the recorded next step is stale. A stage edited by
  hand has no outcome and adds no row. The map, the state card and decide's closing moves
  read the same row. No format change.

### R5 honest gates: G3–G5 readiness and stage warnings (L2 read-only, L3)

Review: `~/notes/toulmin/rdma-trial-review.md` (D1, D2). In the trial the project reached `done`
with every Claim `proposed`, only model-asserted Evidence and no independent verifier run,
while the map showed every stage done; four major Objections deferred in one Decision turned
G2 green without a trace in the gate.
- L2 reason: `project_status` gates add G3–G5 of design section 7, computed from Specs, the
  Evidence they list and that Evidence's Runs. With no Spec each says "at least one Spec".
  - G3 (enters build), per Spec: its target is a Claim of this project that is current or
    has a current successor (Specs keep their targets, R1 of formats.md), and its Acceptance
    criteria name something runnable. The check is a heuristic: inline code or a fenced code
    block. The Spec skeleton and format example now put commands in backticks.
  - G4 (enters accept), per Spec: status `awaiting-acceptance` or `passed`, and a listed
    Evidence that is valid and supports (the implementer's own test report).
  - G5 (enters done), per Spec: `passed`, and a listed Evidence that is valid, supports, is
    `verified`, targets the Spec's Claim or a successor and comes from a Run whose `role` is
    `verifier`. Toulmin has no verifier role file; a researcher or session that ran the checks
    independently is archived by hand as such a Run.
- G2's "no open fatal or major Objection" item stays met when such Objections are deferred,
  but its detail names them as advice ("deferred, not resolved: …; revisit before build").
- `stage_warnings`: for each gate the recorded stage has passed that does not hold, a warning
  in status, the state card and the map, and a rule-table row for the researcher ("rule
  whether to keep the stage or return the project"). The stage is never changed: design
  section 7 leaves a return to critique to the researcher's ruling.
- L3: status, the card and the map fold G3–G5 while they are more than one stage ahead (G1 and
  G2 show as before; `status --verbose` shows all). The map lists the unmet items of a gate
  behind the stage. Rule-table rows toward G3 (draft Specs), G4 (implementer test Evidence)
  and G5 (verifier Run, verified Evidence, Spec rulings) follow the stage; a held gate offers
  the stage proposal as G1/G2 did. Stage proposal previews show G3–G5 readiness too.
- No object format change; the Spec skeleton hint and format example text changed only.

### R6 token usage of independent and native sessions (L1 additive archive file, L2, L3)

Review: `~/notes/toulmin/rdma-trial-review.md` (section 4, C5-3). The trial's seven review and
synthesis sessions left no token record, so their cost could only be guessed from prompt size;
the native project session's 20.8M input tokens were found only by reading Codex's own log.
- L1 (additive): `usage.json` beside output.md (formats.md, R6) with `core/usage.py` reading
  Claude Code's final `result` event (`usage`, `modelUsage`, `total_cost_usd`) and Codex's
  `turn.completed` events (summed over turns). Claude's uncached, cache-read and
  cache-creation input are summed into `input_tokens`, so both tools count input the same way;
  the raw records are kept. Nothing is estimated: no record, no file.
- L2 reason: `ReviewOutcome` and `ArchivedReview` gain an optional `usage`; `archive_review`
  writes the file (for failed sessions too, when the tool reported usage) and the Run summary
  names it. Run fields are unchanged. `calibration` adds a "Token usage by operation" table
  (Runs, Runs with usage, input, cached input, output per operation, model and role; `-` when
  none reported, `?` when a count is missing).
- L3: a review, cross-validation or synthesis round prints each session's tokens and the
  round's total over the sessions that reported. `aoe status` adds a Tokens line for the bound
  native session from the same CLI log WX3 reads for the model (Codex: the newest
  `token_count` running total and the latest request's input as the current context; Claude:
  per-request usage summed once per message ID over the newest 16 MiB of the log). Display
  only; a missing or unrecognized log prints nothing.
- Not covered: a session killed before its final event reports no usage (a timed-out Claude
  session keeps its partial answer but not its tokens); native exploration/Brief sessions of
  the TUI are unchanged.

### R5 follow-up: suggest supported rulings (L2 rule row)

Simulation: `~/notes/toulmin/r56-sim-2026-11-10/` (finding 3). `status` already noted "meets
supported conditions; researcher decision pending", but no suggested move followed, and the
trial project reached `done` with every Claim `proposed`.
- L2 reason: `awaiting_support_ruling` lists current Claims stored `proposed` or `challenged`
  with valid verified supporting Evidence and no open fatal or major Objection (the notice's
  rule, now shared). `next_moves` adds an agent row after the Objection row: propose supported
  rulings for those Claims, each with a Decision naming it; a Claim already named by a pending
  ruling proposal is left out. The map, the state card and decide's closing moves read it.
  Advice only: nothing changes a Claim's status but the researcher's ruling. No format change.


### R8 B2 — Build request to Chief (L1 additive, L2, L3)

Reason for the L2 addition: handing Specs and acceptance commands to implementers by hand
loses the reviewed boundary and the exact checks. `protocols/build.py` derives a contract
from files, compares the explicit request checks with the Spec's commands, and assesses that
Spec's G3 item before the researcher starts implementation. It never executes commands,
reads Chief state, changes a Spec status or makes a ruling.

- The agent drafts `toulmin draft build NAME --spec S-NNN [--repo PATH]`, fills Why and
  optional Context, and moves the draft to runs/proposals/. Repository defaults come from
  workspace `tools/chief.toml [repos]`; tool, budget and optional `trust` also come from that file. The request
  carries every choice explicitly. Missing repo/checks remain placeholders, never guesses.
- Check prefill extracts inline code spans and complete fences whose info string is sh,
  bash, shell or console. A shell fence is one script/check (preserving multiline semantics).
  Console prompts are removed and unprompted output is ignored when prompts exist. Untyped
  and other fences are expected output, never checks. The request list is frozen at apply;
  differences in order or content are prominently shown for the researcher's review, not
  silently replaced or refused. When expected-output fences are present, a comment above
  the draft checks and an advisory Note in decide explain that checks pass on exit status
  only and show an explicit output comparison example. They do not rewrite the checks.
- Contract derivation follows the target Claim's revision chain and uses the current
  successor's Statement, retaining the original target and current ID in the section title.
- `toulmin decide` shows the full contract, check comparison, task ID, Spec's G3 item and
  a reminder that `chief watch` must run. It also shows whether Chief may confirm the worker's
  folder-trust prompt (`trust: false` by default). Refuse missing/non-todo/non-in-progress Specs,
  unmet/unknown G3 items, invalid repositories/base branches, empty/placeholder checks,
  occupied task IDs and prior live/unknown tasks for this Spec. Refusals and skip write nothing.
- L3 `application/build.py` coordinates the protocol and `adapters/chief.py`. Apply rechecks
  the preview and serializes startup with the project writer lock. It records applying,
  archives contract.json and request.json, calls `<command> new --from FILE --id ID
  [--base-branch B] [--trust]` from the workspace, archives stdout/stderr, and records applied
  or failed. `--trust` is passed only for an explicit true request value; configuration only
  prefills new drafts. After a non-zero exit, timeout or OSError, recheck the task ID. If a
  task exists with the same repository, record applied and report that Chief returned an
  error but the task exists, keeping its message in chief-new.txt. If no task exists, record
  failed and say the task ID is free. Unknown or mismatching state is reported without a
  free-ID claim. A failed request keeps its archive and message; a new request may retry. Spec status stays
  unchanged. No model/effort fields are sent to Chief.
- An interrupted retry checks the archive's request identity, frozen contract and Chief
  configuration. A task.json with the same task ID and repository is recorded rather than
  started again. A changed request/configuration/contract or unreadable state is refused;
  restore the frozen inputs before recovery. A missing task can resume startup. An archive
  that was only partly written is reported, never silently repaired.

`tools/chief.toml` is optional, workspace-owned integration configuration, never read from
the researcher's personal config or Chief config:

```toml
command = "python3 ~/aoe-chief/chief.py"
home = "" # empty: $AOE_CHIEF_HOME, otherwise ~/.local/state/aoe-chief
tool = "codex"
trust = false # optionally confirm the worker's folder-trust prompt, never edits/commands
budget = {rounds = 15, hours = 4}
verify_timeout_seconds = 600 # per independent check; positive finite seconds
[repos]
example = "/absolute/path/to/code-repository"
```

Command words are parsed without a shell; home-directory prefixes are expanded. The resolved
home is passed as AOE_CHIEF_HOME to Chief so collision/recovery reads and CLI startup agree.
Chief startup has a 120-second process-group timeout. Toulmin never directly writes Chief
state; only the researcher's apply invokes Chief's documented creation command. The project
guide directs agents to draft requests and never run Chief themselves. Import, verification,
Chief map/card/rule-table integration and live trials remain separate slices.

Compatibility is additive as documented in formats.md; no migration or existing object edit.


### R8 B3 — Chief state, research moves and confirmed result import (L1 additive, L2, L3)

L2 reason: the researcher needs to see an implementation task's state beside its Spec and
bring its report into the research network without hand-carrying files. `build_facts`
rebuilds the latest applied build request/task and import disposition per Spec from workspace
files only. `BuildTask`/`BuildReview` are tool-independent snapshots; L3 reads Chief's task.json
and injects them into map, decide and AoE card refresh. L2 never reads an external Chief home
or invokes git/Chief. Without an injected snapshot, it reports “Chief state not read”. Missing
fields stay null/not reported; malformed or unreadable state is explained, never guessed.

The shared next_moves table adds rows after pending proposals and stage warnings, preserving
existing rows' wording and MOVE_LIMIT. A build-stage Spec with its G3 item met and no pending
request/applied task suggests drafting a build request. Needs-you names chief inbox; review
names chief close / chief nudge; done names import in decide; abandoned names failed import
or re-request. Running tasks appear below their Specs, not as moves. Map watch also observes
external state changes. Read failures are diagnostics, not claims that research data is invalid.

Only the researcher starts an import: the “Chief result ready” decide item or
`toulmin build import NAME S-NNN --confirm --confirmed-by ACTOR` (without --confirm: preview,
no writes). Fresh imports require done/abandoned state and a matching applied build request.
The adapter reads task facts, checks the frozen repository, pins review.head or the task's
branch tip, reads git history/diffstat, and collects review/progress text. Missing optional
material is recorded explicitly; moved repositories or mismatching task repositories refuse.
The task's current state is read again on apply; changed preview inputs refuse before mutation.

L2 publishes the frozen archive and import.json applying record, then an implementer Run,
then the follow-up drafts, then marks the import applied. The workspace journal retains the
first actor and exact artifact hashes. Replay reuses a Run naming the archive and byte-matching
drafts, including after a crash between publication and journal update. A differing artifact,
Run or draft is reported without repair/overwrite. A completed receipt names an existing Run;
imports never create a second Run or second set of drafts for that task/request.

Done produces model-asserted computation Evidence on the Spec's current Claim, a Decision
draft related to the Spec, and a ruling proposal to awaiting-acceptance. The ruling names both
other drafts by filename; each resolves only after the researcher's apply created its formal
object. Abandoned produces a failed Run and no follow-ups. Import does not change the Spec,
Claim, stage or Evidence grade. Chief's report/cross review is not independent acceptance.

Decide rescans after applying an import, offering new Decision → Evidence → ruling proposals
in that same pass. Each still has its own apply/reject/skip/quit choice. Existing skipped
items remain skipped during that pass. Applying the ruling with its active Decision and test
Evidence can satisfy G4; G5 remains separate. Decide's existing optional project-session
notice includes imported task/Run IDs. Import never closes, nudges or answers a Chief task,
never runs checks, and never pushes or merges. Verification remains the later B4 slice.

Formats and compatibility are documented in formats.md; no existing-object migration is needed.


### R8 B4 — Independent execution of frozen checks (L1 additive, L2, L3)

L2 reason: a Chief completion report/cross review establishes the implementer's report (G4),
while G5 needs an independently launched reproduction of the checks. File-derived verification
facts offer “Verify S-NNN in toulmin decide” when the Spec is awaiting-acceptance, its latest
applied import names a head, and that head has no passing verification. An interrupted journal
is offered for recovery. Failure adds the advice to return the task with chief nudge or draft
a new build request. These rows retain existing ordering and MOVE_LIMIT; no gate changes occur.

L3 prepares a preview from the applied request's archived contract.json, never from the
current Spec's Acceptance criteria. It lists repository, imported commit, exact checks and
per-check timeout, and says: “runs code written by an AI worker on this machine, as you,
without network isolation”. `tools/chief.toml verify_timeout_seconds` defaults to 600 and must
be positive and finite. Fresh previews pin the Spec/contract digests and current target Claim;
changed inputs refuse before execution. The checks and execution settings are then frozen
in verify.json. No Chief invocation or Chief state write is needed.

Only the researcher's apply (`toulmin decide` or `toulmin build verify NAME S-NNN --confirm`)
starts execution. The adapter clones locally using `git clone --quiet --no-hardlinks`, outside
the workspace/source repository, checks out the imported commit with `--quiet --detach`, and
runs every command with sh -c in its own process group. It kills/reaps the group on timeout
or interruption. Output capture is file-backed; archived stdout and stderr are each limited
to 64 KiB. The clone is removed on success, failure or interruption. A failure does not prevent
the remaining checks from being recorded; any nonzero exit/timeout prevents passing proposals.

L2 journals and publishes only workspace records. Immutable output/environment checkpoints
precede the journal pointer update. A partial attempt is retained and rerun from scratch only
on another researcher apply; a completed execution is finalized without repeating checks.
Run publication is recovered by archive output, and matching existing drafts are reused,
never overwritten. The original confirming actor is preserved. A completed failed/timed-out
execution is a completed verifier Run with no proposals; clone/setup failure leaves an
applying journal that can be retried. Failed attempts never satisfy passing-head readiness.

Passing execution proposes Decision → verified Evidence → passed ruling. Decide rescans and
offers all three, one at a time. Evidence targets the current Claim; its method names the
frozen Spec checks, fresh clone and full head, and its artifacts/provenance cite the output
and environment. The ruling resolves the applied Evidence filename as in B3 and preserves
existing evidence links. An active Decision naming the Spec is still required. Applying that
ruling can satisfy its G5 item; verification itself changes no Spec status, Claim or stage.

**Independence and limits:** these are the checks frozen for the researcher's apply, executed
by Toulmin rather than the AI worker/Chief, in a fresh clone at a pinned imported commit.
This reproduces them independently of the worker's worktree and narrative. It does not prove
that weak checks establish the Claim, that results carry to other environments, or that the
code is safe. Execution uses the same machine/user and has no network isolation; a fresh clone
is not a sandbox. The researcher judges check adequacy and applies the formal ruling. Agent-run
implementation tests demonstrate this behavior, not researcher acceptance or independent review
of Toulmin's own implementation.

Formats/compatibility are in formats.md; no object migration or new model invocation is involved.
