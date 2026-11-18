"""WO3 root publications, reusing v1 creation, receipt and journal contracts (L2).

Caller-supplied observations are plain data. The L3 coordinator must re-observe
sources under checkout locks before calling confirmed publication. Recovery never
re-observes a moving source into new output.
"""

import difflib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from toulmin.core import workspace_journal as journal
from toulmin.core.atomic import digest, sync_directory, write_atomic
from toulmin.core.codec import decode
from toulmin.core.creation import render_charter, staging_directory
from toulmin.core.documents import FormatError
from toulmin.core.proposals import Receipt, charter_after, render_receipt, validate_change_input
from toulmin.core.repository import Repository
from toulmin.core.schema import utc_text
from toulmin.core.scope import Scope
from toulmin.core.sources import (
    CATALOG,
    LOCAL,
    SourceCatalog,
    parse_bindings,
    parse_source_catalog,
)
from toulmin.core.workspace import validate_charter
from toulmin.core.workspace_onboarding import (
    MAX_BYTES,
    Loaded,
    canonical,
    inventory,
    load_envelope,
    overview,
    owners,
)
from toulmin.protocols import project_creation
from toulmin.protocols.workspace_change import _repository, receipt_for


@dataclass(frozen=True)
class Outcome:
    status: str
    loaded: Loaded
    receipt: Receipt | None = None
    problems: tuple[str, ...] = ()


def _raw(repository: Repository, path: str) -> bytes | None:
    location = repository.path(path)
    if not location.exists():
        return None
    return repository.path(path, "file").read_bytes()


def deltas(before: SourceCatalog, after: SourceCatalog) -> list[dict[str, Any]]:
    old = {(a.scope, a.source): a.role for a in before.associations}
    new = {(a.scope, a.source): a.role for a in after.associations}
    if set(old) - set(new):
        raise FormatError("source catalog: association removal is forbidden")
    return [
        {
            "scope": scope.to_data(),
            "source": source,
            "before": old.get((scope, source)),
            "after": role,
        }
        for (scope, source), role in sorted(
            new.items(), key=lambda item: (item[0][0].kind, item[0][0].project or "", item[0][1])
        )
        if role != old.get((scope, source))
    ]


def seal_packet(
    root: Path,
    directory: str,
    data: dict[str, Any],
    effects: dict[str, bytes],
    artifacts: dict[str, bytes],
    *,
    project_input: bytes | None = None,
) -> Outcome:
    """Called under root lock. Archive observations → privately owned v1 → outer seal."""
    repository = _repository(root)
    if journal.pending(repository):
        raise FormatError("workspace publication incomplete; replay its exact apply first")
    folder = repository.path(directory)
    folder.mkdir()
    token = directory.rsplit("-", 1)[1]
    inputs = list(data["inputs"])
    preconditions = list(data["preconditions"])
    specs = []
    for path, artifact_raw in artifacts.items():
        target = repository.path(f"{directory}/{path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(target, artifact_raw)
    # A read catalog is frozen even for operations that do not write it, so historical
    # semantic validation and replay do not depend on today's catalog bytes.
    for path in (CATALOG, LOCAL):
        raw = _raw(repository, path)
        if raw is None:
            continue
        snapshot = (
            f"tools/wo-{token}-before.local.toml"
            if path == LOCAL
            else f"{directory}/context/sources.toml"
        )
        target = repository.path(snapshot)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            write_atomic(target, raw)
        inputs.append({"path": snapshot, "sha256": digest(raw)})
    for index, (path, after) in enumerate(effects.items(), 1):
        before = _raw(repository, path)
        if before == after:
            continue
        if len(after) > MAX_BYTES or (before is not None and len(before) > MAX_BYTES):
            raise FormatError(f"{path}: publication image exceeds 1,000,000 bytes")
        after_image = (
            f"tools/wo-{token}-after.local.toml" if path == LOCAL else f"{directory}/after/{index}"
        )
        before_image = (
            None
            if before is None
            else (
                f"tools/wo-{token}-before.local.toml"
                if path == LOCAL
                else f"{directory}/before/{index}"
            )
        )
        for name, raw in ((after_image, after), (before_image, before)):
            if name is not None and raw is not None:
                target = repository.path(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    write_atomic(target, raw)
                elif target.read_bytes() != raw:
                    raise FormatError(f"{name}: preparation image collision")
        specs.append(
            {
                "path": path,
                "before": None if before is None else digest(before),
                "after": digest(after),
                "before_image": before_image,
                "after_image": after_image,
            }
        )
    if project_input is not None:
        input_path = f"{directory}/project-input.md"
        write_atomic(repository.path(input_path), project_input)
        inputs.append({"path": input_path, "sha256": digest(project_input)})
        creation = project_creation.propose(
            root,
            data["project"],
            input_path,
            datetime.fromisoformat(data["created"]),
            owner=directory,
            locked=True,
        )
        data["creation"] = {"path": creation.loaded.directory, "seal": creation.loaded.seal}
        marker = f"{creation.loaded.directory}/onboarding"
        item = {"path": marker, "sha256": digest(directory.encode())}
        inputs.append(item)
        preconditions.append(item)
    data = {**data, "images": specs, "inputs": inputs, "preconditions": preconditions}
    raw = canonical(data)
    # Validate everything before publishing the final seal. The archive remains visibly
    # incomplete if a failure interrupts preparation; no confirmed target is written.
    from toulmin.core.workspace_onboarding import envelope

    envelope(raw, directory)
    write_atomic(repository.path(f"{directory}/packet.md"), raw)
    write_atomic(repository.path(f"{directory}/seal"), (digest(raw) + "\n").encode())
    sync_directory(folder)
    sync_directory(folder.parent)
    loaded = load(root, directory)
    return Outcome("proposed", loaded)


def _frozen(
    repository: Repository, path: str, expected: str, *, local_optional: bool
) -> bytes | None:
    target = repository.path(path)
    if (
        not target.exists()
        and local_optional
        and path.startswith("tools/")
        and path.endswith(".local.toml")
    ):
        return None
    raw = repository.path(path, "file").read_bytes()
    if digest(raw) != expected:
        raise FormatError(f"{path}: changed after preview; preserve archive and propose again")
    return raw


def images(
    repository: Repository, loaded: Loaded, *, local_optional: bool = False
) -> tuple[journal.Image, ...]:
    result = []
    for item in loaded.data["images"]:
        before = (
            None
            if item["before"] is None
            else _frozen(
                repository, item["before_image"], item["before"], local_optional=local_optional
            )
        )
        after = _frozen(
            repository, item["after_image"], item["after"], local_optional=local_optional
        )
        if after is not None and (item["before"] is None or before is not None):
            result.append(journal.Image(item["path"], before, after))
    return tuple(result)


def _catalogs(
    repository: Repository, loaded: Loaded, published: tuple[journal.Image, ...]
) -> tuple[SourceCatalog, SourceCatalog]:
    changed = next((image for image in published if image.path == CATALOG), None)
    if changed is not None:
        before = (
            parse_source_catalog(changed.before)
            if changed.before is not None
            else SourceCatalog(2, (), ())
        )
        return before, parse_source_catalog(changed.after)
    snapshot = f"{loaded.directory}/context/sources.toml"
    before = (
        parse_source_catalog(repository.path(snapshot, "file").read_bytes())
        if repository.path(snapshot).exists()
        else SourceCatalog(2, (), ())
    )
    return before, before


def load(root: Path, value: str, *, local_optional: bool = False) -> Loaded:
    repository = Repository(root)
    loaded = load_envelope(repository, value)
    data = loaded.data
    token = loaded.directory.rsplit("-", 1)[1]
    for item in data["inputs"]:
        _frozen(repository, item["path"], item["sha256"], local_optional=local_optional)
    paths = {item["path"]: item["sha256"] for item in data["preconditions"]}
    for item in data["images"]:
        if item["path"] in paths and paths[item["path"]] != item["before"]:
            raise FormatError("packet: read/write before expectations disagree")
        for field, prefix in (("before_image", "before"), ("after_image", "after")):
            path = item[field]
            if path is None:
                continue
            if item["path"] == LOCAL:
                if path != f"tools/wo-{token}-{prefix}.local.toml":
                    raise FormatError("packet: local image outside its reserved ignored path")
            elif (
                not path.startswith(f"{loaded.directory}/{prefix}/")
                or not path.rsplit("/", 1)[1].isdigit()
            ):
                raise FormatError("packet: tracked image outside its reserved archive")
    frozen = images(repository, loaded, local_optional=local_optional)
    old, new = _catalogs(repository, loaded, frozen)
    if new.schema_version != 2:
        raise FormatError("packet requires v2 catalog; propose source upgrade separately")
    old_defs = {d.id: d for d in old.definitions}
    new_defs = {d.id: d for d in new.definitions}
    if any(new_defs.get(key) != item for key, item in old_defs.items()):
        raise FormatError("packet: old source definitions are immutable")
    changes = deltas(old, new)

    def ordered(items: list[dict[str, Any]]) -> list[bytes]:
        return sorted(canonical(item) for item in items)

    if ordered(changes) != ordered(data["association_changes"]):
        raise FormatError(
            "packet: declared association changes differ from exact before/after semantics"
        )
    action_ids = []
    for item in data["source_actions"]:
        source = item["source"]
        action_ids.append(source)
        definition = new.definition(source)
        if definition.sha256 != item["definition_sha256"] or (source in old_defs) != (
            item["action"] == "reuse"
        ):
            raise FormatError("packet: source action disagrees with definitions")
    if len(action_ids) != len(set(action_ids)) or set(new_defs) - set(old_defs) != {
        item["source"] for item in data["source_actions"] if item["action"] == "register"
    }:
        raise FormatError("packet: new/duplicate definitions are not exactly declared")
    inventory_ids = set()
    for item in data["inventories"]:
        source = item["source"]
        if source in inventory_ids or item["path"] != f"inventory/{source}.json":
            raise FormatError("packet: duplicate or misplaced inventory")
        inventory_ids.add(source)
        raw = _frozen(
            repository, f"{loaded.directory}/{item['path']}", item["sha256"], local_optional=False
        )
        assert raw is not None
        observed = inventory(raw, item["path"])
        if source not in action_ids or observed["identity"] != new.definition(source).identity:
            raise FormatError("packet: inventory identity/source disagrees with action")
    if data["notes"] is not None:
        _frozen(
            repository,
            f"{loaded.directory}/{data['notes']['path']}",
            data["notes"]["sha256"],
            local_optional=False,
        )
    _effects(repository, loaded, old, new, frozen)
    if data["creation"] is not None:
        reference = data["creation"]
        creation = project_creation.load(root, reference["path"])
        if creation.packet.project != loaded.project or creation.seal != reference["seal"]:
            raise FormatError("packet: creation name/seal mismatch")
        marker = f"{creation.directory}/onboarding"
        expected = digest(loaded.directory.encode())
        if (
            paths.get(marker) != expected
            or {"path": marker, "sha256": expected} not in data["inputs"]
            or repository.path(marker, "file").read_bytes() != loaded.directory.encode()
        ):
            raise FormatError("packet: child ownership marker missing, changed or not sealed")
        if owners(repository, creation.directory) != (loaded.directory,):
            raise FormatError("packet: child has multiple or inconsistent outer owners")
        if (
            render_charter(creation.input)
            != repository.path(f"{creation.directory}/targets/PROJECT.md", "file").read_bytes()
            or creation.input.brief.encode()
            != repository.path(f"{creation.directory}/targets/brief.md", "file").read_bytes()
        ):
            raise FormatError("packet: creation after images disagree with sealed input")
    return loaded


def _effects(
    repository: Repository,
    loaded: Loaded,
    old: SourceCatalog,
    new: SourceCatalog,
    frozen: tuple[journal.Image, ...],
) -> None:
    data = loaded.data
    operation, mode, project = data["operation"], data["mode"], loaded.project
    targets = {item["path"] for item in data["images"]}
    allowed = {CATALOG, LOCAL}
    if operation == "understanding-update":
        allowed = {"overview.md"}
    elif operation == "catalog-upgrade":
        allowed = {CATALOG}
    elif operation == "child-derive":
        allowed = {CATALOG}
    if mode in {"A", "B"}:
        allowed |= {"overview.md", "WORKSPACE.md"}
    if project is not None:
        allowed.add(f"projects/{project}/overview.md")
    if targets - allowed:
        raise FormatError(f"packet: forbidden effect targets {sorted(targets - allowed)}")
    if operation in {"understanding-update", "child-derive"} and old.definitions != new.definitions:
        raise FormatError("packet: this operation cannot change definitions")
    if operation == "catalog-upgrade":
        if old.schema_version != 1 or any(
            a.scope.project is None and a.role != "reference" for a in new.associations
        ):
            raise FormatError(
                "catalog upgrade must retain old roles and add workspace references only"
            )
        legacy = f"{loaded.directory}/legacy/sources.v1.toml"
        path = repository.path(legacy, "file")
        changed = next(image for image in frozen if image.path == CATALOG)
        if (
            path.read_bytes() != changed.before
            or {"path": legacy, "sha256": digest(path.read_bytes())} not in data["inputs"]
        ):
            raise FormatError("catalog upgrade: exact sealed legacy bytes missing")
    if mode == "C" or operation == "child-derive":
        for delta in data["association_changes"]:
            scope = Scope.from_data(delta["scope"])
            if scope.project != project and not (
                scope.project is None
                and delta["before"] is None
                and delta["after"] == "reference"
                and operation != "child-derive"
            ):
                raise FormatError("packet: C/derive cannot change existing scope selections")
    for image in frozen:
        if image.path == LOCAL:
            previous = parse_bindings(image.before) if image.before is not None else {}
            current = parse_bindings(image.after)
            if any(current.get(key) != value for key, value in previous.items()) or set(
                current
            ) - set(previous) != {d.id for d in new.definitions} - {d.id for d in old.definitions}:
                raise FormatError("packet: local registration must preserve all old bindings")
        if image.path == "overview.md":
            h = overview(image.after, "overview.md after image")
            prior = overview(image.before, "overview.md before image") if image.before else None
            if (
                h["receipt"] != f"{loaded.directory}/receipt.md"
                or h["revision"] != (prior["revision"] + 1 if prior else 1)
                or h["supersedes"] != (prior["receipt"] if prior else None)
            ):
                raise FormatError("overview: revision/receipt chain disagrees with before/after")
            catalog_effect = next((item for item in frozen if item.path == CATALOG), None)
            catalog_raw = (
                catalog_effect.after
                if catalog_effect
                else repository.path(
                    f"{loaded.directory}/context/sources.toml", "file"
                ).read_bytes()
            )
            if {pin["source"] for pin in h["sources"]} != {
                item["source"] for item in data["inventories"]
            }:
                raise FormatError(
                    "overview pins must cover exactly the reviewed source observations"
                )
            for pin in h["sources"]:
                if pin["catalog_sha256"] != digest(catalog_raw):
                    raise FormatError(
                        "overview catalog pin differs from reviewed exact catalog bytes"
                    )
                definition = new.definition(pin["source"])
                snapshot = repository.path(pin["snapshot"], "file").read_bytes()
                if (
                    digest(snapshot) != pin["snapshot_sha256"]
                    or definition.sha256 != pin["definition_sha256"]
                    or definition.identity != pin["identity"]
                ):
                    raise FormatError("overview: invalid source pin")
                observed = inventory(snapshot, pin["snapshot"])
                if observed["head"] != pin["head"]:
                    raise FormatError("overview: head differs from source observation")
        if image.path == "WORKSPACE.md":
            input_path = f"{loaded.directory}/input/charter.md"
            if input_path not in {item["path"] for item in data["inputs"]}:
                raise FormatError("charter change requires sealed reviewed input")
            change = validate_change_input(decode(repository.path(input_path, "file").read_bytes()))
            if (
                change.charter is None
                or change.resources
                or change.supersedes is not None
                or charter_after(
                    image.before or b"", change.charter, f"{loaded.directory}/receipt.md"
                )
                != image.after
            ):
                raise FormatError("charter image differs from sealed reviewed direction fields")
            before = validate_charter(decode(image.before or b"", "charter before"))
            after = validate_charter(decode(image.after, "charter after"))
            if (
                after.revision != before.revision + 1
                or after.receipt != f"{loaded.directory}/receipt.md"
                or (after.next_step, after.last_handoff) != (before.next_step, before.last_handoff)
            ):
                raise FormatError("packet: charter can change only reviewed direction fields")
    for association in new.associations:
        if association.scope.project is not None and association.scope.project != project:
            repository.project(association.scope.project)


def before_problems(repository: Repository, loaded: Loaded) -> tuple[str, ...]:
    problems = []
    if loaded.data["mode"] in {"A", "B"}:
        children = repository.path("projects", "directory")
        if any(path.is_dir() for path in children.iterdir()):
            problems.append(
                "new-workspace intake root gained a child since preparation; prepare C explicitly"
            )
    for item in loaded.data["preconditions"] + [
        {"path": i["path"], "sha256": i["before"]} for i in loaded.data["images"]
    ]:
        raw = _raw(repository, item["path"])
        if (None if raw is None else digest(raw)) != item["sha256"]:
            problems.append(f"{item['path']}: changed since preview; prepare a new proposal")
    if loaded.data["creation"] is not None:
        creation = project_creation.load(repository.root, loaded.data["creation"]["path"])
        problems.extend(project_creation.check(repository.root, creation))
    return tuple(problems)


def _results(images: list[journal.Image]) -> list[dict[str, Any]]:
    return [
        {
            "path": image.path,
            "before_sha256": None if image.before is None else digest(image.before),
            "after_sha256": digest(image.after),
        }
        for image in images
    ]


def apply_locked(
    root: Path,
    value: str,
    actor: str | None,
    *,
    confirmed: bool = False,
    approval_text: str | None = None,
) -> Outcome:
    """Root lock is held by L3 after checkout locks; no external call occurs here."""
    repository = _repository(root)
    loaded = load(root, value)
    record = f"{loaded.directory}/packet.md"
    receipt = receipt_for(repository, loaded.directory, loaded.seal)
    if journal.pending(repository):
        intent = journal.read_intent(repository)
        if intent.record != record or intent.record_sha256 != loaded.seal:
            raise FormatError(
                "another pending workspace journal exists; replay its exact operation"
            )
        # Ownership and all frozen packet dependencies were checked before forwarding.
        if not confirmed:
            return Outcome("incomplete", loaded, receipt)
        journal.finish(repository)
        return Outcome("recovered", loaded, receipt_for(repository, loaded.directory, loaded.seal))
    if receipt is not None:
        if receipt.disposition == "rejected":
            raise FormatError("packet was rejected; propose anew")
        validate_disposed(repository, loaded, receipt)
        return Outcome("replayed", loaded, receipt)
    problems = before_problems(repository, loaded)
    if not confirmed:
        return Outcome("preview", loaded, problems=problems)
    if not actor or not actor.strip():
        raise FormatError("confirmed actor is required")
    if problems:
        raise FormatError("; ".join(problems))
    at = utc_text(datetime.now(UTC))
    approval = approval_text or "Explicit operator approval of this exact sealed packet"
    effect_images = list(images(repository, loaded))
    creation = None
    if loaded.data["creation"] is not None:
        creation = project_creation.load(root, loaded.data["creation"]["path"])
        effect_images = (
            project_creation._child_images(repository, creation, actor, at) + effect_images
        )
    if creation is not None:
        effect_images.append(
            journal.Image(
                f"{creation.directory}/receipt.md",
                None,
                render_receipt(
                    f"{creation.directory}/packet.md",
                    creation.seal,
                    "applied",
                    actor,
                    at,
                    approval,
                    None,
                    _results(effect_images),
                ),
            )
        )
    effect_images.append(
        journal.Image(
            f"{loaded.directory}/receipt.md",
            None,
            render_receipt(
                record, loaded.seal, "applied", actor, at, approval, None, _results(effect_images)
            ),
        )
    )
    journal.prepare(
        repository,
        journal.Intent(
            "project-create" if creation else "workspace-change",
            record,
            loaded.seal,
            actor,
            at,
            approval,
            tuple(effect_images),
            staging_directory(creation.directory) if creation else None,
        ),
    )
    journal.finish(repository)
    return Outcome("applied", loaded, receipt_for(repository, loaded.directory, loaded.seal))


def validate_disposed(repository: Repository, loaded: Loaded, receipt: Receipt) -> None:
    """Validate archived hashes, never restore or compare today's legitimate targets."""
    expected = {item["path"]: (item["before"], item["after"]) for item in loaded.data["images"]}
    recorded = {path: (before, after) for path, before, after in receipt.results}
    if len(recorded) != len(receipt.results):
        raise FormatError("outer receipt contains duplicate effect paths")
    if receipt.disposition == "rejected" and receipt.approval_text is not None:
        raise FormatError("rejected receipt must not contain approval text")
    if receipt.disposition == "applied":
        if not receipt.approval_text or not receipt.approval_text.strip():
            raise FormatError("v2 applied receipt requires captured approval text")
        if loaded.data["creation"] is not None:
            creation = loaded.data["creation"]
            child = project_creation.load(repository.root, creation["path"])
            business = project_creation._child_images(repository, child, receipt.actor, receipt.at)
            expected.update({image.path: (None, digest(image.after)) for image in business})
            inner = receipt_for(repository, creation["path"], creation["seal"])
            if (
                inner is None
                or inner.disposition != "applied"
                or (inner.actor, inner.at, inner.approval_text)
                != (receipt.actor, receipt.at, receipt.approval_text)
            ):
                raise FormatError("applied outer receipt has no matching child receipt")
            if (
                len({path for path, _, _ in inner.results}) != len(inner.results)
                or {path: (before, after) for path, before, after in inner.results} != expected
            ):
                raise FormatError("child receipt does not cover exact reviewed business effects")
            raw = repository.path(f"{creation['path']}/receipt.md", "file").read_bytes()
            expected[f"{creation['path']}/receipt.md"] = (None, digest(raw))
        if recorded != expected:
            raise FormatError("outer receipt does not cover the exact sealed effects")


def reject_locked(root: Path, value: str, actor: str, reason: str) -> Outcome:
    repository = _repository(root)
    if journal.pending(repository):
        raise FormatError("pending publication must finish before rejection")
    loaded = load(root, value)
    receipt = receipt_for(repository, loaded.directory, loaded.seal)
    if receipt is not None:
        if receipt.disposition != "rejected":
            raise FormatError("applied packet cannot be rejected")
        return Outcome("replayed", loaded, receipt)
    if not actor.strip() or not reason.strip():
        raise FormatError("rejection requires explicit actor and reason")
    raw = render_receipt(
        f"{loaded.directory}/packet.md",
        loaded.seal,
        "rejected",
        actor,
        utc_text(datetime.now(UTC)),
        None,
        reason,
        [],
    )
    write_atomic(repository.path(f"{loaded.directory}/receipt.md"), raw)
    return Outcome("rejected", loaded, receipt_for(repository, loaded.directory, loaded.seal))


def preview(root: Path, loaded: Loaded) -> str:
    repository = Repository(root)
    lines = [
        f"Root: {repository.root}",
        "Scope: workspace",
        f"Mode: {loaded.data['mode'] or loaded.data['operation']}",
        f"Seal: {loaded.seal}",
        f"Rationale: {loaded.data['rationale']}",
    ]
    for action in loaded.data["source_actions"]:
        lines.append(f"Source: {action['source']} {action['action']}")
    for delta in loaded.data["association_changes"]:
        lines.append(
            f"{Scope.from_data(delta['scope']).display}: "
            f"{delta['source']} {delta['before']} -> {delta['after']}"
        )
    for image in images(repository, loaded):
        if image.path == LOCAL:
            lines.append("Local cwd candidates (machine only): " + str(parse_bindings(image.after)))
        else:
            lines.append(
                "".join(
                    difflib.unified_diff(
                        (image.before or b"").decode().splitlines(True),
                        image.after.decode().splitlines(True),
                        fromfile=f"before/{image.path}",
                        tofile=f"after/{image.path}",
                    )
                )
            )
    if loaded.data["creation"]:
        lines.append(project_creation.load(root, loaded.data["creation"]["path"]).body)
    lines.append(
        "Confirmation changes records only. Source write permission, "
        "native launch and scientific authority are separate."
    )
    return "\n".join(lines)


def confirmed_overview(root: Path) -> bytes | None:
    repository = Repository(root)
    path = repository.path("overview.md")
    if not path.exists():
        return None
    raw = repository.path("overview.md", "file").read_bytes()
    h = overview(raw, "overview.md")
    directory = h["receipt"].removesuffix("/receipt.md")
    loaded = load(root, directory, local_optional=True)
    receipt = receipt_for(repository, directory, loaded.seal)
    if (
        receipt is None
        or receipt.disposition != "applied"
        or not any(
            target == "overview.md" and after == digest(raw) for target, _, after in receipt.results
        )
    ):
        raise FormatError(
            "overview.md: candidate has no matching applied receipt; review a fresh proposal"
        )
    validate_disposed(repository, loaded, receipt)
    return raw
