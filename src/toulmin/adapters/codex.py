"""Codex CLI: `codex exec` in a read-only sandbox, ephemeral, from an empty directory.

The final message is taken from --output-last-message; the JSONL event stream (--json)
supplies the thread ID. The read-only sandbox blocks writes, not reads, so isolation
also relies on the inlined prompt telling the model to use no tools; the empty working
directory keeps project AGENTS.md files out of discovery.
"""

import json
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

LAST_MESSAGE = ".toulmin-last-message.txt"


class Codex:
    name = "codex"
    default_command = "codex"

    def arguments(self, session: Session, directory: Path) -> list[str]:
        arguments = [session.command, "exec", "--sandbox", "read-only", "--ephemeral"]
        arguments += ["--skip-git-repo-check", "--color", "never", "--json"]
        arguments += ["-C", str(directory), "-o", str(directory / LAST_MESSAGE)]
        if session.model:
            arguments += ["--model", session.model]
        return arguments + list(session.extra_args) + ["-"]

    def run(self, session: Session) -> ReviewOutcome:
        def call(directory: Path) -> tuple[Finished, str]:
            finished = run_process(
                self.arguments(session, directory),
                session.prompt,
                session.timeout_seconds,
                directory,
                session.env,
            )
            message = directory / LAST_MESSAGE
            text = message.read_text("utf-8", errors="replace") if message.is_file() else ""
            return finished, text

        finished, text = in_empty_directory(call)
        return self.interpret(session, finished, text)

    def interpret(self, session: Session, finished: Finished, text: str) -> ReviewOutcome:
        failure = failure_of(finished, session.timeout_seconds)
        session_id = None
        for line in finished.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("type") == "thread.started":
                thread = event.get("thread_id")
                session_id = thread if isinstance(thread, str) and thread else None
        model = session.model or f"{self.name} default (not reported)"
        return ReviewOutcome(
            text="" if failure else text,
            model=model,
            session_id=session_id,
            duration_seconds=finished.duration_seconds,
            failure=failure,
            log="" if failure is None and text.strip() else diagnostics(finished),
        )
