"""Confirmed structural overview and working/reference policy changes.

These research-context changes do not rule on scientific objects or alter stages.
Every update retains exact before/after images and a researcher receipt.
"""

import difflib
import json
import re
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from toulmin.core.atomic import digest, handoff_mutex, write_atomic
from toulmin.core.codec import decode, encode
from toulmin.core.documents import FormatError, replace_section, sections
from toulmin.core.project import validate_project
from toulmin.core.proposals import render_receipt
from toulmin.core.repository import Repository
from toulmin.core.schema import utc_text
from toulmin.core.skeletons import PLACEHOLDER
from toulmin.core.sources import (
    CATALOG,
    LOCAL,
    Source,
    parse_bindings,
    parse_catalog,
    read_catalog,
    render_bindings,
    render_catalog,
)
from toulmin.core.workspace_journal import Image, Intent, finish, pending, prepare, read_intent
from toulmin.protocols.workspace_change import _repository, publish_sealed, receipt_for

DIRECTORY = re.compile(r"runs/[0-9]{8}T[0-9]{6}Z-context-[0-9a-f]{32}")


@dataclass(frozen=True)
class ContextLoaded:
    directory: str
    seal: str
    project: str
    kind: str
    body: str
    images: tuple[Image, ...]


@dataclass(frozen=True)
class ContextOutcome:
    status: str
    loaded: ContextLoaded
    problems: tuple[str, ...] = ()


def _propose(
    root: Path, project: str, kind: str, rationale: str, images: list[Image]
) -> ContextOutcome:
    repository = _repository(root)
    repository.project(project)
    if not rationale.strip():
        raise FormatError("a change rationale is required")
    token = uuid.uuid4().hex
    directory = f"runs/{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-context-{token}"
    files = {}
    specs = []
    for index, image in enumerate(images, 1):
        if image.path == LOCAL:
            write_atomic(repository.path(f"tools/context-{token}-after.local.toml"), image.after)
            if image.before is not None:
                write_atomic(
                    repository.path(f"tools/context-{token}-before.local.toml"), image.before
                )
        else:
            files[f"after/{index}"] = image.after
            if image.before is not None:
                files[f"before/{index}"] = image.before
        specs.append(
            {
                "path": image.path,
                "before": digest(image.before) if image.before is not None else None,
                "after": digest(image.after),
            }
        )
    packet = (
        json.dumps(
            {
                "schema_version": 1,
                "kind": kind,
                "project": project,
                "rationale": rationale,
                "images": specs,
            },
            indent=2,
        )
        + "\n"
    ).encode()
    files["packet.md"] = packet
    with handoff_mutex(repository.root):
        if pending(repository):
            raise FormatError("incomplete workspace publication; finish it first")
        publish_sealed(repository, directory, files, digest(packet), ".context-prepare-")
    return ContextOutcome("proposed", load(root, directory))


def propose_overview(
    root: Path,
    project: str,
    content: str,
    *,
    rationale: str,
    goal: str | None = None,
    constraints: str | None = None,
) -> ContextOutcome:
    repository = _repository(root)
    repository.project(project)
    if not content.strip():
        raise FormatError("overview content must not be empty")
    if PLACEHOLDER in content:
        raise FormatError("overview contains unfilled draft placeholders")
    path = f"projects/{project}/overview.md"
    before = repository.path(path).read_bytes() if repository.path(path).exists() else None
    images = [Image(path, before, content.encode())]
    if goal is not None or constraints is not None:
        path = f"projects/{project}/PROJECT.md"
        before = repository.path(path, "file").read_bytes()
        document = decode(before, path)
        body = document.body
        for name, value in (("Goal", goal), ("Constraints", constraints)):
            if value is not None:
                if not value.strip() or re.search(r"^## ", value, re.M):
                    raise FormatError(f"{name}: expected nonempty section content without headings")
                body = replace_section(body, name, value)
        document = replace(document, body=body)
        validate_project(document, project)
        images.append(Image(path, before, encode(document)))
    return _propose(root, project, "overview", rationale, images)


def propose_source_role(
    root: Path, project: str, working_id: str, *, rationale: str
) -> ContextOutcome:
    repository = _repository(root)
    catalog = read_catalog(root)
    if not any(source.source_id == working_id and source.project == project for source in catalog):
        raise FormatError(f"{working_id}: source is not associated with project {project}")
    updated = tuple(
        replace(source, role="working" if source.source_id == working_id else "reference")
        if source.project == project
        else source
        for source in catalog
    )
    return _propose(
        root,
        project,
        "source-role",
        rationale,
        [Image(CATALOG, repository.path(CATALOG, "file").read_bytes(), render_catalog(updated))],
    )


def load(root: Path, value: str) -> ContextLoaded:
    repository = Repository(root)
    directory = value.removesuffix("/packet.md").rstrip("/")
    if not DIRECTORY.fullmatch(directory):
        raise FormatError("expected a context change packet")
    data = repository.path(f"{directory}/packet.md", "file").read_bytes()
    seal = repository.path(f"{directory}/seal", "file").read_text().strip()
    if digest(data) != seal:
        raise FormatError(f"{directory}: context packet seal mismatch")
    try:
        parsed = json.loads(data)
        if (
            set(parsed) != {"schema_version", "kind", "project", "rationale", "images"}
            or type(parsed["schema_version"]) is not int
            or parsed["schema_version"] != 1
            or parsed["kind"] not in {"overview", "source-role", "source-add"}
        ):
            raise ValueError("invalid packet fields")
        project = parsed["project"]
        repository.project(project)
        allowed = (
            {CATALOG, LOCAL}
            if parsed["kind"] == "source-add"
            else (
                {CATALOG}
                if parsed["kind"] == "source-role"
                else {f"projects/{project}/overview.md", f"projects/{project}/PROJECT.md"}
            )
        )
        images = []
        for index, spec in enumerate(parsed["images"], 1):
            if set(spec) != {"path", "before", "after"} or spec["path"] not in allowed:
                raise ValueError("unexpected target")
            prefix = f"tools/context-{directory.rsplit('-', 1)[1]}" if spec["path"] == LOCAL else ""
            before_path = f"{prefix}-before.local.toml" if prefix else f"{directory}/before/{index}"
            after_path = f"{prefix}-after.local.toml" if prefix else f"{directory}/after/{index}"
            before = (
                repository.path(before_path, "file").read_bytes()
                if spec["before"] is not None
                else None
            )
            after = repository.path(after_path, "file").read_bytes()
            if (
                digest(after) != spec["after"]
                or (digest(before) if before is not None else None) != spec["before"]
            ):
                raise ValueError("context image digest mismatch")
            images.append(Image(spec["path"], before, after))
        if not images or len({i.path for i in images}) != len(images):
            raise ValueError("missing or duplicate targets")
        _validate_images(project, parsed["kind"], images)
        body = f"## {parsed['kind']} change for {project}\n\n{parsed['rationale']}\n\n"
        for image in images:
            body += f"### {image.path}\n"
            if image.path == LOCAL:
                body += (
                    "Machine-local binding will be published; "
                    "absolute paths are kept in ignored files.\n"
                )
                continue
            body += (
                "```diff\n"
                + "".join(
                    difflib.unified_diff(
                        (image.before or b"").decode().splitlines(keepends=True),
                        image.after.decode().splitlines(keepends=True),
                        fromfile="before",
                        tofile="after",
                    )
                )
                + "\n```\n"
            )
    except (KeyError, TypeError, ValueError) as error:
        raise FormatError(f"{directory}: invalid context packet: {error}") from error
    return ContextLoaded(directory, seal, project, parsed["kind"], body, tuple(images))


def _validate_images(project: str, kind: str, images: list[Image]) -> None:
    if kind == "overview":
        if not any(i.path.endswith("/overview.md") for i in images):
            raise ValueError("overview target required")
        for image in images:
            if image.path.endswith("/overview.md"):
                if not image.after.decode().strip():
                    raise ValueError("empty overview")
                if PLACEHOLDER in image.after.decode():
                    raise ValueError("overview contains unfilled draft placeholders")
                continue
            if image.before is None:
                raise ValueError("charter must already exist")
            before = decode(image.before, image.path)
            after = decode(image.after, image.path)
            validate_project(before, project)
            validate_project(after, project)
            if before.header != after.header:
                raise ValueError("overview changes cannot alter charter metadata or stage")
            old, new = sections(before), sections(after)
            if {k: v for k, v in old.items() if k not in {"Goal", "Constraints"}} != {
                k: v for k, v in new.items() if k not in {"Goal", "Constraints"}
            }:
                raise ValueError("overview changes may update only Goal and Constraints")
        return
    catalog = next((i for i in images if i.path == CATALOG), None)
    if catalog is None:
        raise ValueError("source catalog target required")
    old_sources = parse_catalog(catalog.before) if catalog.before is not None else ()
    new_sources = parse_catalog(catalog.after)
    before_map = {(i.source_id, i.project): i for i in old_sources}
    after_map = {(i.source_id, i.project): i for i in new_sources}
    if not before_map.keys() <= after_map.keys():
        raise ValueError("source associations cannot be removed")
    for key, old_source in before_map.items():
        new_source = after_map[key]
        if replace(old_source, role=new_source.role) != new_source or (
            old_source.project != project and old_source != new_source
        ):
            raise ValueError("existing identities and other projects cannot change")
    added = [v for k, v in after_map.items() if k not in before_map]
    if kind == "source-role" and (added or len(images) != 1):
        raise ValueError("role change must preserve source associations")
    if kind == "source-add":
        if len(added) != 1 or added[0].project != project:
            raise ValueError("source add needs exactly one new association")
        local = next((i for i in images if i.path == LOCAL), None)
        if local is None:
            raise ValueError("source add needs local binding")
        old_bindings = parse_bindings(local.before) if local.before is not None else {}
        new_bindings = parse_bindings(local.after)
        if added[0].source_id not in new_bindings or any(
            new_bindings.get(k) != v for k, v in old_bindings.items()
        ):
            raise ValueError("source add cannot replace existing machine-local bindings")


def propose_source_add(
    root: Path, project: str, source: Source, path: str, filesystem: str, *, rationale: str
) -> ContextOutcome:
    repository = _repository(root)
    catalog = read_catalog(root)
    if source.project != project or any(
        (s.source_id, s.project) == (source.source_id, project) for s in catalog
    ):
        raise FormatError("source association already exists or names another project")
    updated = tuple(
        replace(s, role="reference") if source.role == "working" and s.project == project else s
        for s in catalog
    ) + (source,)
    catalog_path = repository.path(CATALOG)
    local_path = repository.path(LOCAL)
    before_catalog = catalog_path.read_bytes() if catalog_path.exists() else None
    before_local = local_path.read_bytes() if local_path.exists() else None
    bindings = parse_bindings(before_local) if before_local is not None else {}
    if source.source_id in bindings and bindings[source.source_id] != (path, filesystem):
        raise FormatError(
            "shared source already bound to another path; bind explicitly before associating it"
        )
    bindings[source.source_id] = (path, filesystem)
    return _propose(
        root,
        project,
        "source-add",
        rationale,
        [
            Image(CATALOG, before_catalog, render_catalog(updated)),
            Image(LOCAL, before_local, render_bindings(bindings)),
        ],
    )


def check(root: Path, loaded: ContextLoaded) -> tuple[str, ...]:
    repository = Repository(root)
    return tuple(
        f"{image.path}: changed since preview; propose again"
        for image in loaded.images
        if (
            repository.path(image.path).read_bytes()
            if repository.path(image.path).exists()
            else None
        )
        != image.before
    )


def apply(
    root: Path,
    value: str,
    actor: str | None,
    *,
    confirmed: bool = False,
    approval_text: str | None = None,
) -> ContextOutcome:
    repository = _repository(root)
    with handoff_mutex(repository.root):
        loaded = load(root, value)
        record = f"{loaded.directory}/packet.md"
        if pending(repository):
            intent = read_intent(repository)
            if intent.record != record or intent.record_sha256 != loaded.seal:
                raise FormatError("another publication is incomplete")
            if not confirmed:
                return ContextOutcome(
                    "incomplete", loaded, ("confirm this decision again to recover",)
                )
            finish(repository)
            return ContextOutcome("recovered", loaded)
        receipt = receipt_for(repository, loaded.directory, loaded.seal)
        if receipt:
            if receipt.disposition == "rejected":
                raise FormatError("context change was rejected; propose anew")
            return ContextOutcome("replayed", loaded)
        problems = check(root, loaded)
        if not confirmed:
            return ContextOutcome("preview", loaded, problems)
        if not actor or not actor.strip():
            raise FormatError("confirming actor is required")
        if problems:
            raise FormatError("; ".join(problems))
        at = utc_text(datetime.now(UTC))
        images = list(loaded.images)
        results = [
            {
                "path": image.path,
                "before_sha256": digest(image.before) if image.before is not None else None,
                "after_sha256": digest(image.after),
            }
            for image in images
        ]
        images.append(
            Image(
                f"{loaded.directory}/receipt.md",
                None,
                render_receipt(
                    record, loaded.seal, "applied", actor, at, approval_text, None, results
                ),
            )
        )
        prepare(
            repository,
            Intent(
                "workspace-change", record, loaded.seal, actor, at, approval_text, tuple(images)
            ),
        )
        finish(repository)
        return ContextOutcome("applied", loaded)


def reject(root: Path, value: str, actor: str, reason: str) -> ContextOutcome:
    repository = _repository(root)
    if not actor.strip() or not reason.strip():
        raise FormatError("actor and rejection reason required")
    with handoff_mutex(repository.root):
        loaded = load(root, value)
        if pending(repository):
            raise FormatError("incomplete publication must finish first")
        receipt = receipt_for(repository, loaded.directory, loaded.seal)
        if receipt:
            if receipt.disposition != "rejected":
                raise FormatError("context change already applied")
            return ContextOutcome("replayed", loaded)
        write_atomic(
            repository.path(f"{loaded.directory}/receipt.md"),
            render_receipt(
                f"{loaded.directory}/packet.md",
                loaded.seal,
                "rejected",
                actor,
                utc_text(datetime.now(UTC)),
                None,
                reason,
                [],
            ),
        )
    return ContextOutcome("rejected", loaded)
