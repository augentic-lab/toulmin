"""The adapter interface and a process runner with a hard timeout."""

import os
import re
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from toulmin.core.atomic import write_atomic
from toulmin.protocols.review import ReviewOutcome

LOG_LIMIT = 20_000
_ACTIVE: set[int] = set()
_ACTIVE_LOCK = threading.Lock()


@dataclass(frozen=True)
class Session:
    """One headless session: a self-contained prompt and optional tool settings."""

    prompt: str
    model: str  # tool model name; empty means the tool's default
    timeout_seconds: float
    command: str  # executable name or path
    extra_args: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()  # added to the inherited environment
    cancel: threading.Event | None = None
    workspace: Path | None = None  # explicit exploration scratch directory; None isolates reviews
    resume_id: str | None = None
    persistent: bool = False
    archive_directory: Path | None = None  # this invocation's logs, outside a shared workspace

    def __post_init__(self) -> None:
        if self.persistent and (self.workspace is None or self.archive_directory is None):
            raise ValueError("persistent exploration requires a workspace and archive_directory")
        if self.resume_id is not None:
            if not self.persistent:
                raise ValueError("resume_id requires persistent exploration")
            if not valid_session_id(self.resume_id):
                raise ValueError("resume_id must be a safe native session identifier")
        if self.workspace is not None and self.archive_directory is not None:
            if self.archive_directory.resolve().is_relative_to(self.workspace.resolve()):
                raise ValueError("archive_directory must be outside the model-writable workspace")


def valid_session_id(value: str) -> bool:
    """Accept opaque CLI identifiers, excluding flags, paths and picker expressions."""
    return re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value) is not None


def persistence_failure(session: Session, session_id: str | None) -> str | None:
    if not session.persistent or session_id is None:
        return None
    if not valid_session_id(session_id):
        return "native session identifier invalid; continuity was not established"
    if session.resume_id is not None and session.resume_id != session_id:
        return (
            "native resume returned a different session identifier; continuity was not established"
        )
    return None


class Adapter(Protocol):
    name: str
    default_command: str

    def preflight(
        self,
        command: str,
        env: tuple[tuple[str, str], ...],
        cancel: threading.Event | None = None,
    ) -> str | None:
        """Return why sessions would not be clean or could not start, without using quota."""
        ...

    def run(self, session: Session) -> ReviewOutcome: ...


@dataclass(frozen=True)
class Finished:
    exit_status: int | None  # None after a timeout
    stdout: str
    stderr: str
    duration_seconds: float
    cancelled: bool = False


def run_process(
    arguments: list[str],
    prompt: str,
    timeout: float,
    cwd: Path,
    env: tuple[tuple[str, str], ...] = (),
    cancel: threading.Event | None = None,
) -> Finished:
    """Reap a fresh process group on timeout or cancellation of this invocation."""
    started = time.monotonic()
    if cancel is not None and cancel.is_set():
        return Finished(None, "", "", 0.0, cancelled=True)
    process = subprocess.Popen(
        arguments,
        cwd=cwd,
        env={**os.environ, **dict(env)},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    with _ACTIVE_LOCK:
        _ACTIVE.add(process.pid)
    cancelled = False
    try:
        pending_input: bytes | None = prompt.encode("utf-8")
        while True:
            cancelled = cancel is not None and cancel.is_set()
            remaining = timeout - (time.monotonic() - started)
            if cancelled or remaining <= 0:
                # Helpers share the group, so stopping the parent alone is insufficient.
                _kill(process.pid)
                stdout, stderr = process.communicate()
                status: int | None = None
                break
            try:
                stdout, stderr = process.communicate(pending_input, timeout=min(0.1, remaining))
                status = process.returncode
                break
            except subprocess.TimeoutExpired:
                # communicate retains partial output and finishes sending stdin on retry.
                pending_input = None
    except BaseException:
        _kill(process.pid)
        process.communicate()
        raise
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE.discard(process.pid)
    return Finished(
        status,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
        time.monotonic() - started,
        cancelled,
    )


def _kill(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # already gone


def stop_all() -> None:
    """Kill every running session; used when the operator interrupts a round.

    Sessions run in their own process groups, so an interrupt would not reach them.
    """
    with _ACTIVE_LOCK:
        active = list(_ACTIVE)
    for pid in active:
        _kill(pid)


def failure_of(finished: Finished, timeout: float) -> str | None:
    if finished.cancelled:
        return "cancelled by the researcher; the process group was killed and reaped"
    if finished.exit_status is None:
        return f"timed out after {timeout:g} s; the process group was killed"
    if finished.exit_status != 0:
        tail = finished.stderr.strip().splitlines()[-1:] or ["no stderr"]
        return f"exit status {finished.exit_status}: {tail[0][:300]}"
    return None


def diagnostics(finished: Finished) -> str:
    text = f"exit status: {finished.exit_status}\n--- stderr ---\n{finished.stderr}"
    text += f"\n--- stdout ---\n{finished.stdout}"
    return text[-LOG_LIMIT:]


def in_empty_directory[T](action: Callable[[Path], T]) -> T:
    """Run in a fresh empty directory, so no project instruction file is discovered."""
    with tempfile.TemporaryDirectory(prefix="toulmin-session-") as directory:
        return action(Path(directory))


def archive_tool_trace(session: Session, finished: Finished) -> None:
    """Keep complete tool events outside the model's writable scratch directory.

    A persistent workspace can span invocations; its caller supplies a distinct
    archive_directory each time. These files preserve successful and failed tool use.
    """
    if session.workspace is not None:
        parent = session.archive_directory or session.workspace.parent
        write_atomic(parent / "tool-events.jsonl", finished.stdout.encode("utf-8"))
        write_atomic(parent / "tool-stderr.log", finished.stderr.encode("utf-8"))
