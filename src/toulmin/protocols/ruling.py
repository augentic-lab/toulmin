"""L2: apply a researcher's confirmed ruling to one stored object.

The tool never chooses a status. It records the researcher's explicit choice, requires an
active Decision that names the object for every status change, keeps all existing text and
writes the complete file atomically or not at all.
"""

from dataclasses import dataclass
from pathlib import Path

from toulmin.core.atomic import write_atomic
from toulmin.core.codec import decode, patch_header
from toulmin.core.documents import DIRECTORIES, STATUSES, FormatError, put_section
from toulmin.core.identifiers import ObjectId, ObjectKind, ObjectRef
from toulmin.core.repository import Repository
from toulmin.core.schema import validate
from toulmin.core.skeletons import PLACEHOLDER


@dataclass(frozen=True)
class RulingResult:
    path: Path
    object_id: str
    previous_status: str
    status: str
    decision: str | None
    sections: tuple[str, ...]
    target: str | None


def _decision(repository: Repository, project: str, value: str, target: ObjectId) -> str:
    try:
        reference = ObjectRef.parse(value)
    except ValueError as error:
        raise FormatError(f"{value}: decision: {error}") from error
    if reference.object_id.kind != ObjectKind.DECISION:
        raise FormatError(f"{value}: decision: expected a Decision reference")
    decision, owner = repository.resolve(project, value)
    repository.validate_links(decision, owner)
    if decision.header["status"] != "active":
        decision.fail("status", "only an active Decision can authorize a ruling")
    named = set()
    for item in decision.header["related"]:
        related = ObjectRef.parse(item)
        named.add(((related.project or owner), related.object_id))
    if (project, target) not in named:
        decision.fail("related", f"must name {target} (or {project}/{target}) to rule on it")
    return value


def apply_ruling(
    root: Path,
    project: str,
    object_id: str,
    actor: str,
    confirmed: bool,
    status: str | None = None,
    decision: str | None = None,
    sections: dict[str, str] | None = None,
) -> RulingResult:
    """Record a confirmed status change and/or section text; return what changed.

    `sections` maps a body section name to a root-relative (or in-root absolute) file
    whose text is added to that section.
    """
    repository = Repository(root)
    repository.project(project)
    try:
        target = ObjectId.parse(object_id)
    except ValueError as error:
        raise FormatError(f"{object_id}: id: {error}") from error
    if not actor.strip():
        raise FormatError("confirmed_by.actor: expected nonempty string")
    if not confirmed:
        raise FormatError(
            f"{object_id}: explicit researcher confirmation required; nothing written"
        )
    if target.kind == ObjectKind.RUN:
        raise FormatError(f"{object_id}: status: Run outcomes are immutable once archived")
    texts: dict[str, str] = {}
    for name, source in (sections or {}).items():
        if name not in _ALLOWED[target.kind]:
            raise FormatError(
                f"{object_id}: body.{name}: rule may add to {sorted(_ALLOWED[target.kind])}"
            )
        path = repository.path(repository.relative(source), "file")
        content = path.read_text(encoding="utf-8")
        if PLACEHOLDER in content:
            raise FormatError(f"{path}: body.{name}: unfilled <fill: ...> placeholder")
        texts[name] = content
    if status is None and not texts:
        raise FormatError(f"{object_id}: nothing to record; pass --status and/or section text")
    if status is not None and decision is None:
        raise FormatError(
            f"{object_id}: status: every status change requires a researcher Decision"
        )

    relative = f"projects/{project}/{DIRECTORIES[target.kind]}/{target}.md"
    with repository.creation_lock(project):
        document = repository.load(project, target)
        original = repository.path(relative, "file").read_bytes()
        previous = document.header["status"]
        if status is not None:
            if status not in STATUSES[target.kind]:
                raise FormatError(f"{object_id}: status: expected one of {STATUSES[target.kind]}")
            if status == previous:
                raise FormatError(f"{object_id}: status: already {status}; nothing to change")
        if decision is not None:
            _decision(repository, project, decision, target)

        body = document.body
        for name, content in texts.items():
            try:
                body = put_section(body, name, content)
            except ValueError as error:
                document.fail(f"body.{name}", str(error))
        changes: dict[str, object] = {}
        if status is not None:
            changes["status"] = status
        if decision is not None:
            existing = list(document.header.get("decisions", []))
            if decision not in existing:
                changes["decisions"] = [*existing, decision]
        text = original.decode("utf-8")
        updated = (text[: len(text) - len(document.body)] + body).encode("utf-8")
        if changes:
            updated = patch_header(updated, changes)
        result = decode(updated, str(repository.path(relative)))
        validate(result)
        repository.validate_links(result, project)
        destination = repository.path(relative, "file")
        if destination.read_bytes() != original:
            raise FormatError(f"{destination}: changed while ruling; nothing written")
        write_atomic(destination, updated, replace=True)
    return RulingResult(
        destination,
        str(target),
        previous,
        status or previous,
        decision,
        tuple(texts),
        document.header.get("target"),
    )


# Sections a ruling may add to: responses and rulings, plus the reason sections that
# formats.md requires for invalidated Evidence and dropped Explorations.
_ALLOWED: dict[ObjectKind, frozenset[str]] = {
    ObjectKind.CLAIM: frozenset(),
    ObjectKind.EVIDENCE: frozenset({"Invalidation"}),
    ObjectKind.OBJECTION: frozenset({"Response", "Ruling"}),
    ObjectKind.DECISION: frozenset(),
    ObjectKind.EXPLORATION: frozenset({"Rationale"}),
    ObjectKind.SPEC: frozenset(),
    ObjectKind.RUN: frozenset(),
}
