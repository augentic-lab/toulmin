"""Read-only local source inspection; external Git commands stay outside L1/L2."""

import fnmatch
import json
import os
import stat
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import ExitStack
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
    read_source_catalog,
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
    project: str | None
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


def inspect_source(root: Path, path: Path, *, _deadline: float | None = None) -> SourceInspection:
    path = validate_directory(root, path)
    top = _git(path, "rev-parse", "--show-toplevel")
    if _deadline is not None and os.path.lexists(path / ".git") and not top:
        raise FormatError(f"{path}: Git discovery unavailable; never reinterpret it as a directory")
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

    def expired() -> bool:
        return _deadline is not None and time.monotonic() >= _deadline

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
            if visited > MAX_FILES * 8 or expired():
                truncated = True
                return
            try:
                with os.scandir(directory) as entries:
                    selected = list(islice(entries, MAX_FILES * 8 + 1))
            except OSError:
                truncated = True
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
        if examined > MAX_FILES * 8 or len(files) >= MAX_FILES or expired():
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
            truncated = True
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


def resolve_source(root: Path, project: str | None, source_id: str) -> ResolvedSource:
    from toulmin.core.scope import Scope

    catalog = read_source_catalog(root)
    association = next(
        (item for item in catalog.associated(Scope(project)) if item.source == source_id), None
    )
    if association is None:
        raise FormatError(f"{source_id}: no such source associated with {Scope(project).display}")
    definition = catalog.definition(source_id)
    repo = Repository(root)
    bindings = (
        parse_bindings(repo.path(LOCAL, "file").read_bytes()) if repo.path(LOCAL).exists() else {}
    )
    if source_id not in bindings:
        raise FormatError(
            f"{source_id}: local path missing; run toulmin "
            f"source bind {source_id} PATH --root {root}"
        )
    name, filesystem = bindings[source_id]
    path = validate_directory(root, Path(name))
    if filesystem_identity(path) != filesystem:
        raise FormatError(f"{source_id}: source directory was replaced; explicitly bind it again")
    if definition.kind == "git":
        top = _git(path, "rev-parse", "--show-toplevel")
        roots = _git(path, "rev-list", "--max-parents=0", "HEAD")
        if (
            not top
            or Path(top).resolve() != path
            or not roots
            or "git:" + digest(roots.encode()) != definition.identity
        ):
            raise FormatError(
                f"{source_id}: repository identity changed; bind the original repository"
            )
    return ResolvedSource(
        source_id,
        project,
        definition.kind,
        association.role,
        path,
        digest(repo.path(CATALOG, "file").read_bytes()),
        definition.identity,
    )


def resolve_working_source(root: Path, project: str | None) -> ResolvedSource | None:
    from toulmin.core.scope import Scope

    catalog = read_source_catalog(root)
    associated = catalog.associated(Scope(project))
    working = next((item for item in associated if item.role == "working"), None)
    if working is None and associated and catalog.schema_version == 2:
        scope = "--workspace" if project is None else project
        raise SourceSelectionRequired(
            f"{Scope(project).display}: references have no working selection; "
            f"propose toulmin source working {scope} ID --root {root}"
        )
    return resolve_source(root, project, working.source) if working else None


class SourceSelectionRequired(FormatError):
    """Invocation requires explicit selection, reported as exit 2 at the CLI boundary."""


load_primary_source = resolve_working_source


def resolve_source_repo(root: Path, project: str, source: str) -> Path:
    return resolve_source(root, project, source).path


def bind_source(
    root: Path, source_id: str, path: Path, *, confirmed: bool = True
) -> ResolvedSource:
    from toulmin.core.scope import Scope
    from toulmin.core.workspace_journal import pending

    repo = Repository(root)
    catalog = read_source_catalog(root)
    definition = catalog.definition(source_id)
    inspected = inspect_source(root, path)
    if (inspected.kind, inspected.identity) != (definition.kind, definition.identity):
        raise FormatError(
            f"{source_id}: source identity mismatch; original directory/repository "
            f"required; register "
            f"a genuinely distinct edited source after review if original anchors "
            f"cannot be restored"
        )
    target = repo.path(LOCAL)
    before = target.read_bytes() if target.exists() else None
    bindings = parse_bindings(before) if before is not None else {}
    checkout_conflicts(bindings, source_id, inspected.path, inspected.filesystem)
    selected = next(
        (item.scope for item in catalog.associations if item.source == source_id), Scope()
    )
    result = ResolvedSource(
        source_id,
        selected.project,
        definition.kind,
        "reference",
        inspected.path,
        digest(repo.path(CATALOG, "file").read_bytes()),
        definition.identity,
    )
    if not confirmed:
        return result
    lock_bindings = tuple(
        [item for item in (bindings.get(source_id),) if item is not None]
        + [(str(inspected.path), inspected.filesystem)]
    )
    with checkout_locks(lock_bindings), handoff_mutex(repo.root):
        if pending(repo):
            raise FormatError("workspace journal pending; finish the recorded operation first")
        if (target.read_bytes() if target.exists() else None) != before or read_source_catalog(
            root
        ) != catalog:
            raise FormatError("source mapping/catalog changed during bind preview; retry")
        current = inspect_source(root, path)
        if (current.kind, current.identity, current.filesystem) != (
            inspected.kind,
            inspected.identity,
            inspected.filesystem,
        ):
            raise FormatError("source identity changed during bind; retry")
        _bound_writer_guard(repo, lock_bindings, all_profiles=catalog.schema_version == 2)
        bindings[source_id] = (str(inspected.path), inspected.filesystem)
        write_atomic(target, render_bindings(bindings), replace=target.exists())
    return result


def _bound_writer_guard(
    repository: Repository,
    checkouts: tuple[tuple[str, str], ...],
    *,
    all_profiles: bool,
) -> None:
    """Reconcile only the selected source's old/new checkout while their locks are held."""
    from toulmin.adapters.aoe import AoEClient, AoEError

    paths = {Path(name).resolve() for name, _ in checkouts}
    identities = {identity for _, identity in checkouts}
    if all_profiles:
        try:
            sessions = AoEClient().list_all_sessions()
            conflicts = []
            for profile, session in sessions:
                if session.state in {"archived", "trashed"}:
                    continue
                # Unknown lifecycle is not proof that a matching checkout is idle.
                same = session.path.resolve() in paths
                if not same and session.path.is_dir():
                    same = filesystem_identity(session.path) in identities
                if same:
                    conflicts.append(f"{profile}/{session.id}")
        except (AoEError, OSError, ValueError) as error:
            raise FormatError(
                f"Cannot verify all-profile checkout writers; rebind refused: {error}"
            ) from error
        if conflicts:
            raise FormatError(
                "Selected source checkout has a possible native writer: "
                + ", ".join(conflicts)
                + "; archive it before binding. Other sources are unchanged"
            )
        return
    # Legacy project-only operations keep their existing adapter boundary and data format.
    candidates = [
        repository.root / ".aoe/binding.json",
        *repository.root.glob("projects/*/.aoe/binding.json"),
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        relative = candidate.relative_to(repository.root).as_posix()
        raw = json.loads(repository.path(relative, "file").read_bytes())
        if raw.get("cwd") in {str(path) for path in paths} and raw.get("session_id"):
            session = AoEClient(raw["profile"]).show(raw["session_id"])
            if session.state == "live":
                raise FormatError(
                    f"{relative}: live native writer {session.id}; archive it before binding"
                )


def inspect_source_v2(
    root: Path, path: Path, *, observed_at: str | None = None, identity: str | None = None
) -> SourceInspection:
    """Version observations keep the v1 logical identity algorithm unchanged."""
    from dataclasses import replace
    from datetime import UTC, datetime

    from toulmin.core.schema import utc_text
    from toulmin.core.workspace_onboarding import LIMITS, MAX_BYTES, canonical, inventory

    # The v1 reader/identity path keeps its historical default. New observations
    # additionally bound traversal time; each read-only Git command has its own timeout.
    inspected = inspect_source(root, path, _deadline=time.monotonic() + 8)
    value = json.loads(inspected.inventory)
    if value["kind"] == "git" and (value["head"] is None or value["status"] is None):
        raise FormatError(f"{path}: Git observation unavailable; inspect locally and retry")
    value.update(
        schema_version=2,
        observed_at=observed_at or utc_text(datetime.now(UTC)),
        identity=identity or inspected.identity,
        limits=LIMITS,
        exclusions=[
            "credential filename patterns, symlinks, ignored/generated material",
            "binary/oversize files are not read; no scripts or checks executed",
            "traversal budget: 8 seconds; Git commands: 8 seconds and bounded output each",
        ],
    )
    if any("\ufffd" in item.get("text", "") for item in value["files"]):
        value["exclusions"].append("Selected UTF-8 display is lossy; hashes cover original bytes")
    raw = canonical(value)
    if len(raw) > MAX_BYTES:
        raise FormatError(
            f"{path}: escaped inventory exceeds 1,000,000 bytes; narrow inspected material"
        )
    inventory(raw, str(path))
    return replace(inspected, inventory=raw)


def checkout_conflicts(
    bindings: dict[str, tuple[str, str]], source_id: str, path: Path, filesystem: str
) -> None:
    for other, (saved_path, saved_filesystem) in bindings.items():
        if other == source_id:
            continue
        saved = Path(saved_path)
        if (
            saved == path
            or saved.is_relative_to(path)
            or path.is_relative_to(saved)
            or saved_filesystem == filesystem
        ):
            raise FormatError(
                f"{source_id}: checkout conflicts with {other} at {saved}; "
                f"reuse its ID or choose a distinct non-overlapping checkout"
            )


def checkout_locks(bindings: tuple[tuple[str, str], ...]) -> ExitStack:
    """Canonical path then saved filesystem locks, all before the root writer lock."""
    from contextlib import ExitStack

    stack = ExitStack()
    try:
        paths = sorted(set(bindings))
        for path in sorted({name for name, _ in paths}):
            stack.enter_context(handoff_mutex(Path(path) / ".toulmin-native-writer"))
        for identity in sorted({identity for _, identity in paths}):
            stack.enter_context(
                handoff_mutex(Path(tempfile.gettempdir()) / ("toulmin-checkout-" + identity))
            )
        return stack
    except BaseException:
        stack.close()
        raise


def scope_source_reports(root: Path, project: str | None) -> tuple[str, ...]:
    """Local availability and freshness advice; observations never revise confirmed records."""
    from toulmin.core.scope import Scope
    from toulmin.core.sources import read_source_catalog
    from toulmin.core.workspace_onboarding import inventory, overview
    from toulmin.protocols.workspace_onboarding import confirmed_overview

    catalog = read_source_catalog(root)
    pins = {}
    if project is None and (raw := confirmed_overview(root)) is not None:
        pins = {pin["source"]: pin for pin in overview(raw, "overview.md")["sources"]}
    lines = []
    for association in catalog.associated(Scope(project)):
        source_id = association.source
        try:
            resolved = resolve_source(root, project, source_id)
            detail = f"{source_id} | {association.role} | available: {resolved.path}"
            pin = pins.get(source_id)
            if pin is not None:
                definition = catalog.definition(source_id)
                previous = inventory(
                    Repository(root).path(pin["snapshot"], "file").read_bytes(), pin["snapshot"]
                )
                current = inspect_source_v2(
                    root,
                    resolved.path,
                    observed_at=previous["observed_at"],
                    identity=definition.identity if definition.kind == "directory" else None,
                )
                observed = inventory(current.inventory, source_id)
                changed = any(
                    previous[key] != observed[key]
                    for key in ("identity", "head", "status", "files", "truncated", "read_bytes")
                )
                detail += (
                    " | changed since confirmed snapshot; consider a reviewed "
                    "understanding checkpoint"
                    if changed
                    else " | matches bounded confirmed snapshot (not runtime verification)"
                )
            else:
                detail += " | no confirmed shared snapshot"
            lines.append(detail)
        except (OSError, ValueError) as error:
            lines.append(f"{source_id} | {association.role} | unavailable: {error}")
    return tuple(lines)
