"""L2 condition assessment; never a state transition or gate ruling."""

from dataclasses import dataclass
from pathlib import Path

from toulmin.core.identifiers import ObjectId, ObjectKind
from toulmin.core.inspection import inspect_project, local_target
from toulmin.core.repository import Repository


@dataclass(frozen=True)
class ClaimStatus:
    object_id: ObjectId
    stored_status: str
    verified_support_count: int
    has_open_objection: bool | None
    eligible_for_supported: bool | None


@dataclass(frozen=True)
class OpenObjection:
    object_id: ObjectId
    target: str
    severity: str


@dataclass(frozen=True)
class StatusReport:
    project: str
    stage: str | None
    next_step: str | None
    claims: tuple[ClaimStatus, ...]
    open_objections: tuple[OpenObjection, ...]
    notices: tuple[str, ...]
    errors: tuple[str, ...]


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
    for claim in sorted(
        (doc for doc in snapshot.objects if doc.object_id.kind == ObjectKind.CLAIM),
        key=lambda doc: doc.object_id.number,
    ):
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
    priority = {"fatal": 0, "major": 1, "minor": 2}
    open_objections = tuple(
        OpenObjection(doc.object_id, doc.header["target"], doc.header["severity"])
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
    )
