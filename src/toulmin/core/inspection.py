"""L1 read-only inspection of project files and direct references."""

import re
from dataclasses import dataclass
from pathlib import Path

from toulmin.core.documents import DIRECTORIES, Document
from toulmin.core.handoffs import validate_applied
from toulmin.core.identifiers import ObjectId, ObjectKind, ObjectRef
from toulmin.core.project import validate_project
from toulmin.core.repository import Repository
from toulmin.core.review import INTAKE_FILE, parse_review, validate_intake
from toulmin.core.schema import validate


@dataclass(frozen=True)
class ProjectSnapshot:
    charter: Document | None
    objects: tuple[Document, ...]
    errors: tuple[str, ...]
    # Explicit [[...]] references in brief.md that resolved, as (line, reference).
    brief_references: tuple[tuple[int, str], ...] = ()
    # Review drafts not yet given an intake outcome, as (Run ID, labels).
    pending_drafts: tuple[tuple[str, tuple[str, ...]], ...] = ()


def _brief_errors(
    repository: Repository, project: str, found: list[tuple[int, str]] | None = None
) -> list[str]:
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
                if found is not None:
                    found.append((line_number, value))
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
    references: list[tuple[int, str]] = []
    try:
        errors.extend(_brief_errors(repository, project, references))
    except (OSError, ValueError) as error:
        errors.append(str(error))
    errors.extend(_supersession_errors(objects, project))
    waiting: list[tuple[str, tuple[str, ...]]] = []
    try:
        folder = repository.path(f"projects/{project}/runs", "directory")
        for record in sorted(folder.glob(f"*/{INTAKE_FILE}")):
            try:
                waiting.extend(_intake(repository, record, objects))
            except (OSError, ValueError) as error:
                errors.append(str(error))
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
    return ProjectSnapshot(
        charter, tuple(objects), tuple(sorted(set(errors))), tuple(references), tuple(waiting)
    )


def _intake(
    repository: Repository, path: Path, objects: list[Document]
) -> list[tuple[str, tuple[str, ...]]]:
    """Validate one intake record against its Run, raw output and Objections."""
    relative = path.relative_to(repository.root).as_posix()
    record = repository.read(relative)
    outcomes = validate_intake(record)
    directory = relative.rsplit("/", 1)[0]
    run = next((doc for doc in objects if str(doc.object_id) == record.header["run"]), None)
    if run is None or run.object_id.kind != ObjectKind.RUN or run.header["output"] != directory:
        record.fail("run", f"expected the Run whose output is {directory}")
    output = record.header["output"]
    if output.rsplit("/", 1)[0] != directory:
        record.fail("output", "raw output must be in the same archive directory")
    raw = repository.path(output, "file")
    labels = [draft.label for draft in parse_review(raw.read_text("utf-8"), str(raw))]
    known = {str(doc.object_id): doc for doc in objects}
    for label, entry in outcomes.items():
        if label not in labels:
            record.fail("outcomes", f"{label}: no such draft in {output}")
        if "object" in entry:
            objection = known.get(entry["object"])
            source = objection.header["source"] if objection else {}
            if source.get("ref") != record.header["run"] or source.get("path") != output:
                record.fail("outcomes", f"{label}: {entry['object']} does not cite this output")
    waiting = tuple(label for label in labels if label not in outcomes)
    return [(record.header["run"], waiting)] if waiting else []


def _supersession_errors(objects: list[Document], project: str) -> list[str]:
    """Revision chains must stay inside the project and must not loop."""
    errors: list[str] = []
    successors: dict[ObjectId, ObjectId] = {}
    for doc in objects:
        if doc.object_id.kind != ObjectKind.CLAIM or "superseded_by" not in doc.header:
            continue
        reference = ObjectRef.parse(doc.header["superseded_by"])
        if reference.project not in {None, project}:
            errors.append(
                f"{doc.location}:{doc.lines.get('superseded_by', 2)}: superseded_by: "
                "successor must be a Claim in the same project"
            )
            continue
        successors[doc.object_id] = reference.object_id
    for start in successors:
        seen = [start]
        current = successors[start]
        while current in successors:
            if current in seen:
                chain = " -> ".join(str(item) for item in [*seen, current])
                errors.append(f"{start}: superseded_by: revision cycle {chain}")
                break
            seen.append(current)
            current = successors[current]
    return errors


def current_claim(objects: tuple[Document, ...], claim: ObjectId) -> tuple[ObjectId, ...]:
    """The revision chain from `claim` to its current (non-superseded) successor."""
    successors = {
        doc.object_id: ObjectRef.parse(doc.header["superseded_by"]).object_id
        for doc in objects
        if doc.object_id.kind == ObjectKind.CLAIM and "superseded_by" in doc.header
    }
    chain = [claim]
    while chain[-1] in successors and successors[chain[-1]] not in chain:
        chain.append(successors[chain[-1]])
    return tuple(chain)


def local_target(document: Document, project: str) -> ObjectId | None:
    reference = ObjectRef.parse(document.header["target"])
    return reference.object_id if reference.project in {None, project} else None
