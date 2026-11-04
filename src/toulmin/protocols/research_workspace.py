"""Read-only research state and resident context, independent of any session tool.

The card describes stored records. It neither reconstructs conversation history nor
infers that a historical next-step suggestion has been completed.
"""

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from toulmin.core.documents import DIRECTORIES, sections
from toulmin.core.identifiers import validate_project_name
from toulmin.core.inspection import inspect_project
from toulmin.core.repository import Repository
from toulmin.protocols.session import entry_files


@dataclass(frozen=True)
class ResearchState:
    project: str
    stage: str
    goal: str
    recorded_next_step: str
    last_handoff: str | None
    objects: tuple[tuple[str, str], ...]
    draft_files: tuple[str, ...]
    pending_review: tuple[str, ...]
    notices: tuple[str, ...]
    errors: tuple[str, ...]
    fingerprint: str
    context_files: tuple[str, ...]


def _file_digest(repository: Repository, relative: str) -> str:
    """Hash regular files without opening a symlink or blocking on a FIFO."""
    path = repository.path(relative, "file")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"{relative}: expected regular file")
        checksum = hashlib.sha256()
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            while data := stream.read(65536):
                checksum.update(data)
        return checksum.hexdigest()
    finally:
        os.close(descriptor)


def research_state(root: Path, project: str) -> ResearchState:
    """Load current file-derived state without creating caches, locks or records.

    Draft files inventory runs/drafts and explicit archive-side draft.md files,
    not native/TUI proposals or proof of pending intake. Review pending labels come
    only from validated inspection records. Raw archives, discussion history and
    integration caches are excluded from context and fingerprint scans.
    """
    errors: list[str] = []
    notices: list[str] = []
    digests: dict[str, str] = {}
    context: list[str] = []
    drafts: list[str] = []
    stage, goal, next_step = "unknown", "Unavailable", "Unavailable"
    last_handoff = None
    objects: tuple[tuple[str, str], ...] = ()
    pending: tuple[str, ...] = ()

    def remember(repository: Repository, relative: str) -> bool:
        try:
            digests[relative] = _file_digest(repository, relative)
            return True
        except (OSError, ValueError) as error:
            errors.append(str(error))
            digests[relative] = "ERROR"
            return False

    try:
        validate_project_name(project)
        repository = Repository(root)
        snapshot = inspect_project(repository, project)
        errors.extend(snapshot.errors)
        objects = tuple(
            (str(document.object_id), document.header["status"])
            for document in sorted(
                snapshot.objects, key=lambda doc: (doc.object_id.kind.value, doc.object_id.number)
            )
        )
        pending = tuple(f"{run}: {', '.join(labels)}" for run, labels in snapshot.pending_drafts)
        charter = snapshot.charter
        if charter is not None:
            stage = charter.header["stage"]
            goal = " ".join(sections(charter)["Goal"].split())
            next_step = charter.header["next_step"]
            handoff = charter.header["last_handoff"]
            if handoff is not None:
                last_handoff = f"projects/{project}/sessions/{handoff}"
            for relative in (
                *(str(path) for path in entry_files(project, handoff)),
                f"projects/{project}/brief.md",
            ):
                if remember(repository, relative):
                    context.append(relative)
            if last_handoff is None:
                notices.append("No applied handoff is recorded.")
            else:
                record = repository.read(last_handoff)
                # The applied source is required to validate the current handoff,
                # but is not additional resident context.
                remember(repository, record.header["source_draft"])
        else:
            # Include malformed charter bytes in freshness; never present them as
            # valid context merely because the file exists.
            remember(repository, f"projects/{project}/PROJECT.md")

        base = f"projects/{project}"
        for directory in DIRECTORIES.values():
            try:
                folder = repository.path(f"{base}/{directory}", "directory")
                for path in sorted(folder.iterdir()):
                    relative = path.relative_to(repository.root).as_posix()
                    try:
                        repository.path(relative)  # reject links before testing the type
                        if path.name == ".gitkeep":
                            continue
                        if directory == "runs" and path.is_dir():
                            continue
                        remember(repository, relative)
                    except (OSError, ValueError) as error:
                        errors.append(str(error))
                        digests[relative] = "ERROR"
            except (OSError, ValueError) as error:
                errors.append(str(error))

        _draft_inventory(repository, f"{base}/runs", drafts, digests, errors)
    except (OSError, ValueError) as error:
        errors.append(str(error))

    errors_tuple = tuple(sorted(set(errors)))
    fingerprint = hashlib.sha256()
    # Length-prefixed values prevent ambiguous path/content boundaries. Diagnostics
    # participate so an incomplete scan never has the same fingerprint as clean data.
    values = [project, stage, goal, next_step, *pending, *errors_tuple]
    for relative, checksum in sorted(digests.items()):
        values.extend((relative, checksum))
    for value in values:
        encoded = value.encode("utf-8")
        fingerprint.update(len(encoded).to_bytes(8, "big"))
        fingerprint.update(encoded)
    return ResearchState(
        project,
        stage,
        goal,
        next_step,
        last_handoff,
        objects,
        tuple(sorted(set(drafts))),
        pending,
        tuple(notices),
        errors_tuple,
        fingerprint.hexdigest(),
        tuple(context),
    )


def _draft_inventory(
    repository: Repository,
    runs: str,
    drafts: list[str],
    digests: dict[str, str],
    errors: list[str],
) -> None:
    """Inspect explicit draft storage and archive-side intake/draft files only."""

    def visit(relative: str, recursive: bool = False) -> None:
        try:
            path = repository.path(relative)
            if path.is_dir():
                if recursive:
                    for entry in sorted(path.iterdir()):
                        visit(entry.relative_to(repository.root).as_posix(), True)
                    return
                raise ValueError(f"{relative}: expected regular file")
            digests[relative] = _file_digest(repository, relative)
            if path.name != "intake.md" and path.name != ".gitkeep":
                drafts.append(relative)
        except (OSError, ValueError) as error:
            errors.append(str(error))
            digests[relative] = "ERROR"

    folder = repository.path(runs, "directory")
    for archive in sorted(folder.iterdir()):
        relative = archive.relative_to(repository.root).as_posix()
        try:
            repository.path(relative)
            if archive.name == "drafts":
                if not archive.is_dir():
                    raise ValueError(f"{relative}: expected draft directory")
                visit(relative, True)
            elif archive.is_dir() and archive.name not in {"conversations", "native"}:
                # Never descend into research workspaces, captured conversations,
                # frozen inputs or raw model outputs.
                for name in ("draft.md", "intake.md"):
                    candidate = archive / name
                    if candidate.exists() or candidate.is_symlink():
                        visit(f"{relative}/{name}")
        except (OSError, ValueError) as error:
            errors.append(str(error))
            digests[relative] = "ERROR"


def render_state(state: ResearchState) -> str:
    """Render deterministic English state and available choices, never activity history."""
    lines = [
        "PROJECT",
        f"{state.project} | stage: {state.stage} | data: {'INVALID' if state.errors else 'valid'}",
        "",
        "QUESTION",
        f"Goal: {state.goal}",
        "",
        "CONFIRMED",
        "Stored object statuses; these are records, not scientific validation.",
        *(f"{object_id}: {status}" for object_id, status in state.objects),
    ]
    if not state.objects:
        lines.append("No formal objects recorded.")
    lines.extend(
        ("", "DRAFTS", "Draft files are not formal objects; confirmation is not inferred.")
    )
    lines.extend(state.draft_files or ("No draft files found.",))
    lines.extend(f"Review intake pending: {item}" for item in state.pending_review)
    lines.extend(
        (
            "",
            "RECORDED NEXT STEP",
            state.recorded_next_step,
            "Historical suggestion from PROJECT.md; completion has not been inferred.",
            "",
            "ACTIONS",
        )
    )
    if state.errors:
        lines.append("Inspect and resolve the reported file errors, then refresh state.")
    else:
        lines.append("Continue research discussion from the current files.")
        if state.draft_files:
            lines.append("Inspect draft files; confirm any formal application separately.")
        if state.pending_review:
            lines.append("Inspect pending review drafts and choose intake outcomes.")
        opened = [object_id for object_id, status in state.objects if status == "open"]
        if opened:
            lines.append(
                f"Inspect open objections and choose responses/rulings: {', '.join(opened)}."
            )
        if any(
            object_id.startswith("C-") and status != "superseded"
            for object_id, status in state.objects
        ):
            lines.append("Request a fresh independent review of selected current Claims.")
        lines.append("Prepare a handoff draft for researcher confirmation.")
    if state.notices:
        lines.extend(("", "NOTICES", *state.notices))
    if state.errors:
        lines.extend(("", "ERRORS", *state.errors))
    return "\n".join(lines) + "\n"
