"""Installed CLI entry point."""

import re
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from toulmin.cli import decide
from toulmin.cli.aoe import app as aoe_app
from toulmin.cli.build import app as build_app
from toulmin.cli.commit import commit_command
from toulmin.cli.decide import decide_command
from toulmin.cli.entry import config_app, open_research, projects_command
from toulmin.cli.initialize import initialize, initialize_workspace, workspace_setup
from toulmin.cli.migration import app as migration_app
from toulmin.cli.onboarding import onboard_command, overview_command, source_app
from toulmin.cli.project import app as project_app
from toulmin.cli.registry import note as register_workspace
from toulmin.cli.settings import ACTOR_HINT, ACTOR_VARIABLE, resolve_actor, root_option
from toulmin.cli.task import app as task_app
from toulmin.cli.terminal import colour, sayer
from toulmin.cli.workspace import app as workspace_app
from toulmin.cli.workspaces import app as workspaces_app
from toulmin.core.identifiers import ObjectKind, validate_project_name
from toulmin.protocols.drafting import ProposalOptions, write_draft, write_proposal_draft
from toulmin.protocols.handoff import apply_handoff, draft_handoff
from toulmin.protocols.inputs import resolve_inputs
from toulmin.protocols.intake import create_object
from toulmin.protocols.review_intake import intake_review
from toulmin.protocols.ruling import apply_ruling
from toulmin.protocols.status import project_status, upcoming
from toulmin.protocols.workspace_state import (
    CREATION_INCOMPLETE,
    RootState,
    project_hint,
    workspace_status,
)

app = typer.Typer(
    help="Toulmin research workbench. Initialize, create objects and inspect project state.",
    add_completion=False,
    no_args_is_help=True,
)
app.add_typer(aoe_app, name="aoe")
app.add_typer(build_app, name="build")
app.add_typer(migration_app, name="migration")
app.add_typer(task_app, name="task")
app.add_typer(source_app, name="source")
app.command("onboard")(onboard_command)
app.command("overview")(overview_command)
app.add_typer(workspace_app, name="workspace")
app.add_typer(project_app, name="project")
app.add_typer(config_app, name="config")
app.add_typer(workspaces_app, name="workspaces")
app.command("commit")(commit_command)
app.command("open")(open_research)
app.command("projects")(projects_command)
app.command("decide")(decide_command)


@app.command("tui")
def interactive_workspace(
    root: Annotated[Path | None, typer.Option("--root", help="Research workbench root.")] = None,
    project: Annotated[str | None, typer.Option("--project", help="Project to open.")] = None,
) -> None:
    """Open the interactive terminal research workspace (requires the tui extra)."""
    if project is not None:
        try:
            validate_project_name(project)
        except ValueError as error:
            raise typer.BadParameter(str(error), param_hint="--project") from error
        if root is None:
            raise typer.BadParameter("--project requires --root")
    try:
        from toulmin.tui.app import launch
    except ModuleNotFoundError as error:
        if error.name != "textual" and not (error.name or "").startswith("textual."):
            raise
        typer.echo(
            "The terminal UI requires Textual. Install the tui extra "
            "(from a checkout: uv sync --locked --extra tui).",
            err=True,
        )
        raise typer.Exit(1) from error
    launch(root=root, project=project)


@app.command("native")
def native_workspace(
    project: Annotated[str, typer.Argument(help="Existing research project slug.")],
    root: Annotated[Path, root_option("Workbench root.")] = Path("."),
    agent: Annotated[str, typer.Option("--agent", help="Native CLI: codex or claude.")] = "codex",
    session: Annotated[
        str | None, typer.Option("--session", help="Inspect a saved native session; no model call.")
    ] = None,
    recover: Annotated[
        bool,
        typer.Option("--recover", help="Explicitly close an interrupted --session without retry."),
    ] = False,
    actor: Annotated[
        str | None,
        typer.Option("--actor", help="Researcher attribution; defaults to current user."),
    ] = None,
) -> None:
    """Discuss in a native CLI beside the project board, then confirm an archived Brief."""
    try:
        from toulmin.application.native import launch_native

        view = launch_native(root, project, agent, session=session, recover=recover, actor=actor)
    except ModuleNotFoundError as error:
        if error.name != "textual" and not (error.name or "").startswith("textual."):
            raise
        typer.echo("Install the tui extra: uv sync --locked --extra tui", err=True)
        raise typer.Exit(1) from error
    except (OSError, ValueError, RuntimeError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Native session: {view.id} | Run: {view.run or 'not archived'}")
    typer.echo(f"Archive: {view.archive}")


def confirmer(value: str | None) -> str | None:
    """Explicit --confirmed-by wins; otherwise the operator's local default, if any."""
    return resolve_actor(value)


def display(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root.absolute()))
    except ValueError:
        return str(path)


@app.callback(invoke_without_command=True)
def main(
    version: Annotated[bool, typer.Option("--version", help="Show the installed version.")] = False,
) -> None:
    if version:
        from importlib.metadata import version as installed_version

        typer.echo(installed_version("toulmin"))
        raise typer.Exit()


@app.command("init")
def init_workbench(
    root: Annotated[Path, typer.Argument(help="Directory for the research workbench.")],
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="Legacy route: also create a template project (refused on workspace roots).",
        ),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option("--name", help="Workspace display name (default: the directory name)."),
    ] = None,
) -> None:
    """Create a project-free research workspace without overwriting existing content.

    No child project, research direction, object or model session is created.
    """
    if project is not None and name is not None:
        raise typer.BadParameter(
            "applies to workspace initialization only, not --project", param_hint="--name"
        )
    if project is not None:
        try:
            validate_project_name(project)
        except ValueError as error:
            raise typer.BadParameter(str(error), param_hint="--project") from error
        try:
            created = initialize(root, project)
        except (OSError, ValueError, RuntimeError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
        typer.echo(
            f"Workbench: {root.absolute()} | project: {project} | created entries: {created}"
        )
        return
    try:
        result = initialize_workspace(root, name)
    except (OSError, ValueError, RuntimeError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    register_workspace(result.root)
    for remnant in result.remnants:
        typer.echo(f"Notice: {remnant}: interrupted initialization remnant (left in place)")
    if result.existing:
        typer.echo(
            f"Workspace already initialized: {result.root} | name: {result.name} | nothing written"
        )
    else:
        typer.echo(
            f"Workspace: {result.root} | name: {result.name} | created entries: {result.created}\n"
            "Scope: Workspace | direction: none confirmed | projects: none | "
            "no model session started"
        )
    typer.echo(f"Next: toulmin status --root {result.root}")


class DraftKind(StrEnum):
    """Object and Run drafts (``toulmin new``), and since R1 the proposal kinds of decide."""

    CLAIM = "claim"
    EVIDENCE = "evidence"
    OBJECTION = "objection"
    DECISION = "decision"
    EXPLORATION = "exploration"
    SPEC = "spec"
    RUN = "run"
    RULING = "ruling"
    INTAKE = "intake"
    REVIEW = "review"
    BRIEF = "brief"
    STAGE = "stage"
    BUILD = "build"
    TASK = "task"
    OVERVIEW = "overview"


@app.command("draft")
def draft_object(
    kind: Annotated[DraftKind, typer.Argument(help="Object, Run or proposal type.")],
    project: Annotated[
        str | None, typer.Argument(help="Project name; omit for workspace overview/task.")
    ] = None,
    root: Annotated[Path, root_option("Research workbench root.")] = Path("."),
    name: Annotated[
        str | None, typer.Option("--name", help="Optional filename suffix, e.g. tail-cause.")
    ] = None,
    role: Annotated[
        str | None,
        typer.Option("--role", help="Run only: fill role and input_files from this role."),
    ] = None,
    claims: Annotated[
        list[str] | None,
        typer.Option(
            "--claim",
            help="Run with --role: give only these Claims. review: the Claims to review. "
            "May be repeated or comma-separated.",
        ),
    ] = None,
    objects: Annotated[
        list[str] | None,
        typer.Option(
            "--object",
            help="ruling: the object to rule; several (repeated or comma-separated) give one "
            "ruling for all of them.",
        ),
    ] = None,
    status: Annotated[
        str | None, typer.Option("--status", help="ruling: the proposed status.")
    ] = None,
    decision: Annotated[
        str | None,
        typer.Option(
            "--decision", help="ruling, stage: D-NNN or the decision-…md proposal beside it."
        ),
    ] = None,
    run: Annotated[
        str | None,
        typer.Option("--run", help="intake: the review Run (R-NNN) or its output path."),
    ] = None,
    sections: Annotated[
        list[str] | None,
        typer.Option("--section", help="brief: a brief.md section to change; may be repeated."),
    ] = None,
    personas: Annotated[
        list[str] | None, typer.Option("--persona", help="review: personas (default: config).")
    ] = None,
    models: Annotated[
        list[str] | None, typer.Option("--model", help="review: models (default: config).")
    ] = None,
    profile: Annotated[
        str | None, typer.Option("--profile", help="review: named review profile.")
    ] = None,
    synthesizer: Annotated[
        str | None, typer.Option("--synthesizer", help="review: explicit synthesis model alias.")
    ] = None,
    spec: Annotated[str | None, typer.Option("--spec", help="build: Spec ID (S-NNN).")] = None,
    repo: Annotated[
        Path | None, typer.Option("--repo", help="build: absolute code repository path.")
    ] = None,
    to: Annotated[
        str | None, typer.Option("--to", help="stage: the stage to enter (default: the next).")
    ] = None,
    workspace: Annotated[
        bool, typer.Option("--workspace", help="Workspace overview or task draft.")
    ] = False,
    source: Annotated[
        str | None, typer.Option("--source", help="Explicit source for a scoped task.")
    ] = None,
) -> None:
    """Draft for PROJECT, or explicit --workspace overview/task.

    Scoped v2 tasks go directly to runs/proposals/; other drafts go to runs/drafts/.
    Proposal kinds (ruling, intake, review, brief, stage) are prefilled from the files: current
    statuses, undecided review draft labels, the brief's digest and sections, the stage.
    """
    if workspace and project is not None:
        raise typer.BadParameter("give PROJECT or --workspace")
    if project is None and not workspace:
        raise typer.BadParameter("give PROJECT or explicit --workspace")
    if (profile is not None or synthesizer is not None) and kind != DraftKind.REVIEW:
        raise typer.BadParameter("--profile/--synthesizer apply only to review drafts")
    if kind == DraftKind.REVIEW and (profile is not None or synthesizer is not None):
        from toulmin.adapters.config import load_config as load_review_config
        from toulmin.adapters.review_profiles import select

        try:
            review_config = load_review_config(root)
            selection = select(
                review_config, _comma_list(personas), _comma_list(models), profile, synthesizer
            )
            for alias in [
                *selection.models,
                *([selection.synthesizer] if selection.synthesizer else []),
            ]:
                if alias not in review_config.available:
                    raise ValueError(f"model {alias!r} not configured")
        except (OSError, ValueError) as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
    if kind == DraftKind.TASK and project is not None and source is None:
        from toulmin.core.sources import read_source_catalog

        if read_source_catalog(root).schema_version == 2 and (root / "sources.toml").exists():
            raise typer.BadParameter("scoped task draft requires explicit --source ID")
    if project is None or (kind == DraftKind.TASK and source is not None):
        if kind == DraftKind.OVERVIEW and project is None:
            from toulmin.protocols.overview_draft import write_workspace_overview_draft

            path = write_workspace_overview_draft(root)
            typer.echo(display(path, root))
            typer.echo(
                "Fill then propose overview --workspace --input "
                "FILE --source ID --rationale TEXT --root ROOT"
            )
            return
        if kind == DraftKind.TASK:
            if source is None or repo is not None:
                raise typer.BadParameter("scoped task requires --source ID, without --repo")
            from toulmin.application.scoped_tasks import write_draft as write_scoped_draft
            from toulmin.core.scope import Scope

            try:
                path = write_scoped_draft(root, Scope(project), source, name=name)
            except (OSError, ValueError) as error:
                typer.echo(f"Error: {error}", err=True)
                raise typer.Exit(1) from error
            typer.echo(display(path, root))
            scope_option = "--workspace" if project is None else f"--project {project}"
            typer.echo(
                "Fill Goal/Scope/checks/protection/budget; task preview "
                f"FILE {scope_option}, then researcher decide {scope_option}"
            )
            return
        raise typer.BadParameter(
            "workspace drafts are overview/task only; scientific drafts require PROJECT"
        )
    if source is not None:
        raise typer.BadParameter("--source is for scoped task drafts only")
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="project") from error
    proposal = kind.value not in {item.value for item in ObjectKind}
    try:
        if kind == DraftKind.OVERVIEW:
            from toulmin.protocols.overview_draft import write_overview_draft

            path = write_overview_draft(root, project)
        elif kind == DraftKind.TASK:
            from toulmin.adapters.chief import load_config
            from toulmin.application.sources import resolve_working_source
            from toulmin.protocols.engineering_tasks import write_task_draft

            config = load_config(root)
            working_source = resolve_working_source(root, project) if repo is None else None
            path = write_task_draft(
                root,
                project,
                name=name,
                repo=str(repo) if repo else None if working_source else config.repos.get(project),
                source=working_source.source_id if working_source else None,
                tool=config.tool,
                budget=config.budget,
                trust=config.trust,
            )
        elif proposal:
            if role is not None:
                raise ValueError(f"{kind.value}: role: only a Run draft takes a role's inputs")
            build_defaults = None
            build_repo = str(repo) if repo is not None else None
            if kind == DraftKind.BUILD:
                from toulmin.adapters.chief import load_config

                config = load_config(root)
                build_repo = build_repo or config.repos.get(project)
                build_defaults = {
                    "tool": config.tool,
                    "budget": config.budget,
                    "trust": config.trust,
                }
            options = ProposalOptions(
                objects=tuple(_comma_list(objects) or ()),
                status=status,
                decision=decision,
                run=run,
                sections=tuple(sections or ()),
                personas=tuple(_comma_list(personas) or ()),
                models=tuple(_comma_list(models) or ()),
                profile=profile,
                synthesizer=synthesizer,
                claims=tuple(_comma_list(claims) or ()),
                stage=to,
                spec=spec,
                repo=build_repo,
                build_defaults=build_defaults,
            )
            path = write_proposal_draft(root, project, kind.value, options, name)
        else:
            extra = [
                flag
                for flag, value in (
                    ("--object", objects), ("--status", status), ("--decision", decision),
                    ("--run", run), ("--section", sections), ("--persona", personas),
                    ("--model", models), ("--to", to), ("--spec", spec), ("--repo", repo),
                )
                if value
            ]  # fmt: skip
            if extra:
                raise ValueError(f"{kind.value}: {extra[0]}: only for proposal drafts")
            path = write_draft(
                root,
                project,
                ObjectKind(kind.value),
                name,
                confirmer(None),
                role=role,
                claims=_comma_list(claims),
            )
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    relative = display(path, root)
    typer.echo(relative)
    location = "" if root == Path(".") else f" --root {root}"
    new = f"toulmin new {kind.value} {project}{location} --input {relative} --confirm"
    if kind == DraftKind.OVERVIEW:
        typer.echo(
            f'Fill the draft, then: toulmin overview {project} "Reason for update"'
            f"{location} --input {relative}",
            err=True,
        )
    elif kind == DraftKind.RUN:
        typer.echo(f"Fill every <fill: ...> value, then: {new}", err=True)
    elif proposal:
        typer.echo(
            "Fill every <fill: ...> value (delete unused optional lines), then move it (name "
            f"unchanged) to projects/{project}/runs/proposals/ for `toulmin decide`.",
            err=True,
        )
    else:
        typer.echo(
            "Fill every <fill: ...> value, then move it (name unchanged) to "
            f"projects/{project}/runs/proposals/ for `toulmin decide`, or: {new}",
            err=True,
        )


@app.command("inputs")
def role_inputs(
    project: Annotated[str, typer.Argument(help="Project name.")],
    role: Annotated[str, typer.Argument(help="Role with an input manifest, e.g. reviewer.")],
    root: Annotated[Path, root_option("Research workbench root.")] = Path("."),
    claims: Annotated[
        list[str] | None,
        typer.Option("--claim", help="Give only these Claims; may be repeated."),
    ] = None,
) -> None:
    """List the files an independent session of a role receives, one per line."""
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="project") from error
    try:
        result = resolve_inputs(root, project, role, claims)
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    for path in result.files:
        typer.echo(path)
    if result.superseded:
        typer.echo(f"Left out superseded Claims: {', '.join(result.superseded)}", err=True)


@app.command("new")
def new_object(
    kind: Annotated[ObjectKind, typer.Argument(help="Object type.")],
    project: Annotated[str, typer.Argument(help="Project name.")],
    input_path: Annotated[
        str,
        typer.Option(
            "--input", help="Markdown draft path, relative to --root or absolute inside it."
        ),
    ],
    actor: Annotated[
        str | None,
        typer.Option(
            "--confirmed-by",
            help=f"Researcher authorizing intake. Defaults to ${ACTOR_VARIABLE}, then config.",
        ),
    ] = None,
    root: Annotated[Path, root_option("Research workbench root.")] = Path("."),
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Explicitly confirm this draft's intake.")
    ] = False,
) -> None:
    """Validate and create one object from a draft with researcher confirmation."""
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="project") from error
    actor = confirmer(actor)
    if actor is None:
        raise typer.BadParameter(f"required: {ACTOR_HINT}", param_hint="--confirmed-by")
    try:
        path = create_object(root, project, kind, input_path, actor, confirm)
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(display(path, root))


@app.command("intake")
def intake_drafts(
    project: Annotated[str, typer.Argument(help="Project name.")],
    output: Annotated[
        str, typer.Argument(help="Archived raw review output containing a draft block.")
    ],
    root: Annotated[Path, root_option("Research workbench root.")] = Path("."),
    take: Annotated[
        list[str] | None,
        typer.Option(
            "--take", help="LABEL or LABEL:SEVERITY to take in; comma lists and repeats allowed."
        ),
    ] = None,
    reject: Annotated[
        list[str] | None, typer.Option("--reject", help="LABEL=REASON; may be repeated.")
    ] = None,
    partly: Annotated[
        list[str] | None,
        typer.Option("--partly", help="LABEL=O-NNN for an Objection written by hand."),
    ] = None,
    duplicate: Annotated[
        list[str] | None,
        typer.Option(
            "--duplicate", help="LABEL=O-NNN for an existing Objection this draft repeats."
        ),
    ] = None,
    duplicate_reason: Annotated[
        list[str] | None,
        typer.Option("--duplicate-reason", help="Optional LABEL=REASON for a duplicate choice."),
    ] = None,
    actor: Annotated[
        str | None,
        typer.Option(
            "--confirmed-by",
            help=f"Researcher choosing these outcomes. Defaults to ${ACTOR_VARIABLE}, then config.",
        ),
    ] = None,
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Explicitly confirm these outcomes.")
    ] = False,
) -> None:
    """Take chosen review drafts in as Objections and record every outcome."""
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="project") from error
    actor = confirmer(actor)
    if actor is None:
        raise typer.BadParameter(f"required: {ACTOR_HINT}", param_hint="--confirmed-by")
    chosen: dict[str, str | None] = {}
    for item in ",".join(take or []).split(","):
        if item.strip():
            label, _, severity = item.strip().partition(":")
            chosen[label] = severity or None

    def pairs(values: list[str] | None, hint: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for value in values or []:
            label, separator, rest = value.partition("=")
            if not separator or not label.strip() or not rest.strip():
                raise typer.BadParameter("expected LABEL=VALUE", param_hint=hint)
            result[label.strip()] = rest.strip()
        return result

    try:
        result = intake_review(
            root,
            project,
            output,
            actor,
            confirm,
            chosen,
            pairs(reject, "--reject"),
            pairs(partly, "--partly"),
            duplicate=pairs(duplicate, "--duplicate"),
            duplicate_reasons=pairs(duplicate_reason, "--duplicate-reason"),
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(display(result.record, root))
    for line in result.lines:
        target = (
            (" of " if line.outcome.endswith("duplicate") else " as ") + line.object_id
            if line.object_id
            else ""
        )
        typer.echo(f"{line.label}: {line.outcome}{target} ({result.run})")


def _comma_list(values: list[str] | None) -> list[str] | None:
    """Join repeated and comma-separated option values in order (repeats once kept the last)."""
    if values is None:
        return None
    return [item.strip() for value in values for item in value.split(",") if item.strip()]


@app.command("review")
def review_project(
    project: Annotated[str, typer.Argument(help="Project name.")],
    root: Annotated[Path, root_option("Research workbench root.")] = Path("."),
    personas: Annotated[
        list[str] | None,
        typer.Option(
            "--personas",
            help="Critique roles, comma-separated or repeated; default from models.toml.",
        ),
    ] = None,
    models: Annotated[
        list[str] | None,
        typer.Option(
            "--models",
            help="Model names from models.toml, comma-separated or repeated; default from it.",
        ),
    ] = None,
    claims: Annotated[
        list[str] | None,
        typer.Option("--claim", help="Review only these Claims; may be repeated."),
    ] = None,
    profile: Annotated[
        str | None, typer.Option("--profile", help="Named profile from models.toml.")
    ] = None,
    synthesizer: Annotated[
        str | None,
        typer.Option("--synthesizer", help="Explicit synthesis model alias; includes synthesis."),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the planned sessions; run nothing.")
    ] = False,
    actor: Annotated[
        str | None,
        typer.Option(
            "--confirmed-by",
            help=f"Researcher starting this round. Defaults to ${ACTOR_VARIABLE}, then config.",
        ),
    ] = None,
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Confirm starting the sessions (uses quota).")
    ] = False,
) -> None:
    """Run read-only reviews for every persona x model pair and record each as a Run."""
    from toulmin.adapters.review import run_round

    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="project") from error
    actor = confirmer(actor)
    if actor is None and not dry_run:
        raise typer.BadParameter(f"required: {ACTOR_HINT}", param_hint="--confirmed-by")

    try:
        failed = run_round(
            root,
            project,
            _comma_list(personas),
            _comma_list(models),
            claims,
            actor or "",
            dry_run=dry_run,
            confirmed=confirm,
            echo=typer.echo,
            profile=profile,
            synthesizer=synthesizer,
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    if failed:
        raise typer.Exit(1)


@app.command("synthesize")
def synthesize_runs(
    project: Annotated[str, typer.Argument(help="Project name.")],
    runs: Annotated[
        list[str], typer.Argument(help="Completed review or crossval Runs, e.g. R-002.")
    ],
    root: Annotated[Path, root_option("Research workbench root.")] = Path("."),
    model: Annotated[
        str | None,
        typer.Option("--model", help="Override the rotated synthesizer model ([models] name)."),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the planned session; run nothing.")
    ] = False,
    actor: Annotated[
        str | None,
        typer.Option(
            "--confirmed-by",
            help=f"Researcher starting this synthesis. Defaults to ${ACTOR_VARIABLE}, then config.",
        ),
    ] = None,
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Confirm starting the session (uses quota).")
    ] = False,
) -> None:
    """Group the drafts of several archived outputs into disagreements, agreements, singletons."""
    from toulmin.adapters.review import run_synthesis

    actor = _round_actor(project, actor, dry_run)
    try:
        failed = run_synthesis(
            root, project, runs, model, actor, dry_run=dry_run, confirmed=confirm, echo=typer.echo
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    if failed:
        raise typer.Exit(1)


@app.command("crossval")
def crossval_question(
    project: Annotated[str, typer.Argument(help="Project name.")],
    question: Annotated[
        str, typer.Argument(help="Question file in the project's runs/drafts/, root-relative.")
    ],
    root: Annotated[Path, root_option("Research workbench root.")] = Path("."),
    models: Annotated[
        list[str] | None,
        typer.Option(
            "--models",
            help="Model names from models.toml, comma-separated or repeated; default from it.",
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--synthesizer", help="Override the rotated synthesizer model."),
    ] = None,
    synthesize: Annotated[
        bool, typer.Option("--synthesis/--no-synthesis", help="Synthesize the answers afterwards.")
    ] = True,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the planned sessions; run nothing.")
    ] = False,
    actor: Annotated[
        str | None,
        typer.Option(
            "--confirmed-by",
            help=f"Researcher starting this round. Defaults to ${ACTOR_VARIABLE}, then config.",
        ),
    ] = None,
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Confirm starting the sessions (uses quota).")
    ] = False,
) -> None:
    """Ask every model the same question independently, then synthesize the answers."""
    from toulmin.adapters.review import run_crossval

    actor = _round_actor(project, actor, dry_run)
    chosen = _comma_list(models)
    try:
        failed = run_crossval(
            root,
            project,
            question,
            chosen,
            model,
            synthesize,
            actor,
            dry_run=dry_run,
            confirmed=confirm,
            echo=typer.echo,
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    if failed:
        raise typer.Exit(1)


def _round_actor(project: str, actor: str | None, dry_run: bool) -> str:
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="project") from error
    actor = confirmer(actor)
    if actor is None and not dry_run:
        raise typer.BadParameter(f"required: {ACTOR_HINT}", param_hint="--confirmed-by")
    return actor or ""


@app.command("rule")
def rule_object(
    project: Annotated[str, typer.Argument(help="Project name.")],
    object_id: Annotated[str, typer.Argument(help="Object ID in this project, e.g. O-001.")],
    root: Annotated[Path, root_option("Research workbench root.")] = Path("."),
    status: Annotated[
        str | None, typer.Option("--status", help="New stored status chosen by the researcher.")
    ] = None,
    decision: Annotated[
        str | None,
        typer.Option(
            "--decision", help="Active Decision naming this object; required for --status."
        ),
    ] = None,
    response: Annotated[
        str | None, typer.Option("--response", help="File whose text is added to Response.")
    ] = None,
    ruling: Annotated[
        str | None, typer.Option("--ruling", help="File whose text is added to Ruling.")
    ] = None,
    section: Annotated[
        list[str] | None,
        typer.Option("--section", help="NAME=FILE for Invalidation or Rationale; may be repeated."),
    ] = None,
    superseded_by: Annotated[
        str | None,
        typer.Option("--superseded-by", help="Successor Claim/Decision for status superseded."),
    ] = None,
    adopted_as: Annotated[
        str | None, typer.Option("--adopted-as", help="Claim an adopted Exploration became.")
    ] = None,
    evidence: Annotated[
        list[str] | None,
        typer.Option("--evidence", help="Evidence to append to a Spec; may be repeated."),
    ] = None,
    actor: Annotated[
        str | None,
        typer.Option(
            "--confirmed-by",
            help=f"Researcher making this ruling. Defaults to ${ACTOR_VARIABLE}, then config.",
        ),
    ] = None,
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Explicitly confirm this ruling.")
    ] = False,
) -> None:
    """Record a researcher's status change, Response or Ruling on one object."""
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="project") from error
    actor = confirmer(actor)
    if actor is None:
        raise typer.BadParameter(f"required: {ACTOR_HINT}", param_hint="--confirmed-by")
    texts: dict[str, str] = {}
    pairs: list[tuple[str, str | None]] = [("Response", response), ("Ruling", ruling)]
    for item in section or []:
        label, separator, path = item.partition("=")
        if not separator or not label.strip() or not path:
            raise typer.BadParameter("expected NAME=FILE", param_hint="--section")
        pairs.append((label.strip(), path))
    for name, source in pairs:
        if source is None:
            continue
        if name in texts:
            raise typer.BadParameter(f"{name} given twice", param_hint="--section")
        texts[name] = source
    try:
        links: dict[str, str | list[str]] = {}
        if superseded_by is not None:
            links["superseded_by"] = superseded_by
        if adopted_as is not None:
            links["adopted_as"] = adopted_as
        if evidence:
            links["evidence"] = list(evidence)
        result = apply_ruling(
            root, project, object_id, actor, confirm, status, decision, texts, links
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(display(result.path, root))
    change = (
        f"{result.previous_status} -> {result.status}"
        if result.status != result.previous_status
        else f"status unchanged ({result.status})"
    )
    added = f"; added to {', '.join(result.sections)}" if result.sections else ""
    linked = f"; linked {', '.join(result.links)}" if result.links else ""
    via = f" by {result.decision}" if result.decision else ""
    typer.echo(f"{result.object_id}: {change}{via}{added}{linked}")
    try:
        report = project_status(root, project)
    except (OSError, ValueError):
        return
    # Show condition notices for the ruled object and the Claim it targets, if any.
    subjects = {result.object_id} | ({result.target} if result.target else set())
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, sorted(subjects))) + r")\b")
    for notice in report.notices:
        if pattern.search(notice):
            typer.echo(f"Notice: {notice}")


@app.command("calibration")
def calibration_report(
    root: Annotated[Path, root_option("Research workbench root.")] = Path("."),
    project: Annotated[
        str | None, typer.Option("--project", help="Count one project only; default: all.")
    ] = None,
    write: Annotated[
        bool,
        typer.Option(
            "--write", help="Also (re)write the report under global/calibration/ (regenerable)."
        ),
    ] = False,
) -> None:
    """Adoption of review drafts per model, role and operation, derived from files (C5)."""
    from toulmin.core.atomic import write_atomic
    from toulmin.core.repository import Repository
    from toulmin.protocols.calibration import calibration, render

    if project is not None:
        try:
            validate_project_name(project)
        except ValueError as error:
            raise typer.BadParameter(str(error), param_hint="--project") from error
    try:
        text = render(calibration(root, project), project)
        if write:
            repository = Repository(root)
            repository.path("global/calibration", "directory")
            name = f"calibration-{project}.md" if project else "calibration.md"
            relative = f"global/calibration/{name}"
            destination = repository.path(relative)
            if destination.exists() and not destination.is_file():
                raise ValueError(f"{relative}: expected a regular file")
            write_atomic(destination, text.encode(), replace=destination.exists())
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(text, nl=False)
    if write:
        typer.echo(f"\nWritten: {relative} (regenerable; derived from files only)")


@app.command("map")
def show_map(
    project: Annotated[
        str | None,
        typer.Argument(
            help="Child project; omitted: the project of the current directory, else the workspace."
        ),
    ] = None,
    root: Annotated[Path, root_option("Research workbench root.")] = Path("."),
    workspace: Annotated[
        bool, typer.Option("--workspace", help="Workspace; suppress records-child inference.")
    ] = False,
    watch: Annotated[
        bool, typer.Option("--watch", help="Redraw whenever project files change; Ctrl-C stops.")
    ] = False,
    interval: Annotated[
        float, typer.Option("--interval", min=0.2, help="Seconds between checks with --watch.")
    ] = 2.0,
    claim: Annotated[
        str | None, typer.Option("--claim", help="Show only this Claim's subtree.")
    ] = None,
    full: Annotated[
        bool,
        typer.Option("--full", help="Gates, the whole argument tree and sources, not the card."),
    ] = False,
    provenance: Annotated[
        bool,
        typer.Option(
            "--provenance", help="With --full: name the review that raised each Objection."
        ),
    ] = False,
    ascii_only: Annotated[
        bool,
        typer.Option("--ascii", help="ASCII marks only (default when the terminal is not UTF-8)."),
    ] = False,
) -> None:
    """Show the project card: current answer, doubts, what waits and what is next (UX3).

    --full shows the earlier view (gates, the whole argument tree, sources); --claim shows one
    Claim's subtree. Everything is derived from files only.
    """
    import time

    from toulmin.application.build import project_map
    from toulmin.cli import research_map as view
    from toulmin.cli.entry import _child

    if workspace and project is not None:
        raise typer.BadParameter("give PROJECT or --workspace")
    if project is None and not workspace:
        try:
            project = _child(Path.cwd().resolve(), root.resolve())
        except OSError:
            project = None
    if project is not None:
        try:
            validate_project_name(project)
        except ValueError as error:
            raise typer.BadParameter(str(error), param_hint="project") from error
    try:
        chosen = view.validate_claim(claim)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="--claim") from error
    glyphs = view.Glyphs(ascii_only or view.ascii_default())

    def draw(refreshed: str | None = None) -> tuple[str, bool]:
        width = view.terminal_width()
        try:
            if project is None:
                return view.render_workspace(root, width, glyphs, refreshed), True
            report = project_map(root, project)
            waiting = [item for item in decide.inventory(root).items if item.project == project]
            if full or chosen is not None:
                text = view.render_project(
                    report, waiting, width, glyphs, refreshed, chosen, provenance
                )
            else:
                from toulmin.protocols.project_card import project_card

                card = project_card(root, project, report)
                text = view.render_card(card, waiting, width, glyphs, refreshed)
            return text, not report.errors
        except (OSError, ValueError) as error:
            return f"Error: {error}\n", False

    if not watch:
        text, healthy = draw()
        typer.echo(colour(text), nl=False)
        if not healthy:
            raise typer.Exit(1)
        return
    folder = root if project is None else root / "projects" / project
    try:
        view.watch(
            lambda: draw(time.strftime("%H:%M:%S"))[0],
            lambda: (view.signature(folder), view.chief_signature(root, project)),
            interval,
            lambda text: typer.echo(colour(text), nl=False),
            clear=sys.stdout.isatty(),
        )
    except KeyboardInterrupt:
        typer.echo("")


@app.command("status")
def show_status(
    project: Annotated[
        str | None, typer.Argument(help="Child project name; omit for the workspace.")
    ] = None,
    root: Annotated[Path, root_option("Research workbench root.")] = Path("."),
    workspace: Annotated[
        bool, typer.Option("--workspace", help="Workspace scope (the same as omitting PROJECT).")
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose", "-v", help="Also show statements, objection text and last handoff."
        ),
    ] = False,
) -> None:
    """Show stored state without changing files. Without PROJECT, show the workspace."""
    say = sayer()
    if project is not None and workspace:
        raise typer.BadParameter("give PROJECT or --workspace, not both", param_hint="--workspace")
    if project is None:
        _workspace_status(root, verbose)
        return
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="project") from error
    try:
        report = project_status(root, project)
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    say(
        f"Project: {report.project}\nStage: {report.stage or 'unknown'}\n"
        f"Next step: {report.next_step or 'unknown'}"
    )
    if verbose:
        say(f"Last handoff: {report.last_handoff or 'none'}")
    say(
        "Data: valid (project files and direct references)"
        if not report.errors
        else "Data: INVALID; conditions unknown (partial view)"
    )
    say("Claims:" + ("" if report.claims else " none"))

    def objections(value: bool | None) -> str:
        return (
            "Objections unknown"
            if value is None
            else "open Objections"
            if value
            else ("no open Objections")
        )

    def conditions(value: bool | None) -> str:
        return "unknown" if value is None else "met" if value else "not met"

    for claim in report.claims:
        # UX4: researcher wording instead of key=value fields.
        say(
            f"  {claim.object_id} {claim.stored_status} · "
            f"{claim.verified_support_count} verified support · "
            f"{objections(claim.has_open_objection)} · "
            f"supported conditions {conditions(claim.eligible_for_supported)}"
        )
        if verbose and claim.summary:
            say(f"      {claim.summary}")
    if report.superseded:
        say("Superseded:")
    for revised in report.superseded:
        say("  " + " -> ".join(str(item) for item in revised.chain))
        if verbose and revised.summary:
            say(f"      {revised.summary}")
    say("Open objections:" + ("" if report.open_objections else " none"))
    for objection in report.open_objections:
        say(f"  {objection.object_id} {objection.severity} · on {objection.target}")
        if verbose and objection.summary:
            say(f"      {objection.summary}")
    if verbose:
        say("Settled objections:" + ("" if report.settled_objections else " none"))
    for settled in report.settled_objections if verbose else ():
        by = f" · by {', '.join(settled.decisions)}" if settled.decisions else ""
        say(f"  {settled.object_id} {settled.status} · on {settled.target}{by}")
        if settled.summary:
            say(f"      {settled.summary}")
    if report.gates:
        say("Gates (readiness from files; the stage changes only by your ruling):")
    for gate in report.gates:
        state = "unknown (data invalid)" if gate.met is None else "met" if gate.met else "not met"
        later = not verbose and not upcoming(report.stage, gate)
        say(f"  {gate.gate} -> {gate.enters}: {state}" + (" (later)" if later else ""))
        for item in () if later else gate.items:
            detail = f": {item.detail}" if item.detail else ""
            say(f"    [{'x' if item.met else ' '}] {item.label}{detail}")
    for warning in report.stage_warnings:
        say(f"Warning: {warning}")
    from toulmin.application.workspace_sync import git_state, sync_notices

    if git_report := git_state(root):
        say(git_report.line())
    for notice in (*report.notices, *sync_notices(root)):
        say(f"Notice: {notice}")
    for message in report.errors:
        typer.echo(f"Error: {message}", err=True)
    if report.errors:
        raise typer.Exit(1)


def _workspace_status(root: Path, verbose: bool) -> None:
    say = sayer()
    try:
        report = workspace_status(root, workspace_setup())
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    state = report.root.state
    say(f"Root: {report.root.root}\nScope: Workspace")
    if state not in {RootState.WORKSPACE, RootState.LEGACY}:
        message = {
            RootState.MISSING: "directory does not exist; `toulmin init ROOT` creates a workspace",
            RootState.EMPTY: "not initialized; `toulmin init ROOT` creates a workspace",
            RootState.INCOMPLETE: "setup incomplete; rerun `toulmin init ROOT` to finish it",
            RootState.UNRELATED: "not a Toulmin workbench; nothing was initialized",
        }[state]
        for notice in report.notices:
            say(f"Notice: {notice}")
        typer.echo(f"Error: {report.root.root}: {message}", err=True)
        hint = project_hint(report.root.root)
        if hint is not None:
            typer.echo(
                f"Error: this looks like a project directory of {hint}; rerun with --root {hint}",
                err=True,
            )
        raise typer.Exit(1)
    charter = report.charter
    if state == RootState.LEGACY:
        say("Workspace state: not configured (existing workbench; projects remain valid)")
    elif charter is not None:
        say(f"Workspace: {charter.name}")
        say(f"Charter revision: {charter.revision}")
        sections = dict(charter.sections)
        say(
            "Direction: "
            + (" ".join(sections["Direction"].split()) if "Direction" in sections else
               "No confirmed direction yet")
        )  # fmt: skip
        for heading in ("Constraints", "Focus"):
            if heading in sections:
                say(f"{heading}: " + " ".join(sections[heading].split()))
        say(f"Recorded next step: {charter.next_step or 'none'}")
        latest = report.history[0] if report.history else None
        say(
            "Last handoff: "
            + (f"sessions/{latest.filename} (applied by {latest.record.applied_by} at "
               f"{latest.record.applied_at})" if latest else
               f"sessions/{charter.last_handoff} (invalid; see errors)" if charter.last_handoff
               else "none (no applied workspace handoff)")
        )  # fmt: skip
    say("Projects:" + ("" if report.children else " none"))
    for child in report.children:
        stage = child.stage or (
            CREATION_INCOMPLETE if child.error == CREATION_INCOMPLETE else "unknown (invalid data)"
        )
        say(f"  {child.name} | stage={stage}")
    if state == RootState.WORKSPACE:
        say("Proposals:" + ("" if report.proposals else " none"))
        for proposal in report.proposals:
            if verbose or proposal.disposition in {"pending", "incomplete", "invalid"}:
                say(f"  {proposal.path} | {proposal.kind} | {proposal.disposition}")
        hidden = sum(
            proposal.disposition in {"applied", "rejected", "superseded"}
            for proposal in report.proposals
        )
        if hidden and not verbose:
            say(f"  ({hidden} applied, rejected or superseded; --verbose lists them)")
        shown = [h for h in report.handoffs if verbose or h.disposition != "applied"]
        say("Handoff drafts:" + ("" if report.handoffs else " none"))
        for item in shown:
            say(f"  {item.path} | {item.disposition}")
        if len(shown) < len(report.handoffs):
            say(f"  ({len(report.handoffs) - len(shown)} applied; --verbose lists them)")
        say("Resources:" + ("" if report.resources else " none"))
        for resource in report.resources:
            say(
                f"  {resource.name} | invalid data" if resource.error else
                f"  {resource.name} | {resource.status} | revision {resource.revision} | "
                f"{resource.title}"
            )  # fmt: skip
    else:
        say(
            "Next: project commands keep working; preview adoption with "
            f"`toulmin workspace adopt {report.root.root}`"
        )
    from toulmin.core.sources import read_source_catalog

    try:
        catalog = read_source_catalog(root)
        if catalog.definitions:
            say("Sources:")
            from toulmin.application.sources import scope_source_reports

            for line in scope_source_reports(root, None):
                say(f"  {line}")
            say(
                "Understanding: overview.md is a reviewed "
                "checkpoint; runs/notebook.md is unconfirmed."
            )
            say(
                "Work: draft task --workspace --source ID for "
                "bounded engineering; no Claim/Spec/gate required."
            )
    except (OSError, ValueError):
        pass  # The structured read-only report above includes invalid source diagnostics.
    say("Data: valid" if not report.errors else "Data: INVALID (partial view)")
    from toulmin.application.workspace_sync import git_state, sync_notices

    if git_report := git_state(root):
        say(git_report.line())
    for notice in (*report.notices, *sync_notices(root)):
        say(f"Notice: {notice}")
    for message in report.errors:
        typer.echo(f"Error: {message}", err=True)
    if report.errors:
        raise typer.Exit(1)


@app.command("handoff")
def handoff(
    project: Annotated[str, typer.Argument(help="Project name.")],
    root: Annotated[Path, root_option("Research workbench root.")] = Path("."),
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
        typer.Option(
            "--confirmed-by",
            help=f"Researcher authorizing application. Defaults to ${ACTOR_VARIABLE}, then config.",
        ),
    ] = None,
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Confirm application of this draft.")
    ] = False,
) -> None:
    """Archive a handoff draft, or explicitly apply/recover an approved draft."""
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="project") from error
    if apply_path is not None and input_path is not None:
        raise typer.BadParameter("--apply and --input are mutually exclusive")
    if apply_path is None and (confirm or actor is not None):
        raise typer.BadParameter("--confirm/--confirmed-by require --apply")
    if apply_path is not None:
        actor = confirmer(actor)
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
    typer.echo(str(path.relative_to(root.absolute())))
