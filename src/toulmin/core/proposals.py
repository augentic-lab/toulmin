"""L1 workspace change inputs, sealed packets and receipts (contract section 7).

Pure models and rendering: bytes in, bytes or validated values out. File access,
locking and publication live in L2 and the journal module.
"""

import difflib
import re
from dataclasses import dataclass
from typing import Any

from toulmin.core.codec import decode
from toulmin.core.documents import Document, FormatError, sections, validate_values
from toulmin.core.identifiers import validate_project_name
from toulmin.core.render import fence, header
from toulmin.core.resources import (
    BODY_FIELDS,
    CHANGE_FIELDS,
    HEX,
    KINDS,
    STATUSES,
    validate_location,
    validate_version,
)
from toulmin.core.schema import mapping, text, timestamp
from toulmin.core.workspace import (
    CHARTER_FILE,
    CHARTER_ORDER,
    INITIAL_NOTE,
    SECTIONS,
    validate_name,
)

COVERAGE = ("full", "selected", "summary", "unknown")
PACKET_DIR = re.compile(r"runs/[0-9]{8}T[0-9]{6}Z-proposal-[0-9a-f]{32}")
SEAL = re.compile(r"[0-9a-f]{64}\n")
RESOURCE_TARGET = re.compile(r"shared/resources/([a-z0-9]+(?:-[a-z0-9]+)*)\.md")
RECEIPT_BODY = (
    "Confirmation receipt. It records an administrative approval, not scientific support.\n"
)
NOT_CHANGED = (
    "No project, Claim, Evidence, Decision, stage or handoff is created or changed. A\n"
    "registered resource is not Evidence for any Claim.\n"
)
INPUT_FIELDS = {"schema_version", "kind", "scope", "supersedes", "sources", "pins", "changes"}
PACKET_ORDER = (
    "schema_version",
    "kind",
    "scope",
    "created",
    "input",
    "supersedes",
    "sources",
    "pins",
    "targets",
)
RECEIPT_ORDER = (
    "schema_version",
    "kind",
    "record",
    "record_sha256",
    "disposition",
    "actor",
    "at",
    "approval_text",
    "reason",
    "results",
)
PIN_ORDER = ("resource", "revision", "description_sha256", "path", "url", "method", "sha256")
MAX_BYTES = 1_000_000


@dataclass(frozen=True)
class SourceRef:
    path: str | None
    url: str | None
    coverage: str


@dataclass(frozen=True)
class PinRef:
    resource: str
    revision: int
    sha256: str | None


@dataclass(frozen=True)
class CharterChange:
    name: str | None
    sections: dict[str, str | None]


@dataclass(frozen=True)
class ResourceChange:
    resource: str
    action: str
    values: dict[str, Any]  # only the fields the input supplied


@dataclass(frozen=True)
class ChangeInput:
    supersedes: str | None
    sources: tuple[SourceRef, ...]
    pins: tuple[PinRef, ...]
    charter: CharterChange | None
    resources: tuple[ResourceChange, ...]
    question: str
    assumptions: str


@dataclass(frozen=True)
class Target:
    path: str
    before_sha256: str | None
    after_sha256: str
    after: str


@dataclass(frozen=True)
class PacketSource:
    path: str | None
    url: str | None
    sha256: str | None
    snapshot: str | None
    coverage: str


@dataclass(frozen=True)
class Packet:
    created: str
    input_path: str
    input_sha256: str
    supersedes: str | None
    sources: tuple[PacketSource, ...]
    pins: tuple[dict[str, Any], ...]
    targets: tuple[Target, ...]


@dataclass(frozen=True)
class Receipt:
    record: str
    record_sha256: str
    disposition: str
    actor: str
    at: str
    approval_text: str | None
    reason: str | None
    results: tuple[tuple[str, str | None, str], ...]


def _hex(document: Document, value: Any, field: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not HEX.fullmatch(value):
        document.fail(field, "expected SHA-256 hex digest" + (" or null" if nullable else ""))
    return str(value)


def packet_directory(value: str) -> str:
    """Normalize a packet path (directory or its packet.md) to its directory."""
    directory = value.removesuffix("/").removesuffix("/packet.md")
    if not PACKET_DIR.fullmatch(directory):
        raise FormatError(
            f"{value}: expected a workspace change packet runs/<stamp>-proposal-<hex>"
        )
    return directory


def _source_refs(document: Document, value: Any) -> tuple[SourceRef, ...]:
    if not isinstance(value, list):
        document.fail("sources", "expected list")
    result = []
    for index, item in enumerate(value):
        field = f"sources[{index}]"
        if not isinstance(item, dict) or set(item) not in (
            {"path", "coverage"},
            {"url", "coverage"},
        ):
            document.fail(field, "expected {path, coverage} or {url, coverage}")
        if item["coverage"] not in COVERAGE:
            document.fail(f"{field}.coverage", f"expected one of {', '.join(COVERAGE)}")
        location = text(document, item.get("path", item.get("url")), field)
        if "url" in item and not re.fullmatch(r"https?://\S+", location):
            document.fail(f"{field}.url", "expected http or https URL")
        result.append(SourceRef(item.get("path"), item.get("url"), item["coverage"]))
    return tuple(result)


def _pin_refs(document: Document, value: Any) -> tuple[PinRef, ...]:
    if not isinstance(value, list):
        document.fail("pins", "expected list")
    result = []
    for index, item in enumerate(value):
        field = f"pins[{index}]"
        pin = mapping(document, item, field, {"resource", "revision", "sha256"})
        try:
            validate_project_name(text(document, pin["resource"], f"{field}.resource"))
        except ValueError as error:
            document.fail(f"{field}.resource", str(error))
        if type(pin["revision"]) is not int or pin["revision"] < 1:
            document.fail(f"{field}.revision", "expected integer >= 1")
        sha256 = _hex(document, pin["sha256"], f"{field}.sha256", nullable=True)
        result.append(PinRef(pin["resource"], pin["revision"], sha256))
    if len({pin.resource for pin in result}) != len(result):
        document.fail("pins", "pin each resource at most once")
    return tuple(result)


def validate_change_input(document: Document) -> ChangeInput:
    validate_values(document)
    h = mapping(document, document.header, "", INPUT_FIELDS)
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    if h["kind"] != "workspace-change-input":
        document.fail("kind", "expected workspace-change-input (a change input, not a packet)")
    if h["scope"] != {"kind": "workspace"}:
        document.fail("scope", "workspace changes have scope {kind: workspace}")
    supersedes = h["supersedes"]
    if supersedes is not None:
        try:
            supersedes = packet_directory(text(document, supersedes, "supersedes"))
        except FormatError as error:
            document.fail("supersedes", str(error))
    changes = h["changes"]
    if not isinstance(changes, list) or not changes:
        document.fail("changes", "expected a nonempty list")
    charter: CharterChange | None = None
    resources: list[ResourceChange] = []
    for index, change in enumerate(changes):
        field = f"changes[{index}]"
        if not isinstance(change, dict):
            document.fail(field, "expected mapping")
        target = change.get("target")
        if target == "charter":
            if charter is not None:
                document.fail(field, "at most one charter change per packet")
            charter = _charter_change(document, change, field)
        elif target == "resource":
            resource = _resource_change(document, change, field)
            if any(item.resource == resource.resource for item in resources):
                document.fail(field, "at most one change per resource")
            resources.append(resource)
        else:
            document.fail(f"{field}.target", "only charter and resource changes are allowed")
    body = sections(document)
    for heading in body:
        if heading not in {"Question", "Unresolved assumptions"}:
            document.fail(f"body.{heading}", "expected Question and Unresolved assumptions")
    for heading in ("Question", "Unresolved assumptions"):
        if not body.get(heading, "").strip():
            document.fail(f"body.{heading}", "required section missing or empty")
    return ChangeInput(
        supersedes,
        _source_refs(document, h["sources"]),
        _pin_refs(document, h["pins"]),
        charter,
        tuple(resources),
        body["Question"].strip(),
        body["Unresolved assumptions"].strip(),
    )


def _charter_change(document: Document, change: dict[str, Any], field: str) -> CharterChange:
    item = mapping(document, change, field, {"target"}, {"name", "sections"})
    name = item.get("name")
    if name is not None:
        try:
            validate_name(name)
        except ValueError as error:
            document.fail(f"{field}.name", str(error))
    values = item.get("sections", {})
    if not isinstance(values, dict):
        document.fail(f"{field}.sections", "expected mapping")
    for heading, content in values.items():
        if heading not in SECTIONS:
            document.fail(f"{field}.sections.{heading}", "expected Direction, Constraints or Focus")
        if content is not None:
            text(document, content, f"{field}.sections.{heading}")
            if re.search(r"^## ", content, re.M):
                document.fail(f"{field}.sections.{heading}", "must not contain '## ' headings")
    if name is None and not values:
        document.fail(field, "a charter change needs name or sections")
    return CharterChange(name, dict(values))


def _resource_change(document: Document, change: dict[str, Any], field: str) -> ResourceChange:
    optional = set(CHANGE_FIELDS) | set(BODY_FIELDS)
    item = mapping(document, change, field, {"target", "resource", "action"}, optional)
    try:
        validate_project_name(text(document, item["resource"], f"{field}.resource"))
    except ValueError as error:
        document.fail(f"{field}.resource", str(error))
    if item["action"] not in {"register", "revise"}:
        document.fail(f"{field}.action", "expected register or revise")
    values = {key: item[key] for key in optional if key in item}
    if item["action"] == "register":
        for key in (*CHANGE_FIELDS, "purpose", "limitations"):
            if key not in values:
                document.fail(f"{field}.{key}", "required to register a resource")
    elif not values:
        document.fail(field, "a revision changes at least one field")
    for key in ("title", "origin", "purpose", "limitations"):
        if key in values:
            text(document, values[key], f"{field}.{key}")
            if key in {"purpose", "limitations"} and re.search(r"^## ", values[key], re.M):
                document.fail(f"{field}.{key}", "must not contain '## ' headings")
    if values.get("notes") is not None:
        text(document, values["notes"], f"{field}.notes")
    if "status" in values and values["status"] not in STATUSES:
        document.fail(f"{field}.status", "expected active or withdrawn")
    if "kind" in values and values["kind"] not in KINDS:
        document.fail(f"{field}.kind", f"expected one of {', '.join(KINDS)}")
    return ResourceChange(item["resource"], item["action"], values)


def check_resource_values(document: Document, values: dict[str, Any], field: str) -> None:
    """Validate a complete (merged) set of description values before rendering."""
    path, _ = validate_location(document, values["location"], f"{field}.location")
    validate_version(document, values["version"], f"{field}.version", path)


def charter_after(before: bytes, change: CharterChange, receipt: str) -> bytes:
    """Apply a charter change: patch owned header fields, regenerate the body."""
    document = decode(before)
    current = sections(document)
    merged = {heading: current[heading].strip() for heading in SECTIONS if heading in current}
    for heading, content in change.sections.items():
        if content is None:
            merged.pop(heading, None)
        else:
            merged[heading] = content.strip()
    updates: dict[str, Any] = {
        "charter_revision": document.header["charter_revision"] + 1,
        "charter_receipt": receipt,
    }
    if change.name is not None:
        updates["name"] = change.name
    # Re-rendered, not round-tripped: the charter header is generated and receipt-owned,
    # and a round trip would rewrite untouched nulls as empty values.
    values = {**document.header, **updates}
    head = header([(key, values[key]) for key in CHARTER_ORDER])
    ordered = [heading for heading in SECTIONS if heading in merged]
    body = "\n".join(f"## {heading}\n{merged[heading]}\n" for heading in ordered)
    return (head + (body or INITIAL_NOTE)).encode()


def unified(before: bytes | None, after: bytes, path: str) -> str:
    lines = difflib.unified_diff(
        (before or b"").decode().splitlines(True),
        after.decode().splitlines(True),
        f"a/{path}",
        f"b/{path}",
    )
    return "".join(line if line.endswith("\n") else line + "\n" for line in lines)


def describe_source(source: PacketSource, capture: tuple[str, bool, str | None] | None) -> str:
    """One readable line stating what a source is and how much of it was captured."""
    name = source.path or source.url or "?"
    if capture is None:
        return f"- {name} (coverage: {source.coverage})"
    coverage, complete, limits = capture
    label = {
        "full": "full transcript; complete capture",
        "selected": "selected messages; complete capture of that selection",
        "summary": "summary only; not a transcript",
        "unknown": "capture coverage unknown",
    }[coverage]
    if not complete:
        label = label.split(";")[0] + f"; INCOMPLETE capture: {limits}"
    return f"- {name} ({label})"


def render_packet(
    created: str,
    input_path: str,
    input_sha256: str,
    supersedes: str | None,
    sources: list[PacketSource],
    pins: list[dict[str, Any]],
    targets: list[tuple[Target, bytes | None, bytes]],
    question: str,
    assumptions: str,
    source_lines: list[str],
) -> bytes:
    fields: list[tuple[str, Any]] = [
        ("schema_version", 1),
        ("kind", "workspace-change"),
        ("scope", {"kind": "workspace"}),
        ("created", created),
        ("input", {"path": input_path, "sha256": input_sha256, "snapshot": "input.md"}),
        ("supersedes", supersedes),
        (
            "sources",
            [
                {
                    "path": item.path,
                    "url": item.url,
                    "sha256": item.sha256,
                    "snapshot": item.snapshot,
                    "coverage": item.coverage,
                }
                for item in sources
            ],
        ),
        ("pins", pins),
        (
            "targets",
            [
                {
                    "path": target.path,
                    "before_sha256": target.before_sha256,
                    "after_sha256": target.after_sha256,
                    "after": target.after,
                }
                for target, _, _ in targets
            ],
        ),
    ]
    changes = "\n".join(
        fence(unified(before, after, target.path), "diff") for target, before, after in targets
    )
    body = (
        f"## Question\n{question}\n\n## Changes\n{changes}\n## Sources\n"
        + ("\n".join(source_lines) if source_lines else "None.")
        + f"\n\n## Unresolved assumptions\n{assumptions}\n\n## Not changed\n{NOT_CHANGED}"
    )
    return (header(fields) + body).encode()


def validate_packet(document: Document) -> Packet:
    validate_values(document)
    h = mapping(document, document.header, "", set(PACKET_ORDER))
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    if h["kind"] != "workspace-change":
        document.fail("kind", "expected workspace-change")
    if h["scope"] != {"kind": "workspace"}:
        document.fail("scope", "expected {kind: workspace}")
    timestamp(document, h["created"], "created")
    source_input = mapping(document, h["input"], "input", {"path", "sha256", "snapshot"})
    text(document, source_input["path"], "input.path")
    _hex(document, source_input["sha256"], "input.sha256")
    if source_input["snapshot"] != "input.md":
        document.fail("input.snapshot", "expected input.md")
    supersedes = h["supersedes"]
    if supersedes is not None:
        try:
            packet_directory(text(document, supersedes, "supersedes"))
        except FormatError as error:
            document.fail("supersedes", str(error))
    sources = []
    if not isinstance(h["sources"], list):
        document.fail("sources", "expected list")
    for index, item in enumerate(h["sources"]):
        field = f"sources[{index}]"
        value = mapping(document, item, field, {"path", "url", "sha256", "snapshot", "coverage"})
        if (value["path"] is None) == (value["url"] is None):
            document.fail(field, "exactly one of path or url")
        if value["coverage"] not in COVERAGE:
            document.fail(f"{field}.coverage", "unknown coverage")
        sha256 = _hex(document, value["sha256"], f"{field}.sha256", nullable=True)
        snapshot = value["snapshot"]
        if snapshot is not None and not re.fullmatch(r"sources/[0-9]+(\.[A-Za-z0-9]+)?", snapshot):
            document.fail(f"{field}.snapshot", "expected sources/N")
        if snapshot is not None and sha256 is None:
            document.fail(f"{field}.sha256", "a snapshot needs its digest")
        sources.append(
            PacketSource(value["path"], value["url"], sha256, snapshot, value["coverage"])
        )
    if not isinstance(h["pins"], list):
        document.fail("pins", "expected list")
    for index, item in enumerate(h["pins"]):
        pin = mapping(document, item, f"pins[{index}]", set(PIN_ORDER))
        _hex(document, pin["description_sha256"], f"pins[{index}].description_sha256")
    targets = []
    if not isinstance(h["targets"], list) or not h["targets"]:
        document.fail("targets", "expected a nonempty list")
    for index, item in enumerate(h["targets"]):
        field = f"targets[{index}]"
        value = mapping(document, item, field, {"path", "before_sha256", "after_sha256", "after"})
        path = text(document, value["path"], f"{field}.path")
        if path != CHARTER_FILE and not RESOURCE_TARGET.fullmatch(path):
            document.fail(f"{field}.path", "only WORKSPACE.md and shared/resources/<name>.md")
        if path == CHARTER_FILE and value["before_sha256"] is None:
            document.fail(f"{field}.before_sha256", "WORKSPACE.md is replaced, never created")
        before = _hex(document, value["before_sha256"], f"{field}.before_sha256", nullable=True)
        after = _hex(document, value["after_sha256"], f"{field}.after_sha256")
        if value["after"] != f"targets/{index + 1}.md":
            document.fail(f"{field}.after", f"expected targets/{index + 1}.md")
        assert after is not None
        targets.append(Target(path, before, after, value["after"]))
    if len({target.path for target in targets}) != len(targets):
        document.fail("targets", "each path appears once")
    return Packet(
        h["created"],
        source_input["path"],
        source_input["sha256"],
        supersedes,
        tuple(sources),
        tuple(h["pins"]),
        tuple(targets),
    )


def render_receipt(
    record: str,
    record_sha256: str,
    disposition: str,
    actor: str,
    at: str,
    approval_text: str | None,
    reason: str | None,
    results: list[dict[str, Any]],
) -> bytes:
    fields: list[tuple[str, Any]] = [
        ("schema_version", 1),
        ("kind", "workspace-receipt"),
        ("record", record),
        ("record_sha256", record_sha256),
        ("disposition", disposition),
        ("actor", actor),
        ("at", at),
        ("approval_text", approval_text),
        ("reason", reason),
        ("results", results),
    ]
    return (header(fields) + RECEIPT_BODY).encode()


def validate_receipt(document: Document) -> Receipt:
    validate_values(document)
    h = mapping(document, document.header, "", set(RECEIPT_ORDER))
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    if h["kind"] != "workspace-receipt":
        document.fail("kind", "expected workspace-receipt")
    record = text(document, h["record"], "record")
    record_sha256 = _hex(document, h["record_sha256"], "record_sha256")
    assert record_sha256 is not None
    if h["disposition"] not in {"applied", "rejected"}:
        document.fail("disposition", "expected applied or rejected")
    actor = text(document, h["actor"], "actor")
    timestamp(document, h["at"], "at")
    approval = h["approval_text"]
    if approval is not None:
        text(document, approval, "approval_text")
    reason = h["reason"]
    if h["disposition"] == "rejected":
        text(document, reason, "reason")
    elif reason is not None:
        document.fail("reason", "must be null for applied")
    if not isinstance(h["results"], list):
        document.fail("results", "expected list")
    if h["disposition"] == "rejected" and h["results"]:
        document.fail("results", "a rejection publishes nothing")
    results = []
    for index, item in enumerate(h["results"]):
        field = f"results[{index}]"
        value = mapping(document, item, field, {"path", "before_sha256", "after_sha256"})
        path = text(document, value["path"], f"{field}.path")
        before = _hex(document, value["before_sha256"], f"{field}.before_sha256", nullable=True)
        after = _hex(document, value["after_sha256"], f"{field}.after_sha256")
        assert after is not None
        results.append((path, before, after))
    return Receipt(
        record,
        record_sha256,
        h["disposition"],
        actor,
        h["at"],
        approval,
        reason,
        tuple(results),
    )
