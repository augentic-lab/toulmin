# Toulmin repository collaboration rules

2026-10-31: The researcher supplied the project Git identity and authorized continuing with the recommendations in TODO.md.
Implement the skeleton in T1–T5 order, completing one task per session and leaving a recoverable record. The user's current instructions take priority.
2026-11-02: The researcher accepted roadmap stage 2. Next work is the usability follow-up U1–U3 in TODO.md, in order.
2026-11-02: The researcher confirmed Q19–Q24 and started stage 3 (critique), tasks C1–C5 in TODO.md, in order.

2026-11-02: The researcher approved TUI decisions Q25–Q29. Implement UI1–UI5 next, one task per session; C4/C5 remain pending. Development may be delegated to GPT-6.1 Sol with high reasoning, with root-agent integration and verification.
2026-11-02: The researcher then asked for C4 (synthesize, crossval) ahead of UI2; it is implemented. UI2–UI5 and C5 remain.
2026-11-03: After rejecting the UI-R2/UI-R3 fixed activity prototypes, the researcher approved a conversation-first workbench. Implement UI2 and the confirmed Brief proposal subset of UI3 as one usable slice; Q30–Q31's broader scope remains unapproved.
2026-11-03: The researcher authorized network access, search and downloads during exploration. Exploration may use tools and write research materials in its archived workspace; formal object/Brief application remains researcher-confirmed. Independent review retains its restricted inputs.

2026-11-03: The researcher approved resumable native exploration with file-based rebuilding on configuration changes or recovery failure. This supersedes Q27's stateless-only choice; independent reviews and Brief authoring remain fresh isolated operations.

2026-11-03: After accepting the smoother native split interaction, the researcher authorized UI-N1: connect real project context, native discussion, archived Brief drafts and explicit application. This does not authorize Claims/review expansion or treating partial native records as complete transcripts.

2026-11-04: Following the AOE2 live trial, the researcher authorized defining and implementing the smallest AoE research entry (AOE3): native-session binding/reuse, current file-derived state and available actions, checked context delivery/receipt, and the existing confirmed handoff. Defer further standalone TUI expansion while retaining compatibility. Chief contract export/result import and a persistent AoE research sidebar are separate follow-ups, not part of AOE3.

2026-11-04: The researcher paused implementation and approved designing workspace-first exploration with optional subprojects and separate workspace/project conversations. Current authorization is WS1 only: document workspace state, file ownership and confirmation boundaries. Keep command/migration design (WS2), acceptance walkthrough (WS3) and implementation separate; the detailed WS1 proposal still requires researcher review.

2026-11-04: The researcher accepted WS1's state/file division and requested WS2 operation design. Current authorization is documentation only: project-free initialization, explicit workspace/child session scope, reviewed child creation, handoff and legacy compatibility. WS2 command forms remain proposals pending review; WS3 and implementation have not started.

2026-11-04: The researcher accepted WS2's operation scheme and requested WS3 acceptance design. Current authorization remains documentation only: define the researcher journey, technical failure/compatibility checks, evidence and acceptance boundaries. Do not implement or run the proposed workflow; its acceptance cases remain unexecuted.

2026-11-04: The researcher adopted WS3 and requested a concrete development task/scope breakdown. Current authorization is planning only: WI1–WI8 define contracts, implementation slices and verification ownership. Record accepted WS3 criteria without marking them executed. Feature implementation and live acceptance remain paused pending a subsequent instruction.

## Project goals and scope

- Toulmin is a project-based research workbench for a single systems researcher. Open files preserve the claim–evidence–objection network and its full provenance.
- `docs/design.md` is the design basis. Record contradictions before resolving them; do not treat assumptions as agreed specifications.
- The current priority is the documentation-only WI development task/scope plan in TODO.md. AOE3 is implemented; further development is paused. Existing Textual/native/AoE interfaces and data remain compatible, and outstanding usability acceptance remains pending. C1–C4 are implemented; C5 remains pending.
- Per Q19 and Q25–Q29, models may be invoked for read-only review, cross-validation, synthesis, exploration, brief proposals and Claim extraction; output is archived in `runs/` and formal application remains researcher-confirmed. Do not implement automatic rulings or gate changes, model writes to formal objects, MCP or reference-manager integrations. Manage Toulmin's own development with TODO, PROGRESS and tests, rather than its research objects.
- This development AGENTS.md and the research workbench AGENTS.md generated by `init` serve different purposes. Generate the latter from a separate template without copying development-tool conventions.

## Layers and dependencies

- L0: the eight design principles constrain every implementation.
- L1: `src/toulmin/core/` defines data models, IDs, references, file formats and validation. Keep pure models and file I/O in separate modules; tool-independent documents define the format rules.
- **L1 must not depend on any specific CLI**, including Typer/Click, Claude Code, Codex or Gemini CLI. It must not depend on L2/L3, model SDKs, MCP, network services or external command execution either.
- L2: `src/toulmin/protocols/` implements entry, handoff and status-condition checks, depending only on L1. It does not parse command lines, print terminal output or invoke models.
- L3: `src/toulmin/cli/` owns arguments, user confirmation, exit codes and output; `tui/` owns Textual presentation, `application/` coordinates workflows and `adapters/` wraps model tools. Dependencies must point L3 → L2/L1 and L2 → L1.
- Model names and session IDs may appear as ordinary provenance data, never as core control branches or fixed vendor enums.
- Removing L3 must leave L1/L2 directly importable and testable. All objects and protocols must remain usable with a text editor.

## Data and ruling boundaries

- Files are the sole source of truth. Generate summaries from object files; do not maintain a separate manual index or database.
- Preserve provenance, creation times and related-object references, including failures, objections, rejected alternatives and superseded decisions.
- `model-asserted` or `intuition` alone cannot satisfy supported conditions. Invalidated evidence must not count.
- Condition checks report compliance or suggestions; they do not change object status or project stage on the researcher's behalf.
- AI research output goes to `runs/` first. Only researcher confirmation permits intake into formal object directories. Research-role write permissions are defined in `docs/protocols.md`.
- An implementer's self-tests are not independent acceptance. Do not claim an independent review occurred in the implementation session.
- Creation commands must not overwrite existing objects. Validate inputs before mutation to prevent path escapes, ID collisions and partial writes. Never silently repair corrupt data.
- L1 format changes require a compatibility assessment and migration plan; provide a script when existing data needs migration. Record the reason for L2 changes. Discuss L0 changes explicitly.

## Code and documentation conventions

- Use Python >=3.12, a `src/` layout and type annotations on public interfaces. Prefer standard-library `dataclasses` and `Enum` for models.
- Use `pathlib`, UTF-8 and LF. Include time zones and separate machine metadata from human-readable bodies. Use English identifiers; comments should explain why.
- Write repository documentation, templates, progress records and commit messages in English. Keep historical facts and acceptance status intact when translating. Non-English test fixtures may remain to exercise Unicode handling. Match the user's language in conversation.
- Keep functions focused. Core logic returns structured results or domain exceptions; the CLI translates these into messages and exit codes at the boundary.
- Minimize dependencies. Resolve concrete versions at first implementation and commit the lockfile; do not guess the latest version.
- Use Ruff for linting/formatting and mypy for types. Do not suppress errors or ignore exceptions without a reason merely to pass checks.
- Tests use temporary directories, never real research projects, subscription CLIs, network access or local model configuration.
- Prioritize data integrity, protocol boundaries and user-visible behavior. Do not add mechanical tests for documentation-only or simple reversible changes.

## Installation and validation commands

Develop with Python 3.12 and uv. README.md documents the local isolated-tool environment.
Report checks as passing only after running and recording them. Full file parsing and the four research commands are implemented in T2–T5.

```sh
uv sync --locked --dev
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src/toulmin
uv run --locked toulmin --help
```

For TUI development, add `--extra tui` to sync/run commands so optional UI tests execute.
For fixes, run affected tests first; run the full set above before committing. For documentation-only changes, inspect the diff and references and explain any skipped code tests.
Stage acceptance is an explicit researcher ruling on recorded trial evidence. Automated tests demonstrate program behavior and are not acceptance by themselves.

## Session protocol

Start by reading this file, `PROGRESS.md` and `TODO.md`, then the design sections relevant to the task. Check Git status and distinguish existing changes from session changes.
Handle one clear task per session and state its output locations first. Do not cross a dependency boundary while a required decision remains unconfirmed.

Before ending every session:

1. Update `PROGRESS.md` with the date, task, completed work, actual checks/results, confirmed/pending decisions, blockers and next step. Record the session ID if available; otherwise say it is unavailable.
2. Check off only TODO.md criteria actually met. Leave researcher-acceptance items pending until accepted.
3. Inspect the diff and stage only this task's files. Use a clear `docs:` / `feat:` / `fix:` / `test:` message referencing the task ID. Commit progress records together with the related changes.
4. Do not include pre-existing user changes, amend others' commits or push automatically. Push when the user explicitly requests it. If identity or permissions prevent a commit, preserve the files and report the blocker in PROGRESS and the response. Never fabricate an author or claim an unmade commit.

Follow the user's thin-first communication convention: lead with the conclusion, use at most three supporting points by default, reply in the user's language and label conclusions Verified / Inferred from code / Guess.
Execution turns end with Conclusion / Evidence / Blockers / Next step / Decision needed. When awaiting confirmation, the last line states the question and recommendation explicitly.
