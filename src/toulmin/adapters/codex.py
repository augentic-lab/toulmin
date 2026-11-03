"""Codex CLI: isolated ephemeral tasks or persistent sandboxed exploration.

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
    archive_tool_trace,
    diagnostics,
    failure_of,
    in_empty_directory,
    persistence_failure,
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
        self._validate_extra_args(session)
        sandbox = "read-only" if session.workspace is None else "workspace-write"
        arguments = [session.command, "exec", "--sandbox", sandbox]
        if not session.persistent:
            arguments += ["--ephemeral"]
        arguments += ["--skip-git-repo-check", "--color", "never", "--json"]
        message = self._message_path(session, directory)
        arguments += ["-C", str(directory), "-o", str(message)]
        if session.model:
            arguments += ["--model", session.model]
        if session.workspace is not None:
            # Do not inherit extra writable roots, hooks or ancestor project
            # instructions from the operator/research workbench configuration.
            arguments += ["--ignore-user-config", "--ignore-rules"]
            for setting in (
                'sandbox_mode="workspace-write"',
                'approval_policy="never"',
                'web_search="live"',
                "sandbox_workspace_write.network_access=true",
                "sandbox_workspace_write.writable_roots=[]",
                "sandbox_workspace_write.exclude_slash_tmp=true",
                "sandbox_workspace_write.exclude_tmpdir_env_var=true",
                "project_doc_max_bytes=0",
                "project_root_markers=[]",
                "features.hooks=false",
            ):
                arguments += ["-c", setting]
        extras = [
            argument
            for argument in session.extra_args
            if session.workspace is None
            or argument not in ("--ignore-user-config", "--ignore-rules")
        ]
        # --sandbox, -C and --color belong to exec, not its resume subcommand.
        # Keep all policy flags before resume so they apply on every invocation.
        continuation = [] if session.resume_id is None else ["resume", session.resume_id]
        return arguments + extras + continuation + ["-"]

    def _message_path(self, session: Session, directory: Path) -> Path:
        if session.workspace is None:
            return directory / LAST_MESSAGE
        return (session.archive_directory or directory.parent) / LAST_MESSAGE

    def _validate_extra_args(self, session: Session) -> None:
        controlled = {
            "--sandbox",
            "-s",
            "--approve-for-me",
            "--full-auto",
            "--dangerously-bypass-approvals-and-sandbox",
            "--yolo",
            "--not-so-yolo",
            "--dangerously-bypass-hook-trust",
            "--cd",
            "-C",
            "--add-dir",
            "--worktree",
            "--profile",
            "-p",
            "--output-last-message",
            "-o",
            "--output-schema",
            "--json",
            "--ask-for-approval",
            "-a",
            "--enable",
            "--disable",
            "--search",
            "--ephemeral",
            "--last",
            "--all",
        }
        safe_settings = {
            "model_reasoning_effort",
            "model_reasoning_summary",
            "model_verbosity",
            "service_tier",
        }
        extras = iter(session.extra_args)
        for argument in extras:
            option = argument.split("=", 1)[0]
            if argument in ("resume", "fork", "review", "--"):
                raise ValueError(f"extra_args cannot override controlled Codex option {argument}")
            if option in controlled or any(
                argument.startswith(short) and argument != short
                for short in ("-s", "-C", "-o", "-p", "-a")
            ):
                raise ValueError(f"extra_args cannot override controlled Codex option {argument}")
            if option == "--config" or argument.startswith("-c"):
                if argument in ("-c", "--config"):
                    value = next(extras, "")
                else:
                    value = (
                        argument.removeprefix("--config=") if option == "--config" else argument[2:]
                    )
                if value.split("=", 1)[0].strip() not in safe_settings:
                    raise ValueError(f"extra_args cannot override controlled Codex config {value}")

    def run(self, session: Session) -> ReviewOutcome:
        def call(directory: Path) -> tuple[Finished, str]:
            message = self._message_path(session, directory)
            if message.exists() or message.is_symlink():
                raise FileExistsError(f"refusing to overwrite native final message: {message}")
            finished = run_process(
                self.arguments(session, directory),
                session.prompt,
                session.timeout_seconds,
                directory,
                session.env,
                session.cancel,
            )
            text = (
                message.read_bytes().decode("utf-8", errors="replace") if message.is_file() else ""
            )
            return finished, text

        finished, text = (
            in_empty_directory(call) if session.workspace is None else call(session.workspace)
        )
        archive_tool_trace(session, finished)
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
        failure = failure or persistence_failure(session, session_id)
        return ReviewOutcome(
            text=text,
            model=model,
            session_id=session_id,
            duration_seconds=finished.duration_seconds,
            failure=failure,
            log="" if failure is None and text.strip() else diagnostics(finished),
        )
