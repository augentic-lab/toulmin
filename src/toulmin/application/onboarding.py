"""Prepare bounded source inventories before reviewed research-only publication."""

import uuid
from pathlib import Path

from toulmin.application.sources import inspect_source
from toulmin.core.documents import FormatError
from toulmin.core.identifiers import validate_project_name
from toulmin.core.sources import Source, read_catalog
from toulmin.protocols.context_change import ContextOutcome
from toulmin.protocols.onboarding import OnboardingOutcome, OnboardingSource, propose


def prepare(
    root: Path,
    source: Path,
    project: str,
    work_at: Path | None = None,
    *,
    overview: str | None = None,
) -> OnboardingOutcome:
    validate_project_name(project)
    inspected = inspect_source(root, source)
    items = [(inspected, "reference" if work_at else "working")]
    if work_at:
        target = inspect_source(root, work_at)
        if (
            target.path == inspected.path
            or target.path.is_relative_to(inspected.path)
            or inspected.path.is_relative_to(target.path)
        ):
            raise FormatError(
                "reference and working source must be distinct non-overlapping directories"
            )
        items.append((target, "working"))
    catalog = read_catalog(root)
    from toulmin.core.repository import Repository
    from toulmin.core.sources import LOCAL, parse_bindings

    repo = Repository(root)
    bindings = parse_bindings(repo.path(LOCAL).read_bytes()) if repo.path(LOCAL).exists() else {}
    sources: list[OnboardingSource] = []
    for item, role in items:
        existing = next(
            (
                s
                for s in catalog
                if s.kind == item.kind
                and (s.kind == "directory" or s.identity == item.identity)
                and bindings.get(s.source_id) == (str(item.path), item.filesystem)
            ),
            None,
        )
        source_id = existing.source_id if existing else "source-" + uuid.uuid4().hex[:16]
        if any(s.source.source_id == source_id and s.source.project == project for s in sources):
            raise FormatError(
                "reference and working source IDs conflict; choose distinct directories"
            )
        sources.append(
            OnboardingSource(
                Source(
                    source_id,
                    project,
                    item.kind,
                    role,
                    existing.identity if existing else item.identity,
                ),
                str(item.path),
                item.filesystem,
                item.inventory,
            )
        )
    return propose(root, project, tuple(sources), overview=overview)


def add_source(
    root: Path, project: str, path: Path, *, working: bool = False, rationale: str
) -> ContextOutcome:
    """Inspect a new direction and propose its association; do not copy files."""
    from toulmin.core.repository import Repository
    from toulmin.core.sources import LOCAL, parse_bindings
    from toulmin.protocols.context_change import propose_source_add

    repo = Repository(root)
    repo.project(project)
    item = inspect_source(root, path)
    bindings = parse_bindings(repo.path(LOCAL).read_bytes()) if repo.path(LOCAL).exists() else {}
    existing = next(
        (
            s
            for s in read_catalog(root)
            if s.kind == item.kind
            and (s.kind == "directory" or s.identity == item.identity)
            and bindings.get(s.source_id) == (str(item.path), item.filesystem)
        ),
        None,
    )
    source_id = existing.source_id if existing else "source-" + uuid.uuid4().hex[:16]
    source = Source(
        source_id,
        project,
        item.kind,
        "working" if working else "reference",
        existing.identity if existing else item.identity,
    )
    return propose_source_add(
        root, project, source, str(item.path), item.filesystem, rationale=rationale
    )
