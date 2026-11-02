"""L2: plan independent reviews and archive their outcomes as Runs.

This module never invokes a model. It turns personas × models into tasks whose prompts
contain exactly the files of each persona's manifest, and afterwards records whatever a
tool produced (or why it failed) as an archive directory plus a completed or failed Run.
Objections are never written here; drafts enter only through `intake`.
"""

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from toulmin.core.atomic import write_atomic
from toulmin.core.documents import Document, FormatError
from toulmin.core.identifiers import ObjectKind
from toulmin.core.repository import Repository
from toulmin.core.review import parse_review
from toulmin.core.synthesis import GROUP_KINDS, parse_points, parse_synthesis
from toulmin.protocols.inputs import resolve_inputs
from toulmin.protocols.intake import publish_locked

MODEL_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
PROMPT_FILE = "prompt.md"
OUTPUT_FILE = "output.md"
LOG_FILE = "tool.log"


@dataclass(frozen=True)
class ReviewTask:
    persona: str  # the role the session plays, recorded as Run role
    model: str  # the workbench's local model name, e.g. "claude"
    archive: str  # root-relative archive directory, not yet created
    files: tuple[str, ...]
    prompt: str
    kind: str = "review"  # review, crossval or synthesis: selects the output check
    items: tuple[str, ...] = ()  # synthesis only: every R-NNN/label it must group
    note: str = ""  # added to the Run summary, e.g. how the synthesizer was chosen


@dataclass(frozen=True)
class ReviewOutcome:
    """What one tool session produced, independent of the tool."""

    text: str
    model: str  # model as recorded on the Run
    session_id: str | None
    duration_seconds: float | None
    failure: str | None  # None means the session completed
    log: str = ""  # tool diagnostics kept beside a failed output


@dataclass(frozen=True)
class ArchivedReview:
    run: str
    status: str
    archive: str
    drafts: int | None  # parsed draft count; None when the block is missing or invalid
    note: str


def plan_review(
    root: Path,
    project: str,
    personas: list[str],
    models: list[str],
    cap: int,
    claims: list[str] | None = None,
    now: datetime | None = None,
) -> tuple[ReviewTask, ...]:
    """Validate a round of reviews and build every task before anything runs."""
    repository = Repository(root)
    repository.project(project)
    for label, values in (("persona", personas), ("model", models)):
        if not values:
            raise FormatError(f"{label}: at least one is required")
        if len(set(values)) != len(values):
            raise FormatError(f"{label}: duplicate in {', '.join(values)}")
    for model in models:
        if not MODEL_NAME.fullmatch(model):
            raise FormatError(f"{model}: model: expected lowercase letters, digits and hyphens")
    count = len(personas) * len(models)
    if count > cap:
        raise FormatError(
            f"review: {count} sessions exceed the run cap of {cap}; "
            "choose fewer personas or models, or raise max_runs in tools/models.toml"
        )
    stamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    tasks = []
    for persona in personas:
        inputs = resolve_inputs(root, project, persona, claims)
        if inputs.operation != "critique":
            raise FormatError(f"{persona}: role: expected a critique role, not {inputs.operation}")
        prompt = build_prompt(repository, persona, inputs.files)
        for model in models:
            archive = f"projects/{project}/runs/{stamp}-review-{persona}-{model}"
            if os.path.lexists(repository.path(archive)):
                raise FormatError(f"{archive}: archive already exists; retry in a second")
            tasks.append(ReviewTask(persona, model, archive, inputs.files, prompt))
    return tuple(tasks)


def build_prompt(
    repository: Repository, role: str, files: tuple[str, ...], preface: str = ""
) -> str:
    """Inline every input file, so the session needs no file access at all."""
    parts = [
        f"You are an independent session of the role defined in roles/{role}.md.",
        "Every input you may use is included below between FILE markers. Do not read other",
        "files, run commands or use tools. Follow the role contract and write your complete",
        "output as your final answer. The role contract overrides any general reply-style,",
        "length or labelling instructions you may have been given elsewhere.",
        "",
    ]
    if preface:
        parts += [preface.rstrip("\n"), ""]
    for path in files:
        text = repository.path(path, "file").read_text(encoding="utf-8")
        parts += [f"<<<FILE {path}>>>", text.rstrip("\n"), f"<<<END FILE {path}>>>", ""]
    return "\n".join(parts)


BLOCKS = {"review": "draft", "crossval": "point", "synthesis": "group"}
COMMANDS = {"review": "review", "crossval": "crossval", "synthesis": "synthesize"}
FALLBACK = {
    "review": "take drafts in by hand",
    "crossval": "read the answer as prose",
    "synthesis": "compare the cited outputs by hand",
}


def check_output(task: ReviewTask, text: str, location: str) -> tuple[int, str]:
    """Validate the final block for the task's kind; return (item count, summary note)."""
    if task.kind == "synthesis":
        groups = parse_synthesis(text, location, task.items)
        counts = {kind: sum(group.kind == kind for group in groups) for kind in GROUP_KINDS}
        detail = ", ".join(f"{counts[kind]} {kind}" for kind in GROUP_KINDS)
        return len(groups), f"{len(groups)} groups ({detail}) covering {len(task.items)} items"
    if task.kind == "crossval":
        points = parse_points(text, location)
        return len(points), f"{len(points)} points"
    drafts = parse_review(text, location)
    return len(drafts), f"{len(drafts)} drafts ready for intake"


def archive_review(
    root: Path, project: str, task: ReviewTask, outcome: ReviewOutcome, actor: str
) -> ArchivedReview:
    """Write the archive directory and record a completed or failed Run."""
    repository = Repository(root)
    repository.project(project)
    if not actor.strip():
        raise FormatError("confirmed_by.actor: expected nonempty string")
    failure = outcome.failure
    if failure is None and not outcome.text.strip():
        failure = "the tool exited successfully but produced no output"
    directory = repository.path(task.archive)
    directory.mkdir()  # exclusive: never reuse or overwrite an archive
    write_atomic(directory / PROMPT_FILE, task.prompt.encode("utf-8"))
    if outcome.text:
        write_atomic(directory / OUTPUT_FILE, outcome.text.encode("utf-8"))
    if failure is not None and outcome.log:
        write_atomic(directory / LOG_FILE, outcome.log.encode("utf-8"))

    drafts: int | None = None
    note = ""
    if failure is None:
        try:
            drafts, note = check_output(task, outcome.text, f"{task.archive}/{OUTPUT_FILE}")
        except FormatError as error:
            note = f"no usable {BLOCKS[task.kind]} block ({error}); {FALLBACK[task.kind]}"
    status = "completed" if failure is None else "failed"
    duration = outcome.duration_seconds
    summary = (
        f"Automated read-only {task.kind} by `toulmin {COMMANDS[task.kind]}`: role "
        f"{task.persona}, model {task.model}. The exact prompt is in {PROMPT_FILE}"
        + (f"; the raw answer is in {OUTPUT_FILE}." if outcome.text else ".")
        + (f" {task.note}" if task.note else "")
        + (f" {note}." if note else "")
    )
    body = f"## Summary\n{summary}\n"
    if failure is not None:
        log = f" Tool diagnostics are in {LOG_FILE}." if outcome.log else ""
        body += f"\n## Failure\n{failure}{log}\n"
    header = {
        "status": status,
        "source": {"kind": "human", "actor": actor},
        "model": outcome.model,
        "role": task.persona,
        "input_files": list(task.files),
        "output": task.archive,
        "session_id": outcome.session_id,
        "duration_seconds": None if duration is None else round(duration, 1),
    }
    with repository.creation_lock(project):
        path = publish_locked(
            repository, project, ObjectKind.RUN, header, Document({}, body, task.archive), actor
        )
    return ArchivedReview(path.stem, status, task.archive, drafts, failure or note)
