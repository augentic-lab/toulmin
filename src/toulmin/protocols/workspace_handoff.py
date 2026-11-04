"""L2 workspace handoffs: summary -> sealed draft -> confirmed session record (contract 8).

Confirmation approves the summary as an accurate session record, nothing else: only
sessions/ and WORKSPACE.md next_step/last_handoff change. Entry planning reads only
the latest applied record; unapplied drafts and orphan records never substitute.
"""

import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from toulmin.core.atomic import digest, handoff_mutex
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError
from toulmin.core.proposals import PACKET_DIR
from toulmin.core.repository import Repository
from toulmin.core.workspace import CHARTER_FILE, RECEIPT, validate_charter
from toulmin.core.workspace_handoffs import (
    HandoffDraft,
    HandoffRecord,
    continuity_after,
    draft_directory,
    precise_text,
    render_draft,
    render_record,
    validate_handoff_draft,
    validate_handoff_input,
    validate_handoff_record,
)
from toulmin.core.workspace_journal import Image, Intent, finish, pending, prepare, read_intent
from toulmin.protocols.workspace_change import (
    applied_receipt,
    packet_directory_or_none,
    publish_sealed,
)

SEAL = re.compile(r"[0-9a-f]{64}\n")
PROJECT_DRAFT = re.compile(r"projects/[^/]+/runs/[^/]+/draft\.md")


@dataclass(frozen=True)
class LoadedDraft:
    path: str  # runs/<stamp>-handoff-<hex>/draft.md
    seal: str
    draft: HandoffDraft
    body: str


@dataclass(frozen=True)
class Applied:
    """One record in the applied chain, newest first."""

    filename: str
    record: HandoffRecord


@dataclass(frozen=True)
class HandoffOutcome:
    """status: drafted, preview, applied, recovered, replayed, incomplete."""

    status: str
    loaded: LoadedDraft
    record: str | None = None  # sessions/<file>
    problems: tuple[str, ...] = ()


def _repository(root: Path) -> Repository:
    repository = Repository(root)
    if not os.path.lexists(repository.root / CHARTER_FILE):
        raise FormatError(
            f"{repository.root}: workspace state not configured (no {CHARTER_FILE}); "
            "a workspace handoff needs a workspace root. Project handoffs: aoe handoff PROJECT"
        )
    return repository


def _charter(repository: Repository) -> bytes:
    path = repository.path(CHARTER_FILE, "file")
    data = path.read_bytes()
    validate_charter(decode(data, str(path)))
    return data


def chain(root: Path) -> list[Applied]:
    """The applied handoff history from WORKSPACE.last_handoff, newest first."""
    repository = Repository(root)
    charter = validate_charter(decode(repository.path(CHARTER_FILE, "file").read_bytes()))
    result: list[Applied] = []
    current = charter.last_handoff
    seen: set[str] = set()
    while current is not None:
        if current in seen:
            raise FormatError(f"sessions/{current}: previous_handoff: cycle in applied history")
        seen.add(current)
        path = repository.path(f"sessions/{current}", "file")
        record = validate_handoff_record(decode(path.read_bytes(), str(path)))
        if not current.endswith(f"-{record.source_sha256}.md"):
            raise FormatError(f"sessions/{current}: source_sha256: does not match the filename")
        result.append(Applied(current, record))
        current = record.previous_handoff
    return result


def latest_handoff(root: Path) -> Applied | None:
    """File-only entry planning: the latest applied record, never a draft or orphan."""
    history = chain(root)
    return history[0] if history else None


def draft(
    root: Path, input_path: str, now: datetime | None = None, token: str | None = None
) -> HandoffOutcome:
    """Seal a reviewable workspace handoff draft; nothing else is written."""
    repository = _repository(root)
    relative = repository.relative(str(input_path)).removesuffix("/")
    if relative.startswith("projects/"):
        raise FormatError(
            f"{relative}: input: a project summary belongs to that project; "
            "use aoe handoff PROJECT --input"
        )
    if PACKET_DIR.fullmatch(packet_directory_or_none(relative) or ""):
        raise FormatError(f"{relative}: this is a review packet; use workspace apply --draft")
    data = repository.path(relative, "file").read_bytes()
    supplied = validate_handoff_input(decode(data, str(repository.root / relative)))
    for receipt in supplied.confirmed_changes:
        applied_receipt(repository.root, receipt)
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    directory = f"runs/{moment.strftime('%Y%m%dT%H%M%SZ')}-handoff-{token or uuid.uuid4().hex}"
    with handoff_mutex(repository.root):
        if pending(repository):
            raise FormatError("an incomplete workspace publication exists; finish it first")
        base = _charter(repository)
        next_step = supplied.next_step or validate_charter(decode(base)).next_step
        if next_step is None:
            raise FormatError(
                f"{relative}: next_step: required; WORKSPACE.md has no recorded next step"
            )
        content = render_draft(
            precise_text(moment), relative, digest(data), supplied, digest(base), next_step
        )
        validate_handoff_draft(decode(content, f"{directory}/draft.md"))
        publish_sealed(
            repository, directory, {"draft.md": content}, digest(content), ".handoff-prepare-"
        )
    return HandoffOutcome("drafted", load_draft(repository.root, directory))


def load_draft(root: Path, value: str) -> LoadedDraft:
    """Verify a draft's location, seal, kind and scope (F02); wrong artifacts are named."""
    repository = Repository(root)
    relative = repository.relative(str(value)).removesuffix("/")
    if PROJECT_DRAFT.fullmatch(relative):
        raise FormatError(
            f"{relative}: this is a project handoff draft; use aoe handoff PROJECT --apply"
        )
    if PACKET_DIR.fullmatch(packet_directory_or_none(relative) or ""):
        raise FormatError(f"{relative}: this is a review packet; use workspace apply --draft")
    if relative.startswith("runs/drafts/") or relative.startswith("sessions/"):
        raise FormatError(
            f"{relative}: this is an input or an applied record, not a generated draft; "
            "run aoe handoff --workspace --input"
        )
    directory = draft_directory(relative)
    content = repository.path(f"{directory}/draft.md", "file").read_bytes()
    sealed = repository.path(f"{directory}/seal", "file").read_bytes()
    if not SEAL.fullmatch(sealed.decode("utf-8", "replace")) or sealed.decode().strip() != digest(
        content
    ):
        raise FormatError(f"{directory}: draft changed after preview (seal mismatch); draft again")
    document = decode(content, str(repository.root / directory / "draft.md"))
    return LoadedDraft(
        f"{directory}/draft.md",
        sealed.decode().strip(),
        validate_handoff_draft(document),
        document.body,
    )


def check(root: Path, loaded: LoadedDraft) -> list[str]:
    """Why apply would be refused now: the base charter and the cited receipts only."""
    repository = Repository(root)
    problems = []
    current = digest(repository.path(CHARTER_FILE, "file").read_bytes())
    if current != loaded.draft.base_workspace_sha256:
        problems.append(
            f"{CHARTER_FILE}: changed since drafting (expected "
            f"{loaded.draft.base_workspace_sha256}, found {current}); stale draft, draft again"
        )
    for receipt in loaded.draft.confirmed_changes:
        try:
            applied_receipt(repository.root, receipt)
        except (OSError, ValueError) as error:
            problems.append(f"confirmed_changes: {error}")
    return problems


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def uncited_receipts(root: Path, cited: tuple[str, ...]) -> list[str]:
    """Workspace changes applied since the latest applied handoff that a summary omits.

    A summary written without them may still call those changes pending (WI8 W8). This is a
    warning for the reviewer, never a refusal: the summary remains the session's record.
    Unreadable receipts are skipped here; workspace status reports them.
    """
    repository = Repository(root)
    latest = latest_handoff(repository.root)
    since = _moment(latest.record.applied_at) if latest is not None else None
    found = []
    for directory in sorted(repository.root.glob("runs/*-proposal-*")):
        relative = f"runs/{directory.name}/receipt.md"
        if not RECEIPT.fullmatch(relative) or relative in cited:
            continue
        try:
            receipt = applied_receipt(repository.root, relative)
        except (OSError, ValueError):
            continue  # absent, rejected or unreadable: nothing applied to cite
        if since is None or _moment(receipt.at) > since:
            found.append(relative)
    return found


def apply(
    root: Path,
    value: str,
    actor: str | None,
    *,
    confirmed: bool,
    now: datetime | None = None,
) -> HandoffOutcome:
    """Preview (not confirmed) or apply one sealed draft; repeats return the record."""
    repository = _repository(root)
    if not confirmed:
        return _apply(repository, value, None, False, now)
    if actor is None or not actor.strip():
        raise FormatError("apply: a confirming actor is required (--confirmed-by)")
    with handoff_mutex(repository.root):
        return _apply(repository, value, actor, True, now)


def _apply(
    repository: Repository,
    value: str,
    actor: str | None,
    confirmed: bool,
    now: datetime | None,
) -> HandoffOutcome:
    intent = read_intent(repository) if pending(repository) else None
    loaded = load_draft(repository.root, value)
    if intent is not None and intent.record != loaded.path:
        raise FormatError(
            f"incomplete {intent.operation} for {intent.record}; rerun that operation's "
            "command first"
        )
    if intent is not None:
        if intent.record_sha256 != loaded.seal:
            raise FormatError(".workspace-pending: journal does not match this draft; journal kept")
        record = next(image.path for image in intent.images if image.path.startswith("sessions/"))
        if not confirmed:
            return HandoffOutcome(
                "incomplete",
                loaded,
                record,
                ("publication interrupted; rerun this apply with --confirm to finish",),
            )
        notes = []
        if actor != intent.actor:
            notes.append(
                f"--confirmed-by {actor} ignored; recovery keeps the first confirmation "
                f"by {intent.actor} at {intent.at}"
            )
        finish(repository)
        return HandoffOutcome("recovered", loaded, record, tuple(notes))
    for applied in chain(repository.root):
        if applied.record.source_sha256 == loaded.seal:
            return HandoffOutcome("replayed", loaded, f"sessions/{applied.filename}")
    problems = check(repository.root, loaded)
    if not confirmed:
        return HandoffOutcome("preview", loaded, problems=tuple(problems))
    assert actor is not None
    if problems:
        raise FormatError("; ".join(problems) + ". Nothing written")
    before = _charter(repository)
    previous = validate_charter(decode(before)).last_handoff
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    filename = f"{moment.strftime('%Y%m%dT%H%M%SZ')}-{loaded.seal}.md"
    session = f"sessions/{filename}"
    if os.path.lexists(repository.path(session)):
        raise FormatError(f"{session}: orphan record for this draft exists; preserved, inspect it")
    after = continuity_after(before, loaded.draft.next_step, filename)
    content = repository.path(loaded.path, "file").read_bytes()
    data = render_record(
        content,
        loaded.path,
        actor,
        precise_text(moment),
        digest(after),
        previous,
        loaded.seal,
    )
    validate_handoff_record(decode(data, session))
    repository.path("sessions", "directory")
    images = (Image(session, None, data), Image(CHARTER_FILE, before, after))
    prepare(
        repository,
        Intent(
            "workspace-handoff", loaded.path, loaded.seal, actor, precise_text(moment), None, images
        ),
    )
    finish(repository)
    return HandoffOutcome("applied", loaded, session)
