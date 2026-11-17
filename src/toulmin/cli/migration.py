"""Guided migration records; external copying stays with the native tools."""

from pathlib import Path
from typing import Annotated

import typer

from toulmin.cli.settings import ACTOR_HINT, resolve_actor, root_option
from toulmin.protocols import migration

app = typer.Typer(help="Draft and record selected migration batches; never move source files.")


@app.command("draft")
def draft(project: str, root: Annotated[Path, root_option("Workspace root.")] = Path(".")) -> None:
    try:
        typer.echo(migration.draft(root, project).relative_to(root.absolute()))
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error


@app.command("record")
def record(
    project: str,
    input_path: Annotated[str, typer.Option("--input")],
    root: Annotated[Path, root_option("Workspace root.")] = Path("."),
    confirm: Annotated[bool, typer.Option("--confirm")] = False,
    actor: Annotated[str | None, typer.Option("--confirmed-by")] = None,
) -> None:
    """Preview a batch; confirmation records the assessment without executing checks."""
    try:
        raw, sha = migration.preview(root, project, input_path)
        typer.echo(raw.decode())
        typer.echo("Records the stated results; does not run checks or move files.")
        if confirm:
            who = resolve_actor(actor)
            if who is None:
                raise ValueError(ACTOR_HINT)
            result = migration.record(root, project, input_path, who, sha)
            typer.echo(result.relative_to(root.absolute()))
        else:
            typer.echo("Preview only; use --confirm in your own terminal to record.")
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
