"""L2 condition assessment; never a state transition or gate ruling."""

import re
from dataclasses import dataclass
from pathlib import Path

from toulmin.core.documents import Document, sections
from toulmin.core.identifiers import ObjectId, ObjectKind, ObjectRef
from toulmin.core.inspection import ProjectSnapshot, current_claim, inspect_project, local_target
from toulmin.core.project import STAGES
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
    stage_warnings: tuple[str, ...] = ()  # R5: gates behind the stage that do not hold


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
        supports = _verified_support(evidence, project, claim.object_id)
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
    gates = _gates(Repository(root), project, snapshot, complete)
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
        gates,
        stage_warnings(charter.get("stage"), gates),
    )


def _verified_support(evidence: list[Document], project: str, claim: ObjectId) -> int:
    return sum(
        local_target(doc, project) == claim
        and doc.header["status"] == "valid"
        and doc.header["grade"] == "verified"
        and doc.header["direction"] == "supports"
        for doc in evidence
    )


def awaiting_support_ruling(snapshot: ProjectSnapshot, project: str) -> tuple[ObjectId, ...]:
    """Current Claims that meet the supported conditions but are not ruled supported yet.

    The same rule as the "meets supported conditions" notice: valid verified supporting
    Evidence and no open fatal or major Objection. Used for advice only (R5 follow-up).
    """
    evidence = [doc for doc in snapshot.objects if doc.object_id.kind == ObjectKind.EVIDENCE]
    blocking = {
        local_target(doc, project)
        for doc in snapshot.objects
        if doc.object_id.kind == ObjectKind.OBJECTION
        and doc.header["status"] == "open"
        and doc.header["severity"] in {"fatal", "major"}
    }
    return tuple(
        doc.object_id
        for doc in sorted(snapshot.objects, key=lambda doc: doc.object_id.number)
        if doc.object_id.kind == ObjectKind.CLAIM
        and doc.header["status"] in {"proposed", "challenged"}
        and doc.object_id not in blocking
        and _verified_support(evidence, project, doc.object_id) > 0
    )


G1_TYPES = ("problem", "magnitude", "mechanism", "novelty")
G1_LABELS = {
    "problem": "the problem exists",
    "magnitude": "the problem's size",
    "mechanism": "the approach works",
    "novelty": "novelty",
}
KILL_CRITERIA = "Kill criteria"
NO_BLOCKING = "no open fatal or major Objection"


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
    """G1-G5 conditions of design section 7, computed from files only.

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
    # R5: a deferred fatal or major Objection is not open, so G2 can hold, but it still
    # matters later; the item says so instead of turning silently green.
    deferred = sorted(
        (
            doc
            for doc in snapshot.objects
            if doc.object_id.kind == ObjectKind.OBJECTION
            and doc.header["status"] == "deferred"
            and doc.header["severity"] in {"fatal", "major"}
        ),
        key=lambda doc: doc.object_id.number,
    )
    detail = ", ".join(f"{doc.object_id} ({doc.header['severity']})" for doc in blocking)
    if deferred:
        listed = ", ".join(f"{doc.object_id} ({doc.header['severity']})" for doc in deferred)
        advice = f"advice: deferred, not resolved: {listed}; revisit before build"
        detail = f"{detail}; {advice}" if detail else advice
    g2 = [GateItem(NO_BLOCKING, not blocking, detail)]
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

    g3, g4, g5 = _spec_gates(snapshot, project)
    return (
        readiness("G1", "critique", g1),
        readiness("G2", "brief-final", g2),
        readiness("G3", "build", g3),
        readiness("G4", "accept", g4),
        readiness("G5", "done", g5),
    )


EXECUTABLE = re.compile(r"`[^`\n]+`|^ {0,3}(`{3,}|~{3,})", re.M)
VERIFIER = "verifier"


def _spec_gates(
    snapshot: ProjectSnapshot, project: str
) -> tuple[list[GateItem], list[GateItem], list[GateItem]]:
    """G3-G5 of design section 7 from Specs, their listed Evidence and its Runs (R5).

    G3: every Spec targets a Claim that is current or has a current successor, and its
    Acceptance criteria name something runnable (heuristic: inline code or a code block).
    G4: every Spec reports completion (awaiting-acceptance or passed) and lists valid
    supporting Evidence, the implementer's own test report. G5: every Spec has passed and lists
    verified supporting Evidence on its Claim whose source Run has the role ``verifier``; a
    researcher who ran the checks independently archives that Run by hand.
    """
    known = {doc.object_id: doc for doc in snapshot.objects}
    specs = sorted(
        (doc for doc in snapshot.objects if doc.object_id.kind == ObjectKind.SPEC),
        key=lambda doc: doc.object_id.number,
    )
    if not specs:
        missing = [GateItem("at least one Spec", False, "no Specs")]
        return missing, list(missing), list(missing)
    g3: list[GateItem] = []
    g4: list[GateItem] = []
    g5: list[GateItem] = []
    for spec in specs:
        name = str(spec.object_id)
        target = local_target(spec, project)
        claims: tuple[ObjectId, ...] = ()
        if target is None:
            mapped, where = False, f"targets {spec.header['target']} outside this project"
        elif target not in known:
            mapped, where = False, f"targets {target}, which does not exist"
        else:
            claims = current_claim(snapshot.objects, target)
            current = known.get(claims[-1])
            if current is None or current.header["status"] in {"superseded", "refuted"}:
                mapped, where = False, f"targets {target}, which is no longer current"
            elif len(claims) > 1:
                mapped, where = True, f"{target} via its successor {claims[-1]}"
            else:
                mapped, where = True, str(target)
        criteria = sections(spec).get("Acceptance criteria", "")
        runnable = bool(EXECUTABLE.search(criteria))
        problems = [] if mapped else [where]
        if not runnable:
            problems.append("Acceptance criteria name no command in backticks or a code block")
        g3.append(
            GateItem(
                f"{name} maps to a Claim with executable acceptance",
                mapped and runnable,
                "; ".join(problems) if problems else where,
            )
        )
        listed = []
        for value in spec.header.get("evidence") or []:
            reference = ObjectRef.parse(value)
            found = known.get(reference.object_id) if reference.project in {None, project} else None
            if found is not None and found.object_id.kind == ObjectKind.EVIDENCE:
                listed.append(found)
        usable = [
            doc
            for doc in listed
            if doc.header["status"] == "valid" and doc.header["direction"] == "supports"
        ]
        status = spec.header["status"]
        if status not in {"awaiting-acceptance", "passed"}:
            reported, detail = False, f"status {status}"
        elif not usable:
            reported, detail = False, f"status {status}; no valid supporting Evidence listed"
        else:
            reported = True
            detail = f"status {status}; " + ", ".join(str(doc.object_id) for doc in usable)
        g4.append(GateItem(f"{name} completion reported with test Evidence", reported, detail))
        verified = [
            doc
            for doc in usable
            if doc.header["grade"] == "verified"
            and local_target(doc, project) in claims
            and _verifier_run(doc, known)
        ]
        if status != "passed":
            accepted, detail = False, f"status {status}, not passed"
        elif not verified:
            accepted = False
            detail = (
                "no verified supporting Evidence on its Claim from a Run with role "
                f"{VERIFIER}: archive an independent check as such a Run, then take its Evidence"
            )
        else:
            accepted, detail = True, ", ".join(str(doc.object_id) for doc in verified)
        g5.append(GateItem(f"{name} passed on a verifier's independent run", accepted, detail))
    return g3, g4, g5


def _verifier_run(evidence: Document, known: dict[ObjectId, Document]) -> bool:
    source = evidence.header["source"]
    if not isinstance(source, dict) or source.get("kind") != "run":
        return False
    run = known.get(ObjectRef.parse(source["ref"]).object_id)
    return run is not None and str(run.header.get("role", "")) == VERIFIER


def upcoming(stage: str | None, gate: GateReadiness) -> bool:
    """Whether a gate concerns the project now: G1/G2 always (as before R5), a later gate once
    it is behind the stage or the next one."""
    if stage not in STAGES or gate.enters not in STAGES:
        return True
    reach = max(STAGES.index(stage) + 1, STAGES.index("brief-final"))
    return STAGES.index(gate.enters) <= reach


def unheld(stage: str | None, gates: tuple[GateReadiness, ...]) -> tuple[GateReadiness, ...]:
    """Gates the recorded stage has passed that do not hold in the files (R5)."""
    if stage not in STAGES:
        return ()
    reached = STAGES.index(stage)
    return tuple(
        gate
        for gate in gates
        if gate.met is False and gate.enters in STAGES and STAGES.index(gate.enters) <= reached
    )


def stage_warnings(stage: str | None, gates: tuple[GateReadiness, ...]) -> tuple[str, ...]:
    """One warning per unheld gate; advice only.

    The stage is the researcher's record and never changes here; design section 7 leaves
    sending a project back to the researcher's ruling.
    """
    return tuple(
        f"Stage {stage} is past {gate.gate} (enters {gate.enters}), which does not hold in the "
        f"files: {'; '.join(item.label for item in gate.items if not item.met)}. The stage "
        "stays as recorded; the researcher rules whether to keep it or return the project."
        for gate in unheld(stage, gates)
    )


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
