"""L1: frozen deterministic verification attempts; no tool execution or file access."""

import json
import math
import re
from dataclasses import asdict, dataclass, fields
from datetime import datetime

from toulmin.core.documents import FormatError
from toulmin.core.identifiers import ObjectId, ObjectKind, ObjectRef

STREAM_LIMIT = 64 * 1024


@dataclass(frozen=True)
class CheckResult:
    command: str
    exit_status: int | None
    duration_seconds: float
    stdout: str
    stderr: str
    stdout_truncated: bool = False
    stderr_truncated: bool = False


@dataclass(frozen=True)
class BuildVerification:
    spec: str
    task_id: str
    import_archive: str
    contract: str
    contract_sha256: str
    spec_sha256: str
    repo: str
    head: str
    claim: str
    checks: tuple[str, ...]
    timeout_seconds: float
    actor: str
    at: str
    results: tuple[CheckResult, ...] = ()
    files: dict[str, str] | None = None
    snapshot: str | None = None
    execution_completed: bool = False
    disposition: str = "applying"
    run: str | None = None
    proposals: tuple[str, ...] = ()
    previous: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return (
            self.execution_completed
            and len(self.results) == len(self.checks)
            and all(result.exit_status == 0 for result in self.results)
        )


def render_verification(record: BuildVerification) -> bytes:
    return (
        json.dumps(
            {"schema_version": 1, "kind": "build-verification", **asdict(record)},
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode()


def parse_verification(data: bytes, location: str) -> BuildVerification:
    try:
        raw = json.loads(data)
        names = {item.name for item in fields(BuildVerification)}
        if not isinstance(raw, dict) or set(raw) != names | {"schema_version", "kind"}:
            raise ValueError("expected the build-verification fields")
        version = raw.pop("schema_version")
        if type(version) is not int or version != 1 or raw.pop("kind") != "build-verification":
            raise ValueError("expected version 1 and kind build-verification")
        for name in (
            "spec",
            "task_id",
            "import_archive",
            "contract",
            "contract_sha256",
            "spec_sha256",
            "repo",
            "head",
            "claim",
            "actor",
            "at",
            "disposition",
        ):
            if not isinstance(raw[name], str) or not raw[name].strip():
                raise ValueError(f"{name}: expected nonempty text")
        if ObjectId.parse(raw["spec"]).kind != ObjectKind.SPEC:
            raise ValueError("expected a Spec")
        if ObjectRef.parse(raw["claim"]).object_id.kind != ObjectKind.CLAIM:
            raise ValueError("expected a Claim")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", raw["task_id"]):
            raise ValueError("invalid task_id")
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", raw["head"]):
            raise ValueError("head must be a pinned commit")
        for name in ("contract_sha256", "spec_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", raw[name]):
                raise ValueError(f"{name}: expected sha256")
        if datetime.fromisoformat(raw["at"].replace("Z", "+00:00")).utcoffset() is None:
            raise ValueError("at: timezone required")
        timeout = raw["timeout_seconds"]
        if type(timeout) not in {int, float} or not 0 < timeout < float("inf"):
            raise ValueError("timeout_seconds: expected a positive finite number")
        if (
            not isinstance(raw["checks"], list)
            or not raw["checks"]
            or any(
                not isinstance(check, str) or not check.strip() or "<fill:" in check
                for check in raw["checks"]
            )
        ):
            raise ValueError("checks: expected nonempty frozen commands without placeholders")
        for name in ("execution_completed",):
            if type(raw[name]) is not bool:
                raise ValueError(f"{name}: expected a Boolean")
        if raw["disposition"] not in {"applying", "applied"}:
            raise ValueError("invalid disposition")
        if raw["run"] is not None and (
            not isinstance(raw["run"], str) or ObjectId.parse(raw["run"]).kind != ObjectKind.RUN
        ):
            raise ValueError("run: expected Run ID or null")
        snapshot = raw["snapshot"]
        if snapshot is not None and (
            not isinstance(snapshot, str) or not re.fullmatch(r"checkpoints/[0-9a-f]{64}", snapshot)
        ):
            raise ValueError("snapshot: expected a checkpoint path or null")
        for name in ("proposals",):
            if not isinstance(raw[name], list) or any(
                not isinstance(value, str) or not value or "/" in value or "\\" in value
                for value in raw[name]
            ):
                raise ValueError(f"{name}: expected filenames")
            raw[name] = tuple(raw[name])
        previous = raw["previous"]
        if not isinstance(previous, list) or any(
            not isinstance(value, str) or not re.fullmatch(r"checkpoints/[0-9a-f]{64}", value)
            for value in previous
        ):
            raise ValueError("previous: expected checkpoint paths")
        raw["previous"] = tuple(previous)
        files = raw["files"]
        if files is not None and (
            not isinstance(files, dict)
            or set(files) != {"output.md", "environment.txt"}
            or any(
                not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                for value in files.values()
            )
        ):
            raise ValueError("files: expected output.md/environment.txt sha256 digests or null")
        if (files is None) != (snapshot is None):
            raise ValueError("checkpoint files and snapshot must be present together")
        results = raw["results"]
        if not isinstance(results, list) or len(results) > len(raw["checks"]):
            raise ValueError("results: expected one result per executed check")
        parsed = []
        for index, item in enumerate(results):
            if not isinstance(item, dict) or set(item) != {
                field.name for field in fields(CheckResult)
            }:
                raise ValueError("invalid check result fields")
            result = CheckResult(**item)
            if result.command != raw["checks"][index]:
                raise ValueError("result command differs from the frozen check")
            if result.exit_status is not None and type(result.exit_status) is not int:
                raise ValueError("exit_status must be an integer or null (timed out)")
            if (
                type(result.duration_seconds) not in {int, float}
                or not math.isfinite(result.duration_seconds)
                or result.duration_seconds < 0
            ):
                raise ValueError("invalid check duration")
            for stream in (result.stdout, result.stderr):
                if not isinstance(stream, str) or len(stream.encode()) > STREAM_LIMIT:
                    raise ValueError("check output must fit within 64 KiB per stream")
            if (
                type(result.stdout_truncated) is not bool
                or type(result.stderr_truncated) is not bool
            ):
                raise ValueError("truncation flags must be Booleans")
            parsed.append(result)
        raw["checks"], raw["results"] = tuple(raw["checks"]), tuple(parsed)
        if raw["execution_completed"] and (len(parsed) != len(raw["checks"]) or files is None):
            raise ValueError("completed execution must include every result and artifact digest")
        if raw["disposition"] == "applied" and (
            not raw["execution_completed"] or raw["run"] is None
        ):
            raise ValueError("applied verification must have completed execution and a Run")
        record = BuildVerification(**raw)
        if record.disposition == "applied" and len(record.proposals) != (3 if record.passed else 0):
            raise ValueError("passing verification requires three proposals; failures require none")
        return record
    except (ValueError, TypeError, KeyError) as error:
        raise FormatError(f"{location}: verification: {error}") from error


@dataclass(frozen=True)
class VerificationFact:
    head: str | None = None
    task_id: str | None = None
    available: bool = False
    passed: bool = False
    failed: bool = False
    archive: str | None = None
    interrupted: bool = False
