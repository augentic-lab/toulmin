"""L3 orchestration of review, synthesis and cross-validation rounds.

Every round is planned and preflighted completely before any session starts. Sessions
run concurrently; archiving happens on this thread only, one Run at a time, because
the project creation lock refuses rather than waits.
"""

import shutil
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from toulmin.adapters.base import Session, stop_all
from toulmin.adapters.config import ReviewConfig, load_config
from toulmin.core.documents import FormatError
from toulmin.core.usage import Usage
from toulmin.protocols.review import (
    ArchivedReview,
    ReviewOutcome,
    ReviewTask,
    archive_review,
    plan_review,
)
from toulmin.protocols.review_progress import review_advisory
from toulmin.protocols.synthesis import (
    choose_model,
    plan_crossval,
    plan_synthesis,
    round_sources,
)

Echo = Callable[[str], None]


def run_round(
    root: Path,
    project: str,
    personas: list[str] | None,
    models: list[str] | None,
    claims: list[str] | None,
    actor: str,
    *,
    dry_run: bool,
    confirmed: bool,
    echo: Echo,
) -> int:
    """Return the number of failed sessions. Validation errors raise before any session."""
    config, tasks = _plan_round(root, project, personas, models, claims)
    _show(config, tasks, echo)
    if notice := review_advisory(root, project):
        echo("Note: " + notice)
    if not _authorised(dry_run, confirmed, "review"):
        return 0
    return sum(
        item.status == "failed" for item in _execute(root, project, config, tasks, actor, echo)
    )


def _plan_round(
    root: Path,
    project: str,
    personas: list[str] | None,
    models: list[str] | None,
    claims: list[str] | None,
) -> tuple[ReviewConfig, tuple[ReviewTask, ...]]:
    config = load_config(root)
    chosen = _models(config, models)
    tasks = plan_review(
        root,
        project,
        personas if personas is not None else list(config.personas),
        chosen,
        config.max_runs,
        claims,
    )
    _preflight(config, [task.model for task in tasks])
    return config, tasks


@dataclass(frozen=True)
class PlannedRound:
    """A review round planned and preflighted completely; nothing has started (H4)."""

    root: Path
    project: str
    config: ReviewConfig
    tasks: tuple[ReviewTask, ...]
    synthesizer: tuple[str, str]  # model name and rotation reason


@dataclass(frozen=True)
class RoundResult:
    reviews: tuple[ArchivedReview, ...]
    synthesis: ArchivedReview | None
    note: str  # why no synthesis ran, when none did

    def summary(self) -> str:
        reviews = ", ".join(f"{item.run} {item.status}" for item in self.reviews)
        if self.synthesis is not None:
            tail = f"synthesis {self.synthesis.run} {self.synthesis.status}"
        else:
            tail = self.note
        return f"reviews {reviews or 'none'}; {tail}"


def prepare_round(
    root: Path,
    project: str,
    personas: list[str] | None,
    models: list[str] | None,
    claims: list[str] | None,
    echo: Echo,
) -> PlannedRound:
    """Plan, preflight and show a decide review round: reviews, then synthesis (D3)."""
    config, tasks = _plan_round(root, project, personas, models, claims)
    name, reason = choose_model(root, project, list(config.models), None)
    _models(config, [name])
    _preflight(config, [name])
    _show(config, tasks, echo)
    if notice := review_advisory(root, project):
        echo("Note: " + notice)
    echo(f"  then synthesis by {name} ({reason}) when two or more outputs complete with drafts")
    return PlannedRound(root, project, config, tasks, (name, reason))


def execute_round(planned: PlannedRound, actor: str, echo: Echo) -> RoundResult:
    """Start the planned sessions, then synthesize the usable outputs; return what ran."""
    root, project, config = planned.root, planned.project, planned.config
    reviews = _execute(root, project, config, planned.tasks, actor, echo)
    reviews.sort(key=lambda item: int(item.run[2:]))
    usable = [item.run for item in reviews if item.status == "completed" and item.drafts]
    if len(usable) < 2:
        note = f"synthesis skipped: {len(usable)} usable outputs; at least two are needed"
        echo(note[0].upper() + note[1:])
        return RoundResult(tuple(reviews), None, note)
    name, reason = planned.synthesizer
    try:
        task = plan_synthesis(root, project, round_sources(root, project, usable), name, reason)
    except (OSError, ValueError) as error:
        note = f"synthesis not run: {error}"
        echo(note[0].upper() + note[1:])
        return RoundResult(tuple(reviews), None, note)
    synthesis = _execute(root, project, config, (task,), actor, echo)
    return RoundResult(tuple(reviews), synthesis[0], "")


def run_synthesis(
    root: Path,
    project: str,
    runs: list[str],
    model: str | None,
    actor: str,
    *,
    dry_run: bool,
    confirmed: bool,
    echo: Echo,
) -> int:
    """Synthesize the named Runs with the rotated (or chosen) model; return failures."""
    config = load_config(root)
    sources = round_sources(root, project, runs)
    name, reason = choose_model(root, project, list(config.models), model)
    _models(config, [name])
    if config.max_runs < 1:
        raise FormatError("synthesis: the run cap allows no session")
    task = plan_synthesis(root, project, sources, name, reason)
    _preflight(config, [name])
    _show(config, (task,), echo)
    echo(f"  synthesizer {reason}; {len(task.items)} items from {len(sources)} Runs")
    if not _authorised(dry_run, confirmed, "synthesize"):
        return 0
    return sum(
        item.status == "failed" for item in _execute(root, project, config, (task,), actor, echo)
    )


def run_crossval(
    root: Path,
    project: str,
    question: str,
    models: list[str] | None,
    synthesizer: str | None,
    synthesize: bool,
    actor: str,
    *,
    dry_run: bool,
    confirmed: bool,
    echo: Echo,
) -> int:
    """Ask each model the same question independently, then synthesize the answers."""
    config = load_config(root)
    chosen = _models(config, models)
    tasks = plan_crossval(
        root, project, question, chosen, config.max_runs, extra_sessions=int(synthesize)
    )
    planned = [task.model for task in tasks]
    reason = ""
    if synthesize:
        name, reason = choose_model(root, project, list(config.models), synthesizer)
        _models(config, [name])
        planned.append(name)
    _preflight(config, planned)
    _show(config, tasks, echo)
    if synthesize:
        echo(f"  then synthesis by {planned[-1]} ({reason})")
    if not _authorised(dry_run, confirmed, "crossval"):
        return 0
    answers = _execute(root, project, config, tasks, actor, echo)
    failed = sum(item.status == "failed" for item in answers)
    usable = [item.run for item in answers if item.status == "completed" and item.drafts]
    if not synthesize:
        return failed
    if len(usable) < 2:
        echo(f"Synthesis skipped: {len(usable)} usable answers; at least two are needed")
        return failed
    sources = round_sources(root, project, sorted(usable, key=lambda run: int(run[2:])))
    task = plan_synthesis(root, project, sources, planned[-1], reason)
    synthesis = _execute(root, project, config, (task,), actor, echo)
    return failed + sum(item.status == "failed" for item in synthesis)


def _models(config: ReviewConfig, names: list[str] | None) -> list[str]:
    chosen = names if names is not None else list(config.models)
    for name in chosen:
        if name not in config.available:
            raise FormatError(f"{name}: model: not configured in tools/models.toml [models]")
    return chosen


def _preflight(config: ReviewConfig, names: list[str]) -> None:
    for name in dict.fromkeys(names):
        entry = config.available[name]
        if shutil.which(entry.command) is None:
            raise FormatError(f"{name}: command {entry.command!r} not found on PATH")
        problem = entry.adapter.preflight(entry.command, entry.env)
        if problem is not None:
            raise FormatError(f"{name}: {problem}; nothing run")


def _show(config: ReviewConfig, tasks: tuple[ReviewTask, ...], echo: Echo) -> None:
    echo(f"Plan: {len(tasks)} sessions (cap {config.max_runs}, parallel {config.parallel})")
    for task in tasks:
        echo(f"  {task.persona} x {task.model} -> {task.archive}")
    first = tasks[0]
    echo(f"  inputs ({len(first.files)} files for {first.persona}): {', '.join(first.files)}")


def _authorised(dry_run: bool, confirmed: bool, command: str) -> bool:
    if dry_run:
        return False
    if not confirmed:
        raise FormatError(f"{command}: explicit --confirm required to start sessions; nothing run")
    return True


def _execute(
    root: Path,
    project: str,
    config: ReviewConfig,
    tasks: tuple[ReviewTask, ...],
    actor: str,
    echo: Echo,
) -> list[ArchivedReview]:
    def execute(task: ReviewTask) -> ReviewOutcome:
        entry = config.available[task.model]
        session = Session(task.prompt, entry.model, config.timeout_seconds, entry.command,
                          entry.extra_args, entry.env)  # fmt: skip
        try:
            return entry.adapter.run(session)
        except OSError as error:
            return ReviewOutcome("", entry.model or f"{entry.adapter.name} default (not reported)",
                                 None, None, f"could not start the tool: {error}")  # fmt: skip

    archived: list[ArchivedReview] = []
    with ThreadPoolExecutor(max_workers=config.parallel) as pool:
        futures: dict[Future[ReviewOutcome], ReviewTask] = {
            pool.submit(execute, task): task for task in tasks
        }
        try:
            for future in as_completed(futures):
                task = futures[future]
                result = archive_review(root, project, task, future.result(), actor)
                archived.append(result)
                pair = f"{task.persona} x {task.model}"
                echo(f"{result.run} {result.status} {pair}: {result.note}")
                if result.usage is not None:
                    echo(f"  tokens: {usage_line(result.usage)}")
        except BaseException:
            # An interrupt or archive error must not leave sessions spending quota.
            for future in futures:
                future.cancel()
            stop_all()
            raise
    echo(round_usage([item.usage for item in archived]))
    return archived


def _size(value: int | None) -> str:
    if value is None:
        return "?"
    return f"{value / 1e6:.2f}M" if value >= 1e6 else f"{value / 1e3:.1f}k"


def usage_line(usage: Usage) -> str:
    """One session's reported tokens; ``?`` marks a count the tool did not report."""
    line = f"input {_size(usage.input_tokens)} (cached {_size(usage.cached_input_tokens)}), "
    line += f"output {_size(usage.output_tokens)}"
    if usage.reasoning_output_tokens is not None:
        line += f" (reasoning {_size(usage.reasoning_output_tokens)})"
    if usage.cost_usd is not None:
        line += f", reported cost ${usage.cost_usd:.2f}"
    return line


def round_usage(usages: list[Usage | None]) -> str:
    """The round's total over the sessions that reported usage (R6)."""
    known = [usage for usage in usages if usage is not None]
    head = f"Usage: {len(known)} of {len(usages)} sessions reported tokens"
    if not known:
        return head + "."

    def total(name: str) -> int | None:
        values = [getattr(usage, name) for usage in known]
        return None if None in values else sum(values)

    summed = Usage(
        "round",
        total("input_tokens"),
        total("cached_input_tokens"),
        total("output_tokens"),
        None,
        None,
    )
    return f"{head}; together {usage_line(summed)} (per session in usage.json)."
