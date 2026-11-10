"""``toulmin decide`` (WX4): one terminal walk through everything awaiting the researcher.

Each item is shown with the preview its own command prints, then decided one at a time:
apply, reject (packets only), skip or quit. Decisions call the existing protocol
functions with the researcher's actor; nothing is decided in bulk. Like every other
confirming command, this relies on being run by the researcher, not by an agent.
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import typer

from toulmin.application.aoe import AoEWorkspace, agent_command
from toulmin.application.build import external_states, project_map
from toulmin.cli import project as project_cli
from toulmin.cli import workspace as workspace_cli
from toulmin.cli.aoe import handoff_preview, handoff_result
from toulmin.cli.initialize import workspace_setup
from toulmin.cli.settings import ACTOR_HINT, resolve_actor, root_option
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
from toulmin.protocols.research_map import AGENT, YOU
from toulmin.protocols.synthesis import synthesis_groups
from toulmin.protocols.workspace_state import RootState, workspace_status

LABEL = {
    "change": "Workspace change",
    "creation": "Child creation",
    "handoff": "Workspace handoff",
    "object": "Object draft",
    "ruling": "Ruling proposal",
    "intake": "Intake recommendation",
    "review": "Review round request",
    "brief": "Brief proposal",
    "stage": "Stage proposal",
    "build": "Build request",
    "build-import": "Chief result ready",
    "build-verify": "Verify",
    "project-handoff": "Project handoff",
}
WORDS = {"a": "apply", "r": "reject", "s": "skip", "q": "quit"}
YES_NO = {"y": "yes", "n": "no"}
NOTICE_ITEMS = 8  # a notice is one line; longer lists end with "and N more"
# Per draft label of an intake recommendation (H4).
LABEL_WORDS = {
    "a": "as recommended",
    "t": "take",
    "o": "other severity",
    "r": "reject",
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


def _ask(choices: str, words: dict[str, str] = WORDS, default: str = "s") -> str:
    text = " / ".join(f"[{letter}]{words[letter][1:]}" for letter in choices)
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

    def _note(self, project: str, text: str) -> None:
        self.notes.setdefault(project, []).append(text)

    def decide(self, item: Item) -> bool:
        """Show and decide one item; False means quit."""
        handler = {
            "change": self._change,
            "creation": self._creation,
            "handoff": self._handoff,
            "object": self._proposal,
            "ruling": self._proposal,
            "intake": self._intake,
            "review": self._review,
            "brief": self._proposal,
            "stage": self._proposal,
            "build": self._build,
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
            verb = {"ruling": "Ruled", "brief": "Updated", "stage": "Stage ruled"}
            typer.echo(f"{verb.get(item.kind, 'Created')}: {done.result}")
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
            typer.echo(f"Rejected; outcome: {project_proposals.outcome_path(item.path)}")
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
            typer.echo(f"  {label}: already {entry['outcome']}")
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
            choice = _ask("atorsq", LABEL_WORDS)
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
                else:
                    assert advice.object is not None
                    partly[label] = advice.object
            elif choice == "t":
                take[label] = None
            elif choice == "o":
                take[label] = _severity()
            else:
                default = advice.reason if advice.outcome == "reject" else None
                reject[label] = _reason(default)
        if not (take or reject or partly):
            typer.echo("Nothing chosen; the recommendation stays pending.")
            self.skipped += 1
            return True
        self._record_intake(item, shown, take, reject, partly)
        return True

    def _record_intake(
        self,
        item: Item,
        shown: project_proposals.Preview,
        take: dict[str, str | None],
        reject: dict[str, str],
        partly: dict[str, str],
    ) -> None:
        assert item.project is not None
        result, done = project_proposals.record_intake(
            self.root, item.project, item.path, self.actor, shown.sha256, take, reject, partly,
            "toulmin decide: a",
        )  # fmt: skip
        if result is not None:
            for line in result.lines:
                target = f" as {line.object_id}" if line.object_id else ""
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
        from toulmin.application.build import apply_build, prepare_build

        assert item.project is not None
        prepared = prepare_build(self.root, item.project, item.path)
        shown = prepared.preview
        if shown.problems and shown.problems[0].startswith("already "):
            typer.echo(f"No longer pending ({shown.problems[0]}); skipped.")
            return True
        typer.echo(f"Project: {item.project}")
        typer.echo(shown.text.rstrip("\n"))
        plan = shown.build
        if plan is not None:
            typer.echo(f"Chief task: {plan.task_id}")
            typer.echo(
                "Chief confirms the worker's folder-trust prompt: "
                + ("yes" if plan.request.trust else "no")
            )
            typer.echo("Full frozen Chief contract:")
            typer.echo(json.dumps(plan.contract, ensure_ascii=False, indent=2))
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
                typer.echo(
                    f"Started/recorded: {done.result}. Keep chief watch running; "
                    "approve tests in chief inbox."
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
        request = shown.review
        if request is not None and not problems:
            try:
                prepare_round(self.root, item.project, request.personas, request.models,
                              request.claims, typer.echo)  # fmt: skip
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
            planned = prepare_round(self.root, item.project, request.personas, request.models,
                                    request.claims, lambda _: None)  # fmt: skip
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
    """After a stage ruling: a handoff, then a fresh session for the new stage (R4)."""
    typer.echo(f"Stage is now {stage}. Suggested before the next stage's work:")
    typer.echo(
        "  1. Ask the project agent for a handoff draft and apply it with `toulmin decide`; "
        "it brings PROJECT.md's next step up to date."
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
        f"  2. Continue in a fresh session: {archive}toulmin open {project} --new-session. "
        "The files and the handoff carry the state; the long conversation is not needed."
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
    if stage is not None:
        handoff = agent_command("aoe", "handoff", project, "--root", where, "--input", "FILE")
        text += (
            f" The stage is now {stage}: prepare a handoff draft now (summary under "
            f"runs/drafts/, then `{handoff}`) so PROJECT.md's next step is current."
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
    if (
        shown.kind not in {"ruling", "brief", "stage"}
        and shown.target is not None
        and shown.recovered is None
    ):
        typer.echo(f"Would create: {shown.target} (the ID is assigned when applied)")
    if shown.done:
        typer.echo("Already ruled before the interruption: " + ", ".join(shown.done))
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
    for problem in shown.problems:
        typer.echo(f"Problem: {problem}")
    if shown.kind in {"ruling", "brief", "stage"}:
        typer.echo("The Why section is shown to you only; it is not written to the target.")


def decide_command(
    root: Annotated[Path, root_option("Research workbench root.")] = Path("."),
    actor: Annotated[
        str | None,
        typer.Option(
            "--confirmed-by", help="Deciding researcher; defaults to $TOULMIN_ACTOR, then config."
        ),
    ] = None,
    notify: Annotated[
        bool | None,
        typer.Option(
            "--notify/--no-notify",
            help="Tell each bound project session what you decided (default: ask per project).",
            show_default=False,
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
            typer.echo(f"  {item.description}")
        typer.echo("Run `toulmin decide` in your own terminal to decide them; nothing changed.")
        return
    who = resolve_actor(actor)
    if who is None:
        raise typer.BadParameter(f"required: {ACTOR_HINT}", param_hint="--confirmed-by")
    typer.echo(f"Deciding as: {who}. Skip leaves an item pending.")
    run = Run(root, who)
    remaining = 0
    queue = list(found.items)
    offered: set[tuple[str, str, str | None]] = set()
    index = 0
    while queue:
        item = queue.pop(0)
        index += 1
        offered.add((item.kind, item.spec or item.path, item.project))
        typer.echo(f"\n[{index}/{index + len(queue)}] {item.description}")
        try:
            if not run.decide(item):
                remaining = len(queue)
                break
        except (OSError, ValueError) as error:
            typer.echo(f"Error: {error}", err=True)
            typer.echo("This item is unchanged and stays pending.")
            run.failed += 1
        if run.rescan:
            refreshed = inventory(root)
            queue = [
                item
                for item in refreshed.items
                if (item.kind, item.spec or item.path, item.project) not in offered
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
