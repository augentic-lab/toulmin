"""L2: decide project proposals: object drafts and rulings (H3), intake and reviews (H4).

Reason for this L2 addition (docs/protocols.md, H3): the agent marks an item ready by putting
it under ``projects/NAME/runs/proposals/``; the researcher decides it in ``toulmin decide``.
Application reuses ``new`` (create_object) and ``rule`` (apply_ruling) unchanged in meaning,
with the researcher as actor. Each decision is recorded in an outcome file beside the
proposal; the proposal itself is never edited, moved or deleted.

An ``applying`` outcome is written before anything else changes, so an interrupted
application is never repeated blindly: the next preview looks for the object or ruling it may
already have produced and offers to record that instead.

H4 (reason in docs/protocols.md, H4): an intake recommendation is recorded label by label with
``intake_review`` (whose own replay makes it safe to repeat) and is applied once every draft
label of its output has an outcome. A review request is started by the researcher's apply
only (D3); the sessions run in L3, which brackets them with ``begin_review`` and
``finish_review``. An interrupted round is never started again: the next apply records the
Runs it archived.

H5 (reason in docs/protocols.md, H5): a Brief proposal replaces named brief.md sections and is
refused once brief.md changed since drafting; a stage proposal is the first path that writes
PROJECT.md ``stage``. It is the researcher's ruling, applied only by their apply, with an
active Decision appended to recent_decisions; gate readiness is shown, never enforced.
"""

import difflib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from toulmin.core.atomic import digest, handoff_mutex, write_atomic
from toulmin.core.codec import decode, patch_header
from toulmin.core.documents import (
    DIRECTORIES,
    Document,
    FormatError,
    replace_section,
    sections,
)
from toulmin.core.handoff_transaction import PENDING
from toulmin.core.handoffs import append_decisions
from toulmin.core.identifiers import ObjectId, ObjectKind, ObjectRef
from toulmin.core.inspection import brief_text_errors
from toulmin.core.project import validate_project
from toulmin.core.project_proposals import (
    BRIEF,
    BUILD,
    INTAKE,
    OBJECT_KINDS,
    OUTCOME_SUFFIX,
    PROPOSALS,
    REVIEW,
    RULING,
    STAGE,
    BriefProposal,
    IntakeRecommendation,
    Outcome,
    ReviewRequest,
    RulingProposal,
    StageProposal,
    proposal_kind,
    render_outcome,
    validate_brief_proposal,
    validate_intake_recommendation,
    validate_outcome,
    validate_review_request,
    validate_ruling_proposal,
    validate_stage_proposal,
)
from toulmin.core.repository import Repository
from toulmin.core.review import INTAKE_FILE
from toulmin.core.schema import utc_text
from toulmin.core.skeletons import PLACEHOLDER
from toulmin.protocols.build import BuildPlan, preview_build
from toulmin.protocols.intake import create_object
from toulmin.protocols.review_intake import IntakeResult, OutputState, intake_review, output_state
from toulmin.protocols.ruling import RulingResult, apply_ruling
from toulmin.protocols.status import GateReadiness, project_status


@dataclass(frozen=True)
class Pending:
    path: str  # root-relative proposal file
    kind: str  # claim … spec, ruling, intake or review
    interrupted: bool  # an ``applying`` outcome exists


@dataclass(frozen=True)
class Inventory:
    items: tuple[Pending, ...]
    unrecognized: tuple[str, ...]  # files in runs/proposals that are not named as proposals
    errors: tuple[str, ...]


@dataclass(frozen=True)
class Preview:
    path: str
    kind: str
    sha256: str
    text: str  # the proposal as written
    problems: tuple[str, ...]
    target: str | None  # predicted object path (objects) or the ruled object ID (rulings)
    ruling: RulingProposal | None = None
    decision: str | None = None  # the Decision the ruling cites, resolved to D-NNN
    change: RulingResult | None = None  # the first (or only) object's change
    interrupted: bool = False
    recovered: str | None = None  # object or ruling an interrupted application produced
    intake: "IntakePreview | None" = None
    review: ReviewRequest | None = None
    runs: tuple[str, ...] = ()  # Runs an interrupted review round archived
    brief: BriefProposal | None = None
    stage: StageProposal | None = None
    diff: tuple[str, ...] = ()  # unified diff of the file the proposal writes (H5)
    before_sha256: str | None = None  # that file as previewed
    after: bytes | None = None  # that file exactly as apply writes it
    gate: GateReadiness | None = None  # readiness of the gate the stage change enters
    changes: tuple[RulingResult, ...] = ()  # every object a ruling still changes (R1 batch)
    build: BuildPlan | None = None
    done: tuple[str, ...] = ()  # batch objects an interrupted application already ruled


@dataclass(frozen=True)
class IntakePreview:
    recommendation: IntakeRecommendation
    state: OutputState
    remaining: tuple[str, ...]  # draft labels without an outcome, in output order


def outcome_path(relative: str) -> str:
    return relative.removesuffix(".md") + OUTCOME_SUFFIX


def _folder(project: str) -> str:
    return f"projects/{project}/{PROPOSALS}"


def _outcome(repository: Repository, relative: str) -> Outcome | None:
    candidate = outcome_path(relative)
    path = repository.path(candidate)
    if not path.exists() and not path.is_symlink():
        return None
    data = repository.path(candidate, "file").read_bytes()
    return validate_outcome(decode(data, candidate))


def inventory(root: Path, project: str) -> Inventory:
    """Undecided proposals of one project: object drafts first, then rulings, by filename."""
    repository = Repository(root)
    repository.project(project)
    folder = repository.path(_folder(project))
    if not folder.exists() and not folder.is_symlink():
        return Inventory((), (), ())
    repository.path(_folder(project), "directory")
    groups: dict[str, list[Pending]] = {
        INTAKE: [],
        "object": [],
        RULING: [],
        BRIEF: [],
        STAGE: [],
        BUILD: [],
        REVIEW: [],
    }
    unrecognized: list[str] = []
    errors: list[str] = []
    for entry in sorted(folder.iterdir()):
        name = entry.name
        relative = f"{_folder(project)}/{name}"
        if name.startswith(".") or name.endswith(OUTCOME_SUFFIX):
            continue
        kind = proposal_kind(name)
        if kind is None:
            unrecognized.append(relative)
            continue
        try:
            repository.path(relative, "file")
            outcome = _outcome(repository, relative)
        except (OSError, ValueError) as error:
            errors.append(str(error))
            continue
        if outcome is not None and outcome.disposition != "applying":
            continue
        item = Pending(relative, kind, outcome is not None)
        groups[kind if kind in groups else "object"].append(item)
    # Loop order: intake creates Objections, objects and rulings answer them, the Brief and a
    # stage ruling follow (a stage Decision draft is an object decided earlier), and a new
    # review round comes last, after the revisions it should see.
    ordered = tuple(item for group in groups.values() for item in group)
    return Inventory(ordered, tuple(unrecognized), tuple(errors))


def _resolve_decision(repository: Repository, project: str, value: str | None) -> str | None:
    """A Decision reference as given, or the D-NNN an applied decision proposal created."""
    if value is None or proposal_kind(value) != "decision":
        return value
    relative = f"{_folder(project)}/{value}"
    repository.path(relative, "file")
    outcome = _outcome(repository, relative)
    if outcome is None or outcome.disposition == "applying":
        raise FormatError(
            f"decision: proposal {value} is not decided yet; decide it first (decide offers "
            "object drafts before rulings)"
        )
    if outcome.disposition == "rejected":
        raise FormatError(f"decision: proposal {value} was rejected ({outcome.reason})")
    return outcome.result


def _load(repository: Repository, project: str, relative: str) -> tuple[str, bytes]:
    if not relative.startswith(_folder(project) + "/") or "/" in relative.removeprefix(
        _folder(project) + "/"
    ):
        raise FormatError(
            f"{relative}: proposal: expected a file directly under {_folder(project)}"
        )
    kind = proposal_kind(relative.rsplit("/", 1)[1])
    if kind is None:
        raise FormatError(f"{relative}: proposal: expected KIND-YYYYMMDDTHHMMSSZ[-name].md")
    return kind, repository.path(relative, "file").read_bytes()


def _created_after(
    repository: Repository, project: str, kind: str, raw: bytes, since: str
) -> str | None:
    """An object an interrupted application created: same body, created at or after ``since``."""
    body = decode(raw).body
    directory = repository.path(
        f"projects/{project}/{DIRECTORIES[OBJECT_KINDS[kind]]}", "directory"
    )
    for path in sorted(directory.glob("*.md")):
        document = decode(path.read_bytes(), str(path))
        if document.body == body and str(document.header.get("created", "")) >= since:
            return str(document.header["id"])
    return None


def _ruled(
    repository: Repository,
    project: str,
    proposal: RulingProposal,
    decision: str | None,
    target: str | None = None,
) -> bool:
    """Whether the object already carries everything the ruling proposal asks for."""
    document = repository.load(project, ObjectId.parse(target or proposal.object))
    if proposal.status is not None and document.header["status"] != proposal.status:
        return False
    if decision is not None and decision not in document.header.get("decisions", []):
        return False
    body = sections(document)
    return all(text.strip() in body.get(name, "") for name, text in proposal.texts.items())


def preview(root: Path, project: str, relative: str) -> Preview:
    """Everything decide shows for one proposal; writes nothing."""
    repository = Repository(root)
    repository.project(project)
    kind, raw = _load(repository, project, relative)
    sha = digest(raw)
    text = raw.decode("utf-8", errors="replace")
    outcome = _outcome(repository, relative)
    if outcome is not None and outcome.disposition != "applying":
        return Preview(relative, kind, sha, text, (f"already {outcome.disposition}",), None)
    interrupted = outcome is not None
    if kind in {RULING, INTAKE, REVIEW, BRIEF, STAGE, BUILD} and PLACEHOLDER in text:
        # R1 skeletons mark every open choice; none may reach a brief, a status or an intake.
        problem = "unfilled <fill: ...> placeholder; ask the agent to finish the draft"
        return Preview(relative, kind, sha, text, (problem,), None, interrupted=interrupted)
    if kind == BUILD:
        try:
            plan = preview_build(root, project, raw, relative)
            problems = plan.problems
            if outcome is not None and outcome.proposal_sha256 != sha:
                problems += (
                    "proposal changed after application started; restore the frozen request",
                )
            return Preview(
                relative, kind, sha, text, problems, None, interrupted=interrupted, build=plan
            )
        except (OSError, ValueError) as error:
            return Preview(relative, kind, sha, text, (str(error),), None, interrupted=interrupted)
    if kind == INTAKE:
        return _intake_preview(root, project, relative, sha, text, raw, interrupted)
    if kind == BRIEF:
        return _brief_preview(repository, project, relative, sha, text, raw, outcome is not None)
    if kind == STAGE:
        return _stage_preview(repository, project, relative, sha, text, raw, outcome is not None)
    if kind == REVIEW:
        runs = _runs_since(repository, project, outcome.at) if outcome is not None else ()
        try:
            request = validate_review_request(decode(raw, relative))
        except (OSError, ValueError) as error:
            return Preview(relative, kind, sha, text, (str(error),), None, interrupted=interrupted,
                           runs=runs)  # fmt: skip
        return Preview(relative, kind, sha, text, (), None, interrupted=interrupted,
                       review=request, runs=runs)  # fmt: skip
    if kind != RULING:
        recovered = None
        if outcome is not None:
            recovered = _created_after(repository, project, kind, raw, outcome.at)
        try:
            path = create_object(
                root, project, OBJECT_KINDS[kind], relative, "preview", False, preview=True
            )
        except (OSError, ValueError) as error:
            return Preview(
                relative,
                kind,
                sha,
                text,
                (str(error),),
                None,
                None,
                None,
                None,
                interrupted,
                recovered,
            )
        target = path.relative_to(repository.root).as_posix()
        return Preview(
            relative, kind, sha, text, (), target, None, None, None, interrupted, recovered
        )
    try:
        proposal = validate_ruling_proposal(decode(raw, relative))
    except (OSError, ValueError) as error:
        return Preview(
            relative, kind, sha, text, (str(error),), None, None, None, None, interrupted
        )
    try:
        decision = _resolve_decision(repository, project, proposal.decision)
        # An interrupted batch may have ruled some objects already; those are only recorded.
        done = tuple(
            target
            for target in proposal.targets
            if outcome is not None and _ruled(repository, project, proposal, decision, target)
        )
        recovered = ", ".join(proposal.targets) if len(done) == len(proposal.targets) else None
        changes = tuple(
            apply_ruling(
                root,
                project,
                target,
                "preview",
                False,
                status=proposal.status,
                decision=decision,
                links=proposal.links or None,
                texts=proposal.texts,
                preview=True,
            )
            for target in proposal.targets
            if target not in done
        )
        change = changes[0] if changes else None
    except (OSError, ValueError) as error:
        return Preview(
            relative,
            kind,
            sha,
            text,
            (str(error),),
            proposal.object,
            proposal,
            None,
            None,
            interrupted,
        )
    return Preview(
        relative,
        kind,
        sha,
        text,
        (),
        proposal.object,
        proposal,
        decision,
        change,
        interrupted,
        recovered,
        changes=changes,
        done=done if recovered is None else (),
    )


def _diff(before: str, after: str, name: str) -> tuple[str, ...]:
    lines = difflib.unified_diff(
        before.splitlines(), after.splitlines(), f"{name} (now)", f"{name} (after)", lineterm=""
    )
    return tuple(lines)


def _brief_preview(
    repository: Repository,
    project: str,
    relative: str,
    sha: str,
    text: str,
    raw: bytes,
    interrupted: bool,
) -> Preview:
    def fail(problem: str, proposal: BriefProposal | None = None) -> Preview:
        return Preview(relative, BRIEF, sha, text, (problem,), None, interrupted=interrupted,
                       brief=proposal)  # fmt: skip

    try:
        proposal = validate_brief_proposal(decode(raw, relative))
    except (OSError, ValueError) as error:
        return fail(str(error))
    path = f"projects/{project}/brief.md"
    current = repository.path(path, "file").read_bytes()
    now = current.decode("utf-8")
    if interrupted and all(
        sections_of(now).get(name, "").strip("\n") == content.strip("\n")
        for name, content in proposal.sections.items()
    ):
        return Preview(relative, BRIEF, sha, text, (), path, interrupted=True, recovered=path,
                       brief=proposal)  # fmt: skip
    if digest(current) != proposal.base_sha256:
        return fail(
            "brief.md changed since this proposal was drafted (base_sha256 differs); ask the "
            "agent to draft it again against the current brief",
            proposal,
        )
    after = now
    try:
        for name, content in proposal.sections.items():
            after = replace_section(after, name, content)
    except ValueError as error:
        return fail(f"brief.md: {error}", proposal)
    errors = brief_text_errors(repository, project, after)
    if errors:
        return fail("\n".join(errors), proposal)
    return Preview(relative, BRIEF, sha, text, (), path, interrupted=interrupted, brief=proposal,
                   diff=_diff(now, after, "brief.md"), before_sha256=digest(current),
                   after=after.encode())  # fmt: skip


def sections_of(text: str) -> dict[str, str]:
    """Level-two sections of a header-less Markdown file such as brief.md."""
    return sections(Document({}, text, "brief.md"))


def _active_decision(repository: Repository, project: str, value: str) -> None:
    try:
        reference = ObjectRef.parse(value)
    except ValueError as error:
        raise FormatError(f"{value}: decision: {error}") from error
    if reference.object_id.kind != ObjectKind.DECISION or reference.project not in {None, project}:
        raise FormatError(f"{value}: decision: expected a Decision of project {project}")
    decision, _ = repository.resolve(project, value)
    if decision.header["status"] != "active":
        raise FormatError(f"{value}: decision: only an active Decision can back a stage ruling")


def _stage_preview(
    repository: Repository,
    project: str,
    relative: str,
    sha: str,
    text: str,
    raw: bytes,
    interrupted: bool,
) -> Preview:
    def fail(problem: str, proposal: StageProposal | None = None) -> Preview:
        return Preview(relative, STAGE, sha, text, (problem,), None, interrupted=interrupted,
                       stage=proposal)  # fmt: skip

    try:
        proposal = validate_stage_proposal(decode(raw, relative))
    except (OSError, ValueError) as error:
        return fail(str(error))
    path = f"projects/{project}/PROJECT.md"
    before = repository.path(path, "file").read_bytes()
    charter = decode(before, path)
    validate_project(charter, project)
    gate = next(
        (item for item in project_status(repository.root, project).gates
         if item.enters == proposal.stage),
        None,
    )  # fmt: skip
    if not interrupted and charter.header["stage"] != proposal.current:
        return fail(
            f"PROJECT.md stage is {charter.header['stage']}, not {proposal.current} as drafted",
            proposal,
        )
    try:
        decision = _resolve_decision(repository, project, proposal.decision)
        assert decision is not None
        _active_decision(repository, project, decision)
    except (OSError, ValueError) as error:
        return fail(str(error), proposal)
    if (
        interrupted
        and charter.header["stage"] == proposal.stage
        and (decision in charter.header["recent_decisions"])
    ):
        return Preview(relative, STAGE, sha, text, (), path, interrupted=True, recovered=path,
                       stage=proposal, decision=decision, gate=gate)  # fmt: skip
    if charter.header["stage"] != proposal.current:
        return fail(
            f"PROJECT.md stage is {charter.header['stage']}, not {proposal.current} as drafted",
            proposal,
        )
    if repository.path(f"projects/{project}/{PENDING}").exists():
        return fail("a handoff application is unfinished; finish it before a stage ruling")
    after = patch_header(
        before,
        {
            "stage": proposal.stage,
            "recent_decisions": append_decisions(charter.header["recent_decisions"], [decision]),
        },
    )
    validate_project(decode(after, path), project)
    return Preview(relative, STAGE, sha, text, (), path, interrupted=interrupted, stage=proposal,
                   decision=decision, diff=_diff(before.decode(), after.decode(), "PROJECT.md"),
                   before_sha256=digest(before), after=after, gate=gate)  # fmt: skip


def _intake_preview(
    root: Path, project: str, relative: str, sha: str, text: str, raw: bytes, interrupted: bool
) -> Preview:
    def fail(problem: str) -> Preview:
        return Preview(relative, INTAKE, sha, text, (problem,), None, interrupted=interrupted)

    try:
        recommendation = validate_intake_recommendation(decode(raw, relative))
        state = output_state(root, project, recommendation.output)
    except (OSError, ValueError) as error:
        return fail(str(error))
    given = {item.label: item for item in recommendation.items}
    unknown = sorted(set(given) - set(state.drafts))
    if unknown:
        return fail(f"{recommendation.output}: {unknown[0]}: no such draft label")
    remaining = tuple(label for label in state.drafts if label not in state.recorded)
    missing = [label for label in remaining if label not in given]
    if missing:
        return fail(
            f"recommendations: no recommendation for {', '.join(missing)}; cover every label"
        )
    take, reject, partly = choices(recommendation, remaining)
    try:
        if remaining:
            intake_review(root, project, recommendation.output, "preview", False, take, reject,
                          partly, preview=True)  # fmt: skip
    except (OSError, ValueError) as error:
        return fail(str(error))
    target = f"{state.run}: {recommendation.output}"
    return Preview(relative, INTAKE, sha, text, (), target, interrupted=interrupted,
                   intake=IntakePreview(recommendation, state, remaining))  # fmt: skip


def choices(
    recommendation: IntakeRecommendation, labels: tuple[str, ...]
) -> tuple[dict[str, str | None], dict[str, str], dict[str, str]]:
    """The recommended outcomes for ``labels`` in intake_review's take/reject/partly form."""
    take: dict[str, str | None] = {}
    reject: dict[str, str] = {}
    partly: dict[str, str] = {}
    for item in recommendation.items:
        if item.label not in labels:
            continue
        if item.outcome == "take":
            take[item.label] = item.severity
        elif item.outcome == "reject":
            reject[item.label] = item.reason
        else:
            assert item.object is not None
            partly[item.label] = item.object
    return take, reject, partly


def record_intake(
    root: Path,
    project: str,
    relative: str,
    actor: str,
    sha256: str,
    take: dict[str, str | None],
    reject: dict[str, str],
    partly: dict[str, str],
    approval_text: str,
) -> tuple[IntakeResult | None, Outcome | None]:
    """Record the researcher's chosen outcomes; the recommendation is applied once none remain.

    The choices are the researcher's, label by label; they may differ from the recommendation.
    """
    if not actor.strip():
        raise FormatError("actor: expected nonempty string")
    current = preview(root, project, relative)
    if current.sha256 != sha256:
        raise FormatError(f"{relative}: changed since the preview; nothing written")
    if current.problems or current.intake is None:
        raise FormatError(f"{relative}: {(current.problems or ('not an intake item',))[0]}")
    output = current.intake.recommendation.output
    result = None
    if take or reject or partly:
        result = intake_review(root, project, output, actor, True, take, reject, partly)
    state = output_state(root, project, output)
    if any(label not in state.recorded for label in state.drafts):
        return result, None
    record = (Path(output).parent / INTAKE_FILE).as_posix()
    done = Outcome(relative, sha256, "applied", actor, utc_text(datetime.now(UTC)),
                   approval_text, None, record)  # fmt: skip
    _write_outcome(Repository(root), relative, done, replace=False)
    return result, done


def _runs_since(repository: Repository, project: str, since: str) -> tuple[str, ...]:
    """Runs archived at or after an interrupted review round's marker."""
    directory = repository.path(f"projects/{project}/{DIRECTORIES[ObjectKind.RUN]}", "directory")
    found = []
    for path in sorted(directory.glob("R-*.md")):
        document = decode(path.read_bytes(), str(path))
        if str(document.header.get("created", "")) >= since:
            found.append(str(document.header["id"]))
    return tuple(sorted(found, key=lambda run: int(run[2:])))


def begin_review(
    root: Path, project: str, relative: str, actor: str, sha256: str, approval_text: str
) -> Outcome:
    """Write the ``applying`` marker before any session starts; refuse an interrupted round."""
    if not actor.strip():
        raise FormatError("actor: expected nonempty string")
    current = preview(root, project, relative)
    if current.sha256 != sha256:
        raise FormatError(f"{relative}: changed since the preview; nothing started")
    if current.problems or current.review is None:
        raise FormatError(f"{relative}: {(current.problems or ('not a review request',))[0]}")
    if current.interrupted:
        raise FormatError(f"{relative}: an interrupted round is recorded, never started again")
    marker = Outcome(relative, sha256, "applying", actor, utc_text(datetime.now(UTC)),
                     approval_text, None, None)  # fmt: skip
    _write_outcome(Repository(root), relative, marker, replace=False)
    return marker


def finish_review(root: Path, project: str, marker: Outcome, result: str) -> Outcome:
    """Record what the round produced (or, after an interruption, the Runs it archived)."""
    done = Outcome(marker.proposal, marker.proposal_sha256, "applied", marker.actor, marker.at,
                   marker.approval_text, None, result)  # fmt: skip
    _write_outcome(Repository(root), marker.proposal, done, replace=True)
    return done


def interrupted_marker(root: Path, project: str, relative: str) -> Outcome:
    """The ``applying`` marker of an interrupted proposal."""
    repository = Repository(root)
    repository.project(project)
    _load(repository, project, relative)
    outcome = _outcome(repository, relative)
    if outcome is None or outcome.disposition != "applying":
        raise FormatError(f"{relative}: no interrupted application to record")
    return outcome


def _write_outcome(
    repository: Repository, relative: str, outcome: Outcome, *, replace: bool
) -> None:
    write_atomic(repository.path(outcome_path(relative)), render_outcome(outcome), replace=replace)


def apply(
    root: Path, project: str, relative: str, actor: str, sha256: str, approval_text: str
) -> Outcome:
    """Apply the proposal exactly as previewed (``sha256``); return the applied outcome."""
    if not actor.strip():
        raise FormatError("actor: expected nonempty string")
    repository = Repository(root)
    current = preview(root, project, relative)
    if current.sha256 != sha256:
        raise FormatError(f"{relative}: changed since the preview; nothing written")
    if current.problems:
        raise FormatError(f"{relative}: {current.problems[0]}")
    if current.kind in {INTAKE, REVIEW, BUILD}:
        raise FormatError(f"{relative}: {current.kind} proposals use their own apply steps")
    now = utc_text(datetime.now(UTC))
    marker = Outcome(relative, sha256, "applying", actor, now, approval_text, None, None)
    # The marker is written exclusively first: a second decider fails here, and a crash after
    # this point leaves evidence that the next preview checks before applying again.
    _write_outcome(repository, relative, marker, replace=current.interrupted)
    result = current.recovered
    if current.kind in {BRIEF, STAGE}:
        if result is None:
            assert current.target is not None and current.after is not None
            _write_checked(repository, project, current.target, current.before_sha256,
                           current.after)  # fmt: skip
        if current.stage is not None:
            result = f"stage {current.stage.stage} ({current.decision})"
        else:
            result = current.target
    elif result is None and current.kind != RULING:
        created = create_object(root, project, OBJECT_KINDS[current.kind], relative, actor, True)
        result = created.stem
    elif result is None:
        ruling = current.ruling
        assert ruling is not None
        # Each object is written atomically; a crash between two leaves the marker, and the
        # next preview rules only the objects not yet carrying the ruling (``done``).
        for target in ruling.targets:
            if target in current.done:
                continue
            apply_ruling(
                root,
                project,
                target,
                actor,
                True,
                status=ruling.status,
                decision=current.decision,
                links=ruling.links or None,
                texts=ruling.texts,
            )
        result = ", ".join(ruling.targets)
    done = Outcome(relative, sha256, "applied", actor, now, approval_text, None, result)
    _write_outcome(repository, relative, done, replace=True)
    return done


def _write_checked(
    repository: Repository, project: str, relative: str, before: str | None, after: bytes
) -> None:
    """Write brief.md or PROJECT.md exactly as previewed, under the project's writer lock."""
    with handoff_mutex(repository.project(project)):
        destination = repository.path(relative, "file")
        if digest(destination.read_bytes()) != before:
            raise FormatError(f"{relative}: changed since the preview; nothing written")
        write_atomic(destination, after, replace=True)


def reject(
    root: Path, project: str, relative: str, actor: str, reason: str, sha256: str
) -> Outcome:
    """Record the researcher's reason for not applying the proposal; nothing else changes."""
    if not actor.strip():
        raise FormatError("actor: expected nonempty string")
    if not reason.strip():
        raise FormatError("reason: a rejection records the researcher's reason")
    repository = Repository(root)
    repository.project(project)
    _, raw = _load(repository, project, relative)
    if digest(raw) != sha256:
        raise FormatError(f"{relative}: changed since the preview; nothing written")
    existing = _outcome(repository, relative)
    if existing is not None:
        if existing.disposition != "applying":
            raise FormatError(f"{relative}: already {existing.disposition}")
        raise FormatError(
            f"{relative}: an interrupted application must be finished or checked first"
        )
    outcome = Outcome(
        relative, sha256, "rejected", actor, utc_text(datetime.now(UTC)), None, reason.strip(), None
    )
    _write_outcome(repository, relative, outcome, replace=False)
    return outcome


def begin_build(
    root: Path,
    project: str,
    relative: str,
    actor: str,
    sha256: str,
    approval_text: str,
    *,
    now: datetime | None = None,
) -> Outcome:
    """Claim this request exclusively before L3 archives the contract and invokes Chief."""
    if not actor.strip():
        raise FormatError("actor: expected nonempty string")
    current = preview(root, project, relative)
    if current.sha256 != sha256:
        raise FormatError(f"{relative}: changed since the preview; nothing started")
    if current.problems or current.build is None:
        raise FormatError(f"{relative}: {(current.problems or ('not a build request',))[0]}")
    if current.interrupted:
        return interrupted_marker(root, project, relative)
    marker = Outcome(
        relative,
        sha256,
        "applying",
        actor,
        utc_text(now or datetime.now(UTC)),
        approval_text,
        None,
        None,
    )
    _write_outcome(Repository(root), relative, marker, replace=False)
    return marker


def finish_build(root: Path, marker: Outcome, task_id: str, failure: str | None = None) -> Outcome:
    """Record Chief's result; failed requests stay archived and need a new request to retry."""
    done = Outcome(
        marker.proposal,
        marker.proposal_sha256,
        "failed" if failure else "applied",
        marker.actor,
        marker.at,
        marker.approval_text,
        failure,
        None if failure else f"chief task {task_id}",
    )
    _write_outcome(Repository(root), marker.proposal, done, replace=True)
    return done
