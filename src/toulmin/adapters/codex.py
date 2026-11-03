"""Codex CLI: `codex exec` in a read-only sandbox, ephemeral, from an empty directory.

The final message is taken from --output-last-message; the JSONL event stream (--json)
supplies the thread ID. The read-only sandbox blocks writes, not reads, so isolation
also relies on the inlined prompt telling the model to use no tools; the empty working
directory keeps project AGENTS.md files out of discovery.
"""

import json
import os
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

LAST_MESSAGE = ".toulmin-last-message.txt"
# Codex adds these from CODEX_HOME to every session as the operator's own instructions.
INSTRUCTION_FILES = ("AGENTS.md", "AGENTS.override.md")
LOGIN_TIMEOUT = 30.0


class Codex:
    name = "codex"
    default_command = "codex"

    def preflight(
        self,
        command: str,
        env: tuple[tuple[str, str], ...],
        cancel: threading.Event | None = None,
    ) -> str | None:
        """Refuse a home with global instructions, or one that is not logged in."""
        configured = dict(env).get("CODEX_HOME") or os.environ.get("CODEX_HOME")
        home = Path(configured) if configured else Path.home() / ".codex"
        login = f"run once: CODEX_HOME={home} {command} login"
        for name in INSTRUCTION_FILES:
            if (home / name).exists():
                return (
                    f"{home / name} would add the operator's global instructions to every "
                    'review; set env = { CODEX_HOME = "~/.codex-toulmin" } for this model in '
                    "tools/models.toml and log in there once: mkdir -p ~/.codex-toulmin && "
                    f"CODEX_HOME=~/.codex-toulmin {command} login"
                )
        if not home.is_dir():
            return f"CODEX_HOME {home} does not exist; {login}"

        def status(directory: Path) -> Finished:
            return run_process(
                [command, "login", "status"], "", LOGIN_TIMEOUT, directory, env, cancel
            )

        finished = in_empty_directory(status)
        if finished.exit_status != 0:
            return f"not logged in for CODEX_HOME {home}; {login}"
        return None

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
                session.cancel,
            )
            message = directory / LAST_MESSAGE
            text = (
                message.read_bytes().decode("utf-8", errors="replace") if message.is_file() else ""
            )
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
            text=text,
            model=model,
            session_id=session_id,
            duration_seconds=finished.duration_seconds,
            failure=failure,
            log="" if failure is None and text.strip() else diagnostics(finished),
        )
