"""R8 B4: deterministic checks in disposable clones, with bounded captured output."""

import os
import platform
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from toulmin.adapters.base import run_process
from toulmin.core.documents import FormatError
from toulmin.core.verification import STREAM_LIMIT, CheckResult


def _capture(stream: BinaryIO) -> tuple[str, bool]:
    size = stream.seek(0, os.SEEK_END)
    stream.seek(0)
    data = stream.read(STREAM_LIMIT).decode("utf-8", errors="replace")
    # Replacement characters can expand malformed bytes; bound the archived UTF-8 too.
    encoded = data.encode()
    return encoded[:STREAM_LIMIT].decode("utf-8", errors="ignore"), (
        size > STREAM_LIMIT or len(encoded) > STREAM_LIMIT
    )


def _kill(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # the group already ended
    process.wait()


def run_check(command: str, clone: Path, timeout: float) -> CheckResult:
    started = time.monotonic()
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(
                ["sh", "-c", command],
                cwd=clone,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
        except (OSError, ValueError) as error:
            return CheckResult(command, 126, time.monotonic() - started, "", str(error))
        try:
            try:
                status: int | None = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                _kill(process)
                status = None
        except BaseException:
            _kill(process)
            raise
        out, out_cut = _capture(stdout)
        err, err_cut = _capture(stderr)
        return CheckResult(command, status, time.monotonic() - started, out, err, out_cut, err_cut)


def environment(repo: str, head: str) -> bytes:
    result = run_process(["git", "--version"], "", 15, Path(tempfile.gettempdir()))
    if result.exit_status != 0:
        raise FormatError(f"git version unavailable: {result.stderr}")
    return (
        f"OS: {platform.platform()}\nPython: {sys.version}\nGit: {result.stdout.strip()}\n"
        f"Repository: {repo}\nHead commit: {head}\n"
        "Execution: local user, without network isolation\n"
    ).encode()


def run_checks(
    workspace: Path,
    repo: str,
    head: str,
    checks: tuple[str, ...],
    timeout: float,
    report: Callable[[tuple[CheckResult, ...]], None],
) -> tuple[CheckResult, ...]:
    """One clean clone per attempt; a retry after a partial attempt starts clean again."""
    parent = Path(tempfile.gettempdir()).resolve()
    if parent.is_relative_to(workspace.resolve()) or parent.is_relative_to(Path(repo).resolve()):
        parent = Path("/tmp")
    with tempfile.TemporaryDirectory(prefix="toulmin-verify-", dir=parent) as scratch:
        clone = Path(scratch) / "clone"
        for argv in (
            ["git", "clone", "--quiet", "--no-hardlinks", repo, str(clone)],
            ["git", "-C", str(clone), "checkout", "--quiet", "--detach", head],
        ):
            result = run_process(argv, "", 120, Path(scratch))
            if result.exit_status != 0:
                raise FormatError(f"fresh verification clone: {result.stderr or result.stdout}")
        results = []
        for command in checks:
            results.append(run_check(command, clone, timeout))
            report(tuple(results))
        return tuple(results)
