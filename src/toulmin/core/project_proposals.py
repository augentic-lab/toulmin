"""L1: project proposals awaiting the researcher's decision (H3).

An agent puts each item it considers ready under ``projects/NAME/runs/proposals/``: an object
draft (``claim-…``, ``evidence-…`` and so on, in the ordinary draft format), a ruling
proposal (``ruling-…``), and since H4 an intake recommendation (``intake-…``) or a review-round
request (``review-…``), and since H5 a Brief proposal (``brief-…``) or a stage proposal
(``stage-…``). The researcher's decision is recorded beside it as an outcome
record (``<stem>.outcome.md``); proposals are never edited, moved or deleted. Pure models and
validation only: no file access here.
"""

import re
from dataclasses import dataclass
from typing import Any

from toulmin.core.documents import Document, sections, validate_values
from toulmin.core.identifiers import ObjectKind
from toulmin.core.project import STAGES
from toulmin.core.render import header
from toulmin.core.schema import SEVERITIES, mapping, text, timestamp

PROPOSALS = "runs/proposals"
OUTCOME_SUFFIX = ".outcome.md"
OBJECT_KINDS = {
    kind.value: kind
    for kind in (
        ObjectKind.CLAIM,
        ObjectKind.EVIDENCE,
        ObjectKind.OBJECTION,
        ObjectKind.DECISION,
        ObjectKind.EXPLORATION,
        ObjectKind.SPEC,
    )
}
RULING = "ruling"
INTAKE = "intake"  # H4
REVIEW = "review"  # H4
BRIEF = "brief"  # H5
STAGE = "stage"  # H5
FILENAME = re.compile(
    rf"({'|'.join([*OBJECT_KINDS, RULING, INTAKE, REVIEW, BRIEF, STAGE])})-[0-9]{{8}}T[0-9]{{6}}Z"
    r"(?:-[A-Za-z0-9][A-Za-z0-9_-]{0,63})?\.md"
)
RULING_FIELDS = {"schema_version", "kind", "object", "status", "decision", "links"}
RULING_SECTIONS = {"Response", "Ruling", "Invalidation", "Rationale"}
REVIEW_FIELDS = {"schema_version", "kind", "personas", "models", "claims"}
INTAKE_FIELDS = {"schema_version", "kind", "output", "recommendations"}
INTAKE_OUTCOMES = ("take", "reject", "partly")
OUTCOME_ORDER = (
    "schema_version",
    "kind",
    "proposal",
    "proposal_sha256",
    "disposition",
    "actor",
    "at",
    "approval_text",
    "reason",
    "result",
)
DISPOSITIONS = ("applying", "applied", "rejected")
SHA256 = re.compile(r"[0-9a-f]{64}")
OUTCOME_BODY = (
    "## Meaning\n"
    "The researcher's decision on this proposal. `applying` means application started and must\n"
    "be finished or checked before the proposal is decided again.\n"
)


def proposal_kind(filename: str) -> str | None:
    """``claim`` … ``spec`` or ``ruling`` for a proposal filename; None for anything else."""
    match = FILENAME.fullmatch(filename)
    return match[1] if match else None


@dataclass(frozen=True)
class RulingProposal:
    object: str
    status: str | None
    decision: str | None  # D-NNN, or a decision proposal in the same directory
    links: dict[str, str | list[str]]
    texts: dict[str, str]  # body sections to add to the object
    why: str  # shown to the researcher; never written to the object


def validate_ruling_proposal(document: Document) -> RulingProposal:
    validate_values(document)
    h = mapping(document, document.header, "", {"schema_version", "kind", "object"},
                RULING_FIELDS - {"schema_version", "kind", "object"})  # fmt: skip
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    if h["kind"] != "ruling-proposal":
        document.fail("kind", "expected ruling-proposal")
    target = text(document, h["object"], "object")
    status = h.get("status")
    if status is not None:
        text(document, status, "status")
    decision = h.get("decision")
    if decision is not None:
        text(document, decision, "decision")
    links: dict[str, str | list[str]] = {}
    raw = h.get("links", {})
    if not isinstance(raw, dict):
        document.fail("links", "expected mapping")
    for key, value in raw.items():
        if isinstance(value, list):
            links[key] = [text(document, item, f"links.{key}[{i}]") for i, item in enumerate(value)]
        else:
            links[key] = text(document, value, f"links.{key}")
    body = sections(document)
    unknown = sorted(set(body) - RULING_SECTIONS - {"Why"})
    if unknown:
        document.fail(f"body.{unknown[0]}", f"expected Why plus any of {sorted(RULING_SECTIONS)}")
    why = body.get("Why", "").strip()
    if not why:
        document.fail("body.Why", "explain the proposed ruling for the researcher")
    texts = {name: body[name] for name in sorted(RULING_SECTIONS) if body.get(name, "").strip()}
    if status is None and not texts and not links:
        document.fail("status", "nothing to rule: give status, a section text or a link")
    return RulingProposal(target, status, decision, links, texts, why)


@dataclass(frozen=True)
class Outcome:
    proposal: str
    proposal_sha256: str
    disposition: str
    actor: str
    at: str
    approval_text: str | None
    reason: str | None
    result: str | None  # the created object, or the ruled object, once applied


def render_outcome(outcome: Outcome) -> bytes:
    fields: list[tuple[str, Any]] = [
        ("schema_version", 1),
        ("kind", "proposal-outcome"),
        ("proposal", outcome.proposal),
        ("proposal_sha256", outcome.proposal_sha256),
        ("disposition", outcome.disposition),
        ("actor", outcome.actor),
        ("at", outcome.at),
        ("approval_text", outcome.approval_text),
        ("reason", outcome.reason),
        ("result", outcome.result),
    ]
    return (header(fields) + OUTCOME_BODY).encode()


def validate_outcome(document: Document) -> Outcome:
    validate_values(document)
    h = mapping(document, document.header, "", set(OUTCOME_ORDER))
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    if h["kind"] != "proposal-outcome":
        document.fail("kind", "expected proposal-outcome")
    proposal = text(document, h["proposal"], "proposal")
    if not isinstance(h["proposal_sha256"], str) or not SHA256.fullmatch(h["proposal_sha256"]):
        document.fail("proposal_sha256", "expected 64 lowercase hex digits")
    if h["disposition"] not in DISPOSITIONS:
        document.fail("disposition", f"expected one of {', '.join(DISPOSITIONS)}")
    actor = text(document, h["actor"], "actor")
    timestamp(document, h["at"], "at")
    approval = h["approval_text"]
    if approval is not None:
        text(document, approval, "approval_text")
    reason = h["reason"]
    if h["disposition"] == "rejected":
        text(document, reason, "reason")
    elif reason is not None:
        document.fail("reason", "only a rejection has a reason")
    result = h["result"]
    if h["disposition"] == "applied":
        text(document, result, "result")
    elif result is not None:
        document.fail("result", "only an applied proposal has a result")
    return Outcome(
        proposal, h["proposal_sha256"], h["disposition"], actor, h["at"], approval, reason, result
    )


def _version(document: Document, h: dict[str, Any], kind: str) -> None:
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    if h["kind"] != kind:
        document.fail("kind", f"expected {kind}")


def _names(document: Document, value: Any, field: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        document.fail(field, "expected a nonempty list, or leave the field out")
    names = [text(document, item, f"{field}[{i}]") for i, item in enumerate(value)]
    if len(set(names)) != len(names):
        document.fail(field, "duplicate entry")
    return names


@dataclass(frozen=True)
class ReviewRequest:
    """A review round the agent asks for; only the researcher's apply starts it (D3)."""

    personas: list[str] | None  # None: the defaults in tools/models.toml
    models: list[str] | None
    claims: list[str] | None  # None: every current Claim the persona's manifest gives
    why: str  # "## Why now", shown to the researcher


def validate_review_request(document: Document) -> ReviewRequest:
    validate_values(document)
    h = mapping(document, document.header, "", {"schema_version", "kind"},
                REVIEW_FIELDS - {"schema_version", "kind"})  # fmt: skip
    _version(document, h, "review-request")
    personas = _names(document, h.get("personas"), "personas")
    models = _names(document, h.get("models"), "models")
    claims = _names(document, h.get("claims"), "claims")
    why = sections(document).get("Why now", "").strip()
    if not why:
        document.fail("body.Why now", "explain why this round is needed now")
    return ReviewRequest(personas, models, claims, why)


@dataclass(frozen=True)
class Recommendation:
    label: str
    outcome: str  # take, reject or partly
    severity: str | None  # take only: a severity other than the reviewer's
    reason: str  # the agent's grounds; for reject, the proposed recorded reason
    object: str | None  # partly only: the Objection written by hand from this draft


@dataclass(frozen=True)
class IntakeRecommendation:
    """The agent's recommendation for every draft label of one raw review output."""

    output: str  # root-relative raw review output
    items: tuple[Recommendation, ...]


def validate_intake_recommendation(document: Document) -> IntakeRecommendation:
    validate_values(document)
    h = mapping(document, document.header, "", INTAKE_FIELDS)
    _version(document, h, "intake-recommendation")
    output = text(document, h["output"], "output")
    raw = h["recommendations"]
    if not isinstance(raw, list) or not raw:
        document.fail("recommendations", "expected a nonempty list")
    items: list[Recommendation] = []
    for index, value in enumerate(raw):
        field = f"recommendations[{index}]"
        entry = mapping(document, value, field, {"label", "outcome", "reason"},
                        {"severity", "object"})  # fmt: skip
        label = text(document, entry["label"], f"{field}.label")
        outcome = entry["outcome"]
        if outcome not in INTAKE_OUTCOMES:
            document.fail(f"{field}.outcome", f"expected one of {', '.join(INTAKE_OUTCOMES)}")
        reason = text(document, entry["reason"], f"{field}.reason")
        severity = entry.get("severity")
        if severity is not None and (outcome != "take" or severity not in SEVERITIES):
            document.fail(f"{field}.severity", "only take may set fatal, major or minor")
        target = entry.get("object")
        if (target is not None) != (outcome == "partly"):
            document.fail(f"{field}.object", "partly names the Objection written by hand")
        if target is not None:
            text(document, target, f"{field}.object")
        if any(item.label == label for item in items):
            document.fail(f"{field}.label", f"{label} recommended twice")
        items.append(Recommendation(label, outcome, severity, reason, target))
    return IntakeRecommendation(output, tuple(items))


@dataclass(frozen=True)
class BriefProposal:
    """Replacement text for named brief.md sections, drafted against one brief version."""

    base_sha256: str  # sha256 of brief.md when the proposal was drafted
    sections: dict[str, str]  # brief section name -> replacement text, in proposal order
    why: str  # "## Why", shown to the researcher, never written to the brief


def validate_brief_proposal(document: Document) -> BriefProposal:
    validate_values(document)
    h = mapping(document, document.header, "", {"schema_version", "kind", "base_sha256"})
    _version(document, h, "brief-proposal")
    if not isinstance(h["base_sha256"], str) or not SHA256.fullmatch(h["base_sha256"]):
        document.fail("base_sha256", "expected the quoted sha256 of brief.md when drafted (64 hex)")
    body = sections(document)
    why = body.pop("Why", "").strip()
    if not why:
        document.fail("body.Why", "explain the change for the researcher")
    replacements = {name: text for name, text in body.items() if text.strip()}
    if not replacements:
        document.fail("body", "give at least one brief section after ## Why")
    empty = sorted(set(body) - set(replacements))
    if empty:
        document.fail(f"body.{empty[0]}", "empty replacement; a proposal never empties a section")
    return BriefProposal(h["base_sha256"], replacements, why)


@dataclass(frozen=True)
class StageProposal:
    """A stage change for the researcher's ruling, backed by a Decision (D4)."""

    current: str  # the stage the proposal was drafted at ("from")
    stage: str  # the proposed stage ("to")
    decision: str  # D-NNN, or a decision proposal in the same directory
    why: str


def validate_stage_proposal(document: Document) -> StageProposal:
    validate_values(document)
    h = mapping(document, document.header, "", {"schema_version", "kind", "from", "to", "decision"})
    _version(document, h, "stage-proposal")
    for field in ("from", "to"):
        if h[field] not in STAGES:
            document.fail(field, f"expected one of {', '.join(STAGES)}")
    if h["from"] == h["to"]:
        document.fail("to", "expected a stage other than from")
    decision = text(document, h["decision"], "decision")
    why = sections(document).get("Why", "").strip()
    if not why:
        document.fail("body.Why", "explain the stage change for the researcher")
    return StageProposal(h["from"], h["to"], decision, why)
