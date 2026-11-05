"""``toulmin workspaces``: the researcher's list of known workspaces (WX6)."""

import shlex
from pathlib import Path
from typing import Annotated

import typer

from toulmin.adapters.aoe import AoEClient, AoEError
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
    help="List, forget or scan for known workspaces (a user-level list, not research data).",
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
