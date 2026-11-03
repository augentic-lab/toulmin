# Native research workspace (UI-N1)

The native workspace connects an existing research project to an interactive Codex or Claude
CLI beside a Toulmin project board. It follows the accepted UI-R4 split interaction; it does
not replace the existing Discussion UI or implement Claims/review automation.

## Open a project

In `toulmin tui`, open a project and press **F4 Native CLI**. Choose a new Codex or Claude
discussion, or select a saved native session. Alternatively:

```sh
uv run --locked --extra tui toulmin native my-topic --root /path/to/workbench --agent codex
uv run --locked --extra tui toulmin native my-topic --root /path/to/workbench --agent claude
```

New discussions require Linux, working bubblewrap (`bwrap`), tmux, an installed/authenticated
native CLI and a terminal of at least 100 columns × 24 rows. Saved-session inspection needs
Textual and an interactive terminal but does not launch a CLI or require tmux/bubblewrap.
Use the workbench root, not its `projects/my-topic` subdirectory. Resolve project diagnostics,
incomplete setup and unfinished headless Discussion/proposals before starting a new session.
The launcher holds the same project job lease as Discussion to prevent concurrent jobs.

## Discuss and return a Brief

1. Toulmin freezes the project's AGENTS.md, PROJECT.md, saved Brief and last handoff, if present.
   The native CLI starts with a message asking it to read the resulting `context.md`. Starting
   a new native discussion can therefore invoke the model; opening the F4 menu does not.
2. Use the native CLI normally: discuss, search, inspect sources, change its model or use its
   own commands. Its configuration/authentication applies, independently of `tools/models.toml`.
   Native model/session selection is not mirrored into the board.
3. When ready, ask it to write a **complete replacement Brief** to `draft.md` in the research
   workspace. Preserve the saved Brief's required headings and valid object references.
   The left board shows the current project state, saved Brief and live draft. Native output
   is a proposal; it does not change project stage or establish supported evidence.
4. Exit the native CLI using its normal exit action. Toulmin freezes the returned draft and
   records an ordinary Run. Preview the draft/diff on the board, then explicitly confirm
   **Apply to Brief**. Application is available only for an archived successful session with
   a valid Brief. A changed saved Brief causes a conflict rather than an overwrite.
5. Quit the board to return to the main workbench or shell. The main TUI reloads the saved Brief.

Press **Ctrl+b**, release, then **o** to switch panes; **Ctrl+b**, then **z** zooms/unzooms.
Mouse clicks also select panes. Quitting the board or detaching closes this split and stops
its native process; it is not a way to keep an agent running in the background. Exit the CLI
normally first if you want its draft to be eligible for application.

## Reopen and recover

F4 lists prior native archives. Opening a closed archive runs no model and lets you inspect
its saved draft, Run and application status. You may apply a still-valid pending draft.

```sh
uv run --locked --extra tui toulmin native my-topic --root /path/to/workbench --session SESSION_ID
# Explicitly close an interrupted record as failed, without retrying the model:
uv run --locked --extra tui toulmin native my-topic --root /path/to/workbench --session SESSION_ID --recover
```

F4's **Open / recover selected archive** is an explicit recovery action for an interrupted
record. Live workers hold a separate lease and cannot be recovered concurrently. Application
intents preserve the actor and exact before/after images; interrupted applications can be
completed with the same actor/text. `--actor` controls attribution for command-line use.
Interrupted/nonzero/unknown-exit sessions retain readable partial drafts for inspection but
cannot apply them. Invalid, oversized or nonregular output fails closed and requires inspection
of the saved workspace; no model retry or silent data repair occurs.

## What is recorded

Auxiliary session data lives under `projects/PROJECT/runs/native/SESSION_ID/`. The `research/`
subdirectory is the native CLI's working directory; downloaded material remains there, mutable
and unverified. Frozen inputs, closure/application records and before/after images sit outside
it. A normal Run points to a separate direct `runs/TIMESTAMP-native-UUID/` archive containing
the supplied context, closure record and returned raw draft, if any.

**The complete native conversation is not captured.** The draft is not a transcript. Tool
label and launch outcome are recorded; model, provider session ID and duration are unknown
unless externally reported to the protocol. The current launcher does not collect those values.
Terminal diagnostics are not evidence or complete conversation history. Native provider caches
remain provider-managed. Existing headless Discussion history/native sessions are not adopted
or resumed by this entry point; current project artifacts and the last handoff are supplied.

## Filesystem and lifecycle boundary

The launcher uses bubblewrap to make direct workbench paths read-only while allowing writes
inside this session's `research/`. It preserves networking and ordinary native cache access,
hides its private tmux socket, creates a private `/dev`/devpts for native command PTYs,
and uses a PID namespace to stop local descendants on exit.
Codex runs with `--no-daemon` so its execution stays in this process tree; remote/shared app
server routing is not enabled. If bubblewrap cannot start, the launcher refuses to run rather
than falling back to unprotected execution.

If an older native session reports `Failed to create unified exec process: Permission denied`
before even running `pwd` or `cat`, close that native split and start a new one after updating
Toulmin. Existing namespaces are not changed in place. This PTY startup failure does not mean
the researcher needs to change `context.md` permissions.

This is path protection, not a comprehensive sandbox against a hostile native agent: existing
hardlink aliases outside the workbench and other same-user host-service sockets remain outside
that guarantee. Native integrations may contact external services under their own permissions.
Do not use terminal output as proof of source accuracy or assume all native integrations are
controlled by Toulmin. Independent research review retains its existing restricted-input path.

## Compatibility and acceptance

The auxiliary records are version 1; the seven research-object schemas are unchanged and no
migration is required. Existing projects acquire these records only when a native session starts.
Older readers can still read ordinary Runs but do not provide this session-management UI.
Automated validation uses temporary projects and fake CLI executables. Real native research
usability, provider-specific UI/configuration and long sessions remain researcher acceptance.
