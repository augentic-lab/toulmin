"""Read-only workspace scope state for native sessions (contract section 11).

The card describes stored workspace records and available choices. It never
reconstructs conversation history, treats a draft as confirmed, or reads child
discussion, sibling histories or creation sources into resident context.
"""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from toulmin.core.repository import Repository
from toulmin.protocols.research_workspace import _file_digest
from toulmin.protocols.workspace_state import CREATION_INCOMPLETE, RootState, workspace_status

RESIDENT = ("AGENTS.md", "WORKSPACE.md")


@dataclass(frozen=True)
class WorkspaceState:
    name: str
    sections: tuple[tuple[str, str], ...]
    recorded_next_step: str | None
    last_handoff: str | None  # sessions/<file>
    children: tuple[tuple[str, str], ...]  # (name, stage or "invalid")
    pending: tuple[str, ...]  # packets and handoff drafts needing a researcher decision
    resources: tuple[str, ...]
    notices: tuple[str, ...]
    errors: tuple[str, ...]
    fingerprint: str
    context_files: tuple[str, ...]


def workspace_research(root: Path) -> WorkspaceState:
    """Current workspace state, resident inputs and freshness fingerprint, from files."""
    report = workspace_status(root, {})
    errors = list(report.errors)
    notices = list(report.notices)
    if report.root.state != RootState.WORKSPACE:
        errors.append(
            f"{report.root.root}: workspace state not configured ({report.root.state.value}); "
            "workspace sessions need a workspace root"
        )
    repository = Repository(report.root.root)
    digests: dict[str, str] = {}
    context: list[str] = []

    def remember(relative: str, resident: bool = False) -> None:
        try:
            digests[relative] = _file_digest(repository, relative)
            if resident:
                context.append(relative)
        except (OSError, ValueError) as error:
            errors.append(str(error))
            digests[relative] = "ERROR"

    if report.root.state == RootState.WORKSPACE:
        for relative in RESIDENT:
            remember(relative, resident=True)
    latest = report.history[0] if report.history else None
    if latest is not None:
        remember(f"sessions/{latest.filename}", resident=True)
        if os.path.lexists(repository.root / latest.record.source_draft):
            remember(latest.record.source_draft)
        else:
            notices.append(f"{latest.record.source_draft}: applied handoff draft archive missing")
    for resource in report.resources:
        remember(f"shared/resources/{resource.name}.md")
    journal = repository.root / ".workspace-pending"
    values: list[str] = []
    if os.path.lexists(journal):
        values.append("journal")
        if os.path.lexists(journal / "intent.md"):
            remember(".workspace-pending/intent.md")
    for proposal in report.proposals:
        seal = repository.root / proposal.path / "seal"
        values.extend((proposal.path, proposal.disposition))
        if seal.is_file() and not seal.is_symlink():
            remember(f"{proposal.path}/seal")
    for item in report.handoffs:
        values.extend((item.path, item.disposition))
    children = tuple(
        (
            child.name,
            child.stage
            or (CREATION_INCOMPLETE if child.error == CREATION_INCOMPLETE else "invalid data"),
        )
        for child in report.children
    )
    for name, stage in children:
        values.extend(("child", name, stage))
    charter = report.charter
    pending = tuple(
        [
            f"{proposal.path} | {proposal.kind} | {proposal.disposition}"
            for proposal in report.proposals
            if proposal.disposition in {"pending", "incomplete", "invalid"}
        ]
        + [
            f"{item.path} | handoff | {item.disposition}"
            for item in report.handoffs
            if item.disposition != "applied"
        ]
    )
    resources = tuple(
        f"{item.name} | invalid data" if item.error else f"{item.name} | {item.status} | revision "
        f"{item.revision} | {item.title}"
        for item in report.resources
    )  # fmt: skip
    errors_tuple = tuple(sorted(set(errors)))
    fingerprint = hashlib.sha256()
    # Length-prefixed values, as for project state; diagnostics participate so an
    # incomplete scan never matches a clean one.
    for value in [*values, *errors_tuple] + [
        part for relative, checksum in sorted(digests.items()) for part in (relative, checksum)
    ]:
        encoded = value.encode("utf-8")
        fingerprint.update(len(encoded).to_bytes(8, "big"))
        fingerprint.update(encoded)
    return WorkspaceState(
        charter.name if charter else "unknown",
        charter.sections if charter else (),
        charter.next_step if charter else None,
        f"sessions/{latest.filename}" if latest else None,
        children,
        pending,
        resources,
        tuple(notices),
        errors_tuple,
        fingerprint.hexdigest(),
        tuple(context),
    )


def render_workspace(state: WorkspaceState) -> str:
    """Deterministic English workspace card: stored records and choices, not history."""
    sections = dict(state.sections)
    lines = [
        "WORKSPACE",
        f"{state.name} | scope: Workspace | data: {'INVALID' if state.errors else 'valid'}",
        "",
        "DIRECTION",
        " ".join(sections["Direction"].split()) if "Direction" in sections else
        "No confirmed direction yet.",
    ]  # fmt: skip
    for heading in ("Constraints", "Focus"):
        if heading in sections:
            lines.extend(("", heading.upper(), " ".join(sections[heading].split())))
    lines.extend(
        (
            "",
            "RECORDED NEXT STEP",
            state.recorded_next_step or "None recorded.",
            "Historical suggestion from the latest applied workspace handoff; completion has "
            "not been inferred.",
            "",
            "PROJECTS",
            *(f"{name} | stage: {stage}" for name, stage in state.children),
        )
    )
    if not state.children:
        lines.append("No projects yet.")
    lines.extend(("", "AWAITING RESEARCHER DECISION"))
    lines.extend(state.pending or ("Nothing pending.",))
    lines.extend(("", "RESOURCES", *(state.resources or ("None registered.",))))
    lines.extend(("", "ACTIONS"))
    if state.errors:
        lines.append("Inspect and resolve the reported file errors, then refresh state.")
    else:
        lines.extend(
            (
                "Continue workspace discussion from the current files.",
                "Record exploration and researcher corrections as an activity record in runs/.",
                "Prepare a change input in runs/drafts/ to propose direction or resource "
                "changes for review.",
            )
        )
        if state.pending:
            lines.append("Show pending packets or drafts for the researcher to apply or reject.")
        lines.append(
            "Prepare a project creation input in runs/drafts/ and run `toulmin project propose "
            "NAME --input FILE` to propose a child project for review."
        )
        for name, _ in state.children:
            lines.append(f"Open project {name} in its own session (not this one).")
        lines.append("Prepare a workspace handoff draft for researcher confirmation.")
    if state.notices:
        lines.extend(("", "NOTICES", *state.notices))
    if state.errors:
        lines.extend(("", "ERRORS", *state.errors))
    return "\n".join(lines) + "\n"
