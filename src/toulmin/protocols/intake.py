"""L2: confirmed intake of a complete draft, never an automatic ruling."""

from datetime import UTC, datetime
from pathlib import Path

from toulmin.core.documents import STATUSES, Document
from toulmin.core.identifiers import SCHEMA_VERSION, ObjectKind
from toulmin.core.repository import Repository
from toulmin.core.schema import text, validate


def create_object(
    root: Path, project: str, kind: ObjectKind, input_path: str, actor: str, confirmed: bool
) -> Path:
    repository = Repository(root)
    repository.project(project)
    draft = repository.read(input_path)
    if not confirmed:
        draft.fail(
            "confirmed_by", "explicit researcher confirmation required; draft kept unchanged"
        )
    text(draft, actor, "confirmed_by.actor")
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
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    with repository.creation_lock(project):
        object_id = repository.next_id(project, kind)
        header = dict(draft.header)
        header.update(
            schema_version=SCHEMA_VERSION,
            id=str(object_id),
            status=status,
            created=now,
            confirmed_by={"actor": actor, "at": now},
        )
        document = Document(header, draft.body, draft.location, draft.lines, draft.body_line)
        validate(document)
        return repository.publish(project, document)
