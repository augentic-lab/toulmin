"""Claude Code: isolated review or sandboxed exploration in an explicit workspace.

--tools "" removes every tool, so the session can read nothing beyond the inlined
prompt. Independent sessions stream their events (stream-json with partial messages) so a
session that times out still shows whether the model answered and how far it got.
--safe-mode skips CLAUDE.md files, skills, plugins, hooks and MCP servers while
keeping normal authentication. Only persistent exploration saves native sessions;
independent tasks stay fresh and out of the operator's resume list.
"""

import json
import threading
from collections import Counter
from dataclasses import replace
from pathlib import Path

from toulmin.adapters.base import (
    Finished,
    Session,
    archive_tool_trace,
    diagnostics,
    failure_of,
    in_empty_directory,
    persistence_failure,
    run_process,
)
from toulmin.core.usage import Usage, claude_usage
from toulmin.protocols.review import ReviewOutcome


class ClaudeCode:
    name = "claude-code"
    default_command = "claude"

    def preflight(
        self,
        command: str,
        env: tuple[tuple[str, str], ...],
        cancel: threading.Event | None = None,
    ) -> str | None:
        return None  # --safe-mode already skips CLAUDE.md files and other customizations

    def arguments(self, session: Session) -> list[str]:
        self._validate_extra_args(session)
        arguments = [session.command, "-p", "--output-format"]
        if session.workspace is None:
            # Streamed, so a killed session leaves its partial answer and progress (W10).
            arguments += ["stream-json", "--verbose", "--include-partial-messages", "--tools", ""]
        else:
            # Only Bash writes files, and every Bash call must stay sandboxed.
            # WebFetch(domain:*) also pre-allows HTTP(S) shell downloads through
            # Claude's proxy without adding a domain allowlist for exploration.
            settings = {
                "permissions": {"allow": ["WebSearch", "WebFetch(domain:*)"]},
                "sandbox": {
                    "enabled": True,
                    "failIfUnavailable": True,
                    "autoAllowBashIfSandboxed": True,
                    "allowUnsandboxedCommands": False,
                    "excludedCommands": [],
                    "filesystem": {"disabled": False},
                },
            }
            arguments += [
                "stream-json",
                "--verbose",
                "--tools",
                "Bash,WebSearch,WebFetch",
                "--restricted",
                "--permission-mode",
                "dontAsk",
                "--permission-prompts",
                "none",
                "--settings",
                json.dumps(settings),
                "--strict-mcp-config",
                "--mcp-config",
                '{"mcpServers":{}}',
            ]
        arguments += ["--safe-mode"]
        if not session.persistent:
            arguments += ["--no-session-persistence"]
        if session.resume_id is not None:
            arguments += ["--resume", session.resume_id]
        if session.model:
            arguments += ["--model", session.model]
        return arguments + list(session.extra_args)

    def _validate_extra_args(self, session: Session) -> None:
        controlled = {
            "-p",
            "--print",
            "--output-format",
            "--verbose",
            "--include-partial-messages",
            "--tools",
            "--allowedTools",
            "--allowed-tools",
            "--disallowedTools",
            "--disallowed-tools",
            "--safe-mode",
            "--restricted",
            "--settings",
            "--setting-sources",
            "--permission-mode",
            "--permission-prompts",
            "--add-dir",
            "--dangerously-skip-permissions",
            "--allow-dangerously-skip-permissions",
            "--mcp-config",
            "--strict-mcp-config",
            "--plugin-dir",
            "--plugin-url",
            "--no-session-persistence",
            "--session-id",
            "--fork-session",
            "--from-pr",
            "--teleport",
            "--cloud",
            "--resume",
            "-r",
            "--continue",
            "-c",
            "--worktree",
            "-w",
            "--system-prompt",
            "--append-system-prompt",
        }
        for argument in session.extra_args:
            if argument.split("=", 1)[0] in controlled or any(
                argument.startswith(short) and argument != short for short in ("-r", "-c", "-w")
            ):
                raise ValueError(f"extra_args cannot override controlled Claude option {argument}")

    def run(self, session: Session) -> ReviewOutcome:
        def call(directory: Path) -> Finished:
            return run_process(
                self.arguments(session),
                session.prompt,
                session.timeout_seconds,
                directory,
                session.env,
                session.cancel,
            )

        finished = (
            in_empty_directory(call) if session.workspace is None else call(session.workspace)
        )
        archive_tool_trace(session, finished)
        return self.interpret(session, finished)

    def interpret(self, session: Session, finished: Finished) -> ReviewOutcome:
        failure = failure_of(finished, session.timeout_seconds)
        text, session_id, reported = "", None, None
        tokens: Usage | None = None
        progress: Progress | None = None
        if finished.stdout:
            try:
                # JSONL events; a single result object from compatible wrappers and older
                # CLI versions is one line of the same form.
                events = [json.loads(line) for line in finished.stdout.splitlines() if line]
                progress = Progress(events)
                results = [
                    event
                    for event in events
                    if isinstance(event, dict)
                    and (event.get("type") == "result" or "result" in event)
                ]
                if not results:
                    raise ValueError("expected a final result event")
                result = results[-1]
                if not isinstance(result, dict):
                    raise ValueError("expected a JSON object")
                text = result.get("result") or ""
                session_id = result.get("session_id") or None
                usage = result.get("modelUsage")
                reported = next(iter(usage), None) if isinstance(usage, dict) else None
                tokens = claude_usage(result)
                if result.get("is_error") and failure is None:
                    failure = f"the tool reported an error: {str(text)[:300]}"
                if not isinstance(text, str):
                    raise ValueError("result: expected a string")
            except ValueError as error:
                failure = failure or f"unreadable JSON output: {error}"
                # A killed or cancelled CLI leaves no result: keep the answer it had
                # streamed so far, or, for output that is not an event stream, the exact
                # bytes, as incomplete output rather than dropping them.
                text = progress.text if progress is not None else finished.stdout
                reported = reported or (progress.model if progress is not None else None)
        elif failure is None:
            failure = "unreadable JSON output: expected a JSON object"
        model = session.model or reported or f"{self.name} default (not reported)"
        native_id = session_id if isinstance(session_id, str) else None
        failure = failure or persistence_failure(session, native_id)
        log = ""
        if failure is not None:
            shown = finished if progress is None else replace(finished, stdout=progress.summary())
            log = diagnostics(shown)
        return ReviewOutcome(
            text=text,
            model=model,
            session_id=native_id,
            duration_seconds=finished.duration_seconds,
            failure=failure,
            log=log,
            usage=tokens,
            reported_model=reported if isinstance(reported, str) else None,
        )


class Progress:
    """How far a streamed session got: blocks, characters received, the last events."""

    def __init__(self, events: list[object]) -> None:
        self.events = [event for event in events if isinstance(event, dict)]
        self.kinds: Counter[str] = Counter()
        self.blocks: list[tuple[str, int]] = []  # (block type, characters received)
        self.answer: list[str] = []
        self.model: str | None = None
        self.started = False
        for event in self.events:
            kind = str(event.get("type"))
            inner = event.get("event") if kind == "stream_event" else None
            if isinstance(inner, dict):
                kind = f"stream_event/{inner.get('type')}"
                self._stream(inner)
            elif kind == "assistant" and not self.blocks:
                # Without partial messages, the whole answer arrives in one message.
                self._message(event.get("message"))
            self.kinds[kind] += 1

    def _stream(self, inner: dict[str, object]) -> None:
        kind = inner.get("type")
        if kind == "message_start":
            self.started = True
            message = inner.get("message")
            if isinstance(message, dict) and isinstance(message.get("model"), str):
                self.model = message["model"]
        elif kind == "content_block_start":
            block = inner.get("content_block")
            name = block.get("type") if isinstance(block, dict) else None
            self.blocks.append((str(name), 0))
        elif kind == "content_block_delta" and self.blocks:
            delta = inner.get("delta")
            if isinstance(delta, dict):
                piece = next(
                    (delta[key] for key in ("text", "thinking", "partial_json") if key in delta),
                    "",
                )
                if isinstance(piece, str):
                    name, size = self.blocks[-1]
                    self.blocks[-1] = (name, size + len(piece))
                    if delta.get("type") == "text_delta":
                        self.answer.append(piece)

    def _message(self, message: object) -> None:
        if not isinstance(message, dict):
            return
        if isinstance(message.get("model"), str):
            self.model = message["model"]
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                self.answer.append(str(block.get("text", "")))

    @property
    def text(self) -> str:
        return "".join(self.answer)

    def summary(self) -> str:
        blocks = ", ".join(f"{name} {size} chars" for name, size in self.blocks) or "none"
        kinds = ", ".join(f"{kind} x{count}" for kind, count in sorted(self.kinds.items()))
        last = [json.dumps(event, ensure_ascii=False)[:400] for event in self.events[-5:]]
        lines = [
            f"events: {len(self.events)} ({kinds or 'none'})",
            f"model answer started: {'yes' if self.started or self.blocks else 'no'}",
            f"content blocks: {blocks}",
            f"partial answer kept: {len(self.text)} chars",
            "last events:",
            *last,
        ]
        return "\n".join(lines) + "\n"
