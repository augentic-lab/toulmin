"""L2 confirmed child creation: input -> sealed packet -> create or reject (contract 9).

A child project appears only from a packet the researcher reviewed, in one rename,
with its creation provenance and a linked workspace receipt. Creation forces no
Claim or Decision, changes no workspace record and never starts a native session;
opening the child is a separate, retryable step.
"""

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from toulmin.core.atomic import digest, handoff_mutex, sync_directory, write_atomic
from toulmin.core.codec import decode
from toulmin.core.creation import (
    CREATION_DIR,
    CREATION_RECORD,
    CreationInput,
    CreationPacket,
    CreationTarget,
    creation_directory,
    render_charter,
    render_creation_packet,
    render_record,
    staging_directory,
    validate_creation_input,
    validate_creation_packet,
    validate_record,
)
from toulmin.core.documents import DIRECTORIES, FormatError
from toulmin.core.inspection import marker_errors
from toulmin.core.proposals import MAX_BYTES, PACKET_DIR, SEAL, Receipt, render_receipt
from toulmin.core.repository import Repository
from toulmin.core.schema import utc_text
from toulmin.core.workspace_journal import (
    JOURNAL,
    Image,
    Intent,
    finish,
    pending,
    prepare,
    read_intent,
    remove_completed,
)
from toulmin.protocols.workspace_change import (
    HANDOFF_DIR,
    _pin,
    _relative,
    _repository,
    _sources,
    pin_problems,
    publish_sealed,
    receipt_for,
    source_problems,
)

GITKEEP = (*DIRECTORIES.values(), "sessions")


@dataclass(frozen=True)
class CreationLoaded:
    directory: str
    seal: str
    packet: CreationPacket
    body: str
    input: CreationInput


@dataclass(frozen=True)
class CreationOutcome:
    """status: proposed, preview, created, recovered, replayed, rejected, incomplete."""

    status: str
    loaded: CreationLoaded
    receipt: Receipt | None = None
    problems: tuple[str, ...] = ()

    @property
    def receipt_path(self) -> str:
        return f"{self.loaded.directory}/receipt.md"

    @property
    def project(self) -> str:
        return self.loaded.packet.project


def propose(
    root: Path,
    name: str,
    input_path: str,
    now: datetime | None = None,
    token: str | None = None,
) -> CreationOutcome:
    """Freeze one sealed creation packet; no project directory is created."""
    repository = _repository(root)
    relative = _relative(repository, input_path)
    if CREATION_DIR.fullmatch(relative.removesuffix("/packet.md")):
        raise FormatError(f"{relative}: this is already a packet; preview it with project create")
    if not relative.startswith("runs/drafts/"):
        raise FormatError(f"{relative}: input: a creation input lives in root runs/drafts/")
    data = repository.path(relative, "file").read_bytes()
    if len(data) > MAX_BYTES:
        raise FormatError(f"{relative}: input exceeds {MAX_BYTES} bytes; shorten the input")
    location = str(repository.root / relative)
    value = validate_creation_input(decode(data, location))
    if value.project != name:
        raise FormatError(
            f"{relative}: project: the input creates {value.project}, the command names {name}"
        )
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    token = token or uuid.uuid4().hex
    directory = f"runs/{moment.strftime('%Y%m%dT%H%M%SZ')}-project-{token}"
    with handoff_mutex(repository.root):
        if pending(repository):
            raise FormatError("an incomplete workspace publication exists; finish it first")
        if value.supersedes is not None:
            _require_pending(repository, value.supersedes)
        if os.path.lexists(repository.root / directory):
            raise FormatError(f"{directory}: packet already exists; retry in a second")
        occupied = _occupied(repository, name, None)
        if occupied is not None:
            raise FormatError(occupied)
        problems = _relationship_problems(repository, value)
        problems += marker_errors(repository, None, value.brief, f"{location} (initial Brief)")
        if problems:
            raise FormatError("; ".join(problems))
        charter = render_charter(value)
        brief = value.brief.encode()
        sources, snapshots, lines = _sources(repository, value.sources)
        pins = [_pin(repository, pin.resource, pin.revision, pin.sha256) for pin in value.pins]
        lines += [
            f"- pinned resource {pin['resource']} revision {pin['revision']} "
            + (f"({pin['method']} {pin['sha256'][:16]}…)" if pin["sha256"] else "(external)")
            for pin in pins
        ]
        targets = [
            (CreationTarget(f"projects/{name}/PROJECT.md", digest(charter), "targets/PROJECT.md"),
             charter),
            (CreationTarget(f"projects/{name}/brief.md", digest(brief), "targets/brief.md"),
             brief),
        ]  # fmt: skip
        packet = render_creation_packet(
            utc_text(moment), value, relative, digest(data), sources, pins, targets, lines
        )
        files = {"packet.md": packet, "input.md": data, **snapshots}
        files.update({target.after: after for target, after in targets})
        publish_sealed(repository, directory, files, digest(packet), ".creation-prepare-")
    return CreationOutcome("proposed", load(repository.root, directory))


def _relationship_problems(repository: Repository, value: CreationInput) -> list[str]:
    problems = []
    for item in value.relationships:
        charter = repository.root / "projects" / item.project / "PROJECT.md"
        if not charter.is_file() or charter.is_symlink():
            problems.append(f"relationships: {item.project}: no such project")
    return problems


def _occupied(repository: Repository, name: str, record: str | None) -> str | None:
    """Why ``projects/NAME`` cannot be created now, naming who owns it (F04)."""
    target = repository.root / "projects" / name
    if not os.path.lexists(target):
        return None
    owner = "an existing project"
    try:
        path = repository.path(f"projects/{name}/{CREATION_RECORD}", "file")
        created = validate_record(decode(path.read_bytes(), str(path)), name)
        if record is not None and created.packet == record:
            return (
                f"projects/{name}: created from this packet by {created.actor} at {created.at}, "
                f"but {created.packet.removesuffix('/packet.md')}/receipt.md is missing and no "
                "journal exists; nothing written. Inspect the child before any further action"
            )
        owner = f"a project created from {created.packet} by {created.actor}"
    except (OSError, ValueError):
        pass
    return (
        f"projects/{name}: occupied by {owner}; never replaced. Choose another name or "
        "inspect the existing project"
    )


def load(root: Path, value: str) -> CreationLoaded:
    """Verify a creation packet's seal and every frozen digest (F02 for other artifacts)."""
    repository = Repository(root)
    relative = _relative(repository, value)
    if PACKET_DIR.fullmatch(relative.removesuffix("/packet.md")):
        raise FormatError(f"{relative}: this is a workspace change packet; use workspace apply")
    if HANDOFF_DIR.fullmatch(relative.removesuffix("/draft.md")):
        raise FormatError(f"{relative}: this is a handoff draft; use aoe handoff --apply")
    if relative.startswith("runs/drafts/"):
        raise FormatError(
            f"{relative}: this is an input, not a reviewed packet; run project propose --input"
        )
    directory = creation_directory(relative)
    base = repository.path(directory, "directory")
    packet = repository.path(f"{directory}/packet.md", "file").read_bytes()
    sealed = repository.path(f"{directory}/seal", "file").read_bytes()
    if not SEAL.fullmatch(sealed.decode("utf-8", "replace")) or sealed.decode().strip() != digest(
        packet
    ):
        raise FormatError(
            f"{directory}: packet changed after preview (seal mismatch); propose again"
        )
    document = decode(packet, str(base / "packet.md"))
    parsed = validate_creation_packet(document)
    frozen: list[tuple[str, str | None]] = [("input.md", parsed.input_sha256)]
    frozen += [(item.snapshot, item.sha256) for item in parsed.sources if item.snapshot]
    frozen += [(target.after, target.after_sha256) for target in parsed.targets]
    for name, expected in frozen:
        if digest(repository.path(f"{directory}/{name}", "file").read_bytes()) != expected:
            raise FormatError(f"{directory}/{name}: changed after preview; propose again")
    snapshot = repository.path(f"{directory}/input.md", "file")
    frozen_input = validate_creation_input(decode(snapshot.read_bytes(), str(snapshot)))
    if frozen_input.project != parsed.project:
        raise FormatError(f"{directory}/input.md: project does not match the packet")
    return CreationLoaded(directory, sealed.decode().strip(), parsed, document.body, frozen_input)


def _successor(repository: Repository, directory: str) -> str | None:
    runs = repository.root / "runs"
    for path in sorted(runs.iterdir()) if runs.is_dir() else ():
        candidate = f"runs/{path.name}"
        if candidate == directory or not CREATION_DIR.fullmatch(candidate):
            continue
        try:
            loaded = load(repository.root, candidate)
        except (OSError, ValueError):
            continue  # an invalid packet supersedes nothing
        if loaded.packet.supersedes == directory:
            return candidate
    return None


def _require_pending(repository: Repository, directory: str) -> None:
    load(repository.root, directory)
    if os.path.lexists(repository.root / directory / "receipt.md"):
        raise FormatError(f"supersedes: {directory} already has a receipt; propose anew")
    successor = _successor(repository, directory)
    if successor is not None:
        raise FormatError(f"supersedes: {directory} is already superseded by {successor}")


def check(root: Path, loaded: CreationLoaded) -> list[str]:
    """Reasons create would be refused now: its own target, sources, pins and links only.

    Shared rules and templates are not compared against pristine copies, and
    unrelated workspace edits never conflict.
    """
    repository = Repository(root)
    record = f"{loaded.directory}/packet.md"
    problems = []
    occupied = _occupied(repository, loaded.packet.project, record)
    if occupied is not None:
        problems.append(occupied)
    staging = staging_directory(loaded.directory)
    if os.path.lexists(repository.root / staging):
        problems.append(
            f"{staging}: staging remnant without a journal; inspect it and remove it by hand"
        )
    problems += source_problems(repository, loaded.packet.sources)
    problems += pin_problems(repository, loaded.packet.pins)
    problems += _relationship_problems(repository, loaded.input)
    problems += marker_errors(
        repository, None, loaded.input.brief, f"{loaded.directory}/targets/brief.md"
    )
    return problems


def create(
    root: Path,
    name: str,
    value: str,
    actor: str | None,
    *,
    confirmed: bool,
    approval_text: str | None = None,
    now: datetime | None = None,
) -> CreationOutcome:
    """Preview (not confirmed) or publish one reviewed child; replays are idempotent."""
    repository = _repository(root)
    if not confirmed:
        return _create(repository, name, value, None, False, approval_text, now)
    if actor is None or not actor.strip():
        raise FormatError("create: a confirming actor is required (--confirmed-by)")
    with handoff_mutex(repository.root):
        return _create(repository, name, value, actor, True, approval_text, now)


def _named(loaded: CreationLoaded, name: str) -> None:
    if loaded.packet.project != name:
        raise FormatError(
            f"{loaded.directory}: this packet creates {loaded.packet.project}, not {name}; "
            f"rerun with NAME {loaded.packet.project}"
        )


def _create(
    repository: Repository,
    name: str,
    value: str,
    actor: str | None,
    confirmed: bool,
    approval_text: str | None,
    now: datetime | None,
) -> CreationOutcome:
    intent = read_intent(repository) if pending(repository) else None
    loaded = load(repository.root, value)
    _named(loaded, name)
    record = f"{loaded.directory}/packet.md"
    if intent is not None and intent.record != record:
        raise FormatError(
            f"incomplete {intent.operation} for {intent.record}; rerun that operation's "
            "command first"
        )
    receipt = receipt_for(repository, loaded.directory, loaded.seal)
    if receipt is not None and intent is None:
        if receipt.disposition == "rejected":
            raise FormatError(
                f"{loaded.directory}: rejected by {receipt.actor} ({receipt.reason}); "
                "propose anew without supersedes"
            )
        return CreationOutcome("replayed", loaded, receipt)
    if intent is not None:
        if intent.record_sha256 != loaded.seal:
            raise FormatError(f"{JOURNAL}: journal does not match this packet's seal; journal kept")
        if not confirmed:
            return CreationOutcome(
                "incomplete",
                loaded,
                problems=("creation interrupted; rerun this create with --confirm to finish",),
            )
        notes = []
        if actor != intent.actor:
            notes.append(
                f"--confirmed-by {actor} ignored; recovery keeps the first confirmation "
                f"by {intent.actor} at {intent.at}"
            )
        finish(repository)
        return CreationOutcome(
            "recovered",
            loaded,
            receipt_for(repository, loaded.directory, loaded.seal),
            tuple(notes),
        )
    problems = check(repository.root, loaded)
    successor = _successor(repository, loaded.directory)
    if successor is not None:
        problems.insert(0, f"superseded by {successor}; review that packet instead")
    if not confirmed:
        return CreationOutcome("preview", loaded, problems=tuple(problems))
    assert actor is not None
    if problems:
        raise FormatError("; ".join(problems) + ". Nothing written; preview a refreshed proposal")
    remove_completed(repository)
    at = utc_text((now or datetime.now(UTC)).astimezone(UTC))
    images = _child_images(repository, loaded, actor, at)
    results = [
        {"path": image.path, "before_sha256": None, "after_sha256": digest(image.after)}
        for image in images
        if image.path.endswith(("/PROJECT.md", "/brief.md", f"/{CREATION_RECORD}"))
    ]
    data = render_receipt(record, loaded.seal, "applied", actor, at, approval_text, None, results)
    images.append(Image(f"{loaded.directory}/receipt.md", None, data))
    staging = staging_directory(loaded.directory)
    prepare(
        repository,
        Intent("project-create", record, loaded.seal, actor, at, approval_text, tuple(images),
               staging),
    )  # fmt: skip
    finish(repository)
    return CreationOutcome(
        "created", loaded, receipt_for(repository, loaded.directory, loaded.seal)
    )


def _child_images(
    repository: Repository, loaded: CreationLoaded, actor: str, at: str
) -> list[Image]:
    """Every file of the new child: documents, empty collections and provenance."""
    base = f"projects/{loaded.packet.project}"

    def frozen(name: str) -> bytes:
        return repository.path(f"{loaded.directory}/{name}", "file").read_bytes()

    images = [
        Image(f"{base}/PROJECT.md", None, frozen("targets/PROJECT.md")),
        Image(f"{base}/brief.md", None, frozen("targets/brief.md")),
        *(Image(f"{base}/{folder}/.gitkeep", None, b"") for folder in GITKEEP),
        Image(f"{base}/runs/creation/packet.md", None, frozen("packet.md")),
        Image(f"{base}/runs/creation/seal", None, frozen("seal")),
        *(
            Image(f"{base}/runs/creation/{item.snapshot}", None, frozen(item.snapshot))
            for item in loaded.packet.sources
            if item.snapshot is not None
        ),
    ]
    record = render_record(
        loaded.input,
        f"{loaded.directory}/packet.md",
        loaded.seal,
        actor,
        at,
        loaded.packet.sources,
        loaded.packet.pins,
    )
    validate_record(decode(record, f"{base}/{CREATION_RECORD}"), loaded.packet.project)
    images.append(Image(f"{base}/{CREATION_RECORD}", None, record))
    return images


def reject(
    root: Path, name: str, value: str, reason: str, actor: str, now: datetime | None = None
) -> CreationOutcome:
    """Record a final rejection for a pending creation packet; nothing else changes."""
    if not reason.strip():
        raise FormatError("reject: a reason is required (--reason)")
    if not actor.strip():
        raise FormatError("reject: a confirming actor is required (--confirmed-by)")
    repository = _repository(root)
    with handoff_mutex(repository.root):
        loaded = load(repository.root, value)
        _named(loaded, name)
        record = f"{loaded.directory}/packet.md"
        receipt = receipt_for(repository, loaded.directory, loaded.seal)
        if pending(repository) and read_intent(repository).record == record:
            raise FormatError(f"{loaded.directory}: creation incomplete; finish it with create")
        if receipt is not None:
            if receipt.disposition == "rejected":
                return CreationOutcome("replayed", loaded, receipt)
            raise FormatError(
                f"{loaded.directory}: already created ({loaded.directory}/receipt.md); "
                "the child stays; nothing written"
            )
        successor = _successor(repository, loaded.directory)
        if successor is not None:
            raise FormatError(
                f"{loaded.directory}: superseded by {successor}; review or reject that packet"
            )
        at = utc_text((now or datetime.now(UTC)).astimezone(UTC))
        data = render_receipt(record, loaded.seal, "rejected", actor, at, None, reason, [])
        write_atomic(repository.path(f"{loaded.directory}/receipt.md"), data)
        sync_directory(repository.path(loaded.directory))
    return CreationOutcome(
        "rejected", loaded, receipt_for(repository, loaded.directory, loaded.seal)
    )
