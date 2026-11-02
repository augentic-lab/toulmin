# Toulmin development progress

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
