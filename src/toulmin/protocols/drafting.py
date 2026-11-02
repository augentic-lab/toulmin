"""L2: write a fillable draft skeleton under runs/drafts/, never a formal object."""

import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from toulmin.core.documents import FormatError
from toulmin.core.identifiers import ObjectKind
from toulmin.core.repository import Repository
from toulmin.core.skeletons import skeleton

DRAFTS = "runs/drafts"
_ATTEMPTS = 100


def write_draft(
    root: Path,
    project: str,
    kind: ObjectKind,
    name: str | None = None,
    actor: str | None = None,
    now: datetime | None = None,
) -> Path:
    """Create a new skeleton file without overwriting; return its absolute path."""
    if name is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise FormatError(f"{name}: name: expected ASCII letters, digits, '_' or '-' (max 64)")
    repository = Repository(root)
    repository.project(project)
    stamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = f"{kind.value}-{stamp}" + (f"-{name}" if name else "")
    skeleton(kind, project, f"projects/{project}/{DRAFTS}/{base}.md", actor)  # validate first
    repository.path(f"projects/{project}/runs", "directory")
    directory = repository.path(f"projects/{project}/{DRAFTS}")
    directory.mkdir(exist_ok=True)
    repository.path(f"projects/{project}/{DRAFTS}", "directory")
    for attempt in range(1, _ATTEMPTS + 1):
        filename = base + ("" if attempt == 1 else f"-{attempt}") + ".md"
        relative = f"projects/{project}/{DRAFTS}/{filename}"
        destination = repository.path(relative)
        data = skeleton(kind, project, relative, actor).encode("utf-8")
        # Publish a complete file via an exclusive link so no draft is overwritten or partial.
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".draft-", suffix=".tmp") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            try:
                os.link(stream.name, destination)
            except FileExistsError:
                continue
        return destination
    raise FormatError(f"{directory}: draft: {_ATTEMPTS} drafts named {base} already exist")
