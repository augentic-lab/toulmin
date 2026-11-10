"""R8 B2: coordinate file-derived build plans and the external Chief adapter."""

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from toulmin.adapters.chief import ChiefClient, ChiefConfig, load_config
from toulmin.core.atomic import digest, handoff_mutex, write_atomic
from toulmin.core.build import BuildTask
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError, sections
from toulmin.core.project_proposals import Outcome, validate_build_request, validate_outcome
from toulmin.core.repository import Repository
from toulmin.protocols import project_proposals
from toulmin.protocols.build import build_facts, contract_bytes, load_spec
from toulmin.protocols.research_map import ResearchMap

FOLDER_TRUST_NOTICE = (
    "Chief will not answer the worker's folder-trust prompt: right after apply, accept it "
    "in the AoE session, then run `chief kickoff {task_id}` (or set trust: true)."
)


def _kickoff_notice(task_id: str) -> str:
    return (
        "If the worker was not kicked off (it may be waiting at a menu), resolve the menu "
        f"in AoE, then run `chief kickoff {task_id}`."
    )


@dataclass(frozen=True)
class PreparedBuild:
    preview: project_proposals.Preview
    config: ChiefConfig
    problems: tuple[str, ...]
    recovered: bool = False
    archive: str | None = None


def _archive(project: str, marker: Outcome, spec: str) -> str:
    stamp = datetime.fromisoformat(marker.at.replace("Z", "+00:00")).strftime("%Y%m%dT%H%M%SZ")
    return f"projects/{project}/runs/{stamp}-build-{spec}"


def _intent(shown: project_proposals.Preview, config: ChiefConfig) -> bytes:
    assert shown.build is not None
    return (
        json.dumps(
            {
                "proposal": shown.path,
                "proposal_sha256": shown.sha256,
                "task_id": shown.build.task_id,
                "chief_home": str(config.home),
                "command": list(config.command),
            },
            indent=2,
        )
        + "\n"
    ).encode()


def prepare_build(root: Path, project: str, relative: str) -> PreparedBuild:
    """Preview all refusals before any write; Chief tasks are read only here."""
    shown = project_proposals.preview(root, project, relative)
    config = load_config(root)
    problems = list(shown.problems)
    plan = shown.build
    if plan is None or problems:
        return PreparedBuild(shown, config, tuple(problems))
    repository = Repository(root)
    client = ChiefClient(repository.root, config)
    recovered = False
    archive = None
    try:
        if plan.request.tool not in ("codex", "claude", "antigravity"):
            raise FormatError("tool: Chief supports codex, claude or antigravity")
        client.check_repository(plan.request.repo, plan.request.base_branch)
        if shown.interrupted:
            marker = project_proposals.interrupted_marker(root, project, relative)
            archive = _archive(project, marker, plan.request.spec)
            folder = repository.path(archive)
            if folder.exists():
                frozen = repository.path(f"{archive}/contract.json", "file").read_bytes()
                intent = repository.path(f"{archive}/request.json", "file").read_bytes()
                # An upgrade must not rename an already frozen Chief task. Accept only the
                # previous title derivation, with every other contract byte still matching.
                requirements = sections(load_spec(repository, project, plan.request.spec))[
                    "Requirements"
                ]
                first = next(
                    (line.strip() for line in requirements.splitlines() if line.strip()),
                    plan.request.spec,
                )
                legacy = {**plan.contract, "name": f"{project} {plan.request.spec}: {first}"}
                if frozen == contract_bytes(legacy):
                    plan = replace(plan, contract=legacy)
                    shown = replace(shown, build=plan)
                if frozen != contract_bytes(plan.contract) or intent != _intent(shown, config):
                    raise FormatError(
                        "interrupted request differs from its frozen contract/configuration; "
                        "restore the inputs"
                    )
        existing = client.task(plan.task_id)
        if existing is not None:
            if not shown.interrupted or archive is None or not repository.path(archive).exists():
                raise FormatError(f"task_id: {plan.task_id} is already taken in Chief")
            if existing.get("repo") != str(Path(plan.request.repo).resolve()):
                raise FormatError(f"task_id: {plan.task_id} belongs to a different repository")
            recovered = True
        # A prior live task for this Spec must be resolved before another can start.
        folder = repository.path(f"projects/{project}/runs/proposals", "directory")
        for path in sorted(folder.glob("build-*.md")):
            other = path.relative_to(repository.root).as_posix()
            if other == relative or other.endswith(".outcome.md"):
                continue
            outcome_path = repository.path(project_proposals.outcome_path(other))
            if not outcome_path.exists():
                continue
            outcome = validate_outcome(decode(outcome_path.read_bytes(), str(outcome_path)))
            if outcome.disposition not in {"applied", "applying"}:
                continue
            raw = repository.path(other, "file").read_bytes()
            request = validate_build_request(decode(raw, other))
            if request.spec != plan.request.spec:
                continue
            if outcome.proposal != other or digest(raw) != outcome.proposal_sha256:
                raise FormatError(f"{other}: applied build request was changed")
            task_id = request.task_id or f"{project}-{request.spec.replace('-', '').lower()}"
            task = client.task(task_id)
            if task is not None and task.get("repo") != str(Path(request.repo).resolve()):
                raise FormatError(f"{task_id}: prior task belongs to a different repository")
            if task is None or task.get("state") not in {"done", "abandoned"}:
                raise FormatError(
                    f"{request.spec}: prior build {task_id} is live or its state is unknown"
                )
    except (OSError, ValueError) as error:
        problems.append(str(error))
    return PreparedBuild(shown, config, tuple(problems), recovered, archive)


def apply_build(
    root: Path,
    project: str,
    prepared: PreparedBuild,
    actor: str,
    approval_text: str,
    *,
    report: Callable[[str], None] | None = None,
) -> Outcome:
    """Freeze a reviewed contract, start Chief once, archive output and record its outcome."""
    repository = Repository(root)
    # Serialize applies through Chief startup, including two different requests for one Spec.
    with handoff_mutex(repository.project(project)):
        current = prepare_build(root, project, prepared.preview.path)
        shown = current.preview
        if current.problems:
            raise FormatError(current.problems[0])
        if (
            shown.sha256 != prepared.preview.sha256
            or current.config != prepared.config
            or shown.build != prepared.preview.build
            or current.recovered != prepared.recovered
        ):
            raise FormatError("build request or inputs changed since the preview; nothing written")
        plan = shown.build
        assert plan is not None
        # Check occupied archive paths before claiming a fresh request.
        started = datetime.now(UTC)
        if not shown.interrupted:
            stamp = started.strftime("%Y%m%dT%H%M%SZ")
            candidate = f"projects/{project}/runs/{stamp}-build-{plan.request.spec}"
            if repository.path(candidate).exists():
                raise FormatError(f"{candidate}: archive already exists; retry later")
        marker = project_proposals.begin_build(
            root, project, shown.path, actor, shown.sha256, approval_text, now=started
        )
        archive = _archive(project, marker, plan.request.spec)
        folder = repository.path(archive)
        if not folder.exists():
            folder.mkdir()
            write_atomic(
                repository.path(f"{archive}/contract.json"),
                contract_bytes(plan.contract),
                replace=False,
            )
            write_atomic(
                repository.path(f"{archive}/request.json"),
                _intent(shown, current.config),
                replace=False,
            )
        output = repository.path(f"{archive}/chief-new.txt")
        if not plan.request.trust and report is not None:
            report(FOLDER_TRUST_NOTICE.format(task_id=plan.task_id))
        if current.recovered:
            if not output.exists():
                write_atomic(
                    output,
                    (
                        f"Recovered existing chief task {plan.task_id}; "
                        "chief new was not repeated.\n"
                    ).encode(),
                    replace=False,
                )
            if report is not None:
                report(f"The task exists. {_kickoff_notice(plan.task_id)}")
            return project_proposals.finish_build(root, marker, plan.task_id)
        client = ChiefClient(repository.root, current.config)
        try:
            finished = client.new(
                repository.path(f"{archive}/contract.json", "file"),
                plan.task_id,
                plan.request.base_branch,
                trust=plan.request.trust,
            )
            text = (
                f"exit status: {finished.exit_status}\n--- stdout ---\n{finished.stdout}"
                f"\n--- stderr ---\n{finished.stderr}"
            )
            failure = None
            if finished.exit_status != 0:
                message = finished.stderr.strip() or finished.stdout.strip() or "no Chief message"
                status = (
                    "timed out" if finished.exit_status is None else f"exit {finished.exit_status}"
                )
                failure = f"chief new {status}: {message}"
        except OSError as error:
            text = f"chief new could not start: {error}\n"
            failure = text.strip()
        note = None
        if failure is not None:
            launch_failure = failure
            text += f"\n{launch_failure}\n"
            # A failed launcher can have already created a worker. Reconcile with Chief's
            # durable task before declaring failure and suggesting a new request.
            try:
                task = client.task(plan.task_id)
            except (OSError, ValueError) as error:
                failure += f"; task lookup failed: {error}"
            else:
                if task is None:
                    failure += f"; task id {plan.task_id} is free"
                elif task.get("repo") == str(Path(plan.request.repo).resolve()):
                    note = "chief new reported an error, but the task exists. " + _kickoff_notice(
                        plan.task_id
                    )
                    failure = None
                else:
                    failure += f"; task id {plan.task_id} belongs to a different repository"
            if note is not None:
                text += f"{note}\n"
            elif failure != launch_failure:
                text += f"{failure}\n"
        write_atomic(output, text.encode(), replace=output.exists())
        done = project_proposals.finish_build(root, marker, plan.task_id, failure)
        if note is not None and report is not None:
            report(note)
        return done


def external_states(root: Path, project: str) -> dict[str, BuildTask]:
    """Inject read-only Chief facts at L3 boundaries; offline state remains explicit."""
    facts = build_facts(root, project)
    tasks = [fact.task_id for fact in facts if fact.task_id is not None]
    if not tasks:
        return {}
    try:
        client = ChiefClient(Repository(root).root, load_config(root))
    except (OSError, ValueError) as error:
        return {task_id: BuildTask(error=str(error)) for task_id in tasks}
    result = {}
    for task_id in tasks:
        try:
            result[task_id] = client.read_task(task_id)
        except (OSError, ValueError) as error:
            result[task_id] = BuildTask(error=str(error))
    return result


def project_map(root: Path, project: str) -> ResearchMap:
    from toulmin.protocols.research_map import research_map

    return research_map(root, project, chief=external_states(root, project))
