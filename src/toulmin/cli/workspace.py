"""Reviewed workspace changes: propose a sealed packet, then apply or reject it."""

import shlex
from pathlib import Path
from typing import Annotated

import typer

from toulmin.cli.initialize import adoption_templates
from toulmin.cli.registry import note as register_workspace
from toulmin.cli.settings import ACTOR_HINT, ACTOR_VARIABLE, resolve_actor, root_option
from toulmin.protocols.adoption import adopt, preview
from toulmin.protocols.workspace_change import Outcome, apply, propose, reject

app = typer.Typer(
    help="Review workspace/child intake and shared changes, or append unconfirmed notes.",
    no_args_is_help=True,
)

Root = Annotated[Path, root_option("Workspace root.")]
Draft = Annotated[
    str,
    typer.Option("--draft", help="Packet directory runs/<stamp>-proposal-<hex> (or packet.md)."),
]
Actor = Annotated[
    str | None,
    typer.Option(
        "--confirmed-by", help=f"Confirming researcher; defaults to ${ACTOR_VARIABLE}, then config."
    ),
]
Confirm = Annotated[bool, typer.Option("--confirm", help="Confirm this exact reviewed packet.")]


def _command(*words: str) -> str:
    return " ".join(shlex.quote(word) for word in words)


def _review(outcome: Outcome, root: Path, *, commands: bool = True) -> None:
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
    if not commands:
        return
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


def _selected(packet: str | None, draft: str | None) -> str:
    if (packet is None) == (draft is None):
        raise typer.BadParameter("give PACKET or --draft PACKET, not both")
    assert packet is not None or draft is not None
    return packet if packet is not None else str(draft)


def _v2(root: Path, value: str) -> bool:
    from toulmin.core.repository import Repository
    from toulmin.core.workspace_onboarding import PACKET_DIR

    relative = Repository(root).relative(value).removesuffix("/packet.md").rstrip("/")
    return PACKET_DIR.fullmatch(relative) is not None


def _v2_command(
    root: Path,
    value: str,
    actor: str | None,
    confirm: bool,
    seal: str | None,
    *,
    rejection: str | None = None,
    approval: str | None = None,
) -> None:
    from toulmin.application import workspace_onboarding
    from toulmin.protocols import workspace_onboarding as protocol

    if not seal or (confirm and (not actor or not actor.strip())):
        raise typer.BadParameter(
            "v2 packets require --expect-seal SHA and explicit --confirmed-by "
            "ACTOR with --confirm; environment defaults never approve"
        )
    if rejection is not None and not confirm:
        raise typer.BadParameter("rejection requires --confirm and explicit reason")
    try:
        if rejection is not None:
            assert actor is not None
            outcome = workspace_onboarding.reject(root, value, actor, rejection, expect_seal=seal)
        else:
            outcome = workspace_onboarding.apply(
                root, value, actor, confirmed=confirm, expect_seal=seal, approval_text=approval
            )
        if outcome.status in {"preview", "incomplete"}:
            typer.echo(protocol.preview(root, outcome.loaded))
            typer.echo("Preview only; nothing written.")
        else:
            typer.echo(
                f"Disposition: {outcome.receipt.disposition if outcome.receipt else outcome.status}"
            )
            if outcome.receipt:
                typer.echo(f"By: {outcome.receipt.actor} at {outcome.receipt.at}")
    except (OSError, ValueError) as error:
        raise _fail(error) from error


@app.command("apply")
def apply_command(
    packet: Annotated[str | None, typer.Argument(help="Exact v2 workspace packet.")] = None,
    draft: Annotated[str | None, typer.Option("--draft", help="Existing v1 packet form.")] = None,
    root: Root = Path("."),
    actor: Actor = None,
    confirm: Confirm = False,
    approval_text: Annotated[str | None, typer.Option("--approval-text")] = None,
    expect_seal: Annotated[
        str | None, typer.Option("--expect-seal", help="Full v2 packet SHA-256.")
    ] = None,
) -> None:
    """Preview or explicitly apply exactly one sealed packet; never bulk approve."""
    selected = _selected(packet, draft)
    if _v2(root, selected):
        _v2_command(root, selected, actor, confirm, expect_seal, approval=approval_text)
        return
    if actor is not None and not confirm:
        typer.echo(
            "Error: not applied; confirmation missing. Review then rerun with --confirm.", err=True
        )
        raise typer.Exit(1)
    if confirm:
        actor = resolve_actor(actor)
        if actor is None:
            raise typer.BadParameter(f"required: {ACTOR_HINT}", param_hint="--confirmed-by")
    try:
        outcome = apply(root, selected, actor, confirmed=confirm, approval_text=approval_text)
    except (OSError, ValueError) as error:
        raise _fail(error) from error
    if outcome.status in {"preview", "incomplete"}:
        if outcome.status == "incomplete":
            typer.echo("State: publication incomplete")
        _review(outcome, root)
        typer.echo("Preview only; nothing written.")
    else:
        _result(outcome)


@app.command("reject")
def reject_command(
    reason: Annotated[str, typer.Option("--reason", help="Why this packet is rejected.")],
    packet: Annotated[str | None, typer.Argument()] = None,
    draft: Annotated[str | None, typer.Option("--draft")] = None,
    root: Root = Path("."),
    actor: Actor = None,
    confirm: Confirm = False,
    expect_seal: Annotated[str | None, typer.Option("--expect-seal")] = None,
) -> None:
    """Record one final rejection; source/catalog/overview/child state stays unchanged."""
    selected = _selected(packet, draft)
    if _v2(root, selected):
        _v2_command(root, selected, actor, confirm, expect_seal, rejection=reason)
        return
    if not confirm:
        typer.echo("Error: not rejected; confirmation missing. Rerun with --confirm.", err=True)
        raise typer.Exit(1)
    actor = resolve_actor(actor)
    if actor is None:
        raise typer.BadParameter(f"required: {ACTOR_HINT}", param_hint="--confirmed-by")
    try:
        outcome = reject(root, selected, reason, actor)
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
    actor = resolve_actor(actor)
    if actor is None:
        raise typer.BadParameter(f"required: {ACTOR_HINT}", param_hint="--confirmed-by")
    try:
        result = adopt(root, name, templates, plan_digest, actor, approval_text=approval_text)
    except (OSError, ValueError) as error:
        raise _fail(error) from error
    receipt = result.receipt
    assert receipt is not None
    register_workspace(result.root)
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
