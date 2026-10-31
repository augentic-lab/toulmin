"""Complete-file publication and a process-death-safe handoff writer mutex."""

import hashlib
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from toulmin.core.documents import FormatError


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_atomic(path: Path, data: bytes, *, replace: bool = False) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        raise FormatError("Durable handoff writes require POSIX directory synchronization")
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=".handoff-", suffix=".tmp", delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(data)
            if replace:
                os.fchmod(stream.fileno(), path.stat().st_mode & 0o7777)
            stream.flush()
            os.fsync(stream.fileno())
            if replace:
                os.replace(stream.name, path)
            else:
                os.link(stream.name, path)
        finally:
            temporary.unlink(missing_ok=True)
    sync_directory(path.parent)


@contextmanager
def handoff_mutex(project_path: Path) -> Iterator[None]:
    # Import lazily: pure models/protocols remain importable on any platform.
    try:
        import fcntl
    except ImportError as error:
        raise FormatError("Handoff application requires POSIX advisory locks") from error
    name = digest(str(project_path).encode())
    path = Path(tempfile.gettempdir()) / f"toulmin-handoff-{os.getuid()}-{name}.lock"
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise FormatError(f"{project_path}: another handoff writer holds the lock") from error
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)
