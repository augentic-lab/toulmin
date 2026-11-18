"""O4: confirmed independent engineering tasks through the existing Chief adapter."""

import json
import os
import socket
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from toulmin.adapters.chief import ChiefClient, ChiefConfig, load_config
from toulmin.application.build import FOLDER_TRUST_NOTICE
from toulmin.application.build_import import _git
from toulmin.core.atomic import digest, handoff_mutex, sync_directory, write_atomic
from toulmin.core.documents import FormatError
from toulmin.core.project_proposals import Outcome
from toulmin.core.repository import Repository
from toulmin.protocols.build import contract_bytes
from toulmin.protocols.engineering_tasks import (
    TaskPlan,
    finish_task,
    new_marker,
    preview_task,
    read_outcome,
    request_path,
    write_task_outcome,
)


@dataclass(frozen=True)
class PreparedTask:
    plan: TaskPlan
    config: ChiefConfig
    problems: tuple[str, ...]
    marker: Outcome | None = None
    archive: str | None = None
    recovered: bool = False

    @property
    def interrupted(self) -> bool:
        return self.marker is not None and self.marker.disposition == "applying"


def task_archive(project: str, marker: Outcome) -> str:
    stamp = (
        datetime.fromisoformat(marker.at.replace("Z", "+00:00"))
        .astimezone(UTC)
        .strftime("%Y%m%dT%H%M%SZ")
    )
    return f"projects/{project}/runs/{stamp}-task-{marker.proposal_sha256[:12]}"


def _intent(plan: TaskPlan, config: ChiefConfig) -> bytes:
    return contract_bytes(
        {
            "schema_version": 1,
            "kind": "task-submission",
            "proposal": plan.path,
            "proposal_sha256": plan.sha256,
            "contract_sha256": digest(contract_bytes(plan.contract)),
            "task_id": plan.task_id,
            "host": socket.gethostname(),
            "chief_command": list(config.command),
            "chief_home": str(config.home),
        }
    )


def _repository(root: Path, project: str, plan: TaskPlan, config: ChiefConfig) -> Path:
    request = plan.request
    if request.source is not None:
        from toulmin.application.sources import resolve_source

        resolved = resolve_source(root, project, request.source)
        if resolved.kind != "git":
            raise FormatError("source: Chief engineering tasks require a git source")
        source_repo = resolved.path
        if request.repo is not None and Path(request.repo).resolve() != source_repo.resolve():
            raise FormatError("repo: explicit path differs from the selected source")
        return source_repo.resolve()
    value = request.repo or config.repos.get(project)
    if value is None:
        raise FormatError("repo: select a source or give an explicit repository path")
    return Path(value).resolve()


def prepare_task(root: Path, project: str, relative: str) -> PreparedTask:
    repository = Repository(root)
    plan = preview_task(root, project, relative)
    config = load_config(root)
    marker = read_outcome(repository, relative, plan.sha256)
    archive = task_archive(project, marker) if marker is not None else None
    recovered = False
    problems: list[str] = []
    try:
        if marker is not None and marker.disposition not in {"applying", "applied"}:
            raise FormatError(f"{relative}: already {marker.disposition}; create a new request")
        if plan.request.tool not in {"codex", "claude", "antigravity"}:
            raise FormatError("tool: Chief supports codex, claude or antigravity")
        repo = _repository(root, project, plan, config)
        client = ChiefClient(repository.root, config)
        client.check_repository(str(repo), plan.request.baseline)
        if Path(_git(root, str(repo), "rev-parse", "--show-toplevel").strip()).resolve() != repo:
            raise FormatError("repo: select the Git repository root, not a subdirectory")
        baseline = _git(
            root,
            str(repo),
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{plan.request.baseline}^{{commit}}",
        ).strip()
        # Chief creates its worktree from this committed revision, never the working tree.
        dirty = _git(root, str(repo), "status", "--porcelain", "--untracked-files=all")
        if dirty:
            raise FormatError(
                "repository has uncommitted changes; commit or stash them before submission. "
                "Chief starts from the committed baseline and does not include those changes"
            )
        contract = {
            "repo": str(repo),
            "name": f"{project}: {plan.request.goal.splitlines()[0][:100]}",
            "goal": f"## Goal\n{plan.request.goal}\n\n## Scope\n{plan.request.scope}\n\n"
            f"Baseline: {baseline}\nDo not change the frozen checks or protected paths. "
            f"Deliver on branch chief/{plan.task_id}.\n",
            "base_branch": baseline,
            "checks": list(plan.request.checks),
            "protected": list(plan.request.protected),
            "budget": dict(plan.request.budget),
            "tool": plan.request.tool,
            "test_first": plan.request.test_first,
        }
        if plan.request.command is not None:
            contract["command"] = plan.request.command
        plan = replace(plan, contract=contract)
        existing = client.task(plan.task_id)
        if marker is not None and archive is not None and repository.path(archive).exists():
            frozen = repository.path(f"{archive}/contract.json", "file").read_bytes()
            intent = repository.path(f"{archive}/request.json", "file").read_bytes()
            saved = json.loads(intent)
            if saved.get("host") != socket.gethostname():
                raise FormatError(f"task started on {saved.get('host')}; continue it there")
            if frozen != contract_bytes(contract) or intent != _intent(plan, config):
                raise FormatError(
                    "task inputs or Chief configuration differ from the frozen submission"
                )
            if existing is not None:
                if existing.get("repo") != str(repo):
                    raise FormatError("existing Chief task belongs to another repository")
                if existing.get("base") is not None and existing["base"] != baseline:
                    raise FormatError(
                        "existing Chief task baseline differs from the frozen contract"
                    )
                recovered = True
        elif existing is not None:
            raise FormatError(f"task_id: {plan.task_id} is already taken in Chief")
        if marker is not None and marker.disposition == "applied" and not recovered:
            raise FormatError("submitted task is missing from this Chief home; do not resubmit it")
    except (OSError, ValueError) as error:
        problems.append(str(error))
    return PreparedTask(plan, config, tuple(problems), marker, archive, recovered)


def apply_task(
    root: Path,
    project: str,
    prepared: PreparedTask,
    actor: str,
    approval_text: str,
    *,
    report: Callable[[str], None] | None = None,
) -> Outcome:
    repository = Repository(root)
    with handoff_mutex(repository.project(project)):
        current = prepare_task(root, project, prepared.plan.path)
        if current.problems:
            raise FormatError(current.problems[0])
        if current != prepared:
            raise FormatError("task request or inputs changed since preview; nothing written")
        if current.marker is not None and current.marker.disposition == "applied":
            return current.marker
        marker = current.marker or new_marker(current.plan, actor, approval_text)
        archive = task_archive(project, marker)
        folder = repository.path(archive)
        if current.marker is None:
            if folder.exists():
                raise FormatError(f"{archive}: occupied submission archive")
            write_task_outcome(repository, marker, replace_existing=False)
        if not folder.exists():
            with tempfile.TemporaryDirectory(dir=folder.parent, prefix=".task-submit-") as scratch:
                temporary = Path(scratch) / "archive"
                temporary.mkdir()
                write_atomic(temporary / "contract.json", contract_bytes(current.plan.contract))
                write_atomic(temporary / "request.json", _intent(current.plan, current.config))
                if folder.exists():
                    raise FormatError("task submission archive occupied")
                os.rename(temporary, folder)
                sync_directory(folder.parent)
        output = repository.path(f"{archive}/chief-new.txt")
        if current.recovered:
            if not output.exists():
                write_atomic(output, b"Recovered the existing Chief task; new was not repeated.\n")
            return finish_task(repository, marker, current.plan.task_id)
        if not current.plan.request.trust and report is not None:
            report(FOLDER_TRUST_NOTICE.format(task_id=current.plan.task_id))
        client = ChiefClient(repository.root, current.config)
        failure = None
        try:
            result = client.new(
                repository.path(f"{archive}/contract.json", "file"),
                current.plan.task_id,
                str(current.plan.contract["base_branch"]),
                trust=current.plan.request.trust,
            )
            text = (
                f"exit status: {result.exit_status}\n--- stdout ---\n{result.stdout}"
                f"\n--- stderr ---\n{result.stderr}"
            )
            if result.exit_status != 0:
                message = result.stderr.strip() or result.stdout.strip() or "no Chief message"
                failure = f"chief new failed ({result.exit_status}): {message}"
        except OSError as error:
            text = failure = f"chief new could not start: {error}"
        if failure is not None:
            # Even a failed/timeout launch may have durably created the worker.
            try:
                task = client.task(current.plan.task_id)
                if task is not None and task.get("repo") == current.plan.contract["repo"]:
                    failure = None
                    text += "\nThe Chief task exists; launcher failure was reconciled.\n"
            except (OSError, ValueError) as error:
                # Keep applying on uncertain lookup: a repeat must reconcile before new.
                write_atomic(
                    output,
                    (text + f"\nTask lookup failed: {error}\n").encode(),
                    replace=output.exists(),
                )
                raise FormatError(
                    "Chief launch outcome is uncertain; retry this same request to recover"
                ) from error
        write_atomic(output, text.encode(), replace=output.exists())
        return finish_task(repository, marker, current.plan.task_id, failure)


def reject_task(root: Path, project: str, relative: str, actor: str, reason: str) -> Outcome:
    if not actor.strip() or not reason.strip():
        raise FormatError("actor and rejection reason must be nonempty")
    repository = Repository(root)
    with handoff_mutex(repository.project(project)):
        raw = request_path(repository, project, relative).read_bytes()
        sha = digest(raw)
        if read_outcome(repository, relative, sha) is not None:
            raise FormatError("task request already decided or applying")
        marker = Outcome(
            relative,
            sha,
            "rejected",
            actor,
            datetime.now(UTC).isoformat(),
            None,
            reason.strip(),
            None,
        )
        write_task_outcome(repository, marker, replace_existing=False)
        return marker


def engineering_task_ids(root: Path, project: str | None) -> tuple[str, ...]:
    """Task identities requiring Chief-state checks before workspace removal."""
    repository = Repository(root)
    if project is not None:
        repository.project(project)
    from toulmin.core.scope import Scope

    folder = repository.path(f"{Scope(project).records('runs')}/proposals")
    identities: set[str] = set()
    if not folder.exists():
        return ()
    for path in sorted(folder.glob("task-*.md")):
        if path.name.endswith(".outcome.md"):
            continue
        relative = path.relative_to(repository.root).as_posix()
        raw = request_path(repository, project, relative).read_bytes()
        marker = read_outcome(repository, relative, digest(raw))
        if marker is not None and marker.disposition in {"applying", "applied"}:
            identities.add(preview_task(root, project, relative).task_id)
    return tuple(sorted(identities))
