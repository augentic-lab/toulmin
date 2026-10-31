"""Installed CLI entry point; research commands arrive in T2–T5."""

from typing import Annotated

import typer

app = typer.Typer(
    help="Toulmin research workbench. T1 foundation; research commands are not implemented yet.",
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
