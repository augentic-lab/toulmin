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
from toulmin.adapters.provider_logs import ModelReport
from toulmin.application.aoe import AoEWorkspace, WorkspaceView, render_scope
from toulmin.cli.settings import (
    ACTOR_HINT,
    AGENTS,
    DEFAULT_PROFILE,
    default_agent,
    default_attach,
    default_profile,
    resolve_actor,
    root_option,
)
from toulmin.core.identifiers import validate_project_name
from toulmin.protocols import workspace_handoff as workspace_handoffs
from toulmin.protocols.handoff import apply_handoff, draft_handoff

app = typer.Typer(
    help="Bind research sessions and explicitly refresh their context.", no_args_is_help=True
)

Project = Annotated[
    str | None,
    typer.Argument(help="Research project name; omit (or pass --workspace) for the workspace."),
]
Workspace = Annotated[
    bool, typer.Option("--workspace", help="Select the workspace scope explicitly.")
]
Root = Annotated[Path, root_option("Research workbench root.")]
Profile = Annotated[
    str | None, typer.Option("--profile", help="AoE profile; defaults to saved binding.")
]


def _select(project: str | None, workspace: bool) -> str | None:
    """Omitted PROJECT selects the workspace (contract 2.2); never inferred from history."""
    if project is not None and workspace:
        raise typer.BadParameter("give PROJECT or --workspace, not both", param_hint="project")
    if project is not None:
        try:
            validate_project_name(project)
        except ValueError as error:
            raise typer.BadParameter(str(error), param_hint="project") from error
    return project


def _selector(project: str | None) -> list[str]:
    return ["--workspace"] if project is None else [project]


def _workspace(
    root: Path, project: str | None, profile: str | None, *, offline: bool = False
) -> AoEWorkspace:
    if project is not None:
        validate_project_name(project)
    client = AoEClient(profile) if profile is not None and not offline else None
    if client is not None or offline:
        return AoEWorkspace(root, project, client=client)
    # Without --profile, a saved binding's profile wins; this default serves new bindings.
    return AoEWorkspace(root, project, client=None, default_profile=default_profile())


def _refresh_command(root: Path, project: str | None, profile: str | None) -> str:
    args = ["toulmin", "aoe", "refresh", *_selector(project), "--root", str(root.absolute())]
    if profile is not None:
        args.extend(("--profile", profile))
    return shlex.join(args)


def _recovery(root: Path, project: str | None, profile: str | None) -> None:
    selected = profile or default_profile() or DEFAULT_PROFILE
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


def _model_line(model: ModelReport | None, agent: str) -> str:
    """Which model answered, as the native CLI logged it; Toulmin never chooses one."""
    if model is None:
        return "Model: not yet reported (the native CLI's own configured default applies)"
    effort = f", effort {model.effort}" if model.effort else ""
    return f"Model: {model.model}{effort} (reported by the {agent} session log)"


def _present(
    view: WorkspaceView,
    root: Path,
    project: str | None,
    *,
    bound_only: bool = False,
    offline: bool = False,
) -> None:
    typer.echo(f"Root: {root.absolute()}")
    typer.echo("Scope: " + ("Workspace" if project is None else f"Project: {project}") + "\n")
    typer.echo(render_scope(view.research), nl=False)
    typer.echo("\nBINDING")
    binding = view.binding
    if binding is None:
        typer.echo("No saved binding.")
    else:
        typer.echo(
            f"Profile: {binding.profile} | agent: {binding.agent} | "
            f"session: {binding.session_id or 'unresolved'}"
        )
        if binding.title:
            typer.echo(f"Title: {binding.title} | binding version {binding.version}")
        typer.echo(_model_line(view.model, binding.agent))
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
    project: str | None,
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


Agent = Annotated[
    str | None,
    typer.Option(
        "--agent",
        help="Native CLI for a new session: codex or claude. Default: the replaced binding's, "
        "then the config, then codex. An existing session keeps its own.",
    ),
]
NewSession = Annotated[
    bool,
    typer.Option(
        "--new-session", help="Replace an archived binding, or retry a launch that left no session."
    ),
]
Attach = Annotated[
    bool | None,
    typer.Option(
        "--attach/--no-attach",
        help="Attach after printing state (default: the config's aoe.attach, else stay here).",
        show_default=False,
    ),
]


@app.command("open")
def open_workspace(
    project: Project = None,
    workspace: Workspace = False,
    root: Root = Path("."),
    profile: Profile = None,
    agent: Agent = None,
    new_session: NewSession = False,
    attach: Attach = None,
) -> None:
    """Open or recover one research session, with checked context delivery."""
    project = _select(project, workspace)
    open_scope(root, project, profile, agent, new_session=new_session, attach=attach)


def open_scope(
    root: Path,
    project: str | None,
    profile: str | None,
    agent: str | None,
    *,
    new_session: bool = False,
    attach: bool | None = None,
) -> None:
    """Shared by ``aoe open`` and ``toulmin open``: flags first, then preferences."""
    if agent is not None and agent not in AGENTS:
        raise typer.BadParameter("expected codex or claude", param_hint="--agent")
    fallback = default_agent()
    _execute(
        root,
        project,
        profile,
        lambda service: service.open(agent, new_session=new_session, fallback_agent=fallback),
        attach=default_attach() if attach is None else attach,
        recovery_on_error=True,
    )


@app.command("bind")
def bind_workspace(
    project: Project = None,
    workspace: Workspace = False,
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
    project = _select(project, workspace)
    _execute(
        root,
        project,
        profile,
        lambda service: service.bind(session, replace_existing=replace_existing),
        bound_only=True,
    )


@app.command("status")
def workspace_status(
    project: Project = None,
    workspace: Workspace = False,
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
    project = _select(project, workspace)
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
    project: Project = None,
    workspace: Workspace = False,
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
    project = _select(project, workspace)
    _execute(
        root,
        project,
        profile,
        lambda service: service.refresh(resend=resend),
        recovery_on_error=True,
    )


@app.command("ack")
def acknowledge_context(
    token: Annotated[str, typer.Option("--token", help="Receipt token from the context file.")],
    project: Project = None,
    workspace: Workspace = False,
    root: Root = Path("."),
    profile: Profile = None,
) -> None:
    """Record a context-read receipt; this does not approve research changes."""
    project = _select(project, workspace)
    _execute(root, project, profile, lambda service: service.acknowledge(token), offline=True)


@app.command("handoff")
def workspace_handoff(
    project: Annotated[
        str | None,
        typer.Argument(help="Project name; omit (or pass --workspace) for the workspace."),
    ] = None,
    root: Root = Path("."),
    workspace: Annotated[
        bool, typer.Option("--workspace", help="Select the workspace scope explicitly.")
    ] = False,
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
        str | None,
        typer.Option("--confirmed-by", help="Researcher; defaults to $TOULMIN_ACTOR, then config."),
    ] = None,
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Confirm this handoff application.")
    ] = False,
) -> None:
    """Draft or explicitly apply a handoff; window exit never confirms or closes a session."""
    if project is not None and workspace:
        raise typer.BadParameter("give PROJECT or --workspace, not both", param_hint="project")
    if apply_path is not None and input_path is not None:
        raise typer.BadParameter("--apply and --input are mutually exclusive")
    if apply_path is None and (confirm or actor is not None):
        raise typer.BadParameter("--confirm/--confirmed-by require --apply")
    if project is None:
        _workspace_handoff(root, input_path, apply_path, actor, confirm)
        return
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="project") from error
    if apply_path is not None:
        actor = resolve_actor(actor)
        if actor is None:
            raise typer.BadParameter(f"--apply requires an actor: {ACTOR_HINT}")
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


def _workspace_handoff(
    root: Path, input_path: str | None, apply_path: str | None, actor: str | None, confirm: bool
) -> None:
    """Workspace scope: a sealed draft, a preview, or a confirmed session record."""
    if input_path is None and apply_path is None:
        raise typer.BadParameter("the workspace handoff needs --input SUMMARY or --apply DRAFT")
    if apply_path is not None and actor is not None and not confirm:
        typer.echo(
            "Error: not applied; confirmation missing. Review the preview, then rerun with "
            "--confirm.",
            err=True,
        )
        raise typer.Exit(1)
    if confirm:
        actor = resolve_actor(actor)
        if actor is None:
            raise typer.BadParameter(f"--confirm requires an actor: {ACTOR_HINT}")
    root_text = str(root.absolute())
    try:
        if input_path is not None:
            outcome = workspace_handoffs.draft(root, input_path)
        else:
            assert apply_path is not None
            outcome = workspace_handoffs.apply(root, apply_path, actor, confirmed=confirm)
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Root: {root_text}")
    typer.echo("Scope: Workspace")
    if outcome.status in {"applied", "recovered", "replayed"}:
        handoff_result(outcome)
        return
    handoff_preview(outcome, root)


def handoff_result(outcome: workspace_handoffs.HandoffOutcome) -> None:
    loaded = outcome.loaded
    typer.echo(f"Draft: {loaded.path}")
    typer.echo(f"Record: {outcome.record}")
    if outcome.status == "replayed":
        typer.echo("Already applied; nothing written.")
    if outcome.status == "recovered":
        typer.echo("Interrupted application finished from the journal.")
    for note in outcome.problems:
        typer.echo(f"Note: {note}")
    typer.echo(f"Recorded next step: {loaded.draft.next_step}")
    typer.echo("Changed: WORKSPACE.md next_step and last_handoff only")


def handoff_preview(
    outcome: workspace_handoffs.HandoffOutcome, root: Path, *, commands: bool = True
) -> None:
    """The sealed draft as apply will check it; ``commands`` adds the apply line."""
    loaded = outcome.loaded
    root_text = str(root.absolute())
    if outcome.status == "incomplete":
        typer.echo("State: publication incomplete")
    typer.echo(f"Draft: {loaded.path}")
    typer.echo(f"Seal: {loaded.seal[:16]}")
    typer.echo(f"Base WORKSPACE.md: {loaded.draft.base_workspace_sha256[:16]}")
    changes = ", ".join(loaded.draft.confirmed_changes) or "none cited"
    typer.echo(f"Confirmed changes: {changes}")
    typer.echo(f"Next step: {loaded.draft.next_step}")
    typer.echo("")
    typer.echo(loaded.body.rstrip("\n"))
    typer.echo("")
    for problem in outcome.problems:
        typer.echo(f"Refused now: {problem}")
    typer.echo(
        "Confirming records this summary only: no direction, resource or project changes, "
        "and pending ideas stay pending."
    )
    if not commands:
        return
    typer.echo(
        "Apply: "
        + " ".join(
            shlex.quote(word)
            for word in (
                "toulmin", "aoe", "handoff", "--workspace", "--root", root_text,
                "--apply", loaded.path, "--confirmed-by", "ACTOR", "--confirm",
            )
        )
    )  # fmt: skip
    if outcome.status != "drafted":
        typer.echo("Preview only; nothing written.")
