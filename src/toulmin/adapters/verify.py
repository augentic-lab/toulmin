"""R8 B4: deterministic checks in disposable clones, with bounded captured output."""

import os
import platform
import shutil
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


def environment(repo: str, head: str, cwd: Path | None = None) -> bytes:
    context = cwd or Path(tempfile.gettempdir())
    result = run_process(["git", "--version"], "", 15, context)
    if result.exit_status != 0:
        raise FormatError(f"git version unavailable: {result.stderr}")
    # exec searches relative PATH entries from the child's cwd, which is the fresh clone.
    search = os.pathsep.join(
        str(context / entry) if not Path(entry).is_absolute() else entry
        for entry in os.get_exec_path()
    )
    shell = shutil.which("sh", path=search)
    path = os.environ.get("PATH", "not set")
    if shell is not None:
        # A shell can supply a default PATH when the parent has none. Record what sh sees,
        # without trying to resolve python or any other command contained in the checks.
        probe = run_process(["sh", "-c", 'printf "%s" "$PATH"'], "", 15, context)
        if probe.exit_status == 0:
            path = probe.stdout
        else:
            status = "timed out" if probe.exit_status is None else f"exited {probe.exit_status}"
            path = f"not reported (sh PATH probe {status})"
    return (
        f"OS: {platform.platform()}\nToulmin Python: {sys.version}\nGit: {result.stdout.strip()}\n"
        f"PATH: {path}\nShell (sh): {shell or 'not found on PATH'}\n"
        f"Repository: {repo}\nHead commit: {head}\n"
        "Execution: local user, without network isolation\n"
    ).encode()


def run_checks(
    workspace: Path,
    repo: str,
    head: str,
    checks: tuple[str, ...],
    timeout: float,
    report: Callable[[tuple[CheckResult, ...], bytes], None],
) -> tuple[tuple[CheckResult, ...], bytes]:
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
        env = environment(repo, head, clone)
        report((), env)
        results = []
        for command in checks:
            results.append(run_check(command, clone, timeout))
            report(tuple(results), env)
        return tuple(results), env
