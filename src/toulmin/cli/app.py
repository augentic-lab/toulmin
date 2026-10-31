"""Installed CLI entry point."""

from pathlib import Path
from typing import Annotated

import typer

from toulmin.cli.initialize import initialize
from toulmin.core.identifiers import validate_project_name

app = typer.Typer(
    help="Toulmin research workbench. Initialize a file-based research repository.",
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
