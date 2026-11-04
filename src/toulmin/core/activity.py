"""L1 schema for workspace activity records (docs/workspace-formats.md, section 5).

Activity records are unconfirmed drafts written by agents or the researcher. They are
validated when a proposal cites them, so capture coverage is stated honestly there.
"""

import re
from dataclasses import dataclass

from toulmin.core.documents import Document, sections, validate_values
from toulmin.core.schema import mapping, text, timestamp

COVERAGE = ("full", "selected", "summary", "unknown")
ACTIVITY_FILE = "activity.md"
ACTIVITY_PATH = re.compile(r"runs/[0-9]{8}T[0-9]{6}Z-[A-Za-z0-9_-]+/activity\.md")
HEX = re.compile(r"[0-9a-f]{64}")
FIELDS = {"schema_version", "kind", "scope", "created", "purpose", "recorded_by", "capture"}
BODY = ("Summary", "Researcher feedback", "Open ideas")


@dataclass(frozen=True)
class Activity:
    coverage: str
    complete: bool
    limits: str | None


def validate_activity(document: Document) -> Activity:
    validate_values(document)
    h = mapping(document, document.header, "", FIELDS | {"sources"})
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    if h["kind"] != "workspace-activity":
        document.fail("kind", "expected workspace-activity")
    if h["scope"] != {"kind": "workspace"}:
        document.fail("scope", "root runs/ activity records have scope {kind: workspace}")
    timestamp(document, h["created"], "created")
    text(document, h["purpose"], "purpose")
    recorded = h["recorded_by"]
    if isinstance(recorded, dict) and recorded.get("kind") == "human":
        mapping(document, recorded, "recorded_by", {"kind", "actor"})
        text(document, recorded["actor"], "recorded_by.actor")
    elif isinstance(recorded, dict) and recorded.get("kind") == "agent":
        mapping(document, recorded, "recorded_by", {"kind", "role", "agent", "model", "session_id"})
        text(document, recorded["role"], "recorded_by.role")
        for field in ("agent", "model", "session_id"):
            if recorded[field] is not None:
                text(document, recorded[field], f"recorded_by.{field}")
    else:
        document.fail("recorded_by", "expected {kind: human, ...} or {kind: agent, ...}")
    capture = mapping(document, h["capture"], "capture", {"coverage", "complete", "limits"})
    if capture["coverage"] not in COVERAGE:
        document.fail("capture.coverage", f"expected one of {', '.join(COVERAGE)}")
    if type(capture["complete"]) is not bool:
        document.fail("capture.complete", "expected true or false")
    limits = capture["limits"]
    if limits is not None:
        text(document, limits, "capture.limits")
    elif capture["coverage"] != "full" or not capture["complete"]:
        document.fail("capture.limits", "required unless coverage is full and complete")
    sources = h["sources"]
    if not isinstance(sources, list):
        document.fail("sources", "expected list")
    for index, source in enumerate(sources):
        field = f"sources[{index}]"
        item = mapping(document, source, field, {"path", "url", "sha256", "note"})
        if (item["path"] is None) == (item["url"] is None):
            document.fail(field, "exactly one of path or url")
        for key in ("path", "url", "note"):
            if item[key] is not None:
                text(document, item[key], f"{field}.{key}")
        if item["sha256"] is not None and not (
            isinstance(item["sha256"], str) and HEX.fullmatch(item["sha256"])
        ):
            document.fail(f"{field}.sha256", "expected SHA-256 hex digest or null")
    body = sections(document)
    for heading, content in body.items():
        if heading not in BODY:
            document.fail(f"body.{heading}", "expected Summary, Researcher feedback or Open ideas")
        if not content.strip():
            document.fail(f"body.{heading}", "required content empty")
    if "Summary" not in body:
        document.fail("body.Summary", "required section missing")
    return Activity(capture["coverage"], capture["complete"], limits)
