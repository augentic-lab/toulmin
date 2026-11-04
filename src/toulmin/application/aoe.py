"""L3 AoE binding and checked context delivery, without owning agent processes."""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from toulmin.adapters.aoe import AoEClient, AoEError, AoESession
from toulmin.core.atomic import digest, handoff_mutex, write_atomic
from toulmin.core.documents import FormatError
from toulmin.core.repository import Repository
from toulmin.protocols.research_workspace import ResearchState, render_state, research_state


@dataclass(frozen=True)
class Binding:
    root: str
    project: str
    profile: str
    agent: str
    session_id: str | None = None
    provider_session_id: str | None = None
    context: str | None = None
    token: str | None = None
    fingerprint: str | None = None
    manifest_sha256: str | None = None
    delivery: str = "none"
    known_ids: tuple[str, ...] = ()
    message: str = ""


@dataclass(frozen=True)
class WorkspaceView:
    research: ResearchState
    binding: Binding | None
    session: AoESession | None
    context_status: str
    diagnostics: tuple[str, ...] = ()
    context_path: Path | None = None


DELIVERY_STATES = {"none", "prepared", "sending", "submitted", "uncertain", "acknowledged"}


class AoEWorkspace:
    def __init__(self, root: Path, project: str, client: AoEClient | None = None) -> None:
        self.repository = Repository(root)
        self.root = self.repository.root
        self.project = project
        self.directory = self.repository.project(project)
        self.binding_relative = f"projects/{project}/.aoe/binding.json"
        self.binding_path = self.repository.path(self.binding_relative)
        self.client = client

    def _lock(self) -> AbstractContextManager[None]:
        # All project bindings share one lock: one session must not silently serve two projects.
        return handoff_mutex(self.root / ".aoe-binding-writer")

    def _read(self, *, allow_moved: bool = False) -> Binding | None:
        path = self.repository.path(self.binding_relative)
        if not path.exists():
            return None
        try:
            self.repository.path(self.binding_relative, "file")
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or type(value.get("schema_version")) is not int:
                raise ValueError("expected versioned binding mapping")
            if value.pop("schema_version") != 1:
                raise ValueError("unsupported binding version")
            required = set(Binding.__dataclass_fields__)
            if set(value) != required:
                raise ValueError("binding fields differ from version 1")
            for field in ("root", "project", "profile", "agent", "delivery", "message"):
                if not isinstance(value[field], str):
                    raise ValueError(f"invalid binding {field}")
            for field in (
                "context",
                "token",
                "fingerprint",
                "manifest_sha256",
                "session_id",
                "provider_session_id",
            ):
                if value[field] is not None and not isinstance(value[field], str):
                    raise ValueError(f"invalid binding {field}")
            if not isinstance(value["known_ids"], list) or not all(
                isinstance(item, str) and re.fullmatch(r"[0-9a-f]{16}", item)
                for item in value["known_ids"]
            ):
                raise ValueError("invalid pre-creation session IDs")
            value["known_ids"] = tuple(value["known_ids"])
            binding = Binding(**value)
            if binding.project != self.project or (
                not allow_moved and binding.root != str(self.root)
            ):
                raise ValueError("binding belongs to another location; explicitly bind --replace")
            if binding.delivery not in DELIVERY_STATES or binding.agent not in {"codex", "claude"}:
                raise ValueError("invalid binding agent/delivery state")
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", binding.profile):
                raise ValueError("invalid binding profile")
            if binding.session_id is not None and not re.fullmatch(
                r"[0-9a-f]{16}", binding.session_id
            ):
                raise ValueError("invalid binding session ID")
            if binding.context is not None:
                prefix = f"projects/{self.project}/runs/"
                if not binding.context.startswith(prefix) or not re.fullmatch(
                    r"[0-9]{8}T[0-9]{6}Z-aoe-context-[0-9a-f]{32}",
                    binding.context.removeprefix(prefix),
                ):
                    raise ValueError("invalid context archive")
                self.repository.path(binding.context, "directory")
                if not binding.token or not re.fullmatch(r"[0-9a-f]{32}", binding.token):
                    raise ValueError("invalid context receipt token")
                for checksum in (binding.fingerprint, binding.manifest_sha256):
                    if not checksum or not re.fullmatch(r"[0-9a-f]{64}", checksum):
                        raise ValueError("invalid context fingerprint/hash")
            elif (
                any((binding.token, binding.fingerprint, binding.manifest_sha256))
                or binding.delivery != "none"
            ):
                raise ValueError("context metadata without an archive")
            return binding
        except (OSError, UnicodeError, ValueError, TypeError) as error:
            raise FormatError(f"{path}: invalid AoE binding: {error}") from error

    def _save(self, binding: Binding) -> None:
        path = self.repository.path(self.binding_relative)
        path.parent.mkdir(exist_ok=True)
        self.repository.path(self.binding_relative)
        value = {"schema_version": 1, **asdict(binding)}
        write_atomic(path, (json.dumps(value, indent=2) + "\n").encode(), replace=path.exists())

    def _client(self, binding: Binding | None = None) -> AoEClient:
        client = self.client or AoEClient(
            binding.profile if binding else os.environ.get("AGENT_OF_EMPIRES_PROFILE", "main")
        )
        if binding and client.profile != binding.profile:
            raise FormatError("Profile differs from binding; use explicit bind --replace")
        return client

    def _check_session(self, session: AoESession, binding: Binding | None = None) -> None:
        if session.path.absolute() not in {self.root, self.directory}:
            raise FormatError(
                "AoE session path must be this workbench or selected project directory"
            )
        if session.tool not in {"codex", "claude"}:
            raise FormatError("Research bindings require a native codex or claude session")
        if binding and (session.id != binding.session_id or session.tool != binding.agent):
            raise FormatError("AoE session identity/tool differs from saved binding")
        if session.state != "live":
            raise FormatError("Bound session is not live; use open --new-session or bind --replace")

    def _unique(self, profile: str, session_id: str) -> None:
        projects = self.repository.path("projects", "directory")
        for other in projects.iterdir():
            if other.name == self.project or not other.is_dir():
                continue
            candidate = self.repository.path(f"projects/{other.name}/.aoe/binding.json")
            if candidate.exists():
                saved = AoEWorkspace(self.root, other.name)._read(allow_moved=True)
                if saved and saved.profile == profile and saved.session_id == session_id:
                    raise FormatError(f"Session already bound to project {other.name}")

    def _state(self) -> ResearchState:
        state = research_state(self.root, self.project)
        if state.errors:
            raise FormatError(
                "Repair project data before loading context: " + "; ".join(state.errors)
            )
        return state

    def _context(self, binding: Binding, state: ResearchState) -> Binding:
        if binding.context and binding.fingerprint == state.fingerprint:
            self._verify_context(binding)
            return binding
        token = uuid4().hex
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        relative = f"projects/{self.project}/runs/{stamp}-aoe-context-{token}"
        archive = self.repository.path(relative)
        archive.mkdir()
        hashes: dict[str, str] = {}
        for name in state.context_files:
            source = self.repository.path(name, "file")
            data = source.read_bytes()
            target = self.repository.path(f"{relative}/inputs/{name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(target, data)
            hashes[f"inputs/{name}"] = digest(data)
        card = render_state(state)
        write_atomic(archive / "state.md", card.encode())
        hashes["state.md"] = digest(card.encode())
        command = shlex.join(
            [
                sys.executable,
                "-m",
                "toulmin",
                "aoe",
                "ack",
                self.project,
                "--root",
                str(self.root),
                "--token",
                token,
            ]
        )
        instructions = (
            "# Research session context\n\n"
            f"Project: {self.project}\nWorkbench: {self.root}\n\n"
            "Read state.md and the listed input snapshots before continuing. They contain the "
            "current recorded state, not an authorization to apply research decisions. "
            "The recorded next step is historical guidance; compare it with current objects.\n\n"
            + "\n".join(f"- inputs/{name}" for name in state.context_files)
            + "\n\nAfter reading these files, record a context-read receipt with:\n\n```sh\n"
            + command
            + "\n```\n\nThe receipt does not approve research or guarantee comprehension. "
            "Show the supplied state card with ACTIONS as available choices, not action history. "
            "Retrieve further project objects only as needed. Keep model output in runs/; "
            "do not change formal objects, Brief, stage or confirmed handoff without explicit "
            "researcher review. Native permissions remain in force. After displaying the card, "
            "wait for researcher input. Only when the researcher asks to end the research "
            "session, prepare a handoff summary under runs/drafts/ to inspect and apply using "
            "toulmin handoff (or toulmin aoe handoff). Closing a terminal is not confirmation.\n"
        )
        write_atomic(archive / "context.md", instructions.encode())
        hashes["context.md"] = digest(instructions.encode())
        manifest = {
            "schema_version": 1,
            "token": token,
            "fingerprint": state.fingerprint,
            "profile": binding.profile,
            "session_id": binding.session_id,
            "provider_session_id": binding.provider_session_id,
            "files": hashes,
        }
        write_atomic(archive / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
        if self._state().fingerprint != state.fingerprint:
            raise FormatError(
                "Research changed while preparing context; archive retained, retry refresh"
            )
        binding = replace(
            binding,
            context=relative,
            token=token,
            fingerprint=state.fingerprint,
            manifest_sha256=digest((archive / "manifest.json").read_bytes()),
            delivery="prepared",
            message="Context prepared; not yet sent",
        )
        self._save(binding)
        return binding

    def _verify_context(self, binding: Binding) -> None:
        if not binding.context:
            raise FormatError("No prepared context")
        manifest_path = self.repository.path(binding.context + "/manifest.json", "file")
        try:
            raw = manifest_path.read_bytes()
            if digest(raw) != binding.manifest_sha256:
                raise ValueError("context manifest changed")
            manifest = json.loads(raw)
            if (
                not isinstance(manifest, dict)
                or manifest.get("schema_version") != 1
                or manifest.get("token") != binding.token
                or manifest.get("fingerprint") != binding.fingerprint
                or manifest.get("profile") != binding.profile
                or manifest.get("session_id") != binding.session_id
                or manifest.get("provider_session_id") != binding.provider_session_id
                or not isinstance(manifest.get("files"), dict)
            ):
                raise ValueError("context manifest does not match binding")
            files = manifest["files"]
            if not {"state.md", "context.md"}.issubset(files):
                raise ValueError("incomplete context manifest")
            for name, expected in files.items():
                if not isinstance(name, str) or not isinstance(expected, str):
                    raise ValueError("invalid context hash entry")
                path = self.repository.path(binding.context + "/" + name, "file")
                if digest(path.read_bytes()) != expected:
                    raise ValueError(f"context changed: {name}")
            if binding.delivery == "acknowledged":
                receipt_path = self.repository.path(binding.context + "/receipt.json", "file")
                receipt = json.loads(receipt_path.read_bytes())
                if (
                    not isinstance(receipt, dict)
                    or receipt.get("schema_version") != 1
                    or receipt.get("token") != binding.token
                    or receipt.get("fingerprint") != binding.fingerprint
                ):
                    raise ValueError("invalid context-read receipt")
        except (OSError, ValueError, UnicodeError) as error:
            raise FormatError(f"Invalid context archive: {error}") from error

    def _sync_identity(self, binding: Binding, session: AoESession) -> Binding:
        current = session.agent_session_id
        if binding.provider_session_id and not current:
            raise FormatError("Native session identity unavailable; reopen AoE before refreshing")
        if current != binding.provider_session_id:
            binding = replace(
                binding,
                provider_session_id=current,
                context=None,
                token=None,
                fingerprint=None,
                manifest_sha256=None,
                delivery="none",
                message="Native conversation changed; new context required",
            )
            self._save(binding)
        return binding

    def _dispatch(
        self, client: AoEClient, *, expected_token: str | None, resend: bool = False
    ) -> None:
        with self._lock():
            binding = self._read()
            assert binding and binding.session_id is not None and binding.context is not None
            if client.profile != binding.profile:
                raise FormatError("Binding profile changed before delivery; refresh again")
            if expected_token != binding.token:
                return
            if (
                binding.delivery in {"sending", "submitted", "uncertain", "acknowledged"}
                and not resend
            ):
                return
            self._verify_context(binding)
            ready, reason = client.ready(binding.session_id)
            if not ready:
                self._save(replace(binding, message="Context not sent: " + reason))
                return
            observed = client.show(binding.session_id)
            self._check_session(observed, binding)
            if observed.agent_session_id != binding.provider_session_id:
                raise FormatError("Native conversation changed before delivery; run refresh again")
            if self._state().fingerprint != binding.fingerprint:
                raise FormatError("Research changed before delivery; run refresh again")
            binding = replace(
                binding, delivery="sending", message="Delivery started; receipt pending"
            )
            self._save(binding)  # A crash from here must never cause an implicit resend.
        assert binding.session_id is not None and binding.context is not None
        message = (
            f"Toulmin research context {binding.token}. Read "
            f"{self.root / binding.context / 'context.md'} and its snapshots, then run the "
            "context-read receipt command it contains. Present the supplied current state and "
            "available actions, then wait for researcher input. Do not prepare a handoff or "
            "apply research decisions automatically."
        )
        try:
            client.send(binding.session_id, message)
        except (AoEError, OSError) as error:
            outcome, description = "uncertain", str(error)
        else:
            outcome, description = "submitted", "Submitted to AoE; context-read receipt pending"
        # The native agent can acknowledge while send is in flight. Never erase its receipt,
        # or a newer binding/context prepared by another explicit operation.
        with self._lock():
            current = self._read()
            if (
                current
                and current.token == binding.token
                and current.session_id == binding.session_id
                and current.delivery == "sending"
            ):
                self._save(replace(current, delivery=outcome, message=description))

    def status(self, *, check_session: bool = True) -> WorkspaceView:
        state = research_state(self.root, self.project)
        diagnostics: list[str] = []
        session = None
        try:
            binding = self._read()
        except FormatError as error:
            return WorkspaceView(state, None, None, "invalid binding", (str(error),))
        if binding is None:
            return WorkspaceView(state, None, None, "unbound")
        status = binding.delivery
        if binding.context:
            try:
                self._verify_context(binding)
            except FormatError as error:
                diagnostics.append(str(error))
                status = "invalid context"
            if state.fingerprint != binding.fingerprint:
                status = "stale context; refresh required"
        if binding.message:
            diagnostics.append(binding.message)
        if binding.session_id is None:
            status = "creation unresolved; inspect AoE before retrying"
        elif check_session:
            try:
                session = self._client(binding).show(binding.session_id)
                self._check_session(session, binding)
                if session.agent_session_id != binding.provider_session_id:
                    status = "native conversation changed or unknown; refresh required"
                elif not session.agent_session_id and status == "acknowledged":
                    status = "acknowledged; native identity unavailable"
            except (AoEError, OSError, ValueError) as error:
                diagnostics.append(str(error))
                status = "session unavailable; " + status
        return WorkspaceView(
            state,
            binding,
            session,
            status,
            tuple(diagnostics),
            self.root / binding.context / "context.md" if binding.context else None,
        )

    def bind(
        self, session_id: str | None = None, *, replace_existing: bool = False
    ) -> WorkspaceView:
        with self._lock():
            self._state()
            previous = self._read(allow_moved=replace_existing)
            client = self.client or self._client(previous)
            session = client.show(session_id) if session_id else client.current()
            self._check_session(session)
            if (
                previous
                and (
                    previous.session_id != session.id
                    or previous.profile != client.profile
                    or previous.agent != session.tool
                )
                and not replace_existing
            ):
                raise FormatError("Project already bound; use explicit bind --replace")
            self._unique(client.profile, session.id)
            if (
                previous
                and previous.session_id == session.id
                and previous.root == str(self.root)
                and previous.profile == client.profile
                and previous.agent == session.tool
            ):
                if previous.profile != client.profile:
                    raise FormatError("Profile differs; use bind --replace")
                binding = previous
            else:
                binding = Binding(
                    str(self.root), self.project, client.profile, session.tool, session.id
                )
                self._save(binding)
            binding = self._sync_identity(binding, session)
            self._context(binding, self._state())
        # Binding is safe inside a busy native session: it prepares files, never sends into itself.
        return self.status()

    def open(self, agent: str = "codex", *, new_session: bool = False) -> WorkspaceView:
        if agent not in {"codex", "claude"}:
            raise FormatError("Native agent must be codex or claude")
        with self._lock():
            state = self._state()
            binding = self._read()
            client = self._client(binding)
            self._unique(client.profile, "")
            if binding and binding.session_id and new_session:
                available = client.list_sessions()
                old = next((item for item in available if item.id == binding.session_id), None)
                if old is not None and old.state == "live":
                    raise FormatError(
                        "Existing session is live; archive it in AoE before replacement"
                    )
                binding = None
            if binding is None:
                known = tuple(item.id for item in client.list_sessions())
                binding = Binding(
                    str(self.root),
                    self.project,
                    client.profile,
                    agent,
                    known_ids=known,
                    message="Session creation started; do not create a duplicate",
                )
                self._save(binding)
                try:
                    session = client.create(self.root, self.project, agent)
                except AoEError as error:
                    sid = getattr(error, "session_id", None)
                    binding = replace(binding, session_id=sid, message=str(error))
                    self._save(binding)
                    raise
                binding = replace(binding, session_id=session.id, message="Session created")
                self._save(binding)
            elif binding.session_id is None:
                candidates = [
                    item
                    for item in client.list_sessions()
                    if item.id not in binding.known_ids
                    and item.path.absolute() == self.root
                    and item.tool == binding.agent
                    and item.title == f"Toulmin: {self.project}"
                ]
                if len(candidates) != 1:
                    raise FormatError(
                        "Creation outcome unresolved; inspect AoE and use bind --replace "
                        "--session ID. No additional session was created"
                    )
                binding = replace(
                    binding, session_id=candidates[0].id, message="Recovered creation"
                )
                self._save(binding)
            assert binding.session_id is not None
            session = client.show(binding.session_id)
            self._check_session(session, binding)
            self._unique(client.profile, session.id)
            binding = self._sync_identity(binding, session)
            binding = self._context(binding, state)
        self._dispatch(client, expected_token=binding.token)
        return self.status()

    def refresh(self, *, resend: bool = False) -> WorkspaceView:
        with self._lock():
            binding = self._read()
            if not binding or not binding.session_id:
                raise FormatError("No bound session; bind or open first")
            client = self._client(binding)
            session = client.show(binding.session_id)
            self._check_session(session, binding)
            binding = self._sync_identity(binding, session)
            binding = self._context(binding, self._state())
        self._dispatch(client, expected_token=binding.token, resend=resend)
        return self.status()

    def acknowledge(self, token: str) -> WorkspaceView:
        with self._lock():
            binding = self._read()
            if not binding or not binding.context or token != binding.token:
                raise FormatError("Receipt token does not match the current context")
            self._verify_context(binding)
            if self._state().fingerprint != binding.fingerprint:
                raise FormatError("Context is stale; refresh before acknowledging")
            if binding.delivery == "acknowledged":
                return self.status(check_session=False)
            receipt = {
                "schema_version": 1,
                "token": token,
                "fingerprint": binding.fingerprint,
                "at": datetime.now(UTC).isoformat(),
                "meaning": "context-read receipt only",
            }
            path = self.repository.path(binding.context + "/receipt.json")
            write_atomic(
                path, (json.dumps(receipt, indent=2) + "\n").encode(), replace=path.exists()
            )
            self._save(
                replace(
                    binding,
                    delivery="acknowledged",
                    message="Agent acknowledged context; no research approval implied",
                )
            )
        return self.status(check_session=False)
