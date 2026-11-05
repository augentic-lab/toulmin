"""The one command to remember (WX2): ``toulmin open`` from wherever the researcher is.

It only chooses the root and scope, then delegates to ``aoe open`` unchanged. It never
initializes without an explicit yes in a terminal, and never approves anything. When no
workbench is found it offers the known workspaces (WX6), which ``--in`` opens by name or path.
"""

import os
import shlex
import sys
from pathlib import Path
from typing import Annotated

import typer

from toulmin.cli.aoe import Agent, Attach, NewSession, Profile, open_scope
from toulmin.cli.decide import inventory
from toulmin.cli.initialize import initialize_workspace, workspace_setup
from toulmin.cli.registry import Known, normal, note, registry_path
from toulmin.cli.settings import (
    ACTOR_VARIABLE,
    DEFAULT_AGENT,
    DEFAULT_PROFILE,
    EXAMPLE,
    PROFILE_VARIABLE,
    find_workbench,
    settings,
)
from toulmin.cli.workspaces import describe, listing
from toulmin.core.identifiers import validate_project_name
from toulmin.protocols.workspace_state import RootState, classify_root

config_app = typer.Typer(
    help="Show CLI preferences: the user config file, environment variables and defaults.",
    no_args_is_help=True,
)


def _fail(message: str) -> typer.Exit:
    typer.echo(f"Error: {message}", err=True)
    return typer.Exit(1)


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _child(here: Path, root: Path) -> str | None:
    """``projects/NAME`` (or below) selects that child; anything else is the workspace."""
    try:
        parts = here.relative_to(root).parts
    except ValueError:
        return None
    if len(parts) < 2 or parts[0] != "projects" or not (root / "projects" / parts[1]).is_dir():
        return None
    try:
        validate_project_name(parts[1])
    except ValueError:
        return None
    return parts[1]


def _initialize(root: Path) -> None:
    try:
        result = initialize_workspace(root, None)
    except (OSError, ValueError, RuntimeError) as error:
        raise _fail(str(error)) from error
    typer.echo(f"Workspace: {result.root} | name: {result.name} | entries: {result.created}")


def _offer_init(root: Path, state: RootState, here: Path, explicit: bool) -> None:
    where = f"at {root}" if explicit else f"at or above {here}"
    typer.echo(f"No Toulmin workspace {where}.")
    if not _interactive():
        typer.echo(f"Create one with: {shlex.join(['toulmin', 'init', str(root)])}")
        raise typer.Exit(1)
    verb = (
        "Finish the interrupted initialization of"
        if state is RootState.INCOMPLETE
        else "Initialize a project-free workspace in"
    )
    if not typer.confirm(f"{verb} {root} and open its session?", default=False):
        typer.echo("Nothing created.")
        raise typer.Exit(1)
    _initialize(root)


def _pick(root: Path, state: RootState, here: Path, items: list[Known]) -> Path:
    """No workbench here: choose a known workspace, initialize here, or stop."""
    initable = state is not RootState.UNRELATED
    if initable:
        typer.echo(f"No Toulmin workspace at or above {here}.")
    else:
        typer.echo(f"No Toulmin workbench at or above {here}, and {root} is not empty.")
    typer.echo("Known workspaces (most recently opened first):")
    for index, item in enumerate(items, 1):
        typer.echo(f"{index:>3}  {describe(item)}")
    if not _interactive():
        typer.echo("Open one with: toulmin open --in NAME_OR_PATH")
        if initable:
            typer.echo(f"Or create one here with: {shlex.join(['toulmin', 'init', str(root)])}")
        raise typer.Exit(1)
    keys = "number / i = initialize here / q = quit" if initable else "number / q = quit"
    while True:
        answer = str(typer.prompt(f"Open which? [{keys}]", default="q")).strip().lower()
        if answer == "q":
            typer.echo("Nothing opened.")
            raise typer.Exit(1)
        if answer == "i" and initable:
            _initialize(root)
            return root
        if answer.isdigit() and 1 <= int(answer) <= len(items):
            item = items[int(answer) - 1]
            if item.state in {"workspace", "legacy"}:
                return item.entry.path
            typer.echo(f"{item.entry.path} cannot be opened now ({item.state}).")
            continue
        typer.echo(f"Choose one of: {keys}")


def _select(value: str) -> Path:
    """``--in``: a path (contains a separator or starts with ~ or .) or a known name."""
    if "/" in value or value.startswith(("~", ".")):
        return normal(Path(value))
    items = listing()
    wanted = value.casefold()
    matches = [item for item in items if item.name.casefold() == wanted]
    usable = [item for item in matches if item.state in {"workspace", "legacy"}]
    if len(usable) == 1:
        return usable[0].entry.path
    if len(usable) > 1:
        typer.echo(f"Error: several known workspaces are named {value!r}:", err=True)
        for item in usable:
            typer.echo(f"  {describe(item)}", err=True)
        typer.echo("Give the path instead: toulmin open --in PATH", err=True)
        raise typer.Exit(2)
    if matches:
        raise _fail(
            f"the known workspace {value!r} cannot be opened now: "
            + ", ".join(f"{item.entry.path} ({item.state})" for item in matches)
        )
    typer.echo(f"Error: no known workspace is named {value!r}.", err=True)
    for item in items:
        typer.echo(f"  {describe(item)}", err=True)
    typer.echo("`toulmin workspaces` lists them; `toulmin workspaces scan` finds more.", err=True)
    raise typer.Exit(2)


def _pending(root: Path) -> None:
    try:
        count = len(inventory(root).items)
    except (OSError, ValueError):
        return  # aoe open reports unreadable workspace state itself; this line is a courtesy
    if count:
        typer.echo(f"Awaiting your decision: {count} item(s); run `toulmin decide`.\n")


def _classify(target: Path) -> tuple[Path, RootState]:
    try:
        report = classify_root(target, workspace_setup())
    except (OSError, ValueError) as error:
        raise _fail(str(error)) from error
    return report.root, report.state


def open_research(
    project: Annotated[
        str | None,
        typer.Argument(
            help="Child project. Omitted: the child whose directory you are in, else the workspace."
        ),
    ] = None,
    root: Annotated[
        Path | None,
        typer.Option(
            "--root",
            help="Workbench root. Omitted: the nearest workbench at or above this directory.",
        ),
    ] = None,
    within: Annotated[
        str | None,
        typer.Option(
            "--in",
            metavar="NAME_OR_PATH",
            help="Open a known workspace from anywhere, by its name or path.",
        ),
    ] = None,
    profile: Profile = None,
    agent: Agent = None,
    new_session: NewSession = False,
    attach: Attach = None,
) -> None:
    """Open the workspace session, or a child's, from wherever you are.

    Finds the workbench above the current directory; if there is none, offers the known
    workspaces or to initialize an empty directory (terminal only, default no). Notes items
    awaiting your review, then runs `aoe open` for the chosen scope. Preferences come from
    `toulmin config show`; `toulmin workspaces` lists the known workspaces.
    """
    if project is not None:
        try:
            validate_project_name(project)
        except ValueError as error:
            raise typer.BadParameter(str(error), param_hint="project") from error
    if within is not None:
        if root is not None:
            raise typer.BadParameter("give either --in or --root", param_hint="--in")
        root = _select(within)
    try:
        here = Path.cwd()
    except OSError as error:
        raise _fail(f"current directory unavailable: {error}") from error
    target = root if root is not None else (find_workbench(here) or here)
    base, state = _classify(target)
    unfound = {RootState.MISSING, RootState.EMPTY, RootState.INCOMPLETE, RootState.UNRELATED}
    if state in unfound and root is None and project is None:
        items = listing()
        if items:
            chosen = _pick(base, state, here, items)
            root = chosen  # explicit from here on: no child is inferred from the cwd
            base, state = _classify(chosen)
    if state in {RootState.MISSING, RootState.EMPTY, RootState.INCOMPLETE}:
        if project is not None:
            raise _fail(f"{base}: no workspace yet; run `toulmin open` without a project first")
        _offer_init(base, state, here, explicit=root is not None)
        state = RootState.WORKSPACE
    elif state is RootState.UNRELATED:
        raise _fail(
            f"{base} is not a Toulmin workbench and is not empty; nothing was initialized. "
            "Create a workspace in an empty directory: toulmin init DIR"
        )
    if project is None and root is None:
        project = _child(here, base)
    if state is RootState.LEGACY and project is None:
        typer.echo(
            f"{base} is an existing workbench without workspace state. Open a project with "
            "`toulmin open NAME`, or preview adoption with "
            f"{shlex.join(['toulmin', 'workspace', 'adopt', str(base)])}"
        )
        raise typer.Exit(1)
    note(base)
    _pending(base)
    open_scope(base, project, profile, agent, new_session=new_session, attach=attach)


@config_app.command("show")
def show_config() -> None:
    """Print each preference, its value and where it came from."""
    current = settings()
    typer.echo(f"Config file: {current.path} ({'loaded' if current.loaded else 'not found'})")

    def origin(variable: str | None, configured: object, default: object) -> tuple[object, str]:
        if variable is not None and os.environ.get(variable):
            return os.environ[variable], f"${variable}"
        if configured is not None:
            return configured, "config"
        return default, "default" if default is not None else "unset"

    rows = {
        "actor": origin(ACTOR_VARIABLE, current.actor, None),
        "aoe.profile": origin(PROFILE_VARIABLE, current.profile, DEFAULT_PROFILE),
        "aoe.agent": origin(None, current.agent, DEFAULT_AGENT),
        "aoe.attach": origin(None, current.attach, False),
    }
    for name, (value, source) in rows.items():
        shown = str(value).lower() if isinstance(value, bool) else value or "-"
        typer.echo(f"{name}: {shown} ({source})")
    typer.echo(
        "Command flags override these; an existing session keeps the profile and agent "
        "saved in its binding."
    )
    typer.echo(f"Workspace list: {registry_path()} (`toulmin workspaces`)")
    if not current.loaded:
        typer.echo(f"\nExample {current.path}:\n{EXAMPLE}", nl=False)
