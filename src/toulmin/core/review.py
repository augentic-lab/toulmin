"""L1 review draft blocks and intake records, with no filesystem access.

A reviewer's raw output stays opaque prose except for one final fenced ``yaml`` block that
lists draft objections. Intake outcomes live in an ``intake.md`` record beside that raw
output, so adoption can be derived from files rather than a separate store.
"""

import re
from dataclasses import dataclass
from typing import Any, NoReturn

from toulmin.core.codec import load_restricted
from toulmin.core.documents import Document, FormatError, headings, sections
from toulmin.core.identifiers import ObjectKind
from toulmin.core.schema import SEVERITIES, mapping, reference, text, timestamp

INTAKE_FILE = "intake.md"
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
DRAFT_FIELDS = {"label", "target", "severity", "content", "grounds"}
OUTCOMES = ("taken", "partly", "rejected")


@dataclass(frozen=True)
class ReviewDraft:
    label: str
    target: str
    severity: str
    content: str
    grounds: str
    uncertainty: str | None
    line: int


def _fences(text: str) -> list[tuple[str, int, int]]:
    """Top-level fenced blocks as (info string, first content line index, end index)."""
    blocks: list[tuple[str, int, int]] = []
    lines = text.splitlines()
    fence = ""
    info = ""
    start = 0
    for index, line in enumerate(lines):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if (
                marker
                and marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence)
                and not marker[2].strip()
            ):
                blocks.append((info, start, index))
                fence = ""
        elif marker:
            fence, info, start = marker[1], marker[2].strip(), index + 1
    return blocks


def final_yaml_list(raw: str, location: str, name: str) -> tuple[list[Any], dict[str, int], int]:
    """The last top-level fenced yaml block as a nonempty list, its line map and first line."""
    blocks = [block for block in _fences(raw) if block[0] in {"yaml", "yml"}]
    if not blocks:
        raise FormatError(f"{location}:1: {name}: no final fenced yaml block of {name}")
    _, start, end = blocks[-1]
    lines = raw.splitlines()
    value, positions = load_restricted(
        "\n".join(lines[start:end]) + "\n", location, start + 1, name
    )
    if not isinstance(value, list) or not value:
        raise FormatError(f"{location}:{start + 1}: {name}: expected a nonempty list")
    return value, positions, start + 1


def parse_review(raw: str, location: str) -> tuple[ReviewDraft, ...]:
    """Parse the last fenced yaml block of a raw review into validated drafts."""
    value, positions, first = final_yaml_list(raw, location, "drafts")
    start = first - 1
    drafts: list[ReviewDraft] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        field = f"[{index}]"
        line = positions.get(field, start + 1)
        holder = Document({}, "", location, {"": line}, line)

        def fail(name: str, message: str, line: int = line, field: str = field) -> NoReturn:
            raise FormatError(f"{location}:{line}: drafts{field}.{name}: {message}")

        if not isinstance(item, dict):
            fail("", "expected mapping")
        for key in sorted(DRAFT_FIELDS - item.keys()):
            fail(key, "required field missing")
        for key in sorted(item.keys() - DRAFT_FIELDS - {"uncertainty"}):
            fail(str(key), "unknown field")
        for key in (*sorted(DRAFT_FIELDS), "uncertainty"):
            if key in item and (not isinstance(item[key], str) or not item[key].strip()):
                fail(key, "expected nonempty string")
        label = item["label"]
        if not LABEL.fullmatch(label):
            fail("label", "expected ASCII letters, digits, '_' or '-'")
        if label in seen:
            fail("label", f"duplicate label {label}")
        seen.add(label)
        try:
            reference(holder, item["target"], "target", ObjectKind.CLAIM)
        except FormatError as error:
            fail("target", str(error).rsplit(": ", 1)[-1])
        if item["severity"] not in SEVERITIES:
            fail("severity", f"expected one of {SEVERITIES}")
        for key in ("content", "grounds", "uncertainty"):
            if key in item and headings(item[key].splitlines(keepends=True)):
                fail(key, "level-two headings are not allowed in draft text")
        drafts.append(
            ReviewDraft(
                label,
                item["target"],
                item["severity"],
                item["content"].strip(),
                item["grounds"].strip(),
                item["uncertainty"].strip() if "uncertainty" in item else None,
                line,
            )
        )
    return tuple(drafts)


def objection_body(draft: ReviewDraft) -> str:
    """The Objection body generated from a draft; deterministic so replays can match it."""
    parts = [draft.content, f"Grounds: {draft.grounds}"]
    if draft.uncertainty:
        parts.append(f"Uncertainty: {draft.uncertainty}")
    return "## Content\n" + "\n\n".join(parts) + "\n\n## Response\n\n## Ruling\n"


def validate_intake(document: Document) -> dict[str, dict[str, Any]]:
    """Validate an intake record; return outcomes keyed by draft label."""
    h = document.header
    mapping(document, h, "", {"schema_version", "run", "output", "outcomes"})
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    run = reference(document, h["run"], "run", ObjectKind.RUN)
    if run.project is not None:
        document.fail("run", "expected a Run in this project")
    text(document, h["output"], "output")
    if not isinstance(h["outcomes"], list):
        document.fail("outcomes", "expected list")
    outcomes: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(h["outcomes"]):
        field = f"outcomes[{index}]"
        entry = mapping(
            document, item, field, {"label", "outcome", "by", "at"}, {"object", "reason"}
        )
        label = text(document, entry["label"], field + ".label")
        if label in outcomes:
            document.fail(field + ".label", f"duplicate outcome for {label}")
        if entry["outcome"] not in OUTCOMES:
            document.fail(field + ".outcome", f"expected one of {OUTCOMES}")
        text(document, entry["by"], field + ".by")
        timestamp(document, entry["at"], field + ".at")
        if entry["outcome"] == "rejected":
            text(document, entry.get("reason"), field + ".reason")
            if "object" in entry:
                document.fail(field + ".object", "a rejected draft has no object")
        else:
            reference(document, entry.get("object"), field + ".object", ObjectKind.OBJECTION)
        outcomes[label] = entry
    sections(document)
    return outcomes
