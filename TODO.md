# Stage 2: skeleton implementation plan

Basis: `docs/design.md` sections 3–8, 10, 12 and 13. On 2026-10-31, the user supplied the project Git identity and authorized proceeding with T1 using the recommendations below.
This file collects technology choices, acceptance criteria and decisions. Design revisions and format/protocol details live in docs/design.md, docs/formats.md and docs/protocols.md.

## Technology recommendations

These choices have been adopted. Their suitability is engineering judgment; PROGRESS.md records actual toolchain verification.

| Area | Recommendation | Rationale and tradeoffs |
| --- | --- | --- |
| Language | Python >=3.12; start development on 3.12, with uv managing environments and the lockfile | The current work centers on text, files, protocols and tests, with future experiment-script integration. Less implementation overhead than Go/Rust, at the cost of a Python runtime. No frontend requirement justifies prioritizing TypeScript. The version is a conservative baseline, not a claim to be latest. |
| CLI | Typer, confined to L3 | Type annotations define arguments for four subcommands, with CliRunner testing support. argparse reduces dependencies but requires more argument/help maintenance. Do not stack multiple CLI frameworks. |
| Markdown | Treat bodies as opaque text; recognize only initial YAML front-matter boundaries | The skeleton needs neither rendering nor Markdown AST analysis. Preserve prose, code blocks and handwritten notes. Missing closing delimiters are errors; body `---` lines must not be mistaken for headers. Reconsider markdown-it-py if future brief-link analysis needs it. |
| YAML | ruamel.yaml with an explicit safe standard-type subset and duplicate-key rejection | Supports duplicate-key checks and comment-preserving edits. Forbid arbitrary object construction and unknown YAML tags. More constraints than a simple PyYAML setup, but better suited to shared human/machine editing. Preserve the entire body; do not promise byte-identical YAML-header round trips. |
| Data model | Standard-library dataclasses + Enum + explicit validation | Seven object types are manageable without coupling L1 to a framework. Separate syntax validation from cross-object semantics; do not add Pydantic yet. |
| Tests | pytest + tmp_path + Typer CliRunner | Isolate real repositories and cover errors/command output. Add installed-package subprocess smoke checks to avoid testing only in-process invocation. |
| Development checks | Ruff, mypy, uv.lock | Formatting, static analysis, types and reproducible environments have separate responsibilities. Resolve concrete dependency versions in T1. |

Official references reviewed on 2026-10-31 (documented capabilities, with project fit still a recommendation):

- [Python version status](https://devguide.python.org/versions/); [uv locking and synchronization](https://docs.astral.sh/uv/concepts/projects/sync/).
- [Typer type annotations](https://typer.tiangolo.com/tutorial/); [Typer testing interface](https://typer.tiangolo.com/tutorial/testing/).
- [ruamel.yaml duplicate-key rules](https://yaml.dev/doc/ruamel.yaml/api/); [editing preservation and limitations](https://yaml.dev/doc/ruamel.yaml/detail/).
- [pytest temporary directories](https://docs.pytest.org/en/stable/how-to/tmp_path.html).

Environment fact: **Verified**: the original default Python was 3.7.5. T1 installed uv and Python 3.12 under .tools/ and uses the project .venv, without replacing system Python or changing global PATH.

## Pre-implementation decisions

Q1–Q9 adopted the recommendations under the user's authorization to continue. Q10 uses the explicitly supplied name/email in this repository only.
Q1–Q4 correspond to the four questions section 13 required resolving before the skeleton; the rest fill contract gaps found during design review.

| ID | Required decision | Recommendation adopted | Impact |
| --- | --- | --- | --- |
| Q1 | Should Claim types be specialized for systems research? | Fix six types: problem, magnitude, mechanism, novelty, assumption, deployability. Represent workload/hardware as tags to avoid continually expanding the enum. | L1 schema, templates, G1 checks. |
| Q2 | Generate a brief draft from the network, or write it by hand and check consistency? | Handwrite the brief. The skeleton supplies structure and explicit object-reference checks; status generates a separate network summary. Do not infer semantic consistency from prose or rewrite brief. | Markdown handling, templates, status scope. |
| Q3 | Refine Evidence grades? | Keep verified / model-asserted / intuition. Record repetitions, variance, environment and reproduction methods in provenance/body rather than new grades. verified still requires traceable verification methods/results. | Evidence schema, supported conditions. |
| Q4 | Adopt the language/interface above? Include MCP in this stage? | Use the Python stack, exposing only CLI + importable L1/L2 in the skeleton. Defer MCP; do not prebuild an abstract plugin system. | Package layout, installation, tests. |
| Q5 | How much global knowledge-base functionality is needed now? Does section 13's sixth item affect templates early? | Create only global/profile.md and papers, assumptions, calibration placeholder directories. Initially keep literature as project Evidence; defer knowledge-base features to stage 6. | init output scope. |
| Q6 | Reconcile section 7's stage diagram and gate table? Represent G2 pending work? | Follow the table: Explore → Critique → Brief final → Build → Accept → Done, with G1–G5. Spec is an artifact prepared after Brief final and before G3, not a stage. Represent G2 pending validation in a separate validation-plan field, without a pending Claim status. | PROJECT.stage, templates, status, handoff. |
| Q7 | Reconcile section 6's role permissions with archiving all AI output in runs first? Apply section 4 conditions automatically? | All research output goes to runs first; role directories mean confirmed destinations. new creates formal objects after human confirmation. status reports condition/state mismatches without promoting/demoting anything. Researchers change stages/stored statuses and record a Decision. | new, status, permissions, traceability. |
| Q8 | Reconcile section 5's sequential IDs with dated Run examples? When do drafts receive formal IDs? | Number all seven types within project + type (C-001, R-001, etc.). Store Run metadata in runs/R-001.md and raw output in referenced timestamped subdirectories. Drafts use Run-local labels until confirmed intake assigns an ID. Cross-project references use project/ID. | File layout, provenance references, allocation-conflict tests. |
| Q9 | Separate software and research repositories? Who creates projects? Does handoff directly edit files/commit? | This repository maintains software/templates. init creates a separate research repository at the specified location and its first --project; reuse it for later projects. handoff creates drafts by default; confirmed --apply writes handoffs and non-ruling PROJECT fields. Never change stage automatically; Git commits follow the exit protocol through manual/explicit action. | Template ownership, four command contracts, write boundaries. |
| Q10 | Which Git name/email authors planning and future commits? | Tianchi YU / yu-tianchi@outlook.com. Configure only this repository's user.name / user.email; their source was verified as .git/config. | This session's and future session commits. |

Q7 implementation limit: local CLI confirmation parameters record the operator's declaration, not proof that the operator is the researcher. The skeleton relies on human workflow and Git review, without an authentication system.

Deferred questions: section 13's synthesizer rotation and calibration-statistics format belong to stage 3 (Decision provenance/rationale fields are fixed now); Zotero belongs to stage 6; quota policies precede automatic orchestration; external prompt reuse can wait for role expansion. The skeleton provides only minimal, originally written manual reviewer/scribe contracts.

## Five implementation tasks

Order: T1 → T2 → T3 → T4 → T5. All five are complete. The researcher accepted roadmap stage 2 on 2026-11-02 on the basis of the agent-run trial (see T5).
Every code delivery must pass AGENTS.md's full checks. Completing a task does not automatically establish researcher acceptance of the stage.

### T1 — Freeze skeleton contracts and establish a testable package

- [x] Outputs: agreed design revisions, L1 format specification, L2 protocols, finalized AGENTS.md, Python package and test/check configuration.
- [x] Documentation acceptance: Q1–Q9 have decisions and rationale. Specify required fields, body responsibilities, field types, initial statuses, invalid-status handling, source formats, schema_version, dates and references for seven types. Include at least one valid/invalid example per type.
- [x] Data-boundary acceptance: trace model/role/run/session, human actor and raw-output paths through provenance. Give body content such as Claim.statement one explicit location without inconsistent duplicates. Distinguish Run metadata from raw output.
- [x] Toolchain acceptance: `uv sync --locked --dev` succeeds in a clean environment; `uv run --locked toulmin --help` exits 0; development checks pass.
- [x] Layering acceptance: `uv run --locked pytest -q tests/unit/test_architecture.py` imports/calls L1/L2 while CLI/adapter imports are blocked. Static dependency checks detect upward imports and external command execution in L1.

T1 verification: 59 tests and Ruff/mypy passed; all 59 passed again after wheel installation in a fresh environment. YAML syntax of seven examples was checked. Full schema validation belongs to T3 and was not claimed implemented in T1.

### T2 — Repository/project templates and init

- [x] Outputs: separate research AGENTS.md template, CLAUDE.md link, Gemini instruction-file settings, framework/, roles/, global/, tools/ and project layout. Generate configuration only, without invoking model tools.
- [x] Behavior acceptance: `toulmin init <root> --project demo` in a temporary directory creates section 5's layout. PROJECT has goal, stage, constraints, recent decisions and next step, with a template of at most 40 lines. brief has section 1's required structure. Placeholders make empty directories trackable in Git.
- [x] Protocol acceptance: generated instructions include entry order, exit steps, human-confirmation boundaries and minimal manual reviewer/scribe contracts, without this software repository's TODO/PROGRESS workflow.
- [x] Write acceptance: repeated init changes no existing file bytes; conflicting files fail without overwriting. Reject path escapes and cross-root symlinks. If links cannot be created, fail explicitly without claiming a partial result succeeded.
- [x] Project acceptance: adding a new project to the same root adds only that project and preserves others. init may initialize Git but never creates an initial commit automatically.
- [x] Run: `uv run --locked pytest -q tests/cli/test_init.py`.

T2 verification: 34 init-specific and 93 total tests passed, along with Ruff/mypy. After wheel installation, initialization, repetition, adding a project and Git status were verified outside the repository.
Requirements: local Git and a filesystem with symbolic/hard links. Reinitializing edited global templates fails with conflicts and preserves content. Ordinary I/O rollback is not a guarantee of recovery from forced termination.

### T3 — Seven object types: read/write, validation and new

- [x] Outputs: file encoding/decoding, reference/provenance checks, ID allocation and `toulmin new <type> <project>`. Required content comes from prompts or file input, without treating placeholders as valid research objects.
- [x] Type acceptance: parameterized tests cover Claim, Evidence, Objection, Decision, Exploration, Spec and Run. Generated files can be reread, with ID prefixes, required fields, initial statuses and directories matching T1.
- [x] Parsing acceptance: preserve Chinese body text, code blocks and body `---` on round trips. Duplicate YAML keys, unknown tags, wrong field types, missing closing header delimiters and unknown versions fail with file/field locations.
- [x] Reference acceptance: support same-project and cross-project references. Missing projects/targets, wrong object types or incomplete provenance create no formal object. After manual Run-to-Objection intake, provenance leads back to raw output.
- [x] Write acceptance: allocate independently by project/type without overwriting used IDs. Two concurrent creates cannot claim one ID (safe retry or explicit failure). Failed writes leave no partial object. Inputs cannot escape the workbench root.
- [x] Confirmation acceptance: unconfirmed AI drafts remain in runs. Confirmed intake records actor, provenance and related decisions/confirmation; replay never overwrites an existing object.
- [x] Run: `uv run --locked pytest -q tests/unit/test_objects.py tests/cli/test_new.py`.

T3 verification: all 218 tests and Ruff/mypy passed. After wheel installation, a separate workbench created all seven types from scratch and validated provenance/references; stage stayed explore.
Boundary: new intakes only confirmed initial objects and checks direct references. It neither rules on statuses nor scans the whole project. An operator must inspect project locks left by forced termination; never delete them automatically.

### T4 — Read-only status and condition-consistency diagnostics

- [x] Outputs: `toulmin status <project>` shows stage, Claim statuses, open objections ordered by severity, next step and data issues, generated from current files.
- [x] Condition acceptance: model-asserted/intuition alone, refutes-only evidence, invalidated evidence or open fatal/major objections cannot satisfy supported. Report eligibility only with valid verified supports evidence and no such blockers.
- [x] Human-boundary acceptance: eligibility produces suggestions, never stored supported/accepted updates or gate advancement. Retain accepted history and report inconsistency if evidence is invalidated. Report the overlap between open minor and supported conditions according to T1, without choosing a status.
- [x] Integrity acceptance: dangling references, duplicate IDs, unparseable objects and invalid stored statuses produce locatable diagnostics and nonzero exits. Never silently skip them and report success. Suggestions on valid data are not parsing errors.
- [x] Brief acceptance: check explicit object references in the agreed syntax and report missing objects. Do not claim semantic consistency between handwritten claims and evidence.
- [x] Read-only acceptance: directory listings, file hashes and mtimes stay unchanged. Generate no cache/index. Cover multi-project isolation and deterministic ordering.
- [x] Run: `uv run --locked pytest -q tests/cli/test_status.py`.

T4 verification: 40 status-specific and 258 total tests and Ruff/mypy passed. After wheel installation, valid/broken-reference statuses were verified outside the checkout with bytes/mtimes preserved.
Boundary: conditions use valid evidence/objections from the selected project only, without scanning other projects' incoming relationships. Any data error or creation lock makes conditions unknown and exits 1. Pure pending-ruling notices exit 0.

### T5 — handoff, recovery and real-project trial

- [x] Outputs: `toulmin handoff <project>`, manual application steps, entry/exit documentation and a manual trial record. Explicit projects avoid guessing; no network/models are required. (Trial record: docs/manual-acceptance.md and PROGRESS S1.)
- [x] Draft acceptance: by default, create a reviewable draft only in runs, covering work done, decisions/pending decisions, open questions, next step and session ID. Never invent discussion content or unknown IDs; mark unknown information explicitly.
- [x] Application acceptance: confirmed `--apply <draft>` writes sessions and PROJECT's recent decisions/next step, preserving goal/constraints/handwritten content. Never change stage or object status. Reject overwrites if PROJECT changed after drafting. Repetition adds no duplicate handoff; interrupted writes recover without silent data loss.
- [x] Automated acceptance: `uv run --locked pytest -q tests/cli/test_handoff.py tests/integration/test_resume.py`. Installed subprocess checks execute init → new claim → archive manual review output → confirmed objection intake → status → handoff → fresh-process resume, recovering the same pending work/provenance from files alone.
- [x] Manual stage acceptance (criterion revised 2026-11-02, see below): the researcher chooses a real idea, writes Claims, invokes an independent manual review, confirms Objections, applies a handoff and commits that day. **The next day**, a fresh session uses only the entry protocol to recover the goal, unresolved objections and next step, locating the raw review.
- [x] Acceptance evidence (criterion revised 2026-11-02, see below): both dates/session details, object/handoff paths, actual command results, explicit researcher acceptance and a stage retrospective. Never replace a real trial with simulated next-day tests. Without researcher confirmation, retain “software complete, stage acceptance pending.”

T5 automated verification: 34 handoff/recovery/end-to-end and 292 total tests and Ruff/mypy passed. Actual processes forced to exit after session/PROJECT writes recovered on retry without duplicate appends.
After wheel installation, all four commands, handoff replay, entry-file recovery and status were verified outside the checkout. See docs/manual-acceptance.md for steps and the recorded trial.
Requirements: POSIX flock and file/directory fsync for handoff writes. The two files are not one atomic operation; pending status reports incomplete data. External edits or corrupt journals preserve the files for inspection rather than guessing a merge.

Acceptance criterion revision (2026-11-02, researcher decision): the original wording above required a human researcher's real idea, resumed on the actual next day, and forbade substituting simulated next-day tests. After reviewing the agent-run trial (PROGRESS S1), the researcher said no human trial is needed, judged the simulation accurate enough, and explicitly declared roadmap stage 2 accepted. The two items above are checked under this revised criterion; their original text is kept as history.
Not covered by the accepted evidence: a cross-model review (reviewer and author were the same model), a human researcher's real next-day memory loss, and genuine researcher confirmations (they were simulated). Stage 3 multi-model review partly covers the first.

## Stage 2 follow-up: usability (U1–U3)

Basis: PROGRESS S1 findings 1–5. Planned on 2026-11-02 after stage 2 acceptance. The researcher confirmed Q11–Q13 as recommended on 2026-11-02; U1–U3 are complete. These tasks improve the existing four-command skeleton before stage 3. They add no automated review, model invocation or automatic ruling.
Order: U1 → U2 → U3, one task per session. U1 removes the largest friction. U2 adds the most common next-day action. U3 is cosmetic and changes no format.

### Pending decisions

| ID | Required decision | Recommendation | Impact |
| --- | --- | --- | --- |
| Q11 | Where does a default confirmer come from? | **Confirmed.** An optional `TOULMIN_ACTOR` environment variable used when `--confirmed-by` is omitted. `--confirm` stays mandatory. Operator identity is local, not research state, so it does not go in workbench files. | L3 only. |
| Q12 | Where do draft skeletons go, and how are they created? | **Confirmed.** `toulmin draft <kind> <project> [--name N]` writes a commented skeleton to `projects/<p>/runs/drafts/<kind>-<UTC>[-N].md` without overwriting, and prints the root-relative path. `runs/drafts/` becomes the documented draft location, replacing ad hoc `runs/manual/`. | L3, L2 note, templates/README. |
| Q13 | How are stored statuses, Objection Responses and Rulings changed? | **Confirmed.** `toulmin rule <project> <ID> --status S --decision D-NNN [--response FILE] [--ruling FILE] --confirmed-by A --confirm`. Every status change needs an existing active Decision reference, which the command appends to `decisions` (Run status is immutable). A Response alone (no status change) needs no Decision. Body sections other than the targeted ones, other fields and comments are preserved. | New L2 protocol (change note), L1 conditional rules reused unchanged. |
| Q14 | Should `last_handoff` become a root-relative path, and should Objections allow several targets? | Neither, for now. Both are L1 format changes that require migration. U3 makes status print the resolved handoff path instead. Revisit multi-target after stage 3 shows how often reviews span several Claims. | None now. |

### U1 — Draft skeletons and simpler intake

- [x] Outputs: the Q12 `draft` command for all seven kinds; skeletons list required fields and sections with short comments and allowed enum values. `new --input` also accepts an absolute path inside the workbench root. The Q11 default confirmer is supported.
- [x] Behavior acceptance: a skeleton filled in without consulting formats.md passes `new` for every kind. Unfilled placeholders fail validation with a located error rather than being accepted. `draft` never overwrites and never creates a formal object.
- [x] Boundary acceptance: absolute paths outside the root, symlink escapes and `..` stay rejected. Without `--confirm`, intake still fails. A missing actor (no flag, no variable) fails with a clear message.
- [x] Run: `uv run --locked pytest -q tests/cli/test_new.py` plus new draft tests; full AGENTS.md checks.

U1 verification: 28 draft-specific and 320 total tests and Ruff/mypy passed. An installed wheel outside the checkout ran draft → fill → `new` with an absolute `--input` and `TOULMIN_ACTOR`, then status. The skeletons were checked by automated filling, not by a human who had not read formats.md.
Scope note: `new` still prints an absolute path; U3 unifies root-relative output. `handoff --apply` also accepts `TOULMIN_ACTOR` for consistency with Q11; `handoff --input/--apply` still require root-relative paths.

### U2 — Confirmed status and response updates

- [x] Outputs: the Q13 `rule` command, plus a protocols.md section and a framework CHANGELOG entry.
- [x] Behavior acceptance: an Objection moves open → answered (Response required), accepted (Ruling and Decision required) or deferred (Ruling required). A Claim moves to challenged, supported, accepted or refuted with a Decision. All formats.md conditional rules hold after the update. status reflects the change.
- [x] Integrity acceptance: the update preserves comments, field order, unrelated body sections and bytes outside the patched regions. A missing or superseded Decision, a wrong project or an invalid transition creates no write. The write is atomic and never leaves a partial file. The tool never chooses a status on the researcher's behalf.
- [x] Run: new `tests/cli/test_rule.py`; full checks.

U2 verification: 36 rule-specific and 356 total tests and Ruff/mypy passed. An installed wheel outside the checkout answered an Objection and changed a Claim status on a copy of the S1 trial workbench; status showed the resulting notices without changing anything else.
Implementation choices within Q13: the Decision's `related` must name the object; nonempty sections gain text after a blank line rather than being replaced; `--section` covers the Invalidation/Rationale reason sections. Reference fields (adopted_as, superseded_by, Spec evidence) remain hand edits.

### U3 — Readable generated files and status output

- [x] Outputs: generated headers in the formats.md field order (common fields first), without line folding and with second-precision UTC timestamps. `new`, `draft` and `handoff` all print root-relative paths. `status --verbose` shows the first line of each Claim Statement and Objection Content plus the resolved `last_handoff` path.
- [x] Compatibility acceptance: existing v1 files with microsecond timestamps or other key orders still validate. No migration is needed because YAML key order and timestamp precision are not format semantics.
- [x] Run: affected unit/CLI tests; full checks.

U3 verification: 6 readability tests and 361 total tests and Ruff/mypy passed. An installed wheel created a Claim in a copy of the S1 workbench (ordered header, whole-second timestamps, root-relative output); `status -v` showed statement/objection summaries and the last handoff path alongside S1's older-style files.
Deviation: handoff draft `created` and record `applied_at` keep sub-second precision. Drafts are identified by content digest, and whole seconds made two same-second drafts byte-identical, breaking an existing T5 test. Summaries use the first paragraph rather than the first line, because hand-wrapped statements were cut mid-sentence.

## Planning delivery status

- [x] Read the design; draft AGENTS.md, technology recommendations, five tasks and pending decisions.
- [x] Create PROGRESS.md recording actual checks and environment blockers.
- [x] Researcher authorized proceeding with Q1–Q9 recommendations.
- [x] Git author identity supplied (Q10) and configured only for this project.
- [x] Begin T1; implementation progress/acceptance results appear above and in PROGRESS.md.

## D1 — English documentation

- [x] Translate all maintained documentation, historical progress, planning decisions, format examples and packaged document copies into English, preserving facts, task checkboxes and pending manual acceptance.
- [x] Record English as the documentation language in development/workbench instructions, retaining Unicode test fixtures and the user's conversational language.
- [x] Verify document language, links, template equality, packaged assets and existing checks; prepare the changes for the requested commit and push.

D1 verification: all 20 tracked Markdown documents are in English, 16 local links resolve, and the three published contract copies match. All 292 tests, Ruff lint/format checks and mypy passed. Built wheel/sdist, checked all 25 template assets, and verified generated English documentation plus the README example and all four commands from an installed wheel outside the checkout.
Delivery: the user explicitly requested a commit and push to the existing origin/main branch; verify the remote commit after pushing.
