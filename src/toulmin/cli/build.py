"""Researcher-confirmed imports and independent frozen-check verification."""

from pathlib import Path
from typing import Annotated

import typer

from toulmin.application.build_import import ImportPreview, apply_import, prepare_import
from toulmin.application.build_verify import VerifyPreview, apply_verification, prepare_verification
from toulmin.cli.settings import ACTOR_HINT, resolve_actor, root_option

app = typer.Typer(
    help="Import Chief results or independently rerun frozen checks (researcher-confirmed).",
    no_args_is_help=True,
)


def show_import(shown: ImportPreview) -> None:
    typer.echo(f"Chief result ready: {shown.label}")
    typer.echo(shown.files["task.md"].decode("utf-8", errors="replace"))
    typer.echo("Apply archives the result and records an implementer Run.")
    if shown.record.state == "done":
        typer.echo(
            "It drafts a Decision, model-asserted Evidence and an awaiting-acceptance ruling; "
            "decide them separately. Independent verification remains separate."
        )
    else:
        typer.echo("The task was abandoned: a failed Run only; no Evidence or ruling proposals.")
    if shown.archive is not None:
        typer.echo(
            f"Archive: {shown.archive} ({shown.record.disposition}; existing files are reused)"
        )


@app.command("import")
def import_result(
    project: Annotated[str, typer.Argument(help="Project name.")],
    spec: Annotated[str, typer.Argument(help="Spec ID (S-NNN).")],
    root: Annotated[Path, root_option("Research workbench root.")] = Path("."),
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Confirm the import, not the proposed rulings.")
    ] = False,
    actor: Annotated[
        str | None, typer.Option("--confirmed-by", help="Researcher attribution.")
    ] = None,
) -> None:
    """Preview a Chief result; --confirm archives it and drafts its follow-ups."""
    try:
        shown = prepare_import(root, project, spec)
        show_import(shown)
        if not confirm:
            typer.echo("Preview only; nothing written. Apply with --confirm in your own terminal.")
            return
        who = resolve_actor(actor)
        if who is None:
            raise ValueError(f"required: {ACTOR_HINT}")
        done = apply_import(root, project, shown, who)
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(
        f"Imported: {done.task_id} as {done.run}. Follow-ups: {len(done.proposals)} proposal(s)."
    )


def show_verification(shown: VerifyPreview) -> None:
    record = shown.record
    typer.echo(f"Verify {shown.label}")
    typer.echo(
        f"Repository: {record.repo}\nCommit: {record.head}\n"
        f"Timeout per check: {record.timeout_seconds:g} seconds"
    )
    if record.repo_reason is not None:
        typer.echo("Repository resolution: " + record.repo_reason)
    typer.echo("Frozen checks from: " + record.contract)
    for index, command in enumerate(record.checks, 1):
        typer.echo(f"  {index}. {command}")
    typer.echo(
        "runs code written by an AI worker on this machine, as you, without network isolation"
    )
    if shown.archive is not None:
        if record.disposition == "applied":
            typer.echo("Already verified successfully; no checks or proposals will be duplicated.")
        elif record.execution_completed:
            typer.echo(
                "Completed results are recorded; apply only finishes the Run/proposals, "
                "without rerunning checks."
            )
        else:
            typer.echo(
                "Interrupted attempt: apply retains its output and reruns the frozen checks "
                "in a new fresh clone."
            )
    typer.echo(
        "Passing checks propose Decision → verified Evidence → passed ruling; "
        "you decide each separately."
    )


@app.command("verify")
def verify_result(
    project: Annotated[str, typer.Argument(help="Project name.")],
    spec: Annotated[str, typer.Argument(help="Spec ID (S-NNN).")],
    root: Annotated[Path, root_option("Research workbench root.")] = Path("."),
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Run the frozen checks as you in a temporary clone.")
    ] = False,
    actor: Annotated[
        str | None, typer.Option("--confirmed-by", help="Researcher attribution.")
    ] = None,
) -> None:
    """Preview independent checks; --confirm executes them and archives their results."""
    try:
        shown = prepare_verification(root, project, spec)
        show_verification(shown)
        if not confirm:
            typer.echo("Preview only; nothing written. Apply with --confirm in your own terminal.")
            return
        who = resolve_actor(actor)
        if who is None:
            raise ValueError(f"required: {ACTOR_HINT}")
        done = apply_verification(root, project, shown, who)
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(
        f"Verification {'passed' if done.passed else 'failed'}: {done.run}; "
        f"{len(done.proposals)} follow-up proposal(s)."
    )
    if not done.passed:
        raise typer.Exit(1)
