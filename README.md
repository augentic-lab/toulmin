# Toulmin

A personal research workbench that stores research state in files and leaves rulings to the researcher.

## Research sessions in AoE

Use AoE's native Codex/Claude sessions with Toulmin's file-based research state.
This entry needs Python/Toulmin and an installed, configured AoE; it does not require Textual.
Create a workbench with `toulmin init` first. From a shell:

```sh
toulmin aoe open tail-latency --root /path/to/research --profile main --attach
```

`open` creates or reuses one project binding. `--attach` explicitly enters its native terminal;
without it, the command prints the state and stays in your current shell. Native folder-trust,
login and update prompts remain yours to resolve. If AoE still reports `starting`, open that
AoE profile and follow the displayed `refresh` command. You can also ask the native agent to
read the displayed context file directly and run its receipt command. No private tmux server
or second Toulmin chat window is started.

If you already have a native research session in AoE, bind it without sending into a busy conversation:

```sh
toulmin aoe bind tail-latency --root /path/to/research --session SESSION_ID --profile main
```

Omit `--session` when invoking from inside the desired AoE session. Its directory must be the
workbench root or the selected project directory. Ask the agent to read the returned context
file and its snapshots; `bind` only prepares files. A session cannot be bound to two projects
in the same workbench. Use `bind --replace` for an intentional rebind, including after a move.

```sh
toulmin aoe status tail-latency --root /path/to/research
toulmin aoe status tail-latency --root /path/to/research --offline
toulmin aoe refresh tail-latency --root /path/to/research
```

The English card derives recorded object statuses, draft files and available actions from files.
`RECORDED NEXT STEP` is historical guidance, not inferred current work. `--offline` needs no AoE;
`--json` exposes the same structured view. This is an on-demand card, not a persistent sidebar.
Existing TUI/native proposal trees are not included in its bounded draft inventory.

Context states distinguish prepared, submitted and acknowledged. A read receipt is an agent
report, not comprehension or research approval. File changes or a different native conversation
invalidate freshness. Refresh never revives a stopped session, submits occupied input, answers
permission menus or automatically retries uncertain delivery. Inspect before using explicit
`refresh --resend`; use `open --new-session` only after the old session is archived/deleted.
Repeated opening or refreshing unchanged submitted context does not send another prompt.

Handoff uses the existing confirmation protocol, without automatically closing the AoE session:

```sh
toulmin aoe handoff tail-latency --root /path/to/research --input projects/tail-latency/runs/drafts/summary.md
toulmin aoe handoff tail-latency --root /path/to/research --apply projects/tail-latency/runs/ARCHIVE/draft.md --confirmed-by 'Your name' --confirm
```

There are three distinct files: a research proposal, a structured session summary supplied
to `--input`, and the generated handoff `runs/<archive>/draft.md` returned by that command.
Only the last is the `--apply` input. A file under `runs/drafts/` is not automatically a
handoff draft. Ask the agent to return the exact generated path; do not add YAML delimiters
to a proposal to make it pass validation. The summary format is defined in `roles/scribe.md`
and `framework/protocols.md` in the research workbench.

Inspect the returned draft before applying it. `TOULMIN_ACTOR` may supply attribution; it does
not supply confirmation. Closing a terminal never confirms a handoff or changes research stage.
Bindings live in the project's `.aoe/binding.json`; immutable context snapshots and read receipts
live under `runs/*-aoe-context-*/`. These are auxiliary records, not model-output Runs or a full
conversation archive. Existing research commands still archive/review/intake actual outputs.
AoE retains session ownership and native permissions: this entry does not reproduce the old
native wrapper's read-only mounts. Chief dispatch/import and research rulings remain separate.
Use `TOULMIN_AOE_COMMAND` to select one AoE executable when necessary; otherwise the local
`~/.local/bin/aoe` is preferred over PATH. Research bindings never change AoE configuration.

Stage 2 is accepted. Structured review, reviewer personas, model adapters, synthesis and cross-validation (C1–C4) are implemented. The Python/Textual workspace now supports durable discussion and confirmed Brief proposals; TUI review/handoff integration and C5 remain pending.

## Terminal workspace

Install the optional interface and launch from the software checkout:

```sh
uv sync --locked --dev --extra tui
uv run --locked --extra tui toulmin tui
# Open a specific existing project:
uv run --locked --extra tui toulmin tui --root /path/to/research --project tail-latency
```

After activating the environment, `toulmin tui` works directly. Keep `--extra tui` on subsequent uv commands that synchronize the environment; a base-only sync may remove the optional interface.

Create or open a project, choose a configured model, and use **Send** to discuss your question. The conversation is the main workspace; the saved research state stays on the left and the Brief is on the right (F2 toggles it in smaller terminals). **Context** shows the saved inputs for the next message. **Propose Brief** makes a separate model call; edit its result, inspect **Changes**, then explicitly **Apply to Brief** or **Dismiss**. A pending proposal does not prevent further discussion. No Claim or stage change is required to chat.

Model tools must be installed and authenticated; configure aliases, model IDs and commands in the research workbench's `tools/models.toml`. Opening a project consumes no model quota. Send enables web research and downloads into a retained research workspace; Propose Brief drafts from supplied context. Exploration resumes the latest compatible native session; F3 shows details and offers rebuilding from files on the next Send. Brief authoring stays separate and ephemeral. Stop cancels only that project's request. Replies appear when the model finishes, without simulated streaming. Submitted turns, outputs, downloaded materials and Runs survive reopening. Incomplete requests require explicit Recover and are never automatically retried.

Read the [discussion workbench guide](docs/discussion-workbench.md) for context, recovery and limitations. Review, Claim intake, rulings and handoff still use the existing CLI commands; their TUI views explain availability. Set `TOULMIN_ASCII=1` for ASCII borders if needed. Opening a project never rewrites templates; interrupted setup can be resumed explicitly.

All interface labels are English. Keyboard navigation is available; F2 toggles the inspector and Ctrl+Q starts the exit flow. Terminal/IME and long-session usability still require researcher trial; headless tests do not establish those experiences.

For interface validation use `uv run --locked --extra tui pytest -q` and include the extra when running mypy. Base installation and CLI help continue to work without Textual. The selected dependency versions are recorded in uv.lock.

## Initialize a research workbench

A workbench starts as a shared workspace with no project, goal or Claim:

```sh
uv run --locked toulmin init /path/to/research --name "Serving Research"
uv run --locked toulmin status --root /path/to/research   # workspace view; no PROJECT
```

`WORKSPACE.md` starts with no confirmed direction. Rerunning init on a workspace reports it and
writes nothing. Existing workbenches are not upgraded by init (adoption is a later release).
Reviewed child creation, workspace conversations and handoffs are not available yet; see the
[workspace-first contract](docs/workspace-formats.md).

The legacy route still creates a template project in a non-workspace workbench:

```sh
uv run --locked toulmin init /path/to/research --project tail-latency
uv run --locked toulmin init /path/to/research --project second-project
```

Requires local Git and a filesystem supporting symbolic and hard links. The command creates research AGENTS,
a CLAUDE symlink, Gemini settings, framework/, roles/, global/ and project directories, and initializes a separate Git repository without a commit.
Invoke models manually, following the generated AGENTS and reviewer/scribe role contracts.

Reinitializing identical content writes nothing. Any conflicting target file causes an error and is preserved.
Adding a project neither checks nor rewrites other projects' files; global templates still undergo the same conflict checks.
Directory symlinks are rejected. CLAUDE.md must be a relative link to the root AGENTS.md.
Ordinary write failures roll back additions from that invocation; after a forced process termination, inspect remaining files before retrying.

## Create a confirmed object

Generate a draft skeleton, fill every `<fill: ...>` value, then confirm intake:

```sh
uv run --locked toulmin draft claim tail-latency --root /path/to/research
# prints e.g. projects/tail-latency/runs/drafts/claim-20261102T140000Z.md
export TOULMIN_ACTOR="Researcher"   # optional default for --confirmed-by
uv run --locked toulmin new claim tail-latency --root /path/to/research \
  --input projects/tail-latency/runs/drafts/claim-20261102T140000Z.md --confirm
```

The skeleton lists required fields with their allowed values, so formats.md is only needed for details.
Intake rejects any value or body section that still contains `<fill: ...>`. `--input` may also be an absolute path inside the workbench.
`--confirm` is always required; `--confirmed-by` overrides `TOULMIN_ACTOR`, and one of them must be present.

A hand-written draft works as well, for example `projects/tail-latency/runs/drafts/claim.md`:

```markdown
---
source: {kind: human, actor: "Researcher"}
type: problem
importance: core
---
## Statement
Queueing delay is the main source of tail latency in the target trace. (Example: a proposition to validate.)
```

```sh
uv run --locked toulmin new claim tail-latency --root /path/to/research \
  --input projects/tail-latency/runs/drafts/claim.md \
  --confirmed-by "Researcher" --confirm
```

The command prints the new file's root-relative path. Intake generates the ID, creation time (whole seconds, UTC) and confirmation record without modifying the draft; the generated header lists fields in contract order.
Supported types: claim, evidence, objection, decision, exploration, spec, run. See the [format contract](docs/formats.md) for fields.
For model output, archive the raw response and record a Run first, then trace its provenance through source.ref/path. Run outcomes must explicitly be completed or failed.
Local file paths are relative to the workbench root; cross-project object references use project/ID.
An existing `.toulmin-new.lock` causes failure and is preserved. Confirm no writing session is active and inspect remaining files before recovery; the tool never removes another session's lock automatically.

## Prepare an independent review

Each independent role file in `roles/` lists the files its session receives. Reviewer personas (`reviewer-skeptic`, `reviewer-industry`, `reviewer-theorist`, `reviewer-why-not-x`) extend `roles/reviewer.md`; `synthesizer.md` compares review outputs.

```sh
uv run --locked toulmin inputs tail-latency reviewer-skeptic --root /path/to/research
uv run --locked toulmin draft run tail-latency --root /path/to/research --role reviewer-skeptic
```

`inputs` prints the brief, current Claims (superseded ones are left out) and the role contracts; `--claim C-002` (repeatable) selects Claims.
`draft run --role` writes the same list into the Run draft, so `input_files` is not retyped. Manifests cannot name sessions, handoffs, Runs, Decisions, Objections or other projects.

## Run automated reviews

`tools/models.toml` names the models (`[models.<name>]` with adapter `claude-code` or `codex`), the default personas and models, the run cap, parallelism and timeout.

```sh
uv run --locked toulmin review tail-latency --root /path/to/research --dry-run
uv run --locked toulmin review tail-latency --root /path/to/research \
  --personas reviewer-skeptic,reviewer-theorist --models claude,codex --confirm
```

Each persona × model pair runs once in a fresh, tool-free (Claude Code) or read-only sandboxed (Codex) session, from an empty temporary directory, with the persona's manifest files inlined in the prompt.
Every session becomes a Run with `prompt.md`, `output.md` and, on failure, `tool.log`; failures and timeouts are recorded as failed Runs and make the command exit 1. Reviews use subscription quota: the plan is printed first and `max_runs` caps one round.
review never writes Objections; take drafts in with `toulmin intake`.
Codex loads `$CODEX_HOME/AGENTS.md` in every session, so the template points Codex at a review-only home (`env = { CODEX_HOME = "~/.codex-toulmin" }`). Log in there once with `mkdir -p ~/.codex-toulmin && CODEX_HOME=~/.codex-toulmin codex login`; review refuses to start if that home holds AGENTS.md or is not logged in.

## Synthesize and cross-validate

```sh
uv run --locked toulmin synthesize tail-latency R-002 R-003 --root /path/to/research --confirm
uv run --locked toulmin crossval tail-latency projects/tail-latency/runs/drafts/question.md \
  --root /path/to/research --confirm
```

`synthesize` gives one fresh session the brief, current Claims and exactly the named Runs' outputs, and asks it to place every `R-NNN/label` into disagreements (listed first), agreements or singletons.
The synthesizer model rotates through `[review] models` across a project's syntheses (`--model` overrides; the Run records which and why).
`crossval` sends one question from `runs/drafts/` to each model independently, then synthesizes their answers. Neither command writes Objections: take drafts in from the original review output a group cites.

## Take in review drafts

A reviewer following `roles/reviewer.md` ends its output with a fenced `yaml` list of drafts (label, target, severity, content, grounds, uncertainty).
After archiving the output and recording its Run, choose drafts by label:

```sh
uv run --locked toulmin intake tail-latency \
  projects/tail-latency/runs/20261102T142016Z-review/output.md --root /path/to/research \
  --take draft-1,draft-3:minor --reject "draft-2=duplicates draft-1" --partly draft-4=O-007 --confirm
```

Each taken draft becomes an open Objection citing the Run and output; `LABEL:SEVERITY` overrides the severity and records the draft as partly taken.
`--partly` links an Objection you wrote by hand from that draft. Rejections need a reason. Outcomes go to `intake.md` beside the output and are never changed; replays report `already-...`.
Unlisted drafts stay pending, and status names them once the archive has an intake record. Nothing is written if any choice is invalid.

## Record a ruling

After writing a Decision whose `related` list names the object, record the researcher's choice:

```sh
uv run --locked toulmin rule tail-latency O-001 --root /path/to/research \
  --status answered --decision D-001 \
  --response projects/tail-latency/runs/drafts/o1-response.md --confirm
```

Every status change needs an active Decision naming the object; the command appends it to the object's `decisions`.
`--response`/`--ruling` (Objections) and `--section Invalidation=FILE` / `--section Rationale=FILE` add text to that section without deleting earlier text.
A Response alone needs no Decision. Run outcomes cannot be changed.
`--superseded-by`, `--adopted-as` and `--evidence` set the links that superseded, adopted and passed statuses need; rule never replaces an existing link.

To revise a Claim, supersede it instead of rewriting its Statement:

```sh
uv run --locked toulmin rule tail-latency C-001 --root /path/to/research \
  --status superseded --superseded-by C-004 --decision D-003 --confirm
```

D-003's `related` must list both C-001 and C-004. Objections and Evidence stay on C-001; status lists `C-001 -> C-004` under `Superseded:` and points each dependent at C-004.
The command preserves comments and other text, writes atomically, and prints status notices for the object and its target Claim.

## Inspect status and consistency

```sh
uv run --locked toulmin status tail-latency --root /path/to/research
uv run --locked toulmin status tail-latency --root /path/to/research --verbose
```

`--verbose` (`-v`) also prints the first paragraph (shortened to 100 characters) of each Claim statement and open Objection, the root-relative path of the last applied handoff, and settled Objections with the Decisions that ruled them.

Shows the stored stage, next step, Claim statuses, counts of valid verified supporting evidence, and open objections ordered fatal/major/minor.
Open-objection presence and eligibility for supported are reported separately; a minor objection can coexist with eligibility.
Gaining or losing eligibility produces a manual-review notice. Stored statuses and stages are preserved.

Checks cover the selected project's seven object types, PROJECT, explicit brief references and direct cross-project references.
They do not scan other projects for incoming evidence/objections or infer semantic consistency between brief prose and evidence.
References in fenced code blocks or examples indented by four spaces/a tab are skipped.
Corrupt files, broken references, invalid IDs/statuses, missing directories or creation locks cause exit 1 and unknown conditions; counts then cover only validated records.
Ruling notices on valid data exit 0; argument-usage errors exit 2. The command writes no objects, caches, indexes or Git metadata.

## Handoff and recovery

```sh
uv run --locked toulmin handoff tail-latency --root /path/to/research
uv run --locked toulmin handoff tail-latency --root /path/to/research \
  --apply "projects/tail-latency/runs/<generated-directory>/draft.md" \
  --confirmed-by "Researcher" --confirm
```

The first command only creates a reviewable draft. Its printed root-relative path can be passed directly to --apply; replace the example directory with the actual output.
Without session content, it records unknown information explicitly rather than inferring completed work.
For an actual handoff, use `--input <root-relative-summary-path>`. YAML may contain session_id (null if unknown), recent_decisions (existing Decision references)
and next_step; the body must contain Done, Decisions and Open questions. The command adds a Next step section pointing to metadata to avoid duplicate facts.
Review the generated draft before applying it. Application updates only PROJECT's recent decisions, next step and handoff pointer, preserving its body, comments and stage.

After interruption, rerun the same --apply command to finish from the complete recovery record. Repeated application returns the existing record without appending again or reverting the next step.
If PROJECT differs from the draft's baseline, the journal is corrupt or a session file conflicts, recovery records are preserved and overwriting is refused.
While pending, status reports incomplete data. Do not delete the journal or edit PROJECT during application.
Handoff writes currently require POSIX file synchronization, atomic rename, hard links and flock. They invoke no model and make no automatic Git commit.

See the [manual acceptance record](docs/manual-acceptance.md) for the accepted trial, its retrospective and a reusable two-day checklist.

## Development

Requires Python >=3.12 and uv. `.python-version` pins the development interpreter to the 3.12 series.

```sh
uv sync --locked --dev
uv run --locked toulmin --help
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src/toulmin
```

On this machine, uv/Python are installed under the Git-ignored `.tools/` to avoid changing the system interpreter or shell configuration.
Set the following in the current shell if using that installation; machines with uv already installed do not need these settings:

```sh
export PATH="$PWD/.tools/bin:$PATH"
export UV_CACHE_DIR="$PWD/.uv-cache"
export UV_PYTHON_INSTALL_DIR="$PWD/.tools/python"
```

### Shell activation troubleshooting

From the software checkout, `source .venv/bin/activate` should make `toulmin` available.
If it disappears at the next zsh prompt, a `pyenv-virtualenv` prompt hook may be deactivating
the externally managed environment. This was reproduced on this host: activation succeeded,
then `_pyenv_virtualenv_hook` removed it. For the current zsh only:

```zsh
precmd_functions=(${precmd_functions:#_pyenv_virtualenv_hook})
source .venv/bin/activate
command -v toulmin
toulmin --help
```

This temporarily disables pyenv's automatic prompt switching in that shell; a new shell
loads its normal hooks again. It changes neither `.zshrc` nor the system Python. Alternatively,
run `.venv/bin/toulmin` directly from the checkout without activation. Do not recreate the
environment merely because a shell hook has removed its PATH entry.

## Project documentation

- [Python/Textual TUI design](docs/tui-design.md): approved workflow, architecture and implementation plan.

- [Design](docs/design.md), [L1 formats](docs/formats.md), [seven object examples](docs/format-examples.md), [L2 protocols](docs/protocols.md), [workspace-first file contract (not implemented)](docs/workspace-formats.md).
- [Repository rules](AGENTS.md), [implementation tasks](TODO.md), [session progress](PROGRESS.md).

Maintain documentation, templates and progress records in English. Conversation follows the user's language.
The published templates framework/formats.md, format-examples.md, protocols.md and workspace-formats.md are copies of their namesakes in docs/.
Synchronize them when editing contracts; tests check equality, and the installed CLI does not depend on the source checkout.

Dependencies point downward: `cli` (L3) → `protocols` (L2) → `core` (L1); L3 may also use L1 directly.
Core and protocols do not depend on Typer, specific model tools or networking. Research workbench templates and the software development repository are managed separately.

## Native CLI with a project board

Open a project in the TUI and press **F4 Native CLI**, or run:

```sh
uv run --locked --extra tui toulmin native my-topic --root /path/to/workbench --agent codex
```

Discuss in the native CLI, ask for `draft.md`, exit the CLI, then confirm **Apply to Brief**
on the project board. Requires Linux, tmux and bubblewrap for new sessions. The returned draft
and input snapshots are archived as a Run; the full native conversation is not captured.
See [native workspace usage and recovery](docs/native-workspace.md).
