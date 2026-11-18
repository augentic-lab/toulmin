"""Versioned scoped engineering requests and imports; provider-independent L1 data."""

from dataclasses import dataclass, replace
from typing import Any

from toulmin.core.documents import Document, FormatError
from toulmin.core.engineering_tasks import TaskImport, TaskRequest, validate_task_request
from toulmin.core.scope import WORKSPACE, Scope
from toulmin.core.workspace_onboarding import (
    canonical,
    checksum,
    exact,
    json_data,
    portable,
    source_pin,
    utc,
)
from toulmin.core.workspace_onboarding import (
    scope as parse_scope,
)


@dataclass(frozen=True)
class ScopedTask:
    scope: Scope
    pin: dict[str, Any]
    request: TaskRequest


def validate_request(document: Document) -> ScopedTask:
    h = document.header
    required = {
        "schema_version",
        "kind",
        "scope",
        "source",
        "source_pin",
        "baseline",
        "tool",
        "checks",
        "protected",
        "budget",
        "test_first",
        "trust",
    }
    if set(h) - required - {"task_id", "command"} or required - set(h):
        document.fail(
            "header", "expected exact scoped task-request v2 fields; repo is not portable"
        )
    if type(h["schema_version"]) is not int or h["schema_version"] != 2:
        document.fail("schema_version", "expected scoped task-request version 2")
    scope = parse_scope(h["scope"], "task.scope")
    pin = source_pin(h["source_pin"])
    if h["source"] != pin["source"]:
        document.fail("source", "request/source pin IDs disagree")
    legacy = {key: value for key, value in h.items() if key not in {"scope", "source_pin"}}
    legacy["schema_version"] = 1
    validated = validate_task_request(replace(document, header=legacy))
    return ScopedTask(scope, pin, validated)


@dataclass(frozen=True)
class ScopedImport(TaskImport):
    scope: Scope = WORKSPACE
    source_pin: dict[str, Any] | None = None
    submission_sha256: str = ""


def render_import(record: ScopedImport) -> bytes:
    from dataclasses import asdict

    value = {"schema_version": 2, "kind": "task-import", **asdict(record)}
    value["scope"] = record.scope.to_data()
    return canonical(value)


def parse_import(data: bytes, location: str) -> ScopedImport:
    from toulmin.core.engineering_tasks import parse_task_import

    value = json_data(data, location)
    expected = set(TaskImport.__dataclass_fields__) | {
        "schema_version",
        "kind",
        "scope",
        "source_pin",
        "submission_sha256",
    }
    exact(value, expected, location)
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 2
        or value["kind"] != "task-import"
    ):
        raise FormatError(f"{location}: expected scoped task-import v2")
    scope = parse_scope(value["scope"], "task-import.scope")
    pin = source_pin(value["source_pin"])
    checksum(value["submission_sha256"], "submission_sha256")
    utc(value["at"], "at")
    run = value["run"]
    if scope.project is None and run is not None:
        portable(run, "run")
        if not run.startswith("runs/") or not run.endswith("-result/run.md"):
            raise FormatError("workspace import run must be an operational result run.md")
    legacy = {
        key: item
        for key, item in value.items()
        if key not in {"scope", "source_pin", "submission_sha256"}
    }
    legacy["schema_version"] = 1
    # The v1 validator checks common fields/artifacts; only project Runs use its ID namespace.
    legacy["run"] = "R-001" if scope.project is None and run is not None else run
    parsed = parse_task_import(canonical(legacy), location)
    from dataclasses import asdict

    common = asdict(parsed)
    common["run"] = run
    return ScopedImport(
        **common, scope=scope, source_pin=pin, submission_sha256=value["submission_sha256"]
    )
