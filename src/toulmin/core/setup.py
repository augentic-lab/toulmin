"""Versioned setup intent validation and initial-document planning (no file I/O)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from toulmin.core.atomic import digest
from toulmin.core.codec import decode, encode
from toulmin.core.documents import Document, FormatError, headings, sections
from toulmin.core.project import validate_project
from toulmin.core.schema import mapping, text, timestamp, utc_text

IMAGES = ("project-before", "project-after", "brief-before", "brief-after")


@dataclass(frozen=True)
class SetupRecord:
    project: str
    goal: str
    motivation: str
    source_name: str | None
    source_file: str | None
    images: dict[str, bytes]
    source: bytes | None = None
    created: str = field(default_factory=lambda: utc_text(datetime.now(UTC)))

    def document(self) -> Document:
        return Document(
            {
                "schema_version": 1,
                "project": self.project,
                "created": self.created,
                "goal": self.goal,
                "motivation": self.motivation,
                "source_name": self.source_name,
                "source_file": self.source_file,
                "source_sha256": digest(self.source) if self.source is not None else None,
                **{f"{name}_sha256": digest(self.images[name]) for name in IMAGES},
            },
            "Researcher-supplied setup input and exact publication images.\n",
        )


def initial_documents(
    project: str, goal: str, motivation: str, charter: bytes, brief: bytes
) -> dict[str, bytes]:
    """Validate supplied values before creating any project files."""
    for label, value in (("goal", goal), ("motivation", motivation)):
        if not value.strip() or "\r" in value or "\x00" in value:
            raise FormatError(f"{label}: expected nonempty UTF-8 text with LF line endings")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as error:
            raise FormatError(f"{label}: expected valid UTF-8 text") from error
    if headings(goal.splitlines(keepends=True)):
        raise FormatError("goal: level-two Markdown headings are reserved for PROJECT sections")
    before = decode(charter)
    validate_project(before, project)
    after = Document(
        dict(before.header),
        f"## Goal\n{goal}\n\n## Constraints\n{sections(before)['Constraints'].strip()}\n",
    )
    project_after = encode(after)
    validate_project(decode(project_after), project)
    initial_brief = (
        f"# Research brief: {project}\n\n"
        "Researcher-supplied starting point; no review has been completed.\n\n"
        "## Problem\n\n"
        + "\n".join("> " + line if line else ">" for line in motivation.split("\n"))
        + "\n\n"
        + "## Why now\n\n"
        "The initial motivation is recorded above; clarify timing during exploration.\n\n"
        "## Magnitude\n\n## Closest prior work\n\n## Objections and responses\n\n"
        "## Kill criteria\n\n## Minimal validation experiment\n"
    ).encode("utf-8")
    return {
        "project-before": charter,
        "project-after": project_after,
        "brief-before": brief,
        "brief-after": initial_brief,
    }


def validate_setup(document: Document, project: str, images: dict[str, bytes]) -> SetupRecord:
    h = mapping(
        document,
        document.header,
        "",
        {
            "schema_version",
            "project",
            "created",
            "goal",
            "motivation",
            "source_name",
            "source_file",
            "source_sha256",
            *{f"{name}_sha256" for name in IMAGES},
        },
    )
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    if h["project"] != project:
        document.fail("project", "setup project does not match directory")
    timestamp(document, h["created"], "created")
    goal = text(document, h["goal"], "goal")
    motivation = text(document, h["motivation"], "motivation")
    source_file = h["source_file"]
    source_name = h["source_name"]
    if source_file is None:
        if source_name is not None or h["source_sha256"] is not None:
            document.fail("source_file", "source metadata requires an archived source")
    else:
        if source_file not in ("source.md", "source.txt"):
            document.fail("source_file", "expected source.md or source.txt")
        source_name = text(document, source_name, "source_name")
        if "/" in source_name or "\\" in source_name or source_name in {".", ".."}:
            document.fail("source_name", "expected original source filename")
        checksum = text(document, h["source_sha256"], "source_sha256")
        if len(checksum) != 64 or any(
            character not in "0123456789abcdef" for character in checksum
        ):
            document.fail("source_sha256", "expected lowercase SHA-256")
    for name in IMAGES:
        if digest(images[name]) != h[f"{name}_sha256"]:
            document.fail(f"{name}_sha256", "setup image checksum mismatch; originals retained")
    expected = initial_documents(
        project, goal, motivation, images["project-before"], images["brief-before"]
    )
    if images != expected:
        document.fail("images", "setup publication images disagree with supplied values")
    return SetupRecord(
        project, goal, motivation, source_name, source_file, images, created=h["created"]
    )
