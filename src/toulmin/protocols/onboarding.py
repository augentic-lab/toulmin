"""Reviewed existing-project onboarding and additive source/overview changes.

Only frozen research-workspace images are published. Source paths are never a
write target, and onboarding creates no scientific object or native session.
"""

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from toulmin.core.atomic import digest, handoff_mutex, write_atomic
from toulmin.core.creation import INPUT_ORDER, staging_directory
from toulmin.core.documents import FormatError
from toulmin.core.proposals import render_receipt
from toulmin.core.render import header
from toulmin.core.repository import Repository
from toulmin.core.schema import utc_text
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
from toulmin.protocols import project_creation
from toulmin.protocols.workspace_change import _repository, publish_sealed, receipt_for

DIRECTORY = re.compile(r"runs/[0-9]{8}T[0-9]{6}Z-onboard-[0-9a-f]{32}")


@dataclass(frozen=True)
class OnboardingSource:
    source: Source
    path: str
    filesystem: str
    inventory: bytes


@dataclass(frozen=True)
class OnboardingLoaded:
    directory: str
    seal: str
    project: str
    creation: str
    body: str
    images: tuple[Image, ...]


@dataclass(frozen=True)
class OnboardingOutcome:
    status: str
    loaded: OnboardingLoaded
    problems: tuple[str, ...] = ()


def _json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode()


def propose(
    root: Path,
    project: str,
    sources: tuple[OnboardingSource, ...],
    *,
    overview: str | None = None,
    now: datetime | None = None,
) -> OnboardingOutcome:
    """Freeze an onboarding packet; the child and source catalog stay absent."""
    repository = _repository(root)
    if not sources or any(item.source.project != project for item in sources):
        raise FormatError("onboarding sources must belong to the proposed project")
    moment = now or datetime.now(UTC)
    token = uuid.uuid4().hex
    stamp = moment.strftime("%Y%m%dT%H%M%SZ")
    directory = f"runs/{stamp}-onboard-{token}"
    # Reuse the established child creation validator and renderer, with deliberately
    # provisional framing rather than inferred scientific claims.
    values: list[Any] = [
        1,
        "project-creation-input",
        project,
        None,
        f"What should be understood or improved in {project}?",
        "Continue an existing project from its preserved local source.",
        ["Understand the linked source and choose the smallest next measurement."],
        [],
        [],
        ["Confirm the research question and scope after inspecting the source."],
        f"Understand and continue the existing {project} project.",
        "Onboarding does not modify source files or execute scripts. "
        "Subsequent development follows the researcher task and source repository rules; "
        "retain provenance.",
        "Review the bounded source inventory and choose the next question.",
        [],
        [],
        [],
    ]
    input_data = (
        header(list(zip(INPUT_ORDER, values, strict=True)))
        + "## Existing project\nLinked source inventory is provisional context, not Evidence.\n"
    ).encode()
    input_path = f"runs/drafts/onboard-{token}.md"
    repository.path(input_path).parent.mkdir(parents=True, exist_ok=True)
    write_atomic(repository.path(input_path), input_data)
    creation = project_creation.propose(root, project, input_path, moment, token)
    with handoff_mutex(repository.root):
        if pending(repository):
            raise FormatError("an incomplete workspace publication exists; finish it first")
        before_catalog = (
            repository.path(CATALOG).read_bytes() if repository.path(CATALOG).exists() else None
        )
        before_local = (
            repository.path(LOCAL).read_bytes() if repository.path(LOCAL).exists() else None
        )
        catalog = read_catalog(root) + tuple(item.source for item in sources)
        after_catalog = render_catalog(catalog)
        bindings = parse_bindings(before_local) if before_local is not None else {}
        bindings.update({item.source.source_id: (item.path, item.filesystem) for item in sources})
        images = [
            Image(CATALOG, before_catalog, after_catalog),
            Image(LOCAL, before_local, render_bindings(bindings)),
        ]
        if overview is not None:
            if not overview.strip():
                raise FormatError("overview must be nonempty when supplied")
            images.append(Image(f"projects/{project}/overview.md", None, overview.encode()))
        files = {f"inventory/{index}.json": item.inventory for index, item in enumerate(sources, 1)}
        specs = []
        for index, image in enumerate(images, 1):
            if image.path == LOCAL:
                # Machine paths never enter a tracked runs/ packet. Pending local
                # images are sealed by digest but kept under the ignored tools/.
                write_atomic(
                    repository.path(f"tools/onboard-{token}-after.local.toml"), image.after
                )
                if image.before is not None:
                    write_atomic(
                        repository.path(f"tools/onboard-{token}-before.local.toml"), image.before
                    )
            else:
                files[f"after/{index}"] = image.after
                if image.before is not None:
                    files[f"before/{index}"] = image.before
            specs.append(
                {
                    "path": image.path,
                    "before": None if image.before is None else digest(image.before),
                    "after": digest(image.after),
                }
            )
        packet = _json(
            {
                "schema_version": 1,
                "kind": "onboarding",
                "project": project,
                "creation": creation.loaded.directory,
                "creation_seal": creation.loaded.seal,
                "images": specs,
                "inventories": {
                    name: digest(data)
                    for name, data in files.items()
                    if name.startswith("inventory/")
                },
            }
        )
        files["packet.md"] = packet
        publish_sealed(repository, directory, files, digest(packet), ".onboarding-prepare-")
        # This small marker prevents the generic decision queue offering a partial
        # child creation independently of its onboarding transaction.
        write_atomic(repository.path(f"{creation.loaded.directory}/onboarding"), directory.encode())
    return OnboardingOutcome("proposed", load(root, directory))


def load(root: Path, value: str) -> OnboardingLoaded:
    repository = Repository(root)
    directory = value.removesuffix("/packet.md").rstrip("/")
    if not DIRECTORY.fullmatch(directory):
        raise FormatError(f"{value}: expected an onboarding packet")
    packet = repository.path(f"{directory}/packet.md", "file").read_bytes()
    seal = repository.path(f"{directory}/seal", "file").read_text().strip()
    if digest(packet) != seal:
        raise FormatError(f"{directory}: onboarding seal mismatch")
    try:
        parsed = json.loads(packet)
        if (
            set(parsed)
            != {
                "schema_version",
                "kind",
                "project",
                "creation",
                "creation_seal",
                "images",
                "inventories",
            }
            or type(parsed["schema_version"]) is not int
            or parsed["schema_version"] != 1
            or parsed["kind"] != "onboarding"
        ):
            raise ValueError("invalid onboarding fields")
        created = project_creation.load(root, parsed["creation"])
        if created.seal != parsed["creation_seal"] or created.packet.project != parsed["project"]:
            raise ValueError("creation packet mismatch")
        images = []
        allowed = {CATALOG, LOCAL, f"projects/{parsed['project']}/overview.md"}
        for index, spec in enumerate(parsed["images"], 1):
            if set(spec) != {"path", "before", "after"} or spec["path"] not in allowed:
                raise ValueError("invalid onboarding target")
            prefix = f"tools/onboard-{directory.rsplit('-', 1)[1]}" if spec["path"] == LOCAL else ""
            after_path = f"{prefix}-after.local.toml" if prefix else f"{directory}/after/{index}"
            before_path = f"{prefix}-before.local.toml" if prefix else f"{directory}/before/{index}"
            after = repository.path(after_path, "file").read_bytes()
            before = (
                repository.path(before_path, "file").read_bytes()
                if spec["before"] is not None
                else None
            )
            if (
                digest(after) != spec["after"]
                or (digest(before) if before is not None else None) != spec["before"]
            ):
                raise ValueError("onboarding target changed")
            images.append(Image(spec["path"], before, after))
        if len({i.path for i in images}) != len(images) or not {CATALOG, LOCAL}.issubset(
            {i.path for i in images}
        ):
            raise ValueError("missing or duplicated source targets")
        parse_catalog(next(i.after for i in images if i.path == CATALOG))
        new_catalog = parse_catalog(next(i.after for i in images if i.path == CATALOG))
        prior_catalog = next(i.before for i in images if i.path == CATALOG)
        old_catalog = parse_catalog(prior_catalog) if prior_catalog is not None else ()
        if new_catalog[: len(old_catalog)] != old_catalog:
            raise ValueError("onboarding cannot alter existing source associations")
        added = new_catalog[len(old_catalog) :]
        if (
            not 1 <= len(added) <= 2
            or any(s.project != parsed["project"] for s in added)
            or sum(s.role == "working" for s in added) != 1
        ):
            raise ValueError("onboarding needs one working and optional reference association")
        local_image = next(i for i in images if i.path == LOCAL)
        old_bindings = parse_bindings(local_image.before) if local_image.before is not None else {}
        new_bindings = parse_bindings(local_image.after)
        if any(new_bindings.get(k) != v for k, v in old_bindings.items()):
            raise ValueError("onboarding cannot replace existing local bindings")
        if set(new_bindings) != set(old_bindings) | {s.source_id for s in added}:
            raise ValueError("local bindings must match onboarding source associations")
        if any(i.path.endswith("/overview.md") and not i.after.decode().strip() for i in images):
            raise ValueError("empty overview")
        for name, sha in parsed["inventories"].items():
            if (
                not re.fullmatch(r"inventory/[1-9][0-9]*\.json", name)
                or digest(repository.path(f"{directory}/{name}", "file").read_bytes()) != sha
            ):
                raise ValueError("inventory changed")
    except (KeyError, TypeError, ValueError) as error:
        raise FormatError(f"{directory}: invalid onboarding packet: {error}") from error
    lines = [created.body, "\n## Linked sources\n"]
    prior_catalog = next(i.before for i in images if i.path == CATALOG)
    previous = parse_catalog(prior_catalog) if prior_catalog is not None else ()
    for source in parse_catalog(next(i.after for i in images if i.path == CATALOG)):
        if source not in previous:
            lines.append(
                f"- {source.source_id}: {source.kind}, {source.role}; "
                "source files remain in place.\n"
            )
    lines.append(
        "\n## Bounded inventories\n"
        + "\n".join(f"- {directory}/{name}" for name in parsed["inventories"])
    )
    if any(i.path.endswith("/overview.md") for i in images):
        lines.append(
            "\n## Proposed overview\n"
            + next(i.after.decode() for i in images if i.path.endswith("/overview.md"))
        )
    return OnboardingLoaded(
        directory, seal, parsed["project"], parsed["creation"], "\n".join(lines), tuple(images)
    )


def check(root: Path, loaded: OnboardingLoaded) -> tuple[str, ...]:
    repository = Repository(root)
    problems = project_creation.check(root, project_creation.load(root, loaded.creation))
    for image in loaded.images:
        path = repository.path(image.path)
        current = path.read_bytes() if path.exists() else None
        if current != image.before:
            problems.append(f"{image.path}: changed since onboarding preview; propose again")
    local = next(i for i in loaded.images if i.path == LOCAL)
    catalog = parse_catalog(next(i.after for i in loaded.images if i.path == CATALOG))
    bindings = parse_bindings(local.after)
    for source in catalog:
        if source.project != loaded.project:
            continue
        path_text, filesystem = bindings[source.source_id]
        path = Path(path_text)
        if any(p.is_symlink() for p in (path, *path.parents)) or ".." in path.parts:
            problems.append(f"{source.source_id}: source symlinks or '..' are forbidden")
            continue
        if (
            path == repository.root
            or path.is_relative_to(repository.root)
            or repository.root.is_relative_to(path)
        ):
            problems.append(f"{source.source_id}: source overlaps research workspace")
            continue
        if not path.is_dir():
            problems.append(
                f"{source.source_id}: source directory disappeared; bind or propose again"
            )
            continue
        info = path.stat()
        if f"{info.st_dev}:{info.st_ino}" != filesystem:
            problems.append(f"{source.source_id}: source directory replaced since preview")
    return tuple(problems)


def apply(
    root: Path,
    value: str,
    actor: str | None,
    *,
    confirmed: bool = False,
    approval_text: str | None = None,
) -> OnboardingOutcome:
    repository = _repository(root)
    with handoff_mutex(repository.root):
        loaded = load(root, value)
        record = f"{loaded.directory}/packet.md"
        if pending(repository):
            intent = read_intent(repository)
            if intent.record != record or intent.record_sha256 != loaded.seal:
                raise FormatError("another incomplete publication exists; finish it first")
            if not confirmed:
                return OnboardingOutcome(
                    "incomplete", loaded, ("rerun this onboarding decision to finish publication",)
                )
            finish(repository)
            return OnboardingOutcome("recovered", loaded)
        receipt = receipt_for(repository, loaded.directory, loaded.seal)
        if receipt:
            if receipt.disposition == "rejected":
                raise FormatError("onboarding was rejected; propose anew")
            return OnboardingOutcome("replayed", loaded)
        problems = check(root, loaded)
        if not confirmed:
            return OnboardingOutcome("preview", loaded, problems)
        if not actor or not actor.strip():
            raise FormatError("onboarding requires a confirming actor")
        if problems:
            raise FormatError("; ".join(problems))
        at = utc_text(datetime.now(UTC))
        creation = project_creation.load(root, loaded.creation)
        images = project_creation._child_images(repository, creation, actor, at)
        images += list(loaded.images)
        # Preserve both the established creation receipt and the enclosing decision.
        for directory, seal in (
            (creation.directory, creation.seal),
            (loaded.directory, loaded.seal),
        ):
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
                    f"{directory}/receipt.md",
                    None,
                    render_receipt(
                        f"{directory}/packet.md",
                        seal,
                        "applied",
                        actor,
                        at,
                        approval_text,
                        None,
                        results,
                    ),
                )
            )
        prepare(
            repository,
            Intent(
                "project-create",
                record,
                loaded.seal,
                actor,
                at,
                approval_text,
                tuple(images),
                staging_directory(creation.directory),
            ),
        )
        finish(repository)
        return OnboardingOutcome("created", loaded)


def reject(root: Path, value: str, actor: str, reason: str) -> OnboardingOutcome:
    repository = _repository(root)
    if not actor.strip() or not reason.strip():
        raise FormatError("onboarding rejection requires actor and reason")
    with handoff_mutex(repository.root):
        loaded = load(root, value)
        if pending(repository):
            raise FormatError("incomplete publication must finish before rejection")
        receipt = receipt_for(repository, loaded.directory, loaded.seal)
        if receipt:
            if receipt.disposition != "rejected":
                raise FormatError("onboarding already applied")
            return OnboardingOutcome("replayed", loaded)
        at = utc_text(datetime.now(UTC))
        write_atomic(
            repository.path(f"{loaded.directory}/receipt.md"),
            render_receipt(
                f"{loaded.directory}/packet.md",
                loaded.seal,
                "rejected",
                actor,
                at,
                None,
                reason,
                [],
            ),
        )
    return OnboardingOutcome("rejected", loaded)


def onboarding_context_files(root: Path, project: str) -> tuple[str, ...]:
    """Verified inventory paths of applied onboarding packets, without local paths.

    Read tracked catalog/packet digests only so copied workspaces need no old
    machine-local pending images merely to recover their confirmed context.
    """
    repository = Repository(root)
    paths = []
    runs = repository.path("runs")
    if not runs.exists():
        return ()
    repository.path("runs", "directory")
    for base in sorted(runs.glob("*-onboard-*")):
        directory = f"runs/{base.name}"
        if not DIRECTORY.fullmatch(directory):
            continue
        packet = repository.path(f"{directory}/packet.md", "file").read_bytes()
        seal = repository.path(f"{directory}/seal", "file").read_text().strip()
        if digest(packet) != seal:
            raise FormatError(f"{directory}: onboarding seal mismatch")
        try:
            value = json.loads(packet)
            if value["project"] != project:
                continue
            receipt = receipt_for(repository, directory, seal)
            if receipt is None or receipt.disposition != "applied":
                continue
            for name, expected in value["inventories"].items():
                if not re.fullmatch(r"inventory/[1-9][0-9]*\.json", name):
                    raise ValueError("invalid inventory path")
                relative = f"{directory}/{name}"
                if digest(repository.path(relative, "file").read_bytes()) != expected:
                    raise ValueError("inventory digest mismatch")
                paths.append(relative)
        except (KeyError, TypeError, ValueError) as error:
            raise FormatError(f"{directory}: invalid onboarding context: {error}") from error
    return tuple(paths)
