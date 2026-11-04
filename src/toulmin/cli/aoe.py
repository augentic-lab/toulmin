"""Explicit AoE workspace operations; research approval remains a separate action."""

import json
import os
import shlex
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer

from toulmin.adapters.aoe import AoEClient, AoEError
from toulmin.application.aoe import AoEWorkspace, WorkspaceView
from toulmin.core.identifiers import validate_project_name
from toulmin.protocols.handoff import apply_handoff, draft_handoff
from toulmin.protocols.research_workspace import render_state

app = typer.Typer(
    help="Bind research sessions and explicitly refresh their context.", no_args_is_help=True
)

Project = Annotated[str, typer.Argument(help="Existing research project name.")]
Root = Annotated[Path, typer.Option("--root", help="Research workbench root.")]
Profile = Annotated[
    str | None, typer.Option("--profile", help="AoE profile; defaults to saved binding.")
]


def _workspace(
    root: Path, project: str, profile: str | None, *, offline: bool = False
) -> AoEWorkspace:
    validate_project_name(project)
    client = AoEClient(profile) if profile is not None and not offline else None
    return AoEWorkspace(root, project, client=client)


def _refresh_command(root: Path, project: str, profile: str | None) -> str:
    args = ["toulmin", "aoe", "refresh", project, "--root", str(root.absolute())]
    if profile is not None:
        args.extend(("--profile", profile))
    return shlex.join(args)


def _recovery(root: Path, project: str, profile: str | None) -> None:
    selected = profile or os.environ.get("AGENT_OF_EMPIRES_PROFILE", "main")
    local = Path.home() / ".local/bin/aoe"
    command = os.environ.get("TOULMIN_AOE_COMMAND") or (
        str(local) if local.is_file() and os.access(local, os.X_OK) else "aoe"
    )
    typer.echo("Inspect the native session in its AoE profile and resolve startup prompts:")
    typer.echo(shlex.join([command, "-p", selected]))
    typer.echo("Then refresh after the native input is ready:")
    typer.echo(_refresh_command(root, project, profile))
    typer.echo(
        "For uncertain delivery, inspect first; add --resend only to explicitly retry delivery."
    )


def _present(
    view: WorkspaceView,
    root: Path,
    project: str,
    *,
    bound_only: bool = False,
    offline: bool = False,
) -> None:
    typer.echo(render_state(view.research), nl=False)
    typer.echo("\nBINDING")
    binding = view.binding
    if binding is None:
        typer.echo("No saved binding.")
    else:
        typer.echo(
            f"Profile: {binding.profile} | agent: {binding.agent} | "
            f"session: {binding.session_id or 'unresolved'}"
        )
        if view.session is not None:
            typer.echo(
                f"Session state: {view.session.state} | status: {view.session.status or 'unknown'}"
            )
    typer.echo(f"\nCONTEXT\n{view.context_status}")
    if binding is not None:
        typer.echo(f"Delivery: {binding.delivery}")
    typer.echo("Submitted is not acknowledged. A context-read receipt is not research approval.")
    if view.context_path is not None:
        typer.echo(f"Read context: {view.context_path}")
        typer.echo(
            "After reading it and the listed snapshots, run its context-read receipt command."
        )
    if bound_only:
        typer.echo("Binding prepares files only; no message was sent to the native session.")
    if view.diagnostics:
        typer.echo("\nDIAGNOSTICS")
        for message in view.diagnostics:
            typer.echo(message)
    if binding and (
        binding.delivery in {"sending", "uncertain"}
        or (binding.delivery == "prepared" and not bound_only)
        or binding.session_id is None
        or (view.session is None and not offline)
        or (view.session is not None and view.session.state != "live")
    ):
        _recovery(root, project, binding.profile)
    elif view.context_status.startswith("stale"):
        typer.echo("Refresh the saved context:")
        typer.echo(_refresh_command(root, project, binding.profile if binding else None))


def _execute(
    root: Path,
    project: str,
    profile: str | None,
    action: Callable[[AoEWorkspace], WorkspaceView],
    *,
    offline: bool = False,
    json_output: bool = False,
    attach: bool = False,
    bound_only: bool = False,
    recovery_on_error: bool = False,
) -> None:
    workspace = None
    try:
        workspace = _workspace(root, project, profile, offline=offline)
        view = action(workspace)
        if json_output:
            typer.echo(json.dumps(asdict(view), indent=2, sort_keys=True, default=str))
        else:
            _present(view, root, project, bound_only=bound_only, offline=offline)
        if view.research.errors or view.context_status.startswith("invalid"):
            raise typer.Exit(1)
        if attach:
            binding, session = view.binding, view.session
            if (
                binding is None
                or session is None
                or binding.session_id != session.id
                or session.state != "live"
                or binding.agent != session.tool
            ):
                raise AoEError("Cannot attach: no verified live bound session")
            client = workspace.client or AoEClient(binding.profile)
            code = client.attach(session.id)
            if code:
                raise typer.Exit(code)
    except (AoEError, OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        if recovery_on_error:
            selected = profile
            if workspace is not None and selected is None:
                try:
                    saved = workspace.status(check_session=False)
                    if saved.binding is not None:
                        selected = saved.binding.profile
                except (AoEError, OSError, ValueError):
                    # Keep the original error visible if recovery metadata is also corrupt.
                    pass
            _recovery(root, project, selected)
        raise typer.Exit(1) from error


@app.command("open")
def open_workspace(
    project: Project,
    root: Root = Path("."),
    profile: Profile = None,
    agent: Annotated[str, typer.Option("--agent", help="Native CLI: codex or claude.")] = "codex",
    new_session: Annotated[
        bool, typer.Option("--new-session", help="Replace an archived binding with a new session.")
    ] = False,
    attach: Annotated[
        bool,
        typer.Option(
            "--attach", help="Attach after printing state; otherwise stay in this terminal."
        ),
    ] = False,
) -> None:
    """Open or recover one research session, with checked context delivery."""
    if agent not in {"codex", "claude"}:
        raise typer.BadParameter("expected codex or claude", param_hint="--agent")
    _execute(
        root,
        project,
        profile,
        lambda service: service.open(agent, new_session=new_session),
        attach=attach,
        recovery_on_error=True,
    )


@app.command("bind")
def bind_workspace(
    project: Project,
    root: Root = Path("."),
    profile: Profile = None,
    session: Annotated[
        str | None,
        typer.Option("--session", help="Session ID; omitted means the current native session."),
    ] = None,
    replace_existing: Annotated[
        bool, typer.Option("--replace", help="Explicitly replace an existing or relocated binding.")
    ] = False,
) -> None:
    """Bind an existing session and prepare context files without sending a message."""
    _execute(
        root,
        project,
        profile,
        lambda service: service.bind(session, replace_existing=replace_existing),
        bound_only=True,
    )


@app.command("status")
def workspace_status(
    project: Project,
    root: Root = Path("."),
    profile: Profile = None,
    offline: Annotated[
        bool, typer.Option("--offline", help="Read saved files only; do not invoke or require AoE.")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print structured state as JSON.")
    ] = False,
) -> None:
    """Show current research, binding and context receipt state."""
    _execute(
        root,
        project,
        profile,
        lambda service: service.status(check_session=not offline),
        offline=offline,
        json_output=json_output,
    )


@app.command("refresh")
def refresh_workspace(
    project: Project,
    root: Root = Path("."),
    profile: Profile = None,
    resend: Annotated[
        bool,
        typer.Option(
            "--resend", help="Explicitly retry previously submitted or uncertain delivery."
        ),
    ] = False,
) -> None:
    """Prepare changed research context and submit it only when the native session is ready."""
    _execute(
        root,
        project,
        profile,
        lambda service: service.refresh(resend=resend),
        recovery_on_error=True,
    )


@app.command("ack")
def acknowledge_context(
    project: Project,
    token: Annotated[str, typer.Option("--token", help="Receipt token from the context file.")],
    root: Root = Path("."),
    profile: Profile = None,
) -> None:
    """Record a context-read receipt; this does not approve research changes."""
    _execute(root, project, profile, lambda service: service.acknowledge(token), offline=True)


@app.command("handoff")
def workspace_handoff(
    project: Project,
    root: Root = Path("."),
    input_path: Annotated[
        str | None,
        typer.Option(
            "--input", help="Structured session summary (YAML + Markdown), relative to --root."
        ),
    ] = None,
    apply_path: Annotated[
        str | None,
        typer.Option(
            "--apply",
            help="Generated handoff draft.md, not a proposal or summary; relative to --root.",
        ),
    ] = None,
    actor: Annotated[
        str | None, typer.Option("--confirmed-by", help="Researcher; defaults to $TOULMIN_ACTOR.")
    ] = None,
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Confirm this handoff application.")
    ] = False,
) -> None:
    """Draft or explicitly apply a handoff; window exit never confirms or closes a session."""
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="project") from error
    if apply_path is not None and input_path is not None:
        raise typer.BadParameter("--apply and --input are mutually exclusive")
    if apply_path is None and (confirm or actor is not None):
        raise typer.BadParameter("--confirm/--confirmed-by require --apply")
    if apply_path is not None:
        actor = actor if actor is not None else os.environ.get("TOULMIN_ACTOR") or None
        if actor is None:
            raise typer.BadParameter("--apply requires --confirmed-by or TOULMIN_ACTOR")
    try:
        path = (
            draft_handoff(root, project, input_path)
            if apply_path is None
            else apply_handoff(root, project, apply_path, actor or "", confirm)
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(path.relative_to(root.absolute()).as_posix())
