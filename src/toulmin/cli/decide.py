"""``toulmin decide`` (WX4): one terminal walk through everything awaiting the researcher.

Each item is shown with the preview its own command prints, then decided one at a time:
apply, reject (packets only), skip or quit. Decisions call the existing protocol
functions with the researcher's actor; nothing is decided in bulk. Like every other
confirming command, this relies on being run by the researcher, not by an agent.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import typer

from toulmin.cli import project as project_cli
from toulmin.cli import workspace as workspace_cli
from toulmin.cli.aoe import handoff_preview, handoff_result
from toulmin.cli.initialize import workspace_setup
from toulmin.cli.settings import ACTOR_HINT, resolve_actor, root_option
from toulmin.core.atomic import digest
from toulmin.core.codec import decode
from toulmin.core.handoffs import validate_handoff
from toulmin.core.identifiers import validate_project_name
from toulmin.core.repository import Repository
from toulmin.core.workspace import CHARTER_FILE
from toulmin.protocols import project_creation, project_proposals, workspace_change
from toulmin.protocols import workspace_handoff as workspace_handoffs
from toulmin.protocols.handoff import apply_handoff
from toulmin.protocols.workspace_state import RootState, workspace_status

LABEL = {
    "change": "Workspace change",
    "creation": "Child creation",
    "handoff": "Workspace handoff",
    "object": "Object draft",
    "ruling": "Ruling proposal",
    "project-handoff": "Project handoff",
}
WORDS = {"a": "apply", "r": "reject", "s": "skip", "q": "quit"}


@dataclass(frozen=True)
class Item:
    kind: str  # a LABEL key
    path: str
    project: str | None = None


@dataclass(frozen=True)
class Inventory:
    items: tuple[Item, ...]
    stale: int  # handoff drafts already stale before this run: not offered
    ignored: tuple[str, ...] = ()  # proposal-folder files that cannot be offered, with why


def _projects(repository: Repository) -> list[str]:
    """Project names whose charter is readable; status reports the others."""
    names: list[str] = []
    folder = repository.root / "projects"
    if not folder.is_dir() or folder.is_symlink():
        return names
    for child in sorted(folder.iterdir()):
        name = child.name
        if name.startswith(".") or child.is_symlink() or not child.is_dir():
            continue
        try:
            validate_project_name(name)
            repository.path(f"projects/{name}/PROJECT.md", "file")
        except (OSError, ValueError):
            continue
        names.append(name)
    return names


def _project_proposals(repository: Repository) -> tuple[list[Item], list[str]]:
    """Undecided H3 proposals of every project: object drafts, then rulings, per project."""
    items: list[Item] = []
    ignored: list[str] = []
    for name in _projects(repository):
        try:
            found = project_proposals.inventory(repository.root, name)
        except (OSError, ValueError) as error:
            ignored.append(str(error))
            continue
        kinds = {"ruling": "ruling"}
        items += [Item(kinds.get(item.kind, "object"), item.path, name) for item in found.items]
        ignored += [
            f"{path}: not named KIND-YYYYMMDDTHHMMSSZ[-name].md" for path in found.unrecognized
        ]
        ignored += list(found.errors)
    return items, ignored


def _project_handoffs(repository: Repository) -> tuple[list[Item], int]:
    """Unapplied project handoff drafts whose base PROJECT.md is still current."""
    items: list[Item] = []
    stale = 0
    for name in _projects(repository):
        child = repository.root / "projects" / name
        try:
            charter = digest(repository.path(f"projects/{name}/PROJECT.md", "file").read_bytes())
        except (OSError, ValueError):
            continue  # status reports broken projects; nothing here is decidable
        sessions = child / "sessions"
        for draft in sorted((child / "runs").glob("*-handoff-*/draft.md")):
            relative = draft.relative_to(repository.root).as_posix()
            try:
                raw = repository.path(relative, "file").read_bytes()
                document = decode(raw, relative)
                validate_handoff(document, name)
            except (OSError, ValueError):
                continue  # not a generated draft (aoe handoff --apply reports why)
            if sessions.is_dir() and any(sessions.glob(f"*-{digest(raw)}.md")):
                continue
            if document.header["base_project_sha256"] != charter:
                stale += 1
                continue
            items.append(Item("project-handoff", relative, name))
    return items, stale


def inventory(root: Path) -> Inventory:
    """Everything awaiting a decision, in the order decide shows it."""
    report = workspace_status(root, workspace_setup())
    state = report.root.state
    if state not in {RootState.WORKSPACE, RootState.LEGACY}:
        raise ValueError(f"{report.root.root}: not a Toulmin workbench; nothing to decide")
    pending = [item for item in report.proposals if item.disposition == "pending"]
    items = [Item("change", item.path) for item in pending if item.kind == "change"]
    items += [Item("creation", item.path) for item in pending if item.kind == "creation"]
    items += [
        Item("handoff", item.path) for item in report.handoffs if item.disposition == "pending"
    ]
    stale = sum(item.disposition == "stale" for item in report.handoffs)
    repository = Repository(report.root.root)
    proposals, ignored = _project_proposals(repository)
    projects, project_stale = _project_handoffs(repository)
    return Inventory(tuple(items + proposals + projects), stale + project_stale, tuple(ignored))


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _ask(choices: str) -> str:
    text = " / ".join(f"[{letter}]{WORDS[letter][1:]}" for letter in choices)
    while True:
        answer = str(typer.prompt(text, default="s")).strip().lower()
        letter = answer[:1]
        if letter in choices and answer in {letter, WORDS[letter]}:
            return letter
        typer.echo("Choose one of: " + ", ".join(WORDS[letter] for letter in choices))


def _reason() -> str:
    while True:
        reason = str(typer.prompt("Reason for rejecting (recorded in the receipt)")).strip()
        if reason:
            return reason


@dataclass
class Run:
    root: Path
    actor: str
    applied: int = 0
    rejected: int = 0
    skipped: int = 0
    failed: int = 0
    charter_changed: bool = False
    handoff_applied: bool = False
    touched: set[str] = field(default_factory=set)  # projects whose handoff was applied

    def decide(self, item: Item) -> bool:
        """Show and decide one item; False means quit."""
        handler = {
            "change": self._change,
            "creation": self._creation,
            "handoff": self._handoff,
            "object": self._proposal,
            "ruling": self._proposal,
            "project-handoff": self._project_handoff,
        }[item.kind]
        return handler(item)

    def _choose(self, choices: str) -> str:
        choice = _ask(choices)
        if choice == "s":
            self.skipped += 1
        return choice

    def _change(self, item: Item) -> bool:
        outcome = workspace_change.apply(self.root, item.path, None, confirmed=False)
        if outcome.status != "preview":
            typer.echo(f"No longer pending ({outcome.status}); skipped.")
            return True
        workspace_cli._review(outcome, self.root, commands=False)
        choice = self._choose("rsq" if outcome.problems else "arsq")
        if choice == "a":
            result = workspace_change.apply(
                self.root, item.path, self.actor, confirmed=True, approval_text="toulmin decide: a"
            )
            workspace_cli._result(result)
            self.applied += 1
            assert result.receipt is not None
            if any(path == CHARTER_FILE for path, _, _ in result.receipt.results):
                self.charter_changed = True
        elif choice == "r":
            result = workspace_change.reject(self.root, item.path, _reason(), self.actor)
            workspace_cli._result(result)
            self.rejected += 1
        return choice != "q"

    def _creation(self, item: Item) -> bool:
        name = project_creation.load(self.root, item.path).packet.project
        outcome = project_creation.create(self.root, name, item.path, None, confirmed=False)
        if outcome.status != "preview":
            typer.echo(f"No longer pending ({outcome.status}); skipped.")
            return True
        project_cli._review(outcome, self.root, commands=False)
        choice = self._choose("rsq" if outcome.problems else "arsq")
        if choice == "a":
            result = project_creation.create(
                self.root,
                name,
                item.path,
                self.actor,
                confirmed=True,
                approval_text="toulmin decide: a",
            )
            project_cli._result(result, self.root)
            self.applied += 1
        elif choice == "r":
            reason = _reason()
            result = project_creation.reject(self.root, name, item.path, reason, self.actor)
            project_cli._result(result, self.root)
            self.rejected += 1
        return choice != "q"

    def _regenerate(self, loaded: workspace_handoffs.LoadedDraft) -> str | None:
        """A draft made stale by a change applied in this run, redrafted from its summary."""
        summary = loaded.draft.input_path
        try:
            data = Repository(self.root).path(summary, "file").read_bytes()
        except (OSError, ValueError) as error:
            typer.echo(f"Not regenerated: summary {summary} unreadable ({error}).")
            return None
        if digest(data) != loaded.draft.input_sha256:
            typer.echo(
                f"Not regenerated: summary {summary} changed since drafting; ask the agent to "
                "draft the handoff again."
            )
            return None
        outcome = workspace_handoffs.draft(self.root, summary)
        typer.echo(
            "WORKSPACE.md changed in this run, so this draft is stale. Regenerated from the "
            f"same summary: {outcome.loaded.path}"
        )
        return outcome.loaded.path

    def _handoff(self, item: Item) -> bool:
        path = item.path
        loaded = workspace_handoffs.load_draft(self.root, path)
        if workspace_handoffs.check(self.root, loaded):
            if self.handoff_applied:
                typer.echo("Superseded by the workspace handoff applied in this run; skipped.")
                self.skipped += 1
                return True
            if self.charter_changed:
                regenerated = self._regenerate(loaded)
                if regenerated is None:
                    self.skipped += 1
                    return True
                path = regenerated
        outcome = workspace_handoffs.apply(self.root, path, None, confirmed=False)
        if outcome.status != "preview":
            typer.echo(f"No longer pending ({outcome.status}); skipped.")
            return True
        handoff_preview(outcome, self.root, commands=False)  # warns about uncited receipts
        choice = self._choose("sq" if outcome.problems else "asq")
        if choice == "a":
            result = workspace_handoffs.apply(self.root, path, self.actor, confirmed=True)
            handoff_result(result)
            self.applied += 1
            self.handoff_applied = self.charter_changed = True
        return choice != "q"

    def _proposal(self, item: Item) -> bool:
        assert item.project is not None
        shown = project_proposals.preview(self.root, item.project, item.path)
        if shown.problems and shown.problems[0].startswith("already "):
            typer.echo(f"No longer pending ({shown.problems[0]}); skipped.")
            return True
        _show_proposal(shown, item.project)
        if shown.interrupted:
            choices = "sq" if shown.problems else "asq"
        else:
            choices = "rsq" if shown.problems else "arsq"
        choice = self._choose(choices)
        if choice == "a":
            done = project_proposals.apply(
                self.root, item.project, item.path, self.actor, shown.sha256, "toulmin decide: a"
            )
            verb = "Ruled" if item.kind == "ruling" else "Created"
            typer.echo(f"{verb}: {done.result}")
            typer.echo(f"Outcome: {project_proposals.outcome_path(item.path)}")
            self.applied += 1
        elif choice == "r":
            reason = _reason()
            project_proposals.reject(
                self.root, item.project, item.path, self.actor, reason, shown.sha256
            )
            typer.echo(f"Rejected; outcome: {project_proposals.outcome_path(item.path)}")
            self.rejected += 1
        return choice != "q"

    def _project_handoff(self, item: Item) -> bool:
        assert item.project is not None
        repository = Repository(self.root)
        raw = repository.path(item.path, "file").read_bytes()
        document = decode(raw, item.path)
        validate_handoff(document, item.project)
        current = digest(
            repository.path(f"projects/{item.project}/PROJECT.md", "file").read_bytes()
        )
        if document.header["base_project_sha256"] != current:
            reason = (
                "superseded by the handoff of this project applied in this run"
                if item.project in self.touched
                else "PROJECT.md changed since drafting; ask the agent to draft again"
            )
            typer.echo(f"Stale: {reason}; skipped.")
            self.skipped += 1
            return True
        typer.echo(f"Project: {item.project}")
        typer.echo(f"Draft: {item.path}")
        typer.echo(f"Next step: {document.header['next_step']}")
        decisions = document.header.get("recent_decisions") or []
        typer.echo("Recent decisions: " + (", ".join(map(str, decisions)) or "none"))
        typer.echo("")
        typer.echo(document.body.rstrip("\n"))
        typer.echo("")
        typer.echo(
            "Confirming records this session and updates PROJECT.md recent_decisions, "
            "next_step and last_handoff only."
        )
        choice = self._choose("asq")
        if choice == "a":
            record = apply_handoff(self.root, item.project, item.path, self.actor, True)
            typer.echo(f"Record: {record.relative_to(repository.root).as_posix()}")
            self.applied += 1
            self.touched.add(item.project)
        return choice != "q"


def _show_proposal(shown: project_proposals.Preview, project: str) -> None:
    typer.echo(f"Project: {project}")
    if shown.interrupted:
        typer.echo("An earlier application of this proposal started but did not finish.")
        if shown.recovered is not None:
            typer.echo(
                f"It already produced {shown.recovered}; apply only records that, changing "
                "nothing else."
            )
        else:
            typer.echo("Nothing it would have produced was found; apply runs it now.")
    if shown.kind != "ruling" and shown.target is not None and shown.recovered is None:
        typer.echo(f"Would create: {shown.target} (the ID is assigned when applied)")
    change = shown.change
    if change is not None:
        line = f"Ruling on: {change.object_id}"
        if change.status != change.previous_status:
            line += f" ({change.previous_status} -> {change.status})"
        typer.echo(line)
        if change.decision is not None:
            typer.echo(f"Decision: {change.decision}")
        if change.sections:
            typer.echo("Adds to sections: " + ", ".join(change.sections))
        if change.links:
            typer.echo("Sets: " + "; ".join(change.links))
    typer.echo("")
    typer.echo(shown.text.rstrip("\n"))
    typer.echo("")
    for problem in shown.problems:
        typer.echo(f"Problem: {problem}")
    if shown.kind == "ruling":
        typer.echo("The Why section is shown to you only; it is not written to the object.")


def decide_command(
    root: Annotated[Path, root_option("Research workbench root.")] = Path("."),
    actor: Annotated[
        str | None,
        typer.Option(
            "--confirmed-by", help="Deciding researcher; defaults to $TOULMIN_ACTOR, then config."
        ),
    ] = None,
) -> None:
    """Decide everything awaiting you, one item at a time, in your own terminal.

    Shows each pending workspace change, child creation, project proposal (object draft or
    ruling under projects/NAME/runs/proposals/) and handoff draft with its preview, then asks
    apply / reject / skip / quit. Skipped items stay pending.
    """
    try:
        found = inventory(root)
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    for line in found.ignored:
        typer.echo(f"Not offered: {line}")
    if found.stale:
        typer.echo(
            f"Not offered: {found.stale} stale handoff draft(s); `toulmin status` shows them."
        )
    if not found.items:
        typer.echo("Nothing awaits your decision.")
        return
    typer.echo(f"Awaiting your decision: {len(found.items)} item(s).")
    if not _interactive():
        for item in found.items:
            typer.echo(f"  {LABEL[item.kind]}: {item.path}")
        typer.echo("Run `toulmin decide` in your own terminal to decide them; nothing changed.")
        return
    who = resolve_actor(actor)
    if who is None:
        raise typer.BadParameter(f"required: {ACTOR_HINT}", param_hint="--confirmed-by")
    typer.echo(f"Deciding as: {who}. Skip leaves an item pending.")
    run = Run(root, who)
    remaining = 0
    for index, item in enumerate(found.items, 1):
        typer.echo(f"\n[{index}/{len(found.items)}] {LABEL[item.kind]}: {item.path}")
        try:
            if not run.decide(item):
                remaining = len(found.items) - index
                break
        except (OSError, ValueError) as error:
            typer.echo(f"Error: {error}", err=True)
            typer.echo("This item is unchanged and stays pending.")
            run.failed += 1
    typer.echo(
        f"\nApplied: {run.applied} | Rejected: {run.rejected} | Skipped: {run.skipped} | "
        f"Failed: {run.failed}" + (f" | Not shown: {remaining}" if remaining else "")
    )
    if run.skipped or run.failed or remaining:
        typer.echo("Undecided items stay pending; run `toulmin decide` again to continue.")
    if run.failed:
        raise typer.Exit(1)
