"""O4: recoverable publication of ordinary engineering Runs, without scientific promotion."""

import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from toulmin.core.atomic import digest, sync_directory, write_atomic
from toulmin.core.codec import encode
from toulmin.core.documents import Document, FormatError
from toulmin.core.engineering_tasks import TaskImport, parse_task_import, render_task_import
from toulmin.core.identifiers import ObjectId, ObjectKind
from toulmin.core.repository import Repository
from toulmin.core.scoped_tasks import ScopedImport
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
    if isinstance(record, ScopedImport):
        return read_scoped_import(repository, archive, record)
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
    if isinstance(record, ScopedImport):
        return publish_scoped_import(repository, record, files, archive)
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


def operational_run(record: ScopedImport, archive: str) -> bytes:
    fields: dict[str, Any] = {
        "schema_version": 1,
        "kind": "engineering-run",
        "scope": record.scope.to_data(),
        "created": record.at,
        "status": "completed" if record.state == "done" else "failed",
        "source": {"kind": "human", "actor": record.actor},
        "role": "implementer",
        "model": None,
        "session_id": record.session_id,
        "duration_seconds": None,
        "input_files": [record.request, archive.removesuffix("-result") + "/submission.json"],
        "output": archive,
    }
    body = _run_content(record, archive)[1]
    body += (
        "\nRaw artifacts are machine-local under ignored .aoe/task-results/; their "
        "hashes are portable. "
        "Missing local artifacts on another machine make replay unavailable, not invalid "
        "scientific history.\n"
    )
    return encode(Document(fields, body, archive))


def read_scoped_import(
    repository: Repository, archive: str, record: ScopedImport
) -> tuple[TaskImport, dict[str, bytes]]:
    private = f".aoe/task-results/{record.request_sha256}"
    files = {}
    for name, sha256 in record.files.items():
        raw = repository.path(f"{private}/{name}", "file").read_bytes()
        if digest(raw) != sha256:
            raise FormatError(
                f"{private}/{name}: frozen task artifact changed; preserve it for inspection"
            )
        files[name] = raw
    submission = repository.path(
        archive.removesuffix("-result") + "/submission.json", "file"
    ).read_bytes()
    if digest(submission) != record.submission_sha256:
        raise FormatError("scoped task submission differs from imported pin")
    if record.disposition == "applied":
        if record.scope.project is None:
            path = repository.path(record.run or "", "file")
            if path.read_bytes() != operational_run(record, archive):
                raise FormatError("workspace import differs from its operational Run")
        else:
            run = repository.load(record.scope.project, ObjectId.parse(record.run or ""))
            header, body = _run_content(record, archive)
            if run.body != body or any(
                run.header.get(key) != value for key, value in header.items()
            ):
                raise FormatError("project v2 import differs from its formal Run")
    return record, files


def publish_scoped_import(
    repository: Repository, record: ScopedImport, files: dict[str, bytes], archive: str
) -> TaskImport:
    from toulmin.core.scoped_tasks import parse_import, render_import

    record = parse_import(render_import(record), "scoped import plan")
    if {name: digest(data) for name, data in files.items()} != record.files:
        raise FormatError("frozen scoped task artifact hashes changed")
    if digest(repository.path(record.request, "file").read_bytes()) != record.request_sha256:
        raise FormatError("task request changed before import")
    target = repository.path(archive)
    import_path = repository.path(f"{archive}/import.json")
    if import_path.exists():
        saved = parse_import(import_path.read_bytes(), "saved import")
        read_scoped_import(repository, archive, saved)
        if saved != record:
            raise FormatError("scoped import changed since preview")
        if saved.disposition == "applied":
            return saved
    else:
        private = repository.path(f".aoe/task-results/{record.request_sha256}")
        if private.exists():
            actual = {
                p.name: digest(p.read_bytes())
                for p in private.iterdir()
                if p.is_file() and not p.is_symlink()
            }
            if actual != record.files or any(
                not p.is_file() or p.is_symlink() for p in private.iterdir()
            ):
                raise FormatError(
                    "partial or changed local artifacts; "
                    "preserve them and restore exact frozen files"
                )
        else:
            private.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix=".task-import-", dir=private.parent
            ) as temporary:
                staging = Path(temporary) / "artifacts"
                staging.mkdir()
                for name, data in files.items():
                    write_atomic(staging / name, data)
                os.rename(staging, private)
                sync_directory(private.parent)
        target.mkdir(exist_ok=True)
        write_atomic(import_path, render_import(record))
    if record.scope.project is None:
        run = f"{archive}/run.md"
        path = repository.path(run)
        expected = operational_run(record, archive)
        if path.exists():
            if path.read_bytes() != expected:
                raise FormatError("operational Run changed during import; nothing repaired")
        else:
            write_atomic(path, expected)
    else:
        project = record.scope.project
        existing = [
            repository.read(path.relative_to(repository.root).as_posix())
            for path in repository.path(f"projects/{project}/runs", "directory").glob("R-*.md")
            if repository.read(path.relative_to(repository.root).as_posix()).header.get("output")
            == archive
        ]
        h, body = _run_content(record, archive)
        if len(existing) > 1:
            raise FormatError("multiple project Runs refer to scoped task result")
        if existing:
            doc = existing[0]
            if doc.body != body or any(doc.header.get(key) != value for key, value in h.items()):
                raise FormatError("existing project Run differs from scoped result")
            run = str(doc.object_id)
        else:
            with repository.creation_lock(project):
                run = publish_locked(
                    repository,
                    project,
                    ObjectKind.RUN,
                    h,
                    Document({}, body, archive),
                    record.actor,
                ).stem
    done = replace(record, run=run, disposition="applied")
    write_atomic(import_path, render_import(done), replace=True)
    return done
