"""Reviewed workspace changes: propose a sealed packet, then apply or reject it."""

import os
import shlex
from pathlib import Path
from typing import Annotated

import typer

from toulmin.cli.initialize import adoption_templates
from toulmin.protocols.adoption import adopt, preview
from toulmin.protocols.workspace_change import Outcome, apply, propose, reject

app = typer.Typer(
    help="Propose, apply or reject reviewed changes to WORKSPACE.md and shared resources.",
    no_args_is_help=True,
)

ACTOR_VARIABLE = "TOULMIN_ACTOR"
Root = Annotated[Path, typer.Option("--root", help="Workspace root.")]
Draft = Annotated[
    str,
    typer.Option("--draft", help="Packet directory runs/<stamp>-proposal-<hex> (or packet.md)."),
]
Actor = Annotated[
    str | None,
    typer.Option("--confirmed-by", help=f"Confirming researcher; defaults to ${ACTOR_VARIABLE}."),
]
Confirm = Annotated[bool, typer.Option("--confirm", help="Confirm this exact reviewed packet.")]


def _command(*words: str) -> str:
    return " ".join(shlex.quote(word) for word in words)


def _review(outcome: Outcome, root: Path) -> None:
    """Render the frozen packet exactly as apply will check it."""
    loaded = outcome.loaded
    root_text = str(root.absolute())
    typer.echo(f"Root: {root_text}")
    typer.echo("Scope: workspace")
    typer.echo(f"Packet: {loaded.directory}")
    typer.echo(f"Seal: {loaded.seal[:16]}")
    for target in loaded.packet.targets:
        action = "create" if target.before_sha256 is None else "replace"
        typer.echo(f"Target: {target.path} ({action})")
    typer.echo("")
    typer.echo(loaded.body.rstrip("\n"))
    typer.echo("")
    for problem in outcome.problems:
        typer.echo(f"Refused now: {problem}")
    draft = loaded.directory
    typer.echo("Apply: " + _command(
        "toulmin", "workspace", "apply", "--root", root_text, "--draft", draft,
        "--confirmed-by", "ACTOR", "--confirm",
    ))  # fmt: skip
    typer.echo("Reject: " + _command(
        "toulmin", "workspace", "reject", "--root", root_text, "--draft", draft,
        "--reason", "TEXT", "--confirmed-by", "ACTOR", "--confirm",
    ))  # fmt: skip


def _result(outcome: Outcome) -> None:
    receipt = outcome.receipt
    assert receipt is not None
    typer.echo(f"Packet: {outcome.loaded.directory}")
    typer.echo(f"Disposition: {receipt.disposition} by {receipt.actor} at {receipt.at}")
    if outcome.status == "replayed":
        typer.echo("Already recorded; nothing written.")
    if outcome.status == "recovered":
        typer.echo("Interrupted publication finished from the journal.")
    for note in outcome.problems:
        typer.echo(f"Note: {note}")
    for path, _, after in receipt.results:
        typer.echo(f"Published: {path} ({after[:16]})")
    typer.echo(f"Receipt: {outcome.receipt_path}")


def _fail(error: Exception) -> typer.Exit:
    typer.echo(f"Error: {error}", err=True)
    return typer.Exit(1)


@app.command("propose")
def propose_command(
    input_path: Annotated[
        str, typer.Option("--input", help="Change input under root runs/drafts/.")
    ],
    root: Root = Path("."),
) -> None:
    """Freeze a sealed review packet; WORKSPACE.md and resources are unchanged."""
    try:
        outcome = propose(root, input_path)
    except (OSError, ValueError) as error:
        raise _fail(error) from error
    _review(outcome, root)


@app.command("apply")
def apply_command(
    draft: Draft,
    root: Root = Path("."),
    actor: Actor = None,
    confirm: Confirm = False,
    approval_text: Annotated[
        str | None,
        typer.Option("--approval-text", help="The researcher's captured approval words."),
    ] = None,
) -> None:
    """Preview a packet (no --confirm) or publish it exactly as reviewed."""
    if actor is not None and not confirm:
        typer.echo(
            "Error: not applied; confirmation missing. Review the preview, then rerun with "
            "--confirm.",
            err=True,
        )
        raise typer.Exit(1)
    if confirm:
        actor = actor if actor is not None else os.environ.get(ACTOR_VARIABLE) or None
        if actor is None:
            raise typer.BadParameter(
                f"required: pass --confirmed-by or set {ACTOR_VARIABLE}",
                param_hint="--confirmed-by",
            )
    try:
        outcome = apply(root, draft, actor, confirmed=confirm, approval_text=approval_text)
    except (OSError, ValueError) as error:
        raise _fail(error) from error
    if outcome.status in {"preview", "incomplete"}:
        if outcome.status == "incomplete":
            typer.echo("State: publication incomplete")
        _review(outcome, root)
        typer.echo("Preview only; nothing written.")
        return
    _result(outcome)


@app.command("reject")
def reject_command(
    draft: Draft,
    reason: Annotated[str, typer.Option("--reason", help="Why this packet is rejected.")],
    root: Root = Path("."),
    actor: Actor = None,
    confirm: Confirm = False,
) -> None:
    """Record a final rejection of a pending packet; nothing else changes."""
    if not confirm:
        typer.echo("Error: not rejected; confirmation missing. Rerun with --confirm.", err=True)
        raise typer.Exit(1)
    actor = actor if actor is not None else os.environ.get(ACTOR_VARIABLE) or None
    if actor is None:
        raise typer.BadParameter(
            f"required: pass --confirmed-by or set {ACTOR_VARIABLE}", param_hint="--confirmed-by"
        )
    try:
        outcome = reject(root, draft, reason, actor)
    except (OSError, ValueError) as error:
        raise _fail(error) from error
    _result(outcome)


@app.command("adopt")
def adopt_command(
    root: Annotated[Path, typer.Argument(help="Existing (legacy) workbench root.")],
    name: Annotated[
        str | None, typer.Option("--name", help="Workspace name; defaults to the directory name.")
    ] = None,
    plan_digest: Annotated[
        str | None,
        typer.Option("--plan-digest", help="Digest of the previewed plan (16+ hex digits)."),
    ] = None,
    actor: Actor = None,
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Confirm the previewed, unchanged plan.")
    ] = False,
    approval_text: Annotated[
        str | None,
        typer.Option("--approval-text", help="The researcher's captured approval words."),
    ] = None,
) -> None:
    """Preview (no digest) or apply the additive adoption plan of a legacy workbench."""
    if (plan_digest is not None or actor is not None) and not confirm:
        typer.echo(
            "Error: not adopted; confirmation missing. Review the plan, then rerun with --confirm.",
            err=True,
        )
        raise typer.Exit(1)
    templates = adoption_templates()
    if not confirm:
        try:
            outcome = preview(root, name, templates)
        except (OSError, ValueError) as error:
            raise _fail(error) from error
        typer.echo(f"Root: {outcome.root}")
        if outcome.status == "configured":
            typer.echo("Workspace state: configured (WORKSPACE.md exists); nothing to adopt.")
            if outcome.receipt is not None:
                typer.echo(
                    f"Adopted: {outcome.directory} by {outcome.receipt.actor} at "
                    f"{outcome.receipt.at}"
                )
            return
        if outcome.status == "incomplete":
            typer.echo("State: adoption incomplete")
            for problem in outcome.problems:
                typer.echo(f"Next: {problem}")
            return
        plan = outcome.plan
        assert plan is not None
        typer.echo("Scope: Workspace (after adoption)")
        typer.echo(f"Workspace name: {plan.name}")
        typer.echo(f"Plan digest: {plan.digest}")
        typer.echo("")
        typer.echo(plan.data.decode().split("---\n", 2)[2].rstrip("\n"))
        typer.echo("")
        if plan.conflicts:
            typer.echo(f"Cannot be confirmed: {len(plan.conflicts)} conflict(s); nothing written.")
        else:
            words = ["toulmin", "workspace", "adopt", str(outcome.root)]
            words += ["--name", name] if name is not None else []
            words += ["--plan-digest", plan.digest, "--confirmed-by", "ACTOR", "--confirm"]
            typer.echo("Adopt: " + _command(*words))
        typer.echo("Preview only; nothing written.")
        return
    if plan_digest is None:
        raise typer.BadParameter("required with --confirm", param_hint="--plan-digest")
    actor = actor if actor is not None else os.environ.get(ACTOR_VARIABLE) or None
    if actor is None:
        raise typer.BadParameter(
            f"required: pass --confirmed-by or set {ACTOR_VARIABLE}", param_hint="--confirmed-by"
        )
    try:
        result = adopt(root, name, templates, plan_digest, actor, approval_text=approval_text)
    except (OSError, ValueError) as error:
        raise _fail(error) from error
    receipt = result.receipt
    assert receipt is not None
    typer.echo(f"Root: {result.root}")
    typer.echo("Scope: Workspace")
    typer.echo(f"Adoption: {result.directory}")
    typer.echo(f"Disposition: {receipt.disposition} by {receipt.actor} at {receipt.at}")
    if result.status == "replayed":
        typer.echo("Already recorded; nothing written.")
    if result.status == "recovered":
        typer.echo("Interrupted adoption finished from the journal.")
    for note in result.problems:
        typer.echo(f"Note: {note}")
    for path, _, after in receipt.results:
        typer.echo(f"Published: {path} ({after[:16]})")
    typer.echo(f"Receipt: {result.directory}/receipt.md")
    typer.echo(
        "No model or session was started. Bound project native contexts, if any, are now "
        "stale (they gain WORKSPACE.md); refresh each with `toulmin aoe refresh PROJECT`."
    )
