"""L1 read-only inspection of project files and direct references."""

import re
from dataclasses import dataclass

from toulmin.core.documents import DIRECTORIES, Document
from toulmin.core.handoffs import validate_applied
from toulmin.core.identifiers import ObjectId, ObjectKind, ObjectRef
from toulmin.core.project import validate_project
from toulmin.core.repository import Repository
from toulmin.core.schema import validate


@dataclass(frozen=True)
class ProjectSnapshot:
    charter: Document | None
    objects: tuple[Document, ...]
    errors: tuple[str, ...]


def _brief_errors(repository: Repository, project: str) -> list[str]:
    errors: list[str] = []
    path = repository.path(f"projects/{project}/brief.md", "file")
    try:
        content = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        return [f"{path}:1: encoding: expected UTF-8 ({error})"]
    if "\r" in content:
        errors.append(f"{path}:1: encoding: expected LF line endings")
    fence = ""
    for line_number, line in enumerate(content.splitlines(), 1):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if (
                marker
                and marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence)
                and not marker[2].strip()
            ):
                fence = ""
            continue
        if marker:
            fence = marker[1]
            continue
        if line.startswith(("    ", "\t")):
            continue
        position = 0
        while (start := line.find("[[", position)) != -1:
            end = line.find("]]", start + 2)
            field = f"{path}:{line_number}: reference"
            if end == -1:
                errors.append(f"{field}: unclosed [[object-reference]]")
                break
            value = line[start + 2 : end]
            try:
                repository.resolve(project, value)
            except (OSError, ValueError) as error:
                errors.append(f"{field}: [[{value}]]: {error}")
            position = end + 2
    return errors


def inspect_project(repository: Repository, project: str) -> ProjectSnapshot:
    errors: list[str] = []
    objects: list[Document] = []
    charter: Document | None = None
    # Without an identifiable charter, loading objects would repeat the same error.
    try:
        repository.project(project)
    except (OSError, ValueError) as error:
        return ProjectSnapshot(None, (), (str(error),))
    try:
        charter = repository.read(f"projects/{project}/PROJECT.md")
        validate_project(charter, project)
        for index, value in enumerate(charter.header["recent_decisions"]):
            try:
                repository.resolve(project, value)
            except (OSError, ValueError) as error:
                charter.fail(f"recent_decisions[{index}]", str(error))
        if charter.header["last_handoff"] is not None:
            try:
                handoff = repository.read(
                    f"projects/{project}/sessions/{charter.header['last_handoff']}"
                )
                validate_applied(repository, handoff, project)
            except (OSError, ValueError) as error:
                charter.fail("last_handoff", str(error))
    except (OSError, ValueError) as error:
        errors.append(str(error))
        charter = None

    seen: dict[ObjectId, str] = {}
    for kind, directory in DIRECTORIES.items():
        try:
            folder = repository.path(f"projects/{project}/{directory}", "directory")
            entries = sorted(folder.iterdir())
        except (OSError, ValueError) as error:
            errors.append(str(error))
            continue
        for path in entries:
            try:
                repository.path(str(path.relative_to(repository.root)))
                if path.name == ".gitkeep":
                    if not path.is_file():
                        raise ValueError(f"{path}: expected regular .gitkeep file")
                    continue
                if path.is_dir() and kind == ObjectKind.RUN and path.suffix != ".md":
                    continue  # Raw outputs and drafts are deliberately opaque.
                if path.suffix != ".md" or not path.is_file():
                    raise ValueError(f"{path}: expected one Markdown object per file")
                doc = repository.read(str(path.relative_to(repository.root)))
                validate(doc)
                object_id = doc.object_id
                if object_id in seen:
                    doc.fail("id", f"duplicate ID {object_id}; also in {seen[object_id]}")
                seen[object_id] = str(path)
                if object_id.kind != kind or path.name != f"{object_id}.md":
                    doc.fail("id", "ID does not match filename or directory")
                repository.validate_links(doc, project)
                objects.append(doc)
            except (OSError, ValueError) as error:
                errors.append(str(error))
    try:
        errors.extend(_brief_errors(repository, project))
    except (OSError, ValueError) as error:
        errors.append(str(error))
    lock = repository.root / "projects" / project / ".toulmin-new.lock"
    if lock.exists() or lock.is_symlink():
        errors.append(
            f"{lock}: creation: active or interrupted writer; condition results incomplete"
        )
    pending = repository.root / "projects" / project / ".handoff-pending"
    if pending.exists() or pending.is_symlink():
        errors.append(f"{pending}: handoff: interrupted application requires explicit recovery")
    return ProjectSnapshot(charter, tuple(objects), tuple(sorted(set(errors))))


def local_target(document: Document, project: str) -> ObjectId | None:
    reference = ObjectRef.parse(document.header["target"])
    return reference.object_id if reference.project in {None, project} else None
