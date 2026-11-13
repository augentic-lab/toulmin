"""R8 B3: publish a confirmed, frozen import in the workspace; external reads stay in L3."""

import os
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from toulmin.core.atomic import digest, sync_directory, write_atomic
from toulmin.core.build import BuildImport, parse_import, render_import
from toulmin.core.codec import decode
from toulmin.core.documents import Document, FormatError
from toulmin.core.identifiers import ObjectKind
from toulmin.core.project_proposals import validate_build_request
from toulmin.core.repository import Repository
from toulmin.protocols.build import import_proposals
from toulmin.protocols.intake import publish_locked


def _worker(repository: Repository, record: BuildImport) -> str:
    """Name the worker launcher; a wrapper may route the tool to another provider's model."""
    worker = record.tool or "not reported"
    raw = repository.path(record.request, "file").read_bytes()
    if digest(raw) != record.request_sha256:
        raise FormatError(f"{record.request}: applied build request was changed")
    command = validate_build_request(decode(raw, record.request)).command
    return worker if command is None else f"{worker} via {command}"


def read_record(repository: Repository, archive: str) -> BuildImport:
    relative = f"{archive}/import.json"
    return parse_import(repository.path(relative, "file").read_bytes(), relative)


def checked_artifacts(
    repository: Repository, archive: str, record: BuildImport
) -> dict[str, bytes]:
    files = {}
    for name, sha in record.files.items():
        data = repository.path(f"{archive}/{name}", "file").read_bytes()
        if digest(data) != sha:
            raise FormatError(f"{archive}/{name}: frozen import artifact changed")
        files[name] = data
    return files


def apply_frozen_import(
    root: Path, project: str, record: BuildImport, files: dict[str, bytes], archive: str
) -> BuildImport:
    """Caller holds the project writer lock. Each publication is exclusive and recoverable."""
    repository = Repository(root)
    if not record.actor.strip():
        raise FormatError("actor: expected nonempty researcher")
    # Check the complete metadata and artifacts before the archive is made visible.
    record = parse_import(render_import(record), "import plan")
    if {name: digest(data) for name, data in files.items()} != record.files:
        raise FormatError("import: artifact set differs from the frozen plan")
    # Read before anything is published: a changed request must not leave a partial import.
    worker = _worker(repository, record)
    destination = repository.path(archive)
    if destination.exists():
        saved = read_record(repository, archive)
        if saved != record:
            raise FormatError(f"{archive}: import record changed since preview")
        checked_artifacts(repository, archive, record)
        if record.disposition == "applied":
            return record
    else:
        proposals = repository.path(f"projects/{project}/runs/proposals")
        stamp = (
            datetime.fromisoformat(record.at.replace("Z", "+00:00"))
            .astimezone(UTC)
            .strftime("%Y%m%dT%H%M%SZ")
        )
        if record.state == "done":
            for kind in ("decision", "evidence", "ruling"):
                path = repository.path(
                    f"projects/{project}/runs/proposals/{kind}-{stamp}-build-{record.spec}.md"
                )
                if path.exists():
                    raise FormatError(f"{path}: import proposal target already exists")
        runs = repository.path(f"projects/{project}/runs", "directory")
        with tempfile.TemporaryDirectory(dir=runs, prefix=".build-import-") as scratch:
            temporary = Path(scratch) / "archive"
            temporary.mkdir()
            for name, data in files.items():
                write_atomic(temporary / name, data)
            write_atomic(temporary / "import.json", render_import(record))
            if destination.exists():
                raise FormatError(f"{archive}: occupied import archive")
            os.rename(temporary, destination)
            sync_directory(runs)
        if not proposals.exists():
            proposals.mkdir()

    # Recover the gap between publishing a Run and updating the journal by its unique output.
    existing = []
    for path in repository.path(f"projects/{project}/runs", "directory").glob("R-*.md"):
        doc = repository.read(path.relative_to(repository.root).as_posix())
        if doc.header.get("output") == archive:
            existing.append(doc)
    if len(existing) > 1:
        raise FormatError(f"{archive}: multiple Runs name this import")
    header = {
        "status": "completed" if record.state == "done" else "failed",
        "source": {"kind": "human", "actor": record.actor},
        "role": "implementer",
        "model": f"{worker} (Chief worker; model not reported)",
        "session_id": record.session_id,
        "duration_seconds": None,
        "input_files": [f"projects/{project}/specs/{record.spec}.md"],
        "output": archive,
    }
    body = (
        f"## Summary\nImported Chief task {record.task_id} ({record.state}) "
        f"at head {record.head or 'not reported'}.\n"
    )
    if record.state == "abandoned":
        body += "\n## Failure\nChief task was abandoned; no Evidence or ruling is proposed.\n"
    if existing:
        doc = existing[0]
        if doc.body != body or any(doc.header.get(key) != value for key, value in header.items()):
            raise FormatError(f"{archive}: existing Run does not match the frozen import")
        run = str(doc.object_id)
    else:
        if record.run is not None:
            raise FormatError(f"{archive}: recorded Run {record.run} is missing")
        with repository.creation_lock(project):
            path = publish_locked(
                repository,
                project,
                ObjectKind.RUN,
                header,
                Document({}, body, archive),
                record.actor,
            )
        run = path.stem
    if record.run not in {None, run}:
        raise FormatError(f"{archive}: import Run identity changed")
    record = replace(record, run=run)
    write_atomic(
        repository.path(f"{archive}/import.json", "file"), render_import(record), replace=True
    )
    drafts = import_proposals(record, archive)
    for name, data in drafts.items():
        path = repository.path(f"projects/{project}/runs/proposals/{name}")
        if path.exists():
            if path.read_bytes() != data:
                raise FormatError(
                    f"{path}: interrupted import proposal differs; nothing overwritten"
                )
        else:
            write_atomic(path, data)
    record = replace(record, disposition="applied", proposals=tuple(drafts))
    write_atomic(
        repository.path(f"{archive}/import.json", "file"), render_import(record), replace=True
    )
    return record
