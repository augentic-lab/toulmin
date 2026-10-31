"""Recoverable forward application of one session record and one PROJECT update."""

import os
import shutil
import tempfile
import uuid
from pathlib import Path

from toulmin.core.atomic import digest, sync_directory, write_atomic
from toulmin.core.codec import decode, encode
from toulmin.core.documents import Document, FormatError
from toulmin.core.handoffs import append_decisions, validate_applied, validate_handoff
from toulmin.core.project import validate_project
from toulmin.core.repository import Repository
from toulmin.core.schema import mapping

PENDING = ".handoff-pending"


def prepare(
    repository: Repository,
    project: str,
    before: bytes,
    after: bytes,
    session: bytes,
    draft: bytes,
    filename: str,
) -> None:
    directory = repository.project(project)
    pending = repository.path(f"projects/{project}/{PENDING}")
    if pending.exists():
        raise FormatError(f"{pending}: unresolved handoff transaction")
    metadata = {"schema_version": 1, "project": project, "session_filename": filename}
    with tempfile.TemporaryDirectory(prefix=".handoff-prepare-", dir=directory) as temporary:
        staging = Path(temporary)
        for name, data in {
            "before": before,
            "after": after,
            "session": session,
            "draft": draft,
        }.items():
            write_atomic(staging / f"{name}.md", data)
            metadata[f"{name}_sha256"] = digest(data)
        write_atomic(staging / "intent.md", encode(Document(metadata, "Handoff write intent.\n")))
        os.rename(staging, pending)
        sync_directory(directory)


def finish(repository: Repository, project: str, expected_draft: str) -> Path:
    prefix = f"projects/{project}/{PENDING}"
    pending = repository.path(prefix, "directory")
    intent = repository.read(prefix + "/intent.md")
    h = mapping(
        intent,
        intent.header,
        "",
        {
            "schema_version",
            "project",
            "session_filename",
            "before_sha256",
            "after_sha256",
            "session_sha256",
            "draft_sha256",
        },
    )
    if type(h["schema_version"]) is not int or h["schema_version"] != 1 or h["project"] != project:
        intent.fail("project", "invalid handoff transaction version/project")
    if h["draft_sha256"] != expected_draft:
        intent.fail(
            "draft_sha256",
            "pending transaction belongs to another draft; restore/apply its original draft",
        )
    filename = h["session_filename"]
    if (
        not isinstance(filename, str)
        or "/" in filename
        or "\\" in filename
        or not filename.endswith(f"-{expected_draft}.md")
    ):
        intent.fail("session_filename", "invalid handoff filename")
    images = {}
    for name in ("before", "after", "session", "draft"):
        data = repository.path(f"{prefix}/{name}.md", "file").read_bytes()
        if digest(data) != h[f"{name}_sha256"]:
            intent.fail(f"{name}_sha256", "journal image checksum mismatch; originals retained")
        images[name] = data
    before = decode(images["before"])
    after = decode(images["after"])
    validate_project(before, project)
    validate_project(after, project)
    record = decode(images["session"])
    validate_applied(repository, record, project)
    draft = decode(images["draft"])
    validate_handoff(draft, project)
    if (
        record.header["source_sha256"] != expected_draft
        or record.header["project_sha256"] != h["after_sha256"]
        or draft.header["base_project_sha256"] != h["before_sha256"]
        or record.header["previous_handoff"] != before.header["last_handoff"]
    ):
        intent.fail("session", "record and write intent disagree")
    allowed = {"recent_decisions", "next_step", "last_handoff"}
    if before.body != after.body or {
        key: value for key, value in before.header.items() if key not in allowed
    } != {key: value for key, value in after.header.items() if key not in allowed}:
        intent.fail("after", "transaction changes researcher-owned content or stage")
    expected_decisions = append_decisions(
        before.header["recent_decisions"], draft.header["recent_decisions"]
    )
    if (
        after.header["last_handoff"] != filename
        or after.header["next_step"] != draft.header["next_step"]
        or after.header["recent_decisions"] != expected_decisions
    ):
        intent.fail("after", "transaction does not match draft intent")
    charter = repository.path(f"projects/{project}/PROJECT.md", "file")
    current = digest(charter.read_bytes())
    if current not in {h["before_sha256"], h["after_sha256"]}:
        intent.fail(
            "base_project_sha256", "PROJECT changed; refusing recovery overwrite; journal retained"
        )
    target = repository.path(f"projects/{project}/sessions/{filename}")
    if target.exists():
        if not target.is_file() or digest(target.read_bytes()) != h["session_sha256"]:
            intent.fail("session", "conflicting session file; kept unchanged")
    else:
        write_atomic(target, images["session"])
    current = digest(charter.read_bytes())
    if current == h["before_sha256"]:
        repository.path(f"projects/{project}/PROJECT.md", "file")
        write_atomic(charter, images["after"], replace=True)
    elif current != h["after_sha256"]:
        intent.fail("base_project_sha256", "PROJECT changed during apply; journal retained")
    # Retire the intact journal atomically before cleanup: a cleanup interruption
    # must not leave a half-deleted *pending* transaction.
    completed = pending.with_name(".handoff-completed-" + uuid.uuid4().hex)
    os.rename(pending, completed)
    sync_directory(charter.parent)
    try:
        shutil.rmtree(completed)
    except OSError as error:
        raise FormatError(
            f"Handoff applied; completed journal cleanup remains at {completed}: {error}"
        ) from error
    return target
