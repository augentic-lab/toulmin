"""The researcher's explicit workspace commit command."""

from pathlib import Path
from typing import Annotated

import typer

from toulmin.adapters.git import GitError
from toulmin.application.workspace_commit import confirm_commit, prepare_commit
from toulmin.cli.settings import root_option


def commit_command(
    root: Annotated[Path, root_option("Research workspace root.")] = Path("."),
    message: Annotated[
        str | None, typer.Option("--message", help="Replace the subject only.")
    ] = None,
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Stage and commit the shown paths.")
    ] = False,
) -> None:
    """Preview a research commit; only --confirm writes it. Never pushes."""
    try:
        plan = prepare_commit(root, message)
        for group, paths in plan.summary.groups:
            typer.echo(group + ":")
            for path in paths:
                typer.echo("  " + repr(path))
        typer.echo("Proposed message:\n" + plan.summary.message)
        if not confirm:
            typer.echo(
                "Nothing is committed without --confirm. "
                "Toulmin never pushes: run git push yourself."
            )
            return
        head = confirm_commit(plan)
    except GitError as error:
        if error.result.stdout:
            typer.echo(error.result.stdout, nl=False)
        if error.result.stderr:
            typer.echo(error.result.stderr, err=True, nl=False)
        if error.result.exit_status is None:
            typer.echo("git timed out", err=True)
        raise typer.Exit(error.result.exit_status or 1) from error
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Committed: {head}\nPush yourself: git push")
