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
from toulmin.core.schema import SEVERITIES, mapping, reference, strings, text, timestamp

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
BUILD = "build"  # R8 B2
_PREFIXES = "|".join([*OBJECT_KINDS, RULING, INTAKE, REVIEW, BRIEF, STAGE, BUILD])
FILENAME = re.compile(
    rf"({_PREFIXES})-[0-9]{{8}}T[0-9]{{6}}Z"
    r"(?:-[A-Za-z0-9][A-Za-z0-9_-]{0,63})?\.md"
)
RULING_FIELDS = {"schema_version", "kind", "object", "objects", "status", "decision", "links"}
RULING_SECTIONS = {"Response", "Ruling", "Invalidation", "Rationale"}
REVIEW_FIELDS = {"schema_version", "kind", "personas", "models", "claims"}
INTAKE_FIELDS = {"schema_version", "kind", "output", "recommendations"}
INTAKE_OUTCOMES = ("take", "reject", "partly", "duplicate")
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
DISPOSITIONS = ("applying", "applied", "rejected", "failed")
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
    object: str  # the ruled object; with ``objects``, the first of them
    status: str | None
    decision: str | None  # D-NNN, or a decision proposal in the same directory
    links: dict[str, str | list[str]]
    texts: dict[str, str]  # body sections to add to the object
    why: str  # shown to the researcher; never written to the object
    batch: tuple[str, ...] = ()  # R1: ``objects``, the same ruling for each, in order

    @property
    def targets(self) -> tuple[str, ...]:
        return self.batch or (self.object,)


def validate_ruling_proposal(document: Document) -> RulingProposal:
    validate_values(document)
    h = mapping(document, document.header, "", {"schema_version", "kind"},
                RULING_FIELDS - {"schema_version", "kind"})  # fmt: skip
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    if h["kind"] != "ruling-proposal":
        document.fail("kind", "expected ruling-proposal")
    if ("object" in h) == ("objects" in h):
        document.fail("object", "give object (one ID) or objects (a list of two or more IDs)")
    batch: tuple[str, ...] = ()
    if "objects" in h:
        names = _names(document, h["objects"], "objects")
        assert names is not None
        if len(names) < 2:
            document.fail("objects", "list two or more IDs; use object for one")
        if "links" in h:
            document.fail("links", "links name one object's successor; rule each separately")
        kinds = {name.split("-", 1)[0] for name in names}
        if len(kinds) > 1:
            document.fail("objects", "one ruling covers objects of one kind")
        batch = tuple(names)
        target = batch[0]
    else:
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
    return RulingProposal(target, status, decision, links, texts, why, batch)


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
    if h["disposition"] in {"rejected", "failed"}:
        text(document, reason, "reason")
    elif reason is not None:
        document.fail("reason", "only a rejection or failure has a reason")
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
    outcome: str  # take, reject, partly or duplicate
    severity: str | None  # take only: a severity other than the reviewer's
    reason: str  # the agent's grounds; for reject, the proposed recorded reason
    object: str | None  # partly: hand-written Objection; duplicate: existing Objection


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
        if (target is not None) != (outcome in {"partly", "duplicate"}):
            document.fail(f"{field}.object", "partly or duplicate requires an Objection object")
        if target is not None:
            text(document, target, f"{field}.object")
            if outcome == "duplicate":
                duplicate = reference(document, target, f"{field}.object", ObjectKind.OBJECTION)
                if duplicate.project is not None:
                    document.fail(f"{field}.object", "duplicate names an Objection in this project")
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


@dataclass(frozen=True)
class BuildRequest:
    """An explicit implementation request; tool names are ordinary provenance data."""

    spec: str
    repo: str
    base_branch: str | None
    task_id: str | None
    tool: str
    checks: tuple[str, ...]
    protected: tuple[str, ...]
    test_first: bool
    budget: dict[str, int | float]
    why: str
    context: str
    trust: bool = False
    command: str | None = None  # worker launcher override, e.g. a model-router wrapper


# Chief's rule for a worker launcher: a bare name on PATH, no arguments or paths.
WORKER_COMMAND = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.+-]{0,127}")


def validate_build_request(document: Document) -> BuildRequest:
    validate_values(document)
    required = {"schema_version", "kind", "spec", "repo", "tool", "checks", "test_first", "budget"}
    h = mapping(
        document,
        document.header,
        "",
        required,
        {"base_branch", "task_id", "protected", "trust", "command"},
    )
    _version(document, h, "build-request")
    spec = reference(document, h["spec"], "spec", ObjectKind.SPEC)
    if spec.project is not None:
        document.fail("spec", "expected a local Spec ID")
    repo = text(document, h["repo"], "repo")
    if not repo.startswith("/") or any(ord(c) < 32 for c in repo):
        document.fail("repo", "expected an absolute repository path")
    checks = strings(document, h["checks"], "checks", nonempty=True)
    if any("<fill:" in check for check in checks):
        document.fail("checks", "unfilled <fill: ...> placeholder")
    protected = strings(document, h.get("protected", []), "protected")
    for value in protected:
        if (
            value.startswith("/")
            or "\\" in value
            or any(p in {"", ".", ".."} for p in value.split("/"))
        ):
            document.fail("protected", "expected repository-relative paths without traversal")
    base = h.get("base_branch")
    if base is not None:
        text(document, base, "base_branch")
        if base.startswith("-") or any(ord(c) < 32 for c in base):
            document.fail("base_branch", "expected a branch name, not a flag or control character")
    task = h.get("task_id")
    if task is not None:
        text(document, task, "task_id")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", task):
            document.fail("task_id", "expected a safe task identifier (max 128 characters)")
    tool = text(document, h["tool"], "tool")
    if type(h["test_first"]) is not bool:
        document.fail("test_first", "expected true or false")
    trust = h.get("trust", False)
    if type(trust) is not bool:
        document.fail("trust", "expected true or false")
    command = h.get("command")
    if command is not None:
        text(document, command, "command")
        if not WORKER_COMMAND.fullmatch(command):
            document.fail(
                "command",
                "expected a bare program name on PATH (no spaces, paths or arguments)",
            )
    budget = mapping(document, h["budget"], "budget", {"rounds", "hours"})
    if type(budget["rounds"]) is not int or budget["rounds"] <= 0:
        document.fail("budget.rounds", "expected a positive integer")
    if type(budget["hours"]) not in {int, float} or not 0 < budget["hours"] < float("inf"):
        document.fail("budget.hours", "expected a positive finite number")
    body = sections(document)
    unknown = set(body) - {"Why", "Context for the implementer"}
    if unknown:
        document.fail("body", f"unknown section: {sorted(unknown)[0]}")
    why = body.get("Why", "").strip()
    if not why:
        document.fail("body.Why", "explain why this build is needed")
    return BuildRequest(
        str(spec.object_id),
        repo,
        base,
        task,
        tool,
        tuple(checks),
        tuple(protected),
        h["test_first"],
        dict(budget),
        why,
        body.get("Context for the implementer", ""),
        trust,
        command,
    )
