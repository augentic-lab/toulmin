"""L1 material digests for shared resources: ``file`` and ``tree-v1`` (contract section 6).

A digest proves byte identity of what was registered or pinned, never its correctness.
"""

import hashlib
import os
import stat
from pathlib import Path


def file_sha256(path: Path) -> str:
    """Hash a regular file without following a link or blocking on a FIFO."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"{path}: expected a regular file")
        checksum = hashlib.sha256()
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            while data := stream.read(1 << 16):
                checksum.update(data)
        return checksum.hexdigest()
    finally:
        os.close(descriptor)


def tree_v1(path: Path) -> str:
    """SHA-256 over sorted ``<sha256>  <relative path>\\n`` lines of every regular file."""
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"{path}: expected a directory")
    lines: list[tuple[bytes, str]] = []
    for current, names, files in os.walk(path):
        base = Path(current)
        for name in names:
            if (base / name).is_symlink():
                raise ValueError(f"{base / name}: symlinks are not allowed in material")
        for name in files:
            child = base / name
            mode = child.lstat().st_mode
            if not stat.S_ISREG(mode):
                raise ValueError(f"{child}: only regular files are allowed in material")
            relative = child.relative_to(path).as_posix()
            lines.append((relative.encode(), f"{file_sha256(child)}  {relative}\n"))
    lines.sort()
    return hashlib.sha256("".join(line for _, line in lines).encode()).hexdigest()


def material_digest(path: Path, method: str) -> str:
    if method == "file":
        return file_sha256(path)
    if method == "tree-v1":
        return tree_v1(path)
    raise ValueError(f"{method}: no local digest for this method")
