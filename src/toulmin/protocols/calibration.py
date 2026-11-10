"""L2: derive adoption rates per model, role and operation from files (C5, Q22).

Reason for this L2 addition (docs/protocols.md, C5): design section 9 asks for reliability
calibration from the researcher's intake rulings. Nothing is stored apart from the files: the
report is recomputed from Runs, the intake.md records beside review outputs and the
Objections those records created. It is read-only and deterministic (no timestamps), so a
report written under global/calibration/ is regenerable and never a second source of truth.
It counts what the researcher decided; it says nothing about which model is right.
"""

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from toulmin.core.documents import DIRECTORIES
from toulmin.core.identifiers import ObjectId, ObjectKind, validate_project_name
from toulmin.core.repository import Repository
from toulmin.core.usage import COUNTS, USAGE_FILE, Usage, decode_usage
from toulmin.protocols.review import OUTPUT_FILE
from toulmin.protocols.review_intake import output_state

SYNTHESIS, CROSSVAL, REVIEW, OTHER = "synthesis", "crossval", "review", "other"
OBJECTION_STATUSES = ("open", "answered", "accepted", "deferred")


def operation(role: str) -> str:
    if role == "synthesizer":
        return SYNTHESIS
    if role == "crossval":
        return CROSSVAL
    if role == "reviewer" or role.startswith("reviewer-"):
        return REVIEW
    return OTHER


@dataclass
class Tally:
    runs: int = 0
    completed: int = 0
    failed: int = 0
    drafts: int = 0
    taken: int = 0
    partly: int = 0
    rejected: int = 0
    objections: Counter[str] = field(default_factory=Counter)  # current status of taken ones
    # R6: summed from usage.json; a count some reporting session left unknown is not summed
    reported: int = 0  # Runs with a usage.json
    tokens: Counter[str] = field(default_factory=Counter)
    unknown: set[str] = field(default_factory=set)  # counts at least one session did not report

    @property
    def decided(self) -> int:
        return self.taken + self.partly + self.rejected

    @property
    def pending(self) -> int:
        return self.drafts - self.decided

    def add(self, other: "Tally") -> None:
        names = ("runs", "completed", "failed", "drafts", "taken", "partly", "rejected", "reported")
        for name in names:
            setattr(self, name, getattr(self, name) + getattr(other, name))
        self.objections.update(other.objections)
        self.tokens.update(other.tokens)
        self.unknown |= other.unknown

    def count(self, usage: Usage) -> None:
        self.reported += 1
        for name in COUNTS[:3]:
            value = getattr(usage, name)
            if value is None:
                self.unknown.add(name)
            else:
                self.tokens[name] += value


@dataclass(frozen=True)
class Calibration:
    projects: tuple[str, ...]
    # (operation, model, role) -> tally; review drafts and outcomes only for operation review.
    groups: dict[tuple[str, str, str], Tally]
    skipped: tuple[str, ...]  # data left out, with the reason


def _projects(repository: Repository, project: str | None) -> list[str]:
    if project is not None:
        repository.project(project)
        return [project]
    folder = repository.path("projects", "directory")
    names = []
    for child in sorted(folder.iterdir()):
        if child.name.startswith(".") or child.is_symlink() or not child.is_dir():
            continue
        try:
            validate_project_name(child.name)
        except ValueError:
            continue
        names.append(child.name)
    return names


def calibration(root: Path, project: str | None = None) -> Calibration:
    """Tally every Run of the chosen project (or all projects) by operation, model and role."""
    repository = Repository(root)
    names = _projects(repository, project)
    groups: dict[tuple[str, str, str], Tally] = {}
    skipped: list[str] = []
    counted: list[str] = []
    for name in names:
        try:
            repository.project(name)
            folder = repository.path(f"projects/{name}/{DIRECTORIES[ObjectKind.RUN]}", "directory")
            runs = sorted(folder.glob("R-*.md"), key=lambda path: int(path.stem[2:]))
        except (OSError, ValueError) as error:
            skipped.append(f"{name}: project not counted: {error}")
            continue
        counted.append(name)
        for path in runs:
            try:
                header = repository.load(name, ObjectId.parse(path.stem)).header
            except (OSError, ValueError) as error:
                skipped.append(f"{name}/{path.stem}: Run not counted: {error}")
                continue
            role = str(header["role"])
            key = (operation(role), str(header["model"]), role)
            tally = groups.setdefault(key, Tally())
            tally.runs += 1
            relative = f"{header['output']}/{USAGE_FILE}"
            usage = repository.root / relative  # the Run's output is checked on load
            if usage.is_file() and not usage.is_symlink():
                try:
                    tally.count(decode_usage(usage.read_bytes(), relative))
                except (OSError, ValueError) as error:
                    skipped.append(f"{name}/{path.stem}: usage not counted: {error}")
            if header["status"] == "completed":
                tally.completed += 1
            else:
                tally.failed += 1
                continue
            if key[0] != REVIEW:
                continue
            output = f"{header['output']}/{OUTPUT_FILE}"
            try:
                state = output_state(root, name, output)
            except (OSError, ValueError) as error:
                skipped.append(f"{name}/{path.stem}: drafts not counted: {error}")
                continue
            tally.drafts += len(state.drafts)
            for entry in state.recorded.values():
                outcome = entry["outcome"]
                if outcome == "taken":
                    tally.taken += 1
                elif outcome == "partly":
                    tally.partly += 1
                else:
                    tally.rejected += 1
                if "object" in entry:
                    tally.objections[_status(repository, name, entry["object"], skipped)] += 1
    return Calibration(tuple(counted), groups, tuple(skipped))


def _status(repository: Repository, project: str, value: str, skipped: list[str]) -> str:
    try:
        return str(repository.load(project, ObjectId.parse(value)).header["status"])
    except (OSError, ValueError) as error:
        skipped.append(f"{project}/{value}: Objection status unknown: {error}")
        return "unknown"


def _rate(tally: Tally) -> str:
    if not tally.decided:
        return "-"
    return f"{100 * (tally.taken + tally.partly) / tally.decided:.0f}%"


def _merge(groups: dict[tuple[str, str, str], Tally], index: int) -> dict[str, Tally]:
    merged: dict[str, Tally] = {}
    for key, tally in groups.items():
        if key[0] == REVIEW:
            merged.setdefault(key[index], Tally()).add(tally)
    return dict(sorted(merged.items()))


def _cell(value: str) -> str:
    return value.replace("|", "\\|")


def render(report: Calibration, project: str | None) -> str:
    """The Markdown report; identical files give identical text."""
    scope = f"project {project}" if project else "all projects"
    command = "toulmin calibration" + (f" --project {project}" if project else "") + " --write"
    lines = [
        "# Calibration report",
        "",
        f"Scope: {scope} ({', '.join(report.projects) or 'none'}). Regenerate with `{command}`.",
        "",
        "Derived only from Runs, intake.md records and Objections; edits to this file are lost on",
        "regeneration. It counts what the researcher decided about each draft, not which model is",
        "right, and small counts mean little. Model is the name each Run recorded. Rejections",
        "include duplicates of a draft taken from another output; intake.md records each reason.",
        "Adopted = (taken + partly) / decided drafts.",
        "",
        "## Runs by operation",
        "",
        "| Operation | Model | Role | Runs | Completed | Failed |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for (kind, model, role), tally in sorted(report.groups.items()):
        lines.append(
            f"| {kind} | {_cell(model)} | {_cell(role)} | {tally.runs} | {tally.completed} | "
            f"{tally.failed} |"
        )
    if not report.groups:
        lines.append("| - | - | - | 0 | 0 | 0 |")
    header = (
        "| Drafts | Taken | Partly | Rejected | Pending | Adopted |",
        "| --- | --- | --- | --- | --- | --- |",
    )

    def row(tally: Tally) -> str:
        return (
            f"{tally.drafts} | {tally.taken} | {tally.partly} | {tally.rejected} | "
            f"{tally.pending} | {_rate(tally)} |"
        )

    reviews = {key: tally for key, tally in sorted(report.groups.items()) if key[0] == REVIEW}
    lines += ["", "## Review drafts by model and role", ""]
    lines += ["| Model | Role " + header[0], "| --- | --- " + header[1]]
    lines += [
        f"| {_cell(model)} | {_cell(role)} | {row(tally)}"
        for (_, model, role), tally in reviews.items()
    ]
    for title, index in (("model", 1), ("role", 2)):
        lines += ["", f"## Review drafts by {title}", ""]
        lines += [f"| {title.capitalize()} " + header[0], "| --- " + header[1]]
        lines += [
            f"| {_cell(name)} | {row(tally)}"
            for name, tally in _merge(report.groups, index).items()
        ]
    lines += [
        "",
        "## Objections created from review drafts, by current status",
        "",
        "| Model | Role | " + " | ".join(OBJECTION_STATUSES) + " |",
        "| --- | --- | " + " | ".join("---" for _ in OBJECTION_STATUSES) + " |",
    ]
    for (_, model, role), tally in reviews.items():
        if tally.objections:
            counts = " | ".join(str(tally.objections[status]) for status in OBJECTION_STATUSES)
            lines.append(f"| {_cell(model)} | {_cell(role)} | {counts} |")
    lines += [
        "",
        "## Token usage by operation",
        "",
        "From usage.json beside each output: what the tool reported, never estimates. Input",
        "includes cached input. `?` marks a total missing a count some session did not report;",
        "`-` means no session of the group reported usage.",
        "",
        "| Operation | Model | Role | Runs | With usage | Input | Cached input | Output |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for (kind, model, role), tally in sorted(report.groups.items()):
        counts = " | ".join(
            "-" if not tally.reported else "?" if name in tally.unknown else str(tally.tokens[name])
            for name in COUNTS[:3]
        )
        lines.append(
            f"| {kind} | {_cell(model)} | {_cell(role)} | {tally.runs} | {tally.reported} | "
            f"{counts} |"
        )
    lines += ["", "## Not counted", ""]
    lines += [f"- {item}" for item in report.skipped] or ["Nothing; every file was readable."]
    return "\n".join(lines) + "\n"
