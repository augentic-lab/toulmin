"""L3 orchestration of review, synthesis and cross-validation rounds.

Every round is planned and preflighted completely before any session starts. Sessions
run concurrently; archiving happens on this thread only, one Run at a time, because
the project creation lock refuses rather than waits.
"""

import shutil
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path

from toulmin.adapters.base import Session, stop_all
from toulmin.adapters.config import ReviewConfig, load_config
from toulmin.core.documents import FormatError
from toulmin.protocols.review import (
    ArchivedReview,
    ReviewOutcome,
    ReviewTask,
    archive_review,
    plan_review,
)
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
    _show(config, tasks, echo)
    if not _authorised(dry_run, confirmed, "review"):
        return 0
    return sum(
        item.status == "failed" for item in _execute(root, project, config, tasks, actor, echo)
    )


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
        except BaseException:
            # An interrupt or archive error must not leave sessions spending quota.
            for future in futures:
                future.cancel()
            stop_all()
            raise
    return archived
