"""C5-F1: new material since review, without changing independent reviewer inputs.

The suggestion must reflect material a further round could reassess, rather than the
mere existence of unanswered Objections. All dates and counts come from workspace files.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from toulmin.core.documents import Document
from toulmin.core.identifiers import ObjectKind
from toulmin.core.inspection import inspect_project
from toulmin.core.repository import Repository
from toulmin.protocols.calibration import REVIEW, operation
from toulmin.protocols.review import OUTPUT_FILE
from toulmin.protocols.review_intake import output_state


@dataclass(frozen=True)
class ReviewProgress:
    latest: str | None
    at: datetime | None
    claims: tuple[str, ...]
    evidence: tuple[str, ...]
    runs: tuple[str, ...]  # completed reviews sharing the latest round's archive stamp

    @property
    def reviewed(self) -> bool:
        return self.latest is not None and not (self.claims or self.evidence)


def _created(document: Document) -> datetime:
    return datetime.fromisoformat(document.header["created"])


def review_progress(objects: tuple[Document, ...]) -> ReviewProgress:
    """Pure derivation: later-created current Claims and non-invalidated Evidence."""
    reviews = [
        doc
        for doc in objects
        if doc.object_id.kind == ObjectKind.RUN
        and operation(str(doc.header["role"])) == REVIEW
        and doc.header["status"] == "completed"
    ]
    latest = max(reviews, key=lambda doc: (_created(doc), doc.object_id.number), default=None)
    at = _created(latest) if latest else None
    claims = tuple(
        str(doc.object_id)
        for doc in objects
        if doc.object_id.kind == ObjectKind.CLAIM
        and doc.header["status"] != "superseded"
        and (at is None or _created(doc) > at)
    )
    evidence = tuple(
        str(doc.object_id)
        for doc in objects
        if doc.object_id.kind == ObjectKind.EVIDENCE
        and doc.header["status"] != "invalidated"
        and (at is None or _created(doc) > at)
    )
    runs: tuple[str, ...] = ()
    if latest:
        # plan_review gives every session of a round this common stamp. An older
        # manually archived Run without that convention is counted on its own.
        name = PurePosixPath(latest.header["output"]).name
        stamp = re.match(r"^([0-9]{8}T[0-9]{6}Z)-review(?:-|$)", name)
        runs = tuple(
            str(doc.object_id)
            for doc in reviews
            if doc is latest
            or stamp
            and PurePosixPath(doc.header["output"]).name.startswith(stamp[1] + "-review-")
        )
    return ReviewProgress(str(latest.object_id) if latest else None, at, claims, evidence, runs)


def review_advisory(root: Path, project: str) -> str | None:
    """Read-only preview advice; unavailable draft counts are never guessed."""
    repository = Repository(root)
    snapshot = inspect_project(repository, project)
    if snapshot.errors:
        return None  # status/preview report data errors; this advice never adds a refusal
    progress = review_progress(snapshot.objects)
    if not progress.reviewed:
        return None
    assert progress.at is not None
    text = (
        f"Since the last round ({progress.latest}, "
        f"{progress.at.astimezone(UTC):%Y-%m-%d %H:%M UTC}): no new Claim or Evidence."
    )
    runs = {
        str(doc.object_id): doc for doc in snapshot.objects if doc.object_id.kind == ObjectKind.RUN
    }
    drafts = duplicates = 0
    try:
        for run in progress.runs:
            state = output_state(root, project, f"{runs[run].header['output']}/{OUTPUT_FILE}")
            drafts += len(state.drafts)
            duplicates += sum(entry["outcome"] == "duplicate" for entry in state.recorded.values())
    except (OSError, ValueError):
        duplicates = 0  # omit the clause if a round output/count is unavailable
    if duplicates:
        text += (
            f" Last round: {duplicates} of {drafts} drafts were duplicates of existing Objections."
            " Another round will likely repeat them (C5); applying still starts it."
        )
        return text
    return text + " Another round will likely repeat its findings (C5); applying still starts it."
