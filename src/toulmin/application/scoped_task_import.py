"""Read-only scoped Chief result preview, then explicit operational/formal Run import."""

import json
from contextlib import ExitStack
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from toulmin.adapters.chief import ChiefClient, load_config
from toulmin.application.build_import import _read_optional
from toulmin.application.chief_contract import validate_chief_contract, validate_lineage
from toulmin.application.scoped_tasks import _git, archive, frozen_submission, request_path
from toulmin.core.atomic import digest, handoff_mutex
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError
from toulmin.core.repository import Repository
from toulmin.core.schema import utc_text
from toulmin.core.scope import Scope
from toulmin.core.scoped_tasks import ScopedImport, validate_request
from toulmin.core.workspace_journal import pending
from toulmin.core.workspace_onboarding import canonical
from toulmin.protocols import engineering_task_import as publication
from toulmin.protocols.engineering_tasks import read_outcome


@dataclass(frozen=True)
class Preview:
    record: ScopedImport
    files: dict[str, bytes]
    archive: str
    existing: bool = False


def prepare(root: Path, scope: Scope, value: str) -> Preview:
    repository = Repository(root)
    path = request_path(repository, scope, value)
    request_bytes = path.read_bytes()
    relative = path.relative_to(repository.root).as_posix()
    sha256 = digest(request_bytes)
    request = validate_request(decode(request_bytes, relative))
    if request.scope != scope:
        raise FormatError("task import request scope/path mismatch")
    marker = read_outcome(repository, relative, sha256)
    if marker is None or marker.disposition != "applied":
        raise FormatError("task must have an applied submission before result import")
    submitted = archive(scope, marker)
    submission, _, contract = frozen_submission(repository, submitted, scope, sha256)
    if submission["proposal"] != relative or submission["source_pin"] != request.pin:
        raise FormatError("task submission differs from request/pin")
    result_archive = submitted + "-result"
    saved = repository.path(f"{result_archive}/import.json")
    if saved.exists():
        record, files = publication.read_task_import(repository, result_archive)
        if (
            not isinstance(record, ScopedImport)
            or record.request != relative
            or record.request_sha256 != sha256
            or record.scope != scope
            or record.source_pin != request.pin
            or record.submission_sha256
            != digest(repository.path(f"{submitted}/submission.json", "file").read_bytes())
            or files["contract.json"] != canonical(contract)
        ):
            raise FormatError("existing task import differs from frozen submission")
        return Preview(record, files, result_archive, True)
    config = load_config(root)
    import tomllib

    from toulmin.application.scoped_tasks import local_path

    local = tomllib.loads(repository.path(local_path(sha256), "file").read_text())
    import socket

    if (
        local["host"] != socket.gethostname()
        or local["chief_home"] != str(config.home)
        or local["chief_command"] != list(config.command)
    ):
        raise FormatError("task import must use the original host and Chief home/command")
    client = ChiefClient(root, config)
    raw_task = client.task(submission["task_id"])
    if raw_task is None:
        raise FormatError("Chief task missing from original home; never redirect result import")
    scope_base = validate_chief_contract(raw_task, contract)
    task = client.read_task(submission["task_id"])
    if task.state not in {"done", "abandoned"}:
        raise FormatError("task import requires done or abandoned Chief state")
    if task.repo != contract["repo"] or task.base != scope_base:
        raise FormatError("Chief result repo/scope base changed during contract validation")
    repo = Path(str(contract["repo"]))
    head = _git(
        repo,
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{task.review.head or task.branch or task.base}^{{commit}}",
    )
    validate_lineage(str(repo), scope_base, head)
    commits = _git(repo, "log", "--oneline", f"{contract['base_branch']}..{head}", "--")
    diffstat = _git(
        repo, "diff", "--no-ext-diff", "--stat", str(contract["base_branch"]), head, "--"
    )
    directory = config.home / "tasks" / submission["task_id"]
    facts = asdict(task)
    facts["head"] = head
    files = {
        "task.md": b"# Chief task result (worker facts, not acceptance)\n" + canonical(facts),
        "commits.txt": (commits + "\n").encode(),
        "diffstat.txt": (diffstat + "\n").encode(),
        "contract.json": canonical(contract),
        "review.md": _read_optional(directory / "review.md") or b"Chief review not reported.\n",
    }
    for name in ("progress.md", "events.jsonl"):
        raw = _read_optional(directory / name)
        if raw is not None:
            files[name] = raw
    cached = _read_optional(config.home / "checks.json")
    if cached is not None:
        checks = json.loads(cached)
        if not isinstance(checks, dict):
            raise FormatError("Chief check cache must be a mapping")
        if task.session_id in checks:
            files["checks.json"] = canonical(checks[task.session_id])
    record = ScopedImport(
        str(submission["task_id"]),
        relative,
        sha256,
        "preview",
        utc_text(datetime.now(UTC)),
        task.state,
        head,
        task.tool,
        request.request.command,
        task.session_id,
        {name: digest(raw) for name, raw in files.items()},
        scope=scope,
        source_pin=request.pin,
        submission_sha256=digest(
            repository.path(f"{submitted}/submission.json", "file").read_bytes()
        ),
    )
    return Preview(record, files, result_archive)


def apply(root: Path, scope: Scope, value: str, shown: Preview, actor: str) -> ScopedImport:
    if not actor.strip():
        raise FormatError("explicit import actor is required")
    repository = Repository(root)
    with ExitStack() as stack:
        stack.enter_context(handoff_mutex(repository.root))
        if scope.project:
            stack.enter_context(handoff_mutex(repository.project(scope.project)))
        if pending(repository):
            raise FormatError("workspace publication pending; finish it before importing a task")
        current = prepare(root, scope, value)
        if (
            replace(current.record, actor="", at="") != replace(shown.record, actor="", at="")
            or current.files != shown.files
            or current.archive != shown.archive
        ):
            raise FormatError("task result changed since preview; review again")
        record = current.record if current.existing else replace(current.record, actor=actor)
        done = publication.publish_task_import(
            root, scope.project or "", record, current.files, current.archive
        )
        assert isinstance(done, ScopedImport)
        return done
