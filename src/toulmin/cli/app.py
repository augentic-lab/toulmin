"""Installed CLI entry point."""

import os
import re
from pathlib import Path
from typing import Annotated

import typer

from toulmin.cli.initialize import initialize
from toulmin.core.identifiers import ObjectKind, validate_project_name
from toulmin.protocols.drafting import write_draft
from toulmin.protocols.handoff import apply_handoff, draft_handoff
from toulmin.protocols.inputs import resolve_inputs
from toulmin.protocols.intake import create_object
from toulmin.protocols.review_intake import intake_review
from toulmin.protocols.ruling import apply_ruling
from toulmin.protocols.status import project_status

app = typer.Typer(
    help="Toulmin research workbench. Initialize, create objects and inspect project state.",
    add_completion=False,
    no_args_is_help=True,
)

ACTOR_VARIABLE = "TOULMIN_ACTOR"


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


def confirmer(value: str | None) -> str | None:
    """Explicit --confirmed-by wins; otherwise the operator's local default, if any."""
    if value is not None:
        return value
    return os.environ.get(ACTOR_VARIABLE) or None


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
    project: Annotated[str, typer.Option("--project", help="Project name, e.g. tail-latency.")],
) -> None:
    """Create a workbench and project without overwriting existing content."""
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="--project") from error
    try:
        created = initialize(root, project)
    except (OSError, ValueError, RuntimeError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Workbench: {root.absolute()} | project: {project} | created entries: {created}")


@app.command("draft")
def draft_object(
    kind: Annotated[ObjectKind, typer.Argument(help="Object type.")],
    project: Annotated[str, typer.Argument(help="Project name.")],
    root: Annotated[Path, typer.Option("--root", help="Research workbench root.")] = Path("."),
    name: Annotated[
        str | None, typer.Option("--name", help="Optional filename suffix, e.g. tail-cause.")
    ] = None,
    role: Annotated[
        str | None,
        typer.Option("--role", help="Run only: fill role and input_files from this role."),
    ] = None,
    claims: Annotated[
        list[str] | None,
        typer.Option("--claim", help="With --role: give only these Claims; may be repeated."),
    ] = None,
) -> None:
    """Write a fillable draft skeleton under the project's runs/drafts/."""
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="project") from error
    try:
        path = write_draft(root, project, kind, name, confirmer(None), role=role, claims=claims)
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    relative = display(path, root)
    typer.echo(relative)
    location = "" if root == Path(".") else f" --root {root}"
    typer.echo(
        f"Fill every <fill: ...> value, then: toulmin new {kind.value} {project}{location} "
        f"--input {relative} --confirm",
        err=True,
    )


@app.command("inputs")
def role_inputs(
    project: Annotated[str, typer.Argument(help="Project name.")],
    role: Annotated[str, typer.Argument(help="Role with an input manifest, e.g. reviewer.")],
    root: Annotated[Path, typer.Option("--root", help="Research workbench root.")] = Path("."),
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
            help=f"Researcher authorizing intake. Defaults to ${ACTOR_VARIABLE}.",
        ),
    ] = None,
    root: Annotated[Path, typer.Option("--root", help="Research workbench root.")] = Path("."),
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
        raise typer.BadParameter(
            f"required: pass --confirmed-by or set {ACTOR_VARIABLE}", param_hint="--confirmed-by"
        )
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
    root: Annotated[Path, typer.Option("--root", help="Research workbench root.")] = Path("."),
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
    actor: Annotated[
        str | None,
        typer.Option(
            "--confirmed-by",
            help=f"Researcher choosing these outcomes. Defaults to ${ACTOR_VARIABLE}.",
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
        raise typer.BadParameter(
            f"required: pass --confirmed-by or set {ACTOR_VARIABLE}", param_hint="--confirmed-by"
        )
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
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(display(result.record, root))
    for line in result.lines:
        target = f" as {line.object_id}" if line.object_id else ""
        typer.echo(f"{line.label}: {line.outcome}{target} ({result.run})")


@app.command("review")
def review_project(
    project: Annotated[str, typer.Argument(help="Project name.")],
    root: Annotated[Path, typer.Option("--root", help="Research workbench root.")] = Path("."),
    personas: Annotated[
        str | None,
        typer.Option("--personas", help="Comma list of critique roles; default from models.toml."),
    ] = None,
    models: Annotated[
        str | None,
        typer.Option("--models", help="Comma list of [models] names; default from models.toml."),
    ] = None,
    claims: Annotated[
        list[str] | None,
        typer.Option("--claim", help="Review only these Claims; may be repeated."),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the planned sessions; run nothing.")
    ] = False,
    actor: Annotated[
        str | None,
        typer.Option(
            "--confirmed-by",
            help=f"Researcher starting this round. Defaults to ${ACTOR_VARIABLE}.",
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
        raise typer.BadParameter(
            f"required: pass --confirmed-by or set {ACTOR_VARIABLE}", param_hint="--confirmed-by"
        )

    def split(value: str | None) -> list[str] | None:
        return (
            None if value is None else [item.strip() for item in value.split(",") if item.strip()]
        )

    try:
        failed = run_round(
            root,
            project,
            split(personas),
            split(models),
            claims,
            actor or "",
            dry_run=dry_run,
            confirmed=confirm,
            echo=typer.echo,
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    if failed:
        raise typer.Exit(1)


@app.command("rule")
def rule_object(
    project: Annotated[str, typer.Argument(help="Project name.")],
    object_id: Annotated[str, typer.Argument(help="Object ID in this project, e.g. O-001.")],
    root: Annotated[Path, typer.Option("--root", help="Research workbench root.")] = Path("."),
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
            help=f"Researcher making this ruling. Defaults to ${ACTOR_VARIABLE}.",
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
        raise typer.BadParameter(
            f"required: pass --confirmed-by or set {ACTOR_VARIABLE}", param_hint="--confirmed-by"
        )
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


@app.command("status")
def show_status(
    project: Annotated[str, typer.Argument(help="Project name.")],
    root: Annotated[Path, typer.Option("--root", help="Research workbench root.")] = Path("."),
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose", "-v", help="Also show statements, objection text and last handoff."
        ),
    ] = False,
) -> None:
    """Show stored state, conditions and data problems without changing files."""
    try:
        validate_project_name(project)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="project") from error
    try:
        report = project_status(root, project)
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(
        f"Project: {report.project}\nStage: {report.stage or 'unknown'}\n"
        f"Next step: {report.next_step or 'unknown'}"
    )
    if verbose:
        typer.echo(f"Last handoff: {report.last_handoff or 'none'}")
    typer.echo(
        "Data: valid (project files and direct references)"
        if not report.errors
        else "Data: INVALID; conditions unknown (partial view)"
    )
    typer.echo("Claims:" + ("" if report.claims else " none"))

    def flag(value: bool | None) -> str:
        return "unknown" if value is None else "yes" if value else "no"

    for claim in report.claims:
        typer.echo(
            f"  {claim.object_id} | stored={claim.stored_status} | "
            f"verified_support={claim.verified_support_count} | "
            f"open_objection={flag(claim.has_open_objection)} | "
            f"eligible_supported={flag(claim.eligible_for_supported)}"
        )
        if verbose and claim.summary:
            typer.echo(f"      {claim.summary}")
    if report.superseded:
        typer.echo("Superseded:")
    for revised in report.superseded:
        typer.echo("  " + " -> ".join(str(item) for item in revised.chain))
        if verbose and revised.summary:
            typer.echo(f"      {revised.summary}")
    typer.echo("Open objections:" + ("" if report.open_objections else " none"))
    for objection in report.open_objections:
        typer.echo(f"  {objection.object_id} | {objection.severity} | target={objection.target}")
        if verbose and objection.summary:
            typer.echo(f"      {objection.summary}")
    if verbose:
        typer.echo("Settled objections:" + ("" if report.settled_objections else " none"))
    for settled in report.settled_objections if verbose else ():
        by = f" | by {', '.join(settled.decisions)}" if settled.decisions else ""
        typer.echo(f"  {settled.object_id} | {settled.status} | target={settled.target}{by}")
        if settled.summary:
            typer.echo(f"      {settled.summary}")
    for notice in report.notices:
        typer.echo(f"Notice: {notice}")
    for message in report.errors:
        typer.echo(f"Error: {message}", err=True)
    if report.errors:
        raise typer.Exit(1)


@app.command("handoff")
def handoff(
    project: Annotated[str, typer.Argument(help="Project name.")],
    root: Annotated[Path, typer.Option("--root", help="Research workbench root.")] = Path("."),
    input_path: Annotated[
        str | None, typer.Option("--input", help="Session summary path relative to --root.")
    ] = None,
    apply_path: Annotated[
        str | None,
        typer.Option("--apply", help="Archived draft to apply or recover, relative to --root."),
    ] = None,
    actor: Annotated[
        str | None,
        typer.Option(
            "--confirmed-by",
            help=f"Researcher authorizing application. Defaults to ${ACTOR_VARIABLE}.",
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
            raise typer.BadParameter(f"--apply requires --confirmed-by or {ACTOR_VARIABLE}")
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
