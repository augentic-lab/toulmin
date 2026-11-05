"""L2 condition assessment; never a state transition or gate ruling."""

import re
from dataclasses import dataclass
from pathlib import Path

from toulmin.core.documents import Document, sections
from toulmin.core.identifiers import ObjectId, ObjectKind, ObjectRef
from toulmin.core.inspection import ProjectSnapshot, current_claim, inspect_project, local_target
from toulmin.core.repository import Repository


@dataclass(frozen=True)
class ClaimStatus:
    object_id: ObjectId
    stored_status: str
    verified_support_count: int
    has_open_objection: bool | None
    eligible_for_supported: bool | None
    summary: str = ""


@dataclass(frozen=True)
class OpenObjection:
    object_id: ObjectId
    target: str
    severity: str
    summary: str = ""


@dataclass(frozen=True)
class SettledObjection:
    object_id: ObjectId
    status: str
    target: str
    decisions: tuple[str, ...]
    summary: str = ""


@dataclass(frozen=True)
class SupersededClaim:
    object_id: ObjectId
    chain: tuple[ObjectId, ...]  # from this Claim to its current successor
    summary: str = ""


@dataclass(frozen=True)
class GateItem:
    label: str
    met: bool
    detail: str


@dataclass(frozen=True)
class GateReadiness:
    """Whether a gate's conditions hold in the files now; never a stage change (H2)."""

    gate: str
    enters: str
    met: bool | None  # None while project data is invalid
    items: tuple[GateItem, ...]


@dataclass(frozen=True)
class StatusReport:
    project: str
    stage: str | None
    next_step: str | None
    claims: tuple[ClaimStatus, ...]
    open_objections: tuple[OpenObjection, ...]
    notices: tuple[str, ...]
    errors: tuple[str, ...]
    last_handoff: str | None = None
    superseded: tuple[SupersededClaim, ...] = ()
    settled_objections: tuple[SettledObjection, ...] = ()
    gates: tuple[GateReadiness, ...] = ()


SUMMARY_LENGTH = 100


def summary(document: Document, section: str) -> str:
    """First paragraph of a body section on one line, shortened for a terminal."""
    paragraph: list[str] = []
    for line in sections(document).get(section, "").splitlines():
        if line.strip():
            paragraph.append(line.strip())
        elif paragraph:
            break
    text = " ".join(paragraph)
    return text if len(text) <= SUMMARY_LENGTH else text[: SUMMARY_LENGTH - 3] + "..."


def project_status(root: Path, project: str) -> StatusReport:
    snapshot = inspect_project(Repository(root), project)
    complete = not snapshot.errors
    claims = []
    notices = []
    evidence = [doc for doc in snapshot.objects if doc.object_id.kind == ObjectKind.EVIDENCE]
    objections = [
        doc
        for doc in snapshot.objects
        if doc.object_id.kind == ObjectKind.OBJECTION and doc.header["status"] == "open"
    ]
    superseded = []
    for claim in sorted(
        (doc for doc in snapshot.objects if doc.object_id.kind == ObjectKind.CLAIM),
        key=lambda doc: doc.object_id.number,
    ):
        if claim.header["status"] == "superseded":
            # Revised wording lives in the successor; conditions apply there.
            superseded.append(
                SupersededClaim(
                    claim.object_id,
                    current_claim(snapshot.objects, claim.object_id),
                    summary(claim, "Statement"),
                )
            )
            continue
        supports = sum(
            local_target(doc, project) == claim.object_id
            and doc.header["status"] == "valid"
            and doc.header["grade"] == "verified"
            and doc.header["direction"] == "supports"
            for doc in evidence
        )
        attacks = [doc for doc in objections if local_target(doc, project) == claim.object_id]
        eligible = supports > 0 and not any(
            doc.header["severity"] in {"fatal", "major"} for doc in attacks
        )
        stored = claim.header["status"]
        claims.append(
            ClaimStatus(
                claim.object_id,
                stored,
                supports,
                bool(attacks) if complete else None,
                eligible if complete else None,
                summary(claim, "Statement"),
            )
        )
        if not complete:
            continue
        if stored in {"supported", "accepted"} and not eligible:
            notices.append(
                f"{claim.object_id}: stored={stored} does not meet supported conditions; "
                "researcher review needed"
            )
        elif eligible and stored not in {"supported", "accepted", "refuted"}:
            notices.append(
                f"{claim.object_id}: meets supported conditions; researcher decision pending"
            )
        if attacks and stored == "proposed":
            notices.append(
                f"{claim.object_id}: open objections meet challenged condition; "
                "researcher review needed"
            )
        elif stored == "challenged" and not attacks:
            notices.append(
                f"{claim.object_id}: challenged but no open objections; researcher review needed"
            )
    if complete:
        notices.extend(_revision_notices(snapshot, project))
        for run, labels in snapshot.pending_drafts:
            notices.append(f"{run}: review drafts pending intake: {', '.join(labels)}")
    settled = tuple(
        SettledObjection(
            doc.object_id,
            doc.header["status"],
            doc.header["target"],
            tuple(doc.header.get("decisions", [])),
            summary(doc, "Content"),
        )
        for doc in sorted(snapshot.objects, key=lambda doc: str(doc.object_id))
        if doc.object_id.kind == ObjectKind.OBJECTION and doc.header["status"] != "open"
    )
    priority = {"fatal": 0, "major": 1, "minor": 2}
    open_objections = tuple(
        OpenObjection(
            doc.object_id,
            doc.header["target"],
            doc.header["severity"],
            summary(doc, "Content"),
        )
        for doc in sorted(
            objections, key=lambda doc: (priority[doc.header["severity"]], doc.object_id.number)
        )
    )
    charter = snapshot.charter.header if snapshot.charter is not None else {}
    return StatusReport(
        project,
        charter.get("stage"),
        charter.get("next_step"),
        tuple(claims),
        open_objections,
        tuple(notices),
        snapshot.errors,
        (
            f"projects/{project}/sessions/{charter['last_handoff']}"
            if charter.get("last_handoff")
            else None
        ),
        tuple(superseded),
        settled,
        _gates(Repository(root), project, snapshot, complete),
    )


G1_TYPES = ("problem", "magnitude", "mechanism", "novelty")
G1_LABELS = {
    "problem": "the problem exists",
    "magnitude": "the problem's size",
    "mechanism": "the approach works",
    "novelty": "novelty",
}
KILL_CRITERIA = "Kill criteria"


def _brief_section(text: str, title: str) -> str:
    """The body of one level-two section of brief.md; fenced code stays opaque."""
    found: list[str] = []
    inside = False
    fence = ""
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = ""
        elif marker:
            fence = marker[1]
        elif re.match(r"^## ", line):
            inside = line[3:].strip() == title
            continue
        if inside:
            found.append(line)
    return "\n".join(found)


def _written(text: str) -> bool:
    """Any line besides blanks and HTML comments counts as written content."""
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return any(line.strip() for line in body.splitlines())


def _gates(
    repository: Repository, project: str, snapshot: ProjectSnapshot, complete: bool
) -> tuple[GateReadiness, ...]:
    """G1/G2 conditions of design section 7, computed from files only.

    Superseded Claims are left out (their successors carry the conditions); a refuted core
    Claim still counts as written for G1 but never satisfies G2.
    """
    claims = sorted(
        (
            doc
            for doc in snapshot.objects
            if doc.object_id.kind == ObjectKind.CLAIM
            and doc.header["status"] != "superseded"
            and doc.header.get("importance") == "core"
        ),
        key=lambda doc: doc.object_id.number,
    )
    g1 = []
    for kind in G1_TYPES:
        ids = [str(doc.object_id) for doc in claims if doc.header.get("type") == kind]
        g1.append(GateItem(f"core {kind} Claim ({G1_LABELS[kind]})", bool(ids), ", ".join(ids)))
    blocking = sorted(
        (
            doc
            for doc in snapshot.objects
            if doc.object_id.kind == ObjectKind.OBJECTION
            and doc.header["status"] == "open"
            and doc.header["severity"] in {"fatal", "major"}
        ),
        key=lambda doc: doc.object_id.number,
    )
    g2 = [
        GateItem(
            "no open fatal or major Objection",
            not blocking,
            ", ".join(f"{doc.object_id} ({doc.header['severity']})" for doc in blocking),
        )
    ]
    if not claims:
        g2.append(GateItem("core Claims supported or planned", False, "no core Claims"))
    for claim in claims:
        supports = [
            str(doc.object_id)
            for doc in snapshot.objects
            if doc.object_id.kind == ObjectKind.EVIDENCE
            and local_target(doc, project) == claim.object_id
            and doc.header["status"] == "valid"
            and doc.header["grade"] == "verified"
            and doc.header["direction"] == "supports"
        ]
        plan = str(claim.header.get("validation_plan") or "").strip()
        if claim.header["status"] == "refuted":
            met, detail = False, "refuted"
        elif supports:
            met, detail = True, "verified support " + ", ".join(supports)
        elif plan:
            met, detail = True, "validation_plan set"
        else:
            met, detail = False, "no verified support and no validation_plan"
        g2.append(GateItem(f"{claim.object_id} supported or planned", met, detail))
    try:
        path = repository.path(f"projects/{project}/brief.md", "file")
        written = _written(_brief_section(path.read_text(encoding="utf-8"), KILL_CRITERIA))
        g2.append(
            GateItem("Kill criteria written in brief.md", written, "" if written else "empty")
        )
    except (OSError, ValueError):
        g2.append(GateItem("Kill criteria written in brief.md", False, "brief.md unreadable"))
        complete = False

    def readiness(gate: str, enters: str, items: list[GateItem]) -> GateReadiness:
        met = all(item.met for item in items) if complete else None
        return GateReadiness(gate, enters, met, tuple(items))

    return (readiness("G1", "critique", g1), readiness("G2", "brief-final", g2))


def _revision_notices(snapshot: ProjectSnapshot, project: str) -> list[str]:
    """Point every dependent of a superseded Claim at its current successor."""
    chains = {
        doc.object_id: current_claim(snapshot.objects, doc.object_id)
        for doc in snapshot.objects
        if doc.object_id.kind == ObjectKind.CLAIM and doc.header["status"] == "superseded"
    }

    def local(value: str) -> ObjectId | None:
        reference = ObjectRef.parse(value)
        return reference.object_id if reference.project in {None, project} else None

    notices = []
    for doc in sorted(snapshot.objects, key=lambda doc: str(doc.object_id)):
        kind, h = doc.object_id.kind, doc.header
        field = "adopted_as" if kind == ObjectKind.EXPLORATION else "target"
        claim = local(h[field]) if field in h else None
        if claim not in chains:
            continue
        current = chains[claim][-1]
        where = f"{doc.object_id}: {field} is superseded {claim} (current: {current})"
        if kind == ObjectKind.OBJECTION and h["status"] == "open":
            notices.append(f"{where}; rule it or raise it against {current}")
        elif kind == ObjectKind.EVIDENCE and h["status"] == "valid":
            notices.append(f"{where}; it does not count for {current}")
        elif kind in {ObjectKind.SPEC, ObjectKind.EXPLORATION}:
            notices.append(f"{where}; researcher review needed")
    for line, value in snapshot.brief_references:
        claim = local(value)
        if claim in chains:
            notices.append(
                f"brief.md:{line}: [[{value}]] is superseded (current: {chains[claim][-1]})"
            )
    return notices
