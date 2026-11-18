"""L2: read-only comparisons of recorded review configurations (R11).

Profile names are not stable experimental treatments: the public configuration digest is
part of every group key. Counts describe archived execution and researcher decisions,
never model correctness or a measured cost/quality ranking. Legacy Runs remain valid.
"""

import hashlib
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from toulmin.core.codec import decode
from toulmin.core.documents import Document, FormatError
from toulmin.core.identifiers import ObjectId, validate_project_name
from toulmin.core.repository import Repository
from toulmin.core.review import INTAKE_FILE, parse_review, validate_intake
from toulmin.core.review_plan import PLAN_FILE, decode_plan
from toulmin.core.usage import COUNTS, USAGE_FILE, decode_usage
from toulmin.protocols.review import OUTPUT_FILE, PROMPT_FILE


@dataclass
class _Group:
    plans: list[tuple[str, Document, dict[str, Any]]] = field(default_factory=list)
    counts: Counter[str] = field(default_factory=Counter)
    known: Counter[str] = field(default_factory=Counter)
    unknown: Counter[str] = field(default_factory=Counter)
    duration: float = 0.0
    dollars: float = 0.0


def _projects(repository: Repository, project: str | None) -> list[str]:
    if project is not None:
        repository.project(project)
        return [project]
    names = []
    for child in sorted(repository.path("projects", "directory").iterdir()):
        if child.name.startswith("."):
            continue
        # Do not follow symlinks even to discover project names; checked access below
        # diagnoses them rather than silently reading a different repository.
        if not child.is_symlink() and not child.is_dir():
            continue
        try:
            validate_project_name(child.name)
        except ValueError:
            continue
        names.append(child.name)
    return names


def _plan(repository: Repository, project: str, run: Document) -> dict[str, Any] | None:
    output = str(run.header["output"])
    archive = repository.path(output, "directory")
    if archive.parent != repository.path(f"projects/{project}/runs", "directory"):
        raise FormatError("Run output must be an archive directly inside its project's runs/")
    sidecar = repository.path(f"{output}/{PLAN_FILE}")
    if not sidecar.exists():
        return None  # Old Runs are counted by the original calibration section.
    plan = decode_plan(repository.path(f"{output}/{PLAN_FILE}", "file").read_bytes(), output)
    role = str(run.header["role"])
    # The checked plan defines operation membership. Critique manifests may use
    # custom role names, so a reviewer- prefix cannot establish their operation.
    if plan["role"] != role:
        raise FormatError("review plan role/operation does not match the Run")
    config = plan["configuration"]
    selected = config["models"] if plan["operation"] == "review" else [config["synthesizer"]]
    if not any(entry["alias"] == plan["model_alias"] for entry in selected):
        raise FormatError("review plan alias does not belong to its operation")
    if plan["reported_model"] is not None and plan["reported_model"] != run.header["model"]:
        raise FormatError("review plan reported model does not match the Run model")
    prompt = repository.path(f"{output}/{PROMPT_FILE}", "file").read_bytes()
    if hashlib.sha256(prompt).hexdigest() != plan["input_sha256"]:
        raise FormatError("review plan input_sha256 does not match archived prompt.md")
    raw = repository.path(f"{output}/{OUTPUT_FILE}")
    if raw.exists() or run.header["status"] == "completed":
        repository.path(f"{output}/{OUTPUT_FILE}", "file")
    return plan


def _usage(repository: Repository, run: Document, group: _Group, notes: list[str]) -> None:
    location = f"{run.header['output']}/{USAGE_FILE}"
    try:
        path = repository.path(location)
        usage = (
            decode_usage(repository.path(location, "file").read_bytes(), location)
            if (path.exists())
            else None
        )
        if (
            usage is not None
            and usage.cost_usd is not None
            and (not math.isfinite(usage.cost_usd) or usage.cost_usd < 0)
        ):
            raise FormatError("cost_usd: expected nonnegative finite number or null")
    except (OSError, ValueError) as error:
        notes.append(f"{location}: usage not counted: {error}")
        usage = None
    for name in COUNTS:
        value = getattr(usage, name) if usage is not None else None
        if value is None:
            group.unknown[name] += 1
        else:
            group.known[name] += value
    if usage is None or usage.cost_usd is None:
        group.unknown["cost_usd"] += 1
    else:
        group.dollars += usage.cost_usd


def _intake(repository: Repository, run: Document, group: _Group, notes: list[str]) -> None:
    location = f"{run.header['output']}/{INTAKE_FILE}"
    try:
        raw = f"{run.header['output']}/{OUTPUT_FILE}"
        path = repository.path(location)
        if (
            run.header["status"] == "failed"
            and not repository.path(raw).exists()
            and not path.exists()
        ):
            return  # A failed session may have no answer or intake at all.
        drafts = parse_review(repository.path(raw, "file").read_text(encoding="utf-8"), raw)
        group.counts["drafts"] += len(drafts)
        if not path.exists():
            return  # No record means no researcher decisions have been recorded.
        record = decode(repository.path(location, "file").read_bytes(), location)
        outcomes = validate_intake(record)
        if record.header["run"] != str(run.object_id) or record.header["output"] != raw:
            raise FormatError("intake record does not belong to this Run/output")
        if not outcomes.keys() <= {draft.label for draft in drafts}:
            raise FormatError("intake record names labels missing from the raw review")
        for entry in outcomes.values():
            group.counts[str(entry["outcome"])] += 1
    except (OSError, ValueError) as error:
        group.unknown["intake"] += 1
        notes.append(f"{location}: intake decisions not counted: {error}")


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _render_group(profile: str | None, digest: str, group: _Group) -> list[str]:
    title = "(custom selection; no named profile)" if profile is None else profile
    lines = [
        "",
        f"### Profile: {_cell(title)}",
        "",
        f"Configuration SHA-256: `{digest}`.",
        "",
        "| Reviews | Synthesis | Completed | Failed |",
        "| --- | --- | --- | --- |",
        f"| {group.counts['review']} | {group.counts['synthesis']} | "
        f"{group.counts['completed']} | {group.counts['failed']} |",
        "",
        "| Metric | Known total | Runs with unknown value |",
        "| --- | --- | --- |",
        f"| Aggregate session-seconds | {group.duration:.1f} | {group.unknown['duration']} |",
    ]
    for name in COUNTS:
        lines.append(f"| {name} | {group.known[name]} | {group.unknown[name]} |")
    lines += [
        f"| Provider-reported USD | {group.dollars:.6f} | {group.unknown['cost_usd']} |",
        "",
        "Researcher intake decisions (not correctness; duplicates excluded from adoption):",
        "",
        "| Drafts | Taken | Partly | Rejected | Duplicate | Runs with unknown intake |",
        "| --- | --- | --- | --- | --- | --- |",
        f"| {group.counts['drafts']} | {group.counts['taken']} | {group.counts['partly']} | "
        f"{group.counts['rejected']} | {group.counts['duplicate']} | {group.unknown['intake']} |",
        "",
        "Recorded identities and exact archived input-prompt digests (Run model may be a",
        "requested fallback when the provider reported no model):",
        "",
        "| Run | Round | Role | Alias | Requested model | Effort | Reported model | "
        "Run model | Input SHA-256 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, run, plan in group.plans:
        config = plan["configuration"]
        selected = config["models"] if plan["operation"] == "review" else [config["synthesizer"]]
        model = next(entry for entry in selected if entry["alias"] == plan["model_alias"])
        values = (
            name,
            plan["round_id"],
            plan["role"],
            plan["model_alias"],
            model["requested_model"] or "unreported default",
            model["effort"] or "provider default",
            plan["reported_model"] or "unknown",
            run.header["model"],
            plan["input_sha256"],
        )
        lines.append("| " + " | ".join(_cell(value) for value in values) + " |")
    return lines


def render_profile_calibration(root: Path, project: str | None = None) -> str:
    """Derive a deterministic Markdown section from checked auxiliary provenance only."""
    repository = Repository(root)
    groups: dict[tuple[str | None, str], _Group] = {}
    notes: list[str] = []
    for name in _projects(repository, project):
        try:
            repository.project(name)
            folder = repository.path(f"projects/{name}/runs", "directory")
        except (OSError, ValueError) as error:
            notes.append(f"{name}: project not counted: {error}")
            continue
        for path in sorted(folder.glob("R-*.md")):
            label = f"{name}/{path.stem}"
            try:
                run = repository.load(name, ObjectId.parse(path.stem))
                plan = _plan(repository, name, run)
            except (OSError, ValueError) as error:
                notes.append(f"{label}: profile provenance not counted: {error}")
                continue
            if plan is None:
                continue
            group = groups.setdefault((plan["profile"], plan["configuration_sha256"]), _Group())
            group.plans.append((label, run, plan))
            group.counts[str(plan["operation"])] += 1
            group.counts[str(run.header["status"])] += 1
            duration = run.header["duration_seconds"]
            if duration is None:
                group.unknown["duration"] += 1
            else:
                group.duration += duration
            _usage(repository, run, group, notes)
            if plan["operation"] == "review":
                _intake(repository, run, group, notes)
    lines = [
        "## Review profile calibration",
        "",
        "Groups use profile name AND recorded configuration SHA-256; changed configurations",
        "stay separate. Only Runs with valid review-plan.json provenance appear here. Legacy",
        "Runs without sidecars remain in the original calibration sections.",
        "Known totals sum reported values only; unknown counts prevent treating missing data",
        "as zero. Duration sums session-seconds, not parallel round wall-clock latency.",
        "Input tokens include cached input. USD is provider-reported, not a measured",
        "subscription charge. Prompt digests are checked against archived prompt.md; raw output",
        "paths are checked, but no raw-output checksum is stored in this sidecar schema.",
        "Verified actionable findings, omissions, human adjudication time and subscription",
        "usage are unmeasured in these records. Intake is researcher decisions, not correctness.",
        "No automatic ranking or cost/quality conclusion is derived.",
    ]
    for (profile, digest), group in sorted(
        groups.items(), key=lambda item: (item[0][0] or "", item[0][1])
    ):
        lines += _render_group(profile, digest, group)
    if not groups:
        lines += ["", "No valid recorded review-profile Runs."]
    lines += ["", "### Profile calibration diagnostics", ""]
    lines += [f"- {_cell(note)}" for note in notes] or ["No profile-record diagnostics."]
    return "\n".join(lines) + "\n"
