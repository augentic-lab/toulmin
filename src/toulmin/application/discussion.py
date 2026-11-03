"""App-owned discussion jobs, shared by every workspace screen.

Only explicit start/recover/apply calls mutate research files. A process lease prevents
another application from recovering an invocation that is still running elsewhere.
"""

import getpass
import shutil
import threading
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path

from toulmin.adapters.base import Session
from toulmin.adapters.config import ModelConfig, load_config
from toulmin.application.workspace import WorkspaceService
from toulmin.core.atomic import handoff_mutex
from toulmin.core.documents import FormatError
from toulmin.protocols.discussion import (
    DiscussionView,
    apply_proposal,
    begin_turn,
    dismiss_proposal,
    finish_turn,
    get_turn_prompt,
    load_discussion,
    prepare_research_workspace,
    preview_context,
    recover_turn,
    save_proposal_draft,
)
from toulmin.protocols.review import ReviewOutcome


@dataclass
class _Job:
    cancel: threading.Event
    thread: threading.Thread


class DiscussionService:
    """One invocation per project, explicit retries and no implicit quota use."""

    def __init__(self, actor: str | None = None) -> None:
        self.actor = actor if actor is not None else getpass.getuser()
        self._jobs: dict[tuple[Path, str], _Job] = {}
        self._errors: dict[tuple[Path, str], str] = {}
        self._lock = threading.RLock()
        self._closed = False

    @staticmethod
    def _key(root: Path, project: str) -> tuple[Path, str]:
        return root.absolute(), project

    @staticmethod
    def _lease(root: Path, project: str) -> AbstractContextManager[None]:
        return handoff_mutex(root.absolute() / "projects" / project / "runs" / "discussion-job")

    def models(self, root: Path) -> tuple[str, ...]:
        return tuple(load_config(root).available)

    def load(self, root: Path, project: str) -> DiscussionView:
        return load_discussion(root, project)

    def context(self, root: Path, project: str) -> str:
        return preview_context(root, project)

    def active(self, root: Path, project: str) -> bool:
        with self._lock:
            job = self._jobs.get(self._key(root, project))
            return job is not None and job.thread.is_alive()

    def error(self, root: Path, project: str) -> str | None:
        with self._lock:
            return self._errors.get(self._key(root, project))

    def start(
        self, root: Path, project: str, text: str, model: str, operation: str = "explore"
    ) -> str:
        with self._lock:
            if self._closed:
                raise FormatError("Discussion service is closed")
            if self.active(root, project):
                raise FormatError("Wait for this project's current response or stop it first")
            view = WorkspaceService().open_project(root, project)
            if view.setup_pending or view.diagnostics:
                raise FormatError("Resolve project diagnostics or incomplete setup before sending")
            config = load_config(root)
            entry = config.available.get(model)
            if entry is None:
                raise FormatError("Choose a configured model from tools/models.toml")
            executable_path = dict(entry.env).get("PATH")
            if shutil.which(entry.command, path=executable_path) is None:
                raise FormatError(
                    f"{entry.command}: executable not found; install and authenticate the tool "
                    "or update tools/models.toml"
                )
            lease = self._lease(root, project)
            lease.__enter__()
            try:
                turn = begin_turn(root, project, text, model, self.actor, operation)
                prompt = get_turn_prompt(root, project, turn.id)
                cancel = threading.Event()
                thread = threading.Thread(
                    target=self._execute,
                    args=(
                        root,
                        project,
                        turn.id,
                        prompt,
                        entry,
                        config.timeout_seconds,
                        operation,
                        cancel,
                        lease,
                    ),
                    name=f"toulmin-discussion-{project}",
                )
                key = self._key(root, project)
                self._jobs[key] = _Job(cancel, thread)
                self._errors.pop(key, None)
                thread.start()
            except BaseException:
                lease.__exit__(None, None, None)
                raise
            return turn.id

    def _execute(
        self,
        root: Path,
        project: str,
        request: str,
        prompt: str,
        entry: ModelConfig,
        timeout: float,
        operation: str,
        cancel: threading.Event,
        lease: AbstractContextManager[None],
    ) -> None:
        started = time.monotonic()
        try:
            try:
                problem: str | None
                if cancel.is_set():
                    problem = "cancelled before the model started"
                else:
                    problem = entry.adapter.preflight(entry.command, entry.env, cancel)
                if problem is not None:
                    raise FormatError(problem)
                if cancel.is_set():
                    raise FormatError("cancelled before the model started")
                workspace = (
                    prepare_research_workspace(root, project, request)
                    if operation == "explore"
                    else None
                )
                outcome = entry.adapter.run(
                    Session(
                        prompt,
                        entry.model,
                        timeout,
                        entry.command,
                        entry.extra_args,
                        entry.env,
                        cancel,
                        workspace=workspace,
                    )
                )
            except Exception as error:
                outcome = ReviewOutcome(
                    "",
                    entry.model or f"{entry.name} default (not reported)",
                    None,
                    time.monotonic() - started,
                    str(error),
                )
            finish_turn(root, project, request, outcome)
        except Exception as error:
            # Preserve the request and any already archived output for explicit recovery.
            with self._lock:
                self._errors[self._key(root, project)] = (
                    f"Could not finalize the archived response: {error}. "
                    "Inspect the saved request before using Recover; no automatic retry occurred."
                )
        finally:
            lease.__exit__(None, None, None)

    def stop(self, root: Path, project: str) -> None:
        with self._lock:
            job = self._jobs.get(self._key(root, project))
            if job is not None:
                job.cancel.set()

    def recover(self, root: Path, project: str) -> None:
        with self._lock, self._lease(root, project):
            if self.active(root, project):
                raise FormatError("The model is still running; stop it before recovery")
            for turn in self.load(root, project).turns:
                if turn.status == "running":
                    recover_turn(root, project, turn.id, self.actor)
            self._errors.pop(self._key(root, project), None)

    def apply(self, root: Path, project: str, proposal: str, text: str) -> None:
        with self._lease(root, project):
            self._check_writable(root, project)
            apply_proposal(root, project, proposal, text, self.actor)

    def dismiss(self, root: Path, project: str, proposal: str) -> None:
        with self._lease(root, project):
            self._check_writable(root, project)
            dismiss_proposal(root, project, proposal, self.actor)

    def save_draft(self, root: Path, project: str, proposal: str, text: str) -> None:
        with self._lease(root, project):
            self._check_writable(root, project)
            save_proposal_draft(root, project, proposal, text)

    @staticmethod
    def _check_writable(root: Path, project: str) -> None:
        view = WorkspaceService().open_project(root, project)
        if view.setup_pending or view.diagnostics:
            raise FormatError("Resolve project diagnostics or incomplete setup before editing")

    def close(self) -> None:
        with self._lock:
            self._closed = True
            jobs = tuple(self._jobs.values())
            for job in jobs:
                job.cancel.set()
        for job in jobs:
            job.thread.join(timeout=10)
            if job.thread.is_alive():
                raise RuntimeError("A discussion job has not stopped; its request remains saved")
