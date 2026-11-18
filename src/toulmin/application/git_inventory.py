"""Bounded NUL-delimited Git filename enumeration; never materialize a whole tree."""

import os
import selectors
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from toulmin.core.documents import FormatError
from toulmin.core.sources import InspectionPolicy

MAX_CANDIDATES = 3_200
MAX_NAME_BYTES = 2_000_000
PATHSPEC_ENV = {
    "GIT_LITERAL_PATHSPECS",
    "GIT_GLOB_PATHSPECS",
    "GIT_NOGLOB_PATHSPECS",
    "GIT_ICASE_PATHSPECS",
}


@dataclass(frozen=True)
class Listing:
    paths: tuple[str, ...]
    truncated: bool


def selection_paths(path: Path, policy: InspectionPolicy | None) -> None:
    """Validate literal selections before Git sees them or initialization writes anything."""
    if policy is None:
        return
    for name in (*policy.include, *policy.exclude):
        target = path / name
        if any(p.is_symlink() for p in (target, *target.parents) if p.is_relative_to(path)):
            raise FormatError(f"{name}: inspection selections must not contain symlinks")
        if not target.exists() or not (target.is_file() or target.is_dir()):
            raise FormatError(f"{name}: inspection selection must name an existing file/directory")


def git_paths(path: Path, policy: InspectionPolicy | None, deadline: float) -> Listing:
    """Preserve include priority, bound all streams together, and reap each Git child."""
    names: list[str] = []
    seen: set[str] = set()
    byte_count = 0
    for prefix in policy.include if policy else (None,):
        if time.monotonic() >= deadline:
            return Listing(tuple(names), True)
        specs = [f":(literal){prefix}"] if prefix is not None else []
        specs += [f":(exclude,literal){p}" for p in policy.exclude] if policy else []
        command = [
            "git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(path),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            *specs,
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={
                # Invocation must retain literal policy meaning under user Git settings.
                **{key: value for key, value in os.environ.items() if key not in PATHSPEC_ENV},
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_NO_LAZY_FETCH": "1",
            },
        )
        assert process.stdout is not None
        buffer = b""
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        return Listing(tuple(names), True)
                    chunk = os.read(process.stdout.fileno(), 65_536)
                    if not chunk:
                        if buffer:
                            raise FormatError(
                                "Git filename inventory ended with an incomplete record"
                            )
                        break
                    byte_count += len(chunk)
                    if byte_count > MAX_NAME_BYTES:
                        return Listing(tuple(names), True)
                    buffer += chunk
                    while b"\0" in buffer:
                        raw, buffer = buffer.split(b"\0", 1)
                        if not raw:
                            continue
                        try:
                            name = raw.decode("utf-8")
                        except UnicodeDecodeError as error:
                            raise FormatError("Git filename is not portable UTF-8") from error
                        parts = PurePosixPath(name).parts
                        if (
                            name.startswith("/")
                            or ".." in parts
                            or "\\" in name
                            or any(ord(char) < 32 or ord(char) == 127 for char in name)
                        ):
                            raise FormatError("Git filename is not a safe portable relative path")
                        if name in seen:
                            continue
                        if len(names) == MAX_CANDIDATES:
                            return Listing(tuple(names), True)
                        seen.add(name)
                        names.append(name)
            if process.wait(timeout=max(deadline - time.monotonic(), 0.01)) != 0:
                raise FormatError("Git filename inventory failed; inspect locally and retry")
        except subprocess.TimeoutExpired:
            return Listing(tuple(names), True)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
    return Listing(tuple(names), False)
