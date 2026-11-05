"""L2: confirmed intake of a complete draft, never an automatic ruling."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from toulmin.core.documents import DIRECTORIES, STATUSES, Document
from toulmin.core.identifiers import SCHEMA_VERSION, ObjectKind
from toulmin.core.repository import Repository
from toulmin.core.schema import in_order, object_order, text, utc_text, validate
from toulmin.core.skeletons import unfilled


def create_object(
    root: Path,
    project: str,
    kind: ObjectKind,
    input_path: str,
    actor: str,
    confirmed: bool,
    *,
    preview: bool = False,
) -> Path:
    """Create one object from a complete draft; ``preview`` checks everything, writes nothing.

    A preview returns the path the object would get now; the ID is assigned again at intake.
    """
    repository = Repository(root)
    repository.project(project)
    draft = repository.read(repository.relative(input_path))
    if not confirmed and not preview:
        draft.fail(
            "confirmed_by", "explicit researcher confirmation required; draft kept unchanged"
        )
    text(draft, actor, "confirmed_by.actor")
    placeholder = unfilled(draft)
    if placeholder:
        draft.fail(placeholder, "unfilled <fill: ...> placeholder; edit the draft first")
    for field in ("id", "created", "confirmed_by"):
        if field in draft.header:
            draft.fail(field, "assigned at intake; supply a draft rather than an existing object")
    if "schema_version" in draft.header and (
        type(draft.header["schema_version"]) is not int
        or draft.header["schema_version"] != SCHEMA_VERSION
    ):
        draft.fail("schema_version", "expected version 1")
    if kind == ObjectKind.RUN and "status" not in draft.header:
        draft.fail("status", "Run outcome must be explicitly completed or failed")
    status = draft.header.get("status", STATUSES[kind][0])
    if status not in (STATUSES[kind] if kind == ObjectKind.RUN else STATUSES[kind][:1]):
        draft.fail(
            "status",
            "new only creates initial states; changes require a researcher Decision",
        )
    header = dict(draft.header)
    header["status"] = status
    if preview:
        document = _prepared(repository, project, kind, header, draft, actor)
        validate(document)
        repository.validate_links(document, project)
        return repository.path(f"projects/{project}/{DIRECTORIES[kind]}/{document.object_id}.md")
    with repository.creation_lock(project):
        return publish_locked(repository, project, kind, header, draft, actor)


def _prepared(
    repository: Repository,
    project: str,
    kind: ObjectKind,
    header: dict[str, Any],
    source: Document,
    actor: str,
) -> Document:
    now = utc_text(datetime.now(UTC))
    object_id = repository.next_id(project, kind)
    header = dict(header)
    header.update(
        schema_version=SCHEMA_VERSION,
        id=str(object_id),
        created=now,
        confirmed_by={"actor": actor, "at": now},
    )
    header = in_order(header, object_order(kind))
    return Document(header, source.body, source.location, source.lines, source.body_line)


def publish_locked(
    repository: Repository,
    project: str,
    kind: ObjectKind,
    header: dict[str, Any],
    source: Document,
    actor: str,
) -> Path:
    """Assign ID, time and confirmation, then publish. The caller holds the creation lock."""
    document = _prepared(repository, project, kind, header, source, actor)
    validate(document)
    return repository.publish(project, document)
