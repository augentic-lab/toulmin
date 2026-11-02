"""The adapter interface and a process runner with a hard timeout."""

import os
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

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


class Adapter(Protocol):
    name: str
    default_command: str

    def run(self, session: Session) -> ReviewOutcome: ...


@dataclass(frozen=True)
class Finished:
    exit_status: int | None  # None after a timeout
    stdout: str
    stderr: str
    duration_seconds: float


def run_process(arguments: list[str], prompt: str, timeout: float, cwd: Path) -> Finished:
    """Run with the prompt on stdin in a new process group; kill the group on timeout."""
    started = time.monotonic()
    process = subprocess.Popen(
        arguments,
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
    )
    with _ACTIVE_LOCK:
        _ACTIVE.add(process.pid)
    try:
        stdout, stderr = process.communicate(prompt, timeout=timeout)
        status: int | None = process.returncode
    except subprocess.TimeoutExpired:
        # Tool CLIs spawn helpers; kill the whole group so nothing keeps using quota.
        _kill(process.pid)
        stdout, stderr = process.communicate()
        status = None
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE.discard(process.pid)
    return Finished(status, stdout, stderr, time.monotonic() - started)


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
