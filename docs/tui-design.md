# Toulmin TUI design proposal

Status: Q25–Q29 approved for implementation on 2026-11-02. UI1 is in development.
Task: UI0. Python and a terminal interface are agreed directions; the researcher approved Q25–Q29 and authorized implementation. Auxiliary file contracts are specified and validated in their implementation slices.
Basis: [design](design.md), [formats](formats.md), [protocols](protocols.md), and the researcher's requested create → discuss → brief → claims → review → resolve workflow.

## 1. Product goal and scope

Provide one keyboard-first research workspace that starts from a terminal and keeps the researcher focused on questions, arguments and decisions. File paths, YAML and object IDs remain inspectable but are not prerequisites for ordinary use.

The first release covers project creation/opening, exploration chat, brief editing, proposed key claims, independent reviews, objection intake/rulings and handoff. All interface labels are English. Researchers may type in any language; maintained research documents default to English, while raw sources retain their original language.

Pixel styling means block borders, restrained colors, geometric icons and optional small activity animations. Body text stays legible. No game engine, browser, web server, score, experience meter or rewards for generating more claims are needed.

Not part of this release: automatic gate decisions, autonomous research, web browsing by the exploration model, reference-manager integration, multi-user editing, automated synthesis/crossval/calibration (unfinished C4/C5), or Build/Accept workflows. Existing CLI operations remain available.

## 2. Starting and opening projects

Proposed command: `toulmin tui [--root PATH] [--project SLUG]`.

- No project argument opens Home, centered on `New Project` and `Open Project`.
- `New Project` asks for workbench location, project slug, motivation and goal. `Import from File` accepts UTF-8 Markdown/text for the first release, previews content and lets the researcher edit it. Other formats report an unsupported-format message.
- Choose an initial model, but do not start an invocation until the researcher presses `Start Discussion`.
- Save the goal in PROJECT's existing Goal section, respecting its 40-line constraint. Put the full motivation in the initial brief's Problem/Why now sections. Preserve imported source bytes in an archived project input directory; never modify the source file.
- Initialization is followed by a recoverable setup step for these supplied values. If setup fails after init, retain the initialized project and offer `Resume Setup`; do not claim a completed setup or delete existing files.
- `Open Project` selects a workbench and one of its project directories. Validate the selected project, show the last handoff and outstanding work, then offer `Resume`.
- Invalid data opens a diagnostic view with file/field details. Reading remains available; affected writes are disabled until the issue is resolved.
- An explicit file import is permitted from outside the workbench and copies the selected file inside it. This does not relax core object/reference path confinement. Use a text path input plus a terminal file browser, without assuming a graphical file picker.

## 3. Workspace and visual language

Target layout: at least 120 columns × 36 rows. Dimensions below are illustrative, not a fixed terminal requirement.

```text
+ Toulmin | tail-latency | Explore | Saved ------------------------------+
| Steps       | Discussion                         | Research Brief      |
| Setup       | Model: configured-model            | Draft / Saved       |
| > Explore   |                                    | Problem             |
| Brief       | Researcher: ...                    | ...                 |
| Key Claims  | Assistant: ...                     |                     |
| Review      |                                    | Why now             |
| Resolve     |                                    | ...                 |
| Handoff     |                                    |                     |
|             | [ Write a message...             ] | [View Changes]      |
|             | [Send] [Stop] [Propose Brief]       | [Apply] [Dismiss]   |
+ Tab: Next pane | Ctrl+Enter: Send | F1: Help | Ctrl+Q: Quit ------------+
```

Three independently scrollable areas: a 16–20-column navigation rail, a flexible main pane and a roughly 35–40% inspector. Use Textual containers and layout styles, not a custom full-screen drawing engine.

At 80–119 columns, collapse the inspector into a toggled panel. Below 80 columns or 24 rows, offer a readable compact single-pane view and a resize notice. Navigation, saving and cancellation must remain reachable. Width-sensitive behavior is a prototype acceptance target, not a verified capability of this application yet.

Use a dark slate background, warm light text, cyan focus, amber pending items and red failures. Every color has a text label or symbol. Support an ASCII border fallback and reduced motion. No mandatory blinking or typewriter delay. Keep terminal font selection under the user's control; do not require a pixel font for prose or CJK text.

Keyboard contract: Tab/Shift+Tab moves focus; arrows navigate lists; Enter activates buttons; Enter in the composer inserts a newline; Ctrl+Enter sends, with a visible Send button fallback; F2 toggles the inspector; Esc closes a modal; Ctrl+Q starts the exit flow. Global shortcuts must not steal normal editor keys. Mouse interaction is optional convenience. Verify paste, selection and IME behavior in actual target terminals; automated tests alone cannot establish these.

## 4. Navigation and research stages

| UI step | Main pane | Inspector | Completion evidence |
| --- | --- | --- | --- |
| Setup | Name, location, motivation, goal | Setup preview | Required values saved |
| Explore | AI discussion and unresolved questions | Brief draft / saved brief | Researcher chooses to consolidate |
| Brief | Edit, compare and accept proposed sections | Sources and open assumptions | Researcher marks the brief ready for claim review |
| Key Claims | Edit/merge/remove candidate claims | Linked brief passages and validation questions | Researcher confirms chosen formal Claims |
| Review | Personas, models, input preview, task progress | Submitted snapshot / individual review | Selected tasks terminate and outputs are archived |
| Resolve | Intake choices, responses, ruling drafts | Raw source, target Claim, Decision | Each chosen issue has an explicit disposition or remains visibly pending |
| Handoff | Session summary and next step | Proposed PROJECT changes | Researcher applies handoff |

These are revisitable views, not new PROJECT.stage values or a forced wizard. Research stages remain explore, critique, brief-final, build, accept and done. Clicking Review or finishing a batch never advances a gate. Show the persisted research stage separately from the selected view.

G1 readiness remains governed by the existing design, including core problem/magnitude/mechanism/novelty claims. The UI may warn about missing coverage without fabricating claims to satisfy a checklist. First release does not add a stage-advance command; an explicit researcher Decision and the existing stage-edit protocol remain authoritative.

## 5. Exploration and brief authoring

Exploration is a new model operation, distinct from independent review. A visible context summary shows the goal, selected brief version, conversation range and explicitly attached files. The assistant helps clarify the problem, scope, alternatives, assumptions and a minimal experiment; it cannot rule on evidence grades or research status.

Proposed interaction:

1. Persist the user's submitted message before launching a model task.
2. Build and archive the exact request context; show the chosen model and `Running` state.
3. Display response deltas if supported, otherwise display honest waiting progress and then the complete response. Do not simulate streaming.
4. Save the final answer and invocation provenance. Partial output stays marked incomplete after cancellation/failure.
5. `Propose Brief` explicitly asks for a new report draft based on a selected conversation range. It does not rewrite brief.md automatically after each message.
6. The inspector offers `Saved`, `Proposed` and `Changes`. The researcher edits, applies or dismisses the proposal. Applying validates the base-file hash, preserves the previous version and records the chosen change.

Manual editor changes auto-save to a working draft, with `Saving`, `Saved` or `Save Failed` feedback. Publishing the draft to brief.md requires `Save Brief`. This separates recoverable typing from a report approved for review. Closing and reopening restores the working draft; no hidden database is required.

For the first release, use file-backed conversation reconstruction rather than relying on vendor session resume. Each turn gets selected context and a new invocation. Long histories require an explicit selection or a reviewable summary with links to the retained original turns; never silently discard history. Changing models starts the next turn with the same visible context selection.

The exploration model has no filesystem write tools. The application validates and writes proposals after the researcher's action. Model names and tool session IDs are provenance strings, never core control branches.

## 6. Key Claims: why and when

The brief is the primary authoring surface. Claims are a small set of propositions that make review, evidence and revision traceable. For example, “queueing is the bottleneck” and “the proposed mechanism reduces queueing” may need different evidence and receive different objections.

Only extract candidates when the researcher chooses `Prepare Review` or `Extract Key Claims`. Do not turn every chat sentence into an object. Each candidate shows its statement, type, importance, source passage and unresolved validation question. Edit/merge/remove candidates before confirmation; allow a human-authored candidate too.

Confirmation creates formal Claims through existing intake, preserving model Run provenance for AI-derived content. Extraction is not evidence that a claim is true. Proposed candidates live under runs until confirmed. IDs are secondary display details.

Once reviewed or linked, substantive Claim changes use the existing supersession workflow: create a successor and a Decision. Show that Evidence/Objections stay attached to the predecessor; do not silently transfer them. Reports may be revised independently, but explicit claim references and review snapshots reveal stale material.

## 7. Independent review and resolution

`Review` presents the four current personas, configured model choices, selected current Claims, exact input manifest and number of persona × model sessions. Start requires one explicit approval of that plan; display subscription use without inventing a monetary estimate.

Snapshot the approved inputs before starting. All members of a round use that snapshot even if the researcher later edits the report. Preserve the input paths and hashes with the archived prompt. The existing prompt already inlines inputs; a structured snapshot manifest adds an inspectable record.

Exploration history, handoffs and other reviews are excluded from reviewer inputs. Current manifest constraints remain authoritative. Keep discussion-model and reviewer configurations separate. Codex global-instruction isolation is an existing unresolved live-verification issue and must be shown as such, not advertised as proven isolation.

Each task card shows persona, configured/reported model, queued/running/completed/failed/cancelled status, elapsed time and archive links. A parser failure is distinct from a failed model invocation: preserve raw output and offer manual intake. No fabricated percent-complete indicator for model generation.

`Resolve` displays objections grouped by source review, target and severity. Use existing intake semantics for `Take`, `Reject` (reason required) and `Partly`; allow severity adjustment with an explicit recorded outcome. A preview lists all writes before confirmation. Taking an objection creates an open issue, not an agreement that its conclusion is correct.

After intake, the researcher may draft a response or Decision and use the existing ruling protocol. The screen explains required fields and preserves earlier responses. Existing immutable intake outcomes remain immutable; later judgments are Decisions rather than edits to history. Pending drafts must be listed by parsing the selected reviews even before their first intake record, filling the current status-view discoverability gap without inventing a second index.

Automatic synthesis, crossval and calibration stay unavailable until C4/C5 exist. Show raw reviews individually rather than presenting an unimplemented combined verdict.

## 8. Python/Textual architecture

Proposed dependency: Textual as an optional `tui` extra, imported lazily by the launch command. Resolve a compatible version against Python >=3.12 and commit the lockfile at implementation time. Do not add or pin an untested version in this design session.

```text
Typer CLI (L3)       Textual TUI (L3)
         \          /       |
       shared application services (L3)
           |                 |
     protocols (L2)    model adapters (L3)
           |
       core/files (L1)
```

- `src/toulmin/tui/`: App, Home/Workspace screens, dialogs, pane widgets, styles and UI messages. Textual imports remain here.
- `src/toulmin/application/` (proposed L3): task coordination, structured application events, model dispatch and protocol calls. Both CLI and TUI use it. Do not parse CLI stdout or shell out to `toulmin` to perform domain operations.
- `protocols/`: UI-independent setup completion, conversation-context selection, proposal application and review-snapshot logic. No Textual imports, model calls or terminal printing.
- `core/`: versioned records, validation and durable file operations. Existing research object schemas remain authoritative.
- `adapters/`: process/session execution, stream parsing when supported, explicit per-task cancellation and completion results. Refactor the current batch runner incrementally; preserve its CLI behavior.

Suggested components: Screen/ModalScreen for navigation and confirmation; Input/TextArea for fields and multiline editing; Markdown for read views; ListView/DataTable for claims, review tasks and choices; standard buttons and scroll containers. Escape untrusted terminal control sequences in model text and logs.

An app-level task manager owns jobs independently of the currently visible screen. Textual Workers keep blocking work off the UI loop and post typed messages back. A cancelled worker alone is not proof that a subprocess stopped: cancellation must terminate/reap the corresponding process group, flush available output and record a terminal task state. Do not reuse the current global stop-all operation for cancelling a single review card.

Events include TaskStarted, TextDelta, TaskFinished, TaskFailed and ArchiveSaved, each with task/project identity and ordering. Coalesce display updates and bound the render queue; preserve durable source output separately. Late events cannot update a newly selected project's pane. Serialize project mutations and preserve existing lock/conflict checks.

## 9. Proposed persisted records and recovery

These are proposed auxiliary formats, not approved additions to the seven research object schemas. Specify exact field/type validation in formats.md before implementation. Every new record has its own schema_version; do not overload PROJECT with chat history or UI state.

```text
projects/<project>/runs/
  conversations/<conversation-id>/
    conversation.md                 # title, creation time, selected context references
    turns/<turn-id>/
      user.md                       # saved submitted message
      task.md                       # invocation state, request ID, archive/Run references
  <UTC>-explore-<unique>/
    prompt.md / output.md / task.md  # exact input, response, task recovery state
  <UTC>-brief-<unique>/
    proposal.md / before.md / after.md / application.md
  drafts/                           # existing object drafts plus editable working brief
  <UTC>-review-<persona>-<model>/
    prompt.md / output.md / inputs.md / intake.md
  R-NNN.md                          # existing completed/failed Run metadata
```

Use stable request IDs to reconnect a turn with its archived output and Run, without duplicating an invocation after restart. Streaming output is visibly partial until finalization. Formal Run metadata retains completed/failed only; cancellation/interruption uses failed with an explanatory Failure section. Queued/running/cancelled task states belong to auxiliary task records, not a new Run enum.

A running task found after restart is interrupted until its process identity/liveness is verified; do not blindly relaunch or kill an unrelated PID. Offer explicit retry as a new attempt linked to the old one. Recovery may finish a validated archive publication without invoking a model again.

Brief application uses durable before/after images and an intent record, with compare-before-replace and recovery from exact known states. An external edit produces a conflict dialog with reload/compare options, not last-writer-wins. Reuse storage primitives but do not pretend the handoff transaction directly implements arbitrary brief transactions.

Recent-project lists, selected pane and scroll offsets are optional disposable local preferences; do not store research decisions there. No data migration is needed for unchanged existing objects. New auxiliary records must live in runs subdirectories so old object scanning ignores them. AI-assisted report authorship changes protocol semantics and therefore needs an explicit L2 change note.

Exit flow: flush drafts, offer `Handoff`, `Quit without Handoff`, or `Cancel`; while tasks run, additionally offer waiting or explicit stop-and-save. Never imply that chat auto-save completes a handoff or Git commit. Handoff uses the existing confirmed protocol. First release may leave Git commits as explicit terminal operations, showing this remaining step clearly.

## 10. Existing workbenches and rollout

Opening a workbench must not call init over edited templates. Compare required role/config capabilities and offer a migration preview: add missing files, show diffs for changed templates, preserve backups and require explicit choices for conflicts. Until a reviewed update is applied, disable only the affected features; allow inspection and existing functions.

Fresh workbenches receive the new exploration role and reviewed templates. Old workbenches must remain readable without the TUI. The TUI extra must not make existing CLI use depend on Textual. Shipping a TUI does not complete C4/C5 or constitute research-stage acceptance.

## 11. Implementation slices and executable acceptance

Implementation starts only after design approval. Each slice includes appropriate existing regression checks, progress updates and a task-scoped commit.

| Task | Deliverable | Acceptance |
| --- | --- | --- |
| UI1 | Textual shell, Home, create/open, navigation, visual theme | With fake services, create a project from typed text and an imported file, reopen it, preserve values; keyboard-only navigation works at 120×36 and 80×24; compact view retains save/quit; normal CLI help works without Textual installed. |
| UI2 | Durable discussion and cancellable model jobs | Fake adapters exercise multi-turn context, incremental and final-only responses, timeout and cancellation; UI remains responsive; switching views does not kill jobs; restart preserves messages and partial output without duplicate model calls; per-task stop leaves other jobs running. |
| UI3 | Brief drafts, change preview and key-claim confirmation | AI output never silently changes brief.md; approved application survives injected write interruption; external edits refuse overwrite; unconfirmed candidates remain drafts; confirmed Claims trace to the extraction Run; revising a linked Claim preserves the predecessor. |
| UI4 | Input snapshots, review cards and resolution | Two personas × two fake models get four independent snapshot-based tasks; editing brief during execution does not alter their inputs; one failure preserves successful outputs; take/reject/partly and replay behave like CLI; status and stored files agree. |
| UI5 | Handoff, workbench upgrade and real trial | Existing edited templates survive opening; upgrade conflict preview preserves originals; confirmed handoff resumes from files in a fresh session; interruption recovers; a researcher completes one real idea-to-review-to-resolution cycle entirely in the TUI except login/Git, then explicitly accepts usability. |

Use pytest with Textual's headless App.run_test/Pilot for interaction and terminal-size tests; add async test support only when resolving implementation dependencies. Add a few visual snapshots for stable layouts, not snapshots as substitutes for state/provenance assertions. Fake model processes remain the default. Supervised real-model tests require explicit quota authorization. Manually verify terminal restoration, keyboard shortcuts, CJK/IME, paste and reduced motion.

The initial vertical slice is UI1–UI3 with fake model output, followed by a supervised real discussion. UI4 reuses C1–C3 without waiting for C4. Do not run TUI work and unfinished C4/C5 as an implicit combined scope.

## 12. Decisions for review

| ID | Proposal | Consequence |
| --- | --- | --- |
| Q25 | Add TUI plus exploration, brief proposal and claim-extraction invocations to the allowed scope; models still produce archived drafts only | Revises AGENTS scope and L2 role contracts; existing Q19 covers review/crossval/synthesis only. |
| Q26 | Make the brief the primary surface; confirm extracted key claims when preparing review | Retains the claim network and G1, removes manual object administration from ordinary exploration. |
| Q27 | Use stateless, file-reconstructed model turns; support true streaming only where the adapter can provide it, with an honest final-only fallback | Adds conversation/task contracts without dependence on vendor session resume. |
| Q28 | Require explicit application of AI report proposals and formal objects; auto-save only conversation and working drafts | Revises the handwritten-brief convention to researcher-controlled assisted authoring; no automatic gates. |
| Q29 | Implement UI1–UI5 next, leaving C4/C5 pending; retain terminal login and Git for the first release | Defines a bounded usable product slice instead of adding all remaining automation. |

Q25–Q29 were explicitly accepted together on 2026-11-02. They are the implementation baseline; completion of each slice still requires its stated validation.

## 13. Evidence and references

Verified by repository inspection: current object/claim-revision protocols, draft/intake/rule/status/handoff commands, review manifests and completed/failed Runs exist. At design time, the adapter used process.communicate and returned a complete response; persistent exploration, streaming events and TUI components were absent. UI1 now implements the terminal shell, setup and inspection; persistent exploration and streaming remain pending. The prior C3 progress entry records live reviews and 478 passing tests; these were not rerun for this design.

UI1 implements the shell, setup archive and inspection described above. UI2–UI5 remain an approved plan, not implemented behavior; acceptance results are recorded in PROGRESS.md.

Official Textual references reviewed for this proposal:

- [Screens and modal navigation](https://textual.textualize.io/guide/screens/): screen composition and dialogs.
- [TextArea](https://textual.textualize.io/widgets/text_area/): multiline editing.
- [Workers](https://textual.textualize.io/guide/workers/): background work and UI messaging; thread cancellation needs explicit cooperation.
- [Testing](https://textual.textualize.io/guide/testing/): headless interaction, terminal-size tests and optional visual snapshots.

## 14. Visual direction research after UI1

Status: research and recommendations only; the researcher rejected the current visual result.
No replacement theme or layout has been approved or implemented in this session.

References consulted:

| Reference | Proposed lesson for Toulmin | Boundary |
| --- | --- | --- |
| [Posting](https://posting.sh/) and its [themes guide](https://posting.sh/guide/themes/) | Clear work areas, contextual keyboard actions and semantic theme colors; keep the central task visually dominant | An API client's dense controls should not become the research conversation layout |
| [Superfile](https://superfile.dev/) | Use a consistent panel/preview system and a restrained theme; differentiate focus from inactive surfaces | Multiple equally prominent file panes are unsuitable for a conversation-led workflow |
| [Cogmind official press kit](https://www.gridsagegames.com/press/sheet.php?p=cogmind) | Explore character-grid identity, compact status labels and retro game framing for Home and navigation | This is a game reference, not evidence of compatibility with ordinary terminal rendering; avoid copying its density, effects or assets |
| [Crush](https://github.com/charmbracelet/crush) | Further reference for a conversational terminal tool's identity and model/session context | Its implementation stack is not a reason to replace Textual |

Verified: official project pages were consulted; image search supplied additional screenshot references.
Direct downloads of the Superfile and Cogmind images were refused (403/406); no local visual
inspection of those originals or installation of these tools was completed. These references
support a direction to explore, not a claim that the proposed Toulmin design is validated.

Design judgment from the UI1 renders: oversized top controls compete with content; duplicate
step navigation wastes space; uniformly bordered panels flatten hierarchy; saturated Markdown
accents compete with body text. A replacement should address hierarchy before adding decoration.

Recommended direction (Guess): a quiet retro research terminal. Use a compact title/status line,
a narrow step rail, dominant conversation space and a subordinate brief inspector. Place a small
character emblem and New Project/Open Project choices on Home. Keep body text neutral, reserve
one accent for focus and a second for status, and style Markdown explicitly. At narrow widths,
show one primary reading surface with switchable context. Pixel details belong at the edges.

Next deliverable: two comparable static Home/workspace concepts using the same English sample
content: a restrained modern terminal and a retro laboratory terminal. Review these before code
changes; do not treat generic visual examples or high-resolution artwork as tested TUI output.
