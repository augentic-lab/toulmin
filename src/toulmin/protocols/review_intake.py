"""L2: take chosen review drafts in as Objections and record every outcome.

The researcher picks drafts by label; nothing is taken by default. Every request is
validated before anything is written. Each created Objection is followed by an atomic
update of the intake record; a replay recognises Objections created before an
interruption by their source and generated body, so no draft is taken twice.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from toulmin.core.atomic import write_atomic
from toulmin.core.codec import decode, encode, patch_header
from toulmin.core.documents import DIRECTORIES, Document, FormatError
from toulmin.core.identifiers import ObjectId, ObjectKind
from toulmin.core.repository import Repository
from toulmin.core.review import (
    INTAKE_FILE,
    LABEL,
    ReviewDraft,
    objection_body,
    parse_review,
    validate_intake,
)
from toulmin.core.schema import SEVERITIES, utc_text
from toulmin.protocols.intake import publish_locked


@dataclass(frozen=True)
class IntakeLine:
    label: str
    outcome: str  # taken, partly, rejected, or already-<outcome> for a replay
    object_id: str | None


@dataclass(frozen=True)
class IntakeResult:
    run: str
    record: Path
    lines: tuple[IntakeLine, ...]


def find_run(repository: Repository, project: str, output: str) -> tuple[str, str]:
    """Return (Run ID, run directory) for a raw output inside exactly one Run's output."""
    path = PurePosixPath(output)
    runs = f"projects/{project}/runs"
    if path.parent.parent != PurePosixPath(runs):
        raise FormatError(f"{output}: path: expected {runs}/<archive>/<file>")
    owners = []
    for candidate in sorted(repository.path(runs, "directory").glob("R-*.md")):
        run = repository.load(project, ObjectId.parse(candidate.stem))
        if run.header["output"] == str(path.parent):
            owners.append(str(run.object_id))
    if len(owners) != 1:
        found = ", ".join(owners) or "none"
        raise FormatError(
            f"{output}: run: expected exactly one Run whose output is {path.parent} "
            f"(found {found}); archive the Run first"
        )
    role = repository.load(project, ObjectId.parse(owners[0])).header["role"]
    if role in {"synthesizer", "crossval"}:
        raise FormatError(
            f"{output}: run: {owners[0]} is a {role} output, not a review; take drafts in from "
            "the original review output each synthesis group cites (R-NNN/label)"
        )
    return owners[0], str(path.parent)


def _existing(repository: Repository, project: str, run: str, output: str) -> dict[str, str]:
    """Objections already created from this output, keyed by generated body."""
    found: dict[str, str] = {}
    folder = repository.path(f"projects/{project}/{DIRECTORIES[ObjectKind.OBJECTION]}")
    for path in sorted(folder.glob("O-*.md")):
        doc = repository.load(project, ObjectId.parse(path.stem))
        source = doc.header["source"]
        if source.get("kind") == "run" and source["ref"] == run and source["path"] == output:
            found.setdefault(doc.body, str(doc.object_id))
    return found


def intake_review(
    root: Path,
    project: str,
    output_path: str,
    actor: str,
    confirmed: bool,
    take: dict[str, str | None] | None = None,
    reject: dict[str, str] | None = None,
    partly: dict[str, str] | None = None,
) -> IntakeResult:
    """Apply the researcher's choices for drafts in one archived raw review output.

    `take` maps label → severity override (None keeps the reviewer's); an override is
    recorded as partly adopted. `reject` maps label → reason. `partly` maps label → an
    existing Objection the researcher wrote from that draft by hand.
    """
    take, reject, partly = dict(take or {}), dict(reject or {}), dict(partly or {})
    repository = Repository(root)
    repository.project(project)
    output = repository.relative(output_path)
    raw_path = repository.path(output, "file")
    run, directory = find_run(repository, project, output)
    drafts = {
        draft.label: draft
        for draft in parse_review(raw_path.read_text(encoding="utf-8"), str(raw_path))
    }
    if not actor.strip():
        raise FormatError("confirmed_by.actor: expected nonempty string")
    chosen = [*take, *reject, *partly]
    if not chosen:
        raise FormatError(f"{output}: nothing to record; choose drafts with take/reject/partly")
    for label in chosen:
        if not LABEL.fullmatch(label) or label not in drafts:
            raise FormatError(f"{output}: {label}: no such draft label")
        if chosen.count(label) > 1:
            raise FormatError(f"{output}: {label}: given more than one outcome")
    for label, severity in take.items():
        if severity is not None and severity not in SEVERITIES:
            raise FormatError(f"{label}: severity: expected one of {SEVERITIES}")
        try:
            target, _ = repository.resolve(project, drafts[label].target)
        except (OSError, ValueError) as error:
            raise FormatError(f"{label}: target {drafts[label].target}: {error}") from error
        if target.object_id.kind != ObjectKind.CLAIM:
            raise FormatError(f"{label}: target: expected a Claim")
    for label, reason in reject.items():
        if not reason.strip():
            raise FormatError(f"{label}: reason: rejecting a draft needs a reason")
    for label, value in partly.items():
        objection = repository.load(project, _objection_id(label, value))
        source = objection.header["source"]
        if source.get("kind") != "run" or source["ref"] != run or source["path"] != output:
            objection.fail("source", f"must cite {run} and {output} to record {label}")
    if not confirmed:
        raise FormatError(f"{output}: explicit researcher confirmation required; nothing written")

    record_path = repository.path(f"{directory}/{INTAKE_FILE}")
    lines: list[IntakeLine] = []
    with repository.creation_lock(project):
        outcomes = _load_record(record_path, run, output)
        planned: list[tuple[str, str, str | None, str | None]] = []
        for label in chosen:
            wanted = "rejected" if label in reject else "partly" if label in partly else "taken"
            if label in take and take[label] not in {None, drafts[label].severity}:
                wanted = "partly"
            if label in outcomes:
                previous = outcomes[label]
                if previous["outcome"] != wanted:
                    raise FormatError(
                        f"{record_path}: {label}: already {previous['outcome']}; "
                        "an outcome is never changed"
                    )
                lines.append(IntakeLine(label, f"already-{wanted}", previous.get("object")))
                continue
            planned.append((label, wanted, reject.get(label), partly.get(label)))
        existing = _existing(repository, project, run, output) if planned else {}
        for label, wanted, why, object_id in planned:
            if label in take:
                draft = drafts[label]
                object_id = existing.get(objection_body(draft)) or _create(
                    repository, project, run, output, draft, take[label], actor
                )
            entry: dict[str, Any] = {"label": label, "outcome": wanted}
            if object_id is not None:
                entry["object"] = object_id
            if why is not None:
                entry["reason"] = why.strip()
            entry.update(by=actor, at=utc_text(datetime.now(UTC)))
            _append(record_path, run, output, entry)
            lines.append(IntakeLine(label, wanted, object_id))
    return IntakeResult(run, record_path, tuple(lines))


def _objection_id(label: str, value: str) -> ObjectId:
    try:
        object_id = ObjectId.parse(value)
    except ValueError as error:
        raise FormatError(f"{label}: object: {error}") from error
    if object_id.kind != ObjectKind.OBJECTION:
        raise FormatError(f"{label}: object: expected an Objection ID")
    return object_id


def _create(
    repository: Repository,
    project: str,
    run: str,
    output: str,
    draft: ReviewDraft,
    severity: str | None,
    actor: str,
) -> str:
    header = {
        "status": "open",
        "source": {"kind": "run", "ref": run, "path": output},
        "target": draft.target,
        "severity": severity or draft.severity,
    }
    body = objection_body(draft)
    path = publish_locked(
        repository, project, ObjectKind.OBJECTION, header, Document({}, body, output), actor
    )
    return path.stem


def _load_record(path: Path, run: str, output: str) -> dict[str, dict[str, Any]]:
    if not path.exists() and not path.is_symlink():
        return {}
    record = decode(path.read_bytes(), str(path))
    outcomes = validate_intake(record)
    if record.header["run"] != run or record.header["output"] != output:
        record.fail("run", f"record belongs to {record.header['run']} {record.header['output']}")
    return outcomes


def _append(path: Path, run: str, output: str, entry: dict[str, Any]) -> None:
    if path.exists():
        data = path.read_bytes()
        current = decode(data, str(path)).header["outcomes"]
        updated = patch_header(data, {"outcomes": [*current, entry]})
        replace = True
    else:
        header = {"schema_version": 1, "run": run, "output": output, "outcomes": [entry]}
        body = (
            "Intake outcomes for the review drafts in this archive. Written by "
            "`toulmin intake`; entries are appended, never changed.\n"
        )
        updated = encode(Document(header, body))
        replace = False
    validate_intake(decode(updated, str(path)))
    write_atomic(path, updated, replace=replace)
