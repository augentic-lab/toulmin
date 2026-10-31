"""L1 validation of the compact project charter."""

from toulmin.core.documents import Document, sections, validate_values
from toulmin.core.identifiers import ObjectKind, validate_project_name
from toulmin.core.schema import mapping, reference, strings, text

STAGES = ("explore", "critique", "brief-final", "build", "accept", "done")


def validate_project(document: Document, project: str) -> None:
    validate_values(document)
    h = mapping(
        document,
        document.header,
        "",
        {
            "schema_version",
            "project",
            "stage",
            "recent_decisions",
            "next_step",
            "last_handoff",
        },
    )
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    name = text(document, h["project"], "project")
    try:
        validate_project_name(name)
    except ValueError as error:
        document.fail("project", str(error))
    if name != project:
        document.fail("project", "charter name does not match project directory")
    if h["stage"] not in STAGES:
        document.fail("stage", f"expected one of {STAGES}")
    text(document, h["next_step"], "next_step")
    for index, value in enumerate(strings(document, h["recent_decisions"], "recent_decisions")):
        reference(document, value, f"recent_decisions[{index}]", ObjectKind.DECISION)
    handoff = h["last_handoff"]
    if handoff is not None:
        handoff = text(document, handoff, "last_handoff")
        if (
            not handoff.endswith(".md")
            or handoff in {".md", "..md"}
            or "/" in handoff
            or "\\" in handoff
        ):
            document.fail("last_handoff", "expected a Markdown filename inside sessions/")
    body = sections(document)
    for field in ("Goal", "Constraints"):
        if not body.get(field, "").strip():
            document.fail("body." + field, "required section is missing or empty")
    if document.body_line - 1 + len(document.body.splitlines()) > 40:
        document.fail("body", "PROJECT.md must fit within 40 lines")
