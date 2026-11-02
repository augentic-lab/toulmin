"""Intrinsic validation of the seven v1 object types; no filesystem access."""

import math
import re
from datetime import UTC, datetime
from typing import Any

from toulmin.core.documents import STATUSES, Document, sections, validate_values
from toulmin.core.identifiers import SCHEMA_VERSION, ObjectId, ObjectKind, ObjectRef

COMMON = {"schema_version", "id", "status", "created", "source", "confirmed_by"}
FIELDS = {
    ObjectKind.CLAIM: ({"type", "importance"}, {"tags", "validation_plan"}),
    ObjectKind.EVIDENCE: ({"target", "direction", "kind", "grade", "provenance"}, {"verification"}),
    ObjectKind.OBJECTION: ({"target", "severity"}, set()),
    ObjectKind.DECISION: ({"related"}, {"superseded_by"}),
    ObjectKind.EXPLORATION: ({"lens"}, {"adopted_as"}),
    ObjectKind.SPEC: ({"target"}, {"evidence"}),
    ObjectKind.RUN: (
        {"model", "role", "input_files", "output", "session_id", "duration_seconds"},
        set(),
    ),
}
# Field order for generated headers: common fields, then formats.md's type-specific
# columns. Order is presentation only; readers accept any key order.
ORDER = ("schema_version", "id", "status", "created", "source", "confirmed_by")
KIND_ORDER = {
    ObjectKind.CLAIM: ("type", "importance", "tags", "validation_plan"),
    ObjectKind.EVIDENCE: ("target", "direction", "kind", "grade", "provenance", "verification"),
    ObjectKind.OBJECTION: ("target", "severity"),
    ObjectKind.DECISION: ("related", "superseded_by"),
    ObjectKind.EXPLORATION: ("lens", "adopted_as"),
    ObjectKind.SPEC: ("target", "evidence"),
    ObjectKind.RUN: ("model", "role", "input_files", "output", "session_id", "duration_seconds"),
}


def in_order(header: dict[str, Any], order: tuple[str, ...]) -> dict[str, Any]:
    """Return header with keys in `order` first; unknown keys keep their relative order."""
    known = {key: header[key] for key in order if key in header}
    return known | {key: value for key, value in header.items() if key not in known}


def object_order(kind: ObjectKind) -> tuple[str, ...]:
    return ORDER + KIND_ORDER[kind] + ("decisions", "extensions")


def utc_text(moment: datetime) -> str:
    """Generated timestamps: UTC, second precision, `Z` suffix."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# Enumerations are shared with draft skeletons so the two cannot drift apart.
CLAIM_TYPES = ("problem", "magnitude", "mechanism", "novelty", "assumption", "deployability")
IMPORTANCE = ("core", "secondary")
DIRECTIONS = ("supports", "refutes")
EVIDENCE_KINDS = ("measurement", "literature", "derivation", "experiment", "computation")
GRADES = ("verified", "model-asserted", "intuition")
SEVERITIES = ("fatal", "major", "minor")
SECTIONS = {
    ObjectKind.CLAIM: ("Statement",),
    ObjectKind.EVIDENCE: ("Material",),
    ObjectKind.OBJECTION: ("Content", "Response", "Ruling"),
    ObjectKind.DECISION: ("Context", "Choice", "Rejected alternatives", "Rationale"),
    ObjectKind.EXPLORATION: ("Content",),
    ObjectKind.SPEC: ("Requirements", "Acceptance criteria"),
    ObjectKind.RUN: ("Summary",),
}


def text(doc: Document, value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        doc.fail(field, "expected nonempty string")
    assert isinstance(value, str)
    return value


def mapping(
    doc: Document, value: Any, field: str, required: set[str], optional: set[str] | None = None
) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        doc.fail(field, "expected string-keyed mapping")
    assert isinstance(value, dict)
    for key in sorted(required - value.keys()):
        doc.fail(f"{field}.{key}" if field else key, "required field missing")
    for key in sorted(value.keys() - required - (optional or set())):
        doc.fail(f"{field}.{key}" if field else key, "unknown field")
    return value


def strings(doc: Document, value: Any, field: str, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        doc.fail(field, "expected list" + (" with at least one item" if nonempty else ""))
    assert isinstance(value, list)
    return [text(doc, item, f"{field}[{index}]") for index, item in enumerate(value)]


def timestamp(doc: Document, value: Any, field: str) -> None:
    value = text(doc, value, field)
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)", value):
        doc.fail(field, "expected RFC 3339 timestamp with timezone")
    try:
        datetime.fromisoformat(value)
    except ValueError as error:
        doc.fail(field, str(error))


def reference(
    doc: Document, value: Any, field: str, expected: ObjectKind | None = None
) -> ObjectRef:
    value = text(doc, value, field)
    try:
        ref = ObjectRef.parse(value)
    except ValueError as error:
        doc.fail(field, str(error))
        raise AssertionError("unreachable") from error
    if expected is not None and ref.object_id.kind != expected:
        doc.fail(field, f"expected {expected} reference")
    return ref


def validate(doc: Document) -> None:
    validate_values(doc)
    h = doc.header
    if type(h.get("schema_version")) is not int or h["schema_version"] != SCHEMA_VERSION:
        doc.fail("schema_version", "expected integer version 1")
    try:
        object_id = ObjectId.parse(text(doc, h.get("id"), "id"))
    except ValueError as error:
        doc.fail("id", str(error))
        raise AssertionError("unreachable") from error
    kind = object_id.kind
    required, optional = FIELDS[kind]
    mapping(
        doc,
        h,
        "",
        COMMON | required,
        optional | {"extensions"} | ({"decisions"} if kind != ObjectKind.RUN else set()),
    )
    if h["status"] not in STATUSES[kind]:
        doc.fail("status", f"expected one of {STATUSES[kind]}")
    text(doc, h["status"], "status")
    timestamp(doc, h["created"], "created")
    confirmation = mapping(doc, h["confirmed_by"], "confirmed_by", {"actor", "at"})
    text(doc, confirmation["actor"], "confirmed_by.actor")
    timestamp(doc, confirmation["at"], "confirmed_by.at")
    source = h["source"]
    if not isinstance(source, dict):
        doc.fail("source", "expected mapping")
    if source.get("kind") == "human":
        mapping(doc, source, "source", {"kind", "actor"})
        text(doc, source["actor"], "source.actor")
    elif source.get("kind") == "run" and kind != ObjectKind.RUN:
        mapping(doc, source, "source", {"kind", "ref", "path"})
        reference(doc, source["ref"], "source.ref", ObjectKind.RUN)
        text(doc, source["path"], "source.path")
    else:
        doc.fail("source.kind", "expected human, or run for a non-Run object")
    if "extensions" in h:
        if not isinstance(h["extensions"], dict):
            doc.fail("extensions", "expected mapping")
        for key in h["extensions"]:
            if not isinstance(key, str) or not re.fullmatch(r"[\w-]+\.[\w.-]+", key):
                doc.fail("extensions", "keys require namespace.name")

    def enum(field: str, values: tuple[str, ...]) -> None:
        if h[field] not in values:
            doc.fail(field, f"expected one of {values}")

    def refs(field: str, expected: ObjectKind | None, nonempty: bool = False) -> None:
        for index, value in enumerate(strings(doc, h.get(field, []), field, nonempty)):
            reference(doc, value, f"{field}[{index}]", expected)

    refs("decisions", ObjectKind.DECISION)
    if kind in {ObjectKind.EVIDENCE, ObjectKind.OBJECTION, ObjectKind.SPEC}:
        reference(doc, h["target"], "target", ObjectKind.CLAIM)
    if kind == ObjectKind.CLAIM:
        enum("type", CLAIM_TYPES)
        enum("importance", IMPORTANCE)
        strings(doc, h.get("tags", []), "tags")
        if "validation_plan" in h:
            text(doc, h["validation_plan"], "validation_plan")
        if h["status"] in {"accepted", "refuted"}:
            refs("decisions", ObjectKind.DECISION, True)
    elif kind == ObjectKind.EVIDENCE:
        enum("direction", DIRECTIONS)
        enum("kind", EVIDENCE_KINDS)
        enum("grade", GRADES)
        if not isinstance(h["provenance"], list) or not h["provenance"]:
            doc.fail("provenance", "expected nonempty list")
        for index, item in enumerate(h["provenance"]):
            field = f"provenance[{index}]"
            entry = mapping(doc, item, field, {"description"}, {"path", "url"})
            text(doc, entry["description"], field + ".description")
            if ("path" in entry) == ("url" in entry):
                doc.fail(field, "expected exactly one of path or url")
            if "url" in entry:
                url = text(doc, entry["url"], field + ".url")
                if not re.fullmatch(r"https?://[^/\s?#]+(?:[/?#][^\s]*)?", url):
                    doc.fail(field + ".url", "expected http/https URL")
            else:
                text(doc, entry["path"], field + ".path")
        if h["grade"] == "verified" and "verification" not in h:
            doc.fail("verification", "required for verified evidence")
        if "verification" in h:
            verification = mapping(
                doc, h["verification"], "verification", {"method", "result", "artifacts"}
            )
            for field in ("method", "result"):
                text(doc, verification[field], "verification." + field)
            strings(doc, verification["artifacts"], "verification.artifacts", True)
    elif kind == ObjectKind.OBJECTION:
        enum("severity", SEVERITIES)
        if h["status"] == "accepted":
            refs("decisions", ObjectKind.DECISION, True)
    elif kind == ObjectKind.DECISION:
        refs("related", None, True)
        if h["status"] == "superseded" and "superseded_by" not in h:
            doc.fail("superseded_by", "required for superseded decision")
        if "superseded_by" in h:
            reference(doc, h["superseded_by"], "superseded_by", ObjectKind.DECISION)
    elif kind == ObjectKind.EXPLORATION:
        text(doc, h["lens"], "lens")
        if h["status"] == "adopted" and "adopted_as" not in h:
            doc.fail("adopted_as", "required for adopted exploration")
        if "adopted_as" in h:
            reference(doc, h["adopted_as"], "adopted_as", ObjectKind.CLAIM)
    elif kind == ObjectKind.SPEC:
        refs("evidence", ObjectKind.EVIDENCE, h["status"] == "passed")
    elif kind == ObjectKind.RUN:
        for field in ("model", "role", "output"):
            text(doc, h[field], field)
        strings(doc, h["input_files"], "input_files")
        if h["session_id"] is not None:
            text(doc, h["session_id"], "session_id")
        duration = h["duration_seconds"]
        if duration is not None and (
            type(duration) not in {int, float}
            or duration < 0
            or (type(duration) is float and not math.isfinite(duration))
        ):
            doc.fail("duration_seconds", "expected nonnegative finite number or null")

    body = sections(doc)
    required_sections = list(SECTIONS[kind])
    if kind == ObjectKind.EVIDENCE and h["status"] == "invalidated":
        required_sections.append("Invalidation")
    if kind == ObjectKind.EXPLORATION and h["status"] == "dropped":
        required_sections.append("Rationale")
    if kind == ObjectKind.RUN and h["status"] == "failed":
        required_sections.append("Failure")
    for name in required_sections:
        if name not in body:
            doc.fail("body." + name, "required section missing")
        may_be_empty = kind == ObjectKind.OBJECTION and name in {"Response", "Ruling"}
        if not may_be_empty and not body[name].strip():
            doc.fail("body." + name, "required section is empty")
    if kind == ObjectKind.OBJECTION:
        needed = "Response" if h["status"] == "answered" else "Ruling"
        if h["status"] != "open" and not body[needed].strip():
            doc.fail("body." + needed, "required for this status")
