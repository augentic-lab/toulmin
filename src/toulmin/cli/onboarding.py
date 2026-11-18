"""Reviewed workspace-first intake, understanding and local source operations."""

import os
from pathlib import Path
from typing import Annotated

import typer

from toulmin.application import workspace_onboarding as onboarding
from toulmin.application.sources import (
    SourceSelectionRequired,
    bind_source,
    inspect_source,
    validate_directory,
)
from toulmin.cli.initialize import initialize_workspace
from toulmin.cli.settings import root_option
from toulmin.core.documents import FormatError
from toulmin.core.identifiers import validate_project_name
from toulmin.core.scope import Scope
from toulmin.core.sources import SOURCE_ID, InspectionPolicy, read_source_catalog
from toulmin.protocols import workspace_onboarding as packets
from toulmin.protocols.context_change import propose_overview, propose_source_role

source_app = typer.Typer(
    help="Inspect shared sources, propose roles, upgrade v1 or bind local paths.",
    no_args_is_help=True,
)
Root = Annotated[Path, root_option("Independent research workspace root.")]


def _error(error: Exception) -> typer.Exit:
    typer.echo(f"Error: {error}", err=True)
    return typer.Exit(2 if isinstance(error, SourceSelectionRequired) else 1)


def _id(value: str | None) -> None:
    if value is not None and not SOURCE_ID.fullmatch(value):
        raise typer.BadParameter("source ID: expected [a-z][a-z0-9-]{0,79}")


def _project(value: str | None) -> None:
    if value is not None:
        try:
            validate_project_name(value)
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error


def _show(root: Path, outcome: packets.Outcome) -> None:
    typer.echo(f"Workspace packet: {outcome.loaded.directory}")
    typer.echo(packets.preview(root, outcome.loaded))
    typer.echo(f"Researcher: toulmin decide --workspace --root {root.absolute()}")


def onboard_command(
    source: Annotated[
        Path, typer.Argument(help="Existing local source root; inspected read-only.")
    ],
    root: Annotated[
        Path | None, typer.Option("--root", help="Required explicit records root; never inferred.")
    ] = None,
    project: Annotated[
        str | None, typer.Option("--project", help="Exactly one explicitly requested NEW child.")
    ] = None,
    init: Annotated[
        bool, typer.Option("--init", help="Initialize a missing/empty records root (A/B only).")
    ] = False,
    work_at: Path | None = None,
    overview: Path | None = None,
    workspace_overview: Path | None = None,
    project_overview: Path | None = None,
    project_input: Path | None = None,
    charter_input: Path | None = None,
    source_id: str | None = None,
    register_source: str | None = None,
    working_source_id: str | None = None,
    register_working_source: str | None = None,
    include: Annotated[
        list[str] | None,
        typer.Option(
            "--include",
            help="Literal source-relative file/directory to inventory; repeat in priority order.",
        ),
    ] = None,
    exclude: Annotated[
        list[str] | None,
        typer.Option(
            "--exclude", help="Literal source-relative prefix to omit; requires --include."
        ),
    ] = None,
) -> None:
    """A: new workspace only; B: plus one child; C: new child in selected workspace.

    Prepare a sealed review packet. Confirm with decide or the exact sealed apply
    form. Intake never starts a session, runs source scripts or grants permissions.
    """
    if root is None:
        raise typer.BadParameter("onboard requires --root ROOT; workspace selection is explicit")
    _project(project)
    for value in (source_id, register_source, working_source_id, register_working_source):
        _id(value)
    if (source_id and register_source) or (working_source_id and register_working_source):
        raise typer.BadParameter("choose reuse ID or registration ID, not both")
    if project is None and (project_input or project_overview):
        raise typer.BadParameter("--project-input/--project-overview require --project")
    if project is None and not init and (root / "WORKSPACE.md").exists():
        raise typer.BadParameter(
            "existing workspace intake requires --project; "
            "later workspace sources use source add --workspace"
        )
    if not init and (workspace_overview or charter_input):
        raise typer.BadParameter(
            "C preserves workspace context; propose overview/charter separately"
        )
    if overview and (
        (project is None and workspace_overview) or (project is not None and project_overview)
    ):
        raise typer.BadParameter("overview aliases are mutually exclusive")
    if work_at is None and (working_source_id or register_working_source):
        raise typer.BadParameter("working source ID requires --work-at TARGET")
    try:
        inspection = (
            InspectionPolicy(tuple(include or ()), tuple(exclude or ()))
            if include is not None or exclude is not None
            else None
        )
        if inspection is not None and work_at is not None:
            raise FormatError("explicit inspection selection cannot be combined with --work-at")
        selected = validate_directory(root, source)
        if inspection is not None:
            # Reject bad/nonexistent/symlink selections before init leaves a records root.
            inspect_source(root, selected, inspection=inspection)
        if work_at:
            target = validate_directory(root, work_at)
            if (
                selected == target
                or selected.is_relative_to(target)
                or target.is_relative_to(selected)
            ):
                raise FormatError("source and target must be distinct non-overlapping directories")
        if project is not None and os.path.lexists(root / "projects" / project):
            raise FormatError(f"projects/{project}: occupied; choose a new child name")
        if init:
            if root.exists() and (
                not root.is_dir() or any(p.name != ".git" for p in root.iterdir())
            ):
                raise FormatError(
                    f"{root}: --init permits only missing/empty "
                    f"roots or .git alone; omit --init for C"
                )
            initialize_workspace(root)
        elif not (root / "WORKSPACE.md").is_file():
            raise FormatError(f"{root}: workspace missing; use --init only for a new empty root")
        workspace_file = workspace_overview or (overview if project is None else None)
        child_file = project_overview or (overview if project is not None else None)
        result = onboarding.prepare(
            root,
            selected,
            project,
            mode=("B" if project else "A") if init else "C",
            work_at=work_at,
            project_input=project_input.read_bytes() if project_input else None,
            workspace_body=workspace_file.read_text(encoding="utf-8") if workspace_file else None,
            project_overview=child_file.read_bytes() if child_file else None,
            charter_input=charter_input.read_bytes() if charter_input else None,
            source_id=source_id,
            register_source=register_source,
            working_source_id=working_source_id,
            register_working_source=register_working_source,
            inspection=inspection,
        )
        _show(root, result)
    except (OSError, ValueError) as error:
        raise _error(error) from error


@source_app.command("list")
def list_command(
    root: Root = Path("."), workspace: bool = False, project: str | None = None
) -> None:
    """Read definitions/roles; missing local mappings remain portable/unavailable state."""
    if workspace and project:
        raise typer.BadParameter("give --workspace or --project")
    try:
        catalog = read_source_catalog(root)
        for definition in catalog.definitions:
            typer.echo(f"Source {definition.id}: {definition.kind} {definition.identity}")
        for association in catalog.associations:
            if (workspace and association.scope.project is not None) or (
                project and association.scope.project != project
            ):
                continue
            typer.echo(f"{association.scope.display}: {association.source} {association.role}")
        if workspace or project is not None:
            from toulmin.application.sources import scope_source_reports

            for line in scope_source_reports(root, project):
                typer.echo(line)
    except (OSError, ValueError) as error:
        raise _error(error) from error


@source_app.command("bind")
def bind_command(source_id: str, path: Path, root: Root = Path("."), confirm: bool = False) -> None:
    """Preview a local binding; --confirm changes only its named local entry."""
    _id(source_id)
    try:
        result = bind_source(root, source_id, path, confirmed=confirm)
        typer.echo(f"{'Bound' if confirm else 'Preview'} {result.source_id}: {result.path}")
        if not confirm:
            typer.echo("Preview only; source files unchanged. Rerun with --confirm after review.")
    except (OSError, ValueError) as error:
        raise _error(error) from error


@source_app.command("working")
def working_command(
    project_or_source: Annotated[
        str, typer.Argument(help="Project name, or source ID with --workspace.")
    ],
    source_id: Annotated[str | None, typer.Argument()] = None,
    rationale_text: Annotated[str | None, typer.Argument()] = None,
    root: Root = Path("."),
    workspace: bool = False,
    rationale: Annotated[str | None, typer.Option("--rationale")] = None,
) -> None:
    """Propose a scope's working selection; never rebind or redirect its session."""
    if workspace and (source_id or rationale_text):
        raise typer.BadParameter("workspace form: source working --workspace ID --rationale TEXT")
    project: str | None
    selected: str | None
    reason: str | None
    if workspace:
        selected, project, reason = project_or_source, None, rationale
    else:
        selected, project, reason = source_id, project_or_source, rationale or rationale_text
    if not selected or not reason:
        raise typer.BadParameter("source ID and rationale are required")
    _id(selected)
    try:
        if not workspace and read_source_catalog(root).schema_version == 1:
            old = propose_source_role(root, project_or_source, selected, rationale=reason)
            typer.echo(f"Source role proposal: {old.loaded.directory}")
        else:
            result = onboarding.prepare(
                root,
                operation="source-change",
                scope=Scope(project),
                sources=(selected,),
                working_source=selected,
                rationale=reason,
            )
            _show(root, result)
    except (OSError, ValueError) as error:
        raise _error(error) from error


def overview_command(
    project: Annotated[str | None, typer.Argument()] = None,
    rationale_text: Annotated[str | None, typer.Argument()] = None,
    input_path: Annotated[Path | None, typer.Option("--input")] = None,
    root: Root = Path("."),
    workspace: bool = False,
    rationale: Annotated[str | None, typer.Option("--rationale")] = None,
    source: Annotated[list[str] | None, typer.Option("--source")] = None,
    goal: str | None = None,
    constraints: str | None = None,
) -> None:
    """Propose shared workspace understanding or an existing project overview."""
    if workspace and project:
        raise typer.BadParameter("give project or --workspace")
    if input_path is None or not (rationale or rationale_text):
        raise typer.BadParameter("--input and rationale are required")
    reason = rationale or rationale_text
    assert reason is not None
    try:
        if workspace:
            if not source or goal is not None or constraints is not None:
                raise typer.BadParameter(
                    "workspace overview needs --source ID ...; charter changes are separate"
                )
            _show(
                root,
                onboarding.prepare(
                    root,
                    operation="understanding-update",
                    sources=tuple(source),
                    workspace_body=input_path.read_text(encoding="utf-8"),
                    rationale=reason,
                ),
            )
        else:
            if project is None:
                raise typer.BadParameter("select project or --workspace")
            result = propose_overview(
                root,
                project,
                input_path.read_text(encoding="utf-8"),
                rationale=reason,
                goal=goal,
                constraints=constraints,
            )
            typer.echo(f"Overview proposal: {result.loaded.directory}")
            typer.echo(f"Researcher: toulmin decide --root {root.absolute()}")
    except typer.BadParameter:
        raise
    except (OSError, ValueError) as error:
        raise _error(error) from error


@source_app.command("add")
def add_command(
    path: Path,
    rationale: Annotated[str, typer.Option("--rationale")],
    project: str | None = None,
    root: Root = Path("."),
    workspace: bool = False,
    working: bool = False,
    source_id: str | None = None,
    register_source: str | None = None,
) -> None:
    """Propose a source reference/working choice in an explicit workspace or project."""
    if workspace == (project is not None):
        raise typer.BadParameter("give --workspace or --project NAME")
    for value in (source_id, register_source):
        _id(value)
    if source_id and register_source:
        raise typer.BadParameter("choose --source-id or --register-source")
    try:
        if not workspace and read_source_catalog(root).schema_version == 1:
            from toulmin.application.onboarding import add_source

            assert project is not None
            result = add_source(root, project, path, working=working, rationale=rationale)
            typer.echo(f"Source association proposal: {result.loaded.directory}")
        else:
            _show(
                root,
                onboarding.prepare(
                    root,
                    path,
                    operation="source-change",
                    scope=Scope(project),
                    working=working,
                    source_id=source_id,
                    register_source=register_source,
                    rationale=rationale,
                ),
            )
    except (OSError, ValueError) as error:
        raise _error(error) from error


@source_app.command("upgrade")
def upgrade_command(root: Root = Path(".")) -> None:
    """Propose opt-in v1 → v2 conversion with exact legacy bytes preserved; never on read."""
    try:
        _show(root, onboarding.upgrade(root))
    except (OSError, ValueError) as error:
        raise _error(error) from error
