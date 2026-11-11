"""L2: the research map (V2): stage, gates, suggested moves and the argument tree, from files.

Reason for this L2 addition (docs/protocols.md, V2): the project loop is deliberately not
enforced, so the researcher needs one view of where a project is and what can happen next.
Everything here is recomputed from the files on every call; nothing is stored, nothing is
changed, and every move is a suggestion naming who would act. ``next_moves`` is the single
rule table behind both ``toulmin map`` and the ACTIONS of the agent's state card, so the
researcher and the agent read the same suggestions.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from toulmin.core.build import BuildTask
from toulmin.core.codec import decode
from toulmin.core.documents import Document, sections
from toulmin.core.identifiers import ObjectId, ObjectKind, ObjectRef, validate_project_name
from toulmin.core.inspection import ProjectSnapshot, current_claim, inspect_project
from toulmin.core.project_proposals import (
    INTAKE,
    OUTCOME_SUFFIX,
    PROPOSALS,
    RULING,
    STAGE,
    validate_intake_recommendation,
    validate_outcome,
    validate_ruling_proposal,
)
from toulmin.core.repository import Repository
from toulmin.protocols import project_proposals
from toulmin.protocols.build import BuildFact, build_facts, build_line, other_host_line
from toulmin.protocols.calibration import REVIEW, operation
from toulmin.protocols.review import OUTPUT_FILE
from toulmin.protocols.review_intake import output_state
from toulmin.protocols.status import (
    NO_BLOCKING,
    GateReadiness,
    awaiting_support_ruling,
    project_status,
    summary,
    unheld,
)

YOU, AGENT, EITHER = "you", "agent", "either"
MOVE_LIMIT = 3
TYPE_ORDER = ("problem", "magnitude", "mechanism", "novelty", "assumption", "deployability")
SEVERITY_ORDER = {"fatal": 0, "major": 1, "minor": 2}
KILL = "Kill criteria written in brief.md"


@dataclass(frozen=True)
class Move:
    actor: str  # you, agent or either
    text: str
    how: str  # where it happens: a command or the proposal it produces


@dataclass(frozen=True)
class Facts:
    """What the rule table reads; all derived from files."""

    stage: str | None
    invalid: bool
    gates: tuple[GateReadiness, ...]
    proposals: int  # undecided project proposals
    undecided: tuple[tuple[str, tuple[str, ...]], ...]  # review Runs: labels without intake
    uncovered: tuple[str, ...]  # review Runs with undecided labels and no intake proposal
    objections: tuple[tuple[str, str], ...]  # open, without a pending ruling: (id, severity)
    current_claims: bool
    reviewed: bool  # a completed review Run is newer than every current Claim
    handoff_due: str | None = None  # R4: the stage ruled after the last applied handoff
    builds: tuple[BuildFact, ...] = ()
    supportable: tuple[str, ...] = ()  # Claims meeting supported conditions, no ruling pending


@dataclass(frozen=True)
class Node:
    object_id: str
    facts: tuple[str, ...]
    summary: str
    children: tuple["Node", ...] = ()


@dataclass(frozen=True)
class ResearchMap:
    project: str
    stage: str | None
    gates: tuple[GateReadiness, ...]
    pending: tuple[project_proposals.Pending, ...]
    undecided: tuple[tuple[str, tuple[str, ...]], ...]  # review Runs: labels without intake
    moves: tuple[Move, ...]
    claims: tuple[Node, ...]  # current Claims with their Evidence, Objections and Decisions
    superseded: tuple[tuple[str, ...], ...]  # revision chains, old to current
    decisions: tuple[Node, ...]  # Decisions not shown under any Claim
    elsewhere: tuple[str, ...]  # objects aimed at another project's Claims
    errors: tuple[str, ...]
    builds: tuple[BuildFact, ...] = ()


# R5: the rows toward G3-G5; {missing} is filled with the gate's unmet items.
BUILD_WORK = (
    (
        "brief-final",
        "G3",
        Move(
            AGENT,
            "Work toward G3: draft Specs whose target is a current Claim and whose Acceptance "
            "criteria name runnable checks: {missing}.",
            "toulmin draft spec -> runs/proposals/",
        ),
    ),
    (
        "build",
        "G4",
        Move(
            EITHER,
            "Work toward G4: the implementer finishes each Spec and its test report is taken as "
            "supporting Evidence listed on the Spec, then the Spec is ruled "
            "awaiting-acceptance: {missing}.",
            "test report in runs/ -> Evidence + ruling proposals",
        ),
    ),
    (
        "accept",
        "G5",
        Move(
            YOU,
            "Work toward G5: run each Spec's acceptance checks independently (yourself or a "
            "verifier session), archive that as a Run with role verifier, take its verified "
            "Evidence, then rule the Spec passed: {missing}.",
            "Run (role verifier) -> Evidence -> ruling proposals",
        ),
    ),
)


def _hold(gate: GateReadiness) -> Move:
    return Move(
        AGENT,
        f"{gate.gate} conditions hold; the researcher may rule the stage change to "
        f"{gate.enters} (propose it as a stage proposal).",
        "runs/proposals/decision-… + stage-…",
    )


def _missing(gate: GateReadiness, skip: tuple[str, ...] = ()) -> str:
    return "; ".join(
        item.label + (f" ({item.detail})" if item.detail else "")
        for item in gate.items
        if not item.met and item.label not in skip
    )


def next_moves(facts: Facts, limit: int = MOVE_LIMIT) -> tuple[Move, ...]:
    """The first matching rows of the rule table (design V1 section 3, M4); never a ruling."""
    if facts.invalid:
        return (Move(YOU, "Resolve the reported file errors, then refresh.", "edit the files"),)
    moves: list[Move] = []
    if facts.proposals:
        moves.append(
            Move(
                YOU,
                f"Run `toulmin decide` for {facts.proposals} pending proposal(s).",
                "toulmin decide",
            )
        )
    for behind in unheld(facts.stage, facts.gates):
        moves.append(
            Move(
                YOU,
                f"The stage {facts.stage} is past {behind.gate}, which does not hold: "
                f"{_missing(behind)}. Rule whether to keep the stage or return the project.",
                "toulmin status NAME; a stage proposal if you return it",
            )
        )
    g3 = next((gate for gate in facts.gates if gate.gate == "G3"), None)
    for build in facts.builds:
        task = build.task
        if build.task_id is None:
            met = (
                g3 is not None
                and g3.met is not None
                and any(item.label.startswith(build.spec + " ") and item.met for item in g3.items)
            )
            if facts.stage == "build" and met and not build.pending:
                moves.append(
                    Move(
                        AGENT,
                        f"Draft a build request for {build.spec} (`toulmin draft build`).",
                        "toulmin draft build NAME --spec " + build.spec,
                    )
                )
        elif task is not None and task.other_host is not None and not build.imported:
            # Once the result is imported (on that host, then synced), nothing remains there.
            moves.append(
                Move(
                    YOU,
                    other_host_line(build.task_id, task.other_host),
                    "continue on " + task.other_host,
                )
            )
        elif task is not None and task.error is None:
            if task.state == "running":
                moves.append(
                    Move(
                        EITHER,
                        f"Chief task {build.task_id} is running for {build.spec}; "
                        "keep `chief watch` running",
                        "chief watch",
                    )
                )
            elif task.state == "needs-you":
                if not task.kickoff_at:
                    moves.append(
                        Move(
                            YOU,
                            f"Chief task {build.task_id} has not started: accept the worker's "
                            f"prompt in AoE, then `chief kickoff {build.task_id}`",
                            f"chief kickoff {build.task_id}",
                        )
                    )
                else:
                    moves.append(
                        Move(
                            YOU,
                            f"Chief task {build.task_id} needs you: `chief inbox`.",
                            "chief inbox",
                        )
                    )
            elif task.state == "review":
                moves.append(
                    Move(
                        YOU,
                        f"Accept or return Chief task {build.task_id}: "
                        "`chief close` / `chief nudge`.",
                        "chief close / chief nudge",
                    )
                )
            elif task.state == "done" and not build.imported:
                moves.append(
                    Move(
                        YOU,
                        f"Import the result of {build.task_id} in `toulmin decide`.",
                        "toulmin decide",
                    )
                )
            elif task.state == "abandoned" and not build.imported:
                moves.append(
                    Move(
                        YOU,
                        f"Chief task {build.task_id} was abandoned: "
                        "import it as failed or re-request.",
                        "toulmin decide / toulmin draft build",
                    )
                )
    for build in facts.builds:
        verification = build.verification
        if verification is None:
            continue
        if verification.failed and not (build.task and build.task.other_host):
            moves.append(
                Move(
                    YOU,
                    f"{build.spec} failed verification at {(verification.head or '')[:12]}: "
                    f"return it with `chief nudge {verification.task_id} …` "
                    "or draft a new build request",
                    "chief nudge / toulmin draft build",
                )
            )
        if verification.available:
            moves.append(Move(YOU, f"Verify {build.spec} in `toulmin decide`", "toulmin decide"))
    if facts.handoff_due:
        moves.append(
            Move(
                AGENT,
                f"Prepare a handoff draft: the stage changed to {facts.handoff_due} after the "
                "last applied handoff, so the recorded next step is stale; the researcher may "
                "then continue in a fresh session.",
                "toulmin aoe handoff",
            )
        )
    if facts.uncovered:
        moves.append(
            Move(
                AGENT,
                f"Recommend intake for the review drafts of {', '.join(facts.uncovered)} "
                "(one intake recommendation per output).",
                "runs/proposals/intake-…",
            )
        )
    if facts.objections:
        listed = ", ".join(f"{item} ({severity})" for item, severity in facts.objections)
        moves.append(
            Move(
                AGENT,
                f"Inspect open objections and draft responses or rulings for the researcher: "
                f"{listed}.",
                "runs/proposals/ruling-…",
            )
        )
    if facts.supportable:
        listed = ", ".join(facts.supportable)
        moves.append(
            Move(
                AGENT,
                f"Propose supported rulings for Claims that meet the conditions (verified "
                f"support, no open fatal or major Objection): {listed}. Each needs a Decision "
                "naming it; the researcher rules.",
                "toulmin draft ruling NAME --object C-NNN --status supported",
            )
        )
    gates = {gate.gate: gate for gate in facts.gates}
    # Undecided review drafts may still become fatal or major Objections: a gate that looks
    # met is not offered for a stage ruling until every draft has an intake outcome.
    settled = not facts.undecided
    if facts.stage == "explore" and (gate := gates.get("G1")) and gate.met is not None:
        if gate.met:
            if settled:
                moves.append(_hold(gate))
        else:
            moves.append(
                Move(
                    AGENT,
                    f"Draft the missing core Claims for researcher confirmation: {_missing(gate)}.",
                    "Claim drafts -> runs/proposals/",
                )
            )
    if facts.stage == "critique" and (gate := gates.get("G2")) and gate.met is not None:
        if facts.current_claims and not facts.reviewed:
            moves.append(
                Move(
                    AGENT,
                    "Request a review round of the current Claims; the researcher starts it "
                    "in `toulmin decide`.",
                    "runs/proposals/review-…",
                )
            )
        if gate.met:
            if settled:
                moves.append(_hold(gate))
        else:
            if any(item.label == KILL and not item.met for item in gate.items):
                moves.append(
                    Move(AGENT, "Propose Kill criteria for brief.md.", "runs/proposals/brief-…")
                )
            rest = _missing(gate, (KILL, NO_BLOCKING))
            if rest:
                moves.append(Move(AGENT, f"Work toward G2: {rest}.", "proposals"))
    for stage, name, move in BUILD_WORK:
        if facts.stage != stage or not (gate := gates.get(name)) or gate.met is None:
            continue
        if gate.met:
            if settled:
                moves.append(_hold(gate))
        else:
            live = {
                build.spec
                for build in facts.builds
                if build.request is not None
                and build.task_id is not None
                and build.task is not None
                and build.task.error is None
                and (
                    build.task.state in {"running", "needs-you", "review"}
                    or (build.task.other_host is not None and not build.imported)
                )
            }
            skip = (
                tuple(item.label for item in gate.items if item.label.split(" ", 1)[0] in live)
                if name == "G4"
                else ()
            )
            missing = _missing(gate, skip)
            if missing or not skip:
                moves.append(Move(move.actor, move.text.format(missing=missing), move.how))
    if not moves:
        moves.append(
            Move(
                EITHER,
                "Continue the research discussion; prepare a handoff draft when pausing.",
                "toulmin open",
            )
        )
    return tuple(moves[:limit])


def _time(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def move_facts(
    root: Path,
    project: str,
    snapshot: ProjectSnapshot,
    gates: tuple[GateReadiness, ...],
    pending: tuple[project_proposals.Pending, ...],
) -> Facts:
    """Collect the rule table's inputs; an unreadable proposal simply covers nothing."""
    repository = Repository(root)
    runs = {doc.object_id: doc for doc in snapshot.objects if doc.object_id.kind == ObjectKind.RUN}
    outputs = {f"{doc.header['output']}/{OUTPUT_FILE}": str(key) for key, doc in runs.items()}
    covered: set[str] = set()
    answered: set[str] = set()
    for item in pending:
        if item.kind not in {INTAKE, RULING}:
            continue
        try:
            document = decode(repository.path(item.path, "file").read_bytes(), item.path)
            if item.kind == INTAKE:
                output = validate_intake_recommendation(document).output
                if output in outputs:
                    covered.add(outputs[output])
            else:
                for target in validate_ruling_proposal(document).targets:
                    reference = ObjectRef.parse(target)
                    if reference.project in {None, project}:
                        answered.add(str(reference.object_id))
        except (OSError, ValueError):
            continue  # decide shows the problem when it offers the proposal
    objections = sorted(
        (
            doc
            for doc in snapshot.objects
            if doc.object_id.kind == ObjectKind.OBJECTION
            and doc.header["status"] == "open"
            and str(doc.object_id) not in answered
        ),
        key=lambda doc: (SEVERITY_ORDER.get(doc.header["severity"], 3), doc.object_id.number),
    )
    claims = [
        doc
        for doc in snapshot.objects
        if doc.object_id.kind == ObjectKind.CLAIM and doc.header["status"] != "superseded"
    ]
    newest_claim = max((_time(doc.header["created"]) for doc in claims), default=None, key=_key)
    reviews = [
        _time(doc.header["created"])
        for doc in runs.values()
        if operation(str(doc.header["role"])) == REVIEW and doc.header["status"] == "completed"
    ]
    newest_review = max(reviews, default=None, key=_key)
    undecided = []
    for key, doc in sorted(runs.items(), key=lambda pair: pair[0].number):
        if operation(str(doc.header["role"])) != REVIEW or doc.header["status"] != "completed":
            continue
        try:
            state = output_state(root, project, f"{doc.header['output']}/{OUTPUT_FILE}")
        except (OSError, ValueError):
            continue  # no draft block or no output: nothing to take in (calibration says so)
        labels = tuple(label for label in state.drafts if label not in state.recorded)
        if labels:
            undecided.append((str(key), labels))
    reviewed = (
        newest_review is not None and newest_claim is not None and newest_review > newest_claim
    )
    stage = snapshot.charter.header["stage"] if snapshot.charter is not None else None
    handoff = snapshot.charter.header["last_handoff"] if snapshot.charter is not None else None
    return Facts(
        stage=stage,
        invalid=bool(snapshot.errors),
        gates=gates,
        proposals=len(pending),
        undecided=tuple(undecided),
        uncovered=tuple(run for run, _ in undecided if run not in covered),
        objections=tuple((str(doc.object_id), doc.header["severity"]) for doc in objections),
        current_claims=bool(claims),
        reviewed=reviewed,
        handoff_due=stage if _stage_after_handoff(repository, project, handoff) else None,
        supportable=tuple(
            str(claim)
            for claim in awaiting_support_ruling(snapshot, project)
            if str(claim) not in answered
        ),
    )


def _stage_after_handoff(repository: Repository, project: str, handoff: object) -> bool:
    """Whether an applied stage proposal is newer than the last applied handoff (R4).

    Session records are named by their UTC application time, so the names compare as text
    with the outcome's ``at`` in the same compact form. A stage edited by hand has no outcome
    and raises nothing here.
    """
    folder = repository.root / f"projects/{project}/{PROPOSALS}"
    newest = ""
    for path in folder.glob(f"{STAGE}-*{OUTCOME_SUFFIX}") if folder.is_dir() else ():
        try:
            outcome = validate_outcome(decode(path.read_bytes(), str(path)))
        except (OSError, ValueError):
            continue
        if outcome.disposition == "applied":
            newest = max(newest, outcome.at.replace("-", "").replace(":", ""))
    if not newest:
        return False
    if not isinstance(handoff, str):
        return True
    return newest > handoff[: len("YYYYMMDDTHHMMSSZ")]


def _key(value: datetime | None) -> float:
    return value.timestamp() if value is not None else float("-inf")


def _text(document: Document, section: str) -> str:
    return summary(document, section) if section in sections(document) else ""


def _decision(document: Document) -> Node:
    return Node(str(document.object_id), (document.header["status"],), _text(document, "Choice"))


def research_map(
    root: Path, project: str, *, chief: Mapping[str, BuildTask] | None = None
) -> ResearchMap:
    """The map of one project, from files only; a partial view when data is invalid."""
    validate_project_name(project)
    repository = Repository(root)
    snapshot = inspect_project(repository, project)
    errors = list(snapshot.errors)
    gates = project_status(root, project).gates
    try:
        found = project_proposals.inventory(root, project)
        pending = found.items
        errors.extend(found.errors)
    except (OSError, ValueError) as error:
        pending = ()
        errors.append(str(error))
    facts = move_facts(root, project, snapshot, gates, pending)
    try:
        builds = build_facts(root, project, chief)
    except (OSError, ValueError) as error:
        builds = ()
        errors.append(str(error))
    facts = replace(facts, builds=builds)
    if errors and not facts.invalid:
        facts = replace(facts, invalid=True)
    claims, superseded, decisions, elsewhere = _tree(snapshot, project, builds)
    return ResearchMap(
        project,
        facts.stage,
        gates,
        pending,
        facts.undecided,
        next_moves(facts),
        claims,
        superseded,
        decisions,
        elsewhere,
        tuple(sorted(set(errors))),
        builds,
    )


def _tree(
    snapshot: ProjectSnapshot, project: str, builds: tuple[BuildFact, ...] = ()
) -> tuple[tuple[Node, ...], tuple[tuple[str, ...], ...], tuple[Node, ...], tuple[str, ...]]:
    objects = snapshot.objects
    by_id = {doc.object_id: doc for doc in objects}
    claims = [doc for doc in objects if doc.object_id.kind == ObjectKind.CLAIM]
    current = [doc for doc in claims if doc.header["status"] != "superseded"]
    chains = tuple(
        tuple(str(item) for item in current_claim(objects, doc.object_id))
        for doc in sorted(claims, key=lambda doc: doc.object_id.number)
        if doc.header["status"] == "superseded"
    )
    children: dict[ObjectId, list[tuple[int, Node]]] = {doc.object_id: [] for doc in current}
    shown: set[str] = set()
    elsewhere: list[str] = []

    def decisions_of(document: Document) -> tuple[Node, ...]:
        nodes = []
        for value in document.header.get("decisions", []):
            reference = ObjectRef.parse(value)
            target = (
                by_id.get(reference.object_id) if reference.project in {None, project} else None
            )
            if target is not None:
                shown.add(str(target.object_id))
                nodes.append(_decision(target))
            else:
                nodes.append(Node(str(value), ("not found here",), ""))
        return tuple(nodes)

    for doc in sorted(objects, key=lambda doc: (doc.object_id.kind.value, doc.object_id.number)):
        kind = doc.object_id.kind
        if kind not in {ObjectKind.EVIDENCE, ObjectKind.OBJECTION, ObjectKind.SPEC}:
            continue
        reference = ObjectRef.parse(doc.header["target"])
        if reference.project not in {None, project}:
            elsewhere.append(f"{doc.object_id} -> {doc.header['target']}")
            continue
        chain = current_claim(objects, reference.object_id)
        owner = chain[-1]
        if owner not in children:
            elsewhere.append(f"{doc.object_id} -> {doc.header['target']} (not found)")
            continue
        moved = (f"on {reference.object_id}",) if owner != reference.object_id else ()
        h = doc.header
        facts: tuple[str, ...]
        if kind == ObjectKind.EVIDENCE:
            facts = (h["direction"], h["kind"], h["grade"])
            if h["status"] == "invalidated":
                facts += ("INVALIDATED",)
            node = Node(str(doc.object_id), facts + moved, _text(doc, "Material"))
            rank = 0
        elif kind == ObjectKind.OBJECTION:
            status = "OPEN" if h["status"] == "open" else h["status"]
            facts = (h["severity"], status)
            source = h["source"]
            if source.get("kind") == "run":
                run = by_id.get(ObjectRef.parse(source["ref"]).object_id)
                origin = f"<- {source['ref']}"
                if run is not None:
                    origin += f" {run.header['model']}/{run.header['role']}"
                facts += (origin,)
            node = Node(str(doc.object_id), facts + moved, _text(doc, "Content"), decisions_of(doc))
            rank = 1 + (0 if h["status"] == "open" else 3) + SEVERITY_ORDER.get(h["severity"], 3)
        else:
            task_nodes = tuple(
                Node(
                    "Chief task " + (build.task_id or ""),
                    (),
                    build_line(build).removeprefix(
                        f"{build.spec} -> Chief task {build.task_id}"
                        + (" " if build.task and build.task.other_host is not None else ": ")
                    ),
                )
                for build in builds
                if build.spec == str(doc.object_id) and build.task_id is not None
            )
            node = Node(
                str(doc.object_id),
                ("spec", h["status"]) + moved,
                _text(doc, "Requirements"),
                task_nodes,
            )
            rank = 10
        children[owner].append((rank, node))

    def order(doc: Document) -> tuple[int, int, int]:
        importance = 0 if doc.header.get("importance") == "core" else 1
        kind = doc.header.get("type")
        position = TYPE_ORDER.index(kind) if kind in TYPE_ORDER else len(TYPE_ORDER)
        return importance, position, doc.object_id.number

    nodes = []
    for doc in sorted(current, key=order):
        h = doc.header
        facts = (str(h.get("type")), str(h.get("importance")), h["status"])
        statement = _text(doc, "Statement")
        plan = str(h.get("validation_plan") or "").strip()
        below = tuple(node for _, node in sorted(children[doc.object_id], key=lambda x: x[0]))
        if plan:
            below += (Node("plan", (), " ".join(plan.split())),)
        nodes.append(Node(str(doc.object_id), facts, statement, below + decisions_of(doc)))
    loose = tuple(
        _decision(doc)
        for doc in sorted(objects, key=lambda doc: doc.object_id.number)
        if doc.object_id.kind == ObjectKind.DECISION and str(doc.object_id) not in shown
    )
    return tuple(nodes), chains, loose, tuple(elsewhere)
