# Toulmin development progress

## 2026-11-02 — UI1 verification-process cleanup

- Verified three leftover sandbox processes from UI1 verification: targeted pytest (PID 4110036), full pytest (4119865), and terminal smoke TUI (4139178). These were abandoned hung attempts, not the successful final validation run.
- Matched exact command lines and working directory before stopping them; verified all three stopped. No researcher project or application code changed.
- The previous session failed to clean up these attempts before reporting completion. Future verification commands must have bounded timeouts and all started sessions must be checked at close.
- Validation: process identity and post-stop state; documentation diff check. Code tests were not rerun for process cleanup.
- Session ID unavailable. Blockers: none. Next: UI2 as previously planned. No push.

## 2026-11-02 — UI1: terminal project workspace

- Status: **Verified**: UI1 implemented and integration checks passed; researcher usability acceptance remains pending UI5.
- Authorization: researcher approved Q25–Q29 and implementation, including GPT-6.1 Sol/high development subagents with root-agent verification. This session completes UI1 only; UI2–UI5 and C4/C5 remain pending.
- Delivered: optional Textual extra and lazy `toulmin tui` command; English Home/New/Open screens; typed goal and motivation, editable UTF-8 Markdown/text import preview with exact source archival, saved-state preview, seven workflow views, three-pane retro theme, compact inspector toggle, keyboard navigation and quit/discard confirmation. Future research actions are explicitly unavailable; no model calls were made.
- Service boundary: L3 application service coordinates existing initialization and read-only inspection. L1 defines setup intent/images and validation without CLI/Textual dependencies. Opening preserves edited templates and project files. Explicit Resume Setup checks intent/source/image digests and refuses external target edits.
- Compatibility: additive `runs/setup/` auxiliary archive with UTC creation time, original input, exact before/after images and completion markers. No object-schema migration. Initial motivation is quoted to preserve Markdown section structure. Hard termination before input-bundle publication can leave a hidden `.setup-*` archive; diagnostics require manual preservation/inspection and a new-slug retry. Ordinary staging failures clean only owned empty directories.
- Development review findings fixed: stale Open selection after a failed selection, missing Git errors escaping recovery, malformed source filename validation after mutation, stale initial motivation hiding later brief edits, import changes after preview, and omitted next-step/open-objection preview.
- Environment finding: sandbox execution hung during Python executor shutdown and terminal input handling; a minimal executor example completed immediately outside it. Final full-suite and PTY validation ran outside the sandbox. Read-only document views use synchronous Rich Markdown; the file picker uses a keyboard list.
- Verification: locked offline sync with the tui extra succeeded; full pytest reported **527 passed in 102.32 s**, including 14 UI tests. Ruff lint and format passed (86 files), strict mypy passed (39 source files), CLI and TUI help passed, and git diff whitespace checks passed; root verified installed-wheel create/open/render/shutdown outside the checkout, base-only installation help without Textual and actionable missing-extra errors, included theme assets and excluded caches/tools in distributions, canonical format/protocol template equality, and PTY confirmed quit with exact terminal attributes and alternate screen restored. Colored wide/compact snapshots were inspected; temporary screenshots are not committed.
- Limits: actual user terminal font, paste and CJK/IME behavior still require researcher trial. Development-agent review and root verification are not independent researcher acceptance. No quota was consumed for research model calls; no automatic push.
- Session ID: unavailable in this environment.
- Blockers: none.
- Next: UI2 durable discussion, saved conversations and cancellable model jobs, tested first with fake adapters.

## 2026-11-02 — UI0: Python/Textual TUI design proposal

- Status: **Verified**: design document written and checked; implementation has not started.
- User authorization: prepare a design for the agreed Python TUI direction, without direct implementation.
- Output: docs/tui-design.md covers startup, a three-pane pixel-style workspace, exploration, brief proposals, key claims, independent review, resolution, handoff, architecture, persistence/recovery, workbench upgrades and UI1–UI5 acceptance criteria.
- Proposed decisions Q25–Q29 remain pending: expanded exploration scope, brief-centered interaction, file-reconstructed conversations, explicit proposal application and implementation priority relative to C4/C5.
- Existing research object formats, executable code, dependencies and templates are unchanged. No real model was invoked.
- Validation: inspected existing adapter/protocol boundaries and official Textual documentation; checked document links, fences, English text and git diff whitespace. Code tests were not rerun for this documentation-only task.
- Session ID: unavailable in the current environment.
- Blockers: none for the design deliverable; implementation awaits review of the proposed scope/contracts.
- Next step: researcher reviews Q25–Q29, then UI1 can begin if approved. No automatic push.

## 2026-11-02 — C4 live synthesis smoke run (approved)

- Status: **Verified: the real synthesizer follows the group format and the rotation works.**
- User authorization: "同意，先跑 C4 真实综合冒烟测试" (agreed; run the C4 live synthesis smoke test first). One session was used.
- Setup: the scratch workbench (copy of R1/S2) was refreshed with the C4 role templates and framework documents. Synthesis over R-002 (Claude review, 7 drafts) and R-004 (isolated Codex review, 4 drafts).
- **Verified** results:
  - R-005 completed: Claude, 45.6 s, session ID recorded. The rotation reason "first synthesis in this project; first of [claude, codex]" is in the Summary.
  - `input_files` = synthesizer manifest + exactly the two outputs.
  - The block parsed: 5 groups (0 disagreement, 4 agreement, 1 singleton) covering all 11 items.
  - intake on the synthesis output was refused with a pointer to the original Runs, and status stayed valid.
  - A dry run shows the next rotation: "previous synthesis R-005 used claude; next of [claude, codex]" → codex.
- Finding: no group was classed as a disagreement, but the synthesizer described two substantive divergences under its Disagreements heading and in notes: C-003's baseline (syscall submission vs interrupt/hybrid poll) and the kill criterion's target (C-002 vs C-003). The strict definition of disagreement hides partial divergence in the machine-readable block. The template is unchanged for now; to be revisited with C5 data.
- Observation: the synthesizer was the same model as one source review (rotation starts at the first model). Rotation spreads this over rounds, as Q23 intends.
- Session ID: unavailable in the current environment.
- Blockers: none.
- Next step: C5 (calibration report, then a stage 3 trial needing about 15 sessions over three rounds; the plan will be shown for approval first), then UI2–UI5.

## 2026-11-02 — C4: synthesizer and crossval

- Status: **Verified with fake CLIs.** No live model was run for C4.
- User authorization: "加上运行前检查，然后开始 C4" (add the preflight check, then start C4). This takes C4 ahead of UI2, changing Q29's order (recorded in AGENTS.md and TODO). The UI0/UI1 commits from another session were not touched.
- L1:
  - `review.final_yaml_list` is shared by every block parser.
  - New `core/synthesis.py` parses crossval point blocks and synthesis group blocks. Group kinds, single-item singletons, items from at least two Runs for agreements and disagreements, every round item placed exactly once, optional Claim target.
  - `roles.OPERATIONS` gains `answer`.
- L2:
  - New `protocols/synthesis.py`. `round_sources` validates two or more completed, non-synthesis Runs of one kind with valid item blocks. `choose_model` implements Q23 rotation (or override) with a recorded reason. `plan_synthesis` builds the manifest, the named outputs and the item list. `plan_crossval` takes a question under `runs/drafts/`, with the cap counting the synthesis.
  - `ReviewTask` gains kind, items and note; archiving checks the block for each kind.
  - Intake refuses synthesizer and crossval outputs.
- L3: `adapters/review.py` shares plan → preflight → show → confirm → execute across `review`, `synthesize` and `crossval`. New commands `toulmin synthesize` and `toulmin crossval`.
- Templates: new roles/crossval.md; synthesizer.md matches the parsed group format and cites `R-NNN/label`; the workbench AGENTS template names the new commands.
- Docs: formats.md and protocols.md (with packaged copies), CHANGELOG, README.
- **Verified**: `tests/cli/test_synthesis.py` **29 passed**, rerun three times after fixing one order-dependent assertion (fake log files were read in random order). Full suite with `--extra tui` **562 passed**. An installed wheel created the crossval role, resolved its inputs, and ships a packaged protocols.md identical to docs. Ruff and mypy (41 source files) passed.
- Session ID: unavailable in the current environment.
- Blockers: none.
- Next step: optionally one supervised live synthesis over R-002/R-003/R-004 on the scratch workbench (needs quota approval), then UI2 or C5 as the researcher chooses.

## 2026-11-02 — C3 follow-up: Codex home preflight

- Status: **Verified: review refuses a Codex home with global instructions or without a login.**
- User authorization: "加上运行前检查，然后开始 C4" (add the preflight check, then start C4).
- Change (L3):
  - Adapters gain `preflight(command, env)`, run during planning, before any session and also on `--dry-run`. Claude Code needs none because `--safe-mode` covers it.
  - The Codex preflight refuses a `CODEX_HOME` containing AGENTS.md or AGENTS.override.md, or one that is missing. It then runs `codex login status`, which uses no quota, and refuses a home that is not logged in.
  - Each refusal message gives the one-time login command.
  - The models.toml template now enables `env = { CODEX_HOME = "~/.codex-toulmin" }` by default. Protocols, README and CHANGELOG were updated.
- **Verified**: `tests/cli/test_review.py` **29 passed**, using a temporary Codex home, never the operator's: instruction files, missing home, logged out, per-adapter scope and `~` expansion. Full suite with `--extra tui` **532 passed**; Ruff and mypy (39 source files) passed.
- **Verified** against the real tools, dry run only: `~/.codex-toulmin` passed (logged in, no AGENTS.md). Without the env line, the default `~/.codex` was refused because of its AGENTS.md. That refusal's first hint wrongly suggested logging in to `~/.codex`; this was fixed and rechecked.
- Note: commits 8e6420d/c41ef80/ae52061 (UI0/UI1, another session) landed during the pause. They are untouched here.
- Session ID: unavailable in the current environment.
- Blockers: none.
- Next step: C4, as the researcher instructed. This takes C4 ahead of UI2, changing Q29's order (UI1–UI5 first, C4/C5 pending).

## 2026-11-02 — C3 follow-up: Codex isolation verified

- Status: **Verified: Codex reviews run without the operator's global instructions.**
- User authorization: "先验证codex隔离吧" (verify Codex isolation first), then "已登录，开始跑吧" (logged in, start the run). One Codex session was used.
- Setup:
  - The researcher logged in once with `CODEX_HOME=~/.codex-toulmin`. That home holds only credentials, with no AGENTS.md, config, hooks, memories or skills (**Verified** by listing it).
  - The scratch workbench's models.toml set `env = { CODEX_HOME = "~/.codex-toulmin" }`, `model = "gpt-6.1-sol"` and `-c model_reasoning_effort="xhigh"`, matching R-003's model and effort taken from `~/.codex/config.toml`.
- **Verified** result: R-004 completed in 122.9 s with model `gpt-6.1-sol` recorded, a session ID and 4 drafts, using the same 7 inputs as R-003. R-003 had opened with "**Verified by inspection of the supplied text:**" and three bullets. R-004 opens with plain prose, has no Verified/Inferred/Guess labels, and is about the same length (825 vs 806 words).
- Limits: one session each, so draft counts (4 vs 5) say nothing about quality. The env change and the prompt line were tested together.
- Observation for later: both live reviewers noted that the brief still cites superseded C-001, which their manifest correctly left out; status already flags stale brief references.
- Session ID: unavailable in the current environment.
- Blockers: none.
- Next step: C4 (synthesizer and crossval) in its own session. For real workbenches, uncomment `env` and set explicit models in tools/models.toml.

## 2026-11-02 — C3 live smoke runs (approved) and Codex isolation follow-up

- Status: **Verified: both adapters work against the real tools; C3 acceptance ticked. Paused here at the researcher's request.**
- User authorization: "批准，跑真实冒烟测试" (approve and run the real smoke test). Exactly 2 sessions were used.
- Run: `toulmin review sqpoll-cost --personas reviewer-skeptic --models claude,codex --confirm` on a scratch copy of the R1/S2 workbench, with models.toml defaults (empty model = tool default).
- **Verified** results:
  - R-002 Claude Code: completed, 86.4 s, model `claude-opus-5-5` reported, session ID recorded, 7 drafts with descriptive labels.
  - R-003 Codex: completed, 113.7 s, model not reported, thread ID recorded, 5 drafts.
  - Both outputs parsed. Intake of one Claude draft created O-005 citing R-002, and status listed the six remaining drafts as pending.
- Finding: the Codex review followed the operator's global `~/.codex/AGENTS.md` (thin-first structure, "Verified by inspection" labels), so the session was not instruction-neutral. Claude's output showed no comparable influence, consistent with `--safe-mode` skipping CLAUDE.md (**Inferred** from the output).
- Changes after the live run:
  - `tools/models.toml` gains a per-model `env` table (`~` expanded) for a review-only `CODEX_HOME`, documented in the template, formats.md and README.
  - The review prompt now states that the role contract overrides general reply-style instructions.
  - Tests cover env passthrough and invalid env: `tests/cli/test_review.py` **24 passed**; full suite **478 passed**; Ruff and mypy passed.
- Not verified: whether the env/prompt mitigations remove the Codex influence (needs the researcher's one-time `CODEX_HOME=~/.codex-toulmin codex login` and one more Codex session).
- Session ID: unavailable in the current environment.
- Blockers: none for C4; the Codex follow-up needs the researcher's login.
- Next step (on resume): either verify the Codex follow-up, or start C4 (synthesizer and crossval). Set an explicit Codex model in models.toml so Runs record it.

## 2026-11-02 — C3: adapters and `toulmin review`

- Status: **Verified with fake CLIs; live smoke runs pending researcher approval.** The C3 acceptance box stays open until one supervised live run per adapter.
- User authorization: implement C3 (Q19–Q24 confirmed). No real model was invoked in this session.
- Flags re-checked from `--help` only:
  - Claude Code 2.1.316: `-p --output-format json --tools "" --safe-mode --no-session-persistence --model`.
  - Codex CLI is now **0.166.0** (the plan cited 0.165.0): `exec --sandbox read-only --ephemeral --skip-git-repo-check -C --json -o --model`, prompt on stdin via `-`.
- L2: new `protocols/review.py` (invokes no model):
  - `plan_review` validates personas (critique roles only), model names, duplicates, the run cap and unused archive names, and builds one self-contained prompt per persona with the manifest files inlined.
  - `archive_review` writes `prompt.md`/`output.md`/`tool.log`, notes whether a valid draft block exists, and publishes a completed or failed Run under the creation lock.
- L3: new `adapters/`:
  - `base` provides the Session interface and a process runner. It runs each session in its own process group, kills the group on timeout, and registers sessions so an interrupt stops them all.
  - `claude_code` (JSON result, session_id, reported model) and `codex` (last message file, `thread.started` ID) are the two adapters.
  - `config` reads `tools/models.toml` with tomllib.
  - `review` orchestrates a round: plan → preflight executables → dry run or `--confirm` → parallel sessions → archive sequentially. It exits 1 if any session failed.
- Templates: `tools/models.toml` (both adapters, four personas × two models = cap 8, parallel 2, 900 s timeout, empty model = tool default). Workbench AGENTS mentions `toulmin review`.
- Docs: formats.md and protocols.md (with packaged copies), framework CHANGELOG, README.
- Known boundary: Codex's read-only sandbox does not block reads, so its isolation relies on the inlined prompt, the instruction and the empty working directory. Global user instruction files of either tool (e.g. `~/.codex/AGENTS.md`) may still load unless extra_args exclude them (**Inferred from tool help**; to confirm in the live smoke run).
- **Verified**: `tests/cli/test_review.py` **23 passed** with fake executables on PATH, including timeout killing a child process and every refusal starting no session and writing nothing. Full suite **477 passed**; Ruff lint/format and mypy (34 source files) passed; `toulmin --help` lists review.
- **Verified**: an installed wheel outside the checkout, with fake `claude` (success) and `codex` (exit 2), recorded one completed and one failed Run with the expected archive files. status stayed valid.
- Session ID: unavailable in the current environment.
- Blockers: the live smoke runs need explicit researcher approval because they use subscription quota.
- Next step: with approval, run one supervised `toulmin review --personas reviewer-skeptic --models claude` and one with `codex` on a scratch workbench, record the results, then tick C3 acceptance. Otherwise continue with C4.

## 2026-11-02 — C2: reviewer personas and role manifests

- Status: **Verified: C2 complete.** Researcher acceptance of stage 3 is pending until C5.
- User authorization: implement C2 (Q19–Q24 already confirmed).
- L1 (additive): new `core/roles.py` parses the role-file YAML header (`schema_version`, `role`, `operation` critique/synthesize, `inputs`). Patterns use only `{project}`, put wildcards in the last component only, and must stay inside a fixed allowlist (AGENTS.md, roles, framework, global/papers, global/assumptions, the project's brief and claims). Sessions, handoffs, Runs, Decisions, Objections, PROJECT.md, calibration and other projects cannot be named.
- L2: new `protocols/inputs.py` resolves a manifest for one project. It applies natural order, skips dotfiles, refuses symlinks, leaves out superseded Claims and handles an optional current-Claim selection. `write_draft` can fill a Run draft's role and input_files from it.
- L3: `toulmin inputs <project> <role> [--claim]` and `toulmin draft run <project> --role <role> [--claim]`.
- Templates: manifest added to roles/reviewer.md; new reviewer-skeptic, reviewer-industry, reviewer-theorist and reviewer-why-not-x (extending reviewer.md) and synthesizer.md (groups disagreements first, then a yaml group block that C4 will parse); workbench AGENTS points independent roles at `toulmin inputs`.
- Docs: formats.md and protocols.md (with packaged copies), framework CHANGELOG, README. The architecture allowlist gains `fnmatch` (pure string matching).
- Compatibility: object formats unchanged; no migration. Changed reviewer.md and AGENTS.md templates conflict with `init --project` on workbenches created earlier (**Inferred from code**).
- **Verified**: `tests/cli/test_inputs.py` **40 passed**; full suite **454 passed**; Ruff lint/format and mypy (27 source files) passed; `toulmin --help` lists inputs.
- **Verified**: an installed wheel outside the checkout created all seven role files and resolved the six manifests; the packaged protocols.md matches docs. On a copy of the R1 workbench, `inputs` left out superseded C-001 and `draft run --role reviewer-theorist --claim C-004` produced the five input files.
- Session ID: unavailable in the current environment.
- Blockers: none.
- Next step: C3 (Claude Code and Codex adapters, `toulmin review`) in its own session. Re-check the exact headless flags first.

## 2026-11-02 — C1: structured review intake

- Status: **Verified: C1 complete.** Researcher acceptance of stage 3 is pending until C5.
- User authorization: Q19–Q24 confirmed as recommended; implement C1.
- L1 (additive within v1):
  - New `core/review.py` parses the last top-level fenced `yaml`/`yml` block of a raw review into drafts. It validates labels, one Claim target, severity, nonempty text, unknown fields and level-two headings, and reports errors with file and line.
  - The same module validates `intake.md` records: Run, output, append-only outcomes taken/partly/rejected, with an object or a reason.
  - `codec.load_restricted` was factored out of `decode` so draft blocks use the header YAML subset; error paths name the block (`drafts[0].<<`).
  - `documents.headings` is now public.
- L2:
  - New `protocols/review_intake.py` validates every choice before writing. Under the creation lock it creates open Objections (source = Run + output) and appends each outcome atomically.
  - A replay reports `already-<outcome>`, refuses to change an outcome, and reuses an Objection created before an interrupted record write.
  - `publish_locked` was factored out of `create_object`.
  - status validates intake records against their Run, raw output, labels and Objection sources. It reports drafts still pending once a record exists, and returns settled Objections with their Decisions (S2 finding 2).
- L3: `toulmin intake <project> <output> --take LABEL[:SEVERITY] --reject LABEL=REASON --partly LABEL=O-NNN --confirm`. `status -v` gains a `Settled objections:` list.
- Scope: AGENTS.md now reflects Q19 (headless read-only review/crossval/synthesis only; no automatic rulings, model writes, MCP or reference managers). TODO marks Q19–Q24 confirmed.
- Docs: formats.md and protocols.md (with packaged copies), reviewer role template (the required final yaml block), framework CHANGELOG and README.
- **Verified**: `tests/cli/test_intake.py` **33 passed**. Full suite **414 passed**; Ruff lint/format and mypy (25 source files) passed; `toulmin --help` lists intake.
- **Verified**: an installed wheel outside the checkout initialized a workbench containing the new templates (packaged formats.md identical to docs). It ran claim → Run → intake → status (pending notice) → replay plus reject (notice cleared).
- **Verified** trial: the S1 (8 drafts) and S2 (6 drafts) raw outputs, converted mechanically to the Q21 block, were taken in with one command each (7+1 rejected, 5+1 rejected). The S2 copy's status also reported missing D-001/D-002, because the copied end-state Claims cite Decisions that were not copied; that is a fixture artifact, not an intake fault.
- Finding: S1 draft-3 targets two Claims, but Q21 allows one target, so the conversion kept C-001. This is the first data point for Q14 (multi-target Objections).
- Known boundary: raw outputs without an intake record raise no pending notice, since older reviews may hold unrelated yaml blocks.
- Session ID: unavailable in the current environment.
- Blockers: none.
- Next step: C2 (reviewer personas and role manifests) in its own session.

## 2026-11-02 — Stage 2 closing retrospective and stage 3 plan

- Status: **plan written; stage 3 not started.** It awaits decisions Q19–Q24.
- User authorization: hold the retrospective and plan stage 3.
- Outputs: a closing retrospective in docs/manual-acceptance.md; TODO.md "Stage 3: critique — plan" with the done criterion, decisions Q19–Q24 and tasks C1–C5.
- Key retrospective points: reviews were most valuable on definitions and measurement validity; transcribing review drafts into Objections is the main remaining burden (hence C1 first); cross-vendor independence and quota cost are untested; template churn will need an upgrade path once a durable workbench exists.
- **Verified** environment facts: Claude Code 2.1.316 and Codex CLI 0.165.0 are installed, and Gemini CLI is not. Their `--help` output listed the headless/read-only flags named in the plan. No model was invoked.
- Checks: documentation only; code tests were not run because no code changed. The diff contains TODO.md, PROGRESS.md and docs/manual-acceptance.md.
- Session ID: unavailable in the current environment.
- Blockers: Q19 (the AGENTS.md scope ban on automation) must be lifted before C3.
- Next step: the researcher confirms Q19–Q24, then C1 in its own session.

## 2026-11-02 — R1: Claim revision by supersession

- Status: **Verified: R1 complete.**
- User authorization: Q15–Q18 confirmed as recommended; implement R1.
- L1 (additive within v1):
  - Claim gains the status `superseded` and the field `superseded_by`. The field is required only for superseded Claims, must reference another Claim, and a superseded Claim requires a Decision.
  - `inspection` reports revision cycles and foreign successors as data errors, captures resolved brief references, and adds `current_claim()` to follow chains.
  - `patch_header` inserts new keys in contract order.
- L2:
  - status leaves superseded Claims out of condition checks and returns `superseded` chains. It adds notices for open Objections, valid Evidence, Specs, adopted Explorations and brief references that point at superseded Claims.
  - rule gains links (`superseded_by`, `adopted_as`, Spec `evidence`) that require a Decision. A successor must be a current object of the same kind in the same project and must be named by the Decision. `superseded` is final for Claims and Decisions, and rule never replaces existing links.
- L3: `rule --superseded-by/--adopted-as/--evidence` and a `Superseded:` section in status (summaries with `-v`). rule notices now include any notice that mentions the object.
- Docs: formats.md, format-examples.md (superseded variant), protocols.md (each with packaged copies), design.md §4, docs/claim-revision.md (marked implemented), framework CHANGELOG, workbench AGENTS guidance and README.
- Compatibility: existing files stay valid and no migration is needed, as verified on S2 files written by the pre-R1 build. Older builds reject `superseded`, as recorded in the CHANGELOG. Changed templates cause the usual `init --project` conflicts on older workbenches.
- **Verified**: `tests/cli/test_revision.py` **20 passed**: successful supersession with field order and dependent/brief notices; chains; nine refusal paths that write nothing; final status and no link replacement; hand-edited cycles and foreign successors; Claim schema conditions; Exploration and Spec links; Decision supersession. Full suite **381 passed**; Ruff lint/format and mypy (23 source files) passed.
- **Verified**: an installed wheel replayed S2's revision (C-004 created, D-003, C-001 superseded, O-001 accepted) on a copy of the S2 workbench. Status showed `C-001 -> C-004` without S2's contradictory notice.
- Session ID: unavailable in the current environment.
- Blockers: none.
- Next step: per design §11–12, a short retrospective on stage 2 plus U1–U3/R1, then agree the stage 3 scope. Remaining S2 findings 2–4 (settled objections in status, draft/new friction, consumed drafts) are candidates.

## 2026-11-02 — R1 design: Claim revision by supersession (proposal)

- Status: **design proposal written; not implemented.** It awaits researcher decisions Q15–Q18.
- User authorization: design Claim revision as a separate task.
- Outputs: docs/claim-revision.md (problem, proposal, worked S2 example, alternatives, compatibility/migration) and TODO.md R1 (decisions Q15–Q18 and implementation tasks).
- Summary: an old Claim becomes `superseded` with `superseded_by` pointing to a new Claim, under a Decision. Nothing is retargeted automatically, and status derives chains and notices. The change is additive within v1 with no migration; older builds would reject the new status.
- Checks: documentation only. The new links resolve and code tests were not run because no code changed. The diff contains only docs/claim-revision.md, TODO.md and PROGRESS.md.
- Session ID: unavailable in the current environment.
- Blockers: none.
- Next step: researcher confirms or amends Q15–Q18, then R1 implementation in its own session.

## 2026-11-02 — S2: agent-run trial after U1–U3

- Status: **Verified**: a second agent-run, same-day trial using `draft`, `rule` and `status -v` completed end to end. A fresh session recovered the project correctly from files and `status -v`.
- User authorization: run one more simulated round with the new commands, then record it here.
- Setup: a fresh scratch workbench outside this repository with project `sqpoll-cost` (whether io_uring SQPOLL's polling core is worth its CPU). It used a wheel built from `9ed1797`. As in S1, the agent acted as researcher with simulated confirmations; the reviewer and resume sessions were fresh-context subagents of the same model (claude-opus-5-5). The scratch location is not durable.
- Session ID: unavailable in the current environment.

### Actual run

- **Verified**: `draft` → edit → `new` for 3 Claims, Run R-001 (raw review archived), 4 Objections (O-001/O-003 fatal, O-002/O-004 major) and 2 Decisions → five `rule` calls (O-001 answered by D-001, O-003 deferred by D-002, C-001/C-003 challenged). A sixth was correctly refused because D-001's `related` did not name C-002. Then `handoff --input` → `--apply` → workbench commit.
- **Verified**: the resume session answered the goal, open majors (O-002, O-004), settled objections with their Decisions, next step and raw-review location correctly. It read 9 files plus `status -v` (about 1,600 words), against S1's 10 files and about 2,500 words.

### Comparison with S1

- Object creation: about 46 field values filled in skeletons, against 114 hand-written lines; no formats.md lookups and no intake errors.
- Rulings are now recordable, so the resume session could distinguish answered/deferred from open (S1 could not).

### Remaining findings (inputs for later work; no code changed)

1. No way to revise a Claim. D-001 calls for rewriting C-001, but v1 has no Claim supersession. Marking C-001 challenged after answering O-001 produced "challenged but no open objections", so no correct move existed. This is an L1 gap.
2. `status` lists only open Objections; answered/deferred ones are only findable through handoff text and the directory.
3. Remaining manual steps: two commands per object plus copying timestamped paths; list fields (`related`, `input_files`) lack placeholder support; no handoff-summary skeleton; consumed drafts accumulate in `runs/drafts/` (13 here).
4. A Decision relating O-004 is invisible on O-004 until `rule` links it.

- Checks: no code or tests changed, so the software checks were not rerun. The diff contains only this file.
- Blockers: none.
- Next step: design Claim revision (finding 1) as its own L1 task before stage 3.

## 2026-11-02 — U3: readable generated files and status output

- Status: **Verified: U3 complete.** The usability follow-up U1–U3 is finished.
- User authorization: implement U3.
- L1:
  - `codec.encode` keeps the caller's key order and no longer folds long strings.
  - `schema.py` adds the contract field order (`ORDER`, `KIND_ORDER`, `object_order`, `in_order`) and `utc_text` for whole-second UTC timestamps.
  - `handoffs.py` defines `DRAFT_ORDER`/`RECORD_ORDER` tuples; the field sets are derived from them.
- L2:
  - Intake writes headers in contract order with whole-second `created`/`confirmed_by.at`.
  - Handoff drafts and records use contract order.
  - `project_status` adds a first-paragraph summary (100 characters) for each Claim and open Objection, plus the root-relative `last_handoff` path.
- L3: `new` prints root-relative paths (all writing commands now do), and `status --verbose/-v` shows the summaries and last handoff.
- Deviations from the plan, recorded in TODO U3:
  - Handoff `created`/`applied_at` keep sub-second precision. Drafts are identified by content digest, and whole seconds made two same-second drafts identical; an existing T5 test caught this.
  - Summaries use the first paragraph instead of the first line, which a smoke test showed cut hand-wrapped statements mid-sentence.
- Compatibility: presentation only. Readers already accept any key order and fractional seconds, so older files (including S1's) stay valid without migration. formats.md and its packaged copy gained a note, and the framework CHANGELOG template has a U3 entry; the usual `init --project` conflict behavior applies to older workbenches.
- **Verified**: `tests/cli/test_readable.py` **6 passed**. It covers ordered, unfolded, second-precise headers; root-relative `new` output from `--root` and from the default root; legacy sorted, folded, microsecond files staying valid; verbose summaries (truncation, hand-wrapped paragraphs, objections) and last handoff before and after applying; and handoff draft field order. Existing tests were updated for root-relative `new` output. Full suite **361 passed**; Ruff lint/format and mypy (23 source files) passed.
- **Verified**: a wheel installed outside the checkout created C-004 in a copy of the S1 workbench via draft → new; the header was ordered with whole-second times, and `status -v` read new and old-style files together.
- Session ID: unavailable in the current environment.
- Blockers: none.
- Next step: per design §12, hold a short retrospective on stage 2 plus U1–U3, then decide stage 3 (critique: review/crossval/synthesizer) scope with the researcher.

## 2026-11-02 — U2: confirmed status and response updates

- Status: **Verified: U2 complete.** U3 has not started.
- User authorization: implement U2 per confirmed Q13.
- L1: `documents.put_section()` is a pure, fence-aware body edit. It fills an empty section, appends after a blank line to a nonempty one, adds a missing section at the end, and never deletes text. Content containing level-two headings is rejected. Header changes reuse the comment-preserving `patch_header`, and writes reuse the atomic `write_atomic` (replace mode).
- L2: `protocols/ruling.py` `apply_ruling()` validates everything before writing:
  - Status changes require an active Decision whose `related` list names the object; that Decision is appended once to the object's `decisions`.
  - Run outcomes cannot be changed, and setting the status the object already has is refused.
  - Only Response/Ruling (Objection), Invalidation (Evidence) and Rationale (Exploration) may receive text, and the text must not contain placeholders.
  - The result must pass full validation and link validation.
  - The function holds the project creation lock, compares file bytes before replacing (refusing if they changed) and writes atomically.
- L3: `toulmin rule <project> <ID> [--status] [--decision] [--response] [--ruling] [--section NAME=FILE]` with `--confirmed-by`/`TOULMIN_ACTOR` and mandatory `--confirm`. It prints the root-relative path, a one-line change summary and status notices for the object and its target Claim.
- Implementation choices recorded in TODO U2: Decision `related` must name the object; appending instead of replacing preserves earlier responses; reference fields (adopted_as, superseded_by, Spec evidence) remain hand edits.
- Compatibility: v1 object fields and formats are unchanged; no migration is needed. The changed packaged templates (AGENTS, framework protocols/CHANGELOG) cause the same `init --project` conflict behavior on older workbenches.
- **Verified**: `tests/cli/test_rule.py` **36 passed**. Coverage:
  - Objection answered/accepted/deferred, together with their required sections.
  - Claim rulings with condition notices, no duplicate Decision references, and the Response-only path.
  - Ten invalid-input cases plus foreign, Run and missing IDs, all writing nothing.
  - The confirmation/actor rules, bad section text, preservation of comments, field order, fenced pseudo-headings and following sections, and appending.
  - Adding an Invalidation section, a failed replace, a held lock, an external edit during ruling, and absolute input paths.
- **Verified**: full suite **356 passed**; Ruff lint/format and mypy (23 source files) passed. A wheel installed outside the checkout ruled on a copy of the S1 workbench; status reflected the change, and only the two targeted files changed.
- Session ID: unavailable in the current environment.
- Blockers: none.
- Next step: U3 readable generated headers, root-relative output for every command, and `status --verbose`.

## 2026-11-02 — U1: draft skeletons and simpler intake

- Status: **Verified: U1 complete.** U2–U3 have not started.
- User authorization: Q11–Q13 confirmed as recommended; implement U1.
- L1: `core/skeletons.py` holds pure skeleton text for all seven kinds and `unfilled()` placeholder detection. Its enum values come from new shared constants in `core/schema.py`, so skeletons cannot drift from validation. `Repository.relative()` accepts absolute paths that lie lexically inside the root; all existing path checks still apply afterwards.
- L2: `protocols/drafting.py` writes `runs/drafts/<kind>-<UTC>[-name][-N].md` through an exclusive hard link, never overwriting and never leaving partial files. Intake now rejects `<fill: ...>` placeholders with a located field and accepts absolute `--input` inside the root. Change notes are in docs/protocols.md (plus its packaged copy) and the framework CHANGELOG template.
- L3: the `draft` command prints a root-relative path and a follow-up `new` hint on stderr. `--confirmed-by` on `new` and on `handoff --apply` falls back to `TOULMIN_ACTOR`; `--confirm` is still mandatory.
- Compatibility: v1 object fields and formats are unchanged; no migration is needed. Previously valid drafts are still accepted unless they literally contain `<fill:`. Changed packaged templates (AGENTS, framework protocols/CHANGELOG) make `init --project` on older workbenches report conflicts and preserve those files (existing behavior).
- **Verified**: `tests/cli/test_draft.py` **28 passed**: every kind rejected while unfilled and accepted once filled; located body placeholders; no-overwrite naming; bad names/actors and symlinked drafts directories write nothing; the default actor and its override; absolute input; status ignores drafts; handoff applies with the default actor. Full suite **320 passed**; Ruff lint/format and mypy (22 source files) passed.
- **Verified**: a wheel installed into a fresh venv outside the checkout ran init → draft → hand fill → `new` with an absolute path and `TOULMIN_ACTOR` → status (valid).
- Not verified: whether a human can fill every skeleton without reading formats.md. The tests fill the skeletons programmatically.
- Session ID: unavailable in the current environment.
- Blockers: none.
- Next step: U2 `rule` command for confirmed status/Response/Ruling updates (Q13).

## 2026-11-02 — Stage 2 acceptance and U1–U3 usability plan

- Status: **Verified**: the researcher explicitly accepted roadmap stage 2. The usability follow-up U1–U3 is planned in TODO.md; implementation has not started.
- User authorization: "Agreed: declare stage 2 accepted, then plan the usability tasks" (the user's request, translated from Chinese), following the S1 trial below.
- Decision: the acceptance criterion changed from a human real-idea, actual-next-day trial to the agent-run trial in S1. TODO.md T5 keeps the original wording as history, with a dated revision note listing what the evidence does not cover (cross-model review, real human next-day memory loss, genuine confirmations).
- Updated: TODO.md (T5 items checked under the revised criterion; U1–U3 with decisions Q11–Q14), docs/design.md §12 and status line, docs/manual-acceptance.md (filled record and retrospective), docs/protocols.md and its packaged copy (stage-acceptance wording), framework CHANGELOG template (L2 note), README.md and AGENTS.md (scope and next work).
- Compatibility: wording only; no object fields, formats or command behavior changed, so no data migration is needed. Because two packaged framework templates changed, running `init --project` on a workbench created before this commit reports conflicts on framework/protocols.md and framework/CHANGELOG.md and preserves them (existing init behavior). The only such workbench is the S1 scratch trial.
- **Verified**: `uv sync --locked --dev`; **292 passed**; Ruff lint/format checks, mypy (20 source files) and CLI help passed. The docs and packaged protocols.md are byte-identical. The edited documents contain no Chinese text.
- Pending decisions: Q11–Q13 (default confirmer, `draft` command, `rule` command) need confirmation before U1/U2 start. Q14 recommends deferring both L1 changes.
- Session ID: unavailable in the current environment.
- Blockers: none.
- Next step: confirm Q11–Q13, then implement U1 in its own session.

## 2026-11-02 — S1: agent-run workflow trial

- Status: **Verified**: an agent-run, same-day simulation of the stage-2 workflow completed end to end, and a fresh session recovered the project from files alone. This is a simulation, not the next-day human trial in docs/manual-acceptance.md.
- User authorization: the user asked the agent to run one usage trial and report the experience, then to record it here.
- Researcher statement (2026-11-02): no human trial is needed; the researcher considers this simulation accurate enough. **Pending**: whether this formally accepts roadmap stage 2 and replaces the manual-acceptance criterion in TODO.md T5 and docs/design.md §12. TODO checkboxes stay unchanged until that is confirmed.
- Setup: a scratch workbench outside this repository, with project `compaction-tail`. The idea was whether RocksDB compaction stalls dominate p99 write latency on NVMe. The agent wrote the idea and acted as the researcher; all confirmations were simulated. The reviewer and the resume session were fresh-context subagents of the same model (claude-opus-5-5), so the review was not cross-model. The scratch location is not durable.
- Session ID: unavailable in the current environment.

### Actual run

- **Verified**: `init` (0.17 s) → three Claims (C-001..C-003) via `new claim` → independent reviewer subagent, given only AGENTS.md, roles/reviewer.md, the brief and the three Claims, returned eight draft objections → raw output archived and Run R-001 recorded → four Objections taken in (O-001 fatal, O-002/O-003 major, O-004 minor) → `status` → Decision D-001 → `handoff --input` → draft reviewed → `--apply` → replay was idempotent → workbench Git commit. Every command exited as expected; stored statuses and stage stayed unchanged.
- **Verified**: error probes (an invalid enum, missing `--confirm`, a missing body section) reported `file:line: field`. An absolute `--input` path was rejected.
- **Verified**: a fresh session that read only the files named by the entry protocol correctly answered the goal, the open fatal/major objections, the next step and the raw-review location. It read about 10 files (roughly 2,500 words). Its answers matched `status`.

### Findings (inputs for the next usability task; no code changed)

1. Creating objects is the main friction: 9 objects took 9 hand-written YAML drafts (114 lines) and 9 long commands. Field names have to be learned from formats.md, absolute `--input` paths are rejected, and drafts accumulate unexplained in `runs/manual/`.
2. No command records an Objection Response/Ruling or a status change with a Decision reference. After D-001, O-001/O-002 stayed `open`, and the resume session could not tell whether they were resolved.
3. Generated headers are hard to read: keys are sorted alphabetically, long strings fold at 80 columns, and timestamps carry microseconds. `last_handoff` is a bare 90-character filename without `sessions/`. Run `output` names a directory rather than a file. `new` prints absolute paths while `handoff` prints root-relative ones.
4. `status` lists IDs without statements. A stale brief section raises no hint (consistent with Q2).
5. Objections have a single target; one review draft that attacked two Claims had to be split or noted in prose.
6. Positive: the review produced research value (a genuinely fatal undefined-metric objection). handoff safety was invisible in normal use, and AGENTS.md context overhead was not a problem in practice.

- Checks: no code or tests changed, so the software checks were not rerun. The diff was inspected and contains only this file.
- Blockers: none.
- Next step: confirm the stage-2 acceptance question above, then plan a usability task from findings 1–3 before stage 3.

## 2026-11-01 — D1: English documentation

- Status: **Verified**: all maintained documentation is in English; documentation, package and existing software checks passed.
- User authorization: translate all documentation into English, then commit and push.
- Scope: root collaboration rules, README, task/decision records, this full session history, L1/L2 contracts, examples, manual acceptance checklist and packaged document copies. The design and other templates were already in English.
- Language policy: maintain documentation, templates, progress records and commit messages in English; conversation follows the user. Preserve Unicode fixtures as test data.
- Compatibility: documentation wording and sample prose only; no object fields, enums, format versions or executable logic change. No persisted data migration is needed. Existing edited workbench templates still follow init's conflict-preserving behavior.
- Acceptance boundary: T5 software remains complete, while the real-project, actual-next-day trial and researcher acceptance remain pending.
- Session ID: unavailable in the current environment.
- **Verified**: all 20 tracked Markdown documents contain no Chinese text and pass UTF-8/LF, whitespace and code-fence checks; all 16 local links resolve. Three published contract copies are byte-identical to docs originals. Historical task checkboxes remain unchanged.
- **Verified**: offline locked synchronization succeeded; full suite **292 passed** in 24.87 seconds. Ruff lint/format checks, mypy (20 source files) and CLI help passed. No executable code or tests changed.
- **Verified**: wheel/sdist built successfully and exclude local tools, environments, caches and Git metadata; all 25 packaged template assets match source. An isolated wheel installation outside the checkout generated 12 English Markdown paths and passed the README Claim example, all four commands and idempotent handoff.
- Verification correction: the initial smoke harness placed its draft directly under runs, where status correctly rejected it as misplaced Run metadata. Repeating with README's documented runs/manual/claim.md location passed.
- Delivery: existing project-local Git identity; commit message \`docs: translate D1 documentation and templates into English\`. Push to origin/main is explicitly authorized; verify remote HEAD after pushing and report its result in the closing response.
- Blockers: none.
- Next research task: the real-project first-day trial and actual-next-day recovery in docs/manual-acceptance.md, once the researcher supplies the idea and separate directory.

## 2026-10-31 — T5: handoff, recovery and end-to-end verification

- Status: **Verified: T5 software and automated verification complete; manual stage acceptance pending.** Roadmap stage 2 has not been declared accepted.
- User authorization: continue development. This session implements handoff, prepares manual trial steps, updates progress and commits.
- L1 outputs: metadata updates preserving YAML comments/quotes and complete bodies; draft/applied handoff formats; complete-file writes, POSIX write locking and recoverable transactions.
- L2 outputs: protocols/handoff.py drafts, confirmed application, replay by full draft digest and recovery; L3 adds handoff --input/--apply/--confirmed-by/--confirm.
- Locations: code/tests, README, docs/formats.md, docs/protocols.md, docs/manual-acceptance.md and workbench templates. handoff prints a root-relative path directly usable with --apply.
- Session ID: unavailable in the current environment; not fabricated.

### Actual verification

- **Verified**: final handoff/recovery/end-to-end checks **34 passed**, full suite **292 passed**; Ruff lint/format checks and mypy passed (20 source files), including two actual forced-process-exit scenarios and end-to-end recovery.
- **Verified**: default drafts write only runs and explicitly mark unavailable session content as unknown; unknown session IDs are null. Only explicit confirmation updates sessions/PROJECT, preserving body, comments, stage, other metadata and original draft.
- **Verified**: replaying the same draft adds no record; replaying an older draft after a newer handoff never reverts PROJECT. Changed baselines, invalid fields, wrong projects/paths and broken Decision references refuse writes.
- **Verified**: an orphan session without a recovery journal is not falsely reported complete. Replayed records must be reachable in current handoff history; existing recent_decisions order and handwritten duplicates are preserved.
- **Verified**: actual child processes called os._exit after session publication and PROJECT publication. Retrying the same draft recovers with exactly one applied record; the OS releases the POSIX lock.
- **Verified**: preparation/PROJECT write failures preserve original content and complete recovery images. External edits, corrupt checksums, conflicting sessions and recovery intents attempting stage changes refuse overwrites and preserve the files. status reports pending state or modified application sources.
- **Verified**: synthetic research data exercises separate processes for init → new Claim → archive simulated review/Run → confirmed Objection → status → handoff → Git commit → fresh-process C0 reading, recovering goal, unresolved objections, next step and provenance. This is neither actual independent model review nor next-day manual acceptance.
- **Verified**: a fresh virtual environment installed the wheel and ran all four commands, handoff replay and entry recovery outside the checkout. Stage remained unchanged, PROJECT bytes/mtime stayed unchanged on replay, and status was valid.

### Protocols and requirements

- L1: implements previously unpersisted handoff formats, specifying full draft SHA256 session suffixes, previous_handoff to verify membership in current applied history, and internal recovery records. Seven object fields/versions are unchanged; no actual old handoff data in the repository needs migration.
- L2: independent-review input exclusions take priority over interactive C0 entry order, resolving the conflict between default handoff reading and reviewer history exclusions. Workbench AGENTS and documentation are synchronized.
- Updating two files is not a single atomic operation: persist complete before/after/session/draft images first, report incomplete status while pending, and retire the journal before cleanup after completion.
- Handoff writes currently require POSIX flock, hard links, atomic rename and file/directory fsync. Recovery retains the first confirmed payload/confirmer. Corruption or external-edit conflicts require operator handling without automatic journal deletion or overwrites.
- No models, networking or automatic research-repository commits. Recovery protection is optimistic concurrency checking; external editors do not participate in locks, so pause manual PROJECT edits during application.

### Handoff and remaining work

- Manual acceptance has not run. The researcher still needs to supply a real idea and separate research directory. Both were requested interactively, without substituting synthetic data.
- Next: follow docs/manual-acceptance.md for first-day Claims, independent manual review, confirmed Objections and handoff on a real idea; resume in a fresh session the actual next day, then obtain researcher acceptance and a retrospective.
- Software blockers: none. Stage acceptance requires an actual two-day trial and an explicit recorded researcher ruling.
- Commit message: `feat: implement T5 handoff and recoverable session updates`.

## 2026-10-31 — T4: read-only status and consistency diagnostics

- Status: **Verified: T4 complete**; T5 not yet started, stage 2 incomplete.
- User authorization: continue. This session implements T4, records actual checks and commits.
- L1 outputs: core/project.py validates project charters; core/inspection.py reads the selected project and checks layout, objects, direct references and brief markers.
- L2 outputs: protocols/status.py returns structured status, conditions and diagnostics; L3 adds status. No dependencies or L1 object fields/versions were added or changed.
- Documentation: README usage, synchronized docs/protocols.md/template scope, unknown conditions and exit codes; this file and TODO updated.
- Session ID: unavailable in the current environment; not fabricated.

### Verification results

- **Verified**: status-specific checks **40 passed**, full suite **258 passed**; Ruff lint/format checks and mypy passed (16 source files).
- **Verified**: covers three evidence grades, supports/refutes directions, invalidated evidence, fatal/major/minor and non-open objections. Reports minor objections and supported eligibility independently without choosing a status for the researcher.
- **Verified**: supported/accepted Claims losing support retain historical statuses and prompt human review. Ruling notices on valid data exit 0 without changing objects/stages.
- **Verified**: broken references, duplicate IDs, corrupt files/illegal statuses, wrong directories/filenames, missing charter fields, illegal stages/overlong charters and creation locks explicitly fail with exit 1 and unknown conditions, never a claim of full validity.
- **Verified**: local/cross-project, invalid/unclosed brief references have file/line diagnostics. Fenced/indented code examples are excluded. No claim of semantic consistency between propositions and evidence.
- **Verified**: complete directory listings, file bytes and mtimes stay unchanged on success/error paths. No caches, indexes, temporary files or Git metadata are written. Severity/numeric-ID sorting is deterministic and projects stay isolated.
- **Verified**: a fresh environment installed the wheel and ran init/new/status outside the checkout. Success worked; broken references exited 1 with unknown conditions. Both paths preserved bytes/mtimes.
- Existing layering/import-without-CLI tests still passed. No network, models or independent acceptance session was used.

### Handoff

- Scope: selected project's seven types, PROJECT, brief and direct cross-project references. Other projects are not scanned for incoming evidence/objections. On errors, counts cover only validated records, not the complete network.
- L2 change note: separate ruling notices from data errors and show incomplete conditions as unknown. The read-only command does not rule on gates. L1 fields/version unchanged; no data migration.
- Commit message: `feat: complete T4 read-only status and consistency diagnostics`.
- Blockers: none.
- Next: T5 handoff drafts/confirmed application, recoverable writes and fresh-process recovery tests. Next-day recovery of a real idea still requires researcher trial/acceptance.

## 2026-10-31 — T3: object encoding/decoding, validation and confirmed intake

- Status: **Verified: T3 complete**; T4–T5 not yet started, stage 2 incomplete.
- User authorization: continue and preserve progress. This session completes T3, updates this file/TODO and commits.
- L1 outputs: core/documents.py, codec.py, schema.py, repository.py; data structures/diagnostics, constrained YAML subset, seven field/body schemas, file/direct-reference validation, numbering and exclusive publication.
- L2 output: protocols/intake.py requires human confirmation and creates only initial statuses. L3 adds new and argument/error presentation. Core/protocols gained no CLI/model dependencies.
- Documentation: executable README draft/new examples; formats/protocols clarify draft fields, confirmation, archive paths, locks and replay semantics. Published template copies synchronized.
- Session ID: unavailable in the current environment; not fabricated.

### Verification results

- **Verified**: full suite **218 passed**; Ruff lint/format checks and mypy passed. All seven formal examples and per-type invalid variants are tested.
- **Verified**: encoding round trips preserve Chinese text, code fences and body separators. Reject duplicate keys, explicit tags, aliases/anchors, merges, nonfinite values, wrong types, missing/unknown fields/versions and illegal status conditions, with file/line/field diagnostics.
- **Verified**: same/cross-project objects and source Runs resolve. Missing projects/targets, wrong reference types, missing verification records/local materials and raw output outside the referenced Run archive fail.
- **Verified**: without confirmation, formal objects are not written. IDs increase by project/type; repeated input allocates a new ID without overwriting. Two independent processes cannot claim one number; a lock causes explicit failure and permits retry after coordination.
- **Verified**: injected fsync/exclusive-publication failures leave no partial object, temporary files or this invocation's lock. Existing targets are preserved. Escape paths and input/target directory symlinks are rejected.
- **Verified**: L1/L2 import without third-party packages. With format dependencies installed and all CLI adapters blocked, direct L2 calls perform actual intake. File-I/O modules such as os/tempfile were added to architecture allowances; external command execution remains forbidden.
- **Verified**: a fresh environment installed the wheel and ran init outside the checkout, then created C-001, R-001, E-001, O-001, D-001, X-001, S-001 and reread/validated references. Stage remained explore; only test samples were used, without models.

### Handoff

- L1 impact: implements agreed v1 fields/status constraints and clarifies basic UTC Run archive names. No object fields/version changed; no actual old research data needs migration. L2 confirmation details are in docs/protocols.md.
- Boundary: new validates candidate direct references without recursively traversing a cyclic network. Whole-project diagnostics belong to T4. Valid format/provenance records do not prove scientific truth, and confirmation parameters are not authentication.
- Forced termination may leave `.toulmin-new.lock` or temporary files. The tool never deletes locks automatically; operators must inspect state and active writing sessions before recovery.
- Commit message: `feat: complete T3 object validation and confirmed intake`.
- Blockers: none.
- Next: T4 reuses Repository/schema for read-only status, evidence/objection conditions and brief-reference diagnostics, without automatic state/stage changes.

## 2026-10-31 — T2: workbench templates and init

- Status: **Verified: T2 complete**; T3–T5 not yet started, stage 2 incomplete.
- User authorization: research and proceed to the next step. This session implements/commits T2 without models or a real research project.
- Outputs: `src/toulmin/cli/initialize.py`, packaged templates, init, dedicated tests, README usage and protocol refinements. L1/L2 Python modules are unchanged.
- Templates: research AGENTS, relative CLAUDE link, Gemini project settings, L0 principles, published L1/L2 documents, reviewer/scribe contracts, global placeholders, project charter/brief and eight object/handoff directories.
- Session ID: unavailable in the current environment; not fabricated.

### Verification and implementation boundaries

- **Verified**: init-specific checks **34 passed**, full suite **93 passed**, including existing core/protocol layering checks. Ruff lint/format checks and mypy passed.
- **Verified**: reject file/link/directory conflicts before writing. Repeated invocation preserves bytes/mtimes; new projects preserve old-project edits. Nested research repositories do not change parent Git metadata.
- **Verified**: failure injection covers file publication, symlink creation and Git metadata copying; cleanup affects only this invocation's additions. A competing writer's target is preserved without falsely reporting success.
- **Verified**: wheel includes hidden settings, empty-directory placeholders and complete framework documents. A fresh environment installed it and ran init, unchanged repetition, adding a project and Git status outside the checkout. The new Git repository has no initial commit.
- **Verified**: Gemini context.fileName was checked against official configuration documentation. The design's earlier contextFileName spelling was corrected; docs/protocols.md records the source link.
- Tests compare published copies with docs originals to avoid checkout dependencies and contract drift. README documents synchronization.
- Requirements: local Git and symbolic/hard-link support. Reinitializing edited global templates reports conflicts while preserving files. Forced termination can leave files/Git metadata requiring inspection; ordinary-error rollback is tested.

### Handoff

- No research conclusions or gate rulings were added. init creates templates/local Git only, without automatic commits or model calls.
- Commit message: `feat: complete T2 workbench templates and init`.
- Blockers: none.
- Next: T3 seven-type encoding/decoding, full validation and new using docs/formats.md and this session's templates.

## 2026-10-31 — T1: contracts and testable package

- Status: **Verified: T1 complete**; T2–T5 not yet started, stage 2 incomplete.
- User authorization: configure Git identity only in this project and continue with TODO Q1–Q9 recommendations.
- Git identity: Tianchi YU / yu-tianchi@outlook.com. `git config --show-origin` confirmed both came from `.git/config`; global configuration was unchanged.
- Outputs: finalized AGENTS, design revisions, docs/formats.md, docs/format-examples.md, docs/protocols.md, README, Python package, uv.lock and test configuration.
- Code scope: L1 canonical IDs/project references, L2 session read order, L3 help/version entry point. Full encoding/decoding and four research commands were not yet implemented.
- Isolated environment: uv 0.13.6 and CPython 3.12.16 under project .tools/, dependencies in .venv/, cache in .uv-cache/. All ignored, without replacing system Python or editing shell settings.
- Session ID: unavailable in the current environment; not fabricated.

### Verification results

- **Verified**: `uv sync --locked --dev --offline` succeeded; `uv run --locked --offline pytest -q` reported **59 passed**. Ruff lint/format checks passed, mypy found no errors in 7 source files, and CLI --help/--version ran.
- **Verified**: tests cover illegal/noncanonical IDs, path-like references, session read order and upward-dependency detection. A `python -I -S` subprocess without third-party packages and actively blocking CLI imports successfully imported/called core/protocols.
- **Verified**: a fresh virtual environment synchronized offline from the lockfile. Built sdist/wheel, installed the wheel and ran entry points/all 59 tests outside the checkout, importing from that environment's site-packages.
- **Verified**: YAML headers of seven samples parse; common fields/type coverage/local documentation links are valid. This is not the full schema/reference validator, which was not yet implemented.
- **Verified**: wheel/sdist exclude .tools, .venv, .uv-cache and .git. Archive inspection ruled out inclusion behind build-cache warnings. Cross-filesystem hard links fell back to copying without affecting installation.
- Initial tests exposed a CLI help-wrap assertion failure; normalized whitespace comparison fixed it. Also removed a pytest parameter-iterator deprecation warning.

### Handoff

- Decisions: adopt Q1–Q9 recommendations; docs/formats.md and docs/protocols.md define key contracts. L0 unchanged; L2 permissions/stage diagram reconciled. No old research data needs migration.
- Commit scope: planning documents, T1 code/tests/lockfile and explicitly revised design. Excludes isolated tools, caches and build outputs. Message: `feat: complete T1 contracts and testable package`.
- Blockers: none.
- Next: T2 independent research workbench/project templates and init, accepted against TODO repetition, conflict, path and project-isolation criteria.
- Stage boundary: real-project next-day recovery and independent manual acceptance remain in T5. This session's self-tests do not replace them.

## 2026-10-31 — Pre-implementation planning for stage 2

- Status: planning drafts written; awaiting researcher confirmation. T1–T5 not started.
- Task: read `docs/design.md`, draft repository rules, technology recommendations, task criteria and pre-implementation decisions, without code implementation.
- Outputs: `AGENTS.md`, `TODO.md` and this file. Original design unchanged.
- Session ID: unavailable in the current environment; not fabricated.

### Findings and checks

- **Verified**: read the full design. Section 13's first four items require decisions before the skeleton. Section 7's diagram/gate table differ in stage mapping; section 6's role-directory permissions need reconciliation with archiving all AI output in runs first.
- **Verified**: the initial repository had no commits. Existing untracked `docs/design.md` was not staged without authorization.
- **Verified**: `python3 --version` returned 3.7.5; `command -v uv` found no command. The proposed toolchain could not yet run.
- **Verified**: `git var GIT_AUTHOR_IDENT` exited 128 with Author identity unknown. No Git name/email was configured, so this session could not commit.
- **Guess (recommendation)**: Python >=3.12 + Typer + ruamel.yaml + pytest, preserving Markdown bodies with no CLI dependency in L1. See TODO.md for rationale/official links.
- **Verified**: three drafts passed UTF-8/LF, trailing-whitespace, code-fence and local-document-path checks. TODO has exactly five tasks with acceptance criteria, plus Q1–Q10. `git diff --check --no-index /dev/null <file>` reported no formatting issues.
- No code tests ran: the repository had no implementation, tests or dependency configuration. These checks demonstrate planning-document structure, not a functioning skeleton.

### Decisions and blockers

- User decision: plan only in this session, then await confirmation.
- Unconfirmed: TODO.md Q1–Q9 (types, brief, evidence grades, stack/MCP, knowledge-base scope, lifecycle, confirmation boundaries, IDs, repositories/command semantics).
- Commit blocker: Q10, missing researcher-supplied Git name/email. No fabricated identity or global configuration changes.
- No commit yet; files remain in the worktree for review. No dependency installation, implementation or research-state changes started.
- Next: obtain planning confirmation and Git author identity, revise documents accordingly, commit the plan, then begin T1.
