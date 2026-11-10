"""Tool-independent snapshots injected by integration readers; missing facts stay unknown."""

import json
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime

from toulmin.core.documents import FormatError
from toulmin.core.identifiers import ObjectId, ObjectKind, ObjectRef


@dataclass(frozen=True)
class BuildReview:
    verdict: str | None = None
    summary: str | None = None
    head: str | None = None
    by: str | None = None


@dataclass(frozen=True)
class BuildTask:
    state: str | None = None
    review: BuildReview = field(default_factory=BuildReview)
    branch: str | None = None
    base: str | None = None
    worktree: str | None = None
    session_id: str | None = None
    tool: str | None = None
    repo: str | None = None
    closed_at: str | None = None
    error: str | None = None
    kickoff_at: bool = False  # presence of the external field, not its timestamp value


@dataclass(frozen=True)
class BuildImport:
    """Frozen workspace-side import journal/receipt, independent of external state."""

    spec: str
    task_id: str
    request: str
    request_sha256: str
    actor: str
    at: str
    state: str
    claim: str
    head: str | None
    verdict: str | None
    reviewer: str | None
    tool: str | None
    session_id: str | None
    files: dict[str, str]
    disposition: str = "applying"
    run: str | None = None
    proposals: tuple[str, ...] = ()


def render_import(record: BuildImport) -> bytes:
    return (
        json.dumps(
            {"schema_version": 1, "kind": "build-import", **asdict(record)},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode()


def parse_import(data: bytes, location: str) -> BuildImport:
    try:
        raw = json.loads(data)
        names = {item.name for item in fields(BuildImport)}
        if not isinstance(raw, dict) or set(raw) != names | {"schema_version", "kind"}:
            raise ValueError("expected the build-import record fields")
        version = raw.pop("schema_version")
        if type(version) is not int or version != 1 or raw.pop("kind") != "build-import":
            raise ValueError("expected schema_version 1 and kind build-import")
        for name in names - {
            "head",
            "verdict",
            "reviewer",
            "tool",
            "session_id",
            "files",
            "run",
            "proposals",
        }:
            if not isinstance(raw[name], str) or not raw[name].strip():
                raise ValueError(f"{name}: expected nonempty text")
        for name in ("head", "verdict", "reviewer", "tool", "session_id", "run"):
            if raw[name] is not None and (not isinstance(raw[name], str) or not raw[name].strip()):
                raise ValueError(f"{name}: expected text or null")
        if raw["state"] not in {"done", "abandoned"} or raw["disposition"] not in {
            "applying",
            "applied",
        }:
            raise ValueError("invalid import state/disposition")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", raw["task_id"]):
            raise ValueError("invalid task_id")
        if not re.fullmatch(r"[0-9a-f]{64}", raw["request_sha256"]):
            raise ValueError("invalid request_sha256")
        if ObjectId.parse(raw["spec"]).kind != ObjectKind.SPEC:
            raise ValueError("expected a Spec")
        if ObjectRef.parse(raw["claim"]).object_id.kind != ObjectKind.CLAIM:
            raise ValueError("expected a Claim")
        if raw["run"] is not None and ObjectId.parse(raw["run"]).kind != ObjectKind.RUN:
            raise ValueError("expected a Run")
        if datetime.fromisoformat(raw["at"].replace("Z", "+00:00")).utcoffset() is None:
            raise ValueError("at: timezone required")
        files = raw["files"]
        if not isinstance(files, dict) or not files:
            raise ValueError("files: expected artifact digests")
        for name, sha in files.items():
            if (
                name not in {"task.md", "commits.txt", "diffstat.txt", "review.md", "progress.md"}
                or not isinstance(sha, str)
                or not re.fullmatch(r"[0-9a-f]{64}", sha)
            ):
                raise ValueError("files: invalid artifact/digest")
        if not {"task.md", "commits.txt", "diffstat.txt", "review.md"} <= files.keys():
            raise ValueError("files: required artifacts missing")
        proposals = raw["proposals"]
        if not isinstance(proposals, list) or any(
            not isinstance(name, str) or "/" in name or "\\" in name for name in proposals
        ):
            raise ValueError("proposals: expected filenames")
        raw["proposals"] = tuple(proposals)
        if raw["disposition"] == "applied" and raw["run"] is None:
            raise ValueError("applied import must name its Run")
        return BuildImport(**raw)
    except (ValueError, TypeError, KeyError) as error:
        raise FormatError(f"{location}: import: {error}") from error
