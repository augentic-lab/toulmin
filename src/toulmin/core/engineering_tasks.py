"""O4 engineering task requests: independent of scientific objects and external tools."""

import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from typing import Any

from toulmin.core.documents import Document, FormatError, sections, validate_values
from toulmin.core.identifiers import ObjectId, ObjectKind
from toulmin.core.schema import mapping, strings, text

TASK_FILENAME = re.compile(r"task-[0-9]{8}T[0-9]{6}Z(?:-[A-Za-z0-9][A-Za-z0-9_-]{0,63})?\.md")
TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


@dataclass(frozen=True)
class TaskRequest:
    source: str | None
    repo: str | None
    baseline: str
    task_id: str | None
    tool: str
    checks: tuple[str, ...]
    protected: tuple[str, ...]
    budget: dict[str, int | float]
    goal: str
    scope: str
    test_first: bool = True
    trust: bool = False
    command: str | None = None


def validate_task_request(document: Document) -> TaskRequest:
    validate_values(document)
    h = mapping(
        document,
        document.header,
        "",
        {"schema_version", "kind", "baseline", "tool", "checks", "protected", "budget"},
        {"source", "repo", "task_id", "test_first", "trust", "command"},
    )
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    if h["kind"] != "task-request":
        document.fail("kind", "expected task-request")

    def filled(value: Any, field: str) -> str:
        result = text(document, value, field)
        if "<fill:" in result or any(ord(c) < 32 for c in result):
            document.fail(field, "expected filled text without control characters")
        return result

    repo = filled(h["repo"], "repo") if h.get("repo") is not None else None
    if repo is not None and not repo.startswith("/"):
        document.fail("repo", "expected an absolute repository path")
    source = filled(h["source"], "source") if h.get("source") is not None else None
    if repo is None and source is None:
        document.fail("source", "give a source identifier or an explicit repo path")
    baseline = filled(h["baseline"], "baseline")
    if baseline.startswith("-"):
        document.fail("baseline", "expected a commit or revision, not an option")
    task_id = filled(h["task_id"], "task_id") if h.get("task_id") is not None else None
    if task_id is not None and not TASK_ID.fullmatch(task_id):
        document.fail("task_id", "expected a safe Chief task identifier")
    checks = tuple(strings(document, h["checks"], "checks", nonempty=True))
    for check in checks:
        if "<fill:" in check or "\x00" in check:
            document.fail("checks", "expected filled executable checks")
    protected = tuple(strings(document, h["protected"], "protected"))
    for path in protected:
        if (
            path.startswith("/")
            or "\\" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or any(ord(c) < 32 for c in path)
        ):
            document.fail("protected", "expected repository-relative paths without traversal")
    budget = mapping(document, h["budget"], "budget", {"rounds", "hours"})
    if type(budget["rounds"]) is not int or budget["rounds"] <= 0:
        document.fail("budget.rounds", "expected a positive integer")
    if type(budget["hours"]) not in {int, float} or not 0 < budget["hours"] < float("inf"):
        document.fail("budget.hours", "expected a positive finite number")
    for flag in ("trust", "test_first"):
        if flag in h and type(h[flag]) is not bool:
            document.fail(flag, "expected true or false")
    command = h.get("command")
    if command is not None and not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.+-]*", filled(command, "command")
    ):
        document.fail("command", "expected a bare program name on PATH")
    body = sections(document)
    if set(body) != {"Goal", "Scope"}:
        document.fail("body", "expected Goal and Scope sections")
    for heading in ("Goal", "Scope"):
        if not body[heading].strip() or "<fill:" in body[heading]:
            document.fail(f"body.{heading}", "fill the section before requesting a task")
    return TaskRequest(
        source,
        repo,
        baseline,
        task_id,
        filled(h["tool"], "tool"),
        checks,
        protected,
        dict(budget),
        body["Goal"].strip(),
        body["Scope"].strip(),
        h.get("test_first", True),
        h.get("trust", False),
        command,
    )


@dataclass(frozen=True)
class TaskImport:
    task_id: str
    request: str
    request_sha256: str
    actor: str
    at: str
    state: str
    head: str | None
    tool: str | None
    command: str | None
    session_id: str | None
    files: dict[str, str]
    disposition: str = "applying"
    run: str | None = None


def render_task_import(record: TaskImport) -> bytes:
    from toulmin.core.scoped_tasks import ScopedImport, render_import

    if isinstance(record, ScopedImport):
        return render_import(record)
    return (
        json.dumps(
            {"schema_version": 1, "kind": "task-import", **asdict(record)},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode()


def parse_task_import(data: bytes, location: str) -> TaskImport:
    from toulmin.core.scoped_tasks import parse_import

    try:
        probe = json.loads(data)
    except (ValueError, UnicodeError) as error:
        raise FormatError(f"{location}: task import: {error}") from error
    if isinstance(probe, dict) and probe.get("schema_version") == 2:
        return parse_import(data, location)
    try:
        raw = json.loads(data)
        names = {item.name for item in fields(TaskImport)}
        if not isinstance(raw, dict) or set(raw) != names | {"schema_version", "kind"}:
            raise ValueError("expected the task-import fields")
        version = raw.pop("schema_version")
        if type(version) is not int or version != 1 or raw.pop("kind") != "task-import":
            raise ValueError("expected schema_version 1 and kind task-import")
        for name in names - {"head", "tool", "command", "session_id", "files", "run"}:
            if not isinstance(raw[name], str) or not raw[name].strip():
                raise ValueError(f"{name}: expected nonempty text")
        for name in ("head", "tool", "command", "session_id", "run"):
            if raw[name] is not None and (not isinstance(raw[name], str) or not raw[name].strip()):
                raise ValueError(f"{name}: expected text or null")
        if not TASK_ID.fullmatch(raw["task_id"]):
            raise ValueError("invalid task_id")
        if not re.fullmatch(r"[0-9a-f]{64}", raw["request_sha256"]):
            raise ValueError("invalid request_sha256")
        if raw["state"] not in {"done", "abandoned"} or raw["disposition"] not in {
            "applying",
            "applied",
        }:
            raise ValueError("invalid state or disposition")
        if datetime.fromisoformat(raw["at"].replace("Z", "+00:00")).utcoffset() is None:
            raise ValueError("at: timezone required")
        files = raw["files"]
        required = {"task.md", "commits.txt", "diffstat.txt", "review.md", "contract.json"}
        if (
            not isinstance(files, dict)
            or not required <= files.keys()
            or files.keys() - required - {"progress.md", "checks.json", "events.jsonl"}
        ):
            raise ValueError("invalid artifact set")
        if any(
            not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
            for value in files.values()
        ):
            raise ValueError("invalid artifact digest")
        if raw["run"] is not None and ObjectId.parse(raw["run"]).kind != ObjectKind.RUN:
            raise ValueError("expected a Run ID")
        if raw["disposition"] == "applied" and raw["run"] is None:
            raise ValueError("applied import must name a Run")
        return TaskImport(**raw)
    except (ValueError, TypeError, KeyError) as error:
        raise FormatError(f"{location}: task import: {error}") from error
