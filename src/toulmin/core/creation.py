"""L1 child creation inputs, sealed packets and creation records (contract section 9).

Pure models and rendering: bytes in, bytes or validated values out. File access,
publication and recovery live in L2 and the journal module. A creation packet
approves a question, scope and initial framing, never the truth of an assumption.
"""

import re
from dataclasses import dataclass
from typing import Any

from toulmin.core.codec import decode
from toulmin.core.documents import DIRECTORIES, Document, FormatError, validate_values
from toulmin.core.identifiers import validate_project_name
from toulmin.core.project import validate_project
from toulmin.core.proposals import (
    COVERAGE,
    PIN_ORDER,
    PacketSource,
    PinRef,
    SourceRef,
    _hex,
    _pin_refs,
    _source_refs,
)
from toulmin.core.render import fence, header
from toulmin.core.schema import mapping, strings, text, timestamp

CREATION_DIR = re.compile(r"runs/[0-9]{8}T[0-9]{6}Z-project-(?P<token>[0-9a-f]{32})")
STAGING = re.compile(r"projects/\.creating-[0-9a-f]{32}")
CREATION_RECORD = "runs/creation/creation.md"
INPUT_ORDER = (
    "schema_version",
    "kind",
    "project",
    "supersedes",
    "question",
    "motivation",
    "included",
    "excluded",
    "assumptions",
    "open_questions",
    "goal",
    "constraints",
    "next_step",
    "sources",
    "pins",
    "relationships",
)
PACKET_ORDER = (
    "schema_version",
    "kind",
    "scope",
    "created",
    "project",
    "input",
    "supersedes",
    "sources",
    "pins",
    "relationships",
    "targets",
)
RECORD_ORDER = (
    "schema_version",
    "kind",
    "project",
    "packet",
    "packet_sha256",
    "confirmed_by",
    "question",
    "motivation",
    "included",
    "excluded",
    "assumptions",
    "open_questions",
    "sources",
    "pins",
    "relationships",
)
TARGETS = (("PROJECT.md", "targets/PROJECT.md"), ("brief.md", "targets/brief.md"))
RECORD_BODY = (
    "Creation provenance for this project. Assumptions listed above are unresolved, not findings.\n"
)
NOT_CHANGED = (
    "No Claim, Evidence or Decision is created. WORKSPACE.md and other projects are unchanged.\n"
    "No native session is started. Approval confirms the question, scope and initial\n"
    "framing, not that any assumption holds.\n"
)


@dataclass(frozen=True)
class Relationship:
    project: str
    note: str


@dataclass(frozen=True)
class CreationInput:
    project: str
    supersedes: str | None
    question: str
    motivation: str
    included: tuple[str, ...]
    excluded: tuple[str, ...]
    assumptions: tuple[str, ...]
    open_questions: tuple[str, ...]
    goal: str
    constraints: str
    next_step: str
    sources: tuple[SourceRef, ...]
    pins: tuple[PinRef, ...]
    relationships: tuple[Relationship, ...]
    brief: str


@dataclass(frozen=True)
class CreationTarget:
    path: str
    after_sha256: str
    after: str


@dataclass(frozen=True)
class CreationPacket:
    created: str
    project: str
    input_path: str
    input_sha256: str
    supersedes: str | None
    sources: tuple[PacketSource, ...]
    pins: tuple[dict[str, Any], ...]
    relationships: tuple[Relationship, ...]
    targets: tuple[CreationTarget, ...]


@dataclass(frozen=True)
class CreationRecord:
    project: str
    packet: str
    packet_sha256: str
    actor: str
    at: str


def creation_directory(value: str) -> str:
    """Normalize a creation packet path (directory or its packet.md) to its directory."""
    directory = value.removesuffix("/").removesuffix("/packet.md")
    if not CREATION_DIR.fullmatch(directory):
        raise FormatError(f"{value}: expected a child creation packet runs/<stamp>-project-<hex>")
    return directory


def staging_directory(directory: str) -> str:
    """The private staging path of a packet's child: hex from the packet directory."""
    match = CREATION_DIR.fullmatch(creation_directory(directory))
    assert match is not None
    return f"projects/.creating-{match['token']}"


def _line(document: Document, value: Any, field: str) -> str:
    line = text(document, value, field)
    if "\n" in line:
        document.fail(field, "expected one line")
    return line


def _lines(document: Document, value: Any, field: str, nonempty: bool = False) -> tuple[str, ...]:
    items = strings(document, value, field, nonempty)
    for index, item in enumerate(items):
        if "\n" in item:
            document.fail(f"{field}[{index}]", "expected one line")
    return tuple(items)


def _section_text(document: Document, value: Any, field: str) -> str:
    content = text(document, value, field)
    if re.search(r"^## ", content, re.M):
        document.fail(field, "must not contain '## ' headings")
    return content.strip()


def _relationships(document: Document, value: Any) -> tuple[Relationship, ...]:
    if not isinstance(value, list):
        document.fail("relationships", "expected list")
    result = []
    for index, item in enumerate(value):
        field = f"relationships[{index}]"
        pair = mapping(document, item, field, {"project", "note"})
        name = text(document, pair["project"], f"{field}.project")
        try:
            validate_project_name(name)
        except ValueError as error:
            document.fail(f"{field}.project", str(error))
        result.append(Relationship(name, _line(document, pair["note"], f"{field}.note")))
    if len({item.project for item in result}) != len(result):
        document.fail("relationships", "name each related project at most once")
    return tuple(result)


def validate_creation_input(document: Document) -> CreationInput:
    validate_values(document)
    h = mapping(document, document.header, "", set(INPUT_ORDER))
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    if h["kind"] != "project-creation-input":
        document.fail("kind", "expected project-creation-input (a creation input, not a packet)")
    project = text(document, h["project"], "project")
    try:
        validate_project_name(project)
    except ValueError as error:
        document.fail("project", str(error))
    supersedes = h["supersedes"]
    if supersedes is not None:
        try:
            supersedes = creation_directory(text(document, supersedes, "supersedes"))
        except FormatError as error:
            document.fail("supersedes", str(error))
    relationships = _relationships(document, h["relationships"])
    if any(item.project == project for item in relationships):
        document.fail("relationships", "a project cannot be related to itself")
    if not document.body.strip():
        document.fail("body", "the initial Brief is required")
    return CreationInput(
        project,
        supersedes,
        _line(document, h["question"], "question"),
        _line(document, h["motivation"], "motivation"),
        _lines(document, h["included"], "included", nonempty=True),
        _lines(document, h["excluded"], "excluded"),
        _lines(document, h["assumptions"], "assumptions"),
        _lines(document, h["open_questions"], "open_questions"),
        _section_text(document, h["goal"], "goal"),
        _section_text(document, h["constraints"], "constraints"),
        _line(document, h["next_step"], "next_step"),
        _source_refs(document, h["sources"]),
        _pin_refs(document, h["pins"]),
        relationships,
        document.body,
    )


def render_charter(value: CreationInput) -> bytes:
    """The child's PROJECT.md: stage explore, no decisions, no handoff."""
    fields: list[tuple[str, Any]] = [
        ("schema_version", 1),
        ("project", value.project),
        ("stage", "explore"),
        ("recent_decisions", []),
        ("next_step", value.next_step),
        ("last_handoff", None),
    ]
    body = f"## Goal\n{value.goal}\n\n## Constraints\n{value.constraints}\n"
    data = (header(fields) + body).encode()
    validate_project(decode(data, f"projects/{value.project}/PROJECT.md (after image)"),
                     value.project)  # fmt: skip
    return data


def _items(values: tuple[str, ...], empty: str) -> str:
    return "\n".join(f"- {item}" for item in values) if values else empty


def _source_fields(sources: list[PacketSource]) -> list[dict[str, Any]]:
    return [
        {
            "path": item.path,
            "url": item.url,
            "sha256": item.sha256,
            "snapshot": item.snapshot,
            "coverage": item.coverage,
        }
        for item in sources
    ]


def render_creation_packet(
    created: str,
    value: CreationInput,
    input_path: str,
    input_sha256: str,
    sources: list[PacketSource],
    pins: list[dict[str, Any]],
    targets: list[tuple[CreationTarget, bytes]],
    source_lines: list[str],
) -> bytes:
    fields: list[tuple[str, Any]] = [
        ("schema_version", 1),
        ("kind", "project-creation"),
        ("scope", {"kind": "workspace"}),
        ("created", created),
        ("project", value.project),
        ("input", {"path": input_path, "sha256": input_sha256, "snapshot": "input.md"}),
        ("supersedes", value.supersedes),
        ("sources", _source_fields(sources)),
        ("pins", pins),
        ("relationships", [{"project": r.project, "note": r.note} for r in value.relationships]),
        (
            "targets",
            [
                {"path": t.path, "after_sha256": t.after_sha256, "after": t.after}
                for t, _ in targets
            ],
        ),
    ]
    base = f"projects/{value.project}"
    files = "\n".join(
        f"{target.path}:\n{fence(after.decode(), 'markdown')}" for target, after in targets
    )
    related = (
        "\n".join(f"- {item.project}: {item.note}" for item in value.relationships)
        if value.relationships
        else "None."
    )
    body = (
        f"## Question\n{value.question}\n\nMotivation: {value.motivation}\n\n"
        f"## Scope\nIncluded:\n{_items(value.included, '')}\n\n"
        f"Excluded:\n{_items(value.excluded, 'None stated.')}\n\n"
        f"Related projects:\n{related}\n\n"
        f"## Files to create\n{base}/ with the PROJECT.md and brief.md below, empty object\n"
        f"directories ({', '.join(f'{name}/' for name in DIRECTORIES.values())}), sessions/\n"
        "and runs/creation/ (provenance written at confirmation).\n\n"
        f"{files}\n"
        "## Carried inputs\n" + ("\n".join(source_lines) if source_lines else "None.") + "\n\n"
        f"## Unresolved assumptions\n{_items(value.assumptions, 'None.')}\n\n"
        f"## Open questions\n{_items(value.open_questions, 'None.')}\n\n"
        f"## Not changed\n{NOT_CHANGED}"
    )
    return (header(fields) + body).encode()


def validate_creation_packet(document: Document) -> CreationPacket:
    validate_values(document)
    h = mapping(document, document.header, "", set(PACKET_ORDER))
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    if h["kind"] != "project-creation":
        document.fail("kind", "expected project-creation")
    if h["scope"] != {"kind": "workspace"}:
        document.fail("scope", "expected {kind: workspace}")
    timestamp(document, h["created"], "created")
    project = text(document, h["project"], "project")
    try:
        validate_project_name(project)
    except ValueError as error:
        document.fail("project", str(error))
    source_input = mapping(document, h["input"], "input", {"path", "sha256", "snapshot"})
    text(document, source_input["path"], "input.path")
    _hex(document, source_input["sha256"], "input.sha256")
    if source_input["snapshot"] != "input.md":
        document.fail("input.snapshot", "expected input.md")
    supersedes = h["supersedes"]
    if supersedes is not None:
        try:
            creation_directory(text(document, supersedes, "supersedes"))
        except FormatError as error:
            document.fail("supersedes", str(error))
    sources = _packet_sources(document, h["sources"])
    pins = _full_pins(document, h["pins"])
    relationships = _relationships(document, h["relationships"])
    if not isinstance(h["targets"], list) or len(h["targets"]) != len(TARGETS):
        document.fail("targets", "expected PROJECT.md and brief.md")
    targets = []
    for index, (item, (name, image)) in enumerate(zip(h["targets"], TARGETS, strict=True)):
        field = f"targets[{index}]"
        value = mapping(document, item, field, {"path", "after_sha256", "after"})
        if value["path"] != f"projects/{project}/{name}":
            document.fail(f"{field}.path", f"expected projects/{project}/{name}")
        after = _hex(document, value["after_sha256"], f"{field}.after_sha256")
        if value["after"] != image:
            document.fail(f"{field}.after", f"expected {image}")
        assert after is not None
        targets.append(CreationTarget(value["path"], after, image))
    return CreationPacket(
        h["created"],
        project,
        source_input["path"],
        source_input["sha256"],
        supersedes,
        sources,
        pins,
        relationships,
        tuple(targets),
    )


def _packet_sources(document: Document, value: Any) -> tuple[PacketSource, ...]:
    if not isinstance(value, list):
        document.fail("sources", "expected list")
    sources = []
    for index, item in enumerate(value):
        field = f"sources[{index}]"
        entry = mapping(document, item, field, {"path", "url", "sha256", "snapshot", "coverage"})
        if (entry["path"] is None) == (entry["url"] is None):
            document.fail(field, "exactly one of path or url")
        if entry["coverage"] not in COVERAGE:
            document.fail(f"{field}.coverage", "unknown coverage")
        sha256 = _hex(document, entry["sha256"], f"{field}.sha256", nullable=True)
        snapshot = entry["snapshot"]
        if snapshot is not None and not re.fullmatch(r"sources/[0-9]+(\.[A-Za-z0-9]+)?", snapshot):
            document.fail(f"{field}.snapshot", "expected sources/N")
        if snapshot is not None and sha256 is None:
            document.fail(f"{field}.sha256", "a snapshot needs its digest")
        sources.append(
            PacketSource(entry["path"], entry["url"], sha256, snapshot, entry["coverage"])
        )
    return tuple(sources)


def _full_pins(document: Document, value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        document.fail("pins", "expected list")
    for index, item in enumerate(value):
        pin = mapping(document, item, f"pins[{index}]", set(PIN_ORDER))
        _hex(document, pin["description_sha256"], f"pins[{index}].description_sha256")
    return tuple(value)


def render_record(
    value: CreationInput,
    packet: str,
    packet_sha256: str,
    actor: str,
    at: str,
    sources: tuple[PacketSource, ...],
    pins: tuple[dict[str, Any], ...],
) -> bytes:
    """``runs/creation/creation.md``: written at confirmation, so it carries the actor."""
    fields: list[tuple[str, Any]] = [
        ("schema_version", 1),
        ("kind", "project-creation-record"),
        ("project", value.project),
        ("packet", packet),
        ("packet_sha256", packet_sha256),
        ("confirmed_by", {"actor": actor, "at": at}),
        ("question", value.question),
        ("motivation", value.motivation),
        ("included", list(value.included)),
        ("excluded", list(value.excluded)),
        ("assumptions", list(value.assumptions)),
        ("open_questions", list(value.open_questions)),
        ("sources", _source_fields(list(sources))),
        ("pins", list(pins)),
        ("relationships", [{"project": r.project, "note": r.note} for r in value.relationships]),
    ]
    return (header(fields) + RECORD_BODY).encode()


def validate_record(document: Document, project: str) -> CreationRecord:
    """Validate a child's creation record; it names its packet and the confirming actor."""
    validate_values(document)
    h = mapping(document, document.header, "", set(RECORD_ORDER))
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    if h["kind"] != "project-creation-record":
        document.fail("kind", "expected project-creation-record")
    if h["project"] != project:
        document.fail("project", "creation record does not match project directory")
    packet = text(document, h["packet"], "packet")
    if not packet.endswith("/packet.md"):
        document.fail("packet", "expected a creation packet's packet.md")
    try:
        creation_directory(packet)
    except FormatError as error:
        document.fail("packet", str(error))
    sha256 = _hex(document, h["packet_sha256"], "packet_sha256")
    assert sha256 is not None
    confirmed = mapping(document, h["confirmed_by"], "confirmed_by", {"actor", "at"})
    actor = text(document, confirmed["actor"], "confirmed_by.actor")
    timestamp(document, confirmed["at"], "confirmed_by.at")
    _line(document, h["question"], "question")
    _line(document, h["motivation"], "motivation")
    _lines(document, h["included"], "included", nonempty=True)
    for field in ("excluded", "assumptions", "open_questions"):
        _lines(document, h[field], field)
    _packet_sources(document, h["sources"])
    _full_pins(document, h["pins"])
    _relationships(document, h["relationships"])
    if document.body != RECORD_BODY:
        document.fail("body", "expected the fixed creation-record sentence")
    return CreationRecord(project, packet, sha256, actor, confirmed["at"])
