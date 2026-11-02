# Toulmin TUI v2: a guided research workbench

Status: **proposed for researcher review**, 2026-11-02. The researcher authorized UI-R2 and its UI-R3 uncertainty-driven refinement; a [standalone memory-only prototype](../prototypes/README.md) now demonstrates this interaction. Production behavior and Q30/Q31 scope remain pending feedback.
Task: UI-R1. This proposal revises the interaction model of [the original TUI design](tui-design.md).
The approved principles, file formats and confirmation boundaries remain authoritative.
The user's clarified requirement is guidance: see the research process, know what is possible,
and resume purposeful work without remembering commands or reconstructing a conversation.

## 1. Purpose and success

Toulmin helps one systems researcher move from an uncertain idea to a defensible brief and,
eventually, independently verified engineering results. The brief is the primary deliverable;
Claims, Evidence and Objections make its reasoning inspectable. More chats, more objects and
more completed reviews are not measures of research quality.

On any normal screen the researcher should be able to answer:

1. What am I trying to find out, and where does this activity fit in the research?
2. What can I do now, what does the suggested action accomplish, and what happens if I choose it?
3. What is saved, what still needs my judgment, and what prevents the next research decision?

Success targets (not yet measured): a researcher can identify their next action within ten
seconds of reopening a project, can finish the basic loop without typing paths/IDs/CLI commands,
and can explain why a model answer has not automatically become evidence or a stage ruling.
A fresh model or no model at all must not erase these affordances.

The earlier synthetic CLI trial demonstrated storage plumbing only. It did not test these
needs and does not justify replacing this interface with a generic AI terminal.

## 2. Separate three meanings of progress

| Meaning | Visible representation | Authority |
| --- | --- | --- |
| Research stage | Header: `Stage: Explore`; Overview shows the complete lifecycle | Stored PROJECT.stage; changes require researcher Decision |
| Current activity | Highlighted work view: Explore, Review, Resolve or Validate | Navigation; never a stage change |
| Action or artifact state | `Draft`, `Needs your decision`, `Running`, `Saved`, `Failed` with specific subject | Derived from files/task records; never an overall research score |

Do not put a check mark next to Review merely because a process exited. Say `2 outputs saved;
3 suggestions need a decision`. Do not mark Explore permanently complete: later objections
can reopen a question. Show `Previously reviewed · brief changed` when relevant inputs change.
Distinguish stale input from a failed review; historical outputs retain their value and sources.

There is no completion percentage for research. Counts describe actual objects/actions only.
A measurement, an uncertainty or a reasoned rejection can all be productive outcomes.

## 3. Information architecture

Home keeps `New Project` and `Open Project` prominent. Recent projects, when available, include
the saved next step, not a decorative progress bar. Creation asks for a title/slug, motivation
and goal, with optional file import. Location uses a visible default with an Edit action;
model settings are requested at the first model call, not as a prerequisite to writing.

The workspace has five work views:

| View | Question it answers | Main content | Typical primary action |
| --- | --- | --- | --- |
| Overview | Where did I stop, and what needs attention? | Saved next step, open work, recent changes, lifecycle | `Resume: define the workload` |
| Explore | What exactly am I proposing, and why? | Task-scoped discussion or brief editor | `Send` or `Save Brief`, according to the active surface |
| Review | What should be challenged, and by whom? | Statements to review, input preview, reviewer setup/results | `Prepare Review`, then `Start N Reviews` |
| Resolve | What do I do with this criticism? | Untriaged suggestions or recorded issues, clearly separated | `Record Issue` or `Review Decision`, according to state |
| Validate | What observation would change my mind? | Minimal experiment plan, result material and evidence links | `Save Validation Plan` or `Review Evidence` |

The rail always shows these views with meaningful counts, e.g. `Resolve · 3 untriaged / 1 open`.
It contains no second dropdown duplicating navigation at wide sizes. At small sizes a single
view selector replaces the rail. `Brief`, `Statements`, `Evidence` and `History` are artifact
views accessible from their task and from Overview, not additional compulsory workflow stages.
Setup moves to project settings after creation. `End Session` is always accessible, not a final
step that only becomes available after every objection is settled.

Overview also shows the canonical roadmap:
`Explore -> Critique -> Brief final -> Build -> Accept -> Done`.
Each gate opens an explanation of its purpose and recorded conditions. Later Build/Accept
capabilities are labeled planned in this release; they are not clickable empty workspaces.
Planning/recording a small validation experiment is available during Explore and Critique and
is not equivalent to entering Build. Full engineering-agent orchestration remains deferred.

## 4. Guidance that does not take over the research

Every task surface contains a short task heading, the reason it matters, a primary action and
at most two visible alternatives. Less frequent actions live under `More actions`. This limit
is per task, not a restriction on editing controls. Actions use concrete verbs and objects.
Avoid generic `Next`, `Done`, `Accept` or `Apply` when the affected object is unclear.

Recommended priority, computed without an LLM:

1. Recover incomplete saves or explain corrupt inputs before offering affected writes.
2. Surface interrupted tasks and saved-but-unconfirmed proposals; never restart them automatically.
3. Show the researcher's saved next step, with a warning if its linked context is obsolete.
4. Suggest triaging new reviews or examining open fatal/major objections.
5. Offer a missing research step, such as defining a test or preparing a review.

Safety diagnostics precede the recommendation; they do not erase the researcher's intended task.
If a model job is running, keep its compact status visible while allowing unrelated work.
AI-generated research suggestions appear separately as `Assistant suggestion`, with reasons;
they cannot change the authoritative action availability or record completion.

For every condition show `Present`, `Missing`, `Needs judgment` or `Unknown`, with the source
and a way to act. An existing section is only `Present`; its scientific adequacy needs judgment.
An LLM saying the question is novel does not satisfy a novelty check. A parser cannot determine
that a kill criterion is useful. Corrupt data yields `Unknown`, never a reassuring zero count.

Two examples of different restrictions:

- `Start Review` unavailable: no selected statement. Explain the dependency beside the action
  and offer `Add a statement`. Authentication failure offers a setup instruction and Retry.
- G1 magnitude coverage missing: allow continued discussion and a scoped review of existing
  statements, label it `Exploratory review`, and keep PROJECT.stage unchanged. Do not invent a
  magnitude Claim or pretend that the formal G1 gate has passed.

Ordinary activities remain revisitable. Going back to Explore does not roll the research stage
back. Returning a formal stage to Critique requires a separate recorded researcher decision.
The application does not silently weaken gate conditions or use a dismiss button to pass them.

## 5. Walkthrough: one small question, a complete loop

Example: "Would caching repeated queries reduce p95 latency?" This is illustrative content,
not a claim that caching helps. The researcher can stop after any step.

| Moment | What the researcher sees | Action and consequence |
| --- | --- | --- |
| Create | Goal and motivation, a preview of what will be saved | `Create Project` archives the input and saves the initial brief; no model call |
| Orient | `Define the workload` with prompts about workload, baseline and the observation that would matter | Write directly or choose `Discuss this question`; the model context is visible |
| Explore | Discussion beside the saved brief; unresolved points remain visible | `Draft Brief Changes` explicitly requests a proposal; chat alone changes no formal text |
| Consolidate | Saved/proposed brief comparison with source turns | Edit, then `Save Brief`; only reviewed content is published, draft work remains recoverable |
| Prepare review | A small list of proposed statements with source passages | Edit/select statements; `Save 2 Statements` creates proposed Claims, not proven conclusions |
| Review | Persona/model choices, selected inputs, number of invocations | Approve the displayed plan; exact input snapshots and raw responses are archived |
| Triage | "Warm-up and hit rate are unspecified" with source and target | `Record Issue` creates an open Objection; `Dismiss Suggestion` needs a reason |
| Respond | Issue, affected statement and any supporting/refuting material | Choose `Plan a Test`, `Revise Statement`, `Write Response` or `Defer with Reason` |
| Validate | Baseline, cache warm-up, load, metric and rejection criterion | Save a plan; later attach actual results and explicitly review their evidential grade |
| Reassess | What changed and what remains unknown | Return to the issue or request another review; no automatic supported status |
| Leave/resume | Concise handoff and the next concrete action | `Save Handoff & Exit`; reopening shows that action and linked issue, not just the last chat |

Do not force four formal claims during initial brainstorming. Explain the four G1 coverage
questions when the researcher considers formal Critique: problem, magnitude, mechanism and
novelty. Unknowns stay unknown. A card such as "No size estimate yet" offers `Plan a measurement`
and `Keep exploring`, rather than a required field that encourages invented numbers.

## 6. Detailed action contracts

### Explore and brief

Discussion is attached to the visible research question. An optional prompt such as "What
would refute this idea?" helps start; it does not turn the conversation into a rigid interview.
Show selected context and model before sending. Long-context summarization is inspectable,
with links to original turns. No silent history loss or vendor session dependence.

The brief inspector defaults to Saved. Proposed changes have an unmistakable label and diff.
Typing saves a recoverable working draft. `Save Brief` publishes the reviewed draft; one explicit
action suffices, without a second generic confirmation dialog. External edits force a comparison
and rebase rather than overwrite. Record human edits and AI origins without confusing the two.

### Review preparation and execution

Use plain-language `Statements to review`, with "stored as Claims" and IDs in details. Explain
why a statement matters and what evidence could test it. Allow manual entry; AI extraction is
optional and invoked explicitly. Editing a linked Claim follows supersession, with a preview
of old Evidence/Objections that will remain on the predecessor.

Reviewer setup has two levels: a small visible plan based on an explicitly chosen/saved preset,
and expandable persona/model/input settings. Show actual configuration rather than silently
picking an expensive model. `2 personas x 1 model = 2 new sessions`; unknown monetary cost stays
unknown. First use requires choosing a configured model; reuse only previously approved choices.

Review sees the approved brief/Claims and role manifest, never exploration history or other
review outputs. Show per-job state and stop/retry controls. Successful jobs survive another
job's failure. A failed structured-output parse means `Output saved · manual triage needed`,
not `No issues`. No fake token streaming or fabricated completion percentage.

C4 synthesis exists in the CLI. Offer `Compare Reviews` as a secondary, separately approved
model action, not a prerequisite for reading originals. Group agreement is not evidence of
truth. Every item points to its original Run/draft label for intake. Show synthesis notes and
raw differences, including partial disagreement that the current group categories may hide.
Crossval remains optional; neither feature is required for the first guided loop.

### Resolve: separate two decisions

1. **Suggestion triage:** `Record Issue`, `Dismiss Suggestion`, `Record Edited Issue`, or leave
   untriaged. This maps to existing intake semantics; nothing is selected by default. A dismiss
   reason belongs to intake, not an invented rejected Objection status. Edited content requiring
   a manual Objection follows the existing partly/source linkage contract. Immutable intake
   outcomes are never rewritten.
2. **Issue response/ruling:** show the recorded Objection, response, related evidence and any
   Decision. Saving a response does not prove the issue resolved. Status changes use explicit
   ruling controls; the UI prepares required Decision fields and previews all writes together.

Use explanatory labels: `Response recorded (answered)`, `Objection accepted (accepted)` and
`Deferred (deferred)`. "Objection accepted" means the criticism was accepted, not that the
Claim was accepted. Revising a Claim requires a successor and Decision; never retarget evidence
or close the old Objection merely because the wording changed. A deferred major issue remains
visible with its rationale at gate review; do not equate deferral with scientific resolution.

`Save Decision` must state the intended status and affected objects. The convenience is hiding
YAML/IDs, not hiding consequences or fabricating a researcher's authorization.

### Validate: the missing connection in the first design

A response often needs an observation rather than more chat. Provide a compact plan editor:
question/target, baseline and controls, procedure, metric, and the result that would refute the
statement. Start with one experiment, not a project-management backlog.

`Save Validation Plan` stores the plan in the existing Claim.validation_plan with reviewed
provenance where model-derived. This is a new controlled write path, not already implemented.
Record what to do outside Toulmin; this release does not autonomously execute experiments.
When results are available, attach material/path/source, select supports/refutes and evidence
kind, then review the grade. `verified` requires actual verification details; importing a file
or receiving two agreeing model answers cannot assign that grade automatically.

Show `Plan saved`, `Results recorded`, `Verified evidence recorded` and `Claim ruling pending`
as different facts. Verified supporting Evidence can make a Claim eligible for supported;
it does not change its stored status. G2 may allow a pending experiment instead of evidence,
but that exception does not satisfy the supported/accepted conditions of an individual Claim.

### Gate review and handoff

Overview offers `Review Stage Readiness`, not an automatic advance button. For G1/G2, display
conditions, their sources, unknown judgments, deferred issues and proposed next stage. Forward
advancement with unmet/unknown required conditions is unavailable; continuing ordinary work is
always possible. When conditions are met, the researcher still chooses and records a Decision.
Human-attested semantic checks must be preserved in that Decision rather than become hidden UI
checkboxes. Recheck source hashes before applying the Decision and PROJECT update.

Stage-ruling UI/transaction support is a proposed scope addition. Existing handoff explicitly
cannot change stage. Do not implement stage advancement by misusing handoff or by adding a new
stage enum. Backward stage rulings need a reason and preserved history. Abandonment remains a
recorded Decision with retained files, not a deletion or an invented v1 abandoned stage.

`End Session` shows what is saved, remaining work and a concise editable next step, then offers
`Save Handoff & Exit`, `Exit without Handoff` and `Keep Working`. Running jobs require explicit
wait/stop-and-save handling. Disk-full/save failures keep the application open with recovery
choices; never silently discard draft text. Saving a handoff is not a Git commit. Where Git is
still external, show that separate outstanding action without making it block later inspection.

## 7. Layout and visualization before styling

Illustrative wide-screen structure, not a validated rendering:

```text
Toulmin / cache-study                 Stage: Explore    Saved   End Session
Work             Resolve: define cache warm-up           Context
Overview         Why: O-001 challenges the comparison    Issue / Statement / Brief
Explore          ------------------------------------   O-001  Major / Open
Review           Baseline: [                        ]   Source: R-001, draft-1
Resolve  1 open   Procedure: [                       ]   Targets: C-001
Validate         Refute if: [                       ]   No verified evidence
                 [Save Validation Plan] [Back to Issue] View source
                 Saving a plan will not close O-001.
Tab: focus   F1: help   F2: context   Ctrl+Q: end session
```

At wide sizes use a 16–18-column rail, dominant task area and a contextual inspector occupying
roughly a quarter to a third of usable width. In Explore it shows the brief; in Resolve it
shows the issue/statement/evidence chain. Pinning context is optional and visibly labeled.
The top header is compact; explanations live beside the task, not in a permanently large banner.

At 80 columns keep the task and its primary action visible; F2 switches to a full-width Context
view and returns to the same task/focus/scroll position. At 60x20 replace the rail with one
selector; collapse explanatory detail before hiding actionable content. Scrolling must expose
all form fields while action labels and save/error state remain reachable. Validate these as
geometry/keyboard behavior, not merely the presence of widget IDs.

Use three visualizations, each answering a concrete question:

- Lifecycle on Overview: where the project is and what each next gate asks, including return paths.
- Readiness list: which conditions have observable records and which need judgment.
- Selected statement trail: `source -> statement -> evidence / objection -> decision`, with
  selectable source links. Do not begin with an unreadable whole-project force graph.

Keyboard and mouse should expose the same operations. Tab order follows the task; Enter in text
is newline, with an explicit Send button and a tested shortcut fallback. Shortcuts appear beside
buttons, but are never required knowledge. English labels are retained; CJK text/IME and paste
need real-terminal testing. Information must remain understandable without color or special glyphs.

Visual styling is deliberately the last decision. After the task walkthrough is accepted,
compare two skins on identical content and geometry: a restrained modern terminal and a retro
laboratory terminal. Use neutral body text, a single focus accent, separate labeled warning/error
states, and lightweight inactive separators. A small character emblem and discrete step markers
can supply identity; large controls, saturated prose, permanent motion and decorative progress
bars must not displace the research task. Check a long brief, an error state and CJK content,
not just an empty Home screen. Typeface choice belongs to the terminal, not the application.

## 8. Durable state, dependency boundaries and gaps

Reuse L1/L2 and the L3 application service; never parse CLI stdout to drive the interface.
An action descriptor contains title, reason, availability, affected sources and write effects.
Readiness/recommendation rules that interpret research state belong in testable L2 code, depend
only on L1 and return structured facts. Textual renders them; models cannot invoke confirmation
callbacks or promote their own proposals. L3 owns background processes and task cancellation.

Derived counts and recommendations are rebuilt from files, not a parallel authoritative task
database. Display order and focus are disposable preferences. Researcher-selected next steps
persist through the handoff contract (a compact preview may reuse it); UI navigation does not
write PROJECT. Model proposals and task state use versioned auxiliary files under runs
subdirectories, so the existing object scan does not mistake them for formal Runs.

| Capability | Current basis | Work required for this proposal |
| --- | --- | --- |
| Create/open | UI1 and application/workspace.py | Reorganize presentation, preserve recovery/read-only opening |
| Facts and issue lists | protocols/status.py and core inspection | Richer draft discovery, freshness and clearly separated readiness judgments |
| Discussion/brief proposals | Approved UI2/UI3 plan, not implemented | Durable messages, request contexts, safe publication, no model formal writes |
| Review/intake/rulings | Existing protocols and adapters | Task UI, snapshot manifest, convenient form/Decision composition |
| Synthesis/crossval | C4 implemented, live smoke recorded in PROGRESS | Optional secondary UI; preserve original-source intake |
| Validation | Evidence schema and Claim.validation_plan exist | Guided plan/evidence forms and controlled plan update; no execution engine |
| Stage ruling | Documented manual protocol, no dedicated stage-write service | New recoverable Decision + PROJECT transaction, explicit confirmation |
| Handoff | Existing draft/apply/recovery protocol | Task-oriented summary, next-step selection, reliable exit/reopen |

No L0 or seven-object schema change is proposed. New auxiliary contracts and L2 write paths
must be specified with compatibility/recovery tests before implementation. Multi-object writes
need durable intent and conflict detection; existing per-object atomic writes are not sufficient
to claim that a combined Decision/Claim/stage transaction is atomic.

Current C3 preflight and the dedicated Codex home are used. A historical live smoke supports
that configuration's instruction isolation; it is not a universal proof of model behavior or
filesystem isolation. Show actual task configuration and provenance, not a blanket guarantee.

## 9. Scope, tradeoffs and delivery order

Why not a fixed wizard? Research branches, returns to old assumptions and can pause anywhere.
Why not chat plus a sidebar? A list of pages does not explain obligations or available actions.
Why not a generic task board? Manual duplicate status creates stale truth and more administration.
Why not expose all seven object forms first? Researchers should name the research action; the
application should prepare the necessary structure and show its consequences.

Keep the approved UI2–UI5 backend work, but review the product interaction before resuming it:

1. **UI-R1 (this document):** agree task model, navigation and the bounded scope additions.
2. **UI-R2:** low-fidelity Home/Overview/Explore/Resolve/resume mockups at 120x36 and 80x24,
   plus one 60x20 task case; walk the same cache question through them before selecting a theme.
3. **Guided Explore slice:** integrate UI2/UI3 conversations/briefs with Overview, next-step and
   handoff access; test creation through a fresh-session return, not chat streaming alone.
4. **Guided Critique slice:** integrate UI4 review preparation/triage/response, basic validation
   plan/evidence entry and G1/G2 ruling support if approved; fake adapters first.
5. **UI5 trial/polish:** run the real researcher workflow, upgrade existing workbenches safely,
   then refine a restrained retro style around the established hierarchy.

Validation and stage controls extend the original first-release scope. Recommended minimum:
one manual experiment plan and evidence intake flow, plus explicit G1/G2 decisions. Defer
experiment execution, general task scheduling, full graph browsing, Build/Accept orchestration
and C5 calibration. If these additions are declined, show precisely where the user must leave
the TUI; do not describe the partial product as an entirely guided research loop.

## 10. Acceptance of the experience

These criteria are proposed, not passed. Automated checks prove behavior; researcher trials
judge clarity. Use the small cache question, not a sophisticated research benchmark.

| Scenario | Observable acceptance |
| --- | --- |
| First use | Without README/commands, the researcher creates a project and identifies the purpose and next available action |
| Resume | After closing/reopening, they identify the saved next task and unresolved issue within ten seconds, without finding the old chat |
| Review | They can name the inputs and session count before starting; output archives but no formal Objection appears without confirmation |
| Missing knowledge | Missing magnitude/novelty can remain unknown; exploration/scoped review remains possible and formal gate passage is not implied |
| Judgment | They distinguish recording a suggestion, responding to it and ruling on it; each final write states its effect and source |
| Validation | They can save a test plan and later record results; a plan or AI answer alone never upgrades a Claim to supported |
| Revision | Editing a reviewed statement shows successor/history consequences; old evidence is not silently transferred |
| Failure | One review failure preserves successful outputs; retry is explicit; no orphan model processes remain after confirmed stop/exit |
| External change | A changed input or invalid file shows stale/unknown conditions and a recovery action, rather than false readiness |
| Navigation | All core actions work by visible controls at 120x36/80x24; compact view preserves editing, action access and return position |
| Gate and exit | Navigation/hand-off never changes stage; a stage decision is explicit; failed saves cannot be reported as successful exit |

Measure path entries, unexplained disabled actions, help requests, lost place and repeated
confirmation prompts during the user trial. Target zero required path/ID/command entry in the
normal loop after initial project/model setup. Do not substitute scripted click counts or the
number of passing unit tests for a user's ability to understand and steer the research.

## 11. Decisions requested before implementation

- **Q30 — interaction model:** adopt activity-based navigation, persistent next-action guidance,
  task-specific context and an explicit distinction between activity progress and research gates.
  Recommendation: adopt; this directly addresses the user's stated need.
- **Q31 — bounded scope:** include manual validation planning/evidence intake and explicit G1/G2
  stage rulings in the first guided loop. Recommendation: adopt the minimum in section 9,
  without automated experiments or Build/Accept orchestration.

Visual theme selection follows the low-fidelity walkthrough. This proposal does not approve a
new theme, execute research, or authorize real-model quota use for its eventual usability trial.

## 12. UI-R3 refinement: uncertainty drives the next action

2026-11-03: the researcher approved trying a more research-centered prototype. This refines the
UI-R2 walkthrough; it does not approve production write paths or claim completed research.

Overview now asks what is observed, what remains unknown, what material exists and which check
could reduce that uncertainty. Saving a brief does not automatically recommend reviewing it.
Exploration separates reported observations from competing hypotheses. AI suggestions are
editable proposals; the researcher can correct their context or choose an alternative action.

Validation is available before Claims and reviews. Its entry offers existing-data inspection,
related-work checking and a small controlled experiment, each with a stated reason and editable
plan. Inspecting material is separate from interpreting it. The researcher records a reason
and chooses to test a lead, redirect the question or seek more information. None of those
planning choices is evidence verification or a formal Claim/stage ruling.

The standalone prototype uses fictional materials to exercise all three outcomes and retains
corrections verbatim without pretending an actual model has understood or regenerated them.
Its suggestions are fixed for the sample question, not a general scientific prioritization
algorithm. A production assistant may help compare uncertainties and costs; the researcher
selects the task. Record the reason and the observation that would change direction in handoff.

Acceptance of this prototype requires showing that early validation is reachable without
creating a Claim/Objection, feedback remains visible, saving a brief leaves exploration open,
material does not automatically determine the conclusion, and changed source material or plans
do not inherit an interpretation made against earlier inputs. Researcher feedback is still
needed on whether this supports thinking rather than becoming another form-filling sequence.
