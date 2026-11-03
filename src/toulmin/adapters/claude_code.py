"""Claude Code: `claude -p` with JSON output and no tools.

--tools "" removes every tool, so the session can read nothing beyond the inlined
prompt. --safe-mode skips CLAUDE.md files, skills, plugins, hooks and MCP servers while
keeping normal authentication. --no-session-persistence keeps the session fresh and
out of the operator's resume list; the reported session ID is still recorded.
"""

import json
import threading
from pathlib import Path

from toulmin.adapters.base import (
    Finished,
    Session,
    diagnostics,
    failure_of,
    in_empty_directory,
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
        arguments = [session.command, "-p", "--output-format", "json", "--tools", ""]
        arguments += ["--safe-mode", "--no-session-persistence"]
        if session.model:
            arguments += ["--model", session.model]
        return arguments + list(session.extra_args)

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

        finished = in_empty_directory(call)
        return self.interpret(session, finished)

    def interpret(self, session: Session, finished: Finished) -> ReviewOutcome:
        failure = failure_of(finished, session.timeout_seconds)
        text, session_id, reported = "", None, None
        if finished.stdout:
            try:
                result = json.loads(finished.stdout)
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
        return ReviewOutcome(
            text=text,
            model=model,
            session_id=session_id if isinstance(session_id, str) else None,
            duration_seconds=finished.duration_seconds,
            failure=failure,
            log="" if failure is None else diagnostics(finished),
        )
