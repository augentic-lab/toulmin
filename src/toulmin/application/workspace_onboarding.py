"""WO3 inspection/coordinated publication, keeping external observations in L3."""

import json
import os
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from toulmin.application.sources import (
    SourceInspection,
    SourceSelectionRequired,
    checkout_conflicts,
    checkout_locks,
    filesystem_identity,
    inspect_source_v2,
    resolve_source,
    validate_directory,
)
from toulmin.core import workspace_journal as journal
from toulmin.core.atomic import digest, handoff_mutex
from toulmin.core.codec import decode, encode
from toulmin.core.creation import INPUT_ORDER, validate_creation_input
from toulmin.core.documents import FormatError
from toulmin.core.proposals import charter_after, validate_change_input
from toulmin.core.render import header
from toulmin.core.repository import Repository
from toulmin.core.schema import utc_text
from toulmin.core.scope import WORKSPACE, Scope
from toulmin.core.sources import (
    CATALOG,
    LOCAL,
    InspectionPolicy,
    SourceAssociation,
    SourceCatalog,
    SourceDefinition,
    parse_bindings,
    read_source_catalog,
    render_bindings,
    render_source_catalog,
)
from toulmin.core.workspace_onboarding import HEADINGS, Loaded, canonical, overview
from toulmin.protocols import workspace_onboarding as protocol

DEFAULT_ORIGIN = {"kind": "model", "model": None, "session_id": None}


def _bytes(repository: Repository, path: str) -> bytes | None:
    target = repository.path(path)
    return repository.path(path, "file").read_bytes() if target.exists() else None


def _base(root: Path) -> tuple[Repository, SourceCatalog, dict[str, tuple[str, str]]]:
    repository = Repository(root)
    if journal.pending(repository):
        raise FormatError("workspace journal pending; replay its exact confirmed operation")
    catalog = read_source_catalog(root)
    if catalog.schema_version != 2:
        raise FormatError(
            f"{root}: v1 catalog remains active; propose toulmin source upgrade --root {root} first"
        )
    local = _bytes(repository, LOCAL)
    return repository, catalog, parse_bindings(local) if local is not None else {}


def _source(
    root: Path,
    path: Path,
    catalog: SourceCatalog,
    bindings: dict[str, tuple[str, str]],
    at: str,
    source_id: str | None,
    register: str | None,
    inspection: InspectionPolicy | None = None,
) -> tuple[SourceDefinition, SourceInspection, str]:
    path = validate_directory(root, path)
    checkout = (str(path), filesystem_identity(path))
    known = (
        catalog.definition(source_id)
        if source_id
        else next((d for d in catalog.definitions if bindings.get(d.id) == checkout), None)
    )
    if known is not None:
        if inspection is not None and inspection != known.inspection:
            raise FormatError("inspection selection differs from immutable registered definition")
        inspection = known.inspection
    inspected = inspect_source_v2(root, path, observed_at=at, inspection=inspection)
    if source_id and register:
        raise FormatError("source reuse and registration flags conflict")
    matched = [
        d
        for d in catalog.definitions
        if bindings.get(d.id) == (str(inspected.path), inspected.filesystem)
    ]
    if source_id:
        definition = catalog.definition(source_id)
        if bindings.get(source_id) != (str(inspected.path), inspected.filesystem):
            raise FormatError(
                f"{source_id}: missing/stale local binding; "
                f"explicitly source bind ID PATH before intake"
            )
    elif register:
        if any(d.id == register for d in catalog.definitions):
            raise FormatError(f"{register}: duplicate source ID; choose a new ID or checked reuse")
        if matched:
            raise FormatError(f"checkout already belongs to {matched[0].id}; reuse its ID")
        definition = SourceDefinition(
            register,
            2 if inspection is not None else 1,
            inspected.kind,
            "git-roots-v1" if inspected.kind == "git" else "directory-anchors-v1",
            inspected.identity,
            inspection,
        )
    elif matched:
        if len(matched) != 1:
            raise SourceSelectionRequired(
                "multiple exact source IDs; select --source-id ID explicitly"
            )
        definition = matched[0]
    else:
        identities = [
            d
            for d in catalog.definitions
            if d.kind == inspected.kind and d.identity == inspected.identity
        ]
        if len(identities) > 1:
            raise SourceSelectionRequired(
                "multiple logical source IDs; select --source-id or --register-source"
            )
        for possible in identities:
            saved = bindings.get(possible.id)
            if saved is None or not Path(saved[0]).is_dir():
                raise FormatError(
                    f"{possible.id}: local binding unavailable; use source "
                    f"bind, or explicitly register a distinct checkout"
                )
        generated = "source-" + uuid.uuid4().hex[:16]
        if any(d.id == generated for d in catalog.definitions):
            raise FormatError("generated source ID collision; retry")
        definition = SourceDefinition(
            generated,
            2 if inspection is not None else 1,
            inspected.kind,
            "git-roots-v1" if inspected.kind == "git" else "directory-anchors-v1",
            inspected.identity,
            inspection,
        )
    reuse = definition in catalog.definitions
    checkout_conflicts(bindings, definition.id, inspected.path, inspected.filesystem)
    if reuse:
        if definition.kind != inspected.kind or (
            definition.kind == "git" and definition.identity != inspected.identity
        ):
            raise FormatError(f"{definition.id}: explicit source identity mismatch")
        if definition.kind == "directory":
            observed = json.loads(inspected.inventory)
            observed["identity"] = definition.identity
            inspected = replace(
                inspected, identity=definition.identity, inventory=canonical(observed)
            )
    return definition, inspected, "reuse" if reuse else "register"


def _associate(catalog: SourceCatalog, scope: Scope, source: str, role: str) -> SourceCatalog:
    associations = list(catalog.associations)
    if role == "working":
        associations = [
            replace(a, role="reference") if a.scope == scope and a.role == "working" else a
            for a in associations
        ]
    associations = [a for a in associations if (a.scope, a.source) != (scope, source)]
    associations.append(SourceAssociation(scope, source, role))
    return replace(catalog, associations=tuple(associations))


def _input(project: str) -> bytes:
    values: list[Any] = [
        1,
        "project-creation-input",
        project,
        None,
        f"What should be understood or improved in {project}?",
        "An explicit project request during existing-repository intake.",
        ["Inspect the linked source and agree one independent measurement."],
        [],
        [],
        ["Research question, included scope and acceptance experiment remain provisional."],
        f"Understand the requested {project} direction.",
        "Source inspection executes no scripts and grants no source write permission.",
        "Review provisional framing and choose the smallest next measurement.",
        [],
        [],
        [],
    ]
    return (
        header(list(zip(INPUT_ORDER, values, strict=True)))
        + "## Problem\nExplicit requested project; framing needs researcher review.\n\n"
        "## Minimal validation experiment\nNo acceptance measurement agreed yet; choose "
        "one before drawing conclusions.\n"
    ).encode()


def _overview(
    directory: str,
    at: str,
    body: str | None,
    catalog: SourceCatalog,
    observations: list[tuple[SourceDefinition, SourceInspection, str]],
    previous: bytes | None,
    catalog_raw: bytes | None = None,
) -> bytes:
    pins = []
    for definition, observed, _ in observations:
        value = json.loads(observed.inventory)
        pins.append(
            {
                "source": definition.id,
                "catalog_sha256": digest(
                    catalog_raw if catalog_raw is not None else render_source_catalog(catalog)
                ),
                "definition_sha256": definition.sha256,
                "identity": definition.identity,
                "snapshot": f"{directory}/inventory/{definition.id}.json",
                "snapshot_sha256": digest(observed.inventory),
                "head": value["head"],
            }
        )
    prior = overview(previous, "overview.md") if previous is not None else None
    metadata = [
        ("schema_version", 1),
        ("kind", "workspace-overview"),
        ("scope", Scope().to_data()),
        ("revision", prior["revision"] + 1 if prior else 1),
        ("receipt", f"{directory}/receipt.md"),
        ("source", DEFAULT_ORIGIN),
        ("recorded_at", at),
        ("coverage", "Bounded read-only inventory of selected text at the pinned source revisions"),
        (
            "limits",
            [
                "No source scripts or checks executed",
                (
                    "Bounded inventory; generated, credential and "
                    "ignored material excluded; absence is not established"
                ),
            ],
        ),
        ("sources", pins),
        ("supersedes", prior["receipt"] if prior else None),
    ]
    if body is None:
        body = "\n".join(
            f"## {heading}\n{content}\n"
            for heading, content in zip(
                HEADINGS,
                (
                    "Provisional inventory: "
                    + ", ".join(d.id for d, _, _ in observations)
                    + "; inspect pinned files before making structural conclusions.",
                    (
                        "Entry points are unknown; read the source "
                        "repository's instructions and selected files."
                    ),
                    "Only bounded text was inspected; runtime behavior remains untested.",
                    "No scripts or checks executed during intake.",
                    (
                        "Purpose, behavior, acceptance criteria and "
                        "deployment constraints need further discussion."
                    ),
                ),
                strict=True,
            )
        )
    raw = (header(metadata) + body).encode()
    overview(raw, "proposed workspace overview")
    return raw


def _note(
    directory: str, at: str, observations: list[tuple[SourceDefinition, SourceInspection, str]]
) -> bytes:
    lines = ["# Workspace notebook", "Entries are unconfirmed; this packet note is provisional."]
    for definition, _inspected, _ in observations:
        lines.append(
            f"\n## {at} — Repository inventory\n- Source: {definition.id}; snapshot: "
            f"{directory}/inventory/{definition.id}.json\n"
            "- Author: model; model: unknown; native session: unknown\n"
            "- Coverage: selected textual files; generated files and credentials excluded\n"
            "- Limits: bounded inspection; no scripts or tests executed\n\n"
            "### Observation\nA bounded inventory is available; structure and behavior "
            "remain provisional.\n\n"
            "### Next measurement\nRead repository instructions and identify the "
            "smallest useful measurement.\n"
        )
    return "\n".join(lines).encode()


def prepare(
    root: Path,
    source: Path | None = None,
    project: str | None = None,
    *,
    mode: str | None = None,
    work_at: Path | None = None,
    project_input: bytes | None = None,
    workspace_body: str | None = None,
    project_overview: bytes | None = None,
    charter_input: bytes | None = None,
    source_id: str | None = None,
    register_source: str | None = None,
    working_source_id: str | None = None,
    register_working_source: str | None = None,
    operation: str = "onboarding",
    scope: Scope = WORKSPACE,
    sources: tuple[str, ...] = (),
    working_source: str | None = None,
    working: bool = False,
    rationale: str = "Review bounded intake and explicit scope choices",
    inspection: InspectionPolicy | None = None,
) -> protocol.Outcome:
    if inspection is not None and (source is None or work_at is not None):
        raise FormatError("explicit inspection selection requires SOURCE without --work-at")
    repository, before_catalog, bindings = _base(root)
    old_catalog = _bytes(repository, CATALOG)
    old_local = _bytes(repository, LOCAL)
    charter = _bytes(repository, "WORKSPACE.md")
    prior_overview = _bytes(repository, "overview.md")
    if project is not None and os.path.lexists(repository.path(f"projects/{project}")):
        raise FormatError(
            f"projects/{project}: occupied, even if empty or damaged; choose a new child name"
        )
    at = utc_text(datetime.now(UTC))
    kind = {
        "onboarding": "onboard",
        "understanding-update": "understanding",
        "source-change": "source",
        "child-derive": "derive",
    }[operation]
    directory = (
        f"runs/{datetime.fromisoformat(at).strftime('%Y%m%dT%H%M%SZ')}-{kind}-{uuid.uuid4().hex}"
    )
    catalog = before_catalog
    observations = []
    if source is not None:
        first = _source(root, source, catalog, bindings, at, source_id, register_source, inspection)
        observations.append(first)
        definition, observed, action = first
        if action == "register":
            catalog = replace(catalog, definitions=(*catalog.definitions, definition))
            bindings[definition.id] = (str(observed.path), observed.filesystem)
        if mode in {"A", "B"}:
            catalog = _associate(
                catalog, Scope(), definition.id, "reference" if work_at else "working"
            )
        elif not any(a.source == definition.id for a in catalog.associated(Scope())):
            catalog = _associate(catalog, Scope(), definition.id, "reference")
        if operation == "source-change":
            catalog = _associate(
                catalog, scope, definition.id, "working" if working else "reference"
            )
        elif project is not None:
            catalog = _associate(
                catalog, Scope(project), definition.id, "reference" if work_at else "working"
            )
        if work_at is not None:
            if (
                source == work_at
                or source.absolute().is_relative_to(work_at.absolute())
                or work_at.absolute().is_relative_to(source.absolute())
            ):
                raise FormatError("source and target must be distinct non-overlapping directories")
            second = _source(
                root, work_at, catalog, bindings, at, working_source_id, register_working_source
            )
            observations.append(second)
            definition, observed, action = second
            if action == "register":
                catalog = replace(catalog, definitions=(*catalog.definitions, definition))
                bindings[definition.id] = (str(observed.path), observed.filesystem)
            if mode in {"A", "B"}:
                catalog = _associate(catalog, Scope(), definition.id, "working")
            elif not any(a.source == definition.id for a in catalog.associated(Scope())):
                catalog = _associate(catalog, Scope(), definition.id, "reference")
            if project is not None:
                catalog = _associate(catalog, Scope(project), definition.id, "working")
    else:
        for source_name in sources:
            if operation == "child-derive":
                if not any(a.source == source_name for a in catalog.associated(Scope())):
                    raise FormatError("derivation source must be workspace-associated")
                catalog.definition(source_name)
                catalog = _associate(
                    catalog,
                    Scope(project),
                    source_name,
                    "working" if source_name == working_source else "reference",
                )
                continue
            resolved = resolve_source(root, None, source_name)
            definition = catalog.definition(source_name)
            source_observation = inspect_source_v2(
                root,
                resolved.path,
                observed_at=at,
                identity=definition.identity if definition.kind == "directory" else None,
                inspection=definition.inspection,
            )
            observations.append((definition, source_observation, "reuse"))
            if operation == "child-derive":
                catalog = _associate(
                    catalog,
                    Scope(project),
                    source_name,
                    "working" if source_name == working_source else "reference",
                )
        if operation == "source-change":
            if working_source is None or not any(
                a.source == working_source for a in catalog.associated(scope)
            ):
                raise FormatError(
                    "working selection must name a source already associated with that scope"
                )
            catalog = _associate(catalog, scope, working_source, "working")
    effects = {}
    after_catalog = render_source_catalog(catalog)
    if after_catalog != old_catalog and operation != "understanding-update":
        effects[CATALOG] = after_catalog
    if source is not None:
        local = render_bindings(bindings)
        if old_local is None or bindings != parse_bindings(old_local):
            effects[LOCAL] = local
    artifacts: dict[str, bytes] = {}
    inputs = []
    preconditions = [
        {"path": path, "sha256": None if raw is None else digest(raw)}
        for path, raw in (
            (CATALOG, old_catalog),
            (LOCAL, old_local),
            ("WORKSPACE.md", charter),
            ("overview.md", prior_overview),
        )
    ]
    inventories = []
    for definition, inspected, _ in observations:
        path = f"inventory/{definition.id}.json"
        artifacts[path] = inspected.inventory
        inventories.append(
            {"source": definition.id, "path": path, "sha256": digest(inspected.inventory)}
        )
    if operation == "understanding-update" or mode in {"A", "B"}:
        effects["overview.md"] = _overview(
            directory,
            at,
            workspace_body,
            catalog,
            observations,
            prior_overview,
            old_catalog if operation == "understanding-update" else after_catalog,
        )
    if project_overview is not None:
        if not project_overview.strip() or b"<fill:" in project_overview:
            raise FormatError("project overview must be filled and nonempty")
        effects[f"projects/{project}/overview.md"] = project_overview
    if charter_input is not None:
        change = validate_change_input(decode(charter_input, "charter input"))
        if change.charter is None or change.resources or change.supersedes is not None:
            raise FormatError("intake charter input may change charter fields only")
        assert charter is not None
        effects["WORKSPACE.md"] = charter_after(charter, change.charter, f"{directory}/receipt.md")
        artifacts["input/charter.md"] = charter_input
        inputs.append({"path": f"{directory}/input/charter.md", "sha256": digest(charter_input)})
    if workspace_body is not None:
        artifacts["input/workspace-overview.md"] = workspace_body.encode()
        inputs.append(
            {
                "path": f"{directory}/input/workspace-overview.md",
                "sha256": digest(workspace_body.encode()),
            }
        )
    child_bytes = None
    if project is not None:
        original_input = project_input or _input(project)
        document = decode(original_input, "project input")
        value = validate_creation_input(document)
        if value.project != project or value.supersedes is not None:
            raise FormatError(
                "project input must match new child name and cannot supersede another creation"
            )
        document.header["sources"] = [
            *document.header["sources"],
            *({"path": f"{directory}/{item['path']}", "coverage": "full"} for item in inventories),
        ]
        child_bytes = encode(document)
        artifacts["input/project-original.md"] = original_input
        inputs.append(
            {"path": f"{directory}/input/project-original.md", "sha256": digest(original_input)}
        )
    notes = None
    if mode == "C":
        artifacts["notes.md"] = _note(directory, at, observations)
        notes = {"path": "notes.md", "sha256": digest(artifacts["notes.md"])}
    data = {
        "schema_version": 2,
        "kind": "workspace-onboarding",
        "operation": operation,
        "scope": Scope().to_data(),
        "created": at,
        "origin": DEFAULT_ORIGIN,
        "mode": mode,
        "project": project,
        "creation": None,
        "catalog_version": 2,
        "inputs": inputs,
        "preconditions": preconditions,
        "images": [],
        "inventories": inventories,
        "source_actions": [
            {"source": d.id, "action": action, "definition_sha256": d.sha256}
            for d, _, action in observations
        ]
        + (
            [
                {
                    "source": name,
                    "action": "reuse",
                    "definition_sha256": catalog.definition(name).sha256,
                }
                for name in sources
            ]
            if operation == "child-derive"
            else []
        ),
        "association_changes": protocol.deltas(before_catalog, catalog),
        "notes": notes,
        "rationale": rationale,
    }
    locks = tuple(bindings.values())
    with checkout_locks(locks), handoff_mutex(repository.root):
        if (
            _bytes(repository, CATALOG),
            _bytes(repository, LOCAL),
            _bytes(repository, "WORKSPACE.md"),
            _bytes(repository, "overview.md"),
        ) != (old_catalog, old_local, charter, prior_overview):
            raise FormatError("workspace context changed during preparation; retry")
        return protocol.seal_packet(
            root, directory, data, effects, artifacts, project_input=child_bytes
        )


def _packet_bindings(repository: Repository, loaded: Loaded) -> dict[str, tuple[str, str]]:
    image = next((item for item in loaded.data["images"] if item["path"] == LOCAL), None)
    if image is not None:
        return parse_bindings(repository.path(image["after_image"], "file").read_bytes())
    token = loaded.directory.rsplit("-", 1)[1]
    path = repository.path(f"tools/wo-{token}-before.local.toml")
    return parse_bindings(path.read_bytes()) if path.exists() else {}


def apply(
    root: Path,
    value: str,
    actor: str | None,
    *,
    confirmed: bool = False,
    expect_seal: str | None = None,
    approval_text: str | None = None,
) -> protocol.Outcome:
    repository = Repository(root)
    loaded = protocol.load(root, value)
    if expect_seal is not None and expect_seal != loaded.seal:
        raise FormatError("expected seal differs from exact reviewed packet; review again")
    bindings = _packet_bindings(repository, loaded)
    if not confirmed:
        return protocol.apply_locked(root, value, None, confirmed=False)
    with checkout_locks(tuple(bindings.values())), handoff_mutex(repository.root):
        loaded = protocol.load(root, value)
        from toulmin.protocols.workspace_change import receipt_for

        receipt = receipt_for(repository, loaded.directory, loaded.seal)
        if not journal.pending(repository) and receipt is None:
            problems = protocol.before_problems(repository, loaded)
            if problems:
                raise FormatError("; ".join(problems))
            for item in loaded.data["inventories"]:
                frozen = repository.path(f"{loaded.directory}/{item['path']}", "file").read_bytes()
                observation = json.loads(frozen)
                path, filesystem = bindings[item["source"]]
                definition = protocol.catalog_after(root, loaded).definition(item["source"])
                current = inspect_source_v2(
                    root,
                    Path(path),
                    observed_at=observation["observed_at"],
                    identity=observation["identity"]
                    if observation["kind"] == "directory"
                    else None,
                    inspection=definition.inspection,
                )
                if current.filesystem != filesystem or current.inventory != frozen:
                    raise FormatError(
                        f"{path}: source HEAD/content/checkout changed since preview; propose anew"
                    )
        return protocol.apply_locked(
            root, value, actor, confirmed=True, approval_text=approval_text
        )


def reject(
    root: Path, value: str, actor: str, reason: str, *, expect_seal: str | None = None
) -> protocol.Outcome:
    repository = Repository(root)
    with handoff_mutex(repository.root):
        loaded = protocol.load(root, value)
        if expect_seal is not None and expect_seal != loaded.seal:
            raise FormatError("expected seal differs from reviewed packet")
        return protocol.reject_locked(root, value, actor, reason)


def upgrade(root: Path) -> protocol.Outcome:
    repository = Repository(root)
    with handoff_mutex(repository.root):
        if journal.pending(repository):
            raise FormatError(
                "pending workspace journal; finish it before proposing catalog conversion"
            )
        old = read_source_catalog(root)
        if old.schema_version != 1:
            raise FormatError("source upgrade requires an active v1 catalog; nothing converted")
        from toulmin.protocols.workspace_change import receipt_for

        for pattern in ("*-onboard-*", "*-context-*"):
            for folder in repository.path("runs", "directory").glob(pattern):
                if not (folder / "seal").exists():
                    continue
                relative = folder.relative_to(repository.root).as_posix()
                seal = (folder / "seal").read_text().strip()
                if receipt_for(repository, relative, seal) is None:
                    raise FormatError(
                        f"{relative}: undecided v1 source/onboarding "
                        f"packet; decide it before upgrade"
                    )
        at = utc_text(datetime.now(UTC))
        directory = (
            f"runs/{datetime.fromisoformat(at).strftime('%Y%m%dT%H%M%SZ')}"
            f"-catalog-{uuid.uuid4().hex}"
        )
        raw = repository.path(CATALOG, "file").read_bytes()
        new = SourceCatalog(
            2,
            old.definitions,
            (
                *old.associations,
                *(
                    SourceAssociation(Scope(), definition.id, "reference")
                    for definition in old.definitions
                ),
            ),
        )
        try:
            after_catalog = render_source_catalog(new)
        except FormatError as error:
            raise FormatError(
                "v1 source identity cannot be represented by strict v2. Keep the v1 "
                "catalog active; its original provenance is unchanged. No identity "
                "normalization or replacement is permitted: " + str(error)
            ) from error
        legacy = f"{directory}/legacy/sources.v1.toml"
        data = {
            "schema_version": 2,
            "kind": "workspace-onboarding",
            "operation": "catalog-upgrade",
            "scope": Scope().to_data(),
            "created": at,
            "origin": DEFAULT_ORIGIN,
            "mode": None,
            "project": None,
            "creation": None,
            "catalog_version": 2,
            "inputs": [{"path": legacy, "sha256": digest(raw)}],
            "preconditions": [
                {"path": CATALOG, "sha256": digest(raw)},
                {"path": legacy, "sha256": digest(raw)},
            ],
            "images": [],
            "inventories": [],
            "source_actions": [],
            "association_changes": protocol.deltas(old, new),
            "notes": None,
            "rationale": (
                "Opt-in v2 conversion: preserve exact legacy catalog and all old roles. "
                "New workspace associations "
                "are references only. Future writes require v2-capable Toulmin; no "
                "automatic downgrade."
            ),
        }
        return protocol.seal_packet(
            root,
            directory,
            data,
            {CATALOG: after_catalog},
            {"legacy/sources.v1.toml": raw},
        )
