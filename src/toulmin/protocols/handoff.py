"""L2 drafting, researcher-confirmed application and idempotent handoff recovery."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from toulmin.core.atomic import digest, handoff_mutex, write_atomic
from toulmin.core.codec import decode, encode, patch_header
from toulmin.core.documents import Document, FormatError, sections
from toulmin.core.handoff_transaction import PENDING, finish, prepare
from toulmin.core.handoffs import (
    NEXT_STEP_TEXT,
    append_decisions,
    validate_applied,
    validate_decisions,
    validate_handoff,
)
from toulmin.core.project import validate_project
from toulmin.core.repository import Repository
from toulmin.core.schema import mapping, text


def draft_handoff(root: Path, project: str, input_path: str | None = None) -> Path:
    repository = Repository(root)
    repository.project(project)
    charter_path = repository.path(f"projects/{project}/PROJECT.md", "file")
    original = charter_path.read_bytes()
    charter = decode(original, str(charter_path))
    validate_project(charter, project)
    if input_path is None:
        header = {
            "session_id": None,
            "recent_decisions": [],
            "next_step": charter.header["next_step"],
        }
        body = (
            "## Done\nUnknown: no session summary supplied.\n\n"
            "## Decisions\nUnknown: no session decisions supplied.\n\n"
            "## Open questions\nUnknown: no session questions supplied.\n"
        )
    else:
        supplied = repository.read(input_path)
        mapping(
            supplied, supplied.header, "", set(), {"session_id", "recent_decisions", "next_step"}
        )
        header = {
            "session_id": supplied.header.get("session_id"),
            "recent_decisions": supplied.header.get("recent_decisions", []),
            "next_step": supplied.header.get("next_step", charter.header["next_step"]),
        }
        body = supplied.body
        if "Next step" in sections(supplied):
            supplied.fail("body.Next step", "omit this section; next step belongs in metadata")
    body += f"\n## Next step\n{NEXT_STEP_TEXT}\n"
    now = datetime.now(UTC)
    header.update(
        schema_version=1,
        project=project,
        created=now.isoformat().replace("+00:00", "Z"),
        base_project_sha256=digest(original),
    )
    document = Document(header, body, input_path or "<handoff>")
    validate_handoff(document, project)
    validate_decisions(repository, document, project)
    directory = repository.path(f"projects/{project}/runs", "directory") / (
        now.strftime("%Y%m%dT%H%M%SZ") + "-handoff-" + uuid4().hex
    )
    directory.mkdir()
    try:
        path = directory / "draft.md"
        write_atomic(path, encode(document))
    except (OSError, ValueError):
        # A directory fsync can fail after publication. Retain a complete draft
        # if it exists rather than silently deleting user-reviewable content.
        if not directory.joinpath("draft.md").exists():
            directory.rmdir()
        raise
    return path


def apply_handoff(root: Path, project: str, draft_path: str, actor: str, confirmed: bool) -> Path:
    repository = Repository(root)
    directory = repository.project(project)
    draft_file = repository.path(draft_path, "file")
    if not draft_file.is_relative_to(directory / "runs"):
        raise FormatError("Handoff draft must be archived inside the selected project's runs/")
    raw = draft_file.read_bytes()
    draft = decode(raw, str(draft_file))
    validate_handoff(draft, project)
    if not confirmed:
        draft.fail("applied_by", "explicit researcher confirmation required")
    text(draft, actor, "applied_by")
    fingerprint = digest(raw)
    with handoff_mutex(directory):
        object_lock = directory / ".toulmin-new.lock"
        if object_lock.exists() or object_lock.is_symlink():
            draft.fail("project", "active or interrupted object writer holds the project lock")
        pending = repository.path(f"projects/{project}/{PENDING}")
        if pending.exists():
            return finish(repository, project, fingerprint)
        sessions = repository.path(f"projects/{project}/sessions", "directory")
        matches = sorted(sessions.glob(f"*-{fingerprint}.md"))
        if len(matches) > 1:
            draft.fail("source_sha256", "multiple applied records for the same draft")
        if matches:
            # A session alone is not proof that the PROJECT update completed.
            charter = repository.read(f"projects/{project}/PROJECT.md")
            validate_project(charter, project)
            current = charter.header["last_handoff"]
            visited = set()
            while current is not None:
                if current in visited:
                    draft.fail("previous_handoff", "cycle in applied session history")
                visited.add(current)
                record = repository.read(f"projects/{project}/sessions/{current}")
                validate_applied(repository, record, project)
                if current == matches[0].name:
                    if record.header["source_sha256"] != fingerprint:
                        record.fail("source_sha256", "record digest does not match filename")
                    return matches[0]
                current = record.header["previous_handoff"]
            draft.fail(
                "source_sha256",
                "session is not linked from PROJECT; missing recovery intent; files retained",
            )
        validate_decisions(repository, draft, project)
        charter_path = repository.path(f"projects/{project}/PROJECT.md", "file")
        before = charter_path.read_bytes()
        if digest(before) != draft.header["base_project_sha256"]:
            draft.fail(
                "base_project_sha256", "PROJECT changed since drafting; create a fresh draft"
            )
        charter = decode(before, str(charter_path))
        validate_project(charter, project)
        now = datetime.now(UTC)
        filename = now.strftime("%Y%m%dT%H%M%SZ") + "-" + fingerprint + ".md"
        decisions = append_decisions(
            charter.header["recent_decisions"], draft.header["recent_decisions"]
        )
        after = patch_header(
            before,
            {
                "recent_decisions": decisions,
                "next_step": draft.header["next_step"],
                "last_handoff": filename,
            },
        )
        validate_project(decode(after), project)
        record_header = dict(draft.header)
        record_header.update(
            source_draft=draft_path,
            source_sha256=fingerprint,
            applied_by=actor,
            applied_at=now.isoformat().replace("+00:00", "Z"),
            project_sha256=digest(after),
            previous_handoff=charter.header["last_handoff"],
        )
        record = Document(record_header, draft.body)
        validate_handoff(record, project, applied=True)
        prepare(repository, project, before, after, encode(record), raw, filename)
        return finish(repository, project, fingerprint)
