"""L1 schema for WORKSPACE.md, the short confirmed workspace charter.

docs/workspace-formats.md (section 4) is the contract. The charter is not an eighth
object type and has no research stage; a missing Direction section is the only
representation of an absent confirmed direction.
"""

import json
import re
import unicodedata
from dataclasses import dataclass

from toulmin.core.documents import Document, sections, validate_values
from toulmin.core.schema import mapping, text

CHARTER_FILE = "WORKSPACE.md"
CHARTER_ORDER = (
    "schema_version",
    "name",
    "charter_revision",
    "charter_receipt",
    "next_step",
    "last_handoff",
)
SECTIONS = ("Direction", "Constraints", "Focus")
MAX_LINES = 40
MAX_NAME = 80
NO_DIRECTION = "No confirmed direction yet"
INITIAL_NOTE = f"{NO_DIRECTION}. Change this charter only through a reviewed workspace proposal.\n"
RECEIPT = re.compile(r"runs/[0-9]{8}T[0-9]{6}Z-proposal-[0-9a-f]{32}/receipt\.md")
SESSION = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{64}\.md")
# YAML treats these as line breaks or forbids them, and a name is one display line.
FORBIDDEN_CATEGORIES = {"Cc", "Cs", "Zl", "Zp"}


@dataclass(frozen=True)
class Charter:
    name: str
    revision: int
    receipt: str | None
    next_step: str | None
    last_handoff: str | None
    sections: tuple[tuple[str, str], ...]

    @property
    def direction(self) -> str | None:
        return dict(self.sections).get("Direction")


def validate_name(name: str) -> str:
    """Return the display name, or raise ValueError; it is identity, not a research claim."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("workspace name: expected nonempty text")
    if name != name.strip():
        raise ValueError("workspace name: remove leading or trailing spaces")
    if len(name) > MAX_NAME:
        raise ValueError(f"workspace name: at most {MAX_NAME} characters")
    if any(unicodedata.category(character) in FORBIDDEN_CATEGORIES for character in name):
        raise ValueError("workspace name: expected one line without control characters")
    return name


def render_initial(name: str) -> bytes:
    """The charter written by init and adoption: revision 0, direction absent."""
    # JSON strings are valid YAML double-quoted scalars, so any allowed name round-trips.
    quoted = json.dumps(validate_name(name), ensure_ascii=False)
    return (
        "---\n"
        "schema_version: 1\n"
        f"name: {quoted}\n"
        "charter_revision: 0\n"
        "charter_receipt: null\n"
        "next_step: null\n"
        "last_handoff: null\n"
        "---\n" + INITIAL_NOTE
    ).encode()


def validate_charter(document: Document) -> Charter:
    validate_values(document)
    h = mapping(document, document.header, "", set(CHARTER_ORDER))
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    name = text(document, h["name"], "name")
    try:
        validate_name(name)
    except ValueError as error:
        document.fail("name", str(error))
    revision = h["charter_revision"]
    if type(revision) is not int or revision < 0:
        document.fail("charter_revision", "expected nonnegative integer")
    receipt = h["charter_receipt"]
    if revision == 0 and receipt is not None:
        document.fail("charter_receipt", "must be null at revision 0")
    if revision > 0 and (not isinstance(receipt, str) or not RECEIPT.fullmatch(receipt)):
        document.fail("charter_receipt", "expected runs/<stamp>-proposal-<hex>/receipt.md")
    next_step = h["next_step"]
    if next_step is not None:
        text(document, next_step, "next_step")
    handoff = h["last_handoff"]
    if handoff is not None and (not isinstance(handoff, str) or not SESSION.fullmatch(handoff)):
        document.fail("last_handoff", "expected a sessions/ filename <stamp>-<sha256>.md or null")
    found = sections(document)
    position = -1
    for heading, content in found.items():
        if heading not in SECTIONS:
            document.fail(
                f"body.{heading}",
                "unknown workspace section; expected Direction, Constraints or Focus",
            )
        if not content.strip():
            document.fail(f"body.{heading}", "required content empty")
        if SECTIONS.index(heading) < position:
            document.fail(
                f"body.{heading}", "sections must appear as Direction, Constraints, Focus"
            )
        position = SECTIONS.index(heading)
    if document.body_line - 1 + len(document.body.splitlines()) > MAX_LINES:
        document.fail("body", f"{CHARTER_FILE} must fit within {MAX_LINES} lines")
    return Charter(
        name,
        revision,
        receipt,
        next_step,
        handoff,
        tuple((heading, content.strip()) for heading, content in found.items()),
    )
