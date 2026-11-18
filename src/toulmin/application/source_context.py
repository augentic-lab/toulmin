"""Native v4: portable scope snapshots and separate ignored local context/receipt.

This extends the existing AoE binding lifecycle; it does not own native sessions,
permissions or a scheduler. Absolute paths appear only in ignored local metadata.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from toulmin.application import native_policy
from toulmin.application.sources import inspect_source_v2
from toulmin.core.atomic import digest, write_atomic
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError
from toulmin.core.schema import utc_text
from toulmin.core.sources import read_source_catalog
from toulmin.core.workspace_onboarding import canonical, json_data, portable, utc
from toulmin.protocols.research_workspace import ResearchState
from toulmin.protocols.workspace_context import WorkspaceState

if TYPE_CHECKING:
    from pathlib import Path

    from toulmin.application.aoe import AoEWorkspace, Binding

MANIFEST_KEYS = {
    "schema_version",
    "scope",
    "token",
    "fingerprint",
    "profile",
    "session_id",
    "provider_session_id",
    "files",
    "working_source",
}
ACK_KEYS = {
    "schema_version",
    "scope",
    "token",
    "fingerprint",
    "session_id",
    "provider_session_id",
    "received_at",
    "manifest_sha256",
}

WORKSPACE_GUIDE = """# Workspace work guide

This conversation owns shared understanding, sources and workspace notes. Children
are optional independent questions with separate goals, scope and acceptance criteria.
Workspace discussion, maintenance and engineering need no Claim, Spec or research gate.

Read the selected source repository's AGENTS.md and follow its code/test/commit rules.
Source availability, working selection, native permission/trust, Chief kickoff and
scientific acceptance are separate choices. A source registration grants no write access.
Use the ignored local.json for the actual records root, selected cwd and ack command.
Relative records paths below belong to the records workspace, never native source cwd.

Work question first: offer the smallest next measurement and append unconfirmed
observations via toulmin workspace note --input ENTRY --root ROOT (root writer lock).
Preserve old entries. Each new entry has a timestamp,
Source/snapshot, Author/model/session (unknown stays unknown), Coverage, Limits,
then nonempty Observation and Next measurement subsections. Qualify formal references
as [[project/C-001]]. Notes are neither confirmed understanding nor Evidence.

For a shared understanding checkpoint: toulmin draft overview --workspace --root ROOT;
fill it and propose toulmin overview --workspace --input FILE --source ID --rationale TEXT
--root ROOT. For substantial engineering: toulmin draft task --workspace --source ID
--root ROOT; fill Goal/Scope/checks/protection/budget, then show task preview. The researcher
reviews it in toulmin decide --workspace --root ROOT. Chief works in separate worktrees;
never redirect a worker into this interactive checkout. Import results as operational
workspace Runs, without automatic merge or scientific promotion.

For a new independent topic: project propose NAME --input FILE --source ID
[--working-source ID] --root ROOT, then researcher decide. No automatic source inheritance,
history move, session launch or permission transfer occurs. Handoff uses the existing
aoe handoff --workspace protocol and explicit researcher application. Agents prepare
proposals and raw output only; the researcher makes administrative and scientific decisions.
"""


def fingerprint(service: AoEWorkspace, resident: str) -> str:
    """Pin exact catalog/selection/checkout, observed content and validated launch intent."""
    source = service._source()
    if source is None:
        raise FormatError("source-backed scope has no selected working source")
    catalog = read_source_catalog(service.root)
    definition = catalog.definition(source.source_id)
    observed = inspect_source_v2(
        service.root,
        source.path,
        observed_at="2000-01-01T00:00:00Z",
        identity=definition.identity if definition.kind == "directory" else None,
    )
    policy = native_policy.load(service.repository).get(service.project)
    # Existing sessions retain actual launch semantics. A matching persisted intent is
    # fingerprint input, never an instruction to reconfigure native permissions.
    intent: dict[str, Any] | None = None
    if policy is not None:
        intent = {"choice": asdict(policy), "matches": policy.matches(service.root, source)}
    return digest(
        canonical(
            {
                "resident": resident,
                "catalog": source.version,
                "definition": definition.sha256,
                "source": source.source_id,
                "cwd": str(source.path),
                "filesystem": observed.filesystem,
                "observation": digest(observed.inventory),
                "permission_intent": intent,
            }
        )
    )


def local_directory(service: AoEWorkspace, binding: Binding) -> Path:
    if binding.token is None:
        raise FormatError("v4 context has no token")
    prefix = "" if service.project is None else f"projects/{service.project}/"
    return service.repository.path(f"{prefix}.aoe/contexts/{binding.token}")


def working_data(binding: Binding) -> dict[str, Any]:
    return {
        "cwd": binding.cwd,
        "source_id": binding.source_id,
        "identity": binding.source_identity,
        "cwd_identity": binding.cwd_identity,
        "catalog_sha256": binding.catalog_sha256,
        "definition_sha256": binding.definition_sha256,
    }


def local_data(service: AoEWorkspace, binding: Binding) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "scope": service.scope.to_data(),
        "token": binding.token,
        "records_root": binding.root,
        "working_source": working_data(binding),
        "ack_command": service._ack_command(str(binding.token)),
    }


def _portable(service: AoEWorkspace, binding: Binding, text: str) -> str:
    for path, replacement in (
        (binding.cwd, "SELECTED_CHECKOUT (see ignored local.json)"),
        (str(service.root), "RECORDS_ROOT (see ignored local.json)"),
    ):
        if path:
            text = text.replace(path, replacement)
    return text


def _notebook(data: bytes, limit: int = 20000) -> bytes:
    tail = data[-limit:]
    if len(data) > limit:
        _, _, tail = tail.partition(b"\n")
    return (
        "# Unconfirmed working notebook\n\nBounded excerpt; not a complete transcript.\n"
        + ("Earlier entries omitted.\n" if len(data) > limit else "")
        + tail.decode("utf-8", "replace")
    ).encode()


def prepare_context(
    service: AoEWorkspace, binding: Binding, state: ResearchState | WorkspaceState
) -> Binding:
    if binding.context and binding.fingerprint == state.fingerprint:
        verify_context(service, binding)
        return binding
    source = service._source()
    if source is None:
        raise FormatError("v4 requires a working source")
    service._check_launch_source(binding, source)
    catalog = read_source_catalog(service.root)
    token = uuid4().hex
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    relative = f"{service.runs}/{stamp}-aoe-context-{token}"
    binding = replace(
        binding,
        context=relative,
        token=token,
        catalog_sha256=source.version,
        definition_sha256=catalog.definition(source.source_id).sha256,
    )
    archive = service.repository.path(relative)
    archive.mkdir()
    hashes = {}
    for name in state.context_files:
        raw = service.repository.path(name, "file").read_bytes()
        target = service.repository.path(f"{relative}/inputs/{name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(target, raw)
        hashes[f"inputs/{name}"] = digest(raw)
    # Shared overview is resident in a child only when its sealed creation explicitly
    # carried it. Use the frozen snapshot, rather than a newer unreviewed replacement.
    if service.project is not None:
        record = service.repository.path(f"projects/{service.project}/runs/creation/creation.md")
        if record.exists():
            document = decode(record.read_bytes(), str(record))
            for item in document.header.get("sources", []):
                if item.get("path") == "overview.md" and item.get("snapshot"):
                    raw = service.repository.path(
                        f"projects/{service.project}/runs/creation/{item['snapshot']}", "file"
                    ).read_bytes()
                    if digest(raw) != item["sha256"]:
                        raise FormatError("pinned shared overview snapshot changed")
                    target = service.repository.path(f"{relative}/inputs/overview.md")
                    write_atomic(target, raw)
                    hashes["inputs/overview.md"] = digest(raw)
    from toulmin.application.aoe import PROJECT_GUIDE, render_scope

    guide = WORKSPACE_GUIDE.encode() if service.project is None else PROJECT_GUIDE.read_bytes()
    write_atomic(archive / "guide.md", guide)
    hashes["guide.md"] = digest(guide)
    card = _portable(service, binding, render_scope(state)).encode()
    write_atomic(archive / "state.md", card)
    hashes["state.md"] = digest(card)
    notebook = service.repository.path(f"{service.runs}/notebook.md")
    if service.project is None and notebook.exists():
        raw = _notebook(service.repository.path(f"{service.runs}/notebook.md", "file").read_bytes())
        write_atomic(archive / "notebook.md", raw)
        hashes["notebook.md"] = digest(raw)
    elif isinstance(state, ResearchState) and state.notebook_excerpt is not None:
        raw = _portable(service, binding, state.notebook_excerpt).encode()
        write_atomic(archive / "notebook.md", raw)
        hashes["notebook.md"] = digest(raw)
    instructions = (
        f"# Native source session context\n\nScope: {service.scope.display}\n"
        f"Selected source: {binding.source_id}; logical identity: {binding.source_identity}.\n\n"
        "Read state.md, guide.md and every inputs/ snapshot listed below before continuing. "
        "They are scoped file-derived state, not a complete conversation transcript or "
        "authorization.\n\n"
        + "\n".join(f"- {name}" for name in hashes)
        + "\n\nThe actual source cwd, records root and executable context-read receipt "
        "command are in "
        "the ignored local.json named in the native delivery message. Read it and execute its "
        "ack_command only after reading all snapshots. Submission is not acknowledgment; "
        "acknowledgment "
        "is not research approval. Do not infer missing native identity.\n\n"
        "Follow the source repository's AGENTS.md for code edits/tests/commits. Keep "
        "native trust and "
        "permission prompts in force. The no-commit rule for records does not govern "
        "source code commits. "
        "Workspace-only discussion and engineering require no child, Claim, Spec or research gate. "
        "For project research, the existing gates and explicit researcher rulings still apply. "
        "Log the smallest next measurement as unconfirmed notes. Offer promotion or "
        "Chief delegation "
        "briefly when useful; prepare drafts only after agreement. Never apply "
        "administrative or scientific "
        "proposals yourself. Fresh-session rebuilding uses files and the applied "
        "handoff; partial native "
        "logs are not a complete transcript. Present state and actions, then wait for "
        "researcher input.\n"
    )
    instructions = _portable(service, binding, instructions)
    write_atomic(archive / "context.md", instructions.encode())
    hashes["context.md"] = digest(instructions.encode())
    local = local_directory(service, binding)
    local.mkdir(parents=True)
    write_atomic(local / "local.json", canonical(local_data(service, binding)))
    manifest = {
        "schema_version": 4,
        "scope": service.scope.to_data(),
        "token": token,
        "fingerprint": state.fingerprint,
        "profile": binding.profile,
        "session_id": binding.session_id,
        "provider_session_id": binding.provider_session_id,
        "files": hashes,
        "working_source": working_data(binding),
    }
    manifest_raw = canonical(manifest)
    write_atomic(local / "manifest.json", manifest_raw)
    if service._state().fingerprint != state.fingerprint:
        raise FormatError(
            "scope state changed while preparing v4 context; archive retained, refresh again"
        )
    binding = replace(
        binding,
        fingerprint=state.fingerprint,
        manifest_sha256=digest(manifest_raw),
        delivery="prepared",
        message="Context prepared; not yet sent",
    )
    service._save(binding)
    return binding


def verify_context(service: AoEWorkspace, binding: Binding) -> None:
    if not binding.context or not binding.session_id:
        raise FormatError("v4 requires prepared context and session")
    try:
        local = local_directory(service, binding)
        raw = service.repository.path(
            (local / "manifest.json").relative_to(service.root).as_posix(), "file"
        ).read_bytes()
        manifest = json_data(raw, str(local / "manifest.json"))
        if (
            digest(raw) != binding.manifest_sha256
            or set(manifest) != MANIFEST_KEYS
            or type(manifest.get("schema_version")) is not int
        ):
            raise FormatError("context manifest hash/fields changed")
        expected = {
            "schema_version": 4,
            "scope": service.scope.to_data(),
            "token": binding.token,
            "fingerprint": binding.fingerprint,
            "profile": binding.profile,
            "session_id": binding.session_id,
            "provider_session_id": binding.provider_session_id,
            "working_source": working_data(binding),
        }
        if any(manifest.get(key) != value for key, value in expected.items()):
            raise FormatError("context manifest scope/pins do not match binding")
        local_raw = service.repository.path(
            (local / "local.json").relative_to(service.root).as_posix(), "file"
        ).read_bytes()
        if json_data(local_raw, "local.json") != local_data(service, binding):
            raise FormatError("machine-local context metadata changed")
        files = manifest["files"]
        if not isinstance(files, dict) or not {"context.md", "state.md", "guide.md"} <= set(files):
            raise FormatError("incomplete v4 context manifest")
        for name, checksum in files.items():
            portable(name, "manifest.files")
            raw = service.repository.path(f"{binding.context}/{name}", "file").read_bytes()
            if digest(raw) != checksum:
                raise FormatError(f"context snapshot changed: {name}")
        if binding.delivery == "acknowledged":
            receipt = json_data(
                service.repository.path(
                    (local / "receipt.json").relative_to(service.root).as_posix(), "file"
                ).read_bytes(),
                "context receipt",
            )
            expected_receipt = {
                key: expected[key]
                for key in (
                    "schema_version",
                    "scope",
                    "token",
                    "fingerprint",
                    "session_id",
                    "provider_session_id",
                )
            }
            expected_receipt["manifest_sha256"] = binding.manifest_sha256
            if (
                type(receipt.get("schema_version")) is not int
                or set(receipt) != ACK_KEYS
                or any(receipt.get(key) != value for key, value in expected_receipt.items())
            ):
                raise FormatError("context-read receipt does not match binding/manifest")
            utc(receipt["received_at"], "context receipt received_at")
    except (OSError, ValueError) as error:
        raise FormatError(f"Invalid context archive: {error}") from error


def acknowledge(service: AoEWorkspace, binding: Binding) -> None:
    source = service._source()
    service._check_launch_source(binding, source)
    if (
        source is None
        or source.version != binding.catalog_sha256
        or read_source_catalog(service.root).definition(source.source_id).sha256
        != binding.definition_sha256
    ):
        raise FormatError("context source pin is stale; refresh before acknowledging")
    receipt = {
        "schema_version": 4,
        "scope": service.scope.to_data(),
        "token": binding.token,
        "fingerprint": binding.fingerprint,
        "session_id": binding.session_id,
        "provider_session_id": binding.provider_session_id,
        "received_at": utc_text(datetime.now(UTC)),
        "manifest_sha256": binding.manifest_sha256,
    }
    path = local_directory(service, binding) / "receipt.json"
    write_atomic(path, canonical(receipt), replace=path.exists())
    service._save(
        replace(
            binding,
            delivery="acknowledged",
            message="Agent acknowledged context; no research approval implied",
        )
    )
