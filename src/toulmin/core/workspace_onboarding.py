"""WO2's portable source observations, understanding and sealed outer envelope (L1).

No identity observation or external execution occurs here. Digests refer to exact
bytes; a valid seal does not authorize an otherwise invalid semantic operation.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from toulmin.core.atomic import digest
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError, sections
from toulmin.core.identifiers import validate_project_name
from toulmin.core.repository import Repository
from toulmin.core.scope import Scope
from toulmin.core.sources import SOURCE_ID

PACKET_DIR = re.compile(
    r"runs/[0-9]{8}T[0-9]{6}Z-(onboard|understanding|source|derive|catalog)-[0-9a-f]{32}"
)
SHA = re.compile(r"[0-9a-f]{64}")
MAX_BYTES = 1_000_000
LIMITS = {"files": 400, "bytes": 512000, "file_bytes": 32000, "candidates": 3200}
HEADINGS = ("Structure", "Entry points", "Current behavior", "Checks", "Known gaps")
PIN_KEYS = {
    "source",
    "catalog_sha256",
    "definition_sha256",
    "identity",
    "snapshot",
    "snapshot_sha256",
    "head",
}
PACKET_KEYS = {
    "schema_version",
    "kind",
    "operation",
    "scope",
    "created",
    "origin",
    "mode",
    "project",
    "creation",
    "catalog_version",
    "inputs",
    "preconditions",
    "images",
    "inventories",
    "source_actions",
    "association_changes",
    "notes",
    "rationale",
}
OPERATIONS = {
    "onboarding",
    "understanding-update",
    "source-change",
    "child-derive",
    "catalog-upgrade",
}


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    ).encode()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key}")
        result[key] = value
    return result


def json_data(data: bytes, location: str) -> dict[str, Any]:
    try:
        if len(data) > MAX_BYTES or b"\r" in data:
            raise ValueError("expected LF data, at most 1,000,000 bytes")
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
        if not isinstance(value, dict):
            raise ValueError("expected JSON mapping")
        return value
    except (ValueError, UnicodeError, RecursionError) as error:
        raise FormatError(f"{location}: {error}") from error


def exact(value: Any, keys: set[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise FormatError(f"{location}: expected exactly {', '.join(sorted(keys))}")
    return value


def text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise FormatError(f"{location}: expected nonempty text")
    return value


def checksum(value: Any, location: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise FormatError(f"{location}: expected SHA-256")
    return value


def portable(value: Any, location: str) -> str:
    result = text(value, location)
    value = result
    path = PurePosixPath(result)
    if (
        path.is_absolute()
        or "\\" in value
        or ":" in value
        or any(ord(c) < 32 for c in value)
        or any(p in {"", ".", ".."} for p in value.split("/"))
    ):
        raise FormatError(f"{location}: expected portable relative path")
    return result


def utc(value: Any, location: str) -> str:
    result = text(value, location)
    try:
        offset = datetime.fromisoformat(result).utcoffset()
        if not result.endswith("Z") or offset is None or offset.total_seconds() != 0:
            raise ValueError("expected UTC time ending Z")
    except ValueError as error:
        raise FormatError(f"{location}: expected RFC 3339 UTC time") from error
    return result


def author(value: Any) -> None:
    if not isinstance(value, dict):
        raise FormatError("origin/source: expected operational Author")
    if value.get("kind") == "human":
        exact(value, {"kind", "actor"}, "author")
        text(value["actor"], "author.actor")
    elif value.get("kind") == "model":
        exact(value, {"kind", "model", "session_id"}, "author")
        for key in ("model", "session_id"):
            if value[key] is not None:
                text(value[key], f"author.{key}")
    else:
        raise FormatError("author: expected human or model provenance")


def source_pin(value: Any) -> dict[str, Any]:
    validated = exact(value, PIN_KEYS, "source_pin")
    value = validated
    if not isinstance(value["source"], str) or not SOURCE_ID.fullmatch(value["source"]):
        raise FormatError("source_pin.source: invalid source ID")
    for key in ("catalog_sha256", "definition_sha256", "snapshot_sha256"):
        checksum(value[key], f"source_pin.{key}")
    portable(value["snapshot"], "source_pin.snapshot")
    if not re.fullmatch(r"(git|directory):[0-9a-f]{64}", text(value["identity"], "identity")):
        raise FormatError("source_pin.identity: invalid logical identity")
    head = value["head"]
    if head is not None and (
        not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head)
    ):
        raise FormatError("source_pin.head: expected full commit or null")
    if (head is None) != value["identity"].startswith("directory:"):
        raise FormatError("source_pin: kind and head disagree")
    return validated


def _inventory(data: bytes, location: str) -> dict[str, Any]:
    value = json_data(data, location)
    exact(
        value,
        {
            "schema_version",
            "kind",
            "identity",
            "observed_at",
            "head",
            "status",
            "files",
            "truncated",
            "read_bytes",
            "limits",
            "coverage",
            "exclusions",
        },
        location,
    )
    if type(value["schema_version"]) is not int or value["schema_version"] != 2:
        raise FormatError(f"{location}: expected inventory version 2")
    if value["kind"] not in {"git", "directory"}:
        raise FormatError(f"{location}: invalid source kind")
    if not re.fullmatch(value["kind"] + r":[0-9a-f]{64}", text(value["identity"], "identity")):
        raise FormatError(f"{location}: invalid identity")
    utc(value["observed_at"], "observed_at")
    if (
        type(value["truncated"]) is not bool
        or type(value["read_bytes"]) is not int
        or not 0 <= value["read_bytes"] <= LIMITS["bytes"]
    ):
        raise FormatError(f"{location}: invalid bounds")
    if value["limits"] != LIMITS or any(type(v) is not int for v in value["limits"].values()):
        raise FormatError(f"{location}: incorrect inventory limits")
    text(value["coverage"], "coverage")
    if not isinstance(value["exclusions"], list) or any(
        not isinstance(v, str) for v in value["exclusions"]
    ):
        raise FormatError(f"{location}: exclusions must be strings")
    if value["kind"] == "git":
        if (
            not isinstance(value["head"], str)
            or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value["head"])
            or not isinstance(value["status"], str)
        ):
            raise FormatError(f"{location}: unavailable Git HEAD/status")
    elif value["head"] is not None or value["status"] is not None:
        raise FormatError(f"{location}: directory cannot have Git observations")
    if not isinstance(value["files"], list) or len(value["files"]) > LIMITS["files"]:
        raise FormatError(f"{location}: invalid file list")
    names = set()
    for item in value["files"]:
        if not isinstance(item, dict) or set(item) not in (
            {"path", "bytes"},
            {"path", "bytes", "sha256", "text"},
        ):
            raise FormatError(f"{location}: invalid inventory item")
        path = portable(item["path"], "files.path")
        if path in names or type(item["bytes"]) is not int or item["bytes"] < 0:
            raise FormatError(f"{location}: duplicate path or invalid size")
        names.add(path)
        if "sha256" in item:
            checksum(item["sha256"], "files.sha256")
            if not isinstance(item["text"], str):
                raise FormatError(f"{location}: invalid text")
    return value


def inventory(data: bytes, location: str) -> dict[str, Any]:
    try:
        return _inventory(data, location)
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise FormatError(f"{location}: invalid inventory: {error}") from error


def overview(data: bytes, location: str) -> dict[str, Any]:
    if len(data) > MAX_BYTES:
        raise FormatError(f"{location}: overview exceeds 1,000,000 bytes")
    document = decode(data, location)
    h = exact(
        document.header,
        {
            "schema_version",
            "kind",
            "scope",
            "revision",
            "receipt",
            "source",
            "recorded_at",
            "coverage",
            "limits",
            "sources",
            "supersedes",
        },
        location,
    )
    if (
        type(h["schema_version"]) is not int
        or h["schema_version"] != 1
        or h["kind"] != "workspace-overview"
        or Scope.from_data(h["scope"]) != Scope()
    ):
        raise FormatError(f"{location}: expected workspace-overview version 1, workspace scope")
    if type(h["revision"]) is not int or h["revision"] < 1:
        raise FormatError(f"{location}: invalid overview revision")
    receipt = portable(h["receipt"], "receipt")
    if not receipt.endswith("/receipt.md") or not PACKET_DIR.fullmatch(
        receipt.removesuffix("/receipt.md")
    ):
        raise FormatError(f"{location}: receipt must name the enclosing reviewed packet")
    author(h["source"])
    utc(h["recorded_at"], "recorded_at")
    text(h["coverage"], "coverage")
    if (
        not isinstance(h["limits"], list)
        or not h["limits"]
        or any(not isinstance(s, str) or not s.strip() for s in h["limits"])
    ):
        raise FormatError(f"{location}: nonempty limits required")
    if not isinstance(h["sources"], list) or not h["sources"]:
        raise FormatError(f"{location}: source pins required")
    ids = [source_pin(item)["source"] for item in h["sources"]]
    if len(ids) != len(set(ids)):
        raise FormatError(f"{location}: duplicate source pins")
    if h["supersedes"] is not None:
        portable(h["supersedes"], "supersedes")
    found = sections(document)
    if tuple(found) != HEADINGS or any(not body.strip() for body in found.values()):
        raise FormatError(f"{location}: expected nonempty ordered overview headings {HEADINGS}")
    if "<fill:" in document.body or re.search(r"(?:^|\s)/[^\s]+", document.body):
        raise FormatError(f"{location}: unfilled or absolute local references in overview")
    return h


@dataclass(frozen=True)
class Loaded:
    directory: str
    seal: str
    data: dict[str, Any]

    @property
    def project(self) -> str | None:
        value = self.data["project"]
        return value if isinstance(value, str) else None


def _envelope(data: bytes, location: str) -> dict[str, Any]:
    value = exact(json_data(data, location), PACKET_KEYS, location)
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 2
        or value["kind"] != "workspace-onboarding"
    ):
        raise FormatError(f"{location}: unsupported workspace packet")
    if (
        value["operation"] not in OPERATIONS
        or Scope.from_data(value["scope"]) != Scope()
        or type(value["catalog_version"]) is not int
        or value["catalog_version"] != 2
    ):
        raise FormatError(f"{location}: invalid operation/scope/catalog version")
    utc(value["created"], "created")
    author(value["origin"])
    text(value["rationale"], "rationale")
    mode = value["mode"]
    if (value["operation"] == "onboarding" and mode not in {"A", "B", "C"}) or (
        value["operation"] != "onboarding" and mode is not None
    ):
        raise FormatError(f"{location}: invalid mode")
    child = mode in {"B", "C"} or value["operation"] == "child-derive"
    if child:
        validate_project_name(text(value["project"], "project"))
        creation = exact(value["creation"], {"path", "seal"}, "creation")
        if not re.fullmatch(
            r"runs/[0-9]{8}T[0-9]{6}Z-project-[0-9a-f]{32}",
            portable(creation["path"], "creation.path"),
        ):
            raise FormatError("creation.path: expected v1 child creation archive")
        checksum(creation["seal"], "creation.seal")
    elif value["project"] is not None or value["creation"] is not None:
        raise FormatError(f"{location}: child not allowed for this operation")
    for key in (
        "inputs",
        "preconditions",
        "images",
        "inventories",
        "source_actions",
        "association_changes",
    ):
        if not isinstance(value[key], list):
            raise FormatError(f"{location}.{key}: expected array")
    for key in ("inputs", "preconditions"):
        seen = set()
        for item in value[key]:
            exact(item, {"path", "sha256"}, key)
            path = portable(item["path"], key)
            checksum(item["sha256"], key, nullable=key == "preconditions")
            if path in seen:
                raise FormatError(f"{location}: duplicate {key} path")
            seen.add(path)
    seen = set()
    for item in value["images"]:
        exact(item, {"path", "before", "after", "before_image", "after_image"}, "image")
        path = portable(item["path"], "image.path")
        if path in seen:
            raise FormatError(f"{location}: duplicate image target")
        seen.add(path)
        checksum(item["before"], "image.before", nullable=True)
        checksum(item["after"], "image.after")
        portable(item["after_image"], "image.after_image")
        if (item["before"] is None) != (item["before_image"] is None):
            raise FormatError("image: before bytes/digest disagree")
        if item["before_image"] is not None:
            portable(item["before_image"], "image.before_image")
    for item in value["inventories"]:
        exact(item, {"source", "path", "sha256"}, "inventory")
        if not isinstance(item["source"], str) or not SOURCE_ID.fullmatch(item["source"]):
            raise FormatError("inventory.source: invalid ID")
        portable(item["path"], "inventory.path")
        checksum(item["sha256"], "inventory.sha256")
    for item in value["source_actions"]:
        exact(item, {"source", "action", "definition_sha256"}, "source_action")
        if (
            not isinstance(item["source"], str)
            or not SOURCE_ID.fullmatch(item["source"])
            or item["action"] not in {"register", "reuse"}
        ):
            raise FormatError("source_actions: invalid source/action")
        checksum(item["definition_sha256"], "source_action.definition_sha256")
    for item in value["association_changes"]:
        exact(item, {"scope", "source", "before", "after"}, "association_change")
        Scope.from_data(item["scope"])
        if (
            not isinstance(item["source"], str)
            or not SOURCE_ID.fullmatch(item["source"])
            or item["before"] not in {None, "reference", "working"}
            or item["after"] not in {"reference", "working"}
        ):
            raise FormatError("association_changes: invalid source/roles")
    if value["notes"] is not None:
        exact(value["notes"], {"path", "sha256"}, "notes")
        portable(value["notes"]["path"], "notes.path")
        checksum(value["notes"]["sha256"], "notes.sha256")
    return value


def envelope(data: bytes, location: str) -> dict[str, Any]:
    try:
        return _envelope(data, location)
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise FormatError(f"{location}: invalid workspace packet: {error}") from error


def load_envelope(repository: Repository, directory: str) -> Loaded:
    directory = repository.relative(directory).removesuffix("/packet.md").rstrip("/")
    if not PACKET_DIR.fullmatch(directory):
        raise FormatError(f"{directory}: expected reviewed workspace v2 packet")
    raw = repository.path(f"{directory}/packet.md", "file").read_bytes()
    seal = repository.path(f"{directory}/seal", "file").read_bytes()
    if seal != (digest(raw) + "\n").encode():
        raise FormatError(f"{directory}: packet changed after preview; seal mismatch")
    return Loaded(directory, digest(raw), envelope(raw, f"{directory}/packet.md"))


def owners(repository: Repository, creation: str) -> tuple[str, ...]:
    """Discover sealed outer ownership independently of a missing/changed marker."""
    found = []
    for path in sorted(repository.path("runs", "directory").glob("*/packet.md")):
        relative = path.parent.relative_to(repository.root).as_posix()
        if not PACKET_DIR.fullmatch(relative) or not (path.parent / "seal").exists():
            continue
        raw = repository.path(f"{relative}/packet.md", "file").read_bytes()
        if json_data(raw, relative).get("schema_version") == 1:
            continue
        loaded = load_envelope(repository, relative)
        reference = loaded.data["creation"]
        if reference is not None and reference["path"] == creation:
            found.append(relative)
    return tuple(found)
