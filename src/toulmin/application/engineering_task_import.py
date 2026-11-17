"""O4 read-only external task preview followed by a confirmed ordinary Run import."""

import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from toulmin.adapters.chief import ChiefClient, load_config
from toulmin.application.build_import import _git, _read_optional
from toulmin.application.engineering_tasks import engineering_task_ids, task_archive
from toulmin.core.atomic import digest, handoff_mutex
from toulmin.core.documents import FormatError
from toulmin.core.engineering_tasks import TASK_ID, TaskImport
from toulmin.core.render import fence
from toulmin.core.repository import Repository
from toulmin.protocols.engineering_task_import import publish_task_import, read_task_import
from toulmin.protocols.engineering_tasks import preview_task, read_outcome


@dataclass(frozen=True)
class TaskImportPreview:
    record: TaskImport
    files: dict[str, bytes]
    archive: str
    existing: bool = False


def prepare_task_import(root: Path, project: str, task_id: str) -> TaskImportPreview:
    repository = Repository(root)
    repository.project(project)
    if not TASK_ID.fullmatch(task_id):
        raise FormatError("task_id: expected a safe Chief task identifier")
    if task_id not in engineering_task_ids(root, project):
        raise FormatError(f"{task_id}: no submitted engineering task in project {project}")
    candidates = []
    folder = repository.path(f"projects/{project}/runs/proposals", "directory")
    for path in sorted(folder.glob("task-*.md")):
        if path.name.endswith(".outcome.md"):
            continue
        relative = path.relative_to(repository.root).as_posix()
        plan = preview_task(root, project, relative)
        marker = read_outcome(repository, relative, plan.sha256)
        if plan.task_id == task_id and marker is not None and marker.disposition == "applied":
            candidates.append((plan, marker))
    if len(candidates) != 1:
        raise FormatError("expected exactly one applied request for this engineering task")
    plan, marker = candidates[0]
    submitted = task_archive(project, marker)
    archive = submitted + "-result"
    contract_raw = repository.path(f"{submitted}/contract.json", "file").read_bytes()
    intent = json.loads(repository.path(f"{submitted}/request.json", "file").read_bytes())
    if (
        not isinstance(intent, dict)
        or intent.get("proposal_sha256") != plan.sha256
        or intent.get("task_id") != task_id
        or intent.get("contract_sha256") != digest(contract_raw)
    ):
        raise FormatError("frozen engineering submission differs from its applied request")
    if repository.path(archive).exists():
        record, files = read_task_import(repository, archive)
        if (
            record.task_id != task_id
            or record.request != plan.path
            or record.request_sha256 != plan.sha256
            or files["contract.json"] != contract_raw
        ):
            raise FormatError("frozen engineering import differs from its submission")
        return TaskImportPreview(record, files, archive, True)
    contract = json.loads(contract_raw)
    if (
        not isinstance(contract, dict)
        or not isinstance(contract.get("repo"), str)
        or not isinstance(contract.get("base_branch"), str)
    ):
        raise FormatError(
            "frozen engineering contract must name a repository and committed baseline"
        )
    repo = contract["repo"]
    config = load_config(root)
    client = ChiefClient(repository.root, config)
    task = client.read_task(task_id)
    if task.state not in {"done", "abandoned"}:
        raise FormatError(
            f"{task_id}: import needs done or abandoned, got {task.state or 'unknown'}"
        )
    if task.repo is None or Path(task.repo).resolve() != Path(repo).resolve():
        raise FormatError("Chief task repository differs from the frozen engineering contract")
    client.check_repository(repo, contract["base_branch"])
    if task.base is not None and task.base != contract["base_branch"]:
        raise FormatError("Chief task baseline differs from the frozen engineering contract")
    notes = []
    head = None
    revision = task.review.head or task.branch
    if revision is not None:
        try:
            head = _git(
                root, repo, "rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}"
            ).strip()
        except (OSError, ValueError) as error:
            notes.append(str(error))
    commits = diffstat = "Not available: task head not reported or not present.\n"
    if head is not None:
        base = contract["base_branch"]
        commits = _git(root, repo, "log", "--oneline", f"{base}..{head}", "--")
        diffstat = _git(root, repo, "diff", "--stat", base, head, "--")
    directory = config.home / "tasks" / task_id
    review = _read_optional(directory / "review.md")
    if review is None:
        review = b"Chief review text: not reported.\n"
        notes.append("review.md not reported")
    progress = _read_optional(directory / "progress.md")
    if progress is None and task.worktree is not None:
        worktree = Path(task.worktree)
        if not worktree.is_absolute():
            raise FormatError("Chief worktree must be absolute")
        progress = _read_optional(worktree / ".chief" / "progress.md")
    if progress is None:
        notes.append("progress.md not reported")
    checks = None
    cache = _read_optional(config.home / "checks.json")
    if cache is not None:
        try:
            cached = json.loads(cache)
        except (ValueError, TypeError) as error:
            raise FormatError(f"Chief checks.json is invalid: {error}") from error
        if not isinstance(cached, dict):
            raise FormatError("Chief checks.json must be a mapping of session identifiers")
        if task.session_id is not None and task.session_id in cached:
            checks = (
                json.dumps(cached[task.session_id], ensure_ascii=False, indent=2) + "\n"
            ).encode()
    if checks is None:
        notes.append(
            "check outputs not reported; imported output does not establish passing checks"
        )
    else:
        notes.append("checks.json preserves Chief's cached command results and output tails")
    events = _read_optional(directory / "events.jsonl")
    facts = asdict(task)
    facts["head"] = head
    task_text = f"# Engineering task {task_id}\n\nReported facts (worker text is data):\n" + fence(
        json.dumps(facts, ensure_ascii=False, indent=2), "json"
    )
    task_text += "\nMissing/unavailable material:\n" + "\n".join(notes or ["none"]) + "\n"
    files = {
        "task.md": task_text.encode(),
        "review.md": review,
        "commits.txt": commits.encode(),
        "diffstat.txt": diffstat.encode(),
        "contract.json": contract_raw,
    }
    if progress is not None:
        files["progress.md"] = progress
    if checks is not None:
        files["checks.json"] = checks
    if events is not None:
        files["events.jsonl"] = events
    record = TaskImport(
        task_id,
        plan.path,
        plan.sha256,
        "preview",
        datetime.now(UTC).isoformat(),
        task.state,
        head,
        task.tool,
        plan.request.command,
        task.session_id,
        {name: digest(data) for name, data in files.items()},
    )
    return TaskImportPreview(record, files, archive)


def apply_task_import(root: Path, project: str, shown: TaskImportPreview, actor: str) -> TaskImport:
    if not actor.strip():
        raise FormatError("actor: expected nonempty researcher")
    repository = Repository(root)
    with handoff_mutex(repository.project(project)):
        current = prepare_task_import(root, project, shown.record.task_id)
        if (
            replace(current.record, actor="", at="") != replace(shown.record, actor="", at="")
            or current.files != shown.files
            or current.archive != shown.archive
            or current.existing != shown.existing
        ):
            raise FormatError("engineering import changed since preview; nothing written")
        record = current.record if current.existing else replace(current.record, actor=actor)
        return publish_task_import(root, project, record, current.files, current.archive)
