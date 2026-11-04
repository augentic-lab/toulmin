"""Reviewed child creation: propose a sealed packet, then create or reject it."""

import os
import shlex
from pathlib import Path
from typing import Annotated

import typer

from toulmin.protocols.project_creation import CreationOutcome, create, propose, reject

app = typer.Typer(
    help="Propose, create or reject reviewed child projects of a workspace.",
    no_args_is_help=True,
)

ACTOR_VARIABLE = "TOULMIN_ACTOR"
Name = Annotated[str, typer.Argument(help="Child project name (lowercase, hyphenated).")]
Root = Annotated[Path, typer.Option("--root", help="Workspace root.")]
Packet = Annotated[
    str,
    typer.Option("--from", help="Creation packet runs/<stamp>-project-<hex> (or packet.md)."),
]
Actor = Annotated[
    str | None,
    typer.Option("--confirmed-by", help=f"Confirming researcher; defaults to ${ACTOR_VARIABLE}."),
]
Confirm = Annotated[bool, typer.Option("--confirm", help="Confirm this exact reviewed packet.")]


def _command(*words: str) -> str:
    return " ".join(shlex.quote(word) for word in words)


def _review(outcome: CreationOutcome, root: Path) -> None:
    """Render the frozen packet exactly as create will check it."""
    loaded = outcome.loaded
    root_text = str(root.absolute())
    name = loaded.packet.project
    typer.echo(f"Root: {root_text}")
    typer.echo("Scope: Workspace")
    typer.echo(f"Packet: {loaded.directory}")
    typer.echo(f"Seal: {loaded.seal[:16]}")
    typer.echo(f"Creates: projects/{name}/ (absent until confirmed)")
    if loaded.packet.supersedes is not None:
        typer.echo(f"Supersedes: {loaded.packet.supersedes}")
    typer.echo("")
    typer.echo(loaded.body.rstrip("\n"))
    typer.echo("")
    for problem in outcome.problems:
        typer.echo(f"Refused now: {problem}")
    typer.echo("Create: " + _command(
        "toulmin", "project", "create", name, "--root", root_text, "--from", loaded.directory,
        "--confirmed-by", "ACTOR", "--confirm",
    ))  # fmt: skip
    typer.echo("Reject: " + _command(
        "toulmin", "project", "reject", name, "--root", root_text, "--from", loaded.directory,
        "--reason", "TEXT", "--confirmed-by", "ACTOR", "--confirm",
    ))  # fmt: skip


def _result(outcome: CreationOutcome, root: Path) -> None:
    receipt = outcome.receipt
    assert receipt is not None
    name = outcome.project
    typer.echo(f"Root: {root.absolute()}")
    typer.echo("Scope: Workspace")
    typer.echo(f"Packet: {outcome.loaded.directory}")
    typer.echo(f"Disposition: {receipt.disposition} by {receipt.actor} at {receipt.at}")
    if outcome.status == "replayed":
        typer.echo("Already recorded; nothing written.")
    if outcome.status == "recovered":
        typer.echo("Interrupted creation finished from the journal.")
    for note in outcome.problems:
        typer.echo(f"Note: {note}")
    for path, _, after in receipt.results:
        typer.echo(f"Published: {path} ({after[:16]})")
    typer.echo(f"Receipt: {outcome.receipt_path}")
    if receipt.disposition == "applied":
        typer.echo(f"Project: projects/{name} (stage explore; no Claim or Decision created)")
        typer.echo("No native session was started; this workspace conversation is unchanged.")
        typer.echo(
            "Open it in its own session: "
            + _command("toulmin", "aoe", "open", name, "--root", str(root.absolute()))
        )


def _fail(error: Exception) -> typer.Exit:
    typer.echo(f"Error: {error}", err=True)
    return typer.Exit(1)


def _actor(actor: str | None) -> str:
    actor = actor if actor is not None else os.environ.get(ACTOR_VARIABLE) or None
    if actor is None:
        raise typer.BadParameter(
            f"required: pass --confirmed-by or set {ACTOR_VARIABLE}", param_hint="--confirmed-by"
        )
    return actor


@app.command("propose")
def propose_command(
    name: Name,
    input_path: Annotated[
        str, typer.Option("--input", help="Creation input under root runs/drafts/.")
    ],
    root: Root = Path("."),
) -> None:
    """Freeze a sealed creation packet; no project directory is created."""
    try:
        outcome = propose(root, name, input_path)
    except (OSError, ValueError) as error:
        raise _fail(error) from error
    _review(outcome, root)


@app.command("create")
def create_command(
    name: Name,
    packet: Packet,
    root: Root = Path("."),
    actor: Actor = None,
    confirm: Confirm = False,
    approval_text: Annotated[
        str | None,
        typer.Option("--approval-text", help="The researcher's captured approval words."),
    ] = None,
) -> None:
    """Preview a creation packet (no --confirm) or create the child exactly as reviewed."""
    if actor is not None and not confirm:
        typer.echo(
            "Error: not created; confirmation missing. Review the preview, then rerun with "
            "--confirm.",
            err=True,
        )
        raise typer.Exit(1)
    if confirm:
        actor = _actor(actor)
    try:
        outcome = create(root, name, packet, actor, confirmed=confirm, approval_text=approval_text)
    except (OSError, ValueError) as error:
        raise _fail(error) from error
    if outcome.status in {"preview", "incomplete"}:
        if outcome.status == "incomplete":
            typer.echo("State: creation incomplete")
        _review(outcome, root)
        typer.echo("Preview only; nothing written.")
        return
    _result(outcome, root)


@app.command("reject")
def reject_command(
    name: Name,
    packet: Packet,
    reason: Annotated[str, typer.Option("--reason", help="Why this packet is rejected.")],
    root: Root = Path("."),
    actor: Actor = None,
    confirm: Confirm = False,
) -> None:
    """Record a final rejection of a pending creation packet; nothing else changes."""
    if not confirm:
        typer.echo("Error: not rejected; confirmation missing. Rerun with --confirm.", err=True)
        raise typer.Exit(1)
    try:
        outcome = reject(root, name, packet, reason, _actor(actor))
    except (OSError, ValueError) as error:
        raise _fail(error) from error
    _result(outcome, root)
