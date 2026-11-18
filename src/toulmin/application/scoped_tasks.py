"""Scoped v2 tasks through the existing Chief adapter and decision outcomes (L3)."""

import json
import re
import socket
import tempfile
import tomllib
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from toulmin.adapters.chief import ChiefClient, ChiefConfig, load_config
from toulmin.application.sources import (
    checkout_locks,
    filesystem_identity,
    inspect_source_v2,
    resolve_source,
)
from toulmin.core.atomic import digest, handoff_mutex, write_atomic
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError
from toulmin.core.engineering_tasks import TASK_FILENAME, TASK_ID
from toulmin.core.project_proposals import Outcome
from toulmin.core.render import header
from toulmin.core.repository import Repository
from toulmin.core.schema import utc_text
from toulmin.core.scope import Scope
from toulmin.core.scoped_tasks import ScopedTask, validate_request
from toulmin.core.sources import read_source_catalog
from toulmin.core.workspace_journal import pending
from toulmin.core.workspace_onboarding import canonical, exact, inventory, json_data
from toulmin.protocols.engineering_tasks import read_outcome, write_task_outcome


@dataclass(frozen=True)
class Prepared:
    path: str
    sha256: str
    request: ScopedTask
    task_id: str
    config: ChiefConfig
    contract: dict[str, Any]
    local: bytes
    submission: dict[str, Any] | None
    marker: Outcome | None
    archive: str | None
    recovered: bool


def request_path(repository: Repository, scope: Scope, value: str) -> Path:
    if scope.project is not None:
        repository.project(scope.project)
    relative = repository.relative(value)
    prefix = f"{scope.records('runs')}/proposals/"
    if not relative.startswith(prefix) or not TASK_FILENAME.fullmatch(relative[len(prefix) :]):
        raise FormatError(f"{relative}: task request must live directly under {prefix}")
    return repository.path(relative, "file")


def write_draft(root: Path, scope: Scope, source: str, *, name: str | None = None) -> Path:
    repository = Repository(root)
    if name is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise FormatError("task name must contain 1–64 letters/digits/underscores/hyphens")
    resolved = resolve_source(root, scope.project, source)
    if resolved.kind != "git":
        raise FormatError("Chief tasks require a Git source; directory work remains interactive")
    catalog = read_source_catalog(root)
    definition = catalog.definition(source)
    observation = inspect_source_v2(root, resolved.path)
    observed = inventory(observation.inventory, source)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    token = uuid4().hex
    snapshot = f"{scope.records('runs')}/{stamp}-task-context-{token}/inventory/{source}.json"
    pin = {
        "source": source,
        "catalog_sha256": resolved.version,
        "definition_sha256": definition.sha256,
        "identity": definition.identity,
        "snapshot": snapshot,
        "snapshot_sha256": digest(observation.inventory),
        "head": observed["head"],
    }
    config = load_config(root)
    fields = [
        ("schema_version", 2),
        ("kind", "task-request"),
        ("scope", scope.to_data()),
        ("source", source),
        ("source_pin", pin),
        ("baseline", observed["head"]),
        ("tool", config.tool),
        ("checks", ["<fill: executable command that rejects incorrect results>"]),
        ("protected", []),
        ("budget", config.budget),
        ("test_first", True),
        ("trust", config.trust),
    ]
    target = (
        f"{scope.records('runs')}/proposals/task-{stamp}" + (f"-{name}" if name else "") + ".md"
    )
    with (
        checkout_locks(((str(resolved.path), observation.filesystem),)),
        handoff_mutex(repository.root),
    ):
        if pending(repository):
            raise FormatError("pending workspace publication; finish it before drafting a task")
        if resolve_source(root, scope.project, source) != resolved:
            raise FormatError("source changed during draft preparation; retry")
        path = repository.path(snapshot)
        path.parent.mkdir(parents=True)
        write_atomic(path, observation.inventory)
        path = repository.path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(
            path,
            (
                header(fields)
                + (
                    "## Goal\n<fill: concrete engineering outcome>\n\n## "
                    "Scope\n<fill: included work and acceptance boundaries>\n"
                )
            ).encode(),
        )
    return repository.path(target)


def local_path(sha256: str) -> str:
    return f"tools/task-{sha256}.local.toml"


def _local(config: ChiefConfig, repo: Path, contract: dict[str, Any]) -> bytes:
    values = {
        "schema_version": 1,
        "host": socket.gethostname(),
        "chief_home": str(config.home),
        "chief_command": list(config.command),
        "repo": str(repo),
        "filesystem": filesystem_identity(repo),
        "contract_json": canonical(contract).decode(),
    }
    return (
        "\n".join(f"{key} = {json.dumps(value)}" for key, value in values.items()) + "\n"
    ).encode()


def archive(scope: Scope, marker: Outcome) -> str:
    moment = datetime.fromisoformat(marker.at)
    return (
        f"{scope.records('runs')}/{moment.strftime('%Y%m%dT%H%M%SZ')}"
        f"-task-{marker.proposal_sha256[:12]}"
    )


def frozen_submission(
    repository: Repository, path: str, scope: Scope, sha256: str
) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    raw = repository.path(f"{path}/submission.json", "file").read_bytes()
    data = json_data(raw, "submission.json")
    exact(
        data,
        {
            "schema_version",
            "kind",
            "scope",
            "proposal",
            "proposal_sha256",
            "source_pin",
            "baseline",
            "task_id",
            "contract_sha256",
            "local_intent_sha256",
        },
        "submission.json",
    )
    local_raw = repository.path(local_path(sha256), "file").read_bytes()
    intent = tomllib.loads(local_raw.decode())
    exact(
        intent,
        {
            "schema_version",
            "host",
            "chief_home",
            "chief_command",
            "repo",
            "filesystem",
            "contract_json",
        },
        "local task intent",
    )
    if type(intent["schema_version"]) is not int or intent["schema_version"] != 1:
        raise FormatError("unsupported local task intent version")
    if (
        type(data["schema_version"]) is not int
        or data["schema_version"] != 2
        or data["kind"] != "task-submission"
        or Scope.from_data(data["scope"]) != scope
        or data["proposal_sha256"] != sha256
        or data["local_intent_sha256"] != digest(local_raw)
        or data["contract_sha256"] != digest(intent["contract_json"].encode())
    ):
        raise FormatError("frozen task submission/local intent mismatch")
    return data, local_raw, json_data(intent["contract_json"].encode(), "frozen contract")


def _git(repo: Path, *args: str) -> str:
    from toulmin.application.sources import _git as observe

    result = observe(repo, *args)
    if result is None:
        raise FormatError(f"{repo}: Git observation unavailable: {args[0]}; inspect locally")
    return result


def validate_chief_contract(existing: dict[str, Any], contract: dict[str, Any]) -> None:
    """Old Chief versions may omit optional fields; any persisted contract value must agree."""
    if existing.get("repo") != contract["repo"] or existing.get("base") != contract["base_branch"]:
        raise FormatError("existing Chief task repo/baseline differs from frozen contract")
    for key, value in contract.items():
        if key in existing and existing[key] != value:
            raise FormatError(f"existing Chief task {key} differs from frozen contract")


def prepare(root: Path, scope: Scope, value: str) -> Prepared:
    repository = Repository(root)
    path = request_path(repository, scope, value)
    raw = path.read_bytes()
    relative = path.relative_to(repository.root).as_posix()
    sha256 = digest(raw)
    task = validate_request(decode(raw, relative))
    if task.scope != scope:
        raise FormatError("task request scope differs from selected scope/path")
    if pending(repository):
        raise FormatError("workspace publication incomplete; finish it before task submission")
    resolved = resolve_source(root, scope.project, str(task.request.source))
    if resolved.kind != "git":
        raise FormatError("scoped Chief task requires a registered Git source")
    pin = task.pin
    definition = read_source_catalog(root).definition(str(task.request.source))
    marker = read_outcome(repository, relative, sha256)
    if (
        (marker is None and pin["catalog_sha256"] != resolved.version)
        or pin["definition_sha256"] != definition.sha256
        or pin["identity"] != definition.identity
    ):
        raise FormatError("task source/catalog/definition pin changed; prepare a new draft")
    snapshot = repository.path(pin["snapshot"], "file").read_bytes()
    observed = inventory(snapshot, pin["snapshot"])
    if digest(snapshot) != pin["snapshot_sha256"] or pin["head"] != observed["head"]:
        raise FormatError("task inventory pin changed")
    config = load_config(root)
    request = task.request
    task_id = request.task_id or f"{scope.project or 'workspace'}-{path.stem}"
    if not TASK_ID.fullmatch(task_id):
        raise FormatError("task_id: derived ID exceeds 128 characters; set task_id explicitly")
    # Supported launcher tools are adapter policy, never a core data enum.
    if request.tool not in {"codex", "claude", "antigravity"}:
        raise FormatError("Chief adapter supports codex, claude or antigravity")
    baseline = _git(
        resolved.path, "rev-parse", "--verify", "--end-of-options", f"{request.baseline}^{{commit}}"
    )
    if baseline != pin["head"]:
        raise FormatError("task baseline differs from source pin.head; make a new draft/pin")
    marker = read_outcome(repository, relative, sha256)
    folder = archive(scope, marker) if marker else None
    existing = ChiefClient(root, config).task(task_id)
    contract = {
        "repo": str(resolved.path),
        "name": f"{scope.project or 'workspace'}: {request.goal.splitlines()[0][:100]}",
        "goal": (
            f"## Goal\n{request.goal}\n\n## Scope\n{request.scope}\n\nScope: "
            f"{scope.to_data()}\nSource pin: {canonical(pin).decode()}\nBaseline: "
            f"{baseline}\nDo not change the frozen checks or protected paths. Deliver on "
            f"branch chief/{task_id}.\n"
        ),
        "base_branch": baseline,
        "checks": list(request.checks),
        "protected": list(request.protected),
        "budget": dict(request.budget),
        "tool": request.tool,
        "test_first": request.test_first,
    }
    if request.command is not None:
        contract["command"] = request.command
    local = _local(config, resolved.path, contract)
    submission = None
    recovered = False
    if marker is not None and marker.disposition in {"rejected", "failed"}:
        raise FormatError("task already decided; draft a new request")
    if (
        marker is not None
        and folder is not None
        and repository.path(f"{folder}/submission.json").exists()
    ):
        submission, frozen_local, frozen_contract = frozen_submission(
            repository, folder, scope, sha256
        )
        if (
            submission["proposal"] != relative
            or submission["source_pin"] != pin
            or submission["baseline"] != baseline
            or submission["task_id"] != task_id
            or frozen_local != local
            or frozen_contract != contract
        ):
            raise FormatError(
                "task request, host, Chief home/config or frozen "
                "contract changed; continue exact original submission"
            )
        if existing is not None:
            validate_chief_contract(existing, frozen_contract)
            recovered = True
        if marker.disposition == "applied" and not recovered:
            raise FormatError("applied Chief task missing; never submit it again to another home")
    elif existing is not None:
        raise FormatError(f"{task_id}: Chief ID collision; choose explicit task_id")
    if marker is None or (submission is None or not recovered):
        if _git(resolved.path, "status", "--porcelain=v1", "--untracked-files=all"):
            raise FormatError(
                "repository has uncommitted changes; commit/stash before task submission"
            )
        current = inspect_source_v2(root, resolved.path, observed_at=observed["observed_at"])
        if current.inventory != snapshot:
            raise FormatError("task source observations changed; prepare a new draft")
    return Prepared(
        relative,
        sha256,
        task,
        task_id,
        config,
        contract,
        local,
        submission,
        marker,
        folder,
        recovered,
    )


def apply(
    root: Path,
    scope: Scope,
    shown: Prepared,
    actor: str,
    approval: str,
    *,
    report: Callable[[str], None] | None = None,
) -> Outcome:
    repository = Repository(root)
    resolved = resolve_source(root, scope.project, str(shown.request.request.source))
    with (
        checkout_locks(((str(resolved.path), filesystem_identity(resolved.path)),)),
        ExitStack() as stack,
    ):
        stack.enter_context(handoff_mutex(repository.root))
        if scope.project is not None:
            stack.enter_context(handoff_mutex(repository.project(scope.project)))
        current = prepare(root, scope, shown.path)
        if current != shown:
            raise FormatError("task changed since preview; nothing written")
        if current.marker is not None and current.marker.disposition == "applied":
            return current.marker
        if not actor.strip() or not approval.strip():
            raise FormatError("task requires actor and explicit approval")
        marker = current.marker or Outcome(
            current.path,
            current.sha256,
            "applying",
            actor,
            utc_text(datetime.now(UTC)),
            approval,
            None,
            None,
        )
        folder = archive(scope, marker)
        local = repository.path(local_path(current.sha256))
        if current.marker is None:
            write_task_outcome(repository, marker, replace_existing=False)
        if not local.exists():
            write_atomic(local, current.local)
        elif local.read_bytes() != current.local:
            raise FormatError("frozen local task intent changed; never overwrite it")
        target = repository.path(folder)
        target.mkdir(exist_ok=True)
        submission = {
            "schema_version": 2,
            "kind": "task-submission",
            "scope": scope.to_data(),
            "proposal": current.path,
            "proposal_sha256": current.sha256,
            "source_pin": current.request.pin,
            "baseline": current.contract["base_branch"],
            "task_id": current.task_id,
            "contract_sha256": digest(canonical(current.contract)),
            "local_intent_sha256": digest(current.local),
        }
        submission_path = repository.path(f"{folder}/submission.json")
        if not submission_path.exists():
            write_atomic(submission_path, canonical(submission))
        elif submission_path.read_bytes() != canonical(submission):
            raise FormatError("frozen submission changed; cannot launch")
        if current.recovered:
            done = replace(marker, disposition="applied", result=f"chief task {current.task_id}")
            write_task_outcome(repository, done, replace_existing=True)
            return done
        client = ChiefClient(root, current.config)
        attempt = repository.path(f"tools/task-{current.sha256}-started.local.toml")
        if attempt.exists():
            raise FormatError(
                "Chief launch was attempted but no exact matching task is visible; "
                "outcome remains uncertain. Inspect this same Chief ID; no second new "
                "was sent"
            )
        write_atomic(
            attempt,
            ("schema_version = 1\ntask_id = " + json.dumps(current.task_id) + "\n").encode(),
        )
        # An unresolved response stays applying. Retrying checks the exact global ID
        # and frozen contract before any new call; no scheduler/kickoff is added.
        result = None
        launch_error = ""
        try:
            with tempfile.TemporaryDirectory(prefix="toulmin-task-export-") as temporary:
                contract_path = Path(temporary) / "contract.json"
                write_atomic(contract_path, canonical(current.contract))
                result = client.new(
                    contract_path,
                    current.task_id,
                    str(current.contract["base_branch"]),
                    trust=current.request.request.trust,
                )
        except OSError as error:
            launch_error = str(error)
            if report:
                report(f"Chief launch outcome uncertain: {error}")
        output = repository.path(f"tools/task-{current.sha256}-result.local.toml")
        result_text = {
            "exit_status": result.exit_status if result else None,
            "stdout": result.stdout if result else "",
            "stderr": result.stderr if result else launch_error,
        }
        write_atomic(
            output,
            (
                "# Local Chief launcher result\nraw_json = "
                + json.dumps(canonical(result_text).decode())
                + "\n"
            ).encode(),
            replace=output.exists(),
        )
        existing = client.task(current.task_id)
        if existing is None:
            raise FormatError(
                "Chief launch outcome uncertain; retry this exact request to reconcile its ID"
            )
        validate_chief_contract(existing, current.contract)
        done = replace(marker, disposition="applied", result=f"chief task {current.task_id}")
        write_task_outcome(repository, done, replace_existing=True)
        if report:
            report(
                f"Submitted {current.task_id}; inspect native trust prompt, then "
                f"chief kickoff {current.task_id}. No worker start is implied."
            )
        return done


def reject(root: Path, scope: Scope, value: str, actor: str, reason: str) -> Outcome:
    repository = Repository(root)
    with handoff_mutex(repository.root):
        path = request_path(repository, scope, value)
        relative = path.relative_to(repository.root).as_posix()
        sha256 = digest(path.read_bytes())
        if read_outcome(repository, relative, sha256) is not None:
            raise FormatError("task already decided or applying")
        if not actor.strip() or not reason.strip():
            raise FormatError("task rejection requires actor and reason")
        marker = Outcome(
            relative, sha256, "rejected", actor, utc_text(datetime.now(UTC)), None, reason, None
        )
        write_task_outcome(repository, marker, replace_existing=False)
        return marker
