"""R8 B4: workspace-only verification journals, checkpoints, Runs and proposed G5 rulings."""

import os
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from toulmin.core.atomic import digest, sync_directory, write_atomic
from toulmin.core.documents import Document, FormatError
from toulmin.core.identifiers import ObjectKind
from toulmin.core.repository import Repository
from toulmin.core.verification import (
    BuildVerification,
    CheckResult,
    parse_verification,
    render_verification,
)
from toulmin.protocols.build import verification_output, verification_proposals
from toulmin.protocols.intake import publish_locked


def read_verification(repository: Repository, archive: str) -> BuildVerification:
    path = f"{archive}/verify.json"
    return parse_verification(repository.path(path, "file").read_bytes(), path)


def save_verification(repository: Repository, archive: str, record: BuildVerification) -> None:
    record = parse_verification(render_verification(record), "verification journal")
    write_atomic(
        repository.path(f"{archive}/verify.json", "file"), render_verification(record), replace=True
    )


def begin_verification(root: Path, project: str, record: BuildVerification) -> str:
    """Publish a complete intent before any code is run; caller holds the project lock."""
    repository = Repository(root)
    record = parse_verification(render_verification(record), "verification plan")
    stamp = (
        datetime.fromisoformat(record.at.replace("Z", "+00:00"))
        .astimezone(UTC)
        .strftime("%Y%m%dT%H%M%SZ")
    )
    runs = repository.path(f"projects/{project}/runs", "directory")
    for number in range(1, 101):
        name = f"{stamp}-verify-{record.spec}" + (f"-{number}" if number > 1 else "")
        archive = f"projects/{project}/runs/{name}"
        destination = repository.path(archive)
        if destination.exists():
            continue
        for kind in ("decision", "evidence", "ruling"):
            if repository.path(f"projects/{project}/runs/proposals/{kind}-{name}.md").exists():
                raise FormatError(f"{name}: occupied verification proposal target")
        with tempfile.TemporaryDirectory(dir=runs, prefix=".verify-intent-") as scratch:
            temporary = Path(scratch) / "archive"
            temporary.mkdir()
            write_atomic(temporary / "verify.json", render_verification(record))
            if destination.exists():
                raise FormatError(f"{archive}: verification archive appeared concurrently")
            os.rename(temporary, destination)
            sync_directory(runs)
        return archive
    raise FormatError("verification: too many archive collisions")


def checkpoint(
    repository: Repository,
    archive: str,
    record: BuildVerification,
    results: tuple[CheckResult, ...],
    environment: bytes,
    *,
    completed: bool = False,
) -> BuildVerification:
    """Publish immutable artifacts before atomically switching the journal pointer."""
    candidate = replace(record, results=results, execution_completed=completed)
    output = verification_output(candidate)
    files = {"output.md": output, "environment.txt": environment}
    hashes = {name: digest(data) for name, data in files.items()}
    snapshot = "checkpoints/" + digest((hashes["output.md"] + hashes["environment.txt"]).encode())
    candidate = replace(candidate, files=hashes, snapshot=snapshot)
    candidate = parse_verification(render_verification(candidate), "verification checkpoint")
    parent = repository.path(f"{archive}/checkpoints")
    parent.mkdir(exist_ok=True)
    destination = repository.path(f"{archive}/{snapshot}")
    if not destination.exists():
        with tempfile.TemporaryDirectory(dir=parent, prefix=".checkpoint-") as scratch:
            temporary = Path(scratch) / "data"
            temporary.mkdir()
            for name, data in files.items():
                write_atomic(temporary / name, data)
            os.rename(temporary, destination)
            sync_directory(parent)
    for name, expected in files.items():
        if repository.path(f"{archive}/{snapshot}/{name}", "file").read_bytes() != expected:
            raise FormatError(f"{archive}/{snapshot}: occupied checkpoint differs")
    save_verification(repository, archive, candidate)
    return candidate


def finish_verification(root: Path, project: str, archive: str) -> BuildVerification:
    """Finish a recorded execution; never execute code and never intake its proposed rulings."""
    repository = Repository(root)
    record = read_verification(repository, archive)
    if not record.execution_completed or record.files is None or record.snapshot is None:
        raise FormatError(f"{archive}: execution is not complete")
    for name, sha in record.files.items():
        data = repository.path(f"{archive}/{record.snapshot}/{name}", "file").read_bytes()
        if digest(data) != sha:
            raise FormatError(f"{archive}: frozen verification checkpoint changed")
        path = repository.path(f"{archive}/{name}")
        if path.exists():
            if path.read_bytes() != data:
                raise FormatError(
                    f"{path}: recorded verification artifact differs; nothing overwritten"
                )
        else:
            write_atomic(path, data)
    if record.disposition == "applied":
        return record
    header = {
        "status": "completed",
        "source": {"kind": "human", "actor": record.actor},
        "model": "none (deterministic re-run by toulmin)",
        "role": "verifier",
        "session_id": None,
        "duration_seconds": sum(item.duration_seconds for item in record.results),
        "input_files": [f"projects/{project}/specs/{record.spec}.md", record.contract],
        "output": archive,
    }
    result = "passed" if record.passed else "failed (including any timed-out checks)"
    body = (
        f"## Summary\nIndependent frozen-check verification of {record.spec} "
        f"at {record.head}: {result}.\n"
        "The Run completed; the check results and environment are archived, "
        "and the researcher rules on acceptance.\n"
    )
    existing = []
    for path in repository.path(f"projects/{project}/runs", "directory").glob("R-*.md"):
        doc = repository.read(path.relative_to(repository.root).as_posix())
        if doc.header.get("output") == archive:
            existing.append(doc)
    if len(existing) > 1:
        raise FormatError(f"{archive}: multiple Runs name this verification")
    if existing:
        doc = existing[0]
        if doc.body != body or any(doc.header.get(key) != value for key, value in header.items()):
            raise FormatError(f"{archive}: Run differs from recorded verification")
        run = str(doc.object_id)
    else:
        if record.run is not None:
            raise FormatError(f"{archive}: recorded Run is missing")
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
        raise FormatError(f"{archive}: Run identity differs")
    record = replace(record, run=run)
    save_verification(repository, archive, record)
    drafts = verification_proposals(record, archive)
    for name, data in drafts.items():
        path = repository.path(f"projects/{project}/runs/proposals/{name}")
        if path.exists():
            if path.read_bytes() != data:
                raise FormatError(f"{path}: verification proposal differs; nothing overwritten")
        else:
            write_atomic(path, data)
    record = replace(record, disposition="applied", proposals=tuple(drafts))
    save_verification(repository, archive, record)
    return record
