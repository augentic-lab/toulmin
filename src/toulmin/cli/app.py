"""Installed CLI entry point."""

from pathlib import Path
from typing import Annotated

import typer

from toulmin.cli.initialize import initialize
from toulmin.core.identifiers import ObjectKind, validate_project_name
from toulmin.protocols.intake import create_object

app = typer.Typer(
    help="Toulmin research workbench. Initialize workbenches and create research objects.",
    add_completion=False,
    no_args_is_help=True,
)


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


@app.command("new")
def new_object(
    kind: Annotated[ObjectKind, typer.Argument(help="Object type.")],
    project: Annotated[str, typer.Argument(help="Project name.")],
    input_path: Annotated[
        str, typer.Option("--input", help="Markdown draft path relative to --root.")
    ],
    actor: Annotated[str, typer.Option("--confirmed-by", help="Researcher authorizing intake.")],
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
    try:
        path = create_object(root, project, kind, input_path, actor, confirm)
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(str(path))
