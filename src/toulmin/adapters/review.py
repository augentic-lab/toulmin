"""L3 orchestration of one review round: plan, preflight, run in parallel, archive.

Sessions run concurrently; archiving happens on this thread only, one Run at a time,
because the project creation lock refuses rather than waits.
"""

import shutil
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path

from toulmin.adapters.base import Session, stop_all
from toulmin.adapters.config import ModelConfig, load_config
from toulmin.core.documents import FormatError
from toulmin.protocols.review import ReviewOutcome, ReviewTask, archive_review, plan_review


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
    echo: Callable[[str], None],
) -> int:
    """Return the number of failed sessions. Validation errors raise before any session."""
    config = load_config(root)
    chosen_models = models if models is not None else list(config.models)
    for name in chosen_models:
        if name not in config.available:
            raise FormatError(f"{name}: model: not configured in tools/models.toml [models]")
    tasks = plan_review(
        root,
        project,
        personas if personas is not None else list(config.personas),
        chosen_models,
        config.max_runs,
        claims,
    )
    for name in dict.fromkeys(task.model for task in tasks):
        entry = config.available[name]
        if shutil.which(entry.command) is None:
            raise FormatError(f"{name}: command {entry.command!r} not found on PATH")

    echo(f"Plan: {len(tasks)} sessions (cap {config.max_runs}, parallel {config.parallel})")
    for task in tasks:
        echo(f"  {task.persona} x {task.model} -> {task.archive}")
    echo(
        f"  inputs ({len(tasks[0].files)} files for the first persona): {', '.join(tasks[0].files)}"
    )
    if dry_run:
        return 0
    if not confirmed:
        raise FormatError("review: explicit --confirm required to start sessions; nothing run")

    def session(task: ReviewTask) -> Session:
        entry: ModelConfig = config.available[task.model]
        return Session(task.prompt, entry.model, config.timeout_seconds, entry.command,
                       entry.extra_args, entry.env)  # fmt: skip

    def execute(task: ReviewTask) -> ReviewOutcome:
        entry = config.available[task.model]
        try:
            return entry.adapter.run(session(task))
        except OSError as error:
            return ReviewOutcome("", entry.model or f"{entry.adapter.name} default (not reported)",
                                 None, None, f"could not start the tool: {error}")  # fmt: skip

    failed = 0
    with ThreadPoolExecutor(max_workers=config.parallel) as pool:
        futures: dict[Future[ReviewOutcome], ReviewTask] = {
            pool.submit(execute, task): task for task in tasks
        }
        try:
            for future in as_completed(futures):
                task = futures[future]
                archived = archive_review(root, project, task, future.result(), actor)
                failed += archived.status == "failed"
                pair = f"{task.persona} x {task.model}"
                echo(f"{archived.run} {archived.status} {pair}: {archived.note}")
        except BaseException:
            # An interrupt or archive error must not leave sessions spending quota.
            for future in futures:
                future.cancel()
            stop_all()
            raise
    return failed
