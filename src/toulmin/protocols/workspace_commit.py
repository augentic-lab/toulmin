"""S4: deterministic commit descriptions from supplied paths and records, without git.

Reason: the researcher should see which research records a commit preserves. This
description is advice, never a ruling or an inferred research conclusion.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

from toulmin.core.documents import DIRECTORIES, Document
from toulmin.core.identifiers import ObjectId


@dataclass(frozen=True)
class ChangedPath:
    path: str
    created: bool = False


@dataclass(frozen=True)
class CommitSummary:
    groups: tuple[tuple[str, tuple[str, ...]], ...]
    message: str


def summarize(
    changes: tuple[ChangedPath, ...],
    records: Mapping[str, Document],
    subject: str | None = None,
) -> CommitSummary:
    """Use filenames for IDs and supplied outcome/session records, never worker prose."""
    groups: dict[str, list[str]] = {}
    objects: dict[str, dict[str, list[str]]] = {}
    outcomes: dict[str, list[str]] = {}
    sessions: dict[str, list[str]] = {}
    highlights: dict[str, list[str]] = {}
    archives: set[str] = set()
    for change in sorted(changes, key=lambda item: item.path):
        path = PurePosixPath(change.path)
        parts = path.parts
        project = parts[1] if len(parts) > 2 and parts[0] == "projects" else "workspace"
        local = parts[2:] if project != "workspace" else parts
        object_id = None
        if len(local) == 2 and path.suffix == ".md":
            try:
                candidate = ObjectId.parse(path.stem)
            except ValueError:
                pass
            else:
                if DIRECTORIES[candidate.kind] == local[0] and project != "workspace":
                    object_id = str(candidate)
        record = records.get(change.path)
        if object_id is not None:
            action = "created" if change.created else "changed"
            group = f"Objects {action} — {project}"
            objects.setdefault(project, {}).setdefault(action, []).append(object_id)
            highlights.setdefault(project, []).append(object_id)
        elif (
            local[:2] == ("runs", "proposals")
            and path.name.endswith(".outcome.md")
            or local
            and local[0] == "proposals"
        ):
            group = "Proposal outcomes"
            if record and record.header.get("disposition") == "applied":
                outcomes.setdefault(project, []).append(change.path)
        elif local and local[0] in {"sessions", "handoffs"}:
            group = "Sessions / handoffs"
            if not PurePosixPath(change.path).name.startswith("."):  # e.g. .gitkeep
                sessions.setdefault(project, []).append(change.path)
        elif local and local[0] == "runs" and len(local) > 1:
            if local[1] in {"proposals", "drafts"}:
                group = "Proposal outcomes" if local[1] == "proposals" else "Other workspace files"
                if record and record.header.get("disposition") == "applied":
                    outcomes.setdefault(project, []).append(change.path)
            else:
                archives.add("/".join(parts[: len(parts) - len(local) + 2]))
                group = "Run archives"
        else:
            group = "Other workspace files"
        groups.setdefault(group, []).append(change.path)
    if archives:
        groups[f"Run archives ({len(archives)})"] = groups.pop("Run archives")
    if subject is None:
        pieces = [f"{project} {', '.join(ids)}" for project, ids in sorted(highlights.items())]
        if not pieces:
            pieces = [
                f"{project}: {len(paths)} session/handoff(s)"
                for project, paths in sorted(sessions.items())
            ]
        subject = "toulmin: " + (
            "; ".join(pieces) if pieces else f"workspace: {len(changes)} files"
        )
        if len(subject) > 100:
            subject = subject[:97].rsplit(" ", 1)[0] + "…"
    body = []
    for project in sorted(objects.keys() | outcomes.keys() | sessions.keys()):
        body.append(project + ":")
        for action, ids in sorted(objects.get(project, {}).items()):
            body.append(f"  Objects {action}: {', '.join(ids)}")
        for name in outcomes.get(project, []):
            body.append("  Applied outcome: " + name)
        for name in sessions.get(project, []):
            body.append("  Session/handoff: " + name)
    ordered = sorted(
        groups.items(),
        key=lambda item: (
            0
            if item[0].startswith("Objects created")
            else 1
            if item[0].startswith("Objects changed")
            else 2
            if item[0] == "Proposal outcomes"
            else 3
            if item[0].startswith("Run archives")
            else 4
            if item[0] == "Sessions / handoffs"
            else 5,
            item[0],
        ),
    )
    return CommitSummary(
        tuple((name, tuple(paths)) for name, paths in ordered),
        subject + ("\n\n" + "\n".join(body) if body else "") + "\n",
    )
