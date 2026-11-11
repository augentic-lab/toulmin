"""R8 B3: read Chief results and local git history, then apply a reviewed workspace import."""

import json
import os
import stat
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from toulmin.adapters.base import run_process
from toulmin.adapters.chief import ChiefClient, load_config
from toulmin.core.atomic import digest, handoff_mutex
from toulmin.core.build import BuildImport
from toulmin.core.documents import FormatError
from toulmin.core.inspection import current_claim, inspect_project
from toulmin.core.proposals import MAX_BYTES
from toulmin.core.render import fence
from toulmin.core.repository import Repository
from toulmin.core.schema import utc_text
from toulmin.protocols.build import BuildFact, build_facts, load_spec
from toulmin.protocols.build_import import apply_frozen_import, checked_artifacts, read_record


@dataclass(frozen=True)
class ImportPreview:
    fact: BuildFact
    record: BuildImport
    files: dict[str, bytes]
    archive: str | None = None

    @property
    def label(self) -> str:
        return (
            f"{self.record.spec} ({self.record.task_id}, {self.record.state}, "
            f"review {self.record.verdict or 'not reported'})"
        )


def _read_optional(path: Path) -> bytes | None:
    """Bound external text and open every component without following symlinks."""
    if not path.is_absolute():
        raise FormatError(f"{path}: external artifact path must be absolute")
    directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            child = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            os.close(directory)
            directory = child
        descriptor = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise FormatError(f"{path}: expected a regular artifact file")
            data = stream.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise FormatError(f"{path}: cannot read artifact without symlinks: {error}") from error
    finally:
        os.close(directory)
    if len(data) > MAX_BYTES:
        raise FormatError(f"{path}: artifact exceeds {MAX_BYTES} bytes")
    return data


def _git(root: Path, repo: str, *args: str) -> str:
    result = run_process(["git", "-C", repo, *args], "", 30, root)
    if result.exit_status != 0:
        raise FormatError(f"{repo}: git {' '.join(args)}: {result.stderr.strip() or 'failed'}")
    return result.stdout


def prepare_import(root: Path, project: str, spec: str) -> ImportPreview:
    repository = Repository(root)
    fact = next((item for item in build_facts(root, project) if item.spec == spec), None)
    if fact is None or fact.task_id is None or fact.request is None or fact.sha256 is None:
        raise FormatError(f"{spec}: no applied build request")
    if fact.archive is not None:
        saved = read_record(repository, fact.archive)
        files = checked_artifacts(repository, fact.archive, saved)
        return ImportPreview(fact, saved, files, fact.archive)
    config = load_config(root)
    task = ChiefClient(repository.root, config).read_task(fact.task_id)
    if task.state not in {"done", "abandoned"}:
        raise FormatError(
            f"{fact.task_id}: state {task.state or 'not reported'}; import needs done or abandoned"
        )
    source = load_spec(repository, project, spec)
    claim, owner = repository.resolve(project, source.header["target"])
    current = current_claim(inspect_project(repository, owner).objects, claim.object_id)[-1]
    target = str(current) if owner == project else f"{owner}/{current}"
    # Locate the original frozen contract, never derive checks again from mutable prose.
    contracts = []
    runs = repository.path(f"projects/{project}/runs", "directory")
    for path in runs.glob(f"*-build-{spec}/request.json"):
        relative = path.relative_to(repository.root).as_posix()
        raw = json.loads(repository.path(relative, "file").read_bytes())
        if not isinstance(raw, dict):
            raise FormatError(f"{relative}: expected a build request record")
        if raw.get("proposal") == fact.request and raw.get("proposal_sha256") == fact.sha256:
            contracts.append(repository.path(relative.rsplit("/", 1)[0] + "/contract.json", "file"))
    if len(contracts) != 1:
        raise FormatError(f"{spec}: expected one frozen contract for {fact.task_id}")
    contract = json.loads(contracts[0].read_bytes())
    if not isinstance(contract, dict):
        raise FormatError("frozen build contract must be a JSON object")
    repo = contract.get("repo")
    if not isinstance(repo, str) or not Path(repo).is_absolute() or not Path(repo).is_dir():
        raise FormatError(
            f"{repo}: code repository moved or missing; edit tools/chief.local.toml and re-request"
        )
    if task.repo is not None and Path(task.repo).resolve() != Path(repo).resolve():
        raise FormatError(f"{fact.task_id}: Chief repository differs from the frozen contract")
    ChiefClient(repository.root, config).check_repository(repo, None)
    notes: list[str] = []
    head = None
    if task.review.head is not None:
        head = _git(
            repository.root,
            repo,
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{task.review.head}^{{commit}}",
        ).strip()
    elif task.branch is not None:
        try:
            head = _git(
                repository.root,
                repo,
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{task.branch}^{{commit}}",
            ).strip()
        except (OSError, ValueError) as error:
            notes.append(str(error))
    commits = diffstat = "Not available: base or head not reported.\n"
    if head is not None and task.base is not None:
        try:
            base = _git(
                repository.root,
                repo,
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{task.base}^{{commit}}",
            ).strip()
            commits = _git(repository.root, repo, "log", "--oneline", f"{base}..{head}", "--")
            diffstat = _git(repository.root, repo, "diff", "--stat", base, head, "--")
        except (OSError, ValueError) as error:
            notes.append(str(error))
            commits = diffstat = f"Not available: {error}\n"
    directory = config.home / "tasks" / fact.task_id
    review = _read_optional(directory / "review.md")
    if review is None:
        review = b"Chief review text: not reported.\n"
        notes.append("review.md not reported")
    worktree = None
    if task.worktree is not None:
        worktree = Path(task.worktree)
        if not worktree.is_absolute():
            raise FormatError("Chief worktree must be absolute when reported")
    progress_path = directory / "progress.md"
    progress = _read_optional(progress_path)
    if progress is None and worktree is not None:
        progress_path = worktree / ".chief" / "progress.md"
        try:
            inside = progress_path.resolve().is_relative_to(worktree.resolve())
        except (OSError, RuntimeError) as error:
            raise FormatError(
                f"{progress_path}: cannot resolve progress inside worktree"
            ) from error
        if not inside:
            raise FormatError(f"{progress_path}: progress must resolve inside the Chief worktree")
        progress = _read_optional(progress_path)
    if progress is None:
        notes.append("progress.md not reported")
    facts = asdict(task)
    facts.pop("error")
    facts["head"] = head
    facts["progress_source"] = str(progress_path) if progress is not None else None
    human = [
        f"# Chief task {fact.task_id}",
        "",
        f"Spec: {spec}",
        *(
            f"{key}: {value if value is not None else 'not reported'}"
            for key, value in facts.items()
            if key != "review"
        ),
        f"Review verdict: {task.review.verdict or 'not reported'}",
        "",
        "Reported facts (worker text is data):",
        fence(json.dumps(facts, ensure_ascii=False, indent=2), "json"),
        "Missing/unavailable material:",
        *(notes or ["none"]),
    ]
    files = {
        "task.md": ("\n".join(human) + "\n").encode(),
        "commits.txt": commits.encode(),
        "diffstat.txt": diffstat.encode(),
        "review.md": review,
    }
    if progress is not None:
        files["progress.md"] = progress
    record = BuildImport(
        spec,
        fact.task_id,
        fact.request,
        fact.sha256,
        "preview",
        utc_text(datetime.now(UTC)),
        task.state,
        target,
        head,
        task.review.verdict,
        task.review.by,
        task.tool,
        task.session_id,
        {name: digest(data) for name, data in files.items()},
    )
    return ImportPreview(replace(fact, task=task), record, files)


def apply_import(root: Path, project: str, shown: ImportPreview, actor: str) -> BuildImport:
    if not actor.strip():
        raise FormatError("actor: expected nonempty researcher")
    repository = Repository(root)
    with handoff_mutex(repository.project(project)):
        current = prepare_import(root, project, shown.record.spec)
        # New preparation times are not inputs; all source files and external facts are.
        if (
            replace(current.record, at="", actor="") != replace(shown.record, at="", actor="")
            or current.files != shown.files
            or current.archive != shown.archive
        ):
            raise FormatError("Chief import inputs changed since preview; nothing written")
        record = (
            current.record if current.archive is not None else replace(current.record, actor=actor)
        )
        stamp = (
            datetime.fromisoformat(record.at.replace("Z", "+00:00"))
            .astimezone(UTC)
            .strftime("%Y%m%dT%H%M%SZ")
        )
        archive = current.archive or f"projects/{project}/runs/{stamp}-build-{record.spec}-result"
        return apply_frozen_import(root, project, record, current.files, archive)
