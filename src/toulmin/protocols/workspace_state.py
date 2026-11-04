"""L2 read-only workspace state derived from files (docs/workspace-formats.md, 2.1 and 7.3).

Nothing here writes, repairs or initializes. The caller supplies the expected setup
files (path -> bytes) because templates belong to the CLI layer, not to L1/L2.
"""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from toulmin.core.atomic import digest
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError
from toulmin.core.identifiers import validate_project_name
from toulmin.core.inspection import marker_errors
from toulmin.core.project import validate_project
from toulmin.core.repository import Repository
from toulmin.core.workspace import CHARTER_FILE, Charter, validate_charter

LINK = ("CLAUDE.md", "AGENTS.md")
INIT_REMNANT = ".toulmin-init-"
JOURNAL = ".workspace-pending"
PACKET = re.compile(r"[0-9]{8}T[0-9]{6}Z-(?P<kind>proposal|project)-[0-9a-f]{32}")
SEAL = re.compile(rb"[0-9a-f]{64}\n")
UNEXPECTED_LIMIT = 10


class RootState(StrEnum):
    MISSING = "missing"
    EMPTY = "empty"
    WORKSPACE = "workspace"
    INCOMPLETE = "incomplete-init"
    LEGACY = "legacy"
    UNRELATED = "unrelated"


@dataclass(frozen=True)
class RootReport:
    root: Path
    state: RootState
    unexpected: tuple[str, ...] = ()
    remnants: tuple[str, ...] = ()


@dataclass(frozen=True)
class Child:
    name: str
    stage: str | None
    error: str | None = None


@dataclass(frozen=True)
class Proposal:
    path: str
    kind: str  # "change" or "creation"
    disposition: str  # pending, applied, rejected, superseded, incomplete, invalid


@dataclass(frozen=True)
class WorkspaceReport:
    root: RootReport
    charter: Charter | None
    children: tuple[Child, ...]
    proposals: tuple[Proposal, ...]
    resources: tuple[str, ...]
    notices: tuple[str, ...]
    errors: tuple[str, ...]


def _absolute(root: Path) -> Path:
    if ".." in root.parts:
        raise FormatError(f"{root}: root: '..' is forbidden")
    root = root.absolute()
    for part in (*reversed(root.parents), root):
        if part.is_symlink():
            raise FormatError(f"{part}: root: directory symlinks forbidden")
    if root.exists() and not root.is_dir():
        raise FormatError(f"{root}: root: expected a directory")
    return root


def classify_root(root: Path, setup: Mapping[str, bytes]) -> RootReport:
    """Classify a root without writing (contract section 2.1)."""
    root = _absolute(root)
    if not root.exists():
        return RootReport(root, RootState.MISSING)
    entries = sorted(path.name for path in root.iterdir() if path.name != ".git")
    remnants = tuple(name for name in entries if name.startswith(INIT_REMNANT))
    if not [name for name in entries if name not in remnants]:
        return RootReport(root, RootState.EMPTY, remnants=remnants)
    if os.path.lexists(root / CHARTER_FILE):
        return RootReport(root, RootState.WORKSPACE, remnants=remnants)
    signature = (
        (root / "AGENTS.md").is_file()
        and (root / "framework/formats.md").is_file()
        and (root / "projects").is_dir()
        and not (root / "projects").is_symlink()
    )
    if signature and any(path.name != ".gitkeep" for path in (root / "projects").iterdir()):
        return RootReport(root, RootState.LEGACY, remnants=remnants)
    unexpected = _unexpected(root, setup, remnants)
    if not unexpected:
        return RootReport(root, RootState.INCOMPLETE, remnants=remnants)
    if signature:
        # No projects: possibly an interrupted init whose templates were edited since.
        return RootReport(root, RootState.LEGACY, unexpected, remnants)
    return RootReport(root, RootState.UNRELATED, unexpected, remnants)


def _unexpected(
    root: Path, setup: Mapping[str, bytes], remnants: tuple[str, ...]
) -> tuple[str, ...]:
    """Entries that are not unmodified setup files (or their directories), up to a limit."""
    directories = {str(Path(path).parent) for path in setup} | {
        str(parent) for path in setup for parent in Path(path).parents
    }
    found: list[str] = []
    for current, names, files in os.walk(root):
        base = Path(current).relative_to(root)
        if base == Path("."):
            names[:] = [name for name in names if name != ".git" and name not in remnants]
            files = [name for name in files if name not in remnants]
        for name in sorted(names):
            relative = (base / name).as_posix()
            path = root / relative
            if path.is_symlink() or relative not in directories:
                found.append(relative)
        names[:] = [name for name in names if (base / name).as_posix() in directories]
        names[:] = [name for name in names if not (root / base / name).is_symlink()]
        for name in sorted(files):
            relative = (base / name).as_posix()
            path = root / relative
            if path.is_symlink():
                if (relative, os.readlink(path)) != LINK:
                    found.append(relative)
            elif relative not in setup or path.read_bytes() != setup[relative]:
                found.append(relative)
        if len(found) >= UNEXPECTED_LIMIT:
            break
    return tuple(found[:UNEXPECTED_LIMIT])


def project_hint(root: Path) -> Path | None:
    """The probable workbench when ``root`` lies inside ``<workbench>/projects/<name>``."""
    root = root.absolute()
    for candidate in (root, *root.parents):
        if (
            candidate.parent.name == "projects"
            and (candidate.parent.parent / "AGENTS.md").is_file()
        ):
            return candidate.parent.parent
    return None


def workspace_status(root: Path, setup: Mapping[str, bytes]) -> WorkspaceReport:
    """Read the workspace view: charter, children, proposals and resources, from files."""
    report = classify_root(root, setup)
    notices = [f"{name}: interrupted initialization remnant" for name in report.remnants]
    errors: list[str] = []
    if report.state not in {RootState.WORKSPACE, RootState.LEGACY}:
        return WorkspaceReport(report, None, (), (), (), tuple(notices), ())
    repository = Repository(report.root)
    charter = None
    if report.state == RootState.WORKSPACE:
        charter = _charter(repository, errors)
    else:
        notices.append("workspace state not configured; existing projects remain valid")
    journal = _journal(repository, errors)
    children = _children(repository, journal, notices, errors)
    proposals: tuple[Proposal, ...] = ()
    resources: tuple[str, ...] = ()
    if report.state == RootState.WORKSPACE:
        proposals = _proposals(repository, journal, errors)
        resources = _resources(repository, errors)
        _misplaced(repository, errors)
    return WorkspaceReport(
        report, charter, children, proposals, resources, tuple(notices), tuple(errors)
    )


def _charter(repository: Repository, errors: list[str]) -> Charter | None:
    try:
        path = repository.path(CHARTER_FILE, "file")
        content = path.read_bytes()
        document = decode(content, str(path))
        charter = validate_charter(document)
    except (OSError, ValueError) as error:
        errors.append(str(error))
        return None
    errors.extend(marker_errors(repository, None, document.body, str(path)))
    if charter.receipt is not None:
        try:
            repository.path(charter.receipt, "file")
        except (OSError, ValueError) as error:
            errors.append(f"{path}: charter_receipt: {error}")
    if charter.last_handoff is not None:
        try:
            repository.path(f"sessions/{charter.last_handoff}", "file")
        except (OSError, ValueError) as error:
            errors.append(f"{path}: last_handoff: {error}")
    return charter


def _journal(repository: Repository, errors: list[str]) -> dict[str, str] | None:
    """Return the pending journal's intent fields; its presence alone makes data incomplete."""
    path = repository.root / JOURNAL
    if not os.path.lexists(path):
        return None
    intent: dict[str, str] = {}
    try:
        header = decode(repository.path(f"{JOURNAL}/intent.md", "file").read_bytes()).header
        intent = {key: value for key, value in header.items() if isinstance(value, str)}
    except (OSError, ValueError) as error:
        errors.append(f"{path}: unreadable publication journal: {error}")
        return intent
    errors.append(
        f"{path}: incomplete {intent.get('operation', 'publication')} for "
        f"{intent.get('record', 'an unknown record')}; rerun that operation to recover"
    )
    return intent


def _children(
    repository: Repository,
    journal: dict[str, str] | None,
    notices: list[str],
    errors: list[str],
) -> tuple[Child, ...]:
    try:
        folder = repository.path("projects", "directory")
    except (OSError, ValueError) as error:
        errors.append(str(error))
        return ()
    staging = (journal or {}).get("staging")
    children = []
    for path in sorted(folder.iterdir()):
        relative = f"projects/{path.name}"
        if path.name == ".gitkeep":
            continue
        if path.name.startswith("."):
            if relative != staging:
                notices.append(f"{relative}: dot-prefixed entry ignored (not a project)")
            continue
        if path.is_symlink() or not path.is_dir():
            errors.append(f"{relative}: expected a project directory, not a link or file")
            continue
        try:
            validate_project_name(path.name)
            charter_path = repository.path(f"{relative}/PROJECT.md", "file")
            document = decode(charter_path.read_bytes(), str(charter_path))
            validate_project(document, path.name)
            children.append(Child(path.name, document.header["stage"]))
        except (OSError, ValueError) as error:
            errors.append(str(error))
            children.append(Child(path.name, None, str(error)))
    return tuple(children)


def _proposals(
    repository: Repository, journal: dict[str, str] | None, errors: list[str]
) -> tuple[Proposal, ...]:
    """Derive dispositions from seals, receipts, successors and the journal (7.3).

    Packet schemas are validated by the operations that consume them; status checks
    only what determines the disposition, and never repairs a record.
    """
    folder = repository.root / "runs"
    if not folder.is_dir() or folder.is_symlink():
        return ()
    seals: dict[str, str | None] = {}
    successors: dict[str, str] = {}
    kinds: dict[str, str] = {}
    for path in sorted(folder.iterdir()):
        match = PACKET.fullmatch(path.name)
        if match is None or not path.is_dir() or path.is_symlink():
            continue
        relative = f"runs/{path.name}"
        kinds[relative] = "change" if match["kind"] == "proposal" else "creation"
        seals[relative] = None
        try:
            sealed = repository.path(f"{relative}/seal", "file").read_bytes()
            packet = repository.path(f"{relative}/packet.md", "file").read_bytes()
            if not SEAL.fullmatch(sealed) or sealed.decode().strip() != digest(packet):
                raise ValueError("seal does not match packet.md (changed after preview)")
            seals[relative] = sealed.decode().strip()
            predecessor = decode(packet, f"{relative}/packet.md").header.get("supersedes")
            if isinstance(predecessor, str):
                successors[predecessor.removesuffix("/packet.md")] = relative
        except (OSError, ValueError) as error:
            errors.append(f"{relative}: invalid proposal: {error}")
    pending_record = (journal or {}).get("record", "").removesuffix("/packet.md")
    result = []
    for relative, seal in seals.items():
        disposition = "pending"
        if seal is None:
            disposition = "invalid"
        elif relative == pending_record:
            disposition = "incomplete"
        elif os.path.lexists(repository.root / relative / "receipt.md"):
            disposition = _receipt(repository, relative, seal, errors)
        elif relative in successors:
            disposition = "superseded"
        result.append(Proposal(relative, kinds[relative], disposition))
    return tuple(result)


def _receipt(repository: Repository, relative: str, seal: str, errors: list[str]) -> str:
    try:
        path = repository.path(f"{relative}/receipt.md", "file")
        header = decode(path.read_bytes(), str(path)).header
        if (
            header.get("kind") != "workspace-receipt"
            or header.get("record") != f"{relative}/packet.md"
            or header.get("record_sha256") != seal
            or header.get("disposition") not in {"applied", "rejected"}
        ):
            raise ValueError("receipt does not dispose of this sealed packet")
        return str(header["disposition"])
    except (OSError, ValueError) as error:
        errors.append(f"{relative}: invalid receipt: {error}")
        return "invalid"


def _resources(repository: Repository, errors: list[str]) -> tuple[str, ...]:
    folder = repository.root / "shared/resources"
    if not folder.exists():
        return ()
    if folder.is_symlink() or not folder.is_dir():
        errors.append(f"{folder}: expected a directory")
        return ()
    names = []
    for path in sorted(folder.glob("*.md")):
        if path.is_symlink() or not path.is_file():
            errors.append(f"shared/resources/{path.name}: expected a regular file")
            continue
        names.append(path.stem)
    return tuple(names)


def _misplaced(repository: Repository, errors: list[str]) -> None:
    folder = repository.root / "runs"
    if folder.is_dir():
        for path in sorted(folder.glob("R-*.md")):
            errors.append(f"runs/{path.name}: misplaced Run object; workspace records have no IDs")
