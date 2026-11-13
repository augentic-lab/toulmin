"""L1: prefilled draft skeletons for the proposal kinds `toulmin decide` offers (R1).

Pure text from data the caller has already read: current statuses, the brief's digest and
sections, the stage, review draft labels. Every value the agent must still choose is a
``<fill: ...>`` placeholder, which decide refuses, so an unedited skeleton can never be applied.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from toulmin.core.skeletons import PLACEHOLDER

DECISION_HINT = "D-NNN, or the decision-…md proposal beside this one"


def _q(value: str) -> str:
    """A double-quoted YAML scalar (JSON strings are valid YAML)."""
    return json.dumps(value, ensure_ascii=False)


def _fill(hint: str) -> str:
    return _q(f"{PLACEHOLDER} {hint}>")


def _section(name: str, hint: str) -> str:
    return f"## {name}\n{PLACEHOLDER} {hint}>\n"


def _one_line(text: str, limit: int = 110) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _head(kind: str, project: str, path: str, notes: Sequence[str]) -> list[str]:
    return [
        "---",
        f"# {kind} proposal draft for project {project} ({path}).",
        "# Replace every <fill ...> marker; delete optional lines and sections you do not use.",
        *notes,
        f"# When complete, move this file (name unchanged) to projects/{project}/runs/proposals/",
        "# for the researcher's `toulmin decide`. Nothing is applied until they apply it.",
        "schema_version: 1",
    ]


@dataclass(frozen=True)
class RulingTarget:
    object_id: str
    status: str  # the object's current status


def ruling_skeleton(
    project: str,
    path: str,
    targets: Sequence[RulingTarget],
    statuses: Sequence[str],
    sections: Sequence[str],
    links: Sequence[str] = (),
    status: str | None = None,
    decision: str | None = None,
) -> str:
    """One ruling for one object, or the same ruling for several objects of one kind."""
    if not targets:
        raise ValueError("object: name at least one object")
    current = ", ".join(f"{item.object_id} {item.status}" for item in targets)
    notes = [
        "# One proposal may give a status, section text and a link together (e.g. a Response",
        "# and status answered); a status or link needs an active Decision whose related",
        "# names every ruled object.",
    ]
    lines = _head("Ruling", project, path, notes)
    lines.append("kind: ruling-proposal")
    if len(targets) == 1:
        lines.append(f"object: {targets[0].object_id}  # current status: {targets[0].status}")
    else:
        lines.append(f"objects: [{', '.join(item.object_id for item in targets)}]")
        lines.append(f"# current: {current}")
    choices = [value for value in statuses if all(value != item.status for item in targets)]
    if status is not None:
        lines.append(f"status: {status}")
    else:
        lines.append(f"status: {_fill(' | '.join(choices))}  # or delete to add text only")
    if decision is not None:
        lines.append(f"decision: {_q(decision)}")
    else:
        lines.append(f"decision: {_fill(DECISION_HINT)}  # delete only with no status/link")
    if links and len(targets) == 1:
        lines.append(f"# links: {{{links[0]}: <ID>}}  # only when the new status requires it")
    lines.append("---")
    body = [_section("Why", "why the researcher should rule this way; shown, never written")]
    body += [_section(name, f"text to add to {name}, or delete this section") for name in sections]
    return "\n".join(lines) + "\n" + "\n".join(body)


@dataclass(frozen=True)
class DraftLine:
    label: str
    target: str
    severity: str
    content: str


def intake_skeleton(project: str, path: str, output: str, drafts: Sequence[DraftLine]) -> str:
    """One recommendation per review draft label still without an intake outcome."""
    if not drafts:
        raise ValueError(f"{output}: every draft already has an intake outcome")
    notes = [
        "# outcome take creates the Objection (optionally with another severity: fatal,",
        "# major or minor); reject records the reason; partly needs object: O-NNN, an",
        "# Objection already written by hand from the draft. Read the drafts in the output.",
        "# duplicate needs object: O-NNN for an existing Objection this draft repeats.",
    ]
    lines = _head("Intake", project, path, notes)
    lines += ["kind: intake-recommendation", f"output: {_q(output)}", "recommendations:"]
    for draft in drafts:
        lines += [
            f"  # {draft.label} -> {draft.target}, {draft.severity}: {_one_line(draft.content)}",
            f"  - label: {_q(draft.label)}",
            f"    outcome: {_fill('take | partly | reject | duplicate')}",
            f"    reason: {_fill('your grounds; for reject, the reason to record')}",
        ]
    lines.append("---")
    return "\n".join(lines) + "\n" + _section("Notes", "a summary for the researcher, optional")


def review_skeleton(
    project: str,
    path: str,
    personas: Sequence[str] | None = None,
    models: Sequence[str] | None = None,
    claims: Sequence[str] | None = None,
) -> str:
    notes = ["# Leave personas/models/claims out for the defaults (every current Claim)."]
    lines = _head("Review request", project, path, notes)
    lines.append("kind: review-request")
    for field, values in (("personas", personas), ("models", models), ("claims", claims)):
        if values:
            lines.append(f"{field}: [{', '.join(values)}]")
    lines.append("---")
    return "\n".join(lines) + "\n" + _section("Why now", "why this round is needed now")


def brief_skeleton(project: str, path: str, base_sha256: str, sections: dict[str, str]) -> str:
    """Replacement text for named brief sections, starting from their current text."""
    if not sections:
        raise ValueError("section: name at least one brief.md section")
    notes = [
        "# base_sha256 is brief.md as drafted; a changed brief makes this proposal stale.",
        "# Edit the sections below (each replaces the whole section); never leave one empty.",
    ]
    lines = _head("Brief", project, path, notes)
    lines += ["kind: brief-proposal", f"base_sha256: {_q(base_sha256)}", "---"]
    body = [_section("Why", "what changes and why; shown to the researcher, never written")]
    body += [f"## {name}\n{text.strip()}\n" for name, text in sections.items()]
    return "\n".join(lines) + "\n" + "\n".join(body)


def stage_skeleton(
    project: str, path: str, current: str, stage: str, decision: str | None = None
) -> str:
    notes = ["# The stage changes only when the researcher applies this, backed by the Decision."]
    lines = _head("Stage", project, path, notes)
    lines += ["kind: stage-proposal", f"from: {current}", f"to: {stage}"]
    lines.append(f"decision: {_q(decision) if decision else _fill(DECISION_HINT)}")
    lines.append("---")
    return "\n".join(lines) + "\n" + _section("Why", "which gate conditions hold, and why now")


def build_skeleton(
    project: str,
    path: str,
    spec: str,
    repo: str | None,
    checks: Sequence[str],
    tool: str = "codex",
    budget: dict[str, int | float] | None = None,
    trust: bool = False,
    note: str | None = None,
) -> str:
    lines = _head(
        "Build request",
        project,
        path,
        [
            "# The researcher's apply freezes checks and starts Chief; never run chief yourself.",
        ],
    )
    lines += [
        "kind: build-request",
        f"spec: {spec}",
        f"repo: {_q(repo) if repo else _fill('absolute path to the code git repository')}",
        f"task_id: {project}-{spec.replace('-', '').lower()}",
        f"tool: {_q(tool)}",
        f"trust: {'true' if trust else 'false'}",
        "# Optional: command: NAME launches the worker through a wrapper on PATH",
        "# (e.g. a model router), only when the researcher asks for it.",
        "# New machines: set [repos] in tools/chief.local.toml to prefill the repository.",
        "# If interpreter/tool versions matter, add a check that asserts them, e.g.:",
        "# python3 -c 'import sys; print(sys.version); assert sys.version_info[:2] >= (3, 7)'",
        "# Its output is kept in the verify record.",
        *([f"# {line}" for line in note.splitlines()] if note is not None else []),
        "checks: "
        + json.dumps(
            list(checks) or [f"{PLACEHOLDER} executable acceptance command>"], ensure_ascii=False
        ),
        "protected: [tests]",
        "test_first: true",
        "budget: " + json.dumps(budget or {"rounds": 15, "hours": 4}),
        "---",
    ]
    return (
        "\n".join(lines)
        + "\n"
        + _section("Why", "why this Spec is ready to build now")
        + "\n## Context for the implementer\n"
    )
