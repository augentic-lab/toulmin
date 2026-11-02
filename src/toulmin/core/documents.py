"""L1 document values and diagnostics, with no parser or filesystem dependency."""

import math
import re
from dataclasses import dataclass, field
from typing import Any, NoReturn

from toulmin.core.identifiers import ObjectId, ObjectKind

DIRECTORIES = dict(
    zip(
        ObjectKind,
        ("claims", "evidence", "objections", "decisions", "explorations", "specs", "runs"),
        strict=True,
    )
)
STATUSES = {
    ObjectKind.CLAIM: ("proposed", "challenged", "supported", "accepted", "refuted", "superseded"),
    ObjectKind.EVIDENCE: ("valid", "invalidated"),
    ObjectKind.OBJECTION: ("open", "answered", "accepted", "deferred"),
    ObjectKind.DECISION: ("active", "superseded"),
    ObjectKind.EXPLORATION: ("pending", "adopted", "dropped"),
    ObjectKind.SPEC: ("todo", "in-progress", "awaiting-acceptance", "passed", "failed"),
    ObjectKind.RUN: ("completed", "failed"),
}


class FormatError(ValueError):
    """A data problem, including its source and field when available."""


@dataclass
class Document:
    # Any represents untrusted YAML values until schema validation succeeds.
    header: dict[str, Any]
    body: str
    location: str = "<memory>"
    lines: dict[str, int] = field(default_factory=dict)
    body_line: int = 1

    def fail(self, field: str, message: str) -> NoReturn:
        fallback = self.body_line if field.startswith("body") else 2
        line = self.lines.get(field, self.lines.get(field.split(".")[0], fallback))
        raise FormatError(f"{self.location}:{line}: {field}: {message}")

    @property
    def object_id(self) -> ObjectId:
        return ObjectId.parse(self.header["id"])


def validate_values(document: Document) -> None:
    """Restrict metadata to the same plain value subset for parsing and API callers."""

    def visit(value: Any, field: str) -> None:
        if value is None or type(value) in {str, int, bool}:
            return
        if type(value) is float and math.isfinite(value):
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{field}[{index}]")
            return
        if isinstance(value, dict) and all(isinstance(key, str) for key in value):
            for key, item in value.items():
                visit(item, f"{field}.{key}" if field else key)
            return
        document.fail(field or "header", "unsupported YAML value")

    visit(document.header, "")


def sections(document: Document) -> dict[str, str]:
    """Read level-two sections while treating fenced code as opaque body text."""
    result: dict[str, str] = {}
    current: str | None = None
    fence = ""
    for line_number, line in enumerate(document.body.splitlines(keepends=True), document.body_line):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\n"))
        if fence:
            if (
                marker
                and marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence)
                and not marker[2].strip()
            ):
                fence = ""
        elif marker:
            fence = marker[1]
        else:
            heading = re.fullmatch(r"## ([^\n]+)\n?", line)
            if heading:
                current = heading[1].rstrip()
                document.lines[f"body.{current}"] = line_number
                if current in result:
                    document.fail(f"body.{current}", "duplicate section")
                result[current] = ""
                continue
        if current is not None:
            result[current] += line
    return result


def headings(lines: list[str]) -> list[tuple[int, str]]:
    """Level-two headings outside fenced code, as (line index, name)."""
    found: list[tuple[int, str]] = []
    fence = ""
    for index, line in enumerate(lines):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\n"))
        if fence:
            if (
                marker
                and marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence)
                and not marker[2].strip()
            ):
                fence = ""
        elif marker:
            fence = marker[1]
        else:
            heading = re.fullmatch(r"## ([^\n]+)\n?", line)
            if heading:
                found.append((index, heading[1].rstrip()))
    return found


def put_section(body: str, name: str, content: str) -> str:
    """Return body with content added to section `name`, never deleting existing text.

    An empty section is filled; a nonempty one keeps its text and gains the new content
    after a blank line; a missing section is appended at the end. Other bytes are kept.
    """
    if not content.strip() or headings(content.splitlines(keepends=True)):
        raise ValueError(f"{name}: expected nonempty content without level-two headings")
    addition = content.strip("\n") + "\n"
    lines = body.splitlines(keepends=True)
    found = headings(lines)
    positions = [index for index, heading in found if heading == name]
    if len(positions) > 1:
        raise ValueError(f"{name}: duplicate section")
    if not positions:
        prefix = body if not body or body.endswith("\n") else body + "\n"
        separator = "\n" if prefix.strip() and not prefix.endswith("\n\n") else ""
        return f"{prefix}{separator}## {name}\n{addition}"
    start = positions[0] + 1
    later = [index for index, _ in found if index > positions[0]]
    end = later[0] if later else len(lines)
    existing = "".join(lines[start:end])
    kept = existing.rstrip()
    if kept and not kept.endswith("\n"):
        kept += "\n"
    trailing = "\n" if end < len(lines) else ""
    if lines and not lines[start - 1].endswith("\n"):
        lines[start - 1] += "\n"
    block = (kept + "\n" if kept.strip() else "") + addition + trailing
    return "".join(lines[:start]) + block + "".join(lines[end:])
