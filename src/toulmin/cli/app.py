"""Installed CLI entry point."""

import os
from pathlib import Path
from typing import Annotated

import typer

from toulmin.cli.initialize import initialize
from toulmin.core.identifiers import ObjectKind, validate_project_name
from toulmin.protocols.drafting import write_draft
from toulmin.protocols.handoff import apply_handoff, draft_handoff
from toulmin.protocols.intake import create_object
from toulmin.protocols.status import project_status

app = typer.Typer(
    help="Toulmin research workbench. Initialize, create objects and inspect project state.",
    add_completion=False,
    no_args_is_help=True,
)

ACTOR_VARIABLE = "TOULMIN_ACTOR"


def confirmer(value: str | None) -> str | None:
    """Explicit --confirmed-by wins; otherwise the operator's local default, if any."""
    if value is not None:
        return value
    return os.environ.get(ACTOR_VARIABLE) or None


def display(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root.absolute()))
    except ValueError:
        return str(path)


@app.callback(invoke_without_command=True)
def main(
    version: Annotated[bool, typer.Option("--version", help="Show the installed version.")] = False,
) -> None:
    if version:
        from importlib.metadata import version as installed_version

        typer.echo(installed_version("toulmin"))
        raise typer.Exit()


@app.command("init")
def init_workbench(
    root: Annotated[Path, typer.Argument(help="Directory for the research workbench.")],
    project: Annotated[str, typer.Option("--project", help="Project name, e.g. tail-latency.")],
) -> None:
    """Create a workbench and project without overwriting existing content."""
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="--project") from error
    try:
        created = initialize(root, project)
    except (OSError, ValueError, RuntimeError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Workbench: {root.absolute()} | project: {project} | created entries: {created}")


@app.command("draft")
def draft_object(
    kind: Annotated[ObjectKind, typer.Argument(help="Object type.")],
    project: Annotated[str, typer.Argument(help="Project name.")],
    root: Annotated[Path, typer.Option("--root", help="Research workbench root.")] = Path("."),
    name: Annotated[
        str | None, typer.Option("--name", help="Optional filename suffix, e.g. tail-cause.")
    ] = None,
) -> None:
    """Write a fillable draft skeleton under the project's runs/drafts/."""
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="project") from error
    try:
        path = write_draft(root, project, kind, name, confirmer(None))
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    relative = display(path, root)
    typer.echo(relative)
    location = "" if root == Path(".") else f" --root {root}"
    typer.echo(
        f"Fill every <fill: ...> value, then: toulmin new {kind.value} {project}{location} "
        f"--input {relative} --confirm",
        err=True,
    )


@app.command("new")
def new_object(
    kind: Annotated[ObjectKind, typer.Argument(help="Object type.")],
    project: Annotated[str, typer.Argument(help="Project name.")],
    input_path: Annotated[
        str,
        typer.Option(
            "--input", help="Markdown draft path, relative to --root or absolute inside it."
        ),
    ],
    actor: Annotated[
        str | None,
        typer.Option(
            "--confirmed-by",
            help=f"Researcher authorizing intake. Defaults to ${ACTOR_VARIABLE}.",
        ),
    ] = None,
    root: Annotated[Path, typer.Option("--root", help="Research workbench root.")] = Path("."),
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Explicitly confirm this draft's intake.")
    ] = False,
) -> None:
    """Validate and create one object from a draft with researcher confirmation."""
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="project") from error
    actor = confirmer(actor)
    if actor is None:
        raise typer.BadParameter(
            f"required: pass --confirmed-by or set {ACTOR_VARIABLE}", param_hint="--confirmed-by"
        )
    try:
        path = create_object(root, project, kind, input_path, actor, confirm)
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(str(path))


@app.command("status")
def show_status(
    project: Annotated[str, typer.Argument(help="Project name.")],
    root: Annotated[Path, typer.Option("--root", help="Research workbench root.")] = Path("."),
) -> None:
    """Show stored state, conditions and data problems without changing files."""
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="project") from error
    try:
        report = project_status(root, project)
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(
        f"Project: {report.project}\nStage: {report.stage or 'unknown'}\n"
        f"Next step: {report.next_step or 'unknown'}"
    )
    typer.echo(
        "Data: valid (project files and direct references)"
        if not report.errors
        else "Data: INVALID; conditions unknown (partial view)"
    )
    typer.echo("Claims:" + ("" if report.claims else " none"))

    def flag(value: bool | None) -> str:
        return "unknown" if value is None else "yes" if value else "no"

    for claim in report.claims:
        typer.echo(
            f"  {claim.object_id} | stored={claim.stored_status} | "
            f"verified_support={claim.verified_support_count} | "
            f"open_objection={flag(claim.has_open_objection)} | "
            f"eligible_supported={flag(claim.eligible_for_supported)}"
        )
    typer.echo("Open objections:" + ("" if report.open_objections else " none"))
    for objection in report.open_objections:
        typer.echo(f"  {objection.object_id} | {objection.severity} | target={objection.target}")
    for notice in report.notices:
        typer.echo(f"Notice: {notice}")
    for message in report.errors:
        typer.echo(f"Error: {message}", err=True)
    if report.errors:
        raise typer.Exit(1)


@app.command("handoff")
def handoff(
    project: Annotated[str, typer.Argument(help="Project name.")],
    root: Annotated[Path, typer.Option("--root", help="Research workbench root.")] = Path("."),
    input_path: Annotated[
        str | None, typer.Option("--input", help="Session summary path relative to --root.")
    ] = None,
    apply_path: Annotated[
        str | None,
        typer.Option("--apply", help="Archived draft to apply or recover, relative to --root."),
    ] = None,
    actor: Annotated[
        str | None,
        typer.Option(
            "--confirmed-by",
            help=f"Researcher authorizing application. Defaults to ${ACTOR_VARIABLE}.",
        ),
    ] = None,
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Confirm application of this draft.")
    ] = False,
) -> None:
    """Archive a handoff draft, or explicitly apply/recover an approved draft."""
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="project") from error
    if apply_path is not None and input_path is not None:
        raise typer.BadParameter("--apply and --input are mutually exclusive")
    if apply_path is None and (confirm or actor is not None):
        raise typer.BadParameter("--confirm/--confirmed-by require --apply")
    if apply_path is not None:
        actor = confirmer(actor)
        if actor is None:
            raise typer.BadParameter(f"--apply requires --confirmed-by or {ACTOR_VARIABLE}")
    try:
        path = (
            draft_handoff(root, project, input_path)
            if apply_path is None
            else apply_handoff(root, project, apply_path, actor or "", confirm)
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(str(path.relative_to(root.absolute())))
