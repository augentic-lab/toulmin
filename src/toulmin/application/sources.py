"""Read-only local source inspection; external Git commands stay outside L1/L2."""

import fnmatch
import json
import os
import stat
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import islice
from pathlib import Path

from toulmin.core.atomic import digest, handoff_mutex, write_atomic
from toulmin.core.documents import FormatError
from toulmin.core.repository import Repository
from toulmin.core.sources import (
    CATALOG,
    LOCAL,
    parse_bindings,
    read_catalog,
    render_bindings,
)

MAX_FILES = 400
MAX_READ_BYTES = 512_000
MAX_FILE_BYTES = 32_000
SKIP = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".ssh",
    ".aws",
    ".gnupg",
    "build",
    "dist",
}
TEXT_SUFFIXES = {
    ".md",
    ".rst",
    ".txt",
    ".toml",
    ".py",
    ".c",
    ".h",
    ".rs",
    ".go",
    ".json",
    ".yaml",
    ".yml",
}
SENSITIVE = (
    ".env*",
    "*secret*",
    "*credential*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    ".npmrc",
    ".netrc",
    ".pypirc",
    "id_rsa*",
    "id_ed25519*",
    "*token*",
)


@dataclass(frozen=True)
class ResolvedSource:
    source_id: str
    project: str
    kind: str
    role: str
    path: Path
    version: str
    identity: str


@dataclass(frozen=True)
class SourceInspection:
    path: Path
    kind: str
    identity: str
    filesystem: str
    inventory: bytes


def _git(path: Path, *args: str) -> str | None:
    try:
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(
                [
                    "git",
                    "-c",
                    "core.fsmonitor=false",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-C",
                    str(path),
                    *args,
                ],
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=8,
                check=False,
                env={
                    **os.environ,
                    "GIT_OPTIONAL_LOCKS": "0",
                    "GIT_TERMINAL_PROMPT": "0",
                    "GIT_NO_LAZY_FETCH": "1",
                },
            )
            output.seek(0)
            data = output.read(2_000_001)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if len(data) > 2_000_000:
        raise FormatError("Git source inventory exceeds bounded command-output limit")
    return data.decode("utf-8", "replace").strip() if result.returncode == 0 else None


def validate_directory(root: Path, path: Path) -> Path:
    # Refuse links in every component, even when resolution would land outside W.
    path = path.expanduser().absolute()
    if ".." in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise FormatError(f"{path}: source directory symlinks and '..' are forbidden")
    if not path.is_dir():
        raise FormatError(f"{path}: expected an existing source directory")
    workspace = root.absolute()
    if path == workspace or path.is_relative_to(workspace) or workspace.is_relative_to(path):
        raise FormatError(
            "source and research workspace must be separate, non-overlapping directories"
        )
    return path


def filesystem_identity(path: Path) -> str:
    info = path.stat()
    return f"{info.st_dev}:{info.st_ino}"


def _sensitive(name: str) -> bool:
    return any(fnmatch.fnmatch(name.lower(), pattern) for pattern in SENSITIVE)


def inspect_source(root: Path, path: Path) -> SourceInspection:
    path = validate_directory(root, path)
    top = _git(path, "rev-parse", "--show-toplevel")
    if top and Path(top).resolve() != path:
        raise FormatError(f"{path}: select the Git repository root {top}")
    kind = "git" if top else "directory"
    roots = _git(path, "rev-list", "--max-parents=0", "HEAD") if top else None
    if top and not roots:
        raise FormatError("Git sources need at least one commit for a stable repository identity")
    identity = "git:" + digest((roots or "").encode()) if top else ""
    git_files = (
        _git(path, "ls-files", "--cached", "--others", "--exclude-standard", "-z") if top else None
    )
    # Keep traversal bounded independently of the number of source files.
    candidates = git_files.split("\0") if git_files is not None else None
    files: list[dict[str, str | int]] = []
    read_bytes = 0
    examined = 0
    truncated = False
    anchors = []

    def ignored(candidate: Path) -> bool:
        excluded = False
        for parent in (
            path,
            *reversed([p for p in candidate.relative_to(path).parents if p != Path(".")]),
        ):
            folder = parent if parent.is_absolute() else path / parent
            rules = folder / ".gitignore"
            if not rules.is_file() or rules.is_symlink() or rules.stat().st_size > MAX_FILE_BYTES:
                continue
            try:
                patterns = rules.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError):
                continue
            relative = candidate.relative_to(folder).as_posix()
            for pattern in patterns:
                pattern = pattern.strip()
                if not pattern or pattern.startswith("#"):
                    continue
                include = pattern.startswith("!")
                pattern = pattern.removeprefix("!").removeprefix("/").rstrip("/")
                if fnmatch.fnmatch(relative, pattern) or (
                    "/" not in pattern and fnmatch.fnmatch(candidate.name, pattern)
                ):
                    excluded = not include
        return excluded

    def walk_files() -> Iterator[Path]:
        nonlocal truncated
        visited = 0
        directories = [path]
        while directories:
            directory = directories.pop()
            visited += 1
            if visited > MAX_FILES * 8:
                truncated = True
                return
            try:
                with os.scandir(directory) as entries:
                    selected = list(islice(entries, MAX_FILES * 8 + 1))
            except OSError:
                continue
            if len(selected) > MAX_FILES * 8:
                truncated = True
                selected = selected[: MAX_FILES * 8]
            for entry in sorted(selected, key=lambda e: e.name):
                if (
                    entry.name in SKIP
                    or _sensitive(entry.name)
                    or entry.is_symlink()
                    or ignored(Path(entry.path))
                ):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    directories.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    yield Path(entry.path)

    iterator = (
        iter(path / name for name in candidates if name) if candidates is not None else walk_files()
    )
    for candidate in iterator:
        examined += 1
        if examined > MAX_FILES * 8 or len(files) >= MAX_FILES:
            truncated = True
            break
        relative = candidate.relative_to(path)
        if any(part in SKIP or _sensitive(part) for part in relative.parts):
            continue
        if any(p.is_symlink() for p in (candidate, *candidate.parents) if p.is_relative_to(path)):
            continue
        try:
            info = candidate.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                continue
            item: dict[str, str | int] = {"path": relative.as_posix(), "bytes": info.st_size}
            if (
                (
                    candidate.suffix.lower() in TEXT_SUFFIXES
                    or candidate.name in {"README", "Makefile", "LICENSE"}
                )
                and info.st_size <= MAX_FILE_BYTES
                and read_bytes + info.st_size <= MAX_READ_BYTES
            ):
                # O_NOFOLLOW closes the final-component symlink race.
                fd = os.open(candidate, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, "rb") as stream:
                    data = stream.read(MAX_FILE_BYTES + 1)
                if len(data) <= MAX_FILE_BYTES and b"\0" not in data:
                    item["sha256"] = digest(data)
                    item["text"] = data.decode("utf-8", "replace")
                    read_bytes += len(data)
                    anchors.append((relative.as_posix(), digest(data)))
            files.append(item)
        except OSError:
            continue
    if not identity:
        # Content identity is checked on an explicit rebind, not on ordinary opens.
        identity = "directory:" + digest(json.dumps(sorted(anchors), ensure_ascii=True).encode())
    inventory = (
        json.dumps(
            {
                "schema_version": 1,
                "kind": kind,
                "identity": identity,
                "head": _git(path, "rev-parse", "HEAD") if top else None,
                "status": _git(path, "status", "--porcelain=v1", "--untracked-files=no")
                if top
                else None,
                "files": files,
                "truncated": truncated,
                "read_bytes": read_bytes,
                "limits": {"files": MAX_FILES, "bytes": MAX_READ_BYTES},
                "coverage": "bounded read-only inventory; omissions are not evidence of absence",
            },
            indent=2,
            ensure_ascii=True,
        ).encode()
        + b"\n"
    )
    return SourceInspection(path, kind, identity, filesystem_identity(path), inventory)


def resolve_source(root: Path, project: str, source_id: str) -> ResolvedSource:
    sources = read_catalog(root)
    source = next((s for s in sources if s.source_id == source_id and s.project == project), None)
    if source is None:
        raise FormatError(f"{source_id}: no such source associated with project {project}")
    repo = Repository(root)
    bindings = (
        parse_bindings(repo.path(LOCAL, "file").read_bytes()) if repo.path(LOCAL).exists() else {}
    )
    if source_id not in bindings:
        raise FormatError(
            f"{source_id}: local path missing; run toulmin source bind "
            f"{source_id} PATH --root {root}"
        )
    name, filesystem = bindings[source_id]
    path = validate_directory(root, Path(name))
    if filesystem_identity(path) != filesystem:
        raise FormatError(f"{source_id}: source directory was replaced; explicitly bind it again")
    if source.kind == "git":
        roots = _git(path, "rev-list", "--max-parents=0", "HEAD")
        if not roots or "git:" + digest(roots.encode()) != source.identity:
            raise FormatError(
                f"{source_id}: repository identity changed; bind the original repository"
            )
    return ResolvedSource(
        source_id,
        project,
        source.kind,
        source.role,
        path,
        digest(repo.path(CATALOG, "file").read_bytes()),
        source.identity,
    )


def resolve_working_source(root: Path, project: str) -> ResolvedSource | None:
    source = next(
        (s for s in read_catalog(root) if s.project == project and s.role == "working"), None
    )
    return resolve_source(root, project, source.source_id) if source else None


load_primary_source = resolve_working_source


def resolve_source_repo(root: Path, project: str, source: str) -> Path:
    return resolve_source(root, project, source).path


def bind_source(root: Path, source_id: str, path: Path) -> ResolvedSource:
    repo = Repository(root)
    with handoff_mutex(repo.root):
        source = next((s for s in read_catalog(root) if s.source_id == source_id), None)
        if source is None:
            raise FormatError(f"{source_id}: no such source")
        inspected = inspect_source(root, path)
        if (inspected.kind, inspected.identity) != (source.kind, source.identity):
            raise FormatError(
                f"{source_id}: source identity mismatch; original directory/repository required"
            )
        target = repo.path(LOCAL)
        bindings = parse_bindings(target.read_bytes()) if target.exists() else {}
        bindings[source_id] = (str(inspected.path), inspected.filesystem)
        target.parent.mkdir(exist_ok=True)
        write_atomic(target, render_bindings(bindings), replace=target.exists())
    return resolve_source(root, source.project, source_id)
