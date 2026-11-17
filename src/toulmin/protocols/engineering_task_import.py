"""O4: recoverable publication of ordinary engineering Runs, without scientific promotion."""

import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from toulmin.core.atomic import digest, sync_directory, write_atomic
from toulmin.core.documents import Document, FormatError
from toulmin.core.engineering_tasks import TaskImport, parse_task_import, render_task_import
from toulmin.core.identifiers import ObjectId, ObjectKind
from toulmin.core.repository import Repository
from toulmin.protocols.intake import publish_locked


def _run_content(record: TaskImport, archive: str) -> tuple[dict[str, Any], str]:
    worker = record.tool or "not reported"
    if record.command is not None:
        worker += f" via {record.command}"
    header = {
        "status": "completed" if record.state == "done" else "failed",
        "source": {"kind": "human", "actor": record.actor},
        "role": "implementer",
        "model": f"{worker} (Chief worker; model not reported)",
        "session_id": record.session_id,
        "duration_seconds": None,
        "input_files": [record.request],
        "output": archive,
    }
    body = (
        f"## Summary\nImported engineering task {record.task_id} ({record.state}) "
        f"at head {record.head or 'not reported'}.\n"
        "Worker artifacts are archived output; scientific promotion remains "
        "a separate researcher decision.\n"
    )
    if record.state == "abandoned":
        body += "\n## Failure\nChief task was abandoned.\n"
    return header, body


def read_task_import(repository: Repository, archive: str) -> tuple[TaskImport, dict[str, bytes]]:
    path = f"{archive}/import.json"
    record = parse_task_import(repository.path(path, "file").read_bytes(), path)
    files = {}
    for name, sha in record.files.items():
        raw = repository.path(f"{archive}/{name}", "file").read_bytes()
        if digest(raw) != sha:
            raise FormatError(f"{archive}/{name}: frozen task artifact changed")
        files[name] = raw
    if record.disposition == "applied":
        run = repository.load(archive.split("/")[1], ObjectId.parse(record.run or ""))
        header, body = _run_content(record, archive)
        if run.body != body or any(run.header.get(key) != value for key, value in header.items()):
            raise FormatError(f"{archive}: import does not match its Run")
    return record, files


def publish_task_import(
    root: Path,
    project: str,
    record: TaskImport,
    files: dict[str, bytes],
    archive: str,
) -> TaskImport:
    """Caller holds the project writer lock; each visible publication can be resumed."""
    repository = Repository(root)
    record = parse_task_import(render_task_import(record), "task import plan")
    if {name: digest(data) for name, data in files.items()} != record.files:
        raise FormatError("task import artifact set differs from its frozen plan")
    if digest(repository.path(record.request, "file").read_bytes()) != record.request_sha256:
        raise FormatError("task request changed before import")
    destination = repository.path(archive)
    if destination.exists():
        saved, _ = read_task_import(repository, archive)
        if saved != record:
            raise FormatError("task import record changed since preview")
        if record.disposition == "applied":
            return record
    else:
        runs = repository.path(f"projects/{project}/runs", "directory")
        with tempfile.TemporaryDirectory(dir=runs, prefix=".task-import-") as scratch:
            temporary = Path(scratch) / "archive"
            temporary.mkdir()
            for name, data in files.items():
                write_atomic(temporary / name, data)
            write_atomic(temporary / "import.json", render_task_import(record))
            if destination.exists():
                raise FormatError("task import archive occupied")
            os.rename(temporary, destination)
            sync_directory(runs)
    existing = []
    for path in repository.path(f"projects/{project}/runs", "directory").glob("R-*.md"):
        document = repository.read(path.relative_to(repository.root).as_posix())
        if document.header.get("output") == archive:
            existing.append(document)
    if len(existing) > 1:
        raise FormatError("multiple Runs name the same engineering task import")
    header, body = _run_content(record, archive)
    if existing:
        doc = existing[0]
        if doc.body != body or any(doc.header.get(key) != value for key, value in header.items()):
            raise FormatError("existing Run differs from the frozen engineering import")
        run = str(doc.object_id)
    else:
        if record.run is not None:
            raise FormatError("recorded engineering Run is missing")
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
        raise FormatError("engineering import Run identity changed")
    done = replace(record, disposition="applied", run=run)
    write_atomic(
        repository.path(f"{archive}/import.json", "file"), render_task_import(done), replace=True
    )
    return done
