"""L1 legacy-workbench adoption plans (contract section 12).

Pure rendering and validation. A plan is deterministic: it contains no time or
absolute path, so its digest identifies exactly what the researcher previewed.
"""

import re
from dataclasses import dataclass
from typing import Any

from toulmin.core.atomic import digest
from toulmin.core.documents import Document, validate_values
from toulmin.core.proposals import unified
from toulmin.core.render import fence, header
from toulmin.core.schema import mapping, text
from toulmin.core.workspace import validate_name

ADOPTION_DIR = re.compile(r"runs/[0-9]{8}T[0-9]{6}Z-adoption-[0-9a-f]{32}")
CONTRACT = "framework/workspace-formats.md"
PLAN_ORDER = ("schema_version", "kind", "name", "creates", "edits", "absent", "conflicts")
WATCHED = ("WORKSPACE.md", "runs", "sessions", "shared/resources", ".aoe/binding.json")
MIN_PREFIX = 16


@dataclass(frozen=True)
class Change:
    """One planned file: created when ``before`` is None, otherwise edited in place."""

    path: str
    before: bytes | None
    after: bytes


@dataclass(frozen=True)
class Conflict:
    path: str
    reason: str


def render_plan(
    name: str,
    changes: tuple[Change, ...],
    absent: tuple[str, ...],
    conflicts: tuple[Conflict, ...],
    projects: tuple[str, ...],
) -> bytes:
    fields: list[tuple[str, Any]] = [
        ("schema_version", 1),
        ("kind", "adoption-plan"),
        ("name", validate_name(name)),
        (
            "creates",
            [{"path": c.path, "sha256": digest(c.after)} for c in changes if c.before is None],
        ),
        (
            "edits",
            [
                {"path": c.path, "before_sha256": digest(c.before), "after_sha256": digest(c.after)}
                for c in changes
                if c.before is not None
            ],
        ),
        ("absent", list(absent)),
        ("conflicts", [{"path": item.path, "reason": item.reason} for item in conflicts]),
    ]
    parts = []
    placeholders = [c.path for c in changes if c.path.endswith("/.gitkeep") and not c.after]
    for change in changes:
        if change.path in placeholders:
            continue
        if change.path == CONTRACT:
            lines = len(change.after.decode().splitlines())
            replaced = (
                ""
                if change.before is None
                else f"; replaces the released copy {digest(change.before)[:16]}…"
            )
            parts.append(
                f"{CONTRACT}: packaged contract copy ({digest(change.after)[:16]}…, {lines} "
                f"lines){replaced}; not shown.\n"
            )
        else:
            parts.append(fence(unified(change.before, change.after, change.path), "diff"))
    if placeholders:
        parts.append(f"Empty placeholders: {', '.join(placeholders)}.\n")
    listed = "\n".join(f"- {item.path}: {item.reason}" for item in conflicts)
    body = (
        "## Changes\n"
        + ("\n".join(parts) if parts else "None.\n")
        + "\n## Conflicts\n"
        + (
            f"{listed}\n\nThis plan cannot be confirmed until every conflict is resolved.\n"
            if conflicts
            else "None.\n"
        )
        + "\n## Not changed\n"
        + f"Projects kept as they are: {', '.join(projects) if projects else 'none'}. Their\n"
        "objects, references, handoffs, bindings and context archives, tools/models.toml,\n"
        "roles, global/profile.md, the other framework files and Git history are unchanged.\n"
        "No model, native session, binding, context receipt or workspace handoff is created;\n"
        "WORKSPACE.md starts with no confirmed direction.\n"
    )
    return (header(fields) + body).encode()


def validate_plan(document: Document) -> str:
    """Check an archived plan's identity fields; returns the workspace name."""
    validate_values(document)
    h = mapping(document, document.header, "", set(PLAN_ORDER))
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    if h["kind"] != "adoption-plan":
        document.fail("kind", "expected adoption-plan")
    name = text(document, h["name"], "name")
    if h["conflicts"] != []:
        document.fail("conflicts", "an archived plan was confirmed, so it has no conflicts")
    return name


def matches(value: str, full: str) -> bool:
    """A full digest or a prefix of at least 16 lowercase hex digits of it."""
    return (
        re.fullmatch(r"[0-9a-f]{16,64}", value) is not None
        and len(value) >= MIN_PREFIX
        and full.startswith(value)
    )
