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
from toulmin.core.schema import object_order, validate
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
    links: tuple[str, ...] = ()


def _decision(repository: Repository, project: str, value: str, targets: list[ObjectId]) -> str:
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
    for target in targets:
        # A superseding Decision may cite itself; it need not list itself in related.
        if target == decision.object_id and owner == project:
            continue
        if (project, target) not in named:
            decision.fail("related", f"must name {target} (or {project}/{target}) to rule on it")
    return value


# Reference fields some statuses require; rule sets them but never replaces or removes one.
LINKS: dict[ObjectKind, frozenset[str]] = {
    ObjectKind.CLAIM: frozenset({"superseded_by"}),
    ObjectKind.DECISION: frozenset({"superseded_by"}),
    ObjectKind.EXPLORATION: frozenset({"adopted_as"}),
    ObjectKind.SPEC: frozenset({"evidence"}),
}
_TERMINAL = {ObjectKind.CLAIM: "superseded", ObjectKind.DECISION: "superseded"}


def _successor(repository: Repository, project: str, target: ObjectId, value: str) -> ObjectId:
    """A superseding object must be a current object of the same kind in this project."""
    try:
        reference = ObjectRef.parse(value)
    except ValueError as error:
        raise FormatError(f"{value}: superseded_by: {error}") from error
    if reference.project not in {None, project}:
        raise FormatError(f"{value}: superseded_by: successor must be in project {project}")
    if reference.object_id.kind != target.kind or reference.object_id == target:
        raise FormatError(f"{value}: superseded_by: expected another {target.kind.value}")
    successor = repository.load(project, reference.object_id)
    if successor.header["status"] == "superseded":
        successor.fail("status", "successor is itself superseded; name its current successor")
    return reference.object_id


def apply_ruling(
    root: Path,
    project: str,
    object_id: str,
    actor: str,
    confirmed: bool,
    status: str | None = None,
    decision: str | None = None,
    sections: dict[str, str] | None = None,
    links: dict[str, str | list[str]] | None = None,
) -> RulingResult:
    """Record a confirmed status change, section text and/or links; return what changed.

    `sections` maps a body section name to a root-relative (or in-root absolute) file
    whose text is added to that section. `links` sets status-required reference fields
    (superseded_by, adopted_as, or Spec evidence to append).
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
    links = dict(links or {})
    for field in links:
        if field not in LINKS.get(target.kind, frozenset()):
            raise FormatError(f"{object_id}: {field}: not a field rule can set on this object")
    if status is None and not texts and not links:
        raise FormatError(f"{object_id}: nothing to record; pass --status, section text or a link")
    if status is not None and decision is None:
        raise FormatError(
            f"{object_id}: status: every status change requires a researcher Decision"
        )
    if links and decision is None:
        raise FormatError(f"{object_id}: links require a researcher Decision")

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
            if _TERMINAL.get(target.kind) == previous:
                raise FormatError(
                    f"{object_id}: status: {previous} is final for rule; "
                    "correct a mistake by hand with a Decision"
                )
        changes: dict[str, object] = {}
        named = [target]
        for field, value in links.items():
            if field == "evidence":
                existing = list(document.header.get("evidence", []))
                added = [item for item in value if item not in existing]
                if added:
                    changes["evidence"] = [*existing, *added]
                continue
            assert isinstance(value, str)
            if field in document.header:
                if document.header[field] != value:
                    document.fail(field, f"already {document.header[field]}; rule never replaces")
                continue
            if field == "superseded_by":
                named.append(_successor(repository, project, target, value))
            changes[field] = value
        if decision is not None:
            _decision(repository, project, decision, named)

        body = document.body
        for name, content in texts.items():
            try:
                body = put_section(body, name, content)
            except ValueError as error:
                document.fail(f"body.{name}", str(error))
        if status is not None:
            changes["status"] = status
        if decision is not None:
            existing = list(document.header.get("decisions", []))
            if decision not in existing:
                changes["decisions"] = [*existing, decision]
        text = original.decode("utf-8")
        updated = (text[: len(text) - len(document.body)] + body).encode("utf-8")
        if changes:
            updated = patch_header(updated, changes, object_order(target.kind))
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
        tuple(
            f"{field}={value if isinstance(value, str) else ', '.join(value)}"
            for field, value in links.items()
        ),
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
