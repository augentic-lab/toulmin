"""Independent engineering tasks: import worker output as ordinary archived Runs."""

from pathlib import Path
from typing import Annotated

import typer

from toulmin.application.engineering_task_import import apply_task_import, prepare_task_import
from toulmin.application.engineering_tasks import PreparedTask
from toulmin.cli.settings import ACTOR_HINT, resolve_actor, root_option

app = typer.Typer(
    help="Independent engineering tasks (no Claim or Spec required).", no_args_is_help=True
)


def show_task(prepared: PreparedTask) -> None:
    plan = prepared.plan
    typer.echo(f"Engineering task: {plan.task_id}\nProposal: {plan.path}")
    typer.echo(
        f"Source: {plan.request.source or 'explicit repository'}\n"
        f"Repository: {plan.contract.get('repo', plan.request.repo)}"
    )
    typer.echo(f"Committed baseline: {plan.contract.get('base_branch', plan.request.baseline)}")
    typer.echo(f"Goal: {plan.request.goal}\nScope: {plan.request.scope}")
    typer.echo(
        f"Tool: {plan.request.tool}"
        + (f" via {plan.request.command}" if plan.request.command else "")
    )
    typer.echo(
        f"Budget: {plan.request.budget}\n"
        f"Protected paths: {', '.join(plan.request.protected) or 'none'}"
    )
    typer.echo("Executable checks:")
    for command in plan.request.checks:
        typer.echo("  " + command)
    if prepared.interrupted:
        typer.echo("Interrupted submission: the frozen contract is checked before recovery.")
    for problem in prepared.problems:
        typer.echo("Blocked: " + problem)


@app.command("import")
def import_result(
    project: Annotated[str, typer.Argument(help="Project name.")],
    task_id: Annotated[str, typer.Argument(help="Submitted engineering Chief task ID.")],
    root: Annotated[Path, root_option("Research workspace root.")] = Path("."),
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Archive the previewed output as an ordinary Run.")
    ] = False,
    actor: Annotated[
        str | None, typer.Option("--confirmed-by", help="Researcher attribution.")
    ] = None,
) -> None:
    """Preview a finished engineering task; confirmation imports an ordinary Run."""
    try:
        shown = prepare_task_import(root, project, task_id)
        typer.echo(f"Engineering task {task_id}: {shown.record.state}")
        typer.echo(shown.files["task.md"].decode("utf-8", errors="replace"))
        typer.echo("Confirmation archives artifacts and creates an ordinary implementer Run.")
        typer.echo("Scientific promotion remains a separate researcher decision.")
        if not confirm:
            typer.echo("Preview only; nothing written. Apply with --confirm in your own terminal.")
            return
        who = resolve_actor(actor)
        if who is None:
            raise ValueError(f"required: {ACTOR_HINT}")
        done = apply_task_import(root, project, shown, who)
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Imported engineering task {done.task_id} as {done.run}.")
