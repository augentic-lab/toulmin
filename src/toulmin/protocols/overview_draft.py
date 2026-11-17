"""Editable understanding drafts are distinct from confirmed overview checkpoints."""

from pathlib import Path
from uuid import uuid4

from toulmin.core.atomic import write_atomic
from toulmin.core.repository import Repository


def write_overview_draft(root: Path, project: str) -> Path:
    repository = Repository(root)
    repository.project(project)
    current = repository.path(f"projects/{project}/overview.md")
    content = (
        current.read_bytes()
        if current.exists()
        else (
            b"# Project understanding\n\n"
            b"Record sources and uncertainty. This draft is not a research conclusion.\n\n"
            b"## Structure\n<fill: components and entry points>\n\n"
            b"## History\n<fill: established history, researcher account, unknowns>\n\n"
            b"## Current understanding\n<fill: facts, inferences and supporting sources>\n\n"
            b"## Directions\n<fill: candidate directions and their rationale>\n\n"
            b"## Open questions\n<fill: what remains uncertain>\n"
        )
    )
    path = repository.path(f"projects/{project}/runs/drafts/overview-{uuid4().hex}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, content)
    return path
