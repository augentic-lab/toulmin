"""L1 schemas for handoff drafts and immutable applied handoff records."""

import re

from toulmin.core.atomic import digest
from toulmin.core.codec import decode
from toulmin.core.documents import Document, sections, validate_values
from toulmin.core.identifiers import ObjectKind
from toulmin.core.repository import Repository
from toulmin.core.schema import mapping, reference, strings, text, timestamp

DRAFT_FIELDS = {
    "schema_version",
    "project",
    "session_id",
    "created",
    "base_project_sha256",
    "recent_decisions",
    "next_step",
}
RECORD_FIELDS = {
    "source_draft",
    "source_sha256",
    "applied_by",
    "applied_at",
    "project_sha256",
    "previous_handoff",
}
NEXT_STEP_TEXT = "See metadata next_step."


def hash_field(document: Document, field: str) -> str:
    value = text(document, document.header.get(field), field)
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        document.fail(field, "expected SHA-256 hex digest")
    return value


def validate_handoff(document: Document, project: str, *, applied: bool = False) -> None:
    validate_values(document)
    h = mapping(document, document.header, "", DRAFT_FIELDS | (RECORD_FIELDS if applied else set()))
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    if h["project"] != project:
        document.fail("project", "handoff belongs to another project")
    timestamp(document, h["created"], "created")
    hash_field(document, "base_project_sha256")
    if h["session_id"] is not None:
        text(document, h["session_id"], "session_id")
    text(document, h["next_step"], "next_step")
    for index, value in enumerate(strings(document, h["recent_decisions"], "recent_decisions")):
        reference(document, value, f"recent_decisions[{index}]", ObjectKind.DECISION)
    body = sections(document)
    for field in ("Done", "Decisions", "Open questions", "Next step"):
        if not body.get(field, "").strip():
            document.fail("body." + field, "required section missing or empty")
    if body["Next step"].strip() != NEXT_STEP_TEXT:
        document.fail("body.Next step", "must point to metadata next_step, not duplicate its value")
    if applied:
        previous = h["previous_handoff"]
        if previous is not None:
            previous = text(document, previous, "previous_handoff")
            if "/" in previous or "\\" in previous or not previous.endswith(".md"):
                document.fail("previous_handoff", "expected a session filename or null")
        for field in ("source_sha256", "project_sha256"):
            hash_field(document, field)
        for field in ("source_draft", "applied_by"):
            text(document, h[field], field)
        timestamp(document, h["applied_at"], "applied_at")


def append_decisions(existing: list[str], additions: list[str]) -> list[str]:
    """Retain the existing sequence; append each new reference at most once."""
    return [*existing, *dict.fromkeys(value for value in additions if value not in existing)]


def validate_decisions(repository: Repository, document: Document, project: str) -> None:
    for index, value in enumerate(document.header["recent_decisions"]):
        try:
            repository.resolve(project, value)
        except (OSError, ValueError) as error:
            document.fail(f"recent_decisions[{index}]", str(error))


def validate_applied(repository: Repository, record: Document, project: str) -> None:
    validate_handoff(record, project, applied=True)
    validate_decisions(repository, record, project)
    if record.header["previous_handoff"] is not None:
        try:
            repository.path(
                f"projects/{project}/sessions/{record.header['previous_handoff']}", "file"
            )
        except (OSError, ValueError) as error:
            record.fail("previous_handoff", str(error))
    try:
        source = repository.path(record.header["source_draft"], "file")
        if not source.is_relative_to(repository.path(f"projects/{project}/runs", "directory")):
            record.fail("source_draft", "source is outside this project's runs/")
        data = source.read_bytes()
    except (OSError, ValueError) as error:
        record.fail("source_draft", str(error))
    if digest(data) != record.header["source_sha256"]:
        record.fail("source_sha256", "archived source draft has changed")
    draft = decode(data, str(source))
    validate_handoff(draft, project)
    if record.body != draft.body or any(
        record.header[key] != draft.header[key] for key in DRAFT_FIELDS
    ):
        record.fail("source_draft", "applied record does not match its source draft")
