"""R8 B2: derive and preview frozen build contracts; no external tools or state access.

The L2 reason is recorded in docs/protocols.md: a researcher reviews one explicit contract
before implementation, with checks compared against the Spec, without changing its status.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from toulmin.core.codec import decode
from toulmin.core.documents import Document, FormatError, sections
from toulmin.core.identifiers import ObjectId, ObjectKind, ObjectRef
from toulmin.core.inspection import current_claim, inspect_project
from toulmin.core.project import validate_project
from toulmin.core.project_proposals import BuildRequest, validate_build_request
from toulmin.core.repository import Repository
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
    first = next((line.strip() for line in requirements.splitlines() if line.strip()), request.spec)
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
