"""L2 reviewed workspace changes: input -> sealed packet -> apply or reject (contract 7).

Only WORKSPACE.md and shared resource descriptions can change, and only through a
packet the researcher reviewed: the seal binds preview to confirmation. Apply checks
the packet's own targets, selected sources and pins, nothing else, so unrelated edits
never conflict. No model is invoked and no project or object is touched.
"""

import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from toulmin.core.activity import ACTIVITY_PATH, validate_activity
from toulmin.core.atomic import digest, handoff_mutex, sync_directory, write_atomic
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError
from toulmin.core.inspection import marker_errors
from toulmin.core.material import material_digest
from toulmin.core.proposals import (
    MAX_BYTES,
    PACKET_DIR,
    SEAL,
    ChangeInput,
    Packet,
    PacketSource,
    Receipt,
    SourceRef,
    Target,
    charter_after,
    check_resource_values,
    describe_source,
    packet_directory,
    render_packet,
    render_receipt,
    validate_change_input,
    validate_packet,
    validate_receipt,
)
from toulmin.core.repository import Repository
from toulmin.core.resources import (
    Description,
    render_description,
    resource_path,
    validate_description,
)
from toulmin.core.schema import utc_text
from toulmin.core.workspace import CHARTER_FILE, validate_charter
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

CREATION_DIR = re.compile(r"runs/[0-9]{8}T[0-9]{6}Z-project-[0-9a-f]{32}")
HANDOFF_DIR = re.compile(r"runs/[0-9]{8}T[0-9]{6}Z-handoff-[0-9a-f]{32}")


@dataclass(frozen=True)
class Loaded:
    directory: str
    seal: str
    packet: Packet
    body: str


@dataclass(frozen=True)
class Outcome:
    """status: proposed, preview, applied, recovered, replayed, rejected, incomplete."""

    status: str
    loaded: Loaded
    receipt: Receipt | None = None
    problems: tuple[str, ...] = ()

    @property
    def receipt_path(self) -> str:
        return f"{self.loaded.directory}/receipt.md"


def _repository(root: Path) -> Repository:
    repository = Repository(root)
    path = repository.root / CHARTER_FILE
    if not os.path.lexists(path):
        raise FormatError(
            f"{repository.root}: workspace state not configured (no {CHARTER_FILE}); "
            "workspace changes need a workspace root"
        )
    charter = repository.path(CHARTER_FILE, "file")
    if not pending(repository):
        # Mid-publication the charter may hold either image or an external edit;
        # recovery reports that precisely, so it is not pre-validated here.
        validate_charter(decode(charter.read_bytes(), str(charter)))
    return repository


def _relative(repository: Repository, value: str) -> str:
    return repository.relative(str(value)).removesuffix("/")


def _check_source_path(value: str) -> None:
    if value.split("/")[0].startswith("."):
        raise FormatError(f"{value}: sources: hidden and journal paths cannot be cited")


def propose(
    root: Path, input_path: str, now: datetime | None = None, token: str | None = None
) -> Outcome:
    """Freeze one sealed packet from a change input; confirmed state is unchanged."""
    repository = _repository(root)
    relative = _relative(repository, input_path)
    if PACKET_DIR.fullmatch(packet_directory_or_none(relative) or ""):
        raise FormatError(f"{relative}: this is already a packet; preview it with workspace apply")
    if not relative.startswith("runs/drafts/"):
        raise FormatError(f"{relative}: input: a change input lives in root runs/drafts/")
    data = repository.path(relative, "file").read_bytes()
    if len(data) > MAX_BYTES:
        raise FormatError(f"{relative}: input exceeds {MAX_BYTES} bytes; shorten the input")
    change = validate_change_input(decode(data, str(repository.root / relative)))
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    token = token or uuid.uuid4().hex
    directory = f"runs/{moment.strftime('%Y%m%dT%H%M%SZ')}-proposal-{token}"
    with handoff_mutex(repository.root):
        if pending(repository):
            raise FormatError("an incomplete workspace publication exists; finish it first")
        if change.supersedes is not None:
            _require_pending(repository, change.supersedes)
        if os.path.lexists(repository.root / directory):
            raise FormatError(f"{directory}: packet already exists; retry in a second")
        sources, snapshots, lines = _sources(repository, change.sources)
        pins = [_pin(repository, pin.resource, pin.revision, pin.sha256) for pin in change.pins]
        lines += [
            f"- pinned resource {pin['resource']} revision {pin['revision']} "
            + (f"({pin['method']} {pin['sha256'][:16]}…)" if pin["sha256"] else "(external)")
            for pin in pins
        ]
        targets = _targets(repository, change, f"{directory}/receipt.md")
        packet = render_packet(
            utc_text(moment),
            relative,
            digest(data),
            change.supersedes,
            sources,
            pins,
            targets,
            change.question,
            change.assumptions,
            lines,
        )
        files = {"packet.md": packet, "input.md": data, **snapshots}
        files.update({target.after: after for target, _, after in targets})
        publish_sealed(repository, directory, files, digest(packet))
    return Outcome("proposed", load(repository.root, directory))


def packet_directory_or_none(value: str) -> str | None:
    try:
        return packet_directory(value)
    except FormatError:
        return None


def _sources(
    repository: Repository, refs: tuple[SourceRef, ...]
) -> tuple[list[PacketSource], dict[str, bytes], list[str]]:
    sources, snapshots, lines = [], {}, []
    for index, source in enumerate(refs, 1):
        if source.url is not None:
            item = PacketSource(None, source.url, None, None, source.coverage)
            sources.append(item)
            lines.append(describe_source(item, None))
            continue
        assert source.path is not None
        _check_source_path(source.path)
        path = repository.path(source.path, "file")
        data = path.read_bytes()
        capture = None
        if ACTIVITY_PATH.fullmatch(source.path):
            activity = validate_activity(decode(data, str(path)))
            if activity.coverage != source.coverage:
                raise FormatError(
                    f"{source.path}: coverage: the activity record says {activity.coverage}, "
                    f"the input says {source.coverage}"
                )
            capture = (activity.coverage, activity.complete, activity.limits)
        snapshot = None
        if len(data) <= MAX_BYTES:
            suffix = PurePosixPath(source.path).suffix
            # Keep a readable suffix only when it fits the packet's snapshot name rule.
            suffix = suffix if re.fullmatch(r"\.[A-Za-z0-9]+", suffix) else ""
            snapshot = f"sources/{index}{suffix}"
            snapshots[snapshot] = data
        item = PacketSource(source.path, None, digest(data), snapshot, source.coverage)
        sources.append(item)
        lines.append(describe_source(item, capture))
    return sources, snapshots, lines


def _description(repository: Repository, name: str) -> tuple[bytes, Description]:
    relative = resource_path(name)
    path = repository.path(relative, "file")
    data = path.read_bytes()
    return data, validate_description(decode(data, str(path)), name)


def _material(repository: Repository, path: str, method: str, expected: str | None) -> None:
    """Verify local material against its recorded digest; never substitute."""
    location = repository.path(path)
    if not location.exists():
        raise FormatError(f"{path}: material missing; restore it or propose a new revision")
    if method == "file" and location.is_dir():
        raise FormatError(f"{path}: version.method: path is a directory; use tree-v1")
    if method == "tree-v1" and not location.is_dir():
        raise FormatError(f"{path}: version.method: path is not a directory; use file")
    try:
        actual = material_digest(location, method)
    except ValueError as error:
        raise FormatError(str(error)) from error
    if actual != expected:
        raise FormatError(
            f"{path}: material digest {actual} differs from the recorded {expected}; "
            "the latest content is never substituted"
        )


def _pin(repository: Repository, name: str, revision: int, sha256: str | None) -> dict[str, Any]:
    data, description = _description(repository, name)
    if description.revision != revision:
        raise FormatError(
            f"pin {name}: revision {revision} requested, description is at {description.revision}"
        )
    if description.sha256 != sha256:
        raise FormatError(f"pin {name}: sha256 differs from the registered material version")
    if description.path is not None:
        _material(repository, description.path, description.method, description.sha256)
    return {
        "resource": name,
        "revision": revision,
        "description_sha256": digest(data),
        "path": description.path,
        "url": description.url,
        "method": description.method,
        "sha256": description.sha256,
    }


def _targets(
    repository: Repository, change: ChangeInput, receipt: str
) -> list[tuple[Target, bytes | None, bytes]]:
    planned: list[tuple[str, bytes | None, bytes]] = []
    if change.charter is not None:
        charter = repository.path(CHARTER_FILE, "file").read_bytes()
        after = charter_after(charter, change.charter, receipt)
        location = str(repository.root / CHARTER_FILE)
        document = decode(after, f"{location} (after image)")
        validate_charter(document)
        problems = marker_errors(repository, None, document.body, location)
        if problems:
            raise FormatError("; ".join(problems))
        existing = decode(charter)
        if document.body == existing.body and document.header["name"] == existing.header["name"]:
            raise FormatError("charter change leaves the name and sections unchanged")
        planned.append((CHARTER_FILE, charter, after))
    for item in change.resources:
        relative = resource_path(item.resource)
        exists = os.path.lexists(repository.root / relative)
        field = f"resource {item.resource}"
        before: bytes | None = None
        values: dict[str, Any] = {"notes": None}
        revision, previous = 1, None
        if item.action == "register":
            if exists:
                raise FormatError(f"{relative}: occupied; use action revise")
        else:
            if not exists:
                raise FormatError(f"{relative}: not registered; use action register")
            before, current = _description(repository, item.resource)
            values, revision, previous = current.fields(), current.revision + 1, digest(before)
        merged = {**values, **item.values}
        if before is not None and merged == values:
            raise FormatError(f"{field}: revision changes nothing")
        holder = decode(b"---\n{}\n---\n", f"{field} (change)")
        check_resource_values(holder, merged, field)
        path = merged["location"]["path"]
        if path is not None:
            _check_source_path(path)
            _material(repository, path, merged["version"]["method"], merged["version"]["sha256"])
        after = render_description(item.resource, merged, revision, previous, receipt)
        validate_description(decode(after, f"{relative} (after image)"), item.resource)
        planned.append((relative, before, after))
    return [
        (
            Target(
                path,
                None if before is None else digest(before),
                digest(after),
                f"targets/{index}.md",
            ),
            before,
            after,
        )
        for index, (path, before, after) in enumerate(planned, 1)
    ]


def publish_sealed(
    repository: Repository,
    directory: str,
    files: dict[str, bytes],
    seal: str,
    prefix: str = ".proposal-prepare-",
) -> None:
    """Publish a complete write-once archive by renaming a staging directory in runs/."""
    runs = repository.path("runs")
    runs.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=prefix, dir=runs) as temporary:
        staging = Path(temporary)
        for name, data in files.items():
            (staging / name).parent.mkdir(parents=True, exist_ok=True)
            write_atomic(staging / name, data)
        write_atomic(staging / "seal", (seal + "\n").encode())
        sync_directory(staging)
        if os.path.lexists(repository.root / directory):
            raise FormatError(f"{directory}: already exists")
        os.rename(staging, repository.root / directory)
    sync_directory(runs)


def load(root: Path, value: str) -> Loaded:
    """Verify a packet's seal and every frozen digest (F02 for other artifacts)."""
    repository = Repository(root)
    relative = _relative(repository, value)
    if CREATION_DIR.fullmatch(relative.removesuffix("/packet.md")):
        raise FormatError(f"{relative}: this is a child creation packet; use project create")
    if HANDOFF_DIR.fullmatch(relative.removesuffix("/draft.md")):
        raise FormatError(f"{relative}: this is a handoff draft; use aoe handoff --apply")
    if relative.startswith("runs/drafts/"):
        raise FormatError(
            f"{relative}: this is an input, not a reviewed packet; run workspace propose --input"
        )
    directory = packet_directory(relative)
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
    parsed = validate_packet(document)
    frozen: list[tuple[str, str | None]] = [("input.md", parsed.input_sha256)]
    frozen += [(item.snapshot, item.sha256) for item in parsed.sources if item.snapshot]
    frozen += [(target.after, target.after_sha256) for target in parsed.targets]
    for name, expected in frozen:
        if digest(repository.path(f"{directory}/{name}", "file").read_bytes()) != expected:
            raise FormatError(f"{directory}/{name}: changed after preview; propose again")
    return Loaded(directory, sealed.decode().strip(), parsed, document.body)


def _successor(repository: Repository, directory: str) -> str | None:
    runs = repository.root / "runs"
    for path in sorted(runs.iterdir()) if runs.is_dir() else ():
        candidate = f"runs/{path.name}"
        if candidate == directory or not PACKET_DIR.fullmatch(candidate):
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


def _receipt(repository: Repository, loaded: Loaded) -> Receipt | None:
    return receipt_for(repository, loaded.directory, loaded.seal)


def receipt_for(
    repository: Repository, directory: str, seal: str, record: str = "packet.md"
) -> Receipt | None:
    """The valid receipt of a sealed record directory, None when absent."""
    relative = f"{directory}/receipt.md"
    if not os.path.lexists(repository.root / relative):
        return None
    path = repository.path(relative, "file")
    receipt = validate_receipt(decode(path.read_bytes(), str(path)))
    if receipt.record != f"{directory}/{record}" or receipt.record_sha256 != seal:
        raise FormatError(f"{relative}: receipt does not belong to this sealed packet")
    return receipt


def source_problems(repository: Repository, sources: tuple[PacketSource, ...]) -> list[str]:
    """Selected local sources that no longer match their frozen digests."""
    problems = []
    for source in sources:
        if source.path is None or source.sha256 is None:
            continue
        path = repository.path(source.path)
        current = digest(path.read_bytes()) if path.is_file() else None
        if current != source.sha256:
            problems.append(
                f"{source.path}: selected source changed since propose (expected "
                f"{source.sha256}, found {current or 'absent'})"
            )
    return problems


def pin_problems(repository: Repository, pins: tuple[dict[str, Any], ...]) -> list[str]:
    """Pinned resources whose description or material no longer matches (F13)."""
    problems = []
    for pin in pins:
        try:
            data, _ = _description(repository, pin["resource"])
            if digest(data) != pin["description_sha256"]:
                raise FormatError(
                    f"{resource_path(pin['resource'])}: description revised since pinned "
                    f"(revision {pin['revision']} pinned)"
                )
            if pin["path"] is not None:
                _material(repository, pin["path"], pin["method"], pin["sha256"])
        except (OSError, ValueError) as error:
            problems.append(f"broken pin {pin['resource']} revision {pin['revision']}: {error}")
    return problems


def check(root: Path, loaded: Loaded) -> list[str]:
    """Reasons apply would be refused now: relevant targets, sources and pins only."""
    repository = Repository(root)
    problems = []
    for target in loaded.packet.targets:
        path = repository.path(target.path)
        current = digest(path.read_bytes()) if path.is_file() else None
        if os.path.lexists(path) and current is None:
            problems.append(f"{target.path}: expected a regular file")
        elif current != target.before_sha256 and target.before_sha256 is None:
            problems.append(f"{target.path}: occupied since propose (found {current})")
        elif current != target.before_sha256:
            problems.append(
                f"{target.path}: changed since propose (expected {target.before_sha256}, "
                f"found {current or 'absent'})"
            )
    problems += source_problems(repository, loaded.packet.sources)
    problems += pin_problems(repository, loaded.packet.pins)
    for target in loaded.packet.targets:
        if target.path == CHARTER_FILE:
            continue
        after = repository.path(f"{loaded.directory}/{target.after}", "file").read_bytes()
        name = target.path.removeprefix("shared/resources/").removesuffix(".md")
        description = validate_description(decode(after), name)
        if description.path is not None:
            try:
                _material(repository, description.path, description.method, description.sha256)
            except (OSError, ValueError) as error:
                problems.append(f"resource {name}: {error}")
    return problems


def apply(
    root: Path,
    value: str,
    actor: str | None,
    *,
    confirmed: bool,
    approval_text: str | None = None,
    now: datetime | None = None,
) -> Outcome:
    """Preview (not confirmed) or publish one reviewed packet; replays are idempotent.

    Preview takes no lock and writes nothing; confirmation runs every check again
    under the root lock, in contract order (section 7.4).
    """
    repository = _repository(root)
    if not confirmed:
        return _apply(repository, value, None, False, approval_text, now)
    if actor is None or not actor.strip():
        raise FormatError("apply: a confirming actor is required (--confirmed-by)")
    with handoff_mutex(repository.root):
        return _apply(repository, value, actor, True, approval_text, now)


def _apply(
    repository: Repository,
    value: str,
    actor: str | None,
    confirmed: bool,
    approval_text: str | None,
    now: datetime | None,
) -> Outcome:
    intent = read_intent(repository) if pending(repository) else None
    loaded = load(repository.root, value)
    record = f"{loaded.directory}/packet.md"
    if intent is not None and intent.record != record:
        raise FormatError(
            f"incomplete {intent.operation} for {intent.record}; rerun that operation's "
            "command first"
        )
    receipt = _receipt(repository, loaded)
    if receipt is not None and intent is None:
        if receipt.disposition == "rejected":
            raise FormatError(
                f"{loaded.directory}: rejected by {receipt.actor} ({receipt.reason}); "
                "propose anew without supersedes"
            )
        return Outcome("replayed", loaded, receipt)
    if intent is not None:
        if intent.record_sha256 != loaded.seal:
            raise FormatError(f"{JOURNAL}: journal does not match this packet's seal; journal kept")
        if not confirmed:
            return Outcome(
                "incomplete",
                loaded,
                problems=("publication interrupted; rerun this apply with --confirm to finish",),
            )
        notes = []
        if actor != intent.actor:
            notes.append(
                f"--confirmed-by {actor} ignored; recovery keeps the first confirmation "
                f"by {intent.actor} at {intent.at}"
            )
        finish(repository)
        return Outcome("recovered", loaded, _receipt(repository, loaded), tuple(notes))
    problems = check(repository.root, loaded)
    successor = _successor(repository, loaded.directory)
    if successor is not None:
        problems.insert(0, f"superseded by {successor}; review that packet instead")
    if not confirmed:
        return Outcome("preview", loaded, problems=tuple(problems))
    assert actor is not None
    if problems:
        raise FormatError("; ".join(problems) + ". Nothing written; preview a refreshed proposal")
    remove_completed(repository)
    images = []
    for target in loaded.packet.targets:
        path = repository.path(target.path)
        before = path.read_bytes() if target.before_sha256 is not None else None
        after = repository.path(f"{loaded.directory}/{target.after}", "file").read_bytes()
        images.append(Image(target.path, before, after))
    at = utc_text((now or datetime.now(UTC)).astimezone(UTC))
    results = [
        {"path": t.path, "before_sha256": t.before_sha256, "after_sha256": t.after_sha256}
        for t in loaded.packet.targets
    ]
    data = render_receipt(record, loaded.seal, "applied", actor, at, approval_text, None, results)
    images.append(Image(f"{loaded.directory}/receipt.md", None, data))
    intent = Intent(
        "workspace-change", record, loaded.seal, actor, at, approval_text, tuple(images)
    )
    prepare(repository, intent)
    finish(repository)
    return Outcome("applied", loaded, _receipt(repository, loaded))


def reject(root: Path, value: str, reason: str, actor: str, now: datetime | None = None) -> Outcome:
    """Record a final rejection for a pending packet; nothing else changes."""
    if not reason.strip():
        raise FormatError("reject: a reason is required (--reason)")
    if not actor.strip():
        raise FormatError("reject: a confirming actor is required (--confirmed-by)")
    repository = _repository(root)
    with handoff_mutex(repository.root):
        loaded = load(repository.root, value)
        record = f"{loaded.directory}/packet.md"
        receipt = _receipt(repository, loaded)
        if pending(repository) and read_intent(repository).record == record:
            raise FormatError(f"{loaded.directory}: publication incomplete; finish it with apply")
        if receipt is not None:
            if receipt.disposition == "rejected":
                return Outcome("replayed", loaded, receipt)
            raise FormatError(
                f"{loaded.directory}: already applied ({loaded.directory}/receipt.md); "
                "propose a new change instead"
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
    return Outcome("rejected", loaded, _receipt(repository, loaded))


def applied_receipt(root: Path, value: str) -> Receipt:
    """An applied, valid receipt of a sealed workspace change packet, or a FormatError."""
    if not value.endswith("/receipt.md"):
        raise FormatError(f"{value}: expected a packet receipt path")
    repository = Repository(root)
    loaded = load(repository.root, value.removesuffix("/receipt.md"))
    receipt = _receipt(repository, loaded)
    if receipt is None or receipt.disposition != "applied":
        state = "absent" if receipt is None else receipt.disposition
        raise FormatError(f"{value}: expected an applied receipt; found {state}")
    return receipt
