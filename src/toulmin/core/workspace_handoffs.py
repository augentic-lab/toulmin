"""L1 workspace handoffs: input, sealed draft and applied record (contract section 8).

The project handoff contract (formats.md, core/handoffs.py) is unchanged; this mirrors
it for the workspace scope. A handoff records a session summary; it never applies a
direction, resource or child, and its pending ideas stay pending.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from toulmin.core.codec import decode
from toulmin.core.documents import Document, FormatError, sections, validate_values
from toulmin.core.handoffs import NEXT_STEP_TEXT
from toulmin.core.render import header, scalar
from toulmin.core.schema import mapping, text, timestamp
from toulmin.core.workspace import RECEIPT, SESSION, validate_charter

INPUT_KIND = "workspace-handoff-input"
KIND = "workspace-handoff"
SECTIONS = ("Done", "Confirmed changes", "Pending ideas", "Open questions")
DRAFT_DIR = re.compile(r"runs/[0-9]{8}T[0-9]{6}Z-handoff-[0-9a-f]{32}")
HEX = re.compile(r"[0-9a-f]{64}")
DRAFT_ORDER = (
    "schema_version",
    "kind",
    "scope",
    "created",
    "input",
    "session_id",
    "base_workspace_sha256",
    "confirmed_changes",
    "next_step",
)
RECORD_ORDER = (
    "source_draft",
    "source_sha256",
    "applied_by",
    "applied_at",
    "workspace_sha256",
    "previous_handoff",
)
CONTINUITY = ("next_step", "last_handoff")


@dataclass(frozen=True)
class HandoffInput:
    session_id: str | None
    next_step: str | None
    confirmed_changes: tuple[str, ...]
    sections: dict[str, str]


@dataclass(frozen=True)
class HandoffDraft:
    created: str
    input_path: str
    input_sha256: str
    session_id: str | None
    base_workspace_sha256: str
    confirmed_changes: tuple[str, ...]
    next_step: str


@dataclass(frozen=True)
class HandoffRecord:
    draft: HandoffDraft
    source_draft: str
    source_sha256: str
    applied_by: str
    applied_at: str
    workspace_sha256: str
    previous_handoff: str | None


def precise_text(moment: datetime) -> str:
    """Sub-second UTC timestamps (milliseconds), as handoff drafts and records use."""
    moment = moment.astimezone(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def draft_directory(value: str) -> str:
    """Normalize a draft path (directory or its draft.md) to its directory."""
    directory = value.removesuffix("/").removesuffix("/draft.md")
    if not DRAFT_DIR.fullmatch(directory):
        raise FormatError(
            f"{value}: expected a workspace handoff draft runs/<stamp>-handoff-<hex>/draft.md"
        )
    return directory


def _receipts(document: Document, value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        document.fail(field, "expected a list of applied receipt paths")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not RECEIPT.fullmatch(item):
            document.fail(f"{field}[{index}]", "expected runs/<stamp>-proposal-<hex>/receipt.md")
    if len(set(value)) != len(value):
        document.fail(field, "list each receipt once")
    return tuple(value)


def _optional_text(document: Document, value: Any, field: str) -> str | None:
    return None if value is None else text(document, value, field)


def _body(document: Document, *, generated: bool) -> dict[str, str]:
    body = sections(document)
    allowed = (*SECTIONS, "Next step") if generated else SECTIONS
    for heading in body:
        if heading == "Next step" and not generated:
            document.fail("body.Next step", "generated; use metadata next_step")
        if heading not in allowed:
            document.fail(f"body.{heading}", "expected " + ", ".join(SECTIONS))
    for heading in SECTIONS:
        if not body.get(heading, "").strip():
            document.fail(
                f"body.{heading}", "required section missing or empty ('None.' is allowed)"
            )
    if generated and body.get("Next step", "").strip() != NEXT_STEP_TEXT:
        document.fail("body.Next step", f"expected the fixed text {NEXT_STEP_TEXT!r}")
    return {heading: body[heading].strip() for heading in SECTIONS}


def validate_handoff_input(document: Document) -> HandoffInput:
    validate_values(document)
    kind = document.header.get("kind")
    if kind != INPUT_KIND:
        hint = {
            "workspace-change-input": "a workspace change input; use workspace propose --input",
            "workspace-change": "a review packet; use workspace apply --draft",
            KIND: "a generated handoff draft; use aoe handoff --workspace --apply",
            "project-creation-input": "a child creation input; use project propose",
        }.get(kind) if isinstance(kind, str) else None  # fmt: skip
        if hint is None and ("recent_decisions" in document.header or "project" in document.header):
            hint = "a project handoff summary; use aoe handoff PROJECT --input"
        document.fail("kind", f"expected {INPUT_KIND}" + (f"; this is {hint}" if hint else ""))
    h = mapping(
        document,
        document.header,
        "",
        {"schema_version", "kind"},
        {"session_id", "next_step", "confirmed_changes"},
    )
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    return HandoffInput(
        _optional_text(document, h.get("session_id"), "session_id"),
        _optional_text(document, h.get("next_step"), "next_step"),
        _receipts(document, h.get("confirmed_changes", []), "confirmed_changes"),
        _body(document, generated=False),
    )


def _draft_fields(document: Document, h: dict[str, Any]) -> HandoffDraft:
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    if h["kind"] != KIND:
        document.fail("kind", f"expected {KIND}")
    if h["scope"] != {"kind": "workspace"}:
        document.fail(
            "scope", "expected {kind: workspace}; project handoffs use aoe handoff PROJECT"
        )
    timestamp(document, h["created"], "created")
    source = mapping(document, h["input"], "input", {"path", "sha256"})
    text(document, source["path"], "input.path")
    for field, value in (
        ("input.sha256", source["sha256"]),
        ("base_workspace_sha256", h["base_workspace_sha256"]),
    ):
        if not isinstance(value, str) or not HEX.fullmatch(value):
            document.fail(field, "expected SHA-256 hex digest")
    return HandoffDraft(
        h["created"],
        source["path"],
        source["sha256"],
        _optional_text(document, h["session_id"], "session_id"),
        h["base_workspace_sha256"],
        _receipts(document, h["confirmed_changes"], "confirmed_changes"),
        text(document, h["next_step"], "next_step"),
    )


def validate_handoff_draft(document: Document) -> HandoffDraft:
    validate_values(document)
    h = mapping(document, document.header, "", set(DRAFT_ORDER))
    draft = _draft_fields(document, h)
    _body(document, generated=True)
    return draft


def validate_handoff_record(document: Document) -> HandoffRecord:
    validate_values(document)
    h = mapping(document, document.header, "", set(DRAFT_ORDER) | set(RECORD_ORDER))
    draft = _draft_fields(document, h)
    _body(document, generated=True)
    source = text(document, h["source_draft"], "source_draft")
    try:
        if draft_directory(source) + "/draft.md" != source:
            raise FormatError("expected the draft.md path")
    except FormatError as error:
        document.fail("source_draft", str(error))
    for field in ("source_sha256", "workspace_sha256"):
        if not isinstance(h[field], str) or not HEX.fullmatch(h[field]):
            document.fail(field, "expected SHA-256 hex digest")
    timestamp(document, h["applied_at"], "applied_at")
    previous = h["previous_handoff"]
    if previous is not None and (not isinstance(previous, str) or not SESSION.fullmatch(previous)):
        document.fail("previous_handoff", "expected a sessions/ filename or null")
    return HandoffRecord(
        draft,
        source,
        h["source_sha256"],
        text(document, h["applied_by"], "applied_by"),
        h["applied_at"],
        h["workspace_sha256"],
        previous,
    )


def render_body(values: dict[str, str]) -> str:
    parts = [f"## {heading}\n{values[heading]}\n" for heading in SECTIONS]
    return "\n".join(parts) + f"\n## Next step\n{NEXT_STEP_TEXT}\n"


def render_draft(
    created: str,
    input_path: str,
    input_sha256: str,
    supplied: HandoffInput,
    base_workspace_sha256: str,
    next_step: str,
) -> bytes:
    fields: list[tuple[str, Any]] = [
        ("schema_version", 1),
        ("kind", KIND),
        ("scope", {"kind": "workspace"}),
        ("created", created),
        ("input", {"path": input_path, "sha256": input_sha256}),
        ("session_id", supplied.session_id),
        ("base_workspace_sha256", base_workspace_sha256),
        ("confirmed_changes", list(supplied.confirmed_changes)),
        ("next_step", next_step),
    ]
    return (header(fields) + render_body(supplied.sections)).encode()


def render_record(
    draft: bytes,
    source_draft: str,
    applied_by: str,
    applied_at: str,
    workspace_sha256: str,
    previous_handoff: str | None,
    source_sha256: str,
) -> bytes:
    """The draft's exact header lines and body, followed by the application fields."""
    head, _, body = draft.decode()[4:].partition("\n---\n")
    added = header(
        [
            ("source_draft", source_draft),
            ("source_sha256", source_sha256),
            ("applied_by", applied_by),
            ("applied_at", applied_at),
            ("workspace_sha256", workspace_sha256),
            ("previous_handoff", previous_handoff),
        ]
    )
    extra = added.removeprefix("---\n").removesuffix("---\n")
    return f"---\n{head}\n{extra}---\n{body}".encode()


def continuity_after(before: bytes, next_step: str, last_handoff: str) -> bytes:
    """Replace only the next_step and last_handoff lines; every other byte stays."""
    document = decode(before)
    validate_charter(document)
    text_value = before.decode()
    head, _, body = text_value[4:].partition("\n---\n")
    lines = head.split("\n")
    values = {"next_step": next_step, "last_handoff": last_handoff}
    for key, value in values.items():
        found = [index for index, line in enumerate(lines) if line.startswith(f"{key}:")]
        if len(found) != 1:
            raise FormatError(f"WORKSPACE.md: {key}: expected exactly one header line")
        index = found[0]
        if index + 1 < len(lines) and lines[index + 1][:1] in {" ", "\t", "-"}:
            raise FormatError(
                f"WORKSPACE.md: {key}: multi-line value; restore a one-line value first"
            )
        lines[index] = f"{key}: {scalar(value)}"
    after = ("---\n" + "\n".join(lines) + "\n---\n" + body).encode()
    patched = decode(after)
    expected = {**document.header, **values}
    if patched.header != expected or patched.body != document.body:
        raise FormatError("WORKSPACE.md: continuity patch would change other fields")
    validate_charter(patched)
    return after
