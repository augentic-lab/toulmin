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
adoption are later tasks; a fresh workspace's AGENTS.md is still the shared template.

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
