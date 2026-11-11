"""R8 B4: confirmed deterministic execution, outside the workbench, with file-based recovery."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from toulmin.adapters import verify
from toulmin.adapters.chief import ChiefClient, load_config
from toulmin.core.atomic import digest, handoff_mutex
from toulmin.core.documents import FormatError
from toulmin.core.inspection import current_claim, inspect_project
from toulmin.core.repository import Repository
from toulmin.core.schema import utc_text
from toulmin.core.verification import BuildVerification, CheckResult
from toulmin.protocols import build_verify
from toulmin.protocols.build import frozen_contract, import_records, load_spec, verification_records


@dataclass(frozen=True)
class VerifyPreview:
    record: BuildVerification
    archive: str | None = None

    @property
    def label(self) -> str:
        return (
            f"{self.record.spec} at {self.record.head[:12]}: "
            f"{len(self.record.checks)} check(s) in a fresh clone"
        )


def _repository_problem(client: ChiefClient, repo: str, head: str) -> str | None:
    try:
        if not Path(repo).is_dir():
            return "missing directory"
        client.check_repository(repo, head)
    except (OSError, ValueError) as error:
        if "base_branch:" in str(error):
            return f"commit {head} absent ({error})"
        return f"repository unavailable ({error})"
    return None


def _resolve_repository(
    client: ChiefClient, project: str, archived: str, head: str
) -> tuple[str, str]:
    problem = _repository_problem(client, archived, head)
    if problem is None:
        return archived, f"archived path {archived} contains {head}"
    mapped = client.config.repos.get(project)
    fallback_problem: str | None
    if mapped is None:
        fallback_problem = "no [repos] entry"
    elif mapped == archived:
        fallback_problem = f"same as archived path: {problem}"
    else:
        fallback_problem = _repository_problem(client, mapped, head)
        if fallback_problem is None:
            source = (
                f"archived path {archived} missing on this machine"
                if problem == "missing directory"
                else f"archived path {archived}: {problem}"
            )
            return mapped, f"{source}; using [repos] {project} = {mapped}, which contains {head}"
    raise FormatError(
        f"verification repository unavailable: archived path {archived}: {problem}; "
        f"[repos] {project} = {mapped or '<not configured>'}: {fallback_problem}; "
        f"clone the repository and set [repos] {project} in tools/chief.local.toml"
    )


def prepare_verification(root: Path, project: str, spec: str) -> VerifyPreview:
    repository = Repository(root)
    source = load_spec(repository, project, spec)
    imports = [
        (archive, record)
        for archive, record in import_records(repository, project)
        if record.spec == spec and record.disposition == "applied"
    ]
    if not imports:
        raise FormatError(f"{spec}: no completed import")
    import_archive, imported = max(
        imports,
        key=lambda item: (datetime.fromisoformat(item[1].at.replace("Z", "+00:00")), item[0]),
    )
    if imported.head is None:
        raise FormatError(f"{spec}: latest import has no reported head commit")
    previous = [
        (archive, record)
        for archive, record in verification_records(repository, project)
        if record.spec == spec and record.head == imported.head
    ]
    pending = [
        (archive, record) for archive, record in previous if record.disposition == "applying"
    ]
    passing = [
        (archive, record)
        for archive, record in previous
        if record.disposition == "applied" and record.passed
    ]
    if len(pending) > 1:
        raise FormatError(f"{spec}: multiple interrupted verification records")
    if pending or passing:
        archive, saved = max(
            pending or passing,
            key=lambda item: (datetime.fromisoformat(item[1].at.replace("Z", "+00:00")), item[0]),
        )
        if pending:
            client = ChiefClient(repository.root, load_config(root))
            if problem := _repository_problem(client, saved.repo, saved.head):
                raise FormatError(
                    f"interrupted verification keeps repository {saved.repo}: {problem}; "
                    "restore that repository; recovery will not switch paths"
                )
        return VerifyPreview(saved, archive)
    if source.header["status"] != "awaiting-acceptance":
        raise FormatError(
            f"{spec}: status {source.header['status']}; verification needs awaiting-acceptance"
        )
    contract_path, contract = frozen_contract(
        repository, project, spec, imported.request, imported.request_sha256
    )
    checks = contract.get("checks")
    if (
        not isinstance(checks, list)
        or not checks
        or any(
            not isinstance(value, str) or not value.strip() or "<fill:" in value for value in checks
        )
    ):
        raise FormatError(f"{contract_path}: checks must be frozen, nonempty commands")
    repo = contract.get("repo")
    if not isinstance(repo, str) or not Path(repo).is_absolute():
        raise FormatError(f"{contract_path}: repo: expected an absolute archived repository path")
    config = load_config(root)
    client = ChiefClient(repository.root, config)
    repo, reason = _resolve_repository(client, project, repo, imported.head)
    claim, owner = repository.resolve(project, source.header["target"])
    target = current_claim(inspect_project(repository, owner).objects, claim.object_id)[-1]
    claim_ref = str(target) if owner == project else f"{owner}/{target}"
    record = BuildVerification(
        spec,
        imported.task_id,
        import_archive,
        contract_path,
        digest(repository.path(contract_path, "file").read_bytes()),
        digest(repository.path(f"projects/{project}/specs/{spec}.md", "file").read_bytes()),
        repo,
        imported.head,
        claim_ref,
        tuple(checks),
        config.verify_timeout_seconds,
        "preview",
        utc_text(datetime.now(UTC)),
        repo_reason=reason,
    )
    return VerifyPreview(record)


def apply_verification(
    root: Path, project: str, shown: VerifyPreview, actor: str
) -> BuildVerification:
    if not actor.strip():
        raise FormatError("actor: expected nonempty researcher")
    repository = Repository(root)
    with handoff_mutex(repository.project(project)):
        current = prepare_verification(root, project, shown.record.spec)
        if (
            replace(current.record, at="", actor="") != replace(shown.record, at="", actor="")
            or current.archive != shown.archive
        ):
            raise FormatError("verification inputs changed since preview; nothing written")
        record = (
            current.record if current.archive is not None else replace(current.record, actor=actor)
        )
        archive = current.archive or build_verify.begin_verification(root, project, record)
        if record.disposition == "applied":
            return build_verify.finish_verification(root, project, archive)
        if not record.execution_completed:
            previous = record.previous
            if record.snapshot is not None:
                previous = tuple(dict.fromkeys((*previous, record.snapshot)))
            record = replace(record, previous=previous, results=(), files=None, snapshot=None)
            build_verify.save_verification(repository, archive, record)

            def report(results: tuple[CheckResult, ...], env: bytes) -> None:
                nonlocal record
                record = build_verify.checkpoint(repository, archive, record, results, env)

            results, env = verify.run_checks(
                repository.root,
                record.repo,
                record.head,
                record.checks,
                record.timeout_seconds,
                report,
                repo_reason=record.repo_reason,
            )
            record = build_verify.checkpoint(
                repository, archive, record, results, env, completed=True
            )
        return build_verify.finish_verification(root, project, archive)
