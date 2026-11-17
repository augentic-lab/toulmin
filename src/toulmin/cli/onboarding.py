"""Research-workspace onboarding and local source binding commands."""

from pathlib import Path
from typing import Annotated

import typer

from toulmin.application.onboarding import prepare
from toulmin.application.sources import bind_source
from toulmin.cli.initialize import initialize_workspace
from toulmin.cli.settings import root_option
from toulmin.core.sources import read_catalog
from toulmin.protocols.context_change import propose_overview, propose_source_role

source_app = typer.Typer(
    help="Inspect source associations and bind machine-local paths.", no_args_is_help=True
)
Root = Annotated[Path, root_option("Independent research workspace root.")]


def onboard_command(
    source: Annotated[
        Path,
        typer.Argument(help="Existing local Git or ordinary project directory (never modified)."),
    ],
    project: Annotated[str, typer.Option("--project", help="New child research project name.")],
    root: Root = Path("."),
    work_at: Annotated[
        Path | None,
        typer.Option("--work-at", help="Existing working directory; SOURCE becomes reference."),
    ] = None,
    overview: Annotated[
        Path | None, typer.Option("--overview", help="Optional proposed structural overview text.")
    ] = None,
    init: Annotated[
        bool,
        typer.Option(
            "--init", help="Explicitly confirm initialization of missing/empty workspace."
        ),
    ] = False,
) -> None:
    """Prepare a reviewed onboarding packet; apply it through toulmin decide."""
    try:
        # Inspect source/workspace separation before any workspace mutation.
        from toulmin.application.sources import validate_directory

        validate_directory(root, source)
        if work_at:
            validate_directory(root, work_at)
        if not (root / "WORKSPACE.md").exists():
            if not init:
                raise ValueError(
                    "workspace is uninitialized; run toulmin init ROOT "
                    "or confirm onboarding initialization with --init"
                )
            initialize_workspace(root)
        result = prepare(
            root,
            source,
            project,
            work_at,
            overview=overview.read_text(encoding="utf-8") if overview else None,
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Onboarding packet: {result.loaded.directory}")
    typer.echo(result.loaded.body)
    typer.echo(f"Researcher: toulmin decide --root {root.absolute()}")


@source_app.command("list")
def list_command(root: Root = Path(".")) -> None:
    """Show tracked logical source identities and project roles."""
    try:
        for source in read_catalog(root):
            typer.echo(f"{source.source_id}: {source.project} {source.role} ({source.kind})")
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error


@source_app.command("bind")
def bind_command(source_id: str, path: Path, root: Root = Path(".")) -> None:
    """Validate identity and save only this machine's source path."""
    try:
        result = bind_source(root, source_id, path)
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Bound {result.source_id}: {result.path} (machine-local; source files unchanged)")


@source_app.command("working")
def working_command(project: str, source_id: str, rationale: str, root: Root = Path(".")) -> None:
    """Propose which existing associated source becomes the working source."""
    try:
        result = propose_source_role(root, project, source_id, rationale=rationale)
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Source role proposal: {result.loaded.directory}")
    typer.echo(f"Researcher: toulmin decide --root {root.absolute()}")


def overview_command(
    project: str,
    input_path: Annotated[Path, typer.Option("--input")],
    rationale: str,
    root: Root = Path("."),
    goal: str | None = None,
    constraints: str | None = None,
) -> None:
    """Propose a structural project overview and optional charter section updates."""
    try:
        result = propose_overview(
            root,
            project,
            input_path.read_text(encoding="utf-8"),
            rationale=rationale,
            goal=goal,
            constraints=constraints,
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Overview proposal: {result.loaded.directory}")
    typer.echo(f"Researcher: toulmin decide --root {root.absolute()}")


@source_app.command("add")
def add_command(
    path: Path,
    project: Annotated[str, typer.Option("--project")],
    rationale: Annotated[str, typer.Option("--rationale")],
    root: Root = Path("."),
    working: bool = False,
) -> None:
    """Propose an additional reference or working source without copying it."""
    from toulmin.application.onboarding import add_source

    try:
        result = add_source(root, project, path, working=working, rationale=rationale)
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Source association proposal: {result.loaded.directory}")
    typer.echo(f"Researcher: toulmin decide --root {root.absolute()}")
