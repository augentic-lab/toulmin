"""L2: the project card (UX3), the first screen of ``toulmin open`` and ``toulmin map``.

Reason for this L2 addition (docs/protocols.md, UX3): the map leads with gates and a full
argument tree, so the researcher could not see what the project currently answers. The card
answers three questions from files only: what does the project currently hold and doubt, what
waits for the researcher, and what can happen next. It is derived on every call (the living
document's display layer, design D1); nothing is stored or changed, and the moves are the same
rule table as the map and the agent's state card.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from toulmin.core.documents import sections
from toulmin.core.identifiers import ObjectKind
from toulmin.core.inspection import current_claim, inspect_project
from toulmin.core.repository import Repository
from toulmin.protocols.build import build_line
from toulmin.protocols.research_map import Move, ResearchMap
from toulmin.protocols.status import project_status, unheld

SEVERITIES = ("fatal", "major", "minor")
HELD = {"supported", "accepted"}
REFERENCE = re.compile(r"\b[A-Z]-[0-9]{3,}\b")


@dataclass(frozen=True)
class AnswerLine:
    claim: str
    state: str  # held, ready, contested, unsupported, refuted or recheck
    stored: str
    statement: str
    verified: int  # valid verified supporting Evidence
    fatal: int  # open fatal Objections aimed at this wording
    major: int  # open major Objections aimed at this wording


@dataclass(frozen=True)
class DoubtGroup:
    target: str  # the Claim wording the Objections were raised against
    current: str | None  # its current successor when that wording was superseded
    counts: tuple[tuple[str, int], ...]  # (severity, open count), most severe first
    first: tuple[str, ...]  # up to three Objection IDs, most severe first
    example: str  # summary of the first


@dataclass(frozen=True)
class ProjectCard:
    project: str
    stage: str | None
    question: str | None
    answer: tuple[AnswerLine, ...]
    doubts: tuple[DoubtGroup, ...]
    moves: tuple[Move, ...]
    recorded_next_step: str | None
    recorded_on: str | None  # YYYY-MM-DD of the handoff that wrote it, when known
    stale_references: tuple[str, ...]  # superseded Claims the recorded step still names
    invalid: bool
    builds: tuple[str, ...] = ()  # Chief tasks started from build requests, with their state
    warnings: tuple[str, ...] = ()  # the stage is past gates that do not hold (R5)


def _state(stored: str, eligible: bool | None, blocking: int, verified: int) -> str:
    if stored == "refuted":
        return "refuted"
    if stored in HELD:
        return "held" if eligible is not False else "recheck"
    if eligible:
        return "ready"
    if blocking:
        return "contested"
    return "unsupported" if not verified else "contested"


def project_card(root: Path, project: str, report: ResearchMap) -> ProjectCard:
    """The card for one project; ``report`` supplies the ordering and the moves."""
    status = project_status(root, project)
    snapshot = inspect_project(Repository(root), project)
    question = None
    if snapshot.charter is not None:
        # The whole first paragraph: status summaries are cut at 100 characters mid-word.
        goal = sections(snapshot.charter).get("Goal", "").strip().split("\n\n", 1)[0]
        question = " ".join(goal.split()) or None

    fatal: dict[str, int] = defaultdict(int)
    major: dict[str, int] = defaultdict(int)
    groups: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for objection in status.open_objections:
        rank = SEVERITIES.index(objection.severity) if objection.severity in SEVERITIES else 3
        groups[objection.target].append((rank, str(objection.object_id), objection.summary))
        if objection.severity == "fatal":
            fatal[objection.target] += 1
        elif objection.severity == "major":
            major[objection.target] += 1

    order = {node.object_id: index for index, node in enumerate(report.claims)}
    answer = []
    for claim in sorted(
        status.claims, key=lambda claim: order.get(str(claim.object_id), len(order))
    ):
        key = str(claim.object_id)
        answer.append(
            AnswerLine(
                key,
                _state(
                    claim.stored_status,
                    claim.eligible_for_supported,
                    fatal[key] + major[key],
                    claim.verified_support_count,
                ),
                claim.stored_status,
                claim.summary,
                claim.verified_support_count,
                fatal[key],
                major[key],
            )
        )

    successors = {
        str(item.object_id): str(item.chain[-1]) for item in status.superseded if item.chain
    }
    doubts = []
    for target, items in groups.items():
        items.sort()
        counts = tuple(
            (severity, sum(rank == index for rank, _, _ in items))
            for index, severity in enumerate(SEVERITIES)
        )
        doubts.append(
            DoubtGroup(
                target,
                successors.get(target),
                tuple(count for count in counts if count[1]),
                tuple(object_id for _, object_id, _ in items[:3]),
                items[0][2],
            )
        )
    # Fatal first, then the most major, then most Objections; ties by Claim ID.
    doubts.sort(
        key=lambda group: (
            -dict(group.counts).get("fatal", 0),
            -dict(group.counts).get("major", 0),
            -sum(count for _, count in group.counts),
            group.target,
        )
    )

    recorded = status.next_step or None
    recorded_on = None
    if status.last_handoff:
        stamp = status.last_handoff.rsplit("/", 1)[-1][:8]
        if stamp.isdigit():
            recorded_on = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}"
    claims = {
        str(doc.object_id): doc
        for doc in snapshot.objects
        if doc.object_id.kind == ObjectKind.CLAIM
    }
    stale = tuple(
        sorted(
            {
                reference
                for reference in REFERENCE.findall(recorded or "")
                if reference in claims
                and claims[reference].header["status"] == "superseded"
                and current_claim(snapshot.objects, claims[reference].object_id)
            }
        )
    )
    return ProjectCard(
        project,
        report.stage,
        question,
        tuple(answer),
        tuple(doubts),
        report.moves,
        recorded,
        recorded_on,
        stale,
        bool(report.errors),
        tuple(build_line(fact) for fact in report.builds if fact.task_id is not None),
        tuple(
            f"Stage {report.stage} is past {gate.gate} (enters {gate.enters}), which does not "
            "hold; you rule whether to keep it"
            for gate in unheld(report.stage, report.gates)
        ),
    )
