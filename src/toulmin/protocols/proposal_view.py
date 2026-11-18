"""L2: what one pending proposal changes, in the researcher's words (decide E1–E3, E6).

Reason for this L2 addition (docs/protocols.md, "Readable decide"): decide titled each item
with its file path, cut the main text to one sentence and never showed the object a ruling
answers, so a researcher could not tell what applying changes. The view is derived from the
exact preview decide already holds plus read-only lookups of the objects it names; it writes
nothing, and the full text stays behind ``v``.
"""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from toulmin.core.codec import decode
from toulmin.core.documents import Document, sections
from toulmin.core.inspection import inspect_project
from toulmin.core.repository import Repository
from toulmin.protocols.project_proposals import Preview

MAIN = {
    "claim": "Statement",
    "evidence": "Material",
    "objection": "Content",
    "decision": "Choice",
    "exploration": "Content",
    "spec": "Requirements",
}
NOUN = {
    "claim": "Claim",
    "evidence": "Evidence",
    "objection": "Objection",
    "decision": "Decision",
    "exploration": "Exploration",
    "spec": "Spec",
}


@dataclass(frozen=True)
class Row:
    label: str  # short column label: a section, an object ID, "Effect", "Why"
    text: str  # one paragraph; the view wraps and limits it
    main: bool = False  # the proposal's own content: shown up to several lines


@dataclass(frozen=True)
class ProposalView:
    title: str  # what the proposal is, e.g. "New Claim · core problem"
    rows: tuple[Row, ...]  # context first, then the proposal's content, its effect and why


def paragraph(text: str) -> str:
    """The first paragraph on one line; a leading Markdown heading becomes its lead-in."""
    blocks = [block.strip() for block in text.strip().split("\n\n") if block.strip()]
    if not blocks:
        return ""
    first = " ".join(blocks[0].split())
    if first.startswith("#"):
        lead = first.lstrip("#").strip()
        rest = " ".join(blocks[1].split()) if len(blocks) > 1 else ""
        return f"{lead}: {rest}" if rest else lead
    return first


def _parsed(text: str) -> Document | None:
    try:
        return decode(text.encode())
    except (OSError, ValueError):
        return None


def _value(header: dict[str, Any], key: str) -> str:
    value = header.get(key)
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return "" if value is None else str(value)


def _objects(root: Path, project: str) -> dict[str, Document]:
    try:
        snapshot = inspect_project(Repository(root), project)
    except (OSError, ValueError):
        return {}
    return {str(doc.object_id): doc for doc in snapshot.objects}


def _bare(reference: str) -> str:
    return reference.rsplit("/", 1)[-1]


def _context(objects: dict[str, Document], reference: str) -> Row | None:
    """The object a proposal answers or targets, as the researcher wrote it."""
    doc = objects.get(_bare(reference))
    if doc is None:
        return None
    kind = _bare(reference)[:1]
    body = sections(doc)
    header = doc.header
    if kind == "O":
        facts = [_value(header, "severity"), _value(header, "status")]
        facts.append(f"on {_bare(_value(header, 'target'))}")
        text = paragraph(body.get("Content", ""))
    elif kind == "C":
        facts = [_value(header, "status"), _value(header, "importance"), _value(header, "type")]
        text = paragraph(body.get("Statement", ""))
    elif kind == "E":
        facts = [_value(header, "direction"), _value(header, "grade"), _value(header, "status")]
        text = paragraph(body.get("Material", ""))
    else:
        facts = [_value(header, "status")]
        text = next((paragraph(value) for value in body.values() if value.strip()), "")
    label = " · ".join(fact for fact in facts if fact)
    return Row(f"{_bare(reference)}", f"({label}) {text}" if label else text)


def _object_view(shown: Preview, objects: dict[str, Document]) -> ProposalView:
    noun = NOUN.get(shown.kind, shown.kind.capitalize())
    doc = _parsed(shown.text)
    header = doc.header if doc is not None else {}
    body = sections(doc) if doc is not None else {}
    created = PurePosixPath(shown.target).stem if shown.target else None
    facts: list[str] = []
    rows: list[Row] = []
    if shown.kind == "claim":
        facts = [f"{_value(header, 'importance')} {_value(header, 'type')}".strip()]
    elif shown.kind == "evidence":
        target = _bare(_value(header, "target"))
        facts = [f"{_value(header, 'direction')} {target}".strip()]
        facts.append(", ".join(v for v in (_value(header, "kind"), _value(header, "grade")) if v))
    elif shown.kind == "objection":
        facts = [f"{_value(header, 'severity')} on {_bare(_value(header, 'target'))}"]
    elif shown.kind == "spec":
        facts = [f"for {_bare(_value(header, 'target'))}"]
    elif shown.kind == "exploration":
        facts = [_value(header, "lens")]
    target = _value(header, "target")
    if target:
        context = _context(objects, target)
        if context is not None:
            rows.append(context)
    main = MAIN.get(shown.kind)
    if main and body.get(main):
        rows.append(Row(main, paragraph(body[main]), main=True))
    elif body:
        name, value = next(iter(body.items()))
        rows.append(Row(name, paragraph(value), main=True))
    effect = f"creates {created}" if created else "creates a new object"
    if shown.kind == "decision":
        effect += " (active)"
        related = [_bare(item) for item in header.get("related") or []]
        if related:
            effect += "; relates " + ", ".join(related)
    elif shown.kind == "evidence" and target:
        effect += f"; {_value(header, 'direction') or 'concerns'} {_bare(target)}"
    elif shown.kind in {"claim", "objection", "spec", "exploration"}:
        effect += " (" + ("open" if shown.kind == "objection" else "proposed") + ")"
    rows.append(Row("Effect", effect + "; nothing else changes"))
    why = body.get("Why") or (body.get("Rationale") if shown.kind == "decision" else None)
    if why:
        rows.append(Row("Why" if body.get("Why") else "Rationale", paragraph(why)))
    title = f"New {noun}" + "".join(f" · {fact}" for fact in facts if fact)
    return ProposalView(title, tuple(rows))


def _ruling_view(shown: Preview, objects: dict[str, Document]) -> ProposalView:
    ruling = shown.ruling
    changes = shown.changes or ((shown.change,) if shown.change is not None else ())
    targets = ruling.targets if ruling is not None else tuple(c.object_id for c in changes)
    first = changes[0] if changes else None
    moving = first is not None and first.status != first.previous_status
    names = ", ".join(targets[:3]) + (f" and {len(targets) - 3} more" if len(targets) > 3 else "")
    if moving and first is not None:
        title = f"Ruling · {names}: {first.previous_status} → {first.status}"
    elif first is not None and first.sections == ("Response",):
        title = f"Response to {names}"
    else:
        title = f"Ruling on {names}"
    rows: list[Row] = []
    for target in targets[:3]:
        context = _context(objects, target)
        if context is not None:
            rows.append(context)
    if len(targets) > 3:
        rows.append(Row("", f"… and {len(targets) - 3} more with the same ruling"))
    if ruling is not None:
        for name, text in ruling.texts.items():
            rows.append(Row(name, paragraph(text), main=True))
    effects: list[str] = []
    if first is not None:
        each = " each" if len(changes) > 1 else ""
        if moving:
            effects.append(f"status {first.previous_status} → {first.status}{each}")
        else:
            effects.append(f"status stays {first.previous_status}")
        if first.sections:
            effects.append("adds " + ", ".join(first.sections) + each)
        effects += list(first.links)
        if first.decision:
            effects.append(f"backed by {first.decision}")
    rows.append(Row("Effect", "; ".join(effects) or "no change can be computed"))
    if ruling is not None and ruling.why:
        rows.append(Row("Why", paragraph(ruling.why)))
    return ProposalView(title, tuple(rows))


def proposal_view(root: Path, project: str, shown: Preview) -> ProposalView:
    """The title and rows decide shows for one object draft, ruling, Brief or stage proposal."""
    objects = _objects(root, project)
    if shown.kind == "ruling":
        return _ruling_view(shown, objects)
    if shown.kind == "brief":
        brief = shown.brief
        names = ", ".join(brief.sections) if brief is not None else ""
        rows = (Row("Why", paragraph(brief.why)),) if brief is not None and brief.why else ()
        return ProposalView("Brief update" + (f" · {names}" if names else ""), rows)
    if shown.kind == "stage":
        stage = shown.stage
        if stage is None:
            return ProposalView("Stage ruling", ())
        rows = (Row("Why", paragraph(stage.why)),) if stage.why else ()
        return ProposalView(f"Stage {stage.current} → {stage.stage}", rows)
    return _object_view(shown, objects)


def plain_problem(root: Path, problem: str) -> str:
    """A problem without the workspace's absolute prefix (E6)."""
    return problem.replace(f"{root.resolve()}/", "").replace(f"{root}/", "")
