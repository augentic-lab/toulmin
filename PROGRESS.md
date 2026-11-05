# Toulmin development progress

## 2026-11-05 — WI8 passed; trial cleanup

- Decision: the researcher tried WX6 (scan, picker, `--in`) and judged it good ("蛮好的"), declined renaming `workspaces` after a `workspace scan` slip, and instructed "按你的建议，记录 WI8 通过并清理". WI8 is passed; the WI8 condition item is ticked.
- Cleanup (operator, on instruction):
  - Trial workbenches copied without .git to `~/notes/toulmin/wi8-2026-11-04/researcher-v2/` (verified identical with `diff -rq`), then `/tmp/toulmin-trial-1ajH` and `/tmp/toulmin-trial-v2` removed.
  - Three live sessions in profile `toulmin-trial-wi8` archived. `aoe list` shows all four trial sessions archived; no tmux session or process refers to the trial folders; tmux count 9.
  - Both entries forgotten from the researcher's workspace list (now empty). The profile, the `~/.local/bin/toulmin` link and the researcher's config are kept.
  - Ledger section "WI8 passed and cleanup" added; MANIFEST regenerated and checked (712 files).
- Finding W9 (recorded, not fixed): `handoff_mutex` lock files accumulate in /tmp (about 14,800 from test runs). They were not deleted. Candidate fix in tests only; requires authorization.
- Checks: documentation and records only; no code changed, so tests were not rerun (last full run 1276 passed at a0f1f6a). Diff inspected.
- Blockers: none. Next step: real use on a research workspace (`toulmin open` in a real folder); W7 and W9 are open candidates.
- Session ID: unavailable.

## 2026-11-05 — WI8 v2 trial ruling and WX6 known workspaces

- Decision: the researcher ruled the WI8 v2 trial a **conditional pass** ("按你的建议，有条件通过，开始实现 WX6"): usable, on condition that workspaces outside the current directory are recognized (trial question 3). The same message authorized WX6. WI8 stays open until the researcher confirms WX6 meets the condition; agent tests are not that confirmation.
- WX6, L3 only (accepted design `~/notes/toulmin/workspace-registry-design.md`, §7 notes):
  - `cli/registry.py`: `$XDG_STATE_HOME/toulmin/workspaces.json` (default `~/.local/state/...`), schema_version 1, entries `{path, name, last_opened}` keyed by normalized absolute path. Strict validation; a damaged file is reported and never rewritten; atomic writes. Each listing re-checks the folder (workspace, legacy, damaged, missing).
  - Registration: `init` (workspace), `toulmin open` (just before delegating to AoE) and a confirmed `workspace adopt`. A failed update is a stderr notice only. Read-only commands never write.
  - `toulmin open`: with no workbench at or above the current directory, no `--root`/`--in` and no CHILD, it lists the known workspaces and asks which to open. `i` initializes an empty directory; the default is quit. Without a terminal it only lists. An empty list keeps the WX2 behavior.
  - `toulmin open --in NAME_OR_PATH [CHILD]`: case-insensitive name or path; an ambiguous or unknown name lists the candidates (exit 2); `--in` cannot be combined with `--root`.
  - `toulmin workspaces` lists (name, path, last opened, missing/pending flags); `forget PATH` removes an entry without touching the folder; `scan [--profile]` reads `aoe list` (read-only) and adds workspace roots or the roots of `projects/NAME` sessions, recorded as "found by scan".
  - `config show` prints the list location. conftest isolates `XDG_STATE_HOME`.
  - README, docs/protocols.md WX6 section (packaged copy synced) and framework CHANGELOG updated.
- Tests: `tests/cli/test_workspaces.py` (17 cases: location, refresh, unusable files, registration and read-only commands, live listing and forget, picker open/quit/invalid/missing/init/non-terminal/inside a workbench, `--in` name/path/child/ambiguous/unknown/conflict, scan with a fake AoE client). Pseudo-terminal smoke with isolated XDG dirs and `TOULMIN_AOE_COMMAND=/bin/false`: the picker listed two same-named folders, choice 2 opened the chosen root, and the stand-in AoE then failed as expected. No live AoE session run.
- Records: TODO (WX5 trial ticked as a conditional pass, WX6 implementation ticked, new open item "WI8 condition"), AGENTS dated entry, ledger "Researcher ruling on the v2 trial" with MANIFEST regenerated and checked.
- Checks: `uv run --locked pytest -q` 1276 passed (7m06s; test_workspaces.py rerun after ruff formatting: 17 passed); ruff check, ruff format --check and mypy clean; `git diff --check` clean; packaged protocols.md byte-matches docs.
- Blockers: none. Next step: the researcher uses `toulmin open` from outside a workspace (or `toulmin workspaces scan` for the v1 trial workspace) and confirms whether the WI8 condition is met.
- Session ID: unavailable.

## 2026-11-05 — W8 fix and WX6 workspace registry design

- Decision: after the v2 trial questions, the researcher chose option ① ("是①，按你的建议写设计并修 W8"): fix W8 and write a registry design. No trial ruling was given; WI8 and the WX5 trial item stay open.
- W8 (observed in the trial files, read only): a proposal was applied, then the agent drafted a workspace handoff with `confirmed_changes: []` whose next step still asked to decide it; applying the handoff copied that stale next step into WORKSPACE.md. Drafting only checked that cited receipts are applied.
- Fix:
  - L2 (read-only, reason recorded in docs/protocols.md "W8"): `workspace_handoff.uncited_receipts(root, cited)` lists applied workspace change receipts later than the latest applied handoff (all before the first) that the summary does not cite. It reuses `applied_receipt`; absent, rejected or unreadable receipts are not listed.
  - L3: `handoff_preview` prints a warning naming them and advising a redraft; this covers the agent's draft output, the `--apply` preview and `toulmin decide`, whose own run-only note is removed. Warning only, never a refusal.
  - Native workspace context asks the agent to cite every such receipt and redraft when warned. The workspace AGENTS.md template is unchanged (no released.json change).
  - Packaged protocols.md copy and framework CHANGELOG updated.
- Tests: two new tests in `tests/cli/test_workspace_handoff.py` (helper cases: no handoff, cited, older than the last handoff, rejected, later change; trial scenario through the CLI draft and preview, nothing else written); existing draft test asserts no warning when cited; decide test asserts the warning.
- WX6 design (documentation only, outside the repository): `~/notes/toulmin/workspace-registry-design.md`. A user-level registry `~/.local/state/toulmin/workspaces.json` (cache, path as identity, never research data) written on init/open/adopt; `toulmin open` offers known workspaces when none is found; `toulmin open --in NAME [CHILD]`; `toulmin workspaces` list/forget; optional explicit `scan` from AoE session paths. No stable workspace ID (that would be an L1 change). The researcher then accepted all five decisions ("按你的建议，五个决定都同意"); per decision 5, implementation follows the trial ruling.
- Ledger: `~/notes/toulmin/wi8-2026-11-04/ledger.md` gains "Researcher v2 trial questions" with W8 and Q3; MANIFEST regenerated and checked.
- Checks: `uv run --locked pytest -q` 1259 passed (7m07s); ruff check, ruff format --check and mypy clean; `git diff --check` clean; packaged protocols.md byte-matches docs. Record-only edits after the run (AGENTS/TODO/PROGRESS) were inspected in the diff.
- Not done: no live AoE run; the trial ruling is pending. Noted for the researcher: the trial's `projects/scheduling` has no applied handoff (A10 apparently not applied), and the v1 session "Workspace: Serving Research" (141011097a524196) still needs archiving.
- Blockers: none. Next step: the researcher gives the WI8 v2 trial ruling; then WX6 implementation on their go-ahead.
- Session ID: unavailable.

## 2026-11-04 — WX5: trial instructions v2 for the improved entry

- Decision: the researcher authorized WX5 ("好的，开始 WX5"). Documentation only; no code changed.
- Output (outside the repository):
  - `~/notes/toulmin/wi8-2026-11-04/researcher-trial.md` v2. The v1 instructions are kept as `researcher-trial-v1.md`.
  - A01–A10 now use `toulmin open` (init prompt, scope from the current directory, re-delivery instead of `refresh`) and `toulmin decide` (A04/A05/A08/A10), with a purpose per step.
  - A06 is reframed as "continue from files only; daily equivalent: a new session the next day".
  - Each step lists what to watch, including whether the agent offers proposals unprompted (O5) and the Model line.
  - Setup keeps the trial profile in `AGENT_OF_EMPIRES_PROFILE` (so real sessions still default to main), writes the researcher's own config, and links `~/.local/bin/toulmin`.
- Observation W7 (inferred from code, not live-verified): native context instructions name `toulmin workspace propose`/`aoe handoff` as a bare `toulmin` command, while the receipt command uses the absolute interpreter path. An agent shell without `toulmin` on PATH would fail those steps. The v2 setup adds the link as a workaround; a product fix (absolute command paths in context) is a candidate follow-up after the trial. Recorded in the WI8 ledger.
- Checks: commands in v2 were checked against the current CLI (`open`, `open --new-session`, `decide`, `config show`, `aoe session archive TITLE`, session title `Workspace: serving` for a directory named serving). WX2/WX4 pseudo-terminal smokes cover `open`/`decide`. No live AoE session was run. Code tests were not rerun (documentation only).
- Blockers: none. Next step: the researcher runs the v2 trial; WI8 and the WX5 trial item stay open until their ruling.
- Session ID: unavailable.

## 2026-11-04 — WX3: show the model the native session reports

- Decision: the researcher authorized WX3 ("好的，开始实现 WX3").
- L3 only:
  - `adapters/provider_logs.py` finds the bound conversation's own log: Codex `$CODEX_HOME/sessions/*/*/*/rollout-*-ID.jsonl`, Claude `$CLAUDE_CONFIG_DIR/projects/*/ID.jsonl`, with `~/.codex` and `~/.claude` as defaults. It reads backwards over at most the last 16 MiB and extracts only the model and effort: from the latest Codex `turn_context`, or from the latest non-synthetic Claude `assistant` message.
  - Provider IDs and values must match conservative patterns. Symlinked logs are ignored. Anything missing or unrecognized is "not reported".
  - `WorkspaceView.model` carries the report. `aoe status`/`open` print `Model: NAME, effort E (reported by the AGENT session log)`, or "not yet reported (the native CLI's own configured default applies)", under BINDING; `--json` includes it.
  - Nothing is written. The agent's state.md is unchanged, so model changes never make a context stale.
- Tests:
  - conftest points `CODEX_HOME`/`CLAUDE_CONFIG_DIR` at temporary directories for every test, so real session logs are never read.
  - 12 new tests: the reader, application status and the CLI line.
- **Verified**:
  - Full suite 1257 passed. ruff, ruff format (163 files), mypy (74 files) and `git diff --check` are clean.
  - The reader on copies of the WI8 logs (in a temporary home) returned gpt-6-luna/medium and claude-opus-5-5/high, matching the WI8 screens.
  - No live AoE session was run.
- Docs: README, docs/protocols.md WX3 section with its packaged copy, and the framework CHANGELOG.
- Note: the session restarted while the suite ran; the recorded result was read from its output file (1257 passed, exit 0) before committing.
- Blockers: none. Next step: WX5. Revise researcher-trial.md for `toulmin open`/`decide` and the A06 purpose; the researcher then resumes the WI8 trial.
- Session ID: unavailable.

## 2026-11-04 — WX4: `toulmin decide`, one-pass researcher decisions

- Decision: the researcher named the command and authorized WX4 ("就用 toulmin decide，开始实现 WX4").
- L3:
  - `cli/decide.py`. The inventory lists pending workspace change packets, pending child creation packets, pending workspace handoff drafts, then unapplied project handoff drafts with a current base PROJECT.md. Stale drafts are counted, not offered.
  - Each item shows its existing preview without the copy-paste command lines and is decided alone: `[a]pply / [r]eject / [s]kip / [q]uit`. The default is skip, handoffs have no reject, and refused packets offer no apply. Decisions call the same protocol functions as the individual commands, with the resolved actor and `approval_text: "toulmin decide: a"`.
  - A workspace handoff made stale by a change applied in the same run is redrafted from its unchanged summary, with a note naming uncited receipts. Drafts after an applied handoff are skipped as superseded.
  - Failures are reported and the item stays pending. Without a terminal, decide only lists.
  - The preview renderers gained `commands=False`. The workspace handoff preview and result were extracted for reuse. `toulmin open` now counts the same inventory and points to decide.
- Guidance: the workspace AGENTS.md template and native context text say pending items await `toulmin decide`, and ask the agent to offer a charter proposal once discussion settles a direction, constraint or resource (O5). released.json gained the new template digest (13 AGENTS.md digests).
- L2 (presentation text only): the workspace state card's pending-action line names `toulmin decide`. Reason: the old line told the agent to show apply/reject commands; no logic or format changed.
- Docs: README, docs/protocols.md WX4 section with its packaged copy, and the framework CHANGELOG.
- **Verified**:
  - 10 new decide tests: list-only without a terminal, actor required, apply/reject/regenerate in one pass, skip/quit, refused packet, superseded handoff, changed summary not regenerated, project handoffs incl. superseded and stale, failure continues. 1 open test updated.
  - Full suite 1245 passed. ruff, ruff format (161 files), mypy (73 files) and `git diff --check` clean.
  - Pseudo-terminal smoke of the installed CLI with a configured actor: piped input lists only; answering `a` applied the packet and the receipt recorded the actor and approval text; a rerun found nothing pending.
  - No live AoE session was run.
- Found: an order-dependent test assumption. Same-second drafts sort by their random suffix, so the test was made order-independent; the product order is path order.
- Known limit: a regenerated handoff keeps the summary's wording and next step, which may predate the decisions just made; decide prints which applied receipts it does not cite.
- Blockers: none. Next step: researcher authorizes WX3 (model line) or goes straight to WX5 (revised trial on the new version).
- Session ID: unavailable.

## 2026-11-04 — WX2: user preferences, root discovery and `toulmin open`

- Decision: the researcher accepted all five WX1 recommendations ("按你的建议，五个决定都同意，开始实现 WX2"): config keys as designed, a [y/N] init prompt, per-item review, stale-handoff regeneration in review, and the order WX2 → WX4 → WX3 → WX5.
- L3 only (no L1/L2 change):
  - `cli/settings.py`: `$XDG_CONFIG_HOME/toulmin/config.toml` (`actor`, `[aoe] profile/agent/attach`), strict validation without repair; precedence flag > saved binding > environment > config > default; `--root` discovery callback (nearest workspace or legacy workbench above the current directory, stderr notice when it moves; explicit `--root` used as given).
  - `cli/entry.py`: `toulmin open [NAME]` (child from `projects/NAME/`, terminal-only init prompt defaulting to no, unrelated directories refused, legacy workbenches need a project, pending-review count) delegating to the shared `aoe open` path; `toulmin config show` with value sources.
  - `application/aoe.py`: an unbound scope takes the given default profile before `AGENT_OF_EMPIRES_PROFILE`; a new session's agent is the flag, else the replaced binding's, else the fallback. Existing bindings keep their agent.
  - Every confirming command resolves the actor through the same function; `aoe open` gained `--attach/--no-attach`.
- Behavior change: `toulmin status` from a project directory now finds the workbench (previously an error with a `--root` hint; an explicit `--root .` keeps the hint). The test was updated accordingly.
- Docs: README quick start; docs/protocols.md (actor default and a WX2 section) with its packaged copy; framework CHANGELOG. The WI1 contract (workspace-formats.md) is unchanged; protocols.md records the config actor as a further fallback.
- **Verified**: 30 new tests (config parsing/refusal, XDG handling, actor/profile/agent/attach precedence, discovery, every `open` branch with fake AoE); tests isolate `XDG_CONFIG_HOME` so the real user config is never read. Full suite 1235 passed; ruff, ruff format (159 files), mypy (72 files) and `git diff --check` clean. Smoke of the installed CLI in a scratch directory with `TOULMIN_AOE_COMMAND=/bin/false`: no terminal prints only the init command; answering n creates nothing; y initializes and hands off to `aoe open` (the fake AoE fails with the usual recovery hint); nested `status` finds the root; an unknown config key stops `config show`. No live AoE session was run.
- Found while implementing: `toulmin review` already names the C3 independent-review command, so WX4's unified decision command needs another name (proposal: `toulmin decide`).
- Blockers: none. Next step: researcher authorizes WX4 and chooses its command name.
- Session ID: unavailable.

## 2026-11-04 — WX1: entry and review ergonomics design after a partial WI8 researcher trial

- Trigger: the researcher ran part of the WI8 trial (not all of A01–A10) and raised four observations: too many setup commands (wants configuration and a heuristic start command), how the model is chosen, per-item `workspace apply --confirm`/handoff commands feel clumsy, and why A06 is needed; earlier, whether the agent must be told to save into WORKSPACE.md. The researcher agreed to record them and review a documentation-only design before any implementation ("可以").
- Output: `~/notes/toulmin/workspace-entry-review-design.md` (outside the repository) with E1 user config/root discovery/`toulmin open`, E2 model line from provider logs, E3 one interactive `toulmin review` (per-item apply/reject/skip, stale-handoff regeneration, template guidance), E4 keep A06 with a stated purpose; tasks WX2–WX5 and five decisions. The WI8 ledger records the observations.
- Facts checked (inferred from code unless noted): `--root` defaults to `.` without discovery; profile/actor fall back to binding/environment variables, no config file exists; AoE `session show` has no model field while provider logs record it (verified on WI8 logs); a change proposal and a workspace handoff draft both pin the whole WORKSPACE.md digest, so applying one makes the other stale; handoff drafts record their summary path and digest.
- Checks: documentation-only; no code changed, so tests were not rerun. Diff inspected.
- Decisions pending: the five WX1 decisions. WI8 stays open; WX2–WX5 are not authorized.
- Blockers: none. Next step: researcher reviews the WX1 design.
- Session ID: unavailable.

## 2026-11-04 — WI8 follow-up: researcher decisions W1/W3

- Decision: the researcher accepted both recommendations ("好的，我同意你的建议"). W1: keep the AOE3 rule (a provider identity reported after the first turn resets the binding and sends one new context). W3: give replacement sessions a unique numbered title.
- L3 (`application/aoe.py`): a new version 2 binding takes the scope title, or `<title> (N)` (N = 2, 3, …) when an AoE session at the root (archived and trashed included) already uses it; creation recovery matches the recorded title as before. Version 1 (legacy) bindings keep `Toulmin: NAME`. The binding-title row of workspace-formats.md (both copies) records the suffix; released.json gained the new contract digest; protocols.md records the WI8 L3 rationale and the W1 decision.
- **Verified**: the fake AoE client now refuses a duplicate title and path like real AoE; a new test covers two numbered replacements, a same-title session at another root and recovery of an uncertain numbered creation without a duplicate. Live: `open --workspace --new-session` on the Codex trial workbench (an archived `Workspace: Serving Research` present) created `e5644a277d264b82` titled `Workspace: Serving Research (2)` without manual renaming; context submitted and acknowledged; the session was archived and its tmux session is gone.
- Checks: the first full locked suite with the TUI extra gave **1 failed, 1204 passed in 415.01 s**: the packaged `framework/protocols.md` copy had not been updated with docs/protocols.md. This was misread and committed in edc62ae with only "1204 passed" recorded; corrected in the next commit by syncing the copy (affected files: 111 passed), then the full suite was rerun: **1205 passed in 414.21 s**. Ruff lint/format, strict mypy (70 files) and `git diff --check` passed.
- Limits: the researcher trial remains NOT RUN; a legacy (version 1) replacement still needs the old AoE session renamed.
- Session ID unavailable. Blockers: none. Next: the researcher trial. No push.

## 2026-11-04 — WI8: integrated verification (agent-run) and live native trial

- Authorization: the researcher authorized WI8 ("同意，开始实现 WI8"), including real AoE native sessions that consume subscription quota, on temporary test workspaces only. Recorded in AGENTS/TODO and the external plan. Profile `toulmin-wi8` was created for this; the main profile, active sessions, authentication and model defaults were not touched. Every `--confirm` was an operator fixture approval labelled `WI8 operator (agent; fixture approval, not the researcher)`.
- Evidence (outside the repository): `~/notes/toulmin/wi8-2026-11-04/` — ledger.md (environment, case table, findings, cleanup), technical/ (driver.py, fixture inputs, run1-ledger.json with the failed first run, final/ and committed/ ledgers with per-case commands, exit codes, output, manifest deltas and assertions), native/ (screens, owned-session provider logs, bindings, workbench copies), researcher-trial.md (instructions and the four WS3 questions).
- **Verified, agent-run technical**: driver.py runs the real CLI against disposable /tmp workbenches for A01–A10, F01–F14 and L01 (165 assertions). Run 1 at bdb3353: 24 pass, A10 failed because of a driver assertion (the first workspace reopen after child creation correctly refreshes a stale context); the assertion was corrected and three vacuous checks tightened. Later runs: 25/25 pass (before and after the fix below, and on the committed code). Native parts of A02/A06/A09/A10 and F06–F09 in this driver use an in-process fake AoE client. Base install: an offline wheel in a fresh venv without the tui extra ran `--help`, `init`, `status`, `workspace`/`project` help, packaged templates and an adoption preview.
- **Verified, live Codex** (codex-cli 0.166.0): workspace open (trust prompt left untouched by Toulmin; operator accepted it for the owned fixture), submission, model read and `aoe ack`; unchanged open/open/refresh sent nothing (provider log count unchanged, binding byte-identical); operator child creation started no session and made the workspace context stale; separate child session with its own title and a context without creation sources or workspace activity; child handoff left WORKSPACE.md unchanged and its refresh was delivered after a completed turn; fresh workspace session after archiving received only AGENTS.md, WORKSPACE.md and the applied handoff and answered direction, constraint, resource and next step from files (it misnamed the handoff path's directory).
- **Verified, live Claude** (Claude Code 2.1.318): workspace scope and delivery smoke only — open, trust prompt, refresh, acknowledgement, unchanged reopen without resend, delivery after a completed turn; the agent showed apply/reject commands without running them. No Claude child or recovery was run.
- Fixes (L3 adapter, `AoEClient.ready`): (W2) the busy/dialog word scan covered the bottom 18 lines, so the agent's own reply ("does not approve research", "How would you like to proceed?") refused every later refresh; it now covers the input line, the lines after it and one non-border line above it, while selection menus anywhere in the tail and unrecognizable prompts still refuse. (W4) Claude's empty-composer hint and suggested prompts looked like typed input after ANSI stripping; readiness now captures raw output and treats dim (SGR 2) text as a hint (extended colour arguments are skipped), with an explicit `Try "…"` fallback. Non-dim composer text still refuses. 12 new adapter tests; the affected live steps were rerun after the fix.
- Open findings for the researcher: (W1) when AoE reports the Codex provider ID only after the first turn, the next open resets the binding and sends one extra context (inherited AOE3 identity rule). (W3) AoE refuses `add` with the title and path of an archived or trashed session, so `open --new-session` after archiving fails until the old session is renamed or purged; Toulmin kept the binding safe and retryable (session_id null, zero candidates). Observations: the state card omits the last-handoff path (W5); two recovery hints are imprecise (W6).
- Checks: full locked suite with the TUI extra **1204 passed in 417.24 s** (after the adapter fix; later edits were PROGRESS/TODO/AGENTS only); Ruff lint/format, strict mypy (70 files) and `git diff --check` passed.
- Cleanup: the four owned sessions are archived (one renamed for W3), no owned tmux session or process remains (tmux count equals the pre-trial count); the profile and /tmp workbenches are retained for diagnosis.
- Limits: all agent-run results are technical evidence, not researcher acceptance; the researcher trial (A01–A10 with the four questions and a usability ruling) is NOT RUN. Claude coverage is workspace-only. Native coverage is selected screens plus provider logs, not full transcripts.
- Session ID unavailable. Blockers: none. Next: researcher trial and W1/W3 decisions. No push.

## 2026-11-04 — WI7: previewed additive legacy-workbench adoption

- Authorization: the researcher authorized WI7 after WI6 ("同意，开始实现 WI7"). Recorded in AGENTS/TODO and the external plan. Only temporary fixtures and fake AoE clients were used; no real workbench, AoE/native session, model or network was touched. WI8 was not started.
- Contract clarifications recorded (section 12): (1) a differing `framework/workspace-formats.md` was a conflict, but workbenches initialized after WI1 carry an older pristine packaged copy and could never adopt; a byte-identical released copy is now replaced, any other content stays a conflict. (2) "Released" means every shipped copy, listed by digest in the packaged `workspace_templates/released.json` (shared and workspace AGENTS templates, contract copies) and regenerated from Git history plus the working copy. (3) The plan's creates include the empty record-location placeholders; conflicts are `{path, reason}`; the body adds `## Conflicts`; the contract copy is summarized by digest instead of a full diff. (4) Publication order: other changes, archive plan and seal, WORKSPACE.md, receipt. The schematic example and rules were rewritten accordingly; the status header lists section 12 adoption as implemented.
- L1: `core/adoption.py` — deterministic plan rendering (no time or absolute path), archived-plan identity check, digest/prefix matching (≥16 lowercase hex).
- L2: `protocols/adoption.py` — `compute` (legacy roots only; other states named with their next action; AGENTS.md unchanged/replaced/section appended/conflict; contract created/replaced/conflict; missing `.gitignore` journal patterns; non-empty root runs/sessions/shared/resources and a root `.aoe/binding.json` are conflicts; placeholders; WORKSPACE.md last), `preview` (plan, incomplete adoption with its digest, or configured with the adoption archive), `adopt` (root lock; adoption journal recovery with the first actor; replay by archive seal and receipt; stale/conflict refusal; one journal publication). Templates and released digests arrive as plain data from L3. `receipt_for` takes the record file name.
- L3: `toulmin workspace adopt ROOT [--name] [--plan-digest --confirmed-by --confirm --approval-text]`; `cli/initialize.adoption_templates()` reads the packaged inputs. Legacy status and init now point to `toulmin workspace adopt ROOT`; the outdated "later release" messages for child creation were updated. The workspace AGENTS template's scope rules are one `## Workspace and project scopes` section (with workspace sessions, child creation and handoff), which is what a customized legacy AGENTS.md receives.
- **Verified**: 29 new tests (tests/cli/test_adoption.py) on a legacy fixture with two projects, a cross-project Brief reference, appended local conventions in AGENTS.md, an edited tools/models.toml, an older .gitignore, an applied project handoff and a v1 AoE binding with its context: deterministic location-independent read-only preview with exact changes and appended section; CLI preview/digest/missing confirmation/digest/actor; pristine released AGENTS and contract replaced, absent contract created; released digests cover the shipped copies; six conflict kinds refused with files intact; empty locations accepted; malformed, short, wrong and stale digests write nothing; four other root states refused; workspace roots report configured; confirmed adoption changes exactly the planned files plus the archive (projects, binding, contexts, config, roles, CLAUDE.md link preserved; valid workspace and project status); the existing child context becomes stale without rewriting or any AoE call; replay by digest prefix with another actor; workspace propose works afterwards; CLI output; fault injection at five publication points with forward recovery by the first actor; external edit during recovery preserved. One WI2 and one WI5 test were updated for the new legacy hint and section name.
- Checks: full locked suite with the TUI extra **1191 passed in 419.09 s** (after all code, template and doc edits); Ruff lint/format (156 files), strict mypy (70 files), a local wheel build containing `workspace_templates/released.json`, and `git diff --check` passed.
- Limits: L01 and the adoption parts of F01/F03–F05/F12 are automated tests only, all NOT RUN as acceptance; no real legacy workbench was adopted. The workspace template no longer reproduces every legacy AGENTS sentence; a pristine legacy AGENTS.md is replaced by the reviewed diff shown in the plan.
- Session ID unavailable. Blockers: none. Next: WI8 integrated verification and researcher trial after authorization. No push.

## 2026-11-04 — WI6: confirmed child creation

- Authorization: the researcher authorized WI6 after WI5 ("同意，开始实现 WI6"). Recorded in AGENTS/TODO and the external plan. Only fake AoE clients were used; no real AoE/native session, model, network or real research data was touched. Adoption (WI7) was not started.
- Contract clarification recorded (section 9): the WI1 packet example abbreviated scope by lower-casing items and did not show the initial Brief, so a preview could not review the Brief's bytes. The packet body now embeds the generated PROJECT.md and the verbatim Brief, renders included/excluded items verbatim as lists, and gives related projects and open questions their own lines. The packet and creation-record examples were regenerated from the real code (seal 33295346…); a creation receipt example was added; pins show the full form including `url`. Input, PROJECT.md and Brief digests are unchanged. Section 10 states the staging recovery rule; the status header lists section 9 as implemented.
- L1: `core/creation.py` — creation input (one-line question/motivation/next step/list items, nonempty `included`, no `## ` in goal/constraints, relationships unique and not self), generated PROJECT.md (explore, no decisions, no handoff, 40-line check), sealed packet and creation-record schemas and rendering, staging path from the packet hex. `core/workspace_journal.py` — `project-create` intents carry `staging`; the child is built in `projects/.creating-<hex>`, renamed into place once, and the receipt is the last image; recovery accepts only expected files at their after images (discarding the writer's `.handoff-*.tmp` temporaries in staging) and otherwise keeps everything; `incomplete_child` lets readers mark the child.
- L2: `protocols/project_creation.py` — propose (input in root `runs/drafts/`, input/command name agreement, supersedes pending creation packet, occupied name naming its creator, related projects, qualified Brief markers, WI3 source snapshots and pins), load (seal and frozen digests; change packets, handoff drafts and inputs named), check (own target, staging remnant, sources, pins, relationships, markers only; shared rules/templates never compared), create (contract 7.4 order incl. forward recovery with the first actor), reject. `workspace_change` exposes shared source/pin/receipt helpers. `workspace_state`, `research_state` and the workspace card show "creation incomplete" and refuse opening such a child; the card adds the propose action.
- L3: `toulmin project propose|create|reject` (preview shows root, scope, seal, the packet body and exact create/reject commands; `--confirmed-by` without `--confirm` exits 1). Create prints the child, that no session started, and the separate `aoe open NAME --root ROOT`. `aoe open --new-session` may now retry a launch that left no matching AoE session; any candidate still requires inspection (no silent duplicate). The workspace AGENTS template tells agents to propose children via packets and open them in their own sessions.
- **Verified**: 44 new tests (tests/cli/test_project_creation.py) reproduce section 9 byte for byte from the docs (packet, seal, input snapshot, both targets, receipt, creation record) and cover the exact child tree and valid project/workspace status, CLI propose/preview/missing confirmation/actor, CLI create output and replay with another actor, eleven invalid inputs, name mismatch, four wrong artifacts plus workspace apply refusing a creation packet, four post-preview edits, repeat create, a second packet for an occupied name, an existing legacy-style child, supersession, changed source and broken pin vs unrelated edits (charter focus, AGENTS, framework customizations preserved), reject/replay/refusals, fault injection before any child file, mid-staging and after the rename (incomplete status, refused open and other applies, recovery with the first actor), staging temporaries, external edits in staging and in the published child, missing journal, failed launch with a retained child and explicit retry, ambiguous candidates refusing `--new-session`, the workspace card and legacy refusal. One WI3 test needle was narrowed for the new receipt example.
- Checks: full locked suite with the TUI extra **1162 passed in 399.22 s** (after all code edits; README/protocols/CHANGELOG/packaged-copy edits followed, so every test reading docs or templates was rerun afterwards: **192 passed**); Ruff lint/format (153 files), strict mypy (68 files), `toulmin project --help` and `git diff --check` passed.
- Limits: no real AoE/provider session was run; native create-and-enter remains two explicit commands (no combined flag). A07/A08 and the WI6 parts of A09/A10/F01–F06/F08/F13 are automated tests only; all WS3 cases remain NOT RUN. No Chief bridge, sidebar or transcript collector was added.
- Session ID unavailable. Blockers: none. Next: WI7 previewed legacy adoption after authorization. No push.

## 2026-11-04 — WI5: two-scope native AoE entry

- Authorization: the researcher authorized WI5 after WI4 ("同意，开始实现 WI5"). Recorded in AGENTS/TODO and the external plan. Only fake AoE clients were used; no real AoE/native session, model, network or real research data was touched. Child creation (WI6) was not worked around: tests use synthetic prepared child copies of the project template.
- Contract clarification recorded (section 11): "version 2 for every new binding" applies to workspace roots. A legacy root has no workspace scope and keeps writing exactly the AOE3 version 1 form, titles and contexts, so existing workbenches see no change. New sessions start at the root in AoE group `research` or `research/NAME`; a bound existing session keeps its own title.
- L2: `protocols/workspace_context.py` derives the workspace card, resident inputs (AGENTS.md, WORKSPACE.md, latest applied workspace handoff) and fingerprint (that handoff's source draft, resource descriptions, packet seals and dispositions, handoff draft dispositions, journal, child names/stages, diagnostics). `research_state` adds WORKSPACE.md and `runs/creation/creation.md` for a child of a workspace root only.
- L3: `application/aoe.py` handles both scopes: version 1/2 binding read/write (v1 byte layout preserved, v2 with scope and title), scope paths (workspace session must be at the root), cross-scope one-session uniqueness, scope-specific context archives, manifests/receipts carrying version and scope, workspace instructions (activity records with the researcher's own corrections and honest coverage, change packets the agent never applies, workspace handoff path, no transcript or isolation claims) and child scope notes. The adapter's `create` accepts a title and a workspace (no project). `cli/aoe.py` adds optional PROJECT/`--workspace` to open/bind/status/refresh/ack, rejects both, and prints root and scope first. New workspace roots get a separate scope-aware research AGENTS.md template; the shared template is unchanged.
- **Verified**: 15 new tests (tests/unit/test_aoe_scopes.py) cover workspace open (title, v2 binding at `.aoe/`, root runs/ context, v2 manifest, resident inputs, instructions, card, one send), unchanged reopen without resend, unrelated vs relevant edits (pending packet, applied change) and refresh, scoped acknowledgement, busy session not sent, uncertain creation recovered by title without a duplicate, native identity change, workspace session path, child context (charter in, workspace discussion out), coexisting scopes refusing a shared session, v1 kept in place then replaced by v2, wrong-scope binding and v1 manifest under v2, legacy roots without workspace scope, CLI selection with one child, conflicting selectors, scoped refresh hints and the templates. All 155 existing AoE tests pass unchanged. A locally built wheel contains the new template.
- Checks: full locked suite with the TUI extra **1118 passed in 373.39 s** (after all code and doc edits); Ruff lint/format (149 files), strict mypy (65 files), `aoe status --help`, a local wheel build and `git diff --check` passed.
- Limits: no real AoE/provider session was run; Codex/Claude native behavior, startup prompts and fresh-session recovery remain WI8 evidence. Native portions of A02/A03/A06/A09/A10 and F06–F12/F14 are automated tests only; all WS3 cases remain NOT RUN. No persistent sidebar, Chief bridge or transcript collector was added.
- Session ID unavailable. Blockers: none. Next: WI6 confirmed child creation after authorization. No push.

## 2026-11-04 — WI4: workspace handoffs and file-based entry

- Authorization: the researcher authorized WI4 after WI3 ("同意，开始实现 WI4"). Recorded in AGENTS/TODO and the external plan. No native AoE scope, child creation, adoption, live model session or real research data was touched.
- Contract contradiction recorded before resolving: section 8's input example had no `confirmed_changes`, while its draft and record examples cited the WI3 receipt; nothing may infer that list from a session. Resolved by adding `confirmed_changes` to the input example and regenerating the cascaded digests (input, draft, record, WORKSPACE after the handoff, and the section 9 creation input/packet that cite the session record) with the WI1 generator; the generator's output is byte-identical to the new code's draft, record and WORKSPACE.md. Section 8 also now states the input location rule, the journal image order and the in-place two-line charter patch.
- L1: `core/workspace_handoffs.py` — input (four required sections, no `Next step`, kind-specific errors for change inputs, packets, drafts, project summaries), sealed draft and applied record schemas, millisecond timestamps, deterministic draft/record rendering, and `continuity_after`, which replaces only the `next_step`/`last_handoff` lines and refuses multi-line values.
- L2: `protocols/workspace_handoff.py` — draft (root lock, applied-receipt check, inherited/required next step, one sealed `runs/<stamp>-handoff-<hex>/`), load (seal, kind, scope; project drafts, packets, inputs and records named), apply (other journal → this journal's forward recovery with the first actor → chain replay → base digest and receipts → session record then WORKSPACE.md via the root journal), `chain` and `latest_handoff` for file-only entry. `workspace_change` exposes `publish_sealed` and `applied_receipt`. `workspace_state` validates the applied chain, derives draft dispositions (pending, stale, applied, incomplete, invalid) and reports orphan session records.
- L3: `aoe handoff` without PROJECT or with `--workspace` handles the workspace (PROJECT plus `--workspace` exits 2); preview without `--confirm`, `--confirmed-by` without `--confirm` exits 1, `--confirm` without actor exits 2. Project handoffs keep their exact behavior and output. Status prints the last handoff's actor/time and handoff drafts.
- **Verified**: tests reproduce section 8 byte for byte from the docs (draft, seal, session record and WORKSPACE.md). 29 new tests (27 in tests/cli/test_workspace_handoff.py, 2 L1) cover CLI scope/preview, malformed and wrong-kind summaries, project-path input, non-applied receipts, inherited/required next step, exact changed files and lines with a hand-quoted name and a child present, preview/missing confirmation/actor, replay with another actor, two-record chain and older-draft replay, stale drafts after a handoff or charter change, four wrong artifacts, edited and rescoped drafts, fault injection before each write and before retire, external edit during recovery, entry ignoring drafts and orphans, zero children, unchanged project handoff in a workspace and legacy refusal.
- Checks: full locked suite with the TUI extra **1103 passed in 371.68 s** (after all code and doc edits); Ruff lint/format (146 files), strict mypy (64 files), `aoe handoff --help` and `git diff --check` passed.
- Limits: the applied chain is validated by status but source draft archives are not re-hashed against `source_sha256`; native session binding, context delivery and fresh-session recovery remain WI5/WI8. A05/A06/A10 file components and F01–F05/F10 handoff behaviors are automated tests only; all WS3 cases remain NOT RUN.
- Session ID unavailable. Blockers: none. Next: WI5 two-scope native AoE entry after authorization. No push.

## 2026-11-04 — WI3: reviewed workspace changes and shared resource descriptions

- Authorization: the researcher authorized WI3 after WI2 ("同意，开始实现 WI3"). Recorded in AGENTS/TODO and the external plan. No workspace handoff, child creation, AoE scope, adoption, live model session or real research data was touched.
- L1: `core/render.py` (deterministic restricted-YAML front matter and adaptive code fences), `core/activity.py` (activity records with honest capture coverage), `core/resources.py` (resource descriptions, location/version rules, rendering), `core/material.py` (`file` and `tree-v1` digests refusing links/special files), `core/proposals.py` (change input, sealed packet and receipt schemas, charter after image, unified diffs, source coverage lines) and `core/workspace_journal.py` (one root journal: prepare → forward publication → retire; external edits stop recovery with everything kept). Architecture allowlist gains stdlib `difflib`.
- L2: `protocols/workspace_change.py` — propose (input under root `runs/drafts/`, supersedes must be pending, activity coverage must match, snapshots ≤1,000,000 bytes as `sources/N<suffix>`, pins in full form, material verified, no-op/occupied/unregistered targets refused, staged one-rename packet publication); load (seal and every frozen digest; wrong artifacts named); apply (contract 7.4 order: other journal → F02 → replay → recovery with the first confirmation's actor → supersession → relevant targets/sources/pins/material only); reject (pending only, receipt only). `workspace_state` now validates descriptions and receipts and notices a charter (owned parts) or description differing from its receipted after image.
- L3: `toulmin workspace propose|apply|reject`. Preview shows root, scope, packet, seal prefix, targets, the packet body and exact apply/reject commands; `--confirmed-by` without `--confirm` exits 1, `--confirm` without actor exits 2; status lists resources with status/revision.
- Docs: contract status header (sections 2.1/4/5–7/10/12 implemented), `sources/N.EXT` naming, packet/receipt examples regenerated from the real code (generic Not changed text; seal 24c921f8…); protocols command rows and WI3 rationale; README usage; framework CHANGELOG; packaged copies synchronized. Fixed during implementation: the charter after image is rendered in canonical order instead of a ruamel round trip, which had rewritten untouched `null` values as empty.
- **Verified**: tests reproduce the contract example byte for byte from the docs (packet.md, seal, input, source snapshot, both after images, applied WORKSPACE.md/resource and receipt). 47 new tests (tests/cli/test_workspace_change.py, tests/unit/test_workspace_records.py) cover coverage labeling/mismatch, oversized and odd-suffix sources, six invalid change forms, input location/kind, supersession, preview/missing confirmation/actor, CLI replay with another actor, four wrong artifacts, four post-preview edits, resealed wrong scope, stale source, unrelated sibling edits (child project, drafts, material, AGENTS), occupied target, changed material, broken and stale pins, revision/withdrawal history, fault injection before each of three publication writes, after the journal commit and before retire, external edit during recovery, reject/replay/refusals, status notices and section 15 invalid variants. Two WI2 tests were updated for full receipt/description validation.
- Checks: full locked suite with the TUI extra **1074 passed in 361.44 s**; Ruff lint/format (143 files), strict mypy (62 files), `toulmin --help`/`workspace --help` and `git diff --check` passed. The snapshot-suffix fix and its test landed during that run; the affected suite was rerun afterwards: **40 passed**, Ruff/mypy clean.
- Limits: status does not recompute material digests (apply and pins do); the A03/A04 file components and F01–F05/F13/F14 behaviors are automated tests only, not executed acceptance cases (all NOT RUN). Agents still have no scope-aware workspace instructions (WI5).
- Session ID unavailable. Blockers: none. Next: WI4 workspace handoff/recovery after authorization. No push.

## 2026-11-04 — WI2: project-free workspace initialization and offline status

- Authorization: the researcher accepted WI1's five recorded choices and authorized WI2 only. Recorded in AGENTS/TODO and the external plan. No proposals, handoffs, child creation, AoE scope, adoption, live sessions or real research data were touched.
- L1: `core/scope.py` (workspace/child scope data and record locations) and `core/workspace.py` (WORKSPACE.md schema: fields, Direction/Constraints/Focus order, absent-direction form, 40-line limit, receipt/handoff path rules, YAML-safe initial rendering). `core/inspection.marker_errors` generalizes brief marker checks; workspace documents require qualified references. The architecture allowlist gains stdlib `json` (quoted name) and `unicodedata` (name validation).
- L2: `protocols/workspace_state.py` classifies roots (missing, empty, workspace, incomplete-init, legacy, unrelated) and derives the read-only workspace view: charter, receipt/handoff target existence, journal, child names/stages, proposal dispositions from seal/receipt/successor/journal (packet schemas left to WI3) and resource names; misplaced root `R-*.md` is an error.
- L3: `init ROOT [--name]` creates templates, empty `projects/`, `runs/drafts/`, `sessions/`, `shared/resources/` and publishes WORKSPACE.md last under the root lock; rerun on a workspace reports identity and writes nothing; legacy, legacy-without-projects (lists modified entries) and unrelated roots are refused; no rename/repair. `init --project` and TUI template setup are refused on workspace roots only. `status` without PROJECT (or `--workspace`) shows the workspace; PROJECT with `--workspace` is a usage error; a cwd inside `projects/<name>` gets an explicit `--root` correction. Template .gitignore gains journal patterns.
- Docs: contract wording fixed (the charter-receipt mismatch notice compares charter-owned parts, since handoffs change next_step/last_handoff legitimately; legacy-without-projects refusal), protocols command table and WI2 note, README, framework CHANGELOG; packaged copies synchronized.
- **Verified**: a fresh `init --name "Serving Research"` produces WORKSPACE.md with the contract example's digest (3a9d405a…). 48 new tests (tests/cli/test_workspace.py, tests/unit/test_workspace_state.py) cover new/repeat/custom-file preservation, rename/repair refusal, interrupted setup completion, modified-template refusal, unrelated/empty-Git/missing roots, legacy preservation, workspace-root guards, scope selection with one child, unchanged qualified references, cwd hint, seven malformed charters, symlinks, proposal dispositions, tamper/journal invalidity and read-only mtimes. One intended behavior change updated `test_missing_required_arguments_are_usage_errors` (init without --project is now valid).
- Checks: full locked suite with the TUI extra **1027 passed in 352.70 s**; Ruff lint/format (133 files), strict mypy (54 files), CLI help and diff whitespace passed. A final name-validation edit landed during that run; affected suites rerun afterwards: **127 passed**, mypy/Ruff clean.
- Limits: a fresh workspace's AGENTS.md is still the shared project-oriented template (scope-aware instructions are WI5); init's Next action is `status` because workspace conversations do not exist yet. A01 and F11/F12/L01 remain NOT RUN as acceptance cases.
- Session ID unavailable. Blockers: none. Next: WI3 reviewed workspace changes/resources after authorization. No push.

## 2026-11-04 — WI1: workspace-first file and scope contracts

- Authorization: the researcher authorized WI1 only, lifting the development pause for this contract task. WI2–WI8, feature code, live trials and real research changes were not requested. Recorded the scope in AGENTS/TODO and the external plan's completion record.
- Delivered `docs/workspace-formats.md` (packaged copy `framework/workspace-formats.md`), a protocol rationale section in docs/protocols.md (and its copy), a framework CHANGELOG entry and README links. The contract fixes: scope serialization and root classification/selection; WORKSPACE.md fields, body sections, absent-direction form and per-operation permitted changes; activity/capture metadata; shared resource descriptions with `tree-v1` material digests and pins; workspace change input → sealed packet → apply/reject receipt with derived dispositions and supersession; workspace handoff input/draft/applied record changing only `next_step`/`last_handoff`; child creation input/packet/staged one-rename publication/creation record; one root publication journal with a crash-boundary table and forward-only recovery; binding/context/receipt version 2 with v1 compatibility, resident inputs and freshness; project-free init and digest-confirmed legacy adoption; an operation authority matrix, error catalog, invalid variants and A01–A10/F01–F14/L01 traceability.
- Choices made within the accepted semantics (pending researcher review, not blockers): packet ids are random and preview/confirmation bind through a write-once seal; apply/create without `--confirm` previews; explicit `reject` commands record rejection; `init --project` is refused on workspace roots; children have no display name; new bindings are version 2 while v1 bindings are updated in place; registration does not copy material; adoption adds WORKSPACE.md to child resident inputs, so existing child contexts become stale; the packaged copy ships before implementation, marked not implemented.
- **Verified**: the examples in sections 4–9 were generated as one fixture by a scratch script; all 16 complete Markdown examples parse with `toulmin.core.codec.decode` and the expected sections; every cited digest matches the shown bytes or fixture material except the explicitly illustrative rejected receipt; the generated child PROJECT.md passes `validate_project`; the binding JSON parses; every `section N` reference resolves; docs and packaged copies are byte-identical. **Not verified**: no reader/writer exists, so no runtime behavior or A/F/L case is claimed.
- Checks: `tests/cli/test_init.py` now also checks the new packaged copy; init/resume tests 36 passed. Full locked suite with the TUI extra: **979 passed in 351.20 s**; Ruff lint and format (128 files), strict mypy (51 files), `toulmin --help` and `git diff --check` passed. These show unchanged program behavior plus synchronized copies, not an implemented contract.
- Session ID unavailable. Blockers: none. Next: researcher reviews the WI1 choices; WI2 (project-free init and offline workspace state) after authorization. No push.

## 2026-11-04 — WI: workspace-first development scope and task breakdown

- Authorization: the researcher adopted WS3 and requested concrete development tasks/scope. Recorded WS3 adoption without changing NOT RUN outcomes; current work is planning only, not feature implementation or a live trial. Updated AGENTS/TODO accordingly.
- Delivered English plan: `/home/tianchi/notes/toulmin/workspace-implementation-plan.md`. WI1–WI8 cover additive contracts, root-only setup/offline state, reviewed workspace/resource publication, workspace handoff, explicit native scope, confirmed child creation, legacy adoption, and integrated/user acceptance. Each task has dependencies, deliverables and executable completion criteria, with primary ownership mapped to all ten A, fourteen F and one L case.
- Delivery boundaries: first usable checkpoint after WI5 is workspace discussion/confirmation/handoff/recovery; WI6 adds the first child and scope switching; WI7/WI8 complete legacy compatibility and evidence. These checkpoints do not remove any accepted WS3 case. Chief automation, new interfaces/sidebar, full-transcript collection and automatic research rulings remain outside scope. Existing project v1/reference/review/TUI/native compatibility remains required.
- **Inferred from code**: the work can extend the existing Python layers and integrity/adapter primitives; there is no demonstrated need for a new stack. Existing project creation/template checks, project handoff fields and AoE bindings need explicit scope/compatibility treatment rather than a placeholder workspace project. The plan freezes exact formats before new writers and separates child publication from external launch. No duration or proven implementation outcome is asserted.
- Validation: inspected accepted notes and current format/initialization/module structure; checked the dependency order, unique WI IDs, complete A/F/L mapping, note/source paths, encoding/fences, remaining NOT RUN labels and Git diff whitespace. The initial search included one nonexistent architecture-test path; the existing test is tests/unit/test_architecture.py. No code tests or model calls: documentation only; no runtime/templates/research records changed.
- Session ID unavailable. Blockers: none for planning. Next: researcher reviews the bounded WI plan; WI1 is the first task after authorization to proceed. Scope/progress committed locally; full plan remains in personal notes outside Git. No push.

## 2026-11-04 — WS3: workspace-first acceptance design

- Authorization: the researcher accepted WS2's operation scheme and requested item 3. Recorded WS2 approval in its external note and TODO; updated AGENTS to the current documentation-only scope. Implementation remains paused, and no acceptance trial was requested or executed.
- Delivered English plan: `/home/tianchi/notes/toulmin/workspace-acceptance-plan.md`. A01–A10 cover empty workspace initialization, native exploration with feedback, reviewed direction/resource registration, workspace handoff, fresh file-based recovery, reviewed first-child creation, independent child entry, scope switching and child handoff. The small synthetic scheduling fixture requires no formal Claim or performance experiment.
- F01–F14 specify confirmation, artifact/scope mismatch, changed inputs, duplicate publication, interrupted writes, native launch/delivery failures, binding identity, stale/tampered context, unconfirmed closure, scope selection, malformed roots, missing resource versions and honest capture coverage. L01 covers previewed legacy adoption, reviewed plan digests and preservation of existing projects/custom configuration/bindings. These are future checks, not executed evidence.
- Human acceptance is separate: the researcher must identify scope, confirmed/pending state, output location and available action through the normal interface. Record path/command/approval friction and author interventions. The plan does not reinstate an obligatory two-day trial, infer live Claude support from fake adapters, claim filesystem isolation from binding scope, or treat transcript summaries as complete provenance.
- Validation: read accepted WS1/WS2 and historical manual-acceptance documentation; checked unique case IDs/counts, referenced note/source paths, UTF-8/LF, Markdown structure, NOT RUN labels and Git diff whitespace. No code tests or live models: only documentation changed; no templates, runtime code, actual research files or AoE sessions were touched. No usability or new operation is reported as verified.
- Session ID unavailable. Blockers: none for plan delivery. Next: researcher reviews WS3; only later authorization can start implementation and eventual execution. Scope/progress committed locally; personal design notes remain outside Git. No push.

## 2026-11-04 — WS2: workspace operations design

- Authorization: the researcher accepted WS1's state/file division and requested item 2, operation design. Recorded WS1 acceptance in its external note and TODO, then updated AGENTS to the current documentation-only scope. Implementation remains paused; WS3 acceptance planning has not started.
- Delivered English draft: `/home/tianchi/notes/toulmin/workspace-operations-design.md`. It proposes workspace-only init; missing PROJECT selecting workspace in the AoE group with an optional explicit --workspace marker; root/scope-tagged context and outputs; reviewed charter/resource and child-creation packets; separate project publication/native launch; and scope-specific handoff. Proposed command examples are prominently marked unimplemented.
- Compatibility/recovery: preserve existing project commands, records and bindings; retain an explicit legacy init --project route; add previewed workspace adoption with a reviewed plan digest rather than silently changing existing roots. Preserve custom instructions/configuration, flag conflicting paths/guidance, and refuse stale or duplicate publication. User-authorized create-and-enter may run both steps, but failed native launch must not undo or duplicate a confirmed child. Existing native permissions and partial-transcript limits remain explicit.
- **Verified by source inspection**: current CLI still requires project arguments; AoE creates native sessions at the workbench root; bind only prepares context. The TUI project-creation service exists but is not the proposed reviewed workspace-to-child operation. Current common-template validation motivates separating fresh workspace initialization from child publication; no implementation was changed.
- Validation: inspected WS1 and current init/AoE/application contracts; checked note links/source paths, UTF-8/LF, Markdown fences, scope/implementation labels and diff whitespace. Reviewed examples for confirmation and scope consistency, including plan-digest binding for adoption. No code tests, model calls, AoE operations or real research writes: this is documentation-only. No new operation or migration is claimed to work.
- Session ID unavailable. Blockers: none. Next: researcher reviews WS2, then WS3 defines the end-to-end usability walkthrough. Local commit records scope/progress; full design notes remain under ~/notes/toulmin, outside Git. No push.

## 2026-11-04 — WS1: workspace state and file ownership design

- Authorization: the researcher approved the workspace-first direction, then requested only item 1 of the design sequence. No implementation, new CLI behavior, migration or live research mutations were requested. Recorded this scope in AGENTS/TODO; prior AOE3 implementation and acceptance history remain intact.
- Delivered English design draft: `/home/tianchi/notes/toulmin/workspace-state-design.md`, outside the repository per the standing notes rule. It separates confirmed organizing decisions from scientific support, exploration/proposal records, shared resource descriptions, applied handoff and operational session state. Recommends WORKSPACE.md, root runs/sessions and shared/resources ownership; no global scientific stage or global seven-object namespace.
- The draft covers exact-content approval/provenance, rejection/supersession/incomplete records, pending versus applied source archives, version-pinned shared materials, project creation source ownership and bounded recovery context. Applying a workspace handoff updates continuity only, not goals/resources/projects/rulings. Exact schemas, command mechanics and acceptance walkthrough remain WS2/WS3 work. These detailed recommendations are not represented as researcher-approved or implemented.
- **Verified by source inspection**: design section 5 already defines a shared Git workbench; formats and Repository.resolve already support other-project/C-001. Corrected the earlier conversational implication that cross-project reference syntax was missing. Project-free charter/handoff support remains absent. Existing global/profile.md and project formal objects retain their roles.
- Validation: read current design/format/protocol contracts and relevant implementation; checked note/source paths, UTF-8/LF, Markdown fences, required scope labels and Git diff whitespace. No application tests or model calls: changes are documentation-only, with no runtime/template/format-contract edits. No actual workspace-state behavior or usability acceptance is claimed.
- Session ID unavailable. Blockers: none. Next: researcher reviews WS1 recommendations, then proceed to WS2 operation design. Progress/scope records committed locally; personal design note remains outside Git. No push.

## 2026-11-04 — AOE3 usability fix: zsh activation and handoff input diagnosis

- Researcher reported that `source .venv/bin/activate` did not leave `toulmin` available, and that applying a saved proposal failed with an LF/front-matter parser message. Investigated the actual shell configuration and selected research files read-only; no native agent messages or formal research writes were made.
- **Verified**: the activation script and console-script interpreter point to this checkout. In the configured zsh, activation resolves `toulmin`; the next `_pyenv_virtualenv_hook` deactivates the external environment and removes it from PATH. Reproduced the same failure with only the installed pyenv hook in clean zsh. Removing that one prompt hook for the current shell and activating again preserves command lookup and runs `toulmin --version` successfully. Documented this reversible workaround and direct executable use; did not modify shell startup files, pyenv installation or the generated virtual environment.
- **Verified**: the selected file was an unconfirmed research-goal/Claim proposal, not the handoff. The agent had already produced a separate structured summary and generated handoff archive. Validated the actual generated handoff schema, Decision references and unchanged PROJECT base hash without applying it. The researcher receives its exact path for inspection and explicit application.
- Fix: handoff validation now preserves the original diagnostic and explains that application needs the complete archived handoff draft returned by drafting. Both CLI entry points distinguish structured summary input from generated draft application. Future AoE context instructions explicitly require summary → draft generation → exact returned path → researcher review; they no longer ambiguously describe applying the source summary. Existing context archives remain unchanged.
- Four regressions cover both CLI entry points with a plain research proposal and a structured source summary, asserting rejection and byte-identical project files. No schema or acceptance changes, automatic conversion, hidden metadata repair or implicit confirmation. The L2 change is diagnostic only, motivated by the misleading parser-first error in this trial.
- Validation: **80 focused tests passed in 11.32 s**; locked offline sync with the TUI extra, Ruff lint/format (126 files), strict mypy (51 files), CLI help and diff whitespace passed. Final full regression: **978 passed in 351.42 s**, exit 0. The initial configured-shell probe encountered sandbox-denied startup cache writes; the clean-zsh reproduction avoids those startup side effects and still reproduces the cause.
- Session ID unavailable. Blockers: none for the fix; researcher usability acceptance remains pending. Next: researcher applies the reviewed generated handoff and retries activation with the current-shell workaround. Commit locally; no push.

## 2026-11-04 — AOE3: minimum native research entry

- Authorization/scope: after AOE2, the researcher requested the smallest justified development slice and its implementation. Added `toulmin aoe open/bind/status/refresh/ack/handoff`: AoE owns native interaction, Toulmin derives research state and reuses confirmed handoff. Chief contract export/result import and persistent sidebar integration remain deferred. Existing Textual/native features and research records remain compatible.
- Implementation: a tool-independent L2 state card distinguishes recorded statuses, bounded draft inventory, historical next steps and available actions. L3 uses public AoE commands, persists binding/creation intent, reconciles interrupted creation, and refuses silent project/profile/tool changes. Context snapshots include hashes, input planning and separate read receipts; file/native-conversation changes invalidate freshness. Busy/menu/occupied composers are not submitted; uncertain delivery is never retried implicitly. Bind and offline status require no model message; attach is explicit.
- Development verification fixed wrong atomic-write arguments, overwritten fast acknowledgments, provider-conversation replacement, malformed foreign bindings, profile/token races and moved-workbench rebinding. Source layering remains intact. No dependencies or L1 object schemas changed; auxiliary binding schema version 1 and context archives require no existing-record migration.
- **Verified live**: isolated profile `toulmin-aoe3-smoke`, native session `860e258848eb45b3`, provider session `01a1a422-9016-7f01-9179-5e3a41edee1d`. New-session open preserved prepared context at the folder-trust prompt; the delegated operator accepted trust only for the generated fixture. With the dedicated AoE TUI updating readiness, refresh submitted context and real Codex read all snapshots and ran the receipt command. This host's native screen reported GPT-6-Astra/high; provider/model selection remains AoE/native configuration.
- The first live prompt exposed premature handoff drafting. Changed startup instructions to display state and wait; prepare a handoff only when the researcher requests session closure. A second context request in the same session acknowledged fresh state and visibly waited, creating no new handoff. Two subsequent opens and one refresh kept the binding and native user-message count unchanged at two. PROJECT/Brief matched initial snapshots, no formal objects or applied handoff appeared, and stage stayed explore. A deliberate fixture Brief edit then made context stale and refused the old receipt without another model call.
- Limits: receipts report reading, not comprehension or research approval; missing native IDs remain unknown. The native adapter does not recreate UI-N1 read-only mounts or full-transcript archival. Claude has adapter coverage but no new live AOE3 provider trial. Available actions are an on-demand card, not a persistent sidebar. User usability acceptance remains pending. A first-turn draft commit attempt failed under the native fixture's read-only Git metadata; no successful native commit is claimed or needed for context delivery.
- Automated verification: final full regression **974 passed in 353.54 s**, exit 0; final focused application/CLI checks after the startup wording change: **43 passed in 5.41 s**. Locked offline sync with the TUI extra, Ruff lint/format (126 files), strict mypy (51 source files), root/AoE CLI help and diff whitespace checks passed. The earlier integration run passed **972 tests in 354.12 s** before the final two binding regression cases were added.
- Durable smoke notes and fixture evidence: `/home/tianchi/notes/toulmin/aoe3-development-smoke-2026-11-04.md` and its same-name directory. The verification driver was corrected to count actual native `response_item` user messages, rather than assuming an older event format. Cleanup: owned smoke session archived, its tmux terminal absent, dedicated AoE TUI exited; no Chief watch started and main-profile sessions were not driven. No root model session ID was supplied.
- Blockers: none for implementation. Next: researcher tries the new entry on a real project and assesses action/progress clarity before broader automation. Session changes are committed locally; no push.

## 2026-11-04 — AOE2: delegated live research/execution/recovery trial

- Authorization: the researcher delegated execution and verification of the complete proposed workflow. Used an isolated synthetic project, a dedicated AoE profile `toulmin-trial-20261104` and a separate Chief state directory. All fixture approvals identify the delegated trial operator; actual researcher content/usability acceptance remains pending. No production runtime code or existing research projects changed.
- Durable report: `/home/tianchi/notes/toulmin/aoe-trial-2026-11-04.md`; complete artifacts, raw native records, manifests and scripts: `/home/tianchi/notes/toulmin/aoe-trial-2026-11-04/`. These personal trial materials remain outside this repository. Baselines: Toulmin `a62094a`, Chief `c25a6fe`, AoE 1.21.0, native Codex 0.166.0.
- **Verified**: native discussion and feedback → reviewed fixture Brief/C-001/S-001 → fresh restricted research review → confirmed O-001 intake → confirmed Handoff → fresh recovery → Chief test-first task → execution and delivery review → independent reproduction → native result discussion → E-001/D-001 → final handoff and a third distinct native recovery session. Seven Runs preserve the separate roles; the final native reader correctly distinguished completed delivery, refuted hypothesis, unconfirmed p95 draft and pending human acceptance.
- Chief task `queue-tail-trial`: Worker first committed eight failing black-box tests (`1ea0c50`), stopped for approval, then implemented only after the delegated operator inspected and reran them. Final execution commit `1d61476315977f0136212b37b92309be5cb9aab8`; both `python3 -m unittest discover -s tests -v` and `python3 verify_delivery.py` passed. Chief's separate `claude/sonnet` delivery review passed and explicitly did not claim to have rerun the experiment. The native research/Worker model was recorded as `gpt-6-astra`; Toulmin's independent research review reported `claude-opus-5-5` and produced three suggestions from exactly five permitted input files.
- **Verified**: the deterministic queue fixture produced FIFO/SJF p99 297/198 for long-first (33 1/3% improvement) and 198/198 for short-first (0%). Both outcomes remained in the completed delivery. A fresh GPT-6.1 Sol/high verifier, given no discussion or Worker test history, independently reconstructed all 400 submitted and 400 rerun records, verified five input hashes and byte-identical CSVs. This is computational verification on the same host, not human acceptance or a real serving-performance finding.
- **Verified**: missing confirmation refused Claim/intake/Evidence/Handoff/ruling writes; missing verification artifacts refused Evidence even with confirmation. Repeated intake and Handoff application were idempotent. Archiving the completed execution and later creating E-001 did not change C-001; a separate explicit fixture Decision/ruling set C-001 refuted, O-001 accepted and S-001 passed. Project stage stayed explore. The fixture workbench commit is `83efaa7`.
- **Verified**: copied committed source, raw data, Spec snapshot, contract, approvals, reviews, native transcript, hashes and a Git bundle into the research archive before cleanup. AoE's worktree ownership lock refused direct Git removal; Chief's official clean moved only the trial Worker/worktree to trash and retained its branch. After the original worktree disappeared, the archived oracle rerun, all artifact hashes and Toulmin references still passed. The persistent relocated workbench also reports valid data; its artifact manifest lists 245 files.
- Observed usability issues: model-written ACTIONS twice described history instead of available actions; old Handoff next steps stayed stale until explicit refresh; first Chief startup waited 120 seconds because AoE reported starting despite a visible native input box. Opening the dedicated AoE TUI changed status to idle and the same task recovered through kickoff. Chief Inbox rendered after setting the test PTY's TERM to xterm-256color; at 80×24 the long goal dominated the detail view and the action footer truncated. These observations motivate deterministic state/action presentation, explicit freshness and checked startup/delivery; they do not establish a specific upstream code defect.
- Cleanup: three research sessions archived, Worker session trashed, all four corresponding tmux sessions absent; the AoE test TUI and Chief Inbox exited. No Chief watch daemon was started. Existing main-profile sessions/tasks were not driven. A transient post-archive list result was rechecked before recording cleanup success. Trial provider session IDs are preserved in the logs; no root model session ID was supplied.
- Repository verification: document diff/format and local report links checked. No application code changed, so the full Toulmin regression suite was not rerun; the actual live experiment, confirmation refusals, independent reproduction and recovery checks above are the relevant evidence. No merge or push. Next: researcher reviews the findings, then define the smallest AoE binding/current-state/handoff slice; a production bridge and persistent research panel remain unimplemented.

## 2026-11-04 — AOE1: research workspace integration proposal

- Scope: analyze the researcher's proposed Toulmin/AoE/Chief split; no integration implementation or task delegation was requested. Detailed analysis is in the researcher's external notes at `/home/tianchi/notes/toulmin/aoe-integration.md`, following the standing notes-location rule. Repository records remain in English.
- **Verified**: inspected Toulmin at `df85aac`, Chief at `c25a6fe`, and installed `/home/tianchi/.local/bin/aoe` version `1.21.0` through source/documentation reads and CLI help. AoE supports native sessions, grouping and lifecycle operations; Chief has bounded task contracts, Thinking sessions, worktree execution and delivery checks. Arbitrary research sidebar integration was not verified.
- **Inferred from code**: recommend AoE as the primary interaction entry, Toulmin as research state/protocol owner, and Chief as bounded execution owner. A resident research conversation should not automatically become a supervised Chief task. Recommend pausing additional standalone TUI/native-runtime expansion while retaining existing functionality and records; this direction is proposed, not yet approved.
- Preserve visible research guidance through a file-derived state card and explicit actions, with a persistent AoE view evaluated if the card is insufficient. A plain native session does not automatically supply the requested research dashboard. Ordinary AoE sessions also do not inherit UI-N1's filesystem protection or full research provenance; these require explicit acceptance checks.
- Proposed sequence: A, manually validate one bound research session and confirmed handoff; B, manually validate Spec → Chief task → archived Run/Evidence draft; C, automate the proven steps through thin L3 adapters. Spec prose needs reviewed contract mapping. A valid negative experiment can complete the Chief task without supporting the Claim. Results must survive worktree cleanup, and imports must not automatically set evidence grades or research rulings.
- Verification: checked local source references, note/document formatting and scoped diffs. No code tests were run because only planning/progress documents changed; no end-to-end integration or independent acceptance is claimed. No AoE/Chief state, research objects, provider configuration or runtime code was changed; no model calls or worker messages were sent.
- Session ID unavailable. Blockers: none for analysis. Next: researcher reviews the proposed direction, then a temporary-project manual trial of the AoE research entry and recovery. AOE1 documentation only is committed locally; no push.

## 2026-11-03 — UI-N1 fix: native command PTY permission failure

- Researcher reported context.md Permission denied and identified Codex. Read-only inspection of the active Toulmin pane found the actual failure: `Failed to create unified exec process: Permission denied (os error 13)` before pwd/rg/cat ran. The context was researcher-owned mode0600 with traversable owned parent directories; no user session input, project files or permission bits were changed.
- Root and a user-authorized GPT-6.1 Sol/high diagnostic agent independently reproduced the missing boundary: direct context reads and inherited TTY descriptors work, but opening /dev/ptmx inside the exact outer user namespace fails with errno13. The old fake-CLI tests checked inherited isatty only, missing new PTY allocation by real native command runners.
- Added bubblewrap `--dev /dev` so the native namespace gets its own devpts. A real nested PTY child now reads the mode0600 context successfully. Regression extends runtime coverage to PTY allocation plus child execution/read; existing actual tmux/bubblewrap cases still verify EROFS for formal writes, hidden private control socket, normal scratch/cache/network access, Run archival, leases and descendant cleanup.
- Focused runtime validation: **11 passed in 3.10 s**. Locked offline sync, Ruff lint/format (117 files), strict mypy (46 files) and CLI help passed. Final full regression: **818 passed in 345.02 s**, exit 0. No model quota was used; independent real-Codex sandbox probing hit a separate socket-metadata prerequisite and is not claimed as end-to-end provider validation. The actual syscall failure and before/after repair were executed, not inferred from file mode alone.
- No schema, dependency or existing-record migration; current native mounts remain unchanged. User must exit the old native split and start a new one to load the fixed wrapper. Documentation and TODO record this recovery step; real-provider retry remains pending researcher acceptance.
- Session ID unavailable. All bounded diagnostic/test commands completed; their temporary processes were reaped. The researcher's original native session was inspected read-only and remains untouched. Blockers: none for implementation. Next: researcher retries native Codex and confirms command execution. Commit UI-N1 fix; no push.

## 2026-11-03 — UI-N1: native discussion on real projects

- Authorization: researcher confirmed that UI-R4 made discussion smoother, then approved connecting the project-context → native discussion → archived draft → confirmed Brief loop. Implemented F4 Native CLI in the existing TUI and `toulmin native PROJECT --root ROOT --agent codex|claude`; Claims/review scope is unchanged.
- New L2 native protocol freezes AGENTS, PROJECT, Brief and any last handoff; native execution gets a mutable research/ workspace plus a frozen-context copy. Normal exit freezes the exact returned draft before one normal Run is published. Model/session identity and full conversation are not fabricated: the launcher does not capture the transcript or provider identity, and the Run says so. Failed/interrupted sessions retain partial drafts but cannot apply them. Native context is relative to the workbench, preserving archive readability and application after moving it.
- Project board displays goal/stage, saved/live-or-archived draft, Run/provenance, full draft/diff preview and explicit application. Apply requires successful archival, valid references, exact frozen proposal and an unchanged saved Brief; before/after images and application intent allow recovery without overwrites or duplicate Runs. Main TUI reloads the Brief after returning. F4 and CLI support saved-session inspection and explicit interrupted recovery without invoking a model.
- L3 uses a private tmux server and shared Discussion job lease, plus a native-worker lease for recovery exclusion. Bubblewrap protects direct workbench paths, keeps research/ writable and hides the private tmux socket. Codex uses installed `--no-daemon` to keep execution in the protected local process tree. TERM/HUP forward to the child; local descendants are reaped/removed on closure, with launcher fallback finalization. Missing namespace support refuses launch before session creation. Standard-library diagnostic encoding/file-descriptor inspection modules were added to the architecture allowlist; L1/L2 still have no CLI/external-command dependencies.
- Root integrated user-authorized GPT-6.1 Sol/high protocol, board and runtime-test work. A read-only runtime review reproduced a host tmux-socket escape and verified masking it, then identified installed Codex shared-daemon routing and required `--no-daemon`. These checks establish direct-path protection, not comprehensive isolation from outside hardlink aliases or other host services. Root found and corrected the archive-migration absolute-path bug with started/closed move-root regressions.
- Verification: final focused protocol/runtime/UI/architecture integration **73 passed in 23.61 s**. Real tmux/bubblewrap tests use fake Codex only and check TTY/context/network/cache access, formal-file EROFS, hidden control socket, Run archival, lease exclusions and cleanup including detached child processes. Attached PTY exercised the actual CLI entry, draft → Run before Apply, confirmed temporary-project Brief replacement, exit 0 and terminal attribute restoration. The main-TUI return/reload regression passed. No real research project or live model quota was used.
- Locked offline sync, Ruff lint/format (117 files), strict mypy (46 source files), CLI help, packaged format/protocol parity and diff checks passed. Final frozen-source full regression: **817 passed in 345.26 s**, exit 0. The earlier run (started before the portability fix) reported 811 passed/3 runtime timeouts in 378.14 s: its parent process retained the old absolute-context implementation while new pane processes imported the relative-context implementation. Reading one preserved failing fixture reproduced the context-hash mismatch; it is mixed-version verification, not the final-source result. Documentation records new auxiliary version-1 records and compatibility: no seven-object schema change or existing-data migration.
- Limits: Linux/tmux/bubblewrap for new splits; native CLI configuration and permissions remain provider-managed outside direct workbench path protection. Initial launch submits context-reading instructions and can consume model quota. Full conversation capture, model/session identity collection, adopting existing headless sessions and native automatic resume are not implemented. Native provider UI/configuration and real research usability require researcher acceptance; development tests are not independent acceptance.
- Session ID unavailable. All bounded verification commands completed and private tmux test servers/descendants were cleaned up. Blockers: none for implementation. Next: researcher tests an existing project through F4 and confirms the resulting Brief workflow. Commit UI-N1; no push.

## 2026-11-03 — UI-R4: native CLI split prototype

- Authorization: researcher chose a same-terminal split over embedding a terminal emulator and asked for a minimal prototype. Delivered standalone prototypes/native_split.py and native_board.py with a private tmux server, research board and untouched interactive Codex/Claude command; production code, model configuration and research projects are unchanged.
- Default mode runs a clearly simulated agent without model/network use. Native mode starts the selected installed CLI without submitting a prompt. Each trial creates a new disposable directory and context.md; the researcher can ask the CLI to read it and write draft.md. The board refreshes proposals and requires explicit confirmation before create-only accepted-brief.md publication. No screen capture is treated as provenance or formal Run intake.
- Pane focus/zoom uses standard tmux keys; mouse selection is enabled. Quitting the board or detaching the client stops only the trial's private server. Trial files remain for inspection. Independent detached services started by a native agent are outside this lifecycle guarantee. Native mode inherits CLI authentication, configuration and permissions rather than the production headless sandbox.
- User-authorized GPT-6.1 Sol/high subagent implemented the compact board and 14 focused tests; root implemented and integrated the launcher and 3 actual tmux tests. Tests cover exclusive workspace creation, 100/140-column real panes, focus/zoom, draft return, native-exit metadata and private-server shutdown, plus 36/40/80-column board controls, explicit/cancelled/stale acceptance and safe file reads/create-only writes.
- Verification: focused board 14 passed; root real-tmux tests 3 passed in 1.53 s. The default sandbox forbids tmux Unix sockets; the scoped test escalation was approved. Locked offline sync, Ruff lint/format (109 files), strict mypy (43 source files) and CLI help passed. Root full regression: **758 passed in 317.62 s**. After the final compact-question/post-acceptance display refinement, root reran all prototype checks: **19 passed in 9.21 s**. An attached PTY exercised focus switching, draft confirmation and quitting with an active simulated agent; it exited 0 and restored terminal attributes. Early PTY harness attempts used incorrect key timing/focus; the corrected actual-terminal sequence passed. No live model quota was used.
- Limits: no live model discussion, native-session adoption, production context synchronization, complete native transcript/Run archiving or formal research-object application. The brief round trip is prototype files only. Researcher usability acceptance remains pending in TODO UI-R4. Native providers' own UI/permission compatibility needs a real trial.
- Session ID unavailable. All bounded verification processes completed and their private tmux servers were cleaned up. Blockers: none for the prototype. Next: researcher tries native mode and assesses whether visible research direction plus unrestricted native interaction is useful. Commit UI-R4; no push.

## 2026-11-03 — UI2 follow-up: resumable native exploration

- Authorization: researcher approved continuous resumable exploration with file-based rebuilding, superseding Q27's stateless-only choice. Independent review and Brief authoring remain separate fresh ephemeral operations. Confirmed the user-installed socat now resolves to /usr/bin/socat; no system package changes were made in this session.
- Exploration now retains native Claude/Codex session IDs and resumes compatible successful exploration across turns and TUI restarts. A stable research workspace preserves working material; prompts, tool traces, outcomes, host-written final-message files and Runs remain separate per invocation. Native CLI caches are auxiliary state outside the workbench, while open files remain the portable record.
- Current project files and explicit current proposal state replace inherited versions. Resume sends intervening turns instead of replaying the entire prior conversation; Brief authoring between exploration turns is included in that delta. Dismissed/applied drafts are explicitly retired from pending context. Actual requests retain the 100,000-character cap; inherited history does not count toward that payload. Fresh rebuilding and Brief authoring still face full-history limits; no automatic summarization was added.
- Configuration fingerprints select compatible sessions without writing raw configured environment values into continuation metadata. First/legacy/no-ID/configuration-changed/failed/recovered histories and explicit rebuilds start fresh from files. A failed native resume creates one failed Run, never an automatic second model call. A successful answer with no native ID stays usable; the next exploration rebuilds. An explicit resume returning another native ID fails continuity validation.
- Added versioned continuation metadata bound by a task checksum, validated ancestry and stable workspace anchors. Missing or changed metadata cannot silently downgrade a delta prompt into a context-free new invocation. Old records stay valid without migration; older TUI readers reject the new optional marker rather than silently interpreting it. Canonical formats/protocols and packaged copies were updated together.
- Added F3 Session controls showing native ID/mode/reason and a pending Rebuild on next Send option; this option survives navigation and Brief authoring within the running app. Context preview uses the selected model and rebuild preference. Idle polling skips archive reads, while completion/error transitions still refresh. External file edits require reopening the project. Protocol validation avoids quadratic task rereads in normal history loading.
- Root integrated user-authorized GPT-6.1 Sol/high protocol, adapter and UI work and separately reviewed it. A read-only review agent reproduced missing-manifest context loss and stale dismissed-proposal inheritance; both gained fixes and regressions. Root service integration passed 8 tests in 14.45 s; adapter agent passed 54 adapter cases plus existing review regressions; final focused protocol and UI tests passed. Development review is not independent research acceptance.
- Final root full regression: **741 passed in 308.93 s** (exit 0). Locked offline sync, Ruff lint/format (105 files), strict mypy (43 source files), CLI help, documentation links and packaged contract checks passed. A real PTY opened F3, closed it and quit with exit 0, restored terminal attributes/alternate screen and reaped its child. Installed CLI help and official references establish flag syntax; no live model quota or native-provider continuity/OS-sandbox trial was used.
- Limits: provider session storage and context limits still apply. Moving a workbench, deleting native caches or changing configuration can require rebuilding. File replay preserves recorded content, not every native working state. Shared research material is mutable, not immutable Evidence. Claims/review/handoff UI work remains pending; long-session research usability remains a user trial.
- Session ID unavailable. All bounded verification commands completed and were reaped. Blockers: none for implementation. Next: two real discussion turns, restart TUI and continue; inspect F3's native ID and then try an explicit rebuild. No push.

## 2026-11-03 — UI2 follow-up: exploration research tools

- Authorization: the researcher explicitly requested unrestricted research network/search/download capabilities during exploration, ahead of Claims/review UI development. Implemented a separate exploration profile while retaining researcher confirmation for formal writes and the existing independent-review profile.
- Discussion Send now enables research tools. Claude uses Bash/WebSearch/WebFetch with strict native sandbox settings, no unsandboxed-command fallback and HTTP(S) domain permission. Codex uses workspace-write, live web search and network access with no additional writable roots, and suppresses inherited project instructions/hooks. Controlled profile arguments cannot be overridden through extra_args; supported reasoning settings remain configurable. Brief proposal generation stays tool-free composition from supplied context.
- Each exploration request gets an archived research/ directory. The exact prompt specifies its writable location before hashing; later turns receive previous workspace paths as untrusted, unfrozen material. Downloads remain after success/failure/cancellation and never automatically become Evidence. The model is instructed to cite URLs/access dates, distinguish abstract/full-text/excerpt access and disclose failed retrievals.
- Full tool-event stdout and stderr are saved beside research/, outside the model-writable directory. Codex's host-written final-message file also lives outside that directory. Existing frozen inputs, normal Runs, no automatic retries, cancellation/reaping and explicit Brief application remain intact. Optional new files require no migration; canonical formats/protocols and packaged copies match.
- Root integrated GPT-6.1 Sol/high protocol and adapter changes, reviewed invocation profiles and ran validation. Focused protocol/service/review/synthesis integration: 106 passed in 30.62 s. Adapter agent: 27 new fake-CLI tests passed plus 34 existing cancellation/review checks. Root full regression: **674 passed in 255.93 s**. Locked offline sync, Ruff lint/format (103 files), strict mypy (43 source files), CLI help, documentation links, packaged contract parity and diff checks passed.
- Official CLI documentation and installed help were checked for profile flags. Fake tests verify argument construction, separate operation behavior, retained downloads/traces, cancellation, path/symlink refusal, prior-material context and unchanged review behavior. No paid model invocation, live retrieval or native OS-sandbox containment trial was performed; these checks do not establish end-to-end research usability.
- Environment blocker: installed Claude 2.1.317 requires bubblewrap and socat for Linux sandboxing. /usr/bin/bwrap is present; socat is absent from PATH (an administrator-managed path was not inspected). Attempted sudo -n dnf install -y socat; sudo required a password and exited before installation, so no system packages changed. Researcher can run sudo dnf install socat interactively. The application fails closed when required sandbox support is unavailable. Codex does not depend on socat.
- User-facing guide documents tool capabilities, source limits, external-service contact, disk use and dependencies. The TUI still returns final answers, without a live tool-activity display or a structured source browser. Provider/admin/site restrictions and paywalls still apply; no sandbox-bypass option was introduced.
- Session ID unavailable. All bounded test commands finished and were reaped. Next: install the missing Claude dependency if using that adapter, then try a real search/read/download discussion and inspect its retained sources. Commit task UI2 follow-up; no push.

## 2026-11-03 — UI2: conversation-first workbench and confirmed Brief proposals

- Authorization: researcher accepted returning to the original interactive workbench. Delivered UI2 with the Brief proposal subset of UI3 as one usable slice. UI-R2/UI-R3 remain unaccepted experiments; Q30/Q31's broader stage-write scope is not adopted.
- The production workspace now centers continuous model discussion, with saved stage/goal/objections/next step alongside the Brief. Send and Propose Brief are explicit calls through configured adapters. A pending proposal permits continued discussion; edited draft text is included as unconfirmed context. Optional views do not impose Claim creation or stage changes.
- Added durable versioned requests, frozen input snapshots and prompt hashes under runs/conversations/main. Each invocation gets a normal completed/failed Run and archive. Context includes AGENTS, PROJECT, saved Brief, the referenced handoff, conversation and any pending working proposal. Opening never invokes a model, rewrites templates or silently recovers/retries.
- The L3 service owns jobs across views, with per-project process leases and cancellation events. Stop/confirmed Quit terminate and reap the affected process group and archive available output. Failed raw responses and CRLF text are retained; subprocess pipes and Codex file reads no longer normalize line endings. Invalid UTF-8 still uses the adapters' replacement decoding policy.
- Brief proposals have editable durable drafts and Saved/Proposed/Changes views. Explicit application validates references and the before image, archives confirmation and both images, then replaces only the Brief. Interrupted application shows the confirmed image read-only with Resume Apply. Reopening or replay does not duplicate Runs or overwrite a newer Brief. External editors do not share the advisory lock; Apply rechecks immediately before replacement but cannot provide OS-level compare-and-swap against them.
- Root integrated GPT-6.1 Sol/high protocol and UI work, reviewed the implementation, and ran fake-CLI integration checks. A separate code-review agent found interrupted-Apply UI, pending-draft context, finalization-error recovery and adapter newline issues; these were fixed. This is development review, not independent research acceptance.
- Root's actual renders exposed a 60x20 inspector with no usable content despite earlier control-geometry tests. Compact controls were reduced; a new test verifies visible proposal text, at least five editor rows and an actual Apply click. Renders at 120x36, 80x24 and 60x20 were inspected. Raster font fallback artifacts are not a claim of terminal-font validation.
- Verification: the first full run reported 633 passed and one failure (251.31 s), exposing a queued refresh during shutdown after children were removed. Added an app-running guard and a deterministic shutdown regression; the failing scenario plus regression passed (2 in 6.00 s). The final full regression passed **636 tests in 255.19 s**. The final pre-send draft-flush fix also passed its three affected tests (12.61 s). Locked offline sync, Ruff lint/format, strict mypy (43 source files), CLI help, packaged contract parity, local documentation links and diff checks passed. A real PTY startup/confirmed exit returned 0, restored terminal attributes/alternate screen and reaped its child.
- Limits: model calls were tested with disposable fakes only; no live model quota was consumed. Replies are final-only; one conversation/project, one pending proposal and a 100,000-character request cap. Long-history selection, Claim extraction and TUI review/resolution/handoff are not implemented. Existing CLI workflows remain available. Human research usability, long sessions and CJK/IME remain unaccepted.
- Storage is additive v1 auxiliary data, with no seven-object schema migration. Canonical format/protocol documentation and packaged copies were updated together. Session ID unavailable. Blockers: none. All bounded test/render/PTY commands returned and were reaped; no task from this session remains running. Next: a short real-research discussion/proposal/reopen trial before extending UI3/UI4 or visual styling. No push.

## 2026-11-03 — UI-R3 purpose review after researcher feedback

- Researcher feedback: the current flow remains unclear and may be less useful than direct AI-agent conversation. Prototype behavior checks did not establish product usability; UI-R2/UI-R3 are not accepted as the production interaction model.
- Re-read docs/design.md sections 1, 2, 4, 6 and 8. The original main workbench is an interactive researcher/model working session, supplemented by fresh, restricted-input task sessions for independent review and verification. The primary artifact is a defensible brief; the network records its arguments and provenance, connects to engineering verification, and survives session/model changes.
- Diagnosis (inference): the prototypes displaced the central collaboration with fixed samples and mandatory-looking forms/action choices, while exposing protocol administration as ordinary research work. The latest iteration further attempted generic scientific-method guidance. These were prototype design choices, not requirements of the original document.
- Product correction to discuss: preserve fluid researcher/AI collaboration, make the current goal, artifacts, unresolved questions and next step visible, and let protocols support archiving, independent tasks and explicit rulings. Do not treat more pages, buttons or passing interaction tests as evidence of greater research value.
- No new prototype or application changes. Existing prototypes retained as unaccepted experiments. Validation: original-source review and documentation diff only; no code tests required. Session ID unavailable. Blockers: none for this retrospective. Next: re-establish the primary interaction around the original purpose before further implementation. No push.

## 2026-11-03 — UI-R3: uncertainty-driven inquiry prototype

- Authorization: researcher approved trying the proposed scientific-workflow adjustments. This iteration remains a standalone, memory-only prototype; production src/, schemas, adapters and Q30/Q31 production scope are unchanged.
- Changed Overview to show the key unknown, proposed action and reason. Saving a brief stays in Explore. Compare Ideas distinguishes a reported observation from competing explanations; users can edit hypotheses and retain verbatim corrections/context without pretending a fixed sample AI answer was regenerated.
- Added early checks for existing data, related work and a small experiment, available before any Claim, review or Objection. Each has an editable plan and three fictional materials. Users explicitly choose a promising lead, a change of direction or insufficient material with a nonempty reason. No material auto-selects a judgment, becomes verified evidence or advances research stage.
- Preserved optional review/intake path, draft retention, source history and simulated handoff/resumption. Changed material or plans cannot inherit an active interpretation from different inputs. New checks/judgments clear an obsolete saved next step. Compact selectors identify the parent activity of subviews.
- Deliverables: revised prototype/renderer/README, fifteen actual SVG renders, a v2-design refinement and UI-R3 TODO criteria. The user should assess whether the uncertainty/action framing supports thinking rather than adding form filling.
- Verification: a user-authorized GPT-6.1 Sol/high development agent updated the prototype tests; root implemented and reviewed changes and ran integration checks. Focused final run reported **19 passed in 75.30 s**, covering early checks, feedback, all three outcomes, a deliberately contrary judgment on favorable material, blank reasons, stale inputs/next steps, keyboard/mouse geometry at 120x36/80x24/60x20, optional review and no working-directory writes.
- Root verification: locked offline sync, Ruff lint/format, strict mypy (43 files), CLI help, actual rendered pages, fifteen parsed SVGs and documentation links/fences/diff checks passed. PTY startup/Ctrl+Q exited 0 with terminal attributes and alternate screen restored; process reaped. Full regression reported **581 passed in 190.33 s**; final display-wording adjustments were checked by Ruff/mypy and regenerated renders. All bounded test, export, conversion and terminal sessions completed; no background task remains from this turn.
- Limits: all AI-style suggestions, traces, paper notes, results, IDs and judgments are simulated. Real model collaboration, source verification, experiment execution, formal evidence/rulings and disk persistence are not tested. Researcher usability acceptance remains pending; development checks are not independent research acceptance.
- Session ID unavailable. Blockers: none for prototype delivery. Next: researcher tries the divergent-material path and evaluates guidance and feedback, before production integration or visual styling. No push.

## 2026-11-02 — UI-R2: runnable guided-workflow wireframe

- Authorization: researcher said to try the proposed direction. Implemented an isolated low-fidelity prototype, not production UI2–UI5 or the proposed Q31 write paths. Q30/Q31 production acceptance remains pending researcher feedback.
- Deliverable: prototypes/guided_workbench.py, launch/route/limitations in prototypes/README.md, a screenshot exporter and nine actual Textual SVG renders under docs/prototypes/guided-workbench/. Uses the existing optional tui extra, with no dependency changes or edits under src/.
- Experience: sample creation, visible next action, editable brief, statement and review input preview, untriaged suggestion versus recorded issue, editable test plan, readiness explanation, handoff next-step editing and a simulated return. Navigation preserves working edits; changed saved briefs mark earlier review inputs stale; a saved plan leaves the issue open and no evidence is fabricated. Header was reduced after actual compact-screen inspection.
- Limits: all values, review outputs, IDs and handoffs live in memory. No model/network/project writes. Preview Reopen is an in-process illustration, not persistence verification; Ctrl+Q discards the demo. Actual chat, experiment/result intake, rulings, stage writes and model-job behavior are not implemented in this wireframe. This is a workflow review artifact, not the final visual theme or research software acceptance.
- Verified: locked offline sync succeeded; full regression passed **570 tests in 143.87 s**. After the final navigation/label adjustment the eight prototype tests passed again. They cover keyboard/clickable action geometry at 120x36, 80x24 and 60x20, retained edits/context focus, pending intake, stale inputs, early handoff routing, sample reset and no working-directory writes.
- Verified: Ruff lint/format passed; strict mypy passed for src/toulmin and prototypes (43 files); CLI help passed. Actual wide/compact renders inspected, nine exported SVGs parsed, documentation links/fences and diff whitespace checked. PTY launch/Ctrl+Q exited 0, restored terminal attributes/alternate screen and reaped the process. Test/export/renderer commands were bounded by timeouts and all returned; no background task was left running by this session.
- No human usability/CJK-IME acceptance claimed. Session ID unavailable. Blockers: none. Next: researcher tries the small walkthrough and identifies unclear actions before visual styling or production integration. No push.

## 2026-11-02 — UI-R1: guided research workbench redesign

- User direction: retain a TUI to externalize the research process and available actions; prioritize purpose, actual user experience, flow and guidance before visual style. This supersedes the proposed AI-terminal replacement trial as the product direction. No application code changed.
- Delivered docs/tui-workflow-design.md: separate stored stage/current activity/action state; five task views; deterministic, source-backed next-action guidance; a cache-question walkthrough; precise draft/confirmation/ruling contracts; manual validation and evidence entry; gate review; handoff/resume; low-fidelity layout; failure/compact-mode behavior and researcher usability criteria.
- Inferred from code: status currently computes Claim conditions, while a dedicated stage-write service, guided validation-plan update, durable discussion and brief proposals are still gaps. Existing C4 synthesis and the successful Codex isolation smoke were found in current repository records; corrected stale statements in the prior TUI design.
- Proposed decisions: Q30 interaction structure; Q31 bounded manual validation/evidence and G1/G2 stage-ruling scope. Neither is treated as approved. No changes to L0, object schema or canonical protocols; exact new auxiliary/L2 contracts precede eventual implementation.
- Validation: read design goals/gates, formats, current protocols, status/project/ruling code and current progress; checked documentation links, Markdown fences and diff whitespace. No code tests or model calls: this is a design-only change. No user usability or rendered-prototype acceptance claimed.
- Session ID unavailable. Blockers: none for design delivery. Next: researcher review, then a low-fidelity task walkthrough before theme selection. No push.

## 2026-11-02 — Minimal CLI reuse smoke trial

- Scope: user requested a quick, simple reuse trial. Ran a synthetic cache/p95-latency case in disposable /tmp workbenches, using actual CLI subprocesses and one fixed-output fake reviewer. No real AI terminal conversation, editor interaction or paid model invocation was tested; this establishes plumbing only, not replacement usability.
- Verified final path: init; prepare brief and Claim draft; confirm C-001; review creates R-001 and raw output without Objections; intake without confirmation refuses; confirmed intake creates O-001 citing R-001; create/apply handoff; a fresh status process reports valid data, O-001 and the saved next step. Research stage remains explore and the Claim remains proposed.
- Fake reviewer asserted that the private discussion marker was absent and C-001 content present in its supplied prompt. This verifies prompt construction, not real model isolation.
- Final run: 9 CLI invocations including one deliberate refusal, plus scripted document/config preparation. Evidence: /tmp/toulmin-reuse-4248oumg/commands.json and its research/ directory (temporary, not durable repository artifacts). Every subprocess had a 15-second timeout; outer runner had a 50-second timeout and exited 0; no background tasks remain from this trial.
- Friction observed during two preliminary attempts: invented Claim type solution was rejected (correct type mechanism); summary.md directly under runs/ was interpreted as a Run and rejected (correct location runs/manual/summary.md). Both mistakes were in the trial driver, not silently repaired by Toulmin. No application changes made.
- Inference: existing commands can provide the structured backend without a custom chat window. A small command/role integration may remove path/schema friction, but real terminal behavior and researcher effort remain untested. Do not claim that this trial proves a TUI is unnecessary.
- Validation: final end-to-end assertions and documentation diff; full regression not rerun because application code was unchanged. Session ID unavailable. Blockers: none for this smoke trial. Next: assess whether a minimal command guide in an existing AI terminal is sufficient before resuming UI2. No push.

## 2026-11-02 — UI1 visual inspiration research

- User requested design inspiration after rejecting the current TUI appearance. No application code changed; UI2 implementation paused for this design discussion.
- Consulted official Posting, Superfile, Crush and Cogmind pages and screenshot search results. Recorded sources, interpretation, current layout issues and a proposed retro research terminal direction in docs/tui-design.md section 14.
- Direct reference-image downloads returned HTTP 403/406; no successful local inspection of those originals is claimed. No tools were installed and no background processes remain from this research.
- Validation: documentation diff whitespace; no code tests needed for this documentation-only change. Visual preference and usability remain unverified.
- Session ID unavailable. Blockers: none for reference research. Next: compare two static visual concepts before implementation. No push.

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
