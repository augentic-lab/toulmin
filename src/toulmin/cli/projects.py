"""File-only project discovery and the scope picker for ``toulmin open`` (PE1)."""

from dataclasses import dataclass
from pathlib import Path

import typer

from toulmin.cli.initialize import workspace_setup
from toulmin.cli.terminal import sayer
from toulmin.core.documents import sections
from toulmin.core.project import validate_project
from toulmin.core.repository import Repository
from toulmin.protocols.engineering_tasks import task_inventory
from toulmin.protocols.project_proposals import inventory
from toulmin.protocols.workspace_state import RootState, workspace_status


@dataclass(frozen=True)
class Project:
    name: str
    stage: str | None
    goal: str | None
    pending: int | None
    error: str | None = None


@dataclass(frozen=True)
class Projects:
    root: Path
    state: RootState
    items: tuple[Project, ...]
    problems: tuple[str, ...]
    notices: tuple[str, ...]


def collect(root: Path) -> Projects:
    """Derive choices from charters and local proposal outcomes, without native clients.

    Pending counts cover research and engineering proposals, not handoff drafts or Chief
    result availability. Errors make counts unknown rather than silently reporting zero.
    """
    report = workspace_status(root, workspace_setup())
    if report.root.state not in {RootState.WORKSPACE, RootState.LEGACY}:
        raise ValueError(f"{report.root.root}: not a Toulmin workbench; nothing was initialized")
    repository = Repository(report.root.root)
    problems = list(report.errors)
    items = []
    for child in report.children:
        if child.error:
            items.append(Project(child.name, None, None, None, child.error))
            problems.append(f"projects/{child.name}: {child.error}")
            continue
        try:
            charter = repository.read(f"projects/{child.name}/PROJECT.md")
            validate_project(charter, child.name)
            goal = " ".join(sections(charter)["Goal"].split())
        except (OSError, ValueError) as error:
            problems.append(str(error))
            items.append(Project(child.name, None, None, None, str(error)))
            continue
        pending: int | None = None
        try:
            proposals = inventory(repository.root, child.name)
            tasks, task_errors = task_inventory(repository.root, child.name)
            errors = (*proposals.errors, *task_errors)
            problems.extend(errors)
            problems.extend(
                f"{path}: unrecognized proposal filename" for path in proposals.unrecognized
            )
            if not errors and not proposals.unrecognized:
                pending = len(proposals.items) + len(tasks)
        except (OSError, ValueError) as error:
            problems.append(str(error))
        items.append(Project(child.name, charter.header["stage"], goal, pending))
    return Projects(
        repository.root,
        report.root.state,
        tuple(items),
        tuple(dict.fromkeys(problems)),
        report.notices,
    )


def show(found: Projects, *, picker: bool = False) -> None:
    """Keep full goals in piped output; wrap at terminal width for a person."""
    say = sayer()
    say(f"Workspace: {found.root}")
    if found.state == RootState.LEGACY:
        say("Legacy workbench: workspace session unavailable; select a project or adopt it first.")
    if picker and found.state == RootState.WORKSPACE:
        say("  0  Workspace conversation")
    for index, item in enumerate(found.items, 1):
        prefix = f"{index:>3}  " if picker else "  "
        if item.error:
            say(f"{prefix}{item.name} | unavailable: {item.error}")
            continue
        pending = str(item.pending) if item.pending is not None else "unknown (see diagnostics)"
        say(f"{prefix}{item.name} | stage: {item.stage} | pending proposals: {pending}")
        say(f"     Goal: {item.goal}")
    if not found.items:
        say(
            "No projects yet. Continue in the workspace; "
            "create a project only when a direction is clear."
        )
    say(
        "Pending proposals: local research and engineering proposals; "
        "excludes handoffs and live Chief results."
    )
    for message in found.notices:
        say(f"Notice: {message}")
    for problem in found.problems:
        say(f"Diagnostic: {problem}")


def choose(found: Projects) -> str | None:
    """Only the explicit answer selects a scope, including with exactly one child."""
    show(found, picker=True)
    keys = (
        "0 = workspace / project number / q = quit"
        if found.state == RootState.WORKSPACE
        else "project number / q = quit"
    )
    while True:
        answer = (
            str(typer.prompt(f"Open which conversation? [{keys}]", default="q")).strip().lower()
        )
        if answer == "q":
            typer.echo("Nothing opened.")
            raise typer.Exit(1)
        if answer == "0" and found.state == RootState.WORKSPACE:
            return None
        if answer.isascii() and answer.isdecimal() and 1 <= int(answer) <= len(found.items):
            item = found.items[int(answer) - 1]
            # Re-read the charter after selection: it may have changed while the menu
            # was waiting. A stale or incomplete directory must not start a session.
            current = collect(found.root)
            selected = next((row for row in current.items if row.name == item.name), None)
            if selected is not None and selected.error is None:
                return selected.name
            typer.echo(
                f"{item.name} is unavailable; inspect `toulmin projects` diagnostics and retry."
            )
            continue
        typer.echo(f"Choose one of: {keys}")
