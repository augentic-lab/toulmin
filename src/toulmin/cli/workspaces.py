"""``toulmin workspaces``: the researcher's list of known workspaces (WX6)."""

import shlex
import tarfile
from pathlib import Path
from typing import Annotated

import typer

from toulmin.adapters.aoe import AoEClient, AoEError
from toulmin.application.workspace_remove import (
    RemovalError,
    RemovalPlan,
    delete_folder,
    plan_removal,
    remove_sessions,
    write_archive,
)
from toulmin.cli.decide import inventory
from toulmin.cli.registry import (
    Known,
    RegistryError,
    charter_name,
    forget,
    known,
    normal,
    registry_path,
    remember,
)
from toulmin.cli.settings import DEFAULT_PROFILE, default_profile
from toulmin.core.workspace import CHARTER_FILE

app = typer.Typer(
    help="List, forget, scan or remove known workspaces (the list is not research data).",
    invoke_without_command=True,
)

FLAGS = {"missing": "missing", "damaged": "WORKSPACE.md unreadable", "legacy": "legacy workbench"}


def _fail(message: object) -> typer.Exit:
    typer.echo(f"Error: {message}", err=True)
    return typer.Exit(1)


def pending_count(root: Path) -> int | None:
    try:
        return len(inventory(root).items)
    except (OSError, ValueError):
        return None  # status and decide report damaged state themselves


def describe(item: Known) -> str:
    """One line: name, path, last opened and what needs attention, computed now."""
    opened = item.entry.last_opened
    when = f"{opened[:10]} {opened[11:16]} UTC" if opened else "found by scan"
    notes = [FLAGS[item.state]] if item.state in FLAGS else []
    if item.state in {"workspace", "legacy"}:
        count = pending_count(item.entry.path)
        if count:
            notes.append(f"{count} item(s) await decision")
    suffix = f"  [{'; '.join(notes)}]" if notes else ""
    return f"{item.name}  {item.entry.path}  {when}{suffix}"


def listing() -> list[Known]:
    """The known workspaces, or an empty list with a notice when the file is unusable."""
    try:
        return known()
    except RegistryError as error:
        typer.echo(f"Notice: workspace list unavailable: {error}", err=True)
        return []


@app.callback()
def list_workspaces(ctx: typer.Context) -> None:
    """Without a subcommand: list known workspaces, most recently opened first."""
    if ctx.invoked_subcommand is not None:
        return
    try:
        items = known()
    except RegistryError as error:
        raise _fail(f"{error}. Fix or delete the file; it only lists folders.") from error
    if not items:
        typer.echo(
            "No known workspaces yet. `toulmin init` and `toulmin open` add them; "
            "`toulmin workspaces scan` finds those with AoE sessions."
        )
        return
    for index, item in enumerate(items, 1):
        typer.echo(f"{index:>3}  {describe(item)}")
    typer.echo(f"\nOpen one from anywhere: toulmin open --in NAME_OR_PATH\nList: {registry_path()}")


@app.command("forget")
def forget_workspace(
    path: Annotated[Path, typer.Argument(help="The listed path to remove from the list.")],
) -> None:
    """Remove one entry from the list; the folder and its files are not touched."""
    try:
        removed = forget(path)
    except (OSError, RegistryError) as error:
        raise _fail(error) from error
    if not removed:
        raise _fail(f"{normal(path)} is not in the workspace list")
    typer.echo(f"Forgotten: {normal(path)} (the folder was not touched)")


def _workspace_root(path: Path) -> Path | None:
    """A session path that is a workspace root or a ``projects/NAME`` child of one."""
    for candidate in (path, path.parent.parent if path.parent.name == "projects" else None):
        if candidate is not None and charter_name(candidate) is not None:
            return candidate
    return None


@app.command("scan")
def scan_workspaces(
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="AoE profile to scan (default: your configured profile)."),
    ] = None,
) -> None:
    """Add workspaces whose folders have sessions in an AoE profile (reads AoE only)."""
    selected = profile or default_profile() or DEFAULT_PROFILE
    try:
        sessions = AoEClient(selected).list_sessions()
    except (AoEError, OSError) as error:
        raise _fail(error) from error
    roots = sorted({root for item in sessions if (root := _workspace_root(item.path))})
    added = 0
    for root in roots:
        try:
            new = remember(root, charter_name(root) or root.name, opened=False)
        except (OSError, RegistryError) as error:
            raise _fail(error) from error
        added += new
        typer.echo(f"{'Added' if new else 'Known'}: {charter_name(root)}  {root}")
    typer.echo(
        f"Profile {selected}: {len(sessions)} session(s), {len(roots)} workspace(s) with a "
        f"{CHARTER_FILE}, {added} added."
    )
    if roots:
        typer.echo("Open one with: " + shlex.join(["toulmin", "open", "--in", str(roots[0])]))


def _target(value: str) -> Path:
    """A path (contains a separator or starts with ~ or .) or exactly one known name."""
    if "/" in value or value.startswith(("~", ".")):
        return normal(Path(value))
    wanted = value.casefold()
    matches = [item for item in listing() if item.name.casefold() == wanted]
    if len(matches) == 1:
        return matches[0].entry.path
    if matches:
        raise _fail(
            f"several known workspaces are named {value!r}; give the path: "
            + ", ".join(str(item.entry.path) for item in matches)
        )
    raise _fail(f"no known workspace is named {value!r}; give its path")


def _size(count: int) -> str:
    if count < 1024:
        return f"{count} B"
    value = float(count)
    for unit in ("KB", "MB", "GB"):
        value /= 1024
        if value < 1024 or unit == "GB":
            break
    return f"{value:.1f} {unit}"


def _render(plan: RemovalPlan) -> None:
    label = "workspace" if plan.kind == "workspace" else "legacy workbench"
    typer.echo(f"Remove {label} {plan.name!r}: {plan.root}")
    projects = ", ".join(plan.projects) or "none"
    typer.echo(f"  Folder: {plan.files} files, {_size(plan.size)}; projects: {projects}")
    typer.echo("  " + (plan.git.line() if plan.git else "git: not a repository"))
    if plan.sessions:
        typer.echo("  AoE sessions to move to AoE's trash:")
        for session in plan.sessions:
            status = f", {session.status}" if session.status else ""
            title = session.title or "(untitled)"
            typer.echo(f"    {session.id}  [{session.profile}] {title} ({session.state}{status})")
    else:
        typer.echo("  AoE sessions: none found")
    for task in plan.tasks:
        where = f"project {task.project}" if task.project else "found by its paths"
        typer.echo(f"  Chief task {task.id} ({where}): {task.state or 'no Chief record'}")
    for note in plan.notes:
        typer.echo(f"  Note: {note}")
    typer.echo("  Not touched: code repositories, Chief state, git remotes, AoE profiles.")
    for loss in plan.losses:
        typer.echo(f"  LOST: {loss}")
    for blocker in plan.blockers:
        typer.echo(f"  BLOCKED: {blocker}")


@app.command("remove")
def remove_workspace(
    target: Annotated[str, typer.Argument(help="Known workspace name, or the folder's path.")],
    archive: Annotated[
        Path | None,
        typer.Option("--archive", help="First save the whole folder as this .tar.gz file."),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="Also look for sessions in this AoE profile."),
    ] = None,
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Remove after you type the folder name.")
    ] = False,
) -> None:
    """Preview, then remove a workspace: its AoE sessions, its folder and its list entry."""
    root = _target(target)
    selected = profile or default_profile() or DEFAULT_PROFILE
    try:
        plan = plan_removal(root, AoEClient, default_profile=selected)
    except (OSError, RemovalError) as error:
        raise _fail(error) from error
    _render(plan)
    if plan.blockers:
        raise _fail("nothing removed; resolve the BLOCKED lines first")
    if archive is not None:
        typer.echo(f"  Archive first: {normal(archive)}")
    elif plan.losses:
        typer.echo("  Keep a copy with --archive FILE.tar.gz (outside the folder).")
    if not confirm:
        typer.echo("Preview only. Remove with --confirm; this cannot be undone.")
        return
    answer = typer.prompt(f"Type the folder name ({plan.root.name}) to remove it", default="")
    if answer != plan.root.name:
        raise _fail("name did not match; nothing removed")
    try:
        if archive is not None:
            size = write_archive(plan.root, archive)
            typer.echo(f"Archived: {normal(archive)} ({_size(size)})")
    except (OSError, RemovalError, tarfile.TarError) as error:
        raise _fail(f"archive not written ({error}); nothing removed") from error
    removed: list[str] = []
    try:
        remove_sessions(plan, AoEClient, removed)
    except (AoEError, OSError) as error:
        done = ", ".join(removed) or "none"
        raise _fail(f"{error}; sessions already in AoE's trash: {done}; folder kept") from error
    for session in plan.sessions:
        typer.echo(f"Session {session.id} moved to AoE's trash")
    try:
        delete_folder(plan.root)
    except (OSError, RemovalError) as error:
        raise _fail(
            f"folder only partly removed ({error}); inspect {plan.root} and delete it by hand; "
            "the workspace list still names it"
        ) from error
    typer.echo(f"Folder removed: {plan.root}")
    try:
        listed = forget(plan.root)
    except (OSError, RegistryError) as error:
        raise _fail(f"folder removed, list entry kept ({error})") from error
    typer.echo(
        "Removed from the workspace list." if listed else "It was not in the workspace list."
    )
