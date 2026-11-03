"""Claude Code: isolated review or sandboxed exploration in an explicit workspace.

--tools "" removes every tool, so the session can read nothing beyond the inlined
prompt. --safe-mode skips CLAUDE.md files, skills, plugins, hooks and MCP servers while
keeping normal authentication. Only persistent exploration saves native sessions;
independent tasks stay fresh and out of the operator's resume list.
"""

import json
import threading
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
            arguments += ["json", "--tools", ""]
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
        if finished.stdout:
            try:
                if session.workspace is None:
                    result = json.loads(finished.stdout)
                else:
                    # Native exploration emits JSONL; also accept a single result
                    # object from compatible wrappers and older CLI versions.
                    events = [json.loads(line) for line in finished.stdout.splitlines() if line]
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
                if result.get("is_error") and failure is None:
                    failure = f"the tool reported an error: {str(text)[:300]}"
                if not isinstance(text, str):
                    raise ValueError("result: expected a string")
            except ValueError as error:
                failure = failure or f"unreadable JSON output: {error}"
                # A cancelled CLI may leave incomplete JSON. Retain these exact bytes
                # as incomplete output rather than dropping them into a truncated log.
                text = finished.stdout
        elif failure is None:
            failure = "unreadable JSON output: expected a JSON object"
        model = session.model or reported or f"{self.name} default (not reported)"
        native_id = session_id if isinstance(session_id, str) else None
        failure = failure or persistence_failure(session, native_id)
        return ReviewOutcome(
            text=text,
            model=model,
            session_id=native_id,
            duration_seconds=finished.duration_seconds,
            failure=failure,
            log="" if failure is None else diagnostics(finished),
        )
