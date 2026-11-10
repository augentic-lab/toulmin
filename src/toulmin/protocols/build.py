"""R8 B2: derive and preview frozen build contracts; no external tools or state access.

The L2 reason is recorded in docs/protocols.md: a researcher reviews one explicit contract
before implementation, with checks compared against the Spec, without changing its status.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from toulmin.core.atomic import digest
from toulmin.core.build import BuildImport, BuildTask, parse_import
from toulmin.core.codec import decode, encode
from toulmin.core.documents import Document, FormatError, sections
from toulmin.core.identifiers import ObjectId, ObjectKind, ObjectRef
from toulmin.core.inspection import current_claim, inspect_project
from toulmin.core.project import validate_project
from toulmin.core.project_proposals import (
    OUTCOME_SUFFIX,
    BuildRequest,
    validate_build_request,
    validate_outcome,
)
from toulmin.core.render import fence
from toulmin.core.repository import Repository
from toulmin.core.verification import BuildVerification, VerificationFact, parse_verification
from toulmin.protocols.status import GateItem, project_status


def spec_commands(criteria: str) -> tuple[str, ...]:
    """Extract inline code and shell fences, keeping each fenced script as one check.

    Other fences are expected output, even if they contain backticks. Console prompts are
    stripped; when prompts are present, unprompted output lines are excluded.
    """
    return _acceptance_parts(criteria)[0]


def _acceptance_parts(criteria: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    commands: list[str] = []
    expected: list[str] = []
    fence = ""
    language = ""
    block: list[str] = []
    for line in criteria.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\n"))
        if fence:
            if (
                marker
                and marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence)
                and not marker[2].strip()
            ):
                if language in {"sh", "bash", "shell", "console"}:
                    content = "".join(block).strip()
                    if language == "console" and any(s.startswith("$ ") for s in block):
                        content = "\n".join(
                            s[2:].rstrip("\n") for s in block if s.startswith(("$ ", "> "))
                        )
                    if content:
                        commands.append(content)
                elif content := "".join(block).strip("\n"):
                    expected.append(content)
                fence = ""
                block = []
            else:
                block.append(line)
        elif marker:
            fence, language = marker[1], marker[2].strip().lower()
        else:
            commands.extend(
                match[2].strip() for match in re.finditer(r"(`+)(.+?)\1", line) if match[2].strip()
            )
    return tuple(dict.fromkeys(commands)), tuple(expected)


def expected_output_note(criteria: str) -> str | None:
    """Explain exit-status-only checks when the Spec also gives literal output to compare."""
    commands, expected = _acceptance_parts(criteria)
    if not expected:
        return None
    # Keep printf's format on one line, quoting shell metacharacters and literal percent signs.
    output = (
        expected[0]
        .replace("\\", "\\\\")
        .replace("%", "%%")
        .replace("\n", r"\n")
        .replace("\r", r"\r")
        .replace("\t", r"\t")
    )
    command = commands[0] if commands else "COMMAND"
    quoted = "'" + output.replace("'", "'\"'\"'") + "'"
    example = f'test "$({command})" = "$(printf {quoted})"'
    return (
        "Checks pass on exit status only; the Spec shows expected output. "
        f"Compare output explicitly, for example: {example}"
    )


def load_spec(repository: Repository, project: str, value: str) -> Document:
    try:
        identifier = ObjectId.parse(value)
    except ValueError as error:
        raise FormatError(f"{value}: spec: {error}") from error
    if identifier.kind != ObjectKind.SPEC:
        raise FormatError(f"{value}: spec: expected a Spec ID")
    return repository.load(project, identifier)


def derive_contract(
    project: str, request: BuildRequest, spec: Document, claim: Document, charter: Document
) -> dict[str, Any]:
    """Pure derivation: only the Spec, target Statement, constraints and request Context."""
    body = sections(spec)
    task_id = request.task_id or f"{project}-{request.spec.replace('-', '').lower()}"
    requirements = body["Requirements"]
    first = re.split(r"(?<=[.!?])\s+", " ".join(requirements.split()), maxsplit=1)[0]
    if len(first) > 60:
        boundary = first.rfind(" ", 0, 60)
        # No space to break at: cut inside the word rather than leave only the ellipsis.
        first = (first[:boundary] if boundary > 0 else first[:59]) + "…"
    target = str(spec.header["target"])
    if claim.object_id != ObjectRef.parse(target).object_id:
        target += f" (current: {claim.object_id})"
    goal = (
        f"## Requirements\n{requirements}\n"
        f"## Acceptance criteria\n{body['Acceptance criteria']}\n"
        f"## Target Claim {target}: Statement\n{sections(claim)['Statement']}\n"
        f"## Project constraints\n{sections(charter)['Constraints']}\n"
    )
    if request.context.strip():
        goal += f"## Context for the implementer\n{request.context}\n"
    goal += (
        "Do not change these acceptance criteria or checks; ask instead. "
        f"Deliver on branch chief/{task_id}.\n"
    )
    contract: dict[str, Any] = {
        "repo": request.repo,
        "name": f"{project} {request.spec}: {first}",
        "goal": goal,
        "checks": list(request.checks),
        "protected": list(request.protected),
        "test_first": request.test_first,
        "tool": request.tool,
        "budget": dict(request.budget),
    }
    if request.base_branch is not None:
        contract["base_branch"] = request.base_branch
    return contract


def contract_bytes(contract: dict[str, Any]) -> bytes:
    return (json.dumps(contract, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


@dataclass(frozen=True)
class BuildPlan:
    request: BuildRequest
    task_id: str
    contract: dict[str, Any]
    spec_commands: tuple[str, ...]
    gate: GateItem | None
    problems: tuple[str, ...]
    note: str | None = None

    @property
    def checks_match(self) -> bool:
        return self.request.checks == self.spec_commands


def preview_build(root: Path, project: str, raw: bytes, relative: str) -> BuildPlan:
    repository = Repository(root)
    request = validate_build_request(decode(raw, relative))
    spec = load_spec(repository, project, request.spec)
    claim, owner = repository.resolve(project, str(spec.header["target"]))
    current = current_claim(inspect_project(repository, owner).objects, claim.object_id)[-1]
    if current != claim.object_id:
        claim = repository.load(owner, current)
    charter = repository.read(f"projects/{project}/PROJECT.md")
    validate_project(charter, project)
    contract = derive_contract(project, request, spec, claim, charter)
    report = project_status(root, project)
    g3 = next(g for g in report.gates if g.gate == "G3")
    gate = next((item for item in g3.items if item.label.startswith(request.spec + " ")), None)
    problems = list(report.errors)
    if spec.header["status"] not in {"todo", "in-progress"}:
        problems.append(
            f"{request.spec}: status {spec.header['status']}; expected todo or in-progress"
        )
    if gate is None or not gate.met or g3.met is None:
        problems.append(
            f"{request.spec}: G3 item not met: {gate.detail if gate else 'not available'}"
        )
    criteria = sections(spec).get("Acceptance criteria", "")
    commands = spec_commands(criteria)
    task_id = request.task_id or f"{project}-{request.spec.replace('-', '').lower()}"
    return BuildPlan(
        request, task_id, contract, commands, gate, tuple(problems), expected_output_note(criteria)
    )


@dataclass(frozen=True)
class BuildFact:
    spec: str
    request: str | None = None
    task_id: str | None = None
    at: str | None = None
    sha256: str | None = None
    pending: bool = False
    imported: bool = False
    archive: str | None = None
    task: BuildTask | None = None
    verification: VerificationFact | None = None


def import_records(repository: Repository, project: str) -> tuple[tuple[str, BuildImport], ...]:
    """Workspace journals only; never follow a path into an external integration home."""
    found = []
    runs = repository.path(f"projects/{project}/runs", "directory")
    for path in sorted(runs.glob("*-build-*-result/import.json")):
        relative = path.relative_to(repository.root).as_posix()
        record = parse_import(repository.path(relative, "file").read_bytes(), relative)
        archive = relative.rsplit("/", 1)[0]
        if not path.parent.name.endswith(f"-build-{record.spec}-result"):
            raise FormatError(f"{relative}: import Spec differs from its archive name")
        if record.disposition == "applied":
            run = repository.load(project, ObjectId.parse(record.run or ""))
            expected = "completed" if record.state == "done" else "failed"
            if (
                run.header["output"] != archive
                or run.header["role"] != "implementer"
                or run.header["status"] != expected
            ):
                raise FormatError(f"{relative}: import receipt does not match its Run")
        found.append((archive, record))
    return tuple(found)


def build_facts(
    root: Path, project: str, chief: Mapping[str, BuildTask] | None = None
) -> tuple[BuildFact, ...]:
    """Latest applied request per Spec; external snapshots must be injected by L3."""
    repository = Repository(root)
    repository.project(project)
    facts = {
        path.stem: BuildFact(path.stem)
        for path in repository.path(f"projects/{project}/specs", "directory").glob("S-*.md")
    }
    records = import_records(repository, project)
    folder = repository.path(f"projects/{project}/runs/proposals")
    if not folder.exists():
        return tuple(facts[key] for key in sorted(facts))
    for path in sorted(folder.glob("build-*.md")):
        if path.name.endswith(OUTCOME_SUFFIX):
            continue
        relative = path.relative_to(repository.root).as_posix()
        raw = repository.path(relative, "file").read_bytes()
        target = decode(raw, relative).header.get("spec")
        if not isinstance(target, str) or target not in facts:
            continue
        receipt = repository.path(relative.removesuffix(".md") + OUTCOME_SUFFIX)
        if not receipt.exists():
            facts[target] = replace(facts[target], pending=True)
            continue
        outcome = validate_outcome(decode(receipt.read_bytes(), str(receipt)))
        if outcome.disposition == "applying":
            facts[target] = replace(facts[target], pending=True)
            continue
        if outcome.disposition != "applied":
            continue
        request = validate_build_request(decode(raw, relative))
        if outcome.proposal != relative or outcome.proposal_sha256 != digest(raw):
            raise FormatError(f"{relative}: applied build request changed")
        previous = facts[target]
        if previous.at is not None and (
            datetime.fromisoformat(previous.at.replace("Z", "+00:00")),
            previous.request or "",
        ) > (datetime.fromisoformat(outcome.at.replace("Z", "+00:00")), relative):
            continue
        task_id = request.task_id or f"{project}-{request.spec.replace('-', '').lower()}"
        if outcome.result != f"chief task {task_id}":
            raise FormatError(f"{relative}: applied result differs from the request task ID")
        matching = [
            (archive, record)
            for archive, record in records
            if record.spec == target
            and record.task_id == task_id
            and record.request == relative
            and record.request_sha256 == outcome.proposal_sha256
        ]
        if len(matching) > 1:
            raise FormatError(f"{task_id}: multiple import records; resolve the conflict")
        archive, imported = matching[0] if matching else (None, None)
        facts[target] = BuildFact(
            target,
            relative,
            task_id,
            outcome.at,
            outcome.proposal_sha256,
            previous.pending,
            imported is not None and imported.disposition == "applied",
            archive,
            chief.get(task_id) if chief is not None else None,
        )
    verified = verification_facts(repository, project, records)
    return tuple(replace(facts[key], verification=verified.get(key)) for key in sorted(facts))


def build_line(fact: BuildFact) -> str:
    if fact.task_id is None:
        return f"{fact.spec}: no applied build request"
    task = fact.task
    if task is None or task.error is not None:
        state = "Chief state not read" + (f": {task.error}" if task is not None else "")
    else:
        state = f"{task.state or 'not reported'}; review {task.review.verdict or 'not reported'}"
    line = f"{fact.spec} -> Chief task {fact.task_id}: {state}" + (
        "; imported" if fact.imported else ""
    )
    if fact.verification is not None:
        verified = fact.verification
        if verified.passed:
            line += f"; verification passed at {(verified.head or '')[:12]}"
        elif verified.failed:
            line += f"; verification failed at {(verified.head or '')[:12]}"
    return line


def import_proposals(record: BuildImport, archive: str) -> dict[str, bytes]:
    """Pure drafts from the frozen import, with no automatic Evidence/ruling intake."""
    if record.state == "abandoned":
        return {}
    if record.run is None:
        raise FormatError("import: a Run is required before drafting proposals")
    stamp = (
        datetime.fromisoformat(record.at.replace("Z", "+00:00"))
        .astimezone(UTC)
        .strftime("%Y%m%dT%H%M%SZ")
    )
    suffix = f"{stamp}-build-{record.spec}.md"
    decision, evidence, ruling = (f"{kind}-{suffix}" for kind in ("decision", "evidence", "ruling"))
    source = {"kind": "run", "ref": record.run, "path": f"{archive}/task.md"}
    reason = (
        f"Chief task {record.task_id} reports completion at {record.head or 'not reported'}; "
        f"cross review {record.verdict or 'not reported'} by {record.reviewer or 'not reported'}."
    )
    drafts = {
        decision: Document(
            {"schema_version": 1, "source": source, "related": [record.spec]},
            f"## Context\n{reason}\n\n## Choice\nMove {record.spec} to awaiting-acceptance "
            "with the imported test Evidence.\n\n## Rejected alternatives\n"
            "Do not mark the Spec passed: independent verification remains separate.\n\n"
            "## Rationale\nRecord the implementer's completion report; "
            "the researcher rules on this proposal.\n",
        ),
        evidence: Document(
            {
                "schema_version": 1,
                "source": source,
                "target": record.claim,
                "direction": "supports",
                "kind": "computation",
                "grade": "model-asserted",
                "provenance": [
                    {
                        "description": "Chief task facts and pinned head",
                        "path": f"{archive}/task.md",
                    },
                    {
                        "description": "Chief cross review (or explicit missing-review note)",
                        "path": f"{archive}/review.md",
                    },
                ],
            },
            f"## Material\nChecks passed under Chief at {record.head or 'not reported'}. {reason}\n"
            "This is the implementer's report, not independent acceptance.\n",
        ),
        ruling: Document(
            {
                "schema_version": 1,
                "kind": "ruling-proposal",
                "object": record.spec,
                "status": "awaiting-acceptance",
                "decision": decision,
                "links": {"evidence": [evidence]},
            },
            f"## Why\n{reason} The linked Evidence and Decision must be applied first.\n",
        ),
    }
    return {name: encode(document) for name, document in drafts.items()}


def frozen_contract(
    repository: Repository, project: str, spec: str, request: str, sha256: str
) -> tuple[str, dict[str, Any]]:
    """Find exactly the contract archived for a confirmed request, never current Spec prose."""
    paths = []
    for path in repository.path(f"projects/{project}/runs", "directory").glob(
        f"*-build-{spec}/request.json"
    ):
        relative = path.relative_to(repository.root).as_posix()
        intent = json.loads(repository.path(relative, "file").read_bytes())
        if not isinstance(intent, dict):
            raise FormatError(f"{relative}: expected a build request record")
        if intent.get("proposal") == request and intent.get("proposal_sha256") == sha256:
            paths.append(relative.rsplit("/", 1)[0] + "/contract.json")
    if len(paths) != 1:
        raise FormatError(f"{spec}: expected one frozen contract for the applied request")
    raw = json.loads(repository.path(paths[0], "file").read_bytes())
    if not isinstance(raw, dict):
        raise FormatError(f"{paths[0]}: expected a contract object")
    return paths[0], raw


def verification_records(
    repository: Repository, project: str
) -> tuple[tuple[str, BuildVerification], ...]:
    found = []
    for path in sorted(
        repository.path(f"projects/{project}/runs", "directory").glob("*-verify-*/verify.json")
    ):
        relative = path.relative_to(repository.root).as_posix()
        record = parse_verification(repository.path(relative, "file").read_bytes(), relative)
        archive = relative.rsplit("/", 1)[0]
        if not re.fullmatch(
            rf"[0-9]{{8}}T[0-9]{{6}}Z-verify-{record.spec}(?:-[0-9]+)?", path.parent.name
        ):
            raise FormatError(f"{relative}: verification Spec differs from archive name")
        if record.files is not None:
            for name, sha in record.files.items():
                if (
                    digest(
                        repository.path(f"{archive}/{record.snapshot}/{name}", "file").read_bytes()
                    )
                    != sha
                ):
                    raise FormatError(f"{archive}/{name}: verification checkpoint changed")
                if (
                    record.disposition == "applied"
                    and digest(repository.path(f"{archive}/{name}", "file").read_bytes()) != sha
                ):
                    raise FormatError(f"{archive}/{name}: verification artifact changed")
        if digest(repository.path(record.contract, "file").read_bytes()) != record.contract_sha256:
            raise FormatError(f"{record.contract}: frozen verification contract changed")
        if record.disposition == "applied":
            run = repository.load(project, ObjectId.parse(record.run or ""))
            if (
                run.header["output"] != archive
                or run.header["role"] != "verifier"
                or run.header["status"] != "completed"
            ):
                raise FormatError(f"{relative}: verification receipt differs from its Run")
        found.append((archive, record))
    return tuple(found)


def verification_facts(
    repository: Repository, project: str, imports: tuple[tuple[str, BuildImport], ...]
) -> dict[str, VerificationFact]:
    records = verification_records(repository, project)
    result = {}
    for spec in repository.path(f"projects/{project}/specs", "directory").glob("S-*.md"):
        candidates = [
            (archive, record)
            for archive, record in imports
            if record.spec == spec.stem and record.disposition == "applied"
        ]
        if not candidates:
            continue
        _, latest = max(
            candidates,
            key=lambda item: (datetime.fromisoformat(item[1].at.replace("Z", "+00:00")), item[0]),
        )
        if latest.head is None:
            continue
        matching = [
            (archive, record)
            for archive, record in records
            if record.spec == spec.stem and record.head == latest.head
        ]
        passing = [
            (archive, record)
            for archive, record in matching
            if record.disposition == "applied" and record.passed
        ]
        pending = [
            (archive, record) for archive, record in matching if record.disposition == "applying"
        ]
        if len(pending) > 1:
            raise FormatError(f"{spec.stem}: multiple interrupted verifications for {latest.head}")
        chosen = max(
            pending or passing or matching,
            key=lambda item: (datetime.fromisoformat(item[1].at.replace("Z", "+00:00")), item[0]),
            default=None,
        )
        source = repository.load(project, ObjectId.parse(spec.stem))
        result[spec.stem] = VerificationFact(
            latest.head,
            latest.task_id,
            bool(pending) or (source.header["status"] == "awaiting-acceptance" and not passing),
            bool(passing),
            bool(chosen and chosen[1].execution_completed and not chosen[1].passed and not passing),
            chosen[0] if chosen else None,
            bool(pending),
        )
    return result


def verification_output(record: BuildVerification) -> bytes:
    lines = [
        f"# Verification of {record.spec} at {record.head}",
        "",
        "Independent execution of frozen checks; the researcher rules on the Claim.",
        "Runs code written by an AI worker on this machine, as you, without network isolation.",
        "",
    ]
    if record.previous:
        lines += ["Earlier interrupted material: " + ", ".join(record.previous), ""]
    for index, result in enumerate(record.results, 1):
        status = "timed out" if result.exit_status is None else str(result.exit_status)
        lines += [
            f"## Check {index}",
            "Command:",
            fence(result.command, "sh"),
            f"Exit status: {status}",
            f"Duration: {result.duration_seconds:.6f} seconds",
            "",
            "Stdout" + (" (truncated at 64 KiB)" if result.stdout_truncated else "") + ":",
            fence(result.stdout, "text"),
            "Stderr" + (" (truncated at 64 KiB)" if result.stderr_truncated else "") + ":",
            fence(result.stderr, "text"),
        ]
    if not record.execution_completed:
        lines += ["Execution not yet recorded as complete; this output does not establish a pass."]
    return ("\n".join(lines) + "\n").encode()


def verification_proposals(record: BuildVerification, archive: str) -> dict[str, bytes]:
    if not record.passed or record.run is None:
        return {}
    suffix = archive.rsplit("/", 1)[1] + ".md"
    decision, evidence, ruling = (f"{kind}-{suffix}" for kind in ("decision", "evidence", "ruling"))
    output, environment = f"{archive}/output.md", f"{archive}/environment.txt"
    source = {"kind": "run", "ref": record.run, "path": output}
    method = f"re-ran the frozen {record.spec} checks in a fresh clone at {record.head}"
    result = f"All {len(record.checks)} frozen checks exited 0 at {record.head}."
    drafts = {
        decision: Document(
            {"schema_version": 1, "source": source, "related": [record.spec]},
            f"## Context\n{result}\n\n## Choice\nMark {record.spec} passed with the "
            "independent verification Evidence.\n\n"
            "## Rejected alternatives\nDo not rely on the implementer's own tests "
            "or cross review alone.\n\n"
            "## Rationale\nThe frozen checks were rerun in a separate clean clone at the "
            "imported commit; the researcher rules on their adequacy.\n",
        ),
        evidence: Document(
            {
                "schema_version": 1,
                "source": source,
                "target": record.claim,
                "direction": "supports",
                "kind": "computation",
                "grade": "verified",
                "verification": {
                    "method": method,
                    "result": result,
                    "artifacts": [output, environment],
                },
                "provenance": [
                    {
                        "description": "Independent frozen-check commands and results",
                        "path": output,
                    },
                    {
                        "description": "Verification environment and pinned commit",
                        "path": environment,
                    },
                ],
            },
            f"## Material\n{result}\n{method}. This verifies these checks in this environment, "
            "not their adequacy or portability.\n",
        ),
        ruling: Document(
            {
                "schema_version": 1,
                "kind": "ruling-proposal",
                "object": record.spec,
                "status": "passed",
                "decision": decision,
                "links": {"evidence": [evidence]},
            },
            f"## Why\n{result} The researcher decides whether this independent check suffices.\n",
        ),
    }
    return {name: encode(document) for name, document in drafts.items()}
