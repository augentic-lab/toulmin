"""L2: decide project proposals (H3): object drafts and ruling proposals.

Reason for this L2 addition (docs/protocols.md, H3): the agent marks an item ready by putting
it under ``projects/NAME/runs/proposals/``; the researcher decides it in ``toulmin decide``.
Application reuses ``new`` (create_object) and ``rule`` (apply_ruling) unchanged in meaning,
with the researcher as actor. Each decision is recorded in an outcome file beside the
proposal; the proposal itself is never edited, moved or deleted.

An ``applying`` outcome is written before anything else changes, so an interrupted
application is never repeated blindly: the next preview looks for the object or ruling it may
already have produced and offers to record that instead.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from toulmin.core.atomic import digest, write_atomic
from toulmin.core.codec import decode
from toulmin.core.documents import DIRECTORIES, FormatError, sections
from toulmin.core.identifiers import ObjectId
from toulmin.core.project_proposals import (
    OBJECT_KINDS,
    OUTCOME_SUFFIX,
    PROPOSALS,
    RULING,
    Outcome,
    RulingProposal,
    proposal_kind,
    render_outcome,
    validate_outcome,
    validate_ruling_proposal,
)
from toulmin.core.repository import Repository
from toulmin.core.schema import utc_text
from toulmin.protocols.intake import create_object
from toulmin.protocols.ruling import RulingResult, apply_ruling


@dataclass(frozen=True)
class Pending:
    path: str  # root-relative proposal file
    kind: str  # claim … spec, or ruling
    interrupted: bool  # an ``applying`` outcome exists


@dataclass(frozen=True)
class Inventory:
    items: tuple[Pending, ...]
    unrecognized: tuple[str, ...]  # files in runs/proposals that are not named as proposals
    errors: tuple[str, ...]


@dataclass(frozen=True)
class Preview:
    path: str
    kind: str
    sha256: str
    text: str  # the proposal as written
    problems: tuple[str, ...]
    target: str | None  # predicted object path (objects) or the ruled object ID (rulings)
    ruling: RulingProposal | None = None
    decision: str | None = None  # the Decision the ruling cites, resolved to D-NNN
    change: RulingResult | None = None
    interrupted: bool = False
    recovered: str | None = None  # object or ruling an interrupted application produced


def outcome_path(relative: str) -> str:
    return relative.removesuffix(".md") + OUTCOME_SUFFIX


def _folder(project: str) -> str:
    return f"projects/{project}/{PROPOSALS}"


def _outcome(repository: Repository, relative: str) -> Outcome | None:
    candidate = outcome_path(relative)
    path = repository.path(candidate)
    if not path.exists() and not path.is_symlink():
        return None
    data = repository.path(candidate, "file").read_bytes()
    return validate_outcome(decode(data, candidate))


def inventory(root: Path, project: str) -> Inventory:
    """Undecided proposals of one project: object drafts first, then rulings, by filename."""
    repository = Repository(root)
    repository.project(project)
    folder = repository.path(_folder(project))
    if not folder.exists() and not folder.is_symlink():
        return Inventory((), (), ())
    repository.path(_folder(project), "directory")
    objects: list[Pending] = []
    rulings: list[Pending] = []
    unrecognized: list[str] = []
    errors: list[str] = []
    for entry in sorted(folder.iterdir()):
        name = entry.name
        relative = f"{_folder(project)}/{name}"
        if name.startswith(".") or name.endswith(OUTCOME_SUFFIX):
            continue
        kind = proposal_kind(name)
        if kind is None:
            unrecognized.append(relative)
            continue
        try:
            repository.path(relative, "file")
            outcome = _outcome(repository, relative)
        except (OSError, ValueError) as error:
            errors.append(str(error))
            continue
        if outcome is not None and outcome.disposition != "applying":
            continue
        item = Pending(relative, kind, outcome is not None)
        (rulings if kind == RULING else objects).append(item)
    return Inventory(tuple(objects + rulings), tuple(unrecognized), tuple(errors))


def _resolve_decision(repository: Repository, project: str, value: str | None) -> str | None:
    """A Decision reference as given, or the D-NNN an applied decision proposal created."""
    if value is None or proposal_kind(value) != "decision":
        return value
    relative = f"{_folder(project)}/{value}"
    repository.path(relative, "file")
    outcome = _outcome(repository, relative)
    if outcome is None or outcome.disposition == "applying":
        raise FormatError(
            f"decision: proposal {value} is not decided yet; decide it first (decide offers "
            "object drafts before rulings)"
        )
    if outcome.disposition == "rejected":
        raise FormatError(f"decision: proposal {value} was rejected ({outcome.reason})")
    return outcome.result


def _load(repository: Repository, project: str, relative: str) -> tuple[str, bytes]:
    if not relative.startswith(_folder(project) + "/") or "/" in relative.removeprefix(
        _folder(project) + "/"
    ):
        raise FormatError(
            f"{relative}: proposal: expected a file directly under {_folder(project)}"
        )
    kind = proposal_kind(relative.rsplit("/", 1)[1])
    if kind is None:
        raise FormatError(f"{relative}: proposal: expected KIND-YYYYMMDDTHHMMSSZ[-name].md")
    return kind, repository.path(relative, "file").read_bytes()


def _created_after(
    repository: Repository, project: str, kind: str, raw: bytes, since: str
) -> str | None:
    """An object an interrupted application created: same body, created at or after ``since``."""
    body = decode(raw).body
    directory = repository.path(
        f"projects/{project}/{DIRECTORIES[OBJECT_KINDS[kind]]}", "directory"
    )
    for path in sorted(directory.glob("*.md")):
        document = decode(path.read_bytes(), str(path))
        if document.body == body and str(document.header.get("created", "")) >= since:
            return str(document.header["id"])
    return None


def _ruled(
    repository: Repository, project: str, proposal: RulingProposal, decision: str | None
) -> bool:
    """Whether the object already carries everything the ruling proposal asks for."""
    document = repository.load(project, ObjectId.parse(proposal.object))
    if proposal.status is not None and document.header["status"] != proposal.status:
        return False
    if decision is not None and decision not in document.header.get("decisions", []):
        return False
    body = sections(document)
    return all(text.strip() in body.get(name, "") for name, text in proposal.texts.items())


def preview(root: Path, project: str, relative: str) -> Preview:
    """Everything decide shows for one proposal; writes nothing."""
    repository = Repository(root)
    repository.project(project)
    kind, raw = _load(repository, project, relative)
    sha = digest(raw)
    text = raw.decode("utf-8", errors="replace")
    outcome = _outcome(repository, relative)
    if outcome is not None and outcome.disposition != "applying":
        return Preview(relative, kind, sha, text, (f"already {outcome.disposition}",), None)
    interrupted = outcome is not None
    if kind != RULING:
        recovered = None
        if outcome is not None:
            recovered = _created_after(repository, project, kind, raw, outcome.at)
        try:
            path = create_object(
                root, project, OBJECT_KINDS[kind], relative, "preview", False, preview=True
            )
        except (OSError, ValueError) as error:
            return Preview(
                relative,
                kind,
                sha,
                text,
                (str(error),),
                None,
                None,
                None,
                None,
                interrupted,
                recovered,
            )
        target = path.relative_to(repository.root).as_posix()
        return Preview(
            relative, kind, sha, text, (), target, None, None, None, interrupted, recovered
        )
    try:
        proposal = validate_ruling_proposal(decode(raw, relative))
    except (OSError, ValueError) as error:
        return Preview(
            relative, kind, sha, text, (str(error),), None, None, None, None, interrupted
        )
    try:
        decision = _resolve_decision(repository, project, proposal.decision)
        recovered = None
        if outcome is not None and _ruled(repository, project, proposal, decision):
            recovered = proposal.object
        change = None
        if recovered is None:
            change = apply_ruling(
                root,
                project,
                proposal.object,
                "preview",
                False,
                status=proposal.status,
                decision=decision,
                links=proposal.links or None,
                texts=proposal.texts,
                preview=True,
            )
    except (OSError, ValueError) as error:
        return Preview(
            relative,
            kind,
            sha,
            text,
            (str(error),),
            proposal.object,
            proposal,
            None,
            None,
            interrupted,
        )
    return Preview(
        relative,
        kind,
        sha,
        text,
        (),
        proposal.object,
        proposal,
        decision,
        change,
        interrupted,
        recovered,
    )


def _write_outcome(
    repository: Repository, relative: str, outcome: Outcome, *, replace: bool
) -> None:
    write_atomic(repository.path(outcome_path(relative)), render_outcome(outcome), replace=replace)


def apply(
    root: Path, project: str, relative: str, actor: str, sha256: str, approval_text: str
) -> Outcome:
    """Apply the proposal exactly as previewed (``sha256``); return the applied outcome."""
    if not actor.strip():
        raise FormatError("actor: expected nonempty string")
    repository = Repository(root)
    current = preview(root, project, relative)
    if current.sha256 != sha256:
        raise FormatError(f"{relative}: changed since the preview; nothing written")
    if current.problems:
        raise FormatError(f"{relative}: {current.problems[0]}")
    now = utc_text(datetime.now(UTC))
    marker = Outcome(relative, sha256, "applying", actor, now, approval_text, None, None)
    # The marker is written exclusively first: a second decider fails here, and a crash after
    # this point leaves evidence that the next preview checks before applying again.
    _write_outcome(repository, relative, marker, replace=current.interrupted)
    result = current.recovered
    if result is None and current.kind != RULING:
        created = create_object(root, project, OBJECT_KINDS[current.kind], relative, actor, True)
        result = created.stem
    elif result is None:
        ruling = current.ruling
        assert ruling is not None
        ruled = apply_ruling(
            root,
            project,
            ruling.object,
            actor,
            True,
            status=ruling.status,
            decision=current.decision,
            links=ruling.links or None,
            texts=ruling.texts,
        )
        result = ruled.object_id
    done = Outcome(relative, sha256, "applied", actor, now, approval_text, None, result)
    _write_outcome(repository, relative, done, replace=True)
    return done


def reject(
    root: Path, project: str, relative: str, actor: str, reason: str, sha256: str
) -> Outcome:
    """Record the researcher's reason for not applying the proposal; nothing else changes."""
    if not actor.strip():
        raise FormatError("actor: expected nonempty string")
    if not reason.strip():
        raise FormatError("reason: a rejection records the researcher's reason")
    repository = Repository(root)
    repository.project(project)
    _, raw = _load(repository, project, relative)
    if digest(raw) != sha256:
        raise FormatError(f"{relative}: changed since the preview; nothing written")
    existing = _outcome(repository, relative)
    if existing is not None:
        if existing.disposition != "applying":
            raise FormatError(f"{relative}: already {existing.disposition}")
        raise FormatError(
            f"{relative}: an interrupted application must be finished or checked first"
        )
    outcome = Outcome(
        relative, sha256, "rejected", actor, utc_text(datetime.now(UTC)), None, reason.strip(), None
    )
    _write_outcome(repository, relative, outcome, replace=False)
    return outcome
