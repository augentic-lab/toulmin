"""L2: plan a synthesis over archived outputs, and a cross-validation round.

The synthesizer receives its static manifest plus exactly the raw outputs of the Runs
the researcher names, and must group every ``R-NNN/label`` in them. Its model rotates
deterministically (Q23): the next configured model after the one that wrote the
project's latest synthesis, unless the researcher overrides it. Nothing here invokes a
model or writes an object; synthesis is archived as a Run like any other session.
"""

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from toulmin.core.documents import FormatError
from toulmin.core.identifiers import ObjectId, ObjectKind
from toulmin.core.repository import Repository
from toulmin.core.review import parse_review
from toulmin.core.synthesis import parse_points
from toulmin.protocols.inputs import resolve_inputs
from toulmin.protocols.review import MODEL_NAME, OUTPUT_FILE, ReviewTask, build_prompt

SYNTHESIZER = "synthesizer"
CROSSVAL = "crossval"
SYNTHESIS_ARCHIVE = re.compile(r"\d{8}T\d{6}Z-synthesis-(?P<model>[a-z0-9]+(?:-[a-z0-9]+)*)")


@dataclass(frozen=True)
class Source:
    run: str
    output: str  # root-relative raw output path
    items: tuple[str, ...]  # R-NNN/label, in output order


def round_sources(root: Path, project: str, runs: list[str]) -> tuple[Source, ...]:
    """Validate the Runs of one round and list every labelled item they contain."""
    repository = Repository(root)
    repository.project(project)
    if len(runs) < 2:
        raise FormatError("synthesis: name at least two Runs; one output has nothing to compare")
    if len(set(runs)) != len(runs):
        raise FormatError(f"synthesis: duplicate Run in {', '.join(runs)}")
    sources = []
    roles: set[bool] = set()
    for value in runs:
        try:
            object_id = ObjectId.parse(value)
        except ValueError as error:
            raise FormatError(f"{value}: run: {error}") from error
        if object_id.kind != ObjectKind.RUN:
            raise FormatError(f"{value}: run: expected a Run ID in project {project}")
        run = repository.load(project, object_id)
        header = run.header
        if header["status"] != "completed":
            raise FormatError(f"{value}: run: status is {header['status']}; only completed Runs")
        if header["role"] == SYNTHESIZER:
            raise FormatError(f"{value}: run: is a synthesis; name the original outputs instead")
        output = f"{header['output']}/{OUTPUT_FILE}"
        raw = repository.path(output, "file").read_text(encoding="utf-8")
        answer = header["role"] == CROSSVAL
        roles.add(answer)
        try:
            labels = (
                [point.label for point in parse_points(raw, output)]
                if answer
                else [draft.label for draft in parse_review(raw, output)]
            )
        except FormatError as error:
            raise FormatError(f"{value}: {error}; synthesis needs labelled items") from error
        sources.append(Source(value, output, tuple(f"{value}/{label}" for label in labels)))
    if len(roles) > 1:
        raise FormatError("synthesis: do not mix cross-validation answers with reviews")
    return tuple(sources)


def choose_model(
    root: Path, project: str, order: list[str], override: str | None
) -> tuple[str, str]:
    """Return (model, recorded reason): rotation after the latest synthesis, or override."""
    if not order:
        raise FormatError("synthesis: no models to rotate; set [review] models")
    previous = _latest_synthesis(Repository(root), project)
    if previous is None:
        rotated = order[0]
        reason = f"first synthesis in this project; first of [{', '.join(order)}]"
    else:
        run, model = previous
        rotated = order[(order.index(model) + 1) % len(order)] if model in order else order[0]
        reason = f"previous synthesis {run} used {model}; next of [{', '.join(order)}]"
    if override is not None:
        if not MODEL_NAME.fullmatch(override):
            raise FormatError(f"{override}: model: expected lowercase letters, digits and hyphens")
        return override, f"chosen by --model override (rotation would choose {rotated}: {reason})"
    return rotated, f"chosen by rotation: {reason}"


def _latest_synthesis(repository: Repository, project: str) -> tuple[str, str] | None:
    latest: tuple[int, str, str] | None = None
    folder = repository.path(f"projects/{project}/runs", "directory")
    for path in folder.glob("R-*.md"):
        run = repository.load(project, ObjectId.parse(path.stem))
        if run.header["role"] != SYNTHESIZER:
            continue
        match = SYNTHESIS_ARCHIVE.fullmatch(PurePosixPath(run.header["output"]).name)
        if match is None:
            continue  # a hand-archived synthesis does not name its local model
        number = run.object_id.number
        if latest is None or number > latest[0]:
            latest = (number, str(run.object_id), match["model"])
    return None if latest is None else (latest[1], latest[2])


def plan_synthesis(
    root: Path,
    project: str,
    sources: tuple[Source, ...],
    model: str,
    reason: str,
    now: datetime | None = None,
) -> ReviewTask:
    """Build the synthesis task: static manifest plus exactly the named raw outputs."""
    repository = Repository(root)
    inputs = resolve_inputs(root, project, SYNTHESIZER)
    if inputs.operation != "synthesize":
        raise FormatError(f"{SYNTHESIZER}: role: expected operation synthesize")
    items = tuple(item for source in sources for item in source.items)
    lines = ["Outputs in this round, by Run (group every item below exactly once):"]
    for source in sources:
        lines.append(f"- {source.run}: {source.output}")
        lines += [f"  - {item}" for item in source.items]
    files = inputs.files + tuple(source.output for source in sources)
    archive = _archive(repository, project, now, f"synthesis-{model}")
    return ReviewTask(
        SYNTHESIZER,
        model,
        archive,
        files,
        build_prompt(repository, SYNTHESIZER, files, "\n".join(lines)),
        kind="synthesis",
        items=items,
        note=f"Synthesizer model {reason}. Sources: "
        + ", ".join(source.run for source in sources)
        + ".",
    )


def plan_crossval(
    root: Path,
    project: str,
    question: str,
    models: list[str],
    cap: int,
    extra_sessions: int = 0,
    now: datetime | None = None,
) -> tuple[ReviewTask, ...]:
    """One independent answer per model to a question drafted under runs/drafts/."""
    repository = Repository(root)
    repository.project(project)
    question = repository.relative(question)
    drafts = f"projects/{project}/runs/drafts/"
    if not question.startswith(drafts) or "/" in question.removeprefix(drafts):
        raise FormatError(f"{question}: question: expected a file directly in {drafts}")
    repository.path(question, "file")
    if not models:
        raise FormatError("model: at least one is required")
    if len(set(models)) != len(models):
        raise FormatError(f"model: duplicate in {', '.join(models)}")
    for model in models:
        if not MODEL_NAME.fullmatch(model):
            raise FormatError(f"{model}: model: expected lowercase letters, digits and hyphens")
    count = len(models) + extra_sessions
    if count > cap:
        raise FormatError(
            f"crossval: {count} sessions exceed the run cap of {cap}; "
            "choose fewer models, or raise max_runs in tools/models.toml"
        )
    inputs = resolve_inputs(root, project, CROSSVAL)
    if inputs.operation != "answer":
        raise FormatError(f"{CROSSVAL}: role: expected operation answer")
    files = inputs.files + (question,)
    prompt = build_prompt(repository, CROSSVAL, files, f"The question to answer is in {question}.")
    return tuple(
        ReviewTask(
            CROSSVAL,
            model,
            _archive(repository, project, now, f"crossval-{model}"),
            files,
            prompt,
            kind="crossval",
            note=f"Question: {question}.",
        )
        for model in models
    )


def _archive(repository: Repository, project: str, now: datetime | None, name: str) -> str:
    stamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive = f"projects/{project}/runs/{stamp}-{name}"
    if os.path.lexists(repository.path(archive)):
        raise FormatError(f"{archive}: archive already exists; retry in a second")
    return archive
