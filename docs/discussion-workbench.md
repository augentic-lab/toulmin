# Conversation-first workbench

The researcher approved this direction on 2026-11-03 after finding the UI-R2/UI-R3
guided prototypes less clear than direct agent conversation. The main task is thinking
with a model toward a defensible Research Brief. Research state and explicit actions
support that conversation; they do not impose a sequence of forms or mandatory Claims.

## Use the workspace

1. Launch `toulmin tui`, create a project with its goal/motivation, or open an existing
   project. From the checkout use `uv run --locked --extra tui toulmin tui`.
2. Select a model alias configured in the workbench's `tools/models.toml`. Its CLI must
   already be installed and authenticated. Exploration uses its own tool-enabled sandbox
   profile; independent reviews retain their restricted profile. Opening calls no model.
3. Type in the composer and select **Send**. Enter inserts newlines. Each explicit Send
   starts one fresh invocation with the saved context and your message. Exploration can
   search the web, read sources and download materials into its research workspace. The UI remains
   available while waiting for the final answer. **Stop** cancels that project's job.
4. Use **Context** to inspect the saved inputs for the next message; the current composer
   and operation instruction are appended on Send. Every submitted exact prompt is archived.
   Model switching carries the same file-backed conversation, without vendor session resume.
5. When useful, select **Propose Brief**. This is another model invocation that produces
   a full replacement draft. The inspector has **Saved**, **Proposed** and **Changes**.
   Edit the proposal and confirm **Apply to Brief**, or **Dismiss** it. Working edits
   auto-save under `runs/`; only confirmed application replaces `brief.md`.
6. Continue discussing while a proposal is pending. Apply or dismiss it before requesting
   another proposal. No model answer changes Claims, evidence grades, Objections or stage.
7. Reopen the project to continue from the submitted messages and archived responses.
   Quit stops active jobs and archives failures; it does not write a research handoff.
   For an interrupted request after a crash, **Recover** finalizes already saved output
   or records an interrupted failure. Sending a new request is always explicit.

The left pane shows the saved stage, goal, open objections and last recorded next step.
These are file-backed research facts, not an inferred progress percentage. Other views
remain optional. The center is the discussion; the inspector is subordinate. F2 switches
between discussion and inspector on narrower terminals. All labels are English.

## Boundaries of this slice

- One conversation per project, one active invocation per project, one pending Brief
  proposal. The full conversation is used until the 100,000-character request limit;
  no history is silently dropped. Context selection/summarization is not implemented.
- Inputs are the workbench instructions, PROJECT, saved Brief, optional last handoff and
  complete submitted conversation, plus any pending edited Brief labelled unconfirmed.
  Exploration may additionally search/read/download using enabled tools. Prior research
  workspace paths are included so downloaded files can be revisited. Arbitrary attachment
  selection is not implemented. Failed partial output stays visible in archives and is excluded from
  completed-answer context. These conversations do not constitute independent review.
- Existing adapters return a final response; no live token stream is claimed. A model
  can fail during login, execution, cancellation or timeout; each attempted invocation
  has its own saved request and completed/failed Run. No background automatic retries.
- Tool permissions differ by operation. Discussion enables research tools in a scoped
  workspace; Brief generation uses supplied context without tools. Independent review
  retains its existing read-only/no-tools contract. These profiles do not guarantee that
  every website is accessible or that search results or downloaded documents are correct.
- Applying a Brief checks the saved before image and rejects an external edit. Retained
  before/after images and confirmation make interrupted application resumable. Do not
  edit `brief.md` concurrently with Apply; external editors do not share Toulmin's lock.
- Claim extraction, independent review cards, objection handling and handoff authoring
  are not implemented in this TUI slice. Use the existing CLI for review/intake/ruling/
  handoff. The UI does not claim a research gate is complete.
- The unsent composer survives navigation in the running app, but is not a submitted
  record and is not saved across process exit. Submitted turns and proposal edits are
  durable. Long-session performance and CJK/IME require a real researcher trial.

## Verification and acceptance

Automated tests use disposable fake CLIs and temporary workbenches. They exercise
conversation reconstruction, cancellation and process cleanup, resume without quota,
proposal confirmation/conflicts/recovery and keyboard access at three terminal sizes.
They demonstrate program behavior, not the value of the research experience.

The next human trial is deliberately small: discuss one real observation for two turns,
request/edit/apply a Brief proposal, close and reopen. Assess whether the conversation
is fluid and whether the saved result, uncertainty and next action remain clear.
Do not treat the earlier fixed-output prototypes as product acceptance.

## Exploration research materials (UI2 follow-up)

The researcher authorized search, network access and downloads on 2026-11-03. Each
exploration request has a `research/` directory inside its archived conversation request.
Downloads stay there after completion, cancellation or failure. Later exploration turns
receive prior workspace locations and may read their materials as needed. Merely having
a downloaded file does not make it verified Evidence or a formal research object.

The prompt asks the model to cite source URLs, access dates, what it actually read
(abstract/full text/excerpt) and failed accesses. These are model-reported statements,
not a verified bibliography. Tool event output and stderr are archived beside `research/`
as `tool-events.jsonl` and `tool-stderr.log`; availability depends on what the CLI emits.
Automatic citation extraction and a structured source browser remain future work.

The adapters retain their CLI sandbox boundaries: research writes are scoped to the
workspace, with any temporary paths the native sandbox requires. They do not grant
unrestricted host writes or use a sandbox-bypass fallback. Missing sandbox support is
reported as a failed invocation. Account, administrator and website policies still
apply, including paywalls and authentication requirements. Research queries contact
external services, and downloads consume local disk space. Stop and the configured
timeout remain available; the UI still displays the final answer rather than a live
tool-activity stream.

Claude's Linux sandbox requires `bubblewrap` and `socat` on PATH (or an
administrator-managed executable path). On openEuler, install missing dependencies with
`sudo dnf install bubblewrap socat`; the application never bypasses a missing sandbox.
See [Claude sandboxing](https://code.claude.com/docs/en/sandboxing).
The Codex profile uses its native workspace-write sandbox, live search and network setting;
see [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference).
