"""O4 file-only task proposals and ordinary Run publication.

Engineering tasks deliberately have no Claim, Spec, gate or scientific ruling dependency.
The researcher confirms the external contract; imported worker output remains a Run.
"""

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from toulmin.core.atomic import digest, write_atomic
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError
from toulmin.core.engineering_tasks import TASK_FILENAME, TaskRequest, validate_task_request
from toulmin.core.project_proposals import OUTCOME_SUFFIX, Outcome, render_outcome, validate_outcome
from toulmin.core.render import header
from toulmin.core.repository import Repository
from toulmin.core.schema import utc_text


@dataclass(frozen=True)
class TaskPlan:
    path: str
    sha256: str
    request: TaskRequest
    task_id: str
    contract: dict[str, Any]


def request_path(repository: Repository, project: str, relative: str) -> Path:
    repository.project(project)
    prefix = f"projects/{project}/runs/proposals/"
    if not relative.startswith(prefix) or not TASK_FILENAME.fullmatch(relative[len(prefix) :]):
        raise FormatError(f"{relative}: expected a task proposal directly under {prefix}")
    return repository.path(relative, "file")


def outcome_path(relative: str) -> str:
    return relative.removesuffix(".md") + OUTCOME_SUFFIX


def read_outcome(repository: Repository, relative: str, sha256: str) -> Outcome | None:
    path = repository.path(outcome_path(relative))
    if not path.exists():
        return None
    record = validate_outcome(decode(path.read_bytes(), str(path)))
    if record.proposal != relative or record.proposal_sha256 != sha256:
        raise FormatError(f"{relative}: decided task request changed")
    return record


def preview_task(root: Path, project: str, relative: str) -> TaskPlan:
    repository = Repository(root)
    raw = request_path(repository, project, relative).read_bytes()
    request = validate_task_request(decode(raw, relative))
    task_id = request.task_id or f"{project}-{Path(relative).stem}"
    if len(task_id) > 128:
        raise FormatError("task_id: derived identifier exceeds 128 characters; give task_id")
    return TaskPlan(relative, digest(raw), request, task_id, {})


def task_inventory(root: Path, project: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    repository = Repository(root)
    repository.project(project)
    folder = repository.path(f"projects/{project}/runs/proposals")
    pending: list[str] = []
    errors: list[str] = []
    if not folder.exists():
        return (), ()
    for path in sorted(folder.glob("task-*.md")):
        if path.name.endswith(OUTCOME_SUFFIX):
            continue
        relative = path.relative_to(repository.root).as_posix()
        try:
            raw = request_path(repository, project, relative).read_bytes()
            marker = read_outcome(repository, relative, digest(raw))
            if marker is None or marker.disposition == "applying":
                pending.append(relative)
        except (OSError, ValueError) as error:
            errors.append(str(error))
    return tuple(pending), tuple(errors)


def task_summaries(root: Path, project: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """File-derived submission/import facts; no scientific acceptance is inferred."""
    summaries: list[str] = []
    errors: list[str] = []
    repository = Repository(root)
    repository.project(project)
    folder = repository.path(f"projects/{project}/runs/proposals")
    if not folder.exists():
        return (), ()
    for path in sorted(folder.glob("task-*.md")):
        if path.name.endswith(OUTCOME_SUFFIX):
            continue
        relative = path.relative_to(repository.root).as_posix()
        try:
            raw = request_path(repository, project, relative).read_bytes()
            marker = read_outcome(repository, relative, digest(raw))
            if marker is None:
                summaries.append(f"Engineering task draft: {path.name} (awaiting researcher)")
                continue
            if marker.disposition in {"rejected", "failed"}:
                summaries.append(f"Engineering task {path.name}: {marker.disposition}")
                continue
            task_id = preview_task(root, project, relative).task_id
            text = f"Engineering task {task_id}: {marker.disposition}"
            stamp = (
                datetime.fromisoformat(marker.at.replace("Z", "+00:00"))
                .astimezone(UTC)
                .strftime("%Y%m%dT%H%M%SZ")
            )
            record_path = (
                f"projects/{project}/runs/{stamp}-task-"
                f"{marker.proposal_sha256[:12]}-result/import.json"
            )
            result = repository.path(record_path)
            if result.exists():
                from toulmin.protocols.engineering_task_import import read_task_import

                record, _ = read_task_import(repository, record_path.rsplit("/", 1)[0])
                if (
                    record.task_id != task_id
                    or record.request != relative
                    or record.request_sha256 != digest(raw)
                ):
                    raise FormatError("engineering import differs from its request")
                text += f"; import {record.disposition}"
                if record.run is not None:
                    text += f" as {record.run}"
            if marker.disposition == "applied":
                text += "; Chief output is not independent acceptance"
            summaries.append(text)
        except (OSError, ValueError) as error:
            errors.append(str(error))
    return tuple(summaries), tuple(errors)


def write_task_draft(
    root: Path,
    project: str,
    *,
    name: str | None = None,
    repo: str | None = None,
    source: str | None = None,
    tool: str = "codex",
    budget: dict[str, int | float] | None = None,
    trust: bool = False,
    command: str | None = None,
) -> Path:
    repository = Repository(root)
    repository.project(project)
    if name is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise FormatError("name: expected 1–64 letters, digits, underscores or hyphens")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"task-{stamp}" + (f"-{name}" if name else "") + ".md"
    folder = repository.path(f"projects/{project}/runs/proposals")
    if not folder.exists():
        folder.mkdir()
    fields: list[tuple[str, Any]] = [
        ("schema_version", 1),
        ("kind", "task-request"),
        ("source", source),
        ("repo", repo),
        ("baseline", "HEAD"),
        ("tool", tool),
        ("checks", ["<fill: executable command that fails on an incorrect result>"]),
        ("protected", []),
        ("budget", budget or {"rounds": 15, "hours": 4}),
        ("test_first", True),
        ("trust", trust),
    ]
    if command is not None:
        fields.append(("command", command))
    body = (
        "## Goal\n<fill: concrete engineering result>\n\n"
        "## Scope\n<fill: included work and boundaries; identify protected paths above>\n"
    )
    path = repository.path(f"projects/{project}/runs/proposals/{filename}")
    write_atomic(path, (header(fields) + body).encode(), replace=False)
    return path


def write_task_outcome(repository: Repository, marker: Outcome, *, replace_existing: bool) -> None:
    validate_outcome(decode(render_outcome(marker), "task outcome"))
    write_atomic(
        repository.path(outcome_path(marker.proposal)),
        render_outcome(marker),
        replace=replace_existing,
    )


def finish_task(
    repository: Repository, marker: Outcome, task_id: str, failure: str | None = None
) -> Outcome:
    done = replace(
        marker,
        disposition="failed" if failure else "applied",
        reason=failure,
        result=None if failure else f"chief task {task_id}",
    )
    write_task_outcome(repository, done, replace_existing=True)
    return done


def new_marker(plan: TaskPlan, actor: str, approval_text: str) -> Outcome:
    if not actor.strip() or not approval_text.strip():
        raise FormatError("actor and approval_text must be nonempty")
    return Outcome(
        plan.path,
        plan.sha256,
        "applying",
        actor,
        utc_text(datetime.now(UTC)),
        approval_text,
        None,
        None,
    )
