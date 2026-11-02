"""L1 draft skeletons and unfilled-placeholder detection, with no filesystem access.

A skeleton is a draft, not an object: it lacks id/created/confirmed_by and carries
placeholders that confirmed intake must reject, so an unedited template can never
become a research object.
"""

from typing import Any

from toulmin.core.documents import Document, sections
from toulmin.core.identifiers import ObjectKind
from toulmin.core.schema import (
    CLAIM_TYPES,
    DIRECTIONS,
    EVIDENCE_KINDS,
    GRADES,
    IMPORTANCE,
    SEVERITIES,
)

PLACEHOLDER = "<fill:"


def _fill(hint: str) -> str:
    return f'"{PLACEHOLDER} {hint}>"'


def _choices(values: tuple[str, ...]) -> str:
    return _fill(" | ".join(values))


def _quote(value: str) -> str:
    if not value.strip() or any(ord(character) < 32 for character in value):
        raise ValueError("actor: expected nonempty single-line text")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _human(actor: str | None) -> str:
    return f"source: {{kind: human, actor: {_quote(actor) if actor else _fill('researcher')}}}"


def _run(project: str) -> str:
    return (
        f"source: {{kind: run, ref: {_fill('R-NNN')}, "
        f"path: {_fill(f'projects/{project}/runs/<archive>/output.md')}}}"
    )


def skeleton(
    kind: ObjectKind,
    project: str,
    path: str,
    actor: str | None = None,
    role_inputs: tuple[str, tuple[str, ...]] | None = None,
) -> str:
    """Return a commented draft for `toulmin new` that fails intake until filled.

    For a Run, `role_inputs` (role, files) fills role and input_files from a resolved
    role manifest instead of leaving them to be retyped.
    """
    if role_inputs is not None and kind != ObjectKind.RUN:
        raise ValueError("role: only a Run draft takes a role's inputs")
    human, run = _human(actor), _run(project)
    alternative = {
        True: f"# Model-derived alternative: {run}",
        False: f"# Human-authored alternative: {_human(actor)}",
    }
    fields: list[str]
    body: list[tuple[str, str]]
    if kind == ObjectKind.CLAIM:
        fields = [
            human,
            alternative[True],
            f"type: {_choices(CLAIM_TYPES)}",
            f"importance: {_choices(IMPORTANCE)}",
            "tags: []  # e.g. [workload, hardware]",
            '# validation_plan: "Minimal experiment that would test this Claim."',
        ]
        body = [("Statement", "one testable statement")]
    elif kind == ObjectKind.EVIDENCE:
        fields = [
            human,
            alternative[True],
            f"target: {_fill('C-NNN')}",
            f"direction: {_choices(DIRECTIONS)}",
            f"kind: {_choices(EVIDENCE_KINDS)}",
            f"grade: {_choices(GRADES)}",
            "provenance:",
            f"  - description: {_fill('what this source is')}",
            f"    path: {_fill('root-relative file path; or replace path with url')}",
            "# verification is required when grade is verified; artifacts must exist:",
            '# verification: {method: "...", result: "...", artifacts: ["path/to/artifact"]}',
        ]
        body = [("Material", "the evidence itself")]
    elif kind == ObjectKind.OBJECTION:
        fields = [
            run,
            alternative[False],
            f"target: {_fill('C-NNN')}",
            f"severity: {_choices(SEVERITIES)}",
        ]
        body = [("Content", "the objection"), ("Response", ""), ("Ruling", "")]
    elif kind == ObjectKind.DECISION:
        fields = [human, f"related: [{_fill('C-NNN, O-NNN or other object IDs')}]"]
        body = [
            ("Context", "what prompted this ruling"),
            ("Choice", "what was decided"),
            ("Rejected alternatives", "options considered and why they lost"),
            ("Rationale", "why this choice"),
        ]
    elif kind == ObjectKind.EXPLORATION:
        fields = [run, alternative[False], f"lens: {_fill('lens, e.g. alternative mechanism')}"]
        body = [("Content", "the candidate branch")]
    elif kind == ObjectKind.SPEC:
        fields = [
            human,
            f"target: {_fill('C-NNN')}",
            "evidence: []  # Evidence IDs; required once the Spec has passed",
        ]
        body = [
            ("Requirements", "what to implement"),
            ("Acceptance criteria", "which evidence would show it works"),
        ]
    else:
        fields = [
            human,
            f"status: {_choices(('completed', 'failed'))}",
            f"model: {_fill('model name as reported by the tool')}",
            *_role_fields(role_inputs),
            f"output: {_fill(f'projects/{project}/runs/YYYYMMDDTHHMMSSZ-name')}",
            "session_id: null  # keep null when unknown; never guess",
            "duration_seconds: null  # keep null when unknown",
        ]
        body = [("Summary", "what was run and what it produced")]
        # Failure is required only for failed Runs; it is added by hand when needed.
    header = [
        "---",
        f"# {kind.value.capitalize()} draft for project {project}.",
        "# Replace every <fill: ...> value. id, created, confirmed_by and the initial",
        "# status are assigned at intake. Then run:",
        f"#   toulmin new {kind.value} {project} --input {path} --confirm",
        *fields,
        "---",
    ]
    text = [f"## {name}\n" + (f"{PLACEHOLDER} {hint}>\n" if hint else "") for name, hint in body]
    return "\n".join(header) + "\n" + "\n".join(text)


def _role_fields(role_inputs: tuple[str, tuple[str, ...]] | None) -> list[str]:
    if role_inputs is None:
        return [
            f"role: {_fill('e.g. reviewer')}",
            "input_files: []  # root-relative paths given to the model",
        ]
    role, files = role_inputs
    return [
        f"role: {_quote(role)}",
        f"input_files:  # from the {role} manifest; edit only if the session received others",
        *(f"  - {_quote(file)}" for file in files),
    ]


def unfilled(document: Document) -> str | None:
    """Return the first field still holding a placeholder, or None."""

    def visit(value: Any, field: str) -> str | None:
        if isinstance(value, str):
            return field if PLACEHOLDER in value else None
        if isinstance(value, dict):
            items = [(f"{field}.{key}" if field else str(key), item) for key, item in value.items()]
        elif isinstance(value, list):
            items = [(f"{field}[{index}]", item) for index, item in enumerate(value)]
        else:
            return None
        for name, item in items:
            found = visit(item, name)
            if found:
                return found
        return None

    found = visit(document.header, "")
    if found:
        return found
    if PLACEHOLDER in document.body:
        for name, content in sections(document).items():
            if PLACEHOLDER in content:
                return f"body.{name}"
        return "body"
    return None
