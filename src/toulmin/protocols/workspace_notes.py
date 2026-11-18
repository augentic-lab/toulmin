"""Append unconfirmed workspace observations under the existing workspace writer lock."""

import re
from pathlib import Path

from toulmin.core.atomic import handoff_mutex, write_atomic
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError
from toulmin.core.repository import Repository
from toulmin.core.workspace import validate_charter
from toulmin.core.workspace_onboarding import MAX_BYTES, utc

HEADER = b"# Workspace notebook\n\nEntries are unconfirmed working observations.\n"


def validate_entry(data: bytes) -> bytes:
    if len(data) > MAX_BYTES:
        raise FormatError("workspace notebook entry exceeds 1,000,000 bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeError as error:
        raise FormatError("workspace notebook entry must be UTF-8") from error
    lines = text.strip().splitlines()
    title = re.fullmatch(r"## (\S+) — (\S.*)", lines[0]) if lines else None
    if title is None:
        raise FormatError("entry must begin with ## UTC_TIMESTAMP — Title")
    utc(title[1], "notebook timestamp")
    for index, prefix in enumerate(("- Source: ", "- Author: ", "- Coverage: ", "- Limits: "), 1):
        if (
            len(lines) <= index
            or not lines[index].startswith(prefix)
            or not lines[index][len(prefix) :].strip()
        ):
            raise FormatError(f"notebook entry requires nonempty {prefix}")
    if not re.fullmatch(r"- Source: \S+; snapshot: \S+", lines[1]):
        raise FormatError("notebook Source line requires source and snapshot provenance")
    if not re.fullmatch(r"- Author: \S+; model: .+; native session: .+", lines[2]):
        raise FormatError(
            "notebook Author line requires author, model and native session (or unknown)"
        )
    body = "\n".join(lines[5:])
    sections = re.split(r"(?m)^### (.+)\n", body)
    if (
        len(sections) != 5
        or sections[0].strip()
        or sections[1::2] != ["Observation", "Next measurement"]
        or not all(s.strip() for s in sections[2::2])
    ):
        raise FormatError("notebook requires nonempty Observation and Next measurement sections")
    if re.search(r"(?m)^## ", body) or re.search(r"\[\[[CEODXSR]-[0-9]+\]\]", text):
        raise FormatError("append one entry; qualify root formal references as [[project/C-001]]")
    return ("\n".join(lines) + "\n").encode()


def append(root: Path, data: bytes) -> Path:
    """Preserve all old bytes; historical hand-written notes remain opaque Markdown."""
    entry = validate_entry(data)
    repository = Repository(root)
    with handoff_mutex(repository.root):
        validate_charter(decode(repository.path("WORKSPACE.md", "file").read_bytes()))
        path = repository.path("runs/notebook.md")
        before = (
            repository.path("runs/notebook.md", "file").read_bytes() if path.exists() else HEADER
        )
        after = before + (b"\n\n" if not before.endswith(b"\n") else b"\n") + entry
        write_atomic(path, after, replace=path.exists())
    return path
