"""``toulmin decide`` (WX4): one terminal walk through everything awaiting the researcher.

Each item is shown with the preview its own command prints, then decided one at a time:
apply, reject (packets only), skip or quit. Decisions call the existing protocol
functions with the researcher's actor; nothing is decided in bulk. Like every other
confirming command, this relies on being run by the researcher, not by an agent.
"""

import json
import re
import shutil
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

import typer

from toulmin.application.aoe import AoEWorkspace, agent_command
from toulmin.application.build import external_states, project_map
from toulmin.cli import project as project_cli
from toulmin.cli import workspace as workspace_cli
from toulmin.cli.aoe import handoff_preview, handoff_result
from toulmin.cli.initialize import workspace_setup
from toulmin.cli.settings import ACTOR_HINT, resolve_actor, root_option
from toulmin.cli.terminal import colour_enabled, interactive, paint
from toulmin.core.atomic import digest
from toulmin.core.codec import decode
from toulmin.core.handoffs import validate_handoff
from toulmin.core.identifiers import validate_project_name
from toulmin.core.project_proposals import Recommendation
from toulmin.core.repository import Repository
from toulmin.core.schema import SEVERITIES
from toulmin.core.workspace import CHARTER_FILE
from toulmin.protocols import project_creation, project_proposals, workspace_change
from toulmin.protocols import workspace_handoff as workspace_handoffs
from toulmin.protocols.build import build_facts, import_records, verification_facts
from toulmin.protocols.build_import import read_record
from toulmin.protocols.handoff import apply_handoff
from toulmin.protocols.labels import short_label
from toulmin.protocols.proposal_summary import proposal_summary
from toulmin.protocols.proposal_view import ProposalView, plain_problem, proposal_view
from toulmin.protocols.research_map import AGENT, YOU
from toulmin.protocols.synthesis import synthesis_groups
from toulmin.protocols.workspace_state import RootState, workspace_status

LABEL = {
    "change": "Workspace change",
    "onboarding": "Existing project onboarding",
    "context-change": "Project context change",
    "creation": "Child creation",
    "handoff": "Workspace handoff",
    "object": "Object draft",
    "ruling": "Ruling proposal",
    "intake": "Intake recommendation",
    "review": "Review round request",
    "brief": "Brief proposal",
    "stage": "Stage proposal",
    "build": "Build request",
    "task-request": "Engineering task",
    "build-import": "Chief result ready",
    "build-verify": "Verify",
    "project-handoff": "Project handoff",
}
WORDS = {"a": "apply", "r": "reject", "s": "skip", "q": "quit", "v": "view all"}
YES_NO = {"y": "yes", "n": "no"}
NOTICE_ITEMS = 8  # a notice is one line; longer lists end with "and N more"
# Per draft label of an intake recommendation (H4).
LABEL_WORDS = {
    "a": "as recommended",
    "t": "take",
    "o": "other severity",
    "r": "reject",
    "d": "duplicate of O-…",
    "s": "skip",
    "q": "quit",
}


@dataclass(frozen=True)
class Item:
    kind: str  # a LABEL key
    path: str
    project: str | None = None
    spec: str | None = None  # build import or verification

    @property
    def description(self) -> str:
        return (
            f"Verify {self.path}"
            if self.kind == "build-verify"
            else f"{LABEL[self.kind]}: {self.path}"
        )


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
        from toulmin.protocols.engineering_tasks import task_inventory

        tasks, task_errors = task_inventory(repository.root, name)
        items += [Item("task-request", path, name) for path in tasks]
        ignored += list(task_errors)
        kinds = {k: k for k in ("ruling", "intake", "review", "brief", "stage", "build")}
        items += [Item(kinds.get(item.kind, "object"), item.path, name) for item in found.items]
        ignored += [
            f"{path}: not named KIND-YYYYMMDDTHHMMSSZ[-name].md" for path in found.unrecognized
        ]
        ignored += list(found.errors)
        try:
            builds = build_facts(repository.root, name, external_states(repository.root, name))
        except (OSError, ValueError) as error:
            ignored.append(f"Chief builds for {name}: {error}")
            continue
        for fact in builds:
            if fact.task_id is None or fact.imported:
                continue
            task = fact.task
            if fact.archive is None and (
                task is None or task.error is not None or task.state not in {"done", "abandoned"}
            ):
                continue
            if fact.archive is not None:
                saved = read_record(repository, fact.archive)
                state, verdict = saved.state, saved.verdict
            else:
                assert task is not None and task.state is not None
                state, verdict = task.state, task.review.verdict
            label = f"{fact.spec} ({fact.task_id}, {state}, review {verdict or 'not reported'})"
            items.append(Item("build-import", label, name, fact.spec))
        try:
            verifies = verification_facts(repository, name, import_records(repository, name))
            for spec, verification in verifies.items():
                if not verification.available:
                    continue
                from toulmin.application.build_verify import prepare_verification

                shown = prepare_verification(repository.root, name, spec)
                items.append(Item("build-verify", shown.label, name, spec))
        except (OSError, ValueError) as error:
            ignored.append(f"Verification for {name}: {error}")
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


def _onboarding_creation(repository: Repository, relative: str) -> bool:
    from toulmin.core.workspace_onboarding import PACKET_DIR as OUTER
    from toulmin.core.workspace_onboarding import owners

    if owners(repository, relative) or repository.path(f"{relative}/onboarding").exists():
        return True
    creation = project_creation.load(repository.root, relative)
    if OUTER.fullmatch(creation.packet.input_path.rsplit("/", 1)[0]):
        return True
    return (
        re.fullmatch(r"runs/drafts/onboard-[0-9a-f]{32}\.md", creation.packet.input_path)
        is not None
    )


def inventory(root: Path) -> Inventory:
    """Everything awaiting a decision, in the order decide shows it."""
    report = workspace_status(root, workspace_setup())
    state = report.root.state
    if state not in {RootState.WORKSPACE, RootState.LEGACY}:
        raise ValueError(f"{report.root.root}: not a Toulmin workbench; nothing to decide")
    repository = Repository(report.root.root)
    from toulmin.core.workspace_journal import pending as journal_pending
    from toulmin.core.workspace_journal import read_intent

    recovery_record = read_intent(repository).record if journal_pending(repository) else None
    pending = [item for item in report.proposals if item.disposition == "pending"]
    items = [Item("change", item.path) for item in pending if item.kind == "change"]
    items += [Item("onboarding", item.path) for item in pending if item.kind == "onboarding"]
    items += [
        Item("creation", item.path)
        for item in pending
        if item.kind == "creation" and not _onboarding_creation(repository, item.path)
    ]
    items += [
        Item("handoff", item.path) for item in report.handoffs if item.disposition == "pending"
    ]
    stale = sum(item.disposition == "stale" for item in report.handoffs)
    repository = Repository(report.root.root)
    proposals, ignored = _project_proposals(repository)
    from toulmin.protocols import context_change, onboarding
    from toulmin.protocols.workspace_change import receipt_for

    for pattern, kind, packet_directory, loader in (
        ("*-onboard-*", "onboarding", onboarding.DIRECTORY, onboarding.load),
        ("*-context-*", "context-change", context_change.DIRECTORY, context_change.load),
    ):
        for folder in sorted(repository.path("runs").glob(pattern)):
            relative = folder.relative_to(repository.root).as_posix()
            # Task/native context archives are not sealed change packets. Classify
            # by the protocol grammar first; genuine incomplete packets still report
            # missing dependencies through the normal validation below.
            if not packet_directory.fullmatch(relative):
                continue
            if any(
                item.path == relative and item.kind == "onboarding" for item in report.proposals
            ):
                if recovery_record == f"{relative}/packet.md" and not any(
                    item.path == relative for item in items
                ):
                    items.append(Item("onboarding", relative))
                continue
            try:
                seal = repository.path(f"{relative}/seal", "file").read_text().strip()
                if (
                    receipt_for(repository, relative, seal) is not None
                    and recovery_record != f"{relative}/packet.md"
                ):
                    continue
                loaded = loader(repository.root, relative)
                items.append(Item(kind, relative, loaded.project))
            except (OSError, ValueError) as error:
                ignored.append(str(error))
    root_tasks = repository.path("runs/proposals")
    if root_tasks.exists():
        from toulmin.protocols.engineering_tasks import read_outcome

        for task in sorted(root_tasks.glob("task-*.md")):
            if task.name.endswith(".outcome.md"):
                continue
            relative = task.relative_to(repository.root).as_posix()
            try:
                marker = read_outcome(repository, relative, digest(task.read_bytes()))
                if marker is None or marker.disposition == "applying":
                    items.append(Item("task-request", relative))
            except (OSError, ValueError) as error:
                ignored.append(str(error))
    projects, project_stale = _project_handoffs(repository)
    return Inventory(tuple(items + proposals + projects), stale + project_stale, tuple(ignored))


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _ask(choices: str, words: dict[str, str] = WORDS, default: str = "s") -> str:
    text = " / ".join(f"[{styled(letter, 'bold')}]{words[letter][1:]}" for letter in choices)
    while True:
        answer = str(typer.prompt(text, default=default)).strip().lower()
        letter = answer[:1]
        if letter in choices and answer in {letter, words[letter]}:
            return letter
        typer.echo("Choose one of: " + ", ".join(words[letter] for letter in choices))


def _reason(default: str | None = None) -> str:
    while True:
        reason = str(typer.prompt("Reason for rejecting (it is recorded)", default=default)).strip()
        if reason:
            return reason


def _severity() -> str:
    while True:
        answer = str(typer.prompt("Severity (fatal / major / minor)")).strip().lower()
        if answer in SEVERITIES:
            return answer


def _advice(advice: Recommendation) -> str:
    if advice.outcome == "take":
        return "take" + (f" as {advice.severity}" if advice.severity else "")
    if advice.outcome == "partly":
        return f"partly, as {advice.object} (written by hand)"
    if advice.outcome == "duplicate":
        return f"duplicate of {advice.object}"
    return "reject"


@dataclass
class Run:
    root: Path
    actor: str
    applied: int = 0
    rejected: int = 0
    skipped: int = 0
    failed: int = 0
    partial: int = 0  # intake recommendations with labels still undecided (H4)
    rescan: bool = False
    charter_changed: bool = False
    handoff_applied: bool = False
    touched: set[str] = field(default_factory=set)  # projects whose handoff was applied
    staged: set[str] = field(default_factory=set)  # projects whose stage was ruled (H5)
    notes: dict[str, list[str]] = field(default_factory=dict)  # per project, in order (R3)
    full: bool = False  # UX6: print every proposal in full instead of its summary
    position: str = ""  # "[2/5]" of the item being shown, for its header

    def _note(self, project: str, text: str) -> None:
        self.notes.setdefault(project, []).append(text)

    def decide(self, item: Item) -> bool:
        """Show and decide one item; False means quit."""
        handler = {
            "change": self._change,
            "onboarding": self._context_packet,
            "context-change": self._context_packet,
            "creation": self._creation,
            "handoff": self._handoff,
            "object": self._proposal,
            "ruling": self._proposal,
            "intake": self._intake,
            "review": self._review,
            "brief": self._proposal,
            "stage": self._proposal,
            "build": self._build,
            "task-request": self._task_request,
            "build-import": self._build_import,
            "build-verify": self._build_verify,
            "project-handoff": self._project_handoff,
        }[item.kind]
        return handler(item)

    def _choose(self, choices: str) -> str:
        choice = _ask(choices)
        if choice == "s":
            self.skipped += 1
        return choice

    def _context_packet(self, item: Item) -> bool:
        from toulmin.cli.workspace import _v2
        from toulmin.protocols import context_change, onboarding

        if _v2(self.root, item.path):
            from toulmin.application import workspace_onboarding
            from toulmin.protocols import workspace_onboarding as packets

            shown_v2 = workspace_onboarding.apply(self.root, item.path, None)
            typer.echo(packets.preview(self.root, shown_v2.loaded))
            for problem in shown_v2.problems:
                typer.echo(f"Problem: {problem}")
            choice = self._choose(
                "asq" if shown_v2.status == "incomplete" else "rsq" if shown_v2.problems else "arsq"
            )
            if choice == "a":
                done_v2 = workspace_onboarding.apply(
                    self.root,
                    item.path,
                    self.actor,
                    confirmed=True,
                    expect_seal=shown_v2.loaded.seal,
                    approval_text="toulmin decide: a",
                )
                typer.echo(f"{done_v2.status}: workspace publication")
                self.applied += 1
            elif choice == "r":
                workspace_onboarding.reject(
                    self.root, item.path, self.actor, _reason(), expect_seal=shown_v2.loaded.seal
                )
                self.rejected += 1
            return choice != "q"

        protocol = onboarding if item.kind == "onboarding" else context_change
        shown = protocol.apply(self.root, item.path, None, confirmed=False)
        if shown.status not in {"preview", "incomplete"}:
            typer.echo(f"No longer pending ({shown.status}); skipped.")
            return True
        typer.echo(shown.loaded.body)
        for problem in shown.problems:
            typer.echo(f"Problem: {problem}")
        choices = "asq" if shown.status == "incomplete" else ("rsq" if shown.problems else "arsq")
        choice = self._choose(choices)
        if choice == "a":
            done = protocol.apply(
                self.root, item.path, self.actor, confirmed=True, approval_text="toulmin decide: a"
            )
            typer.echo(f"{done.status}: {done.loaded.project}")
            self.applied += 1
            if item.kind == "context-change":
                self._note(done.loaded.project, "updated confirmed project context")
        elif choice == "r":
            protocol.reject(self.root, item.path, self.actor, _reason())
            self.rejected += 1
        return choice != "q"

    def _task_request(self, item: Item) -> bool:
        document = decode(Repository(self.root).path(item.path, "file").read_bytes(), item.path)
        if document.header.get("schema_version") == 2:
            from toulmin.application import scoped_tasks
            from toulmin.core.scope import Scope

            scope = Scope(item.project)
            shown_v2 = scoped_tasks.prepare(self.root, scope, item.path)
            typer.echo(json.dumps(shown_v2.contract, indent=2))
            typer.echo(
                "Apply delegates a bounded engineering task; no "
                "scientific approval or worker kickoff is implied."
            )
            choice = self._choose("asq" if shown_v2.marker is not None else "arsq")
            if choice == "a":
                done_v2 = scoped_tasks.apply(
                    self.root, scope, shown_v2, self.actor, "toulmin decide: a", report=typer.echo
                )
                typer.echo(f"Task outcome: {done_v2.disposition}: {done_v2.result}")
                self.applied += 1
            elif choice == "r":
                scoped_tasks.reject(self.root, scope, item.path, self.actor, _reason())
                self.rejected += 1
            return choice != "q"
        from toulmin.application.engineering_tasks import apply_task, prepare_task, reject_task

        assert item.project is not None
        shown = prepare_task(self.root, item.project, item.path)
        typer.echo(json.dumps(shown.plan.contract, indent=2, ensure_ascii=False))
        for problem in shown.problems:
            typer.echo(f"Problem: {problem}")
        typer.echo("Apply delegates this engineering task; no research conclusion is approved.")
        choices = (
            "sq"
            if shown.interrupted and shown.problems
            else ("asq" if shown.interrupted else "rsq" if shown.problems else "arsq")
        )
        choice = self._choose(choices)
        if choice == "a":
            done = apply_task(
                self.root, item.project, shown, self.actor, "toulmin decide: a", report=typer.echo
            )
            typer.echo(f"Task outcome: {done.disposition}: {done.result}")
            if done.disposition == "failed":
                self.failed += 1
            else:
                self.applied += 1
            self._note(item.project, f"engineering task {done.disposition}: {done.result}")
        elif choice == "r":
            reject_task(self.root, item.project, item.path, self.actor, _reason())
            self.rejected += 1
        return choice != "q"

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
        _show_proposal(self.root, shown, item.project, self.position, full=self.full)
        if shown.interrupted:
            choices = "sq" if shown.problems else "asq"
        else:
            choices = "rsq" if shown.problems else "arsq"
        choice = self._choose(choices if self.full else choices[:-1] + "vq")
        while choice == "v":
            typer.echo(shown.text.rstrip("\n"))
            typer.echo("")
            choice = self._choose(choices)
        if choice == "a":
            done = project_proposals.apply(
                self.root, item.project, item.path, self.actor, shown.sha256, "toulmin decide: a"
            )
            verb = {"ruling": "Ruled", "brief": "Updated", "stage": "Stage ruled"}
            typer.echo(styled(f"{verb.get(item.kind, 'Created')}: {done.result}", "green"))
            typer.echo(f"Outcome: {project_proposals.outcome_path(item.path)}")
            self.applied += 1
            self._note(item.project, f"applied {_name(item.path)} ({done.result})")
            if item.kind == "stage":
                self.staged.add(item.project)
                assert shown.stage is not None
                _hygiene(self.root, item.project, shown.stage.stage)
        elif choice == "r":
            reason = _reason()
            project_proposals.reject(
                self.root, item.project, item.path, self.actor, reason, shown.sha256
            )
            typer.echo(
                styled(f"Rejected; outcome: {project_proposals.outcome_path(item.path)}", "yellow")
            )
            self.rejected += 1
            self._note(item.project, f"rejected {_name(item.path)}")
        return choice != "q"

    def _reject_proposal(self, item: Item, shown: project_proposals.Preview) -> None:
        assert item.project is not None
        reason = _reason()
        project_proposals.reject(
            self.root, item.project, item.path, self.actor, reason, shown.sha256
        )
        typer.echo(f"Rejected; outcome: {project_proposals.outcome_path(item.path)}")
        self.rejected += 1
        self._note(item.project, f"rejected {_name(item.path)}")

    def _intake(self, item: Item) -> bool:
        assert item.project is not None
        shown = project_proposals.preview(self.root, item.project, item.path)
        if shown.problems and shown.problems[0].startswith("already "):
            typer.echo(f"No longer pending ({shown.problems[0]}); skipped.")
            return True
        typer.echo(f"Project: {item.project}")
        if shown.intake is None:
            typer.echo("")
            typer.echo(shown.text.rstrip("\n"))
            typer.echo("")
            for problem in shown.problems:
                typer.echo(f"Problem: {problem}")
            choice = self._choose("rsq")
            if choice == "r":
                self._reject_proposal(item, shown)
            return choice != "q"
        intake = shown.intake
        state = intake.state
        recommended = {entry.label: entry for entry in intake.recommendation.items}
        typer.echo(f"Review output: {intake.recommendation.output} ({state.run})")
        grouped, unreadable = synthesis_groups(self.root, item.project, state.run)
        for problem in unreadable:
            typer.echo(f"Note: {problem}")
        for label, entry in state.recorded.items():
            target = f" of {entry['object']}" if entry["outcome"] == "duplicate" else ""
            typer.echo(f"  {label}: already {entry['outcome']}{target}")
        if not intake.remaining:
            typer.echo("Every draft label already has an outcome in intake.md.")
            choice = self._choose("asq")
            if choice == "a":
                self._record_intake(item, shown, {}, {}, {})
            return choice != "q"
        typer.echo(
            "Decide each draft label; the recommendation is the agent's, the choice is yours. "
            "Choices are recorded when this output's walk ends; quit records nothing for it."
        )
        take: dict[str, str | None] = {}
        reject: dict[str, str] = {}
        partly: dict[str, str] = {}
        duplicate: dict[str, str] = {}
        duplicate_reasons: dict[str, str] = {}
        for index, label in enumerate(intake.remaining, 1):
            draft, advice = state.drafts[label], recommended[label]
            typer.echo(f"\n  ({index}/{len(intake.remaining)}) {label} -> {draft.target} "
                       f"({draft.severity}): {draft.content}")  # fmt: skip
            typer.echo(f"    Grounds: {draft.grounds}")
            if draft.uncertainty:
                typer.echo(f"    Uncertainty: {draft.uncertainty}")
            for line in grouped.get(label, ()):
                typer.echo(f"    Synthesis: {line}")
            typer.echo(f"    Recommended: {_advice(advice)} - {advice.reason}")
            choice = _ask("atodrsq", LABEL_WORDS)
            if choice == "q":
                typer.echo("Nothing recorded for this output; it stays pending.")
                return False
            if choice == "s":
                continue
            if choice == "a":
                if advice.outcome == "take":
                    take[label] = advice.severity
                elif advice.outcome == "reject":
                    reject[label] = advice.reason
                elif advice.outcome == "partly":
                    assert advice.object is not None
                    partly[label] = advice.object
                else:
                    assert advice.object is not None
                    duplicate[label] = advice.object
                    duplicate_reasons[label] = advice.reason
            elif choice == "t":
                take[label] = None
            elif choice == "o":
                take[label] = _severity()
            elif choice == "d":
                duplicate[label] = str(
                    typer.prompt(
                        "Existing Objection ID",
                        default=advice.object if advice.outcome == "duplicate" else None,
                    )
                ).strip()
                if advice.outcome == "duplicate":
                    duplicate_reasons[label] = advice.reason
            else:
                default = advice.reason if advice.outcome == "reject" else None
                reject[label] = _reason(default)
        if not (take or reject or partly or duplicate):
            typer.echo("Nothing chosen; the recommendation stays pending.")
            self.skipped += 1
            return True
        self._record_intake(item, shown, take, reject, partly, duplicate, duplicate_reasons)
        return True

    def _record_intake(
        self,
        item: Item,
        shown: project_proposals.Preview,
        take: dict[str, str | None],
        reject: dict[str, str],
        partly: dict[str, str],
        duplicate: dict[str, str] | None = None,
        duplicate_reasons: dict[str, str] | None = None,
    ) -> None:
        assert item.project is not None
        result, done = project_proposals.record_intake(
            self.root, item.project, item.path, self.actor, shown.sha256, take, reject, partly,
            "toulmin decide: a",
            duplicate=duplicate, duplicate_reasons=duplicate_reasons,
        )  # fmt: skip
        if result is not None:
            for line in result.lines:
                target = (
                    (" of " if line.outcome.endswith("duplicate") else " as ") + line.object_id
                    if line.object_id
                    else ""
                )
                typer.echo(f"{line.label}: {line.outcome}{target} ({result.run})")
            outcomes = ", ".join(
                f"{line.label} {line.outcome}" + (f" {line.object_id}" if line.object_id else "")
                for line in result.lines
            )
            self._note(item.project, f"intake {result.run}: {outcomes}")
            record = result.record.relative_to(Repository(self.root).root).as_posix()
            typer.echo(f"Record: {record}")
        if done is not None:
            typer.echo(
                f"Every label has an outcome; outcome: {project_proposals.outcome_path(item.path)}"
            )
            self.applied += 1
        else:
            typer.echo("Labels you skipped stay undecided; the recommendation stays pending.")
            self.partial += 1

    def _build_verify(self, item: Item) -> bool:
        from toulmin.application.build_verify import apply_verification, prepare_verification
        from toulmin.cli.build import show_verification

        assert item.project is not None and item.spec is not None
        shown = prepare_verification(self.root, item.project, item.spec)
        show_verification(shown)
        choice = self._choose("asq")
        if choice == "a":
            done = apply_verification(self.root, item.project, shown, self.actor)
            typer.echo(
                f"Verification {'passed' if done.passed else 'failed'}: {done.run}; "
                f"{len(done.proposals)} follow-up proposal(s)."
            )
            self.applied += 1  # a failed check is still a completed, archived verification Run
            self.rescan = True
            self._note(
                item.project,
                f"verified {done.spec} at {done.head[:12]}: "
                f"{'passed' if done.passed else 'failed'} ({done.run})",
            )
        return choice != "q"

    def _build_import(self, item: Item) -> bool:
        from toulmin.application.build_import import apply_import, prepare_import
        from toulmin.cli.build import show_import

        assert item.project is not None and item.spec is not None
        shown = prepare_import(self.root, item.project, item.spec)
        show_import(shown)
        choice = self._choose("asq")
        if choice == "a":
            done = apply_import(self.root, item.project, shown, self.actor)
            typer.echo(
                f"Imported Chief task {done.task_id} as {done.run}; "
                f"{len(done.proposals)} follow-up proposal(s)."
            )
            self.applied += 1
            self.rescan = True
            self._note(item.project, f"imported Chief task {done.task_id} ({done.run})")
        return choice != "q"

    def _build(self, item: Item) -> bool:
        from toulmin.adapters.chief import ChiefClient
        from toulmin.application.build import FOLDER_TRUST_NOTICE, apply_build, prepare_build

        assert item.project is not None
        prepared = prepare_build(self.root, item.project, item.path)
        shown = prepared.preview
        if shown.problems and shown.problems[0].startswith("already "):
            typer.echo(f"No longer pending ({shown.problems[0]}); skipped.")
            return True
        typer.echo(f"Project: {item.project}")
        if self.full:
            typer.echo(shown.text.rstrip("\n"))
        else:
            typer.echo("\n".join(summary_lines(shown.text, terminal_width())))
        plan = shown.build
        if plan is not None:
            typer.echo(f"Chief task: {plan.task_id}")
            typer.echo(
                "Chief confirms the worker's folder-trust prompt: "
                + ("yes" if plan.request.trust else "no")
            )
            if not plan.request.trust:
                typer.echo(FOLDER_TRUST_NOTICE.format(task_id=plan.task_id))
            if plan.request.command is not None:
                typer.echo(
                    f"Worker launch command: {plan.request.command} "
                    f"(instead of Chief's default for {plan.request.tool})"
                )
            if self.full:
                typer.echo("Full frozen Chief contract:")
                typer.echo(json.dumps(plan.contract, ensure_ascii=False, indent=2))
            else:
                typer.echo("Frozen Chief contract (v views all of it, with the worker's goal):")
                for line in contract_lines(plan.contract):
                    typer.echo(line)
            if plan.note is not None:
                typer.echo(f"Note: {plan.note}")
            if plan.checks_match:
                typer.echo("Checks match the Spec's commands.")
            else:
                typer.echo("Check mismatch: request checks differ from the Spec's commands.")
                typer.echo("  Spec commands: " + json.dumps(plan.spec_commands, ensure_ascii=False))
                typer.echo(
                    "  Request checks (frozen on apply): "
                    + json.dumps(plan.request.checks, ensure_ascii=False)
                )
            if plan.gate is not None:
                typer.echo(
                    f"G3 item [{'x' if plan.gate.met else ' '}]: "
                    f"{plan.gate.label}: {plan.gate.detail}"
                )
            if prepared.recovered:
                typer.echo(
                    "Interrupted apply: existing task matches the frozen request and repository; "
                    "apply only records it."
                )
            elif shown.interrupted:
                typer.echo("Interrupted apply: no task found; apply starts the frozen request.")
            if not prepared.recovered:
                typer.echo("Apply starts Chief now.")
            typer.echo("Spec status stays unchanged. chief watch must be running.")
        for problem in prepared.problems:
            typer.echo(f"Problem: {problem}")
        choices = (
            ("sq" if prepared.problems else "asq")
            if shown.interrupted
            else ("rsq" if prepared.problems else "arsq")
        )
        choice = self._choose(choices if self.full else choices[:-1] + "vq")
        while choice == "v":
            typer.echo(shown.text.rstrip("\n"))
            if plan is not None:
                typer.echo("Full frozen Chief contract:")
                typer.echo(json.dumps(plan.contract, ensure_ascii=False, indent=2))
            choice = self._choose(choices)
        if choice == "a":
            done = apply_build(
                self.root,
                item.project,
                prepared,
                self.actor,
                "toulmin decide: a",
                report=typer.echo,
            )
            typer.echo(f"Outcome: {project_proposals.outcome_path(item.path)}")
            if done.disposition == "failed":
                typer.echo(
                    f"Chief failed: {done.reason}; archive kept. Draft a new request to retry."
                )
                self.failed += 1
            else:
                assert plan is not None
                started = f"Started/recorded: {done.result}."
                try:
                    task = ChiefClient(self.root, prepared.config).task(plan.task_id)
                    if task is None:
                        raise ValueError("task.json missing; kickoff not reported")
                    if task.get("repo") is not None and task["repo"] != str(
                        Path(plan.request.repo).resolve()
                    ):
                        raise ValueError("task repository differs; kickoff not confirmed")
                except (OSError, ValueError) as error:
                    typer.echo(started)
                    typer.echo(f"Chief state not read after apply: {error}")
                else:
                    if "kickoff_at" not in task:
                        typer.echo(started)
                        typer.echo(
                            "Not started yet: accept the worker's prompt in AoE, then run "
                            f"`chief kickoff {plan.task_id}`."
                        )
                    else:
                        typer.echo(
                            f"{started} Keep chief watch running; approve tests in chief inbox."
                        )
                self.applied += 1
                self._note(item.project, f"applied {_name(item.path)} ({done.result})")
        elif choice == "r":
            self._reject_proposal(item, shown)
        return choice != "q"

    def _review(self, item: Item) -> bool:
        from toulmin.adapters.review import execute_round, prepare_round

        assert item.project is not None
        shown = project_proposals.preview(self.root, item.project, item.path)
        if shown.problems and shown.problems[0].startswith("already "):
            typer.echo(f"No longer pending ({shown.problems[0]}); skipped.")
            return True
        typer.echo(f"Project: {item.project}")
        typer.echo("")
        typer.echo(shown.text.rstrip("\n"))
        typer.echo("")
        if shown.interrupted:
            typer.echo("This round started earlier and did not finish; it is never started again.")
            typer.echo("Runs archived since it started: " + (", ".join(shown.runs) or "none"))
            typer.echo("Apply records them as this request's result; no session starts.")
            choice = self._choose("asq")
            if choice == "a":
                marker = project_proposals.interrupted_marker(self.root, item.project, item.path)
                runs = ", ".join(shown.runs) or "none"
                project_proposals.finish_review(
                    self.root, item.project, marker, f"interrupted; Runs archived: {runs}"
                )
                typer.echo(f"Recorded; outcome: {project_proposals.outcome_path(item.path)}")
                self.applied += 1
            return choice != "q"
        problems = list(shown.problems)
        previewed = None
        request = shown.review
        if request is not None and not problems:
            try:
                previewed = prepare_round(
                    self.root,
                    item.project,
                    request.personas,
                    request.models,
                    request.claims,
                    typer.echo,
                    profile=request.profile,
                    synthesizer=request.synthesizer,
                )
            except (OSError, ValueError) as error:
                problems.append(str(error))
        for problem in problems:
            typer.echo(f"Problem: {problem}")
        if not problems:
            typer.echo("Apply starts these sessions now in this terminal (uses quota).")
        choice = self._choose("rsq" if problems else "arsq")
        if choice == "a":
            assert request is not None
            # Plan again so a changed configuration fails before the marker is written.
            planned = prepare_round(
                self.root,
                item.project,
                request.personas,
                request.models,
                request.claims,
                lambda _: None,
                profile=request.profile,
                synthesizer=request.synthesizer,
            )
            if previewed is None or planned.approval_key != previewed.approval_key:
                typer.echo(
                    "Review configuration or inputs changed since preview; nothing started. "
                    "Run toulmin decide again to review the new plan."
                )
                return True
            marker = project_proposals.begin_review(
                self.root, item.project, item.path, self.actor, shown.sha256, "toulmin decide: a"
            )
            result = execute_round(planned, self.actor, typer.echo)
            project_proposals.finish_review(self.root, item.project, marker, result.summary())
            typer.echo(f"Round: {result.summary()}")
            self._note(item.project, f"review round run ({result.summary()})")
            typer.echo(f"Outcome: {project_proposals.outcome_path(item.path)}")
            self.applied += 1
        elif choice == "r":
            self._reject_proposal(item, shown)
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
                else "PROJECT.md changed by the stage ruling in this run; ask the agent to "
                "draft again"
                if item.project in self.staged
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
            self._note(item.project, "applied the handoff")
        return choice != "q"


def _name(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _hygiene(root: Path, project: str, stage: str) -> None:
    """Keep coordination continuous; context replacement is explicit and optional (R10)."""
    typer.echo(f"Stage is now {stage}. Continue in the current project conversation.")
    if stage == "critique":
        typer.echo(
            f"  Next: `toulmin review {project} --dry-run`, then ask the agent for "
            f"`toulmin draft review {project}`; approve it in `toulmin decide` to start "
            "quota-consuming independent sessions."
        )
    else:
        typer.echo(f"  Refresh with `toulmin map {project}` for the next research action.")
    typer.echo(
        "  Optional context management: ask for a handoff draft and apply it with "
        "`toulmin decide` when pausing or choosing a fresh coordinator session."
    )
    try:
        binding = AoEWorkspace(root, project).bound_session()
    except (OSError, ValueError):
        binding = None
    archive = (
        f"aoe -p {binding.profile} session archive {binding.session_id}, then "
        if binding is not None
        else ""
    )
    typer.echo(
        f"  Explicit replacement only: {archive}toulmin open {project} --new-session. "
        "Plain open may resume the existing binding; nothing is archived automatically."
    )


def notice(root: Path, project: str, notes: list[str], stage: str | None) -> str:
    """The one-line message a bound project session receives after decide (R3)."""
    shown = notes[:NOTICE_ITEMS]
    if len(notes) > NOTICE_ITEMS:
        shown.append(f"and {len(notes) - NOTICE_ITEMS} more")
    where = str(root.absolute())
    text = (
        f"Toulmin notice for project {project}: the researcher decided in `toulmin decide`: "
        + "; ".join(shown)
        + ". Reasons are in the .outcome.md files beside each proposal. Before acting, "
        f"refresh your view with `{agent_command('map', project, '--root', where)}`; propose, "
        "never apply."
    )
    if stage == "critique":
        plan = agent_command("review", project, "--root", where, "--dry-run")
        draft = agent_command("draft", "review", project, "--root", where)
        text += (
            f" The stage is now critique: continue as coordinator here; plan with `{plan}`, "
            f"then prepare `{draft}` for researcher approval in `toulmin decide`. Only "
            "approval starts quota-consuming review; reviewers and synthesis stay in fresh "
            "isolated restricted sessions. Handoff or coordinator replacement is optional."
        )
    elif stage is not None:
        text += (
            f" The stage is now {stage}: continue as coordinator here using the refreshed "
            "next moves. Handoff and fresh coordinator sessions are optional context "
            "management; never archive automatically."
        )
    return text


def _wrap_up(run: Run, notify: bool | None) -> None:
    """Close the loop: next moves per decided project, then an optional session notice."""
    for project, notes in run.notes.items():
        typer.echo(f"\nNext for {project} (advice; you rule):")
        try:
            moves = project_map(run.root, project).moves
        except (OSError, ValueError) as error:
            typer.echo(f"  unavailable: {error}")
            moves = ()
        for move in moves:
            who = {YOU: "you", AGENT: "agent"}.get(move.actor, "either")
            typer.echo(f"  {who}: {move.text}")
        try:
            bound = AoEWorkspace(run.root, project).bound_session() is not None
        except (OSError, ValueError):
            bound = False
        if not bound or notify is False:
            continue
        if notify is None:
            typer.echo(
                f"Tell the {project} session what you decided (one line; it may start work)?"
            )
            if _ask("yn", YES_NO, default="n") != "y":
                continue
        stage = None
        if project in run.staged:
            stage = project_map(run.root, project).stage
        message = notice(run.root, project, notes, stage)
        sent, why = AoEWorkspace(run.root, project).notify(message)
        typer.echo(
            f"Notice {why}." if sent else f"Notice not sent: {why}. Tell the agent yourself."
        )


def terminal_width() -> int:
    return max(shutil.get_terminal_size((80, 24)).columns, 40)


def contract_lines(contract: dict[str, Any]) -> list[str]:
    """The contract fields a researcher checks before code runs as them; goal stays behind v."""
    lines = [
        f"  {key}: {contract[key]}"
        for key in ("name", "repo", "tool", "command")
        if key in contract
    ]
    lines.append(f"  checks ({len(contract.get('checks', []))}, run as you on apply and verify):")
    lines += [f"    {check}" for check in contract.get("checks", [])]
    for key in ("protected", "budget", "test_first", "base_branch"):
        if key in contract:
            lines.append(f"  {key}: {json.dumps(contract[key], ensure_ascii=False)}")
    return lines


def summary_lines(text: str, width: int) -> list[str]:
    """UX6: header facts, the main section and Why, each on one line, from the full text."""
    found = proposal_summary(text)
    lines = []
    if found.facts:
        facts = " · ".join(f"{key} {value}" for key, value in found.facts)
        lines.append("  " + short_label(facts, max(width - 2, 20)))
    for name, value in ((found.main or (None, None)), ("Why", found.why)):
        if name and value:
            head = f"  {name}: "
            lines.append(head + short_label(value, max(width - len(head), 20)))
    return lines or ["  (no summary; press v to view all)"]


MAIN_LINES = 6  # the proposal's own text before "v" is needed (E2)
CONTEXT_LINES = 3  # the object it answers or targets (E3)
COLUMN = 10  # label column, as on the project card


def styled(text: str, *styles: str) -> str:
    """Colour only on a terminal with NO_COLOR unset (UX5); otherwise the text unchanged."""
    return paint(text, *styles) if text and colour_enabled() else text


def header(position: str, title: str, project: str | None, width: int) -> str:
    """One rule per item: ``── [2/5] New Claim · core problem ───── project``."""
    left = f"── {position} {title} ".replace("  ", " ")
    right = f" {project}" if project else ""
    fill = max(width - len(left) - len(right), 3)
    if not colour_enabled():
        return left + "─" * fill + right
    return (
        paint("── ", "dim")
        + paint(f"{position} {title}".strip(), "bold")
        + " "
        + paint("─" * fill, "dim")
        + right
    )


def view_lines(view: ProposalView, width: int) -> list[str]:
    """Labelled rows: context, the proposal's content, its effect and why (E1–E3)."""
    lines: list[str] = []
    room = max(width - COLUMN, 20)
    shaped = interactive()  # off a terminal each row stays one exact, uncut line
    for row in view.rows:
        limit = MAIN_LINES if row.main else CONTEXT_LINES if row.label != "Effect" else 4
        body = textwrap.wrap(row.text, room, break_on_hyphens=False) if shaped else [row.text]
        body = body or [""]
        if len(body) > limit:
            body = body[:limit]
            tail = " … (v)"
            body[-1] = short_label(body[-1] + " …", room - len(tail)).rstrip("…").rstrip() + tail
        label = row.label
        if len(label) >= COLUMN:
            lines.append(styled(label, "bold"))
            label = ""
        colour = ("green",) if row.label == "Effect" else ()
        for index, text in enumerate(body):
            head = label.ljust(COLUMN) if index == 0 else " " * COLUMN
            lines.append(styled(head, "bold") + (styled(text, *colour) if colour else text))
    return lines


def problem_lines(root: Path, problems: tuple[str, ...], width: int) -> list[str]:
    """Problems in plain words with the way out (E6)."""
    lines: list[str] = []
    for problem in problems:
        text = "Problem: " + plain_problem(root, problem)
        shaped = textwrap.wrap(text, width, subsequent_indent="  ") if interactive() else [text]
        lines += [styled(line, "red") for line in shaped]
    if problems:
        lines.append("  It cannot be applied as written: reject it with a reason, or ask the agent")
        lines.append("  to fix the draft and decide it again.")
    return lines


def _show_proposal(
    root: Path,
    shown: project_proposals.Preview,
    project: str,
    position: str = "",
    *,
    full: bool = True,
) -> None:
    width = terminal_width()
    view = proposal_view(root, project, shown)
    room = max(width - len(position) - len(project) - 12, 20)
    typer.echo(header(position, short_label(view.title, room), project, width))
    typer.echo(styled(f"{LABEL[item_kind(shown.kind)]}: {shown.path}", "dim"))
    if shown.interrupted:
        typer.echo("An earlier application of this proposal started but did not finish.")
        if shown.recovered is not None:
            typer.echo(
                f"It already produced {shown.recovered}; apply only records that, changing "
                "nothing else."
            )
        else:
            typer.echo("Nothing it would have produced was found; apply runs it now.")
    if shown.done:
        typer.echo("Already ruled before the interruption: " + ", ".join(shown.done))
    if full:
        if (
            shown.kind not in {"ruling", "brief", "stage"}
            and shown.target is not None
            and shown.recovered is None
        ):
            typer.echo(f"Would create: {shown.target} (the ID is assigned when applied)")
        changes = shown.changes or ((shown.change,) if shown.change is not None else ())
        for change in changes:
            line = f"Ruling on: {change.object_id}"
            if change.status != change.previous_status:
                line += f" ({change.previous_status} -> {change.status})"
            typer.echo(line)
        if changes:
            change = changes[0]
            if change.decision is not None:
                typer.echo(f"Decision: {change.decision}")
            if change.sections:
                each = " (each object)" if len(changes) > 1 else ""
                typer.echo("Adds to sections: " + ", ".join(change.sections) + each)
            if change.links:
                typer.echo("Sets: " + "; ".join(change.links))
        typer.echo("")
        typer.echo(shown.text.rstrip("\n"))
    else:
        for line in view_lines(view, width):
            typer.echo(line)
    typer.echo("")
    stage = shown.stage
    if stage is not None and not shown.problems and shown.recovered is None:
        typer.echo(f"Stage: {stage.current} -> {stage.stage}, backed by {shown.decision}")
        gate = shown.gate
        if gate is not None:
            state = {True: "met", False: "not met", None: "unknown"}[gate.met]
            typer.echo(f"{gate.gate} readiness (advice; the ruling is yours): {state}")
            for entry in gate.items:
                detail = f": {entry.detail}" if entry.detail else ""
                typer.echo(f"  [{'x' if entry.met else ' '}] {entry.label}{detail}")
        else:
            typer.echo(f"No gate is defined for entering {stage.stage}.")
    if shown.diff and shown.recovered is None:
        typer.echo("Change:")
        for line in shown.diff:
            typer.echo(f"  {line}")
        typer.echo("")
    for line in problem_lines(root, shown.problems, width):
        typer.echo(line)
    if full and shown.kind in {"ruling", "brief", "stage"}:
        typer.echo("The Why section is shown to you only; it is not written to the target.")


def item_kind(kind: str) -> str:
    """The decide item kind of a proposal kind: object drafts share one."""
    return kind if kind in {"ruling", "brief", "stage"} else "object"


def agenda_title(root: Path, item: Item) -> str:
    """One line per item for the opening overview (E4)."""
    if item.project is not None and item.kind in {"object", "ruling", "brief", "stage"}:
        try:
            shown = project_proposals.preview(root, item.project, item.path)
            if shown.problems and shown.problems[0].startswith("already "):
                return f"{LABEL[item.kind]} (no longer pending)"
            title = proposal_view(root, item.project, shown).title
            return title + (" — cannot be applied as written" if shown.problems else "")
        except (OSError, ValueError):
            return item.description
    name = item.path.rsplit("/", 1)[-1] if item.kind != "build-verify" else item.path
    return f"{LABEL[item.kind]} · {name}" if item.kind != "build-verify" else item.description


def agenda(root: Path, items: list[Item], width: int) -> list[str]:
    """The opening overview: every item numbered as it will be shown, with its project."""
    counts: dict[str, int] = {}
    for item in items:
        counts[LABEL[item.kind]] = counts.get(LABEL[item.kind], 0) + 1
    lines = ["  " + " · ".join(f"{name} {count}" for name, count in counts.items())]
    digits = len(str(len(items)))
    for number, item in enumerate(items, 1):
        where = f"  ({item.project})" if item.project else "  (workspace)"
        lead = f"  {str(number).rjust(digits)}  "
        room = max(width - len(lead) - len(where), 20)
        lines.append(lead + short_label(agenda_title(root, item), room) + styled(where, "dim"))
    return lines


def decide_command(
    root: Annotated[Path, root_option("Research workbench root.")] = Path("."),
    actor: Annotated[
        str | None,
        typer.Option(
            "--confirmed-by", help="Deciding researcher; defaults to $TOULMIN_ACTOR, then config."
        ),
    ] = None,
    workspace: Annotated[
        bool, typer.Option("--workspace", help="Root publications/tasks only.")
    ] = False,
    project: Annotated[
        str | None, typer.Option("--project", help="Existing child proposals only.")
    ] = None,
    notify: Annotated[
        bool | None,
        typer.Option(
            "--notify/--no-notify",
            help="Tell each bound project session what you decided (default: ask per project).",
            show_default=False,
        ),
    ] = None,
    full: Annotated[
        bool,
        typer.Option("--full", help="Print each proposal in full instead of its summary."),
    ] = False,
) -> None:
    """Decide everything awaiting you, one item at a time, in your own terminal.

    Shows each pending workspace change, child creation, project proposal (object draft or
    ruling under projects/NAME/runs/proposals/) and handoff draft with its preview, then asks
    apply / reject / skip / quit. Skipped items stay pending.
    """
    from toulmin.application.workspace_sync import git_state

    if workspace and project is not None:
        raise typer.BadParameter("give --workspace or --project")

    def selected(item: Item) -> bool:
        return (
            item.project is None
            if workspace
            else item.project == project
            if project is not None
            else True
        )

    git_report = git_state(root)
    if git_report and git_report.error:
        typer.echo(git_report.line())
    elif git_report and git_report.warning:
        typer.echo("Warning: " + git_report.warning)
    try:
        collected = inventory(root)
        found = Inventory(
            tuple(item for item in collected.items if selected(item)),
            collected.stale,
            collected.ignored,
        )
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
            typer.echo(f"  {item.description}")
        typer.echo("Run `toulmin decide` in your own terminal to decide them; nothing changed.")
        return
    who = resolve_actor(actor)
    if who is None:
        raise typer.BadParameter(f"required: {ACTOR_HINT}", param_hint="--confirmed-by")
    for line in agenda(root, list(found.items), terminal_width()):
        typer.echo(line)
    typer.echo(f"Deciding as: {who}. Skip leaves an item pending; v shows an item in full.")
    run = Run(root, who, full=full)
    remaining = 0
    queue = list(found.items)
    offered: set[tuple[str, str, str | None]] = set()
    index = 0
    while queue:
        item = queue.pop(0)
        index += 1
        offered.add((item.kind, item.spec or item.path, item.project))
        run.position = f"[{index}/{index + len(queue)}]"
        typer.echo("")
        if item.kind not in {"object", "ruling", "brief", "stage"}:
            title = "Verify" if item.kind == "build-verify" else LABEL[item.kind]
            typer.echo(header(run.position, title, item.project, terminal_width()))
            typer.echo(styled(item.description, "dim"))
        try:
            if not run.decide(item):
                remaining = len(queue)
                break
        except (OSError, ValueError) as error:
            typer.echo(styled(f"Error: {plain_problem(root, str(error))}", "red"), err=True)
            typer.echo("This item is unchanged and stays pending.")
            run.failed += 1
        if run.rescan:
            refreshed = inventory(root)
            queue = [
                item
                for item in refreshed.items
                if selected(item)
                and (item.kind, item.spec or item.path, item.project) not in offered
            ]
            run.rescan = False
    typer.echo(
        f"\nApplied: {run.applied} | Rejected: {run.rejected} | Skipped: {run.skipped} | "
        f"Failed: {run.failed}"
        + (f" | Partly recorded: {run.partial}" if run.partial else "")
        + (f" | Not shown: {remaining}" if remaining else "")
    )
    if run.skipped or run.failed or run.partial or remaining:
        typer.echo("Undecided items stay pending; run `toulmin decide` again to continue.")
    _wrap_up(run, notify)
    if run.failed:
        raise typer.Exit(1)
