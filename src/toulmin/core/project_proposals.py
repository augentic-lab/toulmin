"""L1: project proposals awaiting the researcher's decision (H3).

An agent puts each item it considers ready under ``projects/NAME/runs/proposals/``: an object
draft (``claim-…``, ``evidence-…`` and so on, in the ordinary draft format) or a ruling
proposal (``ruling-…``). The researcher's decision is recorded beside it as an outcome
record (``<stem>.outcome.md``); proposals are never edited, moved or deleted. Pure models and
validation only: no file access here.
"""

import re
from dataclasses import dataclass
from typing import Any

from toulmin.core.documents import Document, sections, validate_values
from toulmin.core.identifiers import ObjectKind
from toulmin.core.render import header
from toulmin.core.schema import mapping, text, timestamp

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
FILENAME = re.compile(
    rf"({'|'.join([*OBJECT_KINDS, RULING])})-[0-9]{{8}}T[0-9]{{6}}Z"
    r"(?:-[A-Za-z0-9][A-Za-z0-9_-]{0,63})?\.md"
)
RULING_FIELDS = {"schema_version", "kind", "object", "status", "decision", "links"}
RULING_SECTIONS = {"Response", "Ruling", "Invalidation", "Rationale"}
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
