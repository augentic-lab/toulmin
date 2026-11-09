"""L2: write a fillable draft skeleton under runs/drafts/, never a formal object.

R1 (reason in docs/protocols.md, R1): proposal kinds get skeletons prefilled from the files
(current statuses, the brief digest and sections, the stage, undecided review draft labels), so a
project agent no longer reads the protocol text or Toulmin's source to learn the formats.
"""

import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from toulmin.core.atomic import digest
from toulmin.core.codec import decode
from toulmin.core.documents import STATUSES, FormatError
from toulmin.core.identifiers import ObjectId, ObjectKind
from toulmin.core.project import STAGES, validate_project
from toulmin.core.project_proposals import BRIEF, INTAKE, REVIEW, RULING, STAGE
from toulmin.core.proposal_skeletons import (
    DraftLine,
    RulingTarget,
    brief_skeleton,
    intake_skeleton,
    review_skeleton,
    ruling_skeleton,
    stage_skeleton,
)
from toulmin.core.repository import Repository
from toulmin.core.skeletons import skeleton
from toulmin.protocols.inputs import resolve_inputs
from toulmin.protocols.review import OUTPUT_FILE
from toulmin.protocols.review_intake import output_state
from toulmin.protocols.ruling import LINKS, SECTIONS_BY_KIND

PROPOSAL_KINDS = (RULING, INTAKE, REVIEW, BRIEF, STAGE)

DRAFTS = "runs/drafts"
_ATTEMPTS = 100


def write_draft(
    root: Path,
    project: str,
    kind: ObjectKind,
    name: str | None = None,
    actor: str | None = None,
    now: datetime | None = None,
    role: str | None = None,
    claims: list[str] | None = None,
) -> Path:
    """Create a new skeleton file without overwriting; return its absolute path.

    With `role` (Run drafts only), role and input_files come from the role's manifest.
    """
    repository = Repository(root)
    base = _base(repository, project, kind.value, name, now)
    role_inputs = None
    if role is not None or claims is not None:
        if kind != ObjectKind.RUN:
            raise FormatError(f"{kind.value}: role: only a Run draft takes a role's inputs")
        if role is None:
            raise FormatError("claim: selecting Claims needs a role")
        resolved = resolve_inputs(root, project, role, claims)
        role_inputs = (resolved.role, resolved.files)
    # Validate the complete skeleton before touching the filesystem.
    skeleton(kind, project, f"projects/{project}/{DRAFTS}/{base}.md", actor, role_inputs)
    return _publish(
        repository,
        project,
        base,
        lambda relative: skeleton(kind, project, relative, actor, role_inputs),
    )


def _base(
    repository: Repository, project: str, kind: str, name: str | None, now: datetime | None
) -> str:
    if name is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise FormatError(f"{name}: name: expected ASCII letters, digits, '_' or '-' (max 64)")
    repository.project(project)
    stamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{kind}-{stamp}" + (f"-{name}" if name else "")


def _publish(repository: Repository, project: str, base: str, render: Callable[[str], str]) -> Path:
    repository.path(f"projects/{project}/runs", "directory")
    directory = repository.path(f"projects/{project}/{DRAFTS}")
    directory.mkdir(exist_ok=True)
    repository.path(f"projects/{project}/{DRAFTS}", "directory")
    for attempt in range(1, _ATTEMPTS + 1):
        filename = base + ("" if attempt == 1 else f"-{attempt}") + ".md"
        relative = f"projects/{project}/{DRAFTS}/{filename}"
        destination = repository.path(relative)
        data = render(relative).encode("utf-8")
        # Publish a complete file via an exclusive link so no draft is overwritten or partial.
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".draft-", suffix=".tmp") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            try:
                os.link(stream.name, destination)
            except FileExistsError:
                continue
        return destination
    raise FormatError(f"{directory}: draft: {_ATTEMPTS} drafts named {base} already exist")


@dataclass(frozen=True)
class ProposalOptions:
    """What the agent already knows; everything else is read from the files."""

    objects: tuple[str, ...] = ()  # ruling
    status: str | None = None  # ruling
    decision: str | None = None  # ruling, stage
    run: str | None = None  # intake: R-NNN or the root-relative output path
    sections: tuple[str, ...] = ()  # brief
    personas: tuple[str, ...] = ()  # review
    models: tuple[str, ...] = ()  # review
    claims: tuple[str, ...] = ()  # review
    stage: str | None = None  # stage: the stage to enter; default the next one


_OPTION_KINDS = {
    "objects": (RULING,),
    "status": (RULING,),
    "decision": (RULING, STAGE),
    "run": (INTAKE,),
    "sections": (BRIEF,),
    "personas": (REVIEW,),
    "models": (REVIEW,),
    "claims": (REVIEW,),
    "stage": (STAGE,),
}


def write_proposal_draft(
    root: Path,
    project: str,
    kind: str,
    options: ProposalOptions,
    name: str | None = None,
    now: datetime | None = None,
) -> Path:
    """Write a prefilled proposal skeleton under runs/drafts/; never under proposals/."""
    if kind not in PROPOSAL_KINDS:
        raise FormatError(f"{kind}: expected one of {', '.join(PROPOSAL_KINDS)}")
    for field, kinds in _OPTION_KINDS.items():
        if getattr(options, field) not in (None, ()) and kind not in kinds:
            raise FormatError(f"{kind}: {field}: only for {' and '.join(kinds)} drafts")
    repository = Repository(root)
    base = _base(repository, project, kind, name, now)
    relative = f"projects/{project}/{DRAFTS}/{base}.md"
    render = _RENDERERS[kind](repository, project, options)
    render(relative)  # every check runs before the filesystem is touched
    return _publish(repository, project, base, render)


Render = Callable[[str], str]


def _ruling(repository: Repository, project: str, options: ProposalOptions) -> Render:
    if not options.objects:
        raise FormatError("ruling: object: name the object to rule (repeat for several)")
    if len(set(options.objects)) != len(options.objects):
        raise FormatError("ruling: object: an object is named twice")
    targets = []
    kinds = set()
    for value in options.objects:
        try:
            object_id = ObjectId.parse(value)
        except ValueError as error:
            raise FormatError(f"{value}: object: {error}") from error
        if object_id.kind == ObjectKind.RUN:
            raise FormatError(f"{value}: object: Run outcomes are immutable once archived")
        document = repository.load(project, object_id)
        targets.append(RulingTarget(str(object_id), str(document.header["status"])))
        kinds.add(object_id.kind)
    if len(kinds) > 1:
        raise FormatError("ruling: object: one ruling covers objects of one kind")
    kind = kinds.pop()
    statuses = STATUSES[kind]
    if options.status is not None and options.status not in statuses:
        raise FormatError(f"{options.status}: status: expected one of {', '.join(statuses)}")
    unchanged = [item.object_id for item in targets if item.status == options.status]
    if unchanged:
        raise FormatError(f"{', '.join(unchanged)}: status: already {options.status}")
    sections = tuple(sorted(SECTIONS_BY_KIND[kind]))
    links = tuple(sorted(LINKS.get(kind, ())))
    return lambda relative: ruling_skeleton(
        project, relative, targets, statuses, sections, links, options.status, options.decision
    )


def _intake(repository: Repository, project: str, options: ProposalOptions) -> Render:
    if options.run is None:
        raise FormatError("intake: run: name the review Run (R-NNN) or its output path")
    output = options.run
    if re.fullmatch(r"R-[0-9]{3,}", output):
        run = repository.load(project, ObjectId.parse(output))
        output = f"{run.header['output']}/{OUTPUT_FILE}"
    state = output_state(repository.root, project, output)
    output = repository.relative(output)
    drafts = [
        DraftLine(draft.label, draft.target, draft.severity, draft.content)
        for label, draft in state.drafts.items()
        if label not in state.recorded
    ]
    return lambda relative: intake_skeleton(project, relative, output, drafts)


def _review(repository: Repository, project: str, options: ProposalOptions) -> Render:
    repository.project(project)
    for value in options.claims:
        try:
            claim = ObjectId.parse(value)
        except ValueError as error:
            raise FormatError(f"{value}: claim: {error}") from error
        if claim.kind != ObjectKind.CLAIM:
            raise FormatError(f"{value}: claim: expected a Claim ID")
        repository.load(project, claim)
    return lambda relative: review_skeleton(
        project, relative, options.personas or None, options.models or None,
        options.claims or None,
    )  # fmt: skip


def _brief(repository: Repository, project: str, options: ProposalOptions) -> Render:
    from toulmin.protocols.project_proposals import sections_of  # avoids an import cycle

    if not options.sections:
        raise FormatError("brief: section: name each brief.md section to change")
    path = f"projects/{project}/brief.md"
    raw = repository.path(path, "file").read_bytes()
    current = sections_of(raw.decode("utf-8"))
    missing = [name for name in options.sections if name not in current]
    if missing:
        raise FormatError(f"{missing[0]}: section: brief.md has {', '.join(current)}")
    chosen = {name: current[name] for name in dict.fromkeys(options.sections)}
    return lambda relative: brief_skeleton(project, relative, digest(raw), chosen)


def _stage(repository: Repository, project: str, options: ProposalOptions) -> Render:
    path = f"projects/{project}/PROJECT.md"
    charter = decode(repository.path(path, "file").read_bytes(), path)
    validate_project(charter, project)
    current = str(charter.header["stage"])
    target = options.stage
    if target is None:
        index = STAGES.index(current)
        if index + 1 == len(STAGES):
            raise FormatError(f"stage: {current} is the last stage; name the stage with --to")
        target = STAGES[index + 1]
    if target not in STAGES or target == current:
        raise FormatError(f"{target}: to: expected a stage other than {current}")
    return lambda relative: stage_skeleton(project, relative, current, target, options.decision)


_RENDERERS: dict[str, Callable[[Repository, str, ProposalOptions], Render]] = {
    RULING: _ruling,
    INTAKE: _intake,
    REVIEW: _review,
    BRIEF: _brief,
    STAGE: _stage,
}
