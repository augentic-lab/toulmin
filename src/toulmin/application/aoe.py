"""L3 AoE binding and checked context delivery, without owning agent processes."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, ExitStack
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from toulmin.adapters.aoe import AoEClient, AoEError, AoESession, settling
from toulmin.adapters.provider_logs import (
    ModelReport,
    SessionUsage,
    reported_model,
    reported_usage,
)
from toulmin.application import native_policy
from toulmin.application.build import external_states
from toulmin.application.sources import (
    ResolvedSource,
    checkout_conflicts,
    checkout_locks,
    filesystem_identity,
    resolve_working_source,
)
from toulmin.application.workspace_sync import git_state, sync_notices
from toulmin.core.atomic import digest, handoff_mutex, write_atomic
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError
from toulmin.core.repository import Repository
from toulmin.core.scope import Scope
from toulmin.core.sources import LOCAL as SOURCE_LOCAL
from toulmin.core.sources import parse_bindings, read_source_catalog
from toulmin.core.workspace import CHARTER_FILE, validate_charter
from toulmin.core.workspace_journal import pending as publication_pending
from toulmin.protocols.research_workspace import ResearchState, render_state, research_state
from toulmin.protocols.workspace_context import (
    WorkspaceState,
    render_workspace,
    workspace_research,
)


@dataclass(frozen=True)
class Binding:
    root: str
    project: str | None  # None: the workspace scope (version 2 only)
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
    # Version 2 (workspace roots) carries scope and title; version 1 keeps the AOE3 form.
    version: int = 1
    title: str | None = None
    # Version 3 pins the native cwd and working-source identity, separate from record root.
    cwd: str | None = None
    source_id: str | None = None
    source_identity: str | None = None
    cwd_identity: str | None = None
    catalog_sha256: str | None = None
    definition_sha256: str | None = None

    @property
    def scope(self) -> Scope:
        return Scope(self.project)


V1_FIELDS = (
    "root",
    "project",
    "profile",
    "agent",
    "session_id",
    "provider_session_id",
    "context",
    "token",
    "fingerprint",
    "manifest_sha256",
    "delivery",
    "known_ids",
    "message",
)
V2_FIELDS = ("scope", "title", *(name for name in V1_FIELDS if name != "project"))
V3_FIELDS = (*V2_FIELDS, "cwd", "source_id", "source_identity", "cwd_identity")
V4_FIELDS = (*V3_FIELDS, "catalog_sha256", "definition_sha256")


@dataclass(frozen=True)
class _LaunchObservation:
    source: ResolvedSource
    directories: native_policy.LaunchPolicy
    inputs: tuple[tuple[str, bytes | None], ...]
    profile: str
    sessions: tuple[tuple[str, AoESession], ...]


@dataclass(frozen=True)
class WorkspaceView:
    research: ResearchState | WorkspaceState
    binding: Binding | None
    session: AoESession | None
    context_status: str
    diagnostics: tuple[str, ...] = ()
    context_path: Path | None = None
    model: ModelReport | None = None  # WX3: as reported by the native session log
    usage: SessionUsage | None = None  # R6: token totals from the same log


DELIVERY_STATES = {"none", "prepared", "sending", "submitted", "uncertain", "acknowledged"}


def scope_state(root: Path, project: str | None) -> ResearchState | WorkspaceState:
    state = (
        workspace_research(root)
        if project is None
        else research_state(root, project, chief=external_states(root, project))
    )
    if project is not None:
        try:
            source = resolve_working_source(root, project)
            if source is not None:
                detail = _source_report(source)
                state = replace(
                    state,
                    fingerprint=digest((state.fingerprint + detail).encode()),
                    notices=(*state.notices, detail.strip()),
                )
        except (OSError, ValueError) as error:
            state = replace(state, errors=(*state.errors, str(error)))
        # The agent guide travels with each project context; an updated guide makes the
        # bound context stale so refresh delivers it (otherwise sessions keep an old copy).
        guide = digest(PROJECT_GUIDE.read_bytes())
        state = replace(state, fingerprint=digest(f"{state.fingerprint}\nguide {guide}".encode()))
    git_report = git_state(root)
    return replace(
        state,
        notices=(
            *state.notices,
            *sync_notices(root),
            *((git_report.line(),) if git_report else ()),
        ),
    )


def _source_report(source: ResolvedSource) -> str:
    """Observe a local checkout without fetching, changing refs or mutating the source."""
    lines = [
        f"Working source: {source.source_id} ({source.kind})",
        f"Native cwd: {source.path}",
        f"Source identity: {source.identity}",
        f"Checkout filesystem identity: {filesystem_identity(source.path)}",
        f"Catalog version: {source.version}",
    ]
    if source.kind == "git":
        for label, args in (
            ("HEAD", ["rev-parse", "HEAD"]),
            ("Branch", ["symbolic-ref", "--short", "-q", "HEAD"]),
            ("Worktree changes", ["status", "--porcelain=v1", "--untracked-files=normal"]),
        ):
            try:
                result = subprocess.run(
                    [
                        "git",
                        "--no-optional-locks",
                        "-c",
                        "core.fsmonitor=false",
                        "-c",
                        "core.hooksPath=/dev/null",
                        "-C",
                        str(source.path),
                        *args,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                    stdin=subprocess.DEVNULL,
                    env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"},
                )
                value = result.stdout[:2_000_000].strip()
                if label == "Worktree changes" and result.returncode == 0:
                    value = str(len(value.splitlines())) if value else "0"
                elif not value:
                    value = (
                        "detached"
                        if label == "Branch" and result.returncode == 1
                        else "unavailable"
                    )
                lines.append(f"{label}: {value}")
            except (OSError, subprocess.TimeoutExpired, UnicodeError):
                lines.append(f"{label}: unavailable")
    else:
        lines.append("Version: unversioned directory (no reproducible revision asserted)")
    return "\n".join(lines) + "\n"


def render_scope(state: ResearchState | WorkspaceState) -> str:
    if isinstance(state, WorkspaceState):
        return render_workspace(state)
    return render_state(state)


PROJECT_GUIDE = Path(__file__).with_name("project-guide.md")


def _command(*args: str) -> str:
    """A toulmin command for the agent's shell, which may not have ``toulmin`` on PATH (W7)."""
    return shlex.join([sys.executable, "-m", "toulmin", *args])


agent_command = _command  # the same form for text other L3 modules send to an agent (R3)


def _prefix_note() -> str:
    return (
        "Run every toulmin command you execute yourself as `"
        + shlex.join([sys.executable, "-m", "toulmin"])
        + " ...`: the bare `toulmin` name may not be on this shell's PATH. Wherever files "
        "or the state card write `toulmin ...` for you to run, use this prefix; "
        "`toulmin decide` is the researcher's own command, so name it as written.\n\n"
    )


class AoEWorkspace:
    """One scope's binding: the workspace (``project`` None) or a named child project."""

    # A just-created native CLI needs a few seconds before its prompt is drawn; one
    # immediate readiness check left the WI8/C5 workspace session without context (R7).
    startup_wait = 30.0
    startup_poll = 1.0

    def __init__(
        self,
        root: Path,
        project: str | None,
        client: AoEClient | None = None,
        *,
        default_profile: str | None = None,
    ) -> None:
        self.repository = Repository(root)
        self.root = self.repository.root
        self.project = project
        self.scope = Scope(project)
        # Legacy roots keep AOE3 version 1 bindings exactly; workspace roots write version 2.
        self.workspace_root = os.path.lexists(self.root / CHARTER_FILE)
        if project is None:
            if not self.workspace_root:
                raise FormatError(
                    f"{self.root}: workspace state not configured (no {CHARTER_FILE}); "
                    "open a project session with aoe open PROJECT"
                )
            self.directory = self.root
            self.binding_relative = ".aoe/binding.json"
        else:
            self.directory = self.repository.project(project)
            self.binding_relative = f"projects/{project}/.aoe/binding.json"
        self.runs = self.scope.records("runs")
        self.binding_path = self.repository.path(self.binding_relative)
        self.client = client
        # Profile for a scope without a saved binding (WX2: environment, then user config).
        self.default_profile = default_profile

    def _source(self) -> ResolvedSource | None:
        return resolve_working_source(self.root, self.project)

    def _cwd(self) -> Path:
        source = self._source()
        return source.path.resolve() if source else self.root

    def _workspace_name(self) -> str:
        path = self.repository.path(CHARTER_FILE, "file")
        return validate_charter(decode(path.read_bytes(), str(path))).name

    def _title(self) -> str:
        """The native session title for a new binding of this scope."""
        if not self.workspace_root:
            return f"Toulmin: {self.project}"
        if self.project is None:
            return f"Workspace: {self._workspace_name()}"
        return f"Project: {self.project} | {self._workspace_name()}"

    def _free_title(self, sessions: tuple[AoESession, ...]) -> str:
        """The scope title, numbered when a session at this root already uses it.

        AoE refuses to add a session whose title and path match an existing one, archived
        and trashed sessions included, so a replacement needs its own title (WI8 W3).
        """
        base = self._title()
        taken = {item.title for item in sessions if item.path.resolve() == self._cwd()}
        previous = self._read(allow_moved=True)
        if previous is not None and previous.version == 4 and previous.title:
            taken.add(previous.title)
        title, number = base, 2
        while title in taken:
            title, number = f"{base} ({number})", number + 1
        return title

    def _new_binding(
        self,
        profile: str,
        agent: str,
        *,
        session_id: str | None = None,
        title: str | None = None,
        known_ids: tuple[str, ...] = (),
        message: str = "",
    ) -> Binding:
        source = self._source()
        if source is not None:
            return Binding(
                str(self.root),
                self.project,
                profile,
                agent,
                session_id,
                known_ids=known_ids,
                message=message,
                version=4 if read_source_catalog(self.root).schema_version == 2 else 3,
                title=title or self._title(),
                cwd=str(source.path.resolve()),
                source_id=source.source_id,
                source_identity=source.identity,
                cwd_identity=filesystem_identity(source.path),
                catalog_sha256=source.version
                if read_source_catalog(self.root).schema_version == 2
                else None,
                definition_sha256=(
                    read_source_catalog(self.root).definition(source.source_id).sha256
                    if read_source_catalog(self.root).schema_version == 2
                    else None
                ),
            )
        if not self.workspace_root:
            return Binding(
                str(self.root), self.project, profile, agent, session_id,
                known_ids=known_ids, message=message,
            )  # fmt: skip
        return Binding(
            str(self.root),
            self.project,
            profile,
            agent,
            session_id,
            known_ids=known_ids,
            message=message,
            version=2,
            title=title or self._title(),
        )

    def _lock(self) -> AbstractContextManager[object]:
        # Checkout → root → child → native binding. The permission callback is outside
        # this entire stack; all observations are revalidated after it returns.
        stack = ExitStack()
        try:
            records_identity = filesystem_identity(self.root)
            source = self._source()
            if source:
                stack.enter_context(
                    checkout_locks(
                        ((str(source.path.resolve()), filesystem_identity(source.path)),)
                    )
                )
                stack.enter_context(handoff_mutex(self.root))
                if self.project is not None:
                    stack.enter_context(handoff_mutex(self.directory))
            stack.enter_context(handoff_mutex(self.root / ".aoe-binding-writer"))
            Repository(self.root)
            if records_identity != filesystem_identity(self.root) or self._source() != source:
                raise FormatError(
                    "source/records selection changed while acquiring launch locks; retry open"
                )
            return stack
        except BaseException:
            stack.close()
            raise

    def _read(self, *, allow_moved: bool = False) -> Binding | None:
        path = self.repository.path(self.binding_relative)
        if not path.exists():
            return None
        try:
            self.repository.path(self.binding_relative, "file")
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and value.get("schema_version") == 4:
                from toulmin.core.workspace_onboarding import json_data

                value = json_data(path.read_bytes(), str(path))
            if not isinstance(value, dict) or type(value.get("schema_version")) is not int:
                raise ValueError("expected versioned binding mapping")
            version = value.pop("schema_version")
            if version == 1:
                if self.project is None:
                    raise ValueError("a version 1 binding is a project binding")
                if set(value) != set(V1_FIELDS):
                    raise ValueError("binding fields differ from version 1")
            elif version in {2, 3, 4}:
                expected = V2_FIELDS if version == 2 else V3_FIELDS if version == 3 else V4_FIELDS
                if set(value) != set(expected):
                    raise ValueError(f"binding fields differ from version {version}")
                if version in {3, 4}:
                    if version == 3 and self.project is None:
                        raise ValueError("a source binding requires a project scope")
                    for field in ("cwd", "source_id", "source_identity", "cwd_identity"):
                        if not isinstance(value[field], str) or not value[field].strip():
                            raise ValueError(f"invalid binding {field}")
                    if not Path(value["cwd"]).is_absolute():
                        raise ValueError("binding cwd is not absolute")
                if Scope.from_data(value.pop("scope")) != self.scope:
                    raise ValueError("scope does not match binding location")
                if not isinstance(value["title"], str) or not value["title"].strip():
                    raise ValueError("invalid binding title")
                value["project"] = self.project
                if version == 4:
                    for field in ("catalog_sha256", "definition_sha256"):
                        if not isinstance(value[field], str) or not re.fullmatch(
                            r"[0-9a-f]{64}", value[field]
                        ):
                            raise ValueError(f"invalid v4 pin {field}")
                    if ".." in Path(value["cwd"]).parts or str(Path(value["cwd"])) != value["cwd"]:
                        raise ValueError("v4 cwd must be canonical without traversal")
                    if not re.fullmatch(r"[0-9]+:[0-9]+", value["cwd_identity"]):
                        raise ValueError("v4 checkout identity must be DEVICE:INODE")
            else:
                raise ValueError("unsupported binding version")
            value["version"] = version
            for field in ("root", "profile", "agent", "delivery", "message"):
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
                prefix = f"{self.runs}/"
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
            if binding.version == 4:
                if len(binding.known_ids) != len(set(binding.known_ids)):
                    raise ValueError("duplicate known session IDs")
                if binding.delivery != "none" and binding.session_id is None:
                    raise ValueError("prepared v4 delivery requires a session ID")
            return binding
        except (OSError, UnicodeError, ValueError, TypeError) as error:
            raise FormatError(f"{path}: invalid AoE binding: {error}") from error

    def _save(self, binding: Binding) -> None:
        path = self.repository.path(self.binding_relative)
        path.parent.mkdir(exist_ok=True)
        self.repository.path(self.binding_relative)
        fields = asdict(binding)
        if binding.version == 1:
            value = {"schema_version": 1, **{name: fields[name] for name in V1_FIELDS}}
        else:
            value = {"schema_version": binding.version, "scope": self.scope.to_data()}
            names = (
                V4_FIELDS
                if binding.version == 4
                else V3_FIELDS
                if binding.version == 3
                else V2_FIELDS
            )
            value.update({name: fields[name] for name in names if name != "scope"})
        write_atomic(path, (json.dumps(value, indent=2) + "\n").encode(), replace=path.exists())

    def _client(self, binding: Binding | None = None) -> AoEClient:
        client = self.client or AoEClient(
            binding.profile
            if binding
            else self.default_profile or os.environ.get("AGENT_OF_EMPIRES_PROFILE", "main")
        )
        if binding and client.profile != binding.profile:
            raise FormatError("Profile differs from binding; use explicit bind --replace")
        return client

    def _check_session(self, session: AoESession, binding: Binding | None = None) -> None:
        source = self._source()
        if binding and binding.version in {3, 4}:
            if (
                source is None
                or source.source_id != binding.source_id
                or source.identity != binding.source_identity
                or str(source.path.resolve()) != binding.cwd
                or filesystem_identity(source.path) != binding.cwd_identity
            ):
                raise FormatError(
                    "Working source changed; archive the old session and explicitly use "
                    "open --new-session (or bind --replace). Native cwd is never changed silently"
                )
            allowed = {Path(binding.cwd)} if binding.cwd else set()
        elif source:
            if binding:
                raise FormatError(
                    "Working source configured after this session; archive it and explicitly "
                    "use open --new-session or bind --replace"
                )
            allowed = {source.path.resolve()}
        else:
            allowed = {self.root, self.directory}
        if session.path.resolve() not in allowed:
            raise FormatError(
                "AoE session path differs from the selected working source"
                if source
                else (
                    "AoE session path must be this workbench or selected project directory"
                    if self.project is not None
                    else "A workspace session's path must be the workbench root"
                )
            )
        if session.tool not in {"codex", "claude"}:
            raise FormatError("Research bindings require a native codex or claude session")
        if binding and (session.id != binding.session_id or session.tool != binding.agent):
            raise FormatError("AoE session identity/tool differs from saved binding")
        if session.state != "live":
            raise FormatError("Bound session is not live; use open --new-session or bind --replace")

    def _unique(self, profile: str, session_id: str) -> None:
        """One native session serves at most one scope in this workbench (F08)."""
        if self.project is not None and self.workspace_root:
            candidate = self.repository.path(".aoe/binding.json")
            if candidate.exists():
                saved = AoEWorkspace(self.root, None)._read(allow_moved=True)
                if saved and saved.profile == profile and saved.session_id == session_id:
                    raise FormatError("Session already bound to the workspace")
        projects = self.repository.path("projects", "directory")
        for other in projects.iterdir():
            if other.name == self.project or not other.is_dir() or other.name.startswith("."):
                continue
            candidate = self.repository.path(f"projects/{other.name}/.aoe/binding.json")
            if candidate.exists():
                saved = AoEWorkspace(self.root, other.name)._read(allow_moved=True)
                if saved and saved.profile == profile and saved.session_id == session_id:
                    raise FormatError(f"Session already bound to project {other.name}")

    def _state(self) -> ResearchState | WorkspaceState:
        if publication_pending(self.repository):
            from toulmin.core.workspace_journal import incomplete_child

            if self.project is not None and incomplete_child(self.repository) == self.project:
                raise FormatError(
                    "creation incomplete; replay the exact confirmed workspace publication"
                )
            raise FormatError(
                "workspace publication journal pending; replay "
                "exact apply before native context writes"
            )
        state = scope_state(self.root, self.project)
        if self._source() is not None and read_source_catalog(self.root).schema_version == 2:
            from toulmin.application.source_context import fingerprint

            state = replace(state, fingerprint=fingerprint(self, state.fingerprint))
        if state.errors:
            subject = "workspace" if self.project is None else "project"
            raise FormatError(
                f"Repair {subject} data before loading context: " + "; ".join(state.errors)
            )
        return state

    def _ack_command(self, token: str) -> str:
        selector = ["--workspace"] if self.project is None else [self.project]
        return _command(
            "aoe", "ack", *selector, "--root", str(self.root), "--token", token
        )  # fmt: skip

    def _context(self, binding: Binding, state: ResearchState | WorkspaceState) -> Binding:
        if binding.version == 4:
            from toulmin.application.source_context import prepare_context

            return prepare_context(self, binding, state)
        if binding.context and binding.fingerprint == state.fingerprint:
            self._verify_context(binding)
            return binding
        token = uuid4().hex
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        relative = f"{self.runs}/{stamp}-aoe-context-{token}"
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
        card = render_scope(state)
        write_atomic(archive / "state.md", card.encode())
        hashes["state.md"] = digest(card.encode())
        if self.project is not None:
            # R2: the compact agent guide travels with each project context, so workspaces
            # created before it existed get it too and agents need not read protocols.md.
            guide = PROJECT_GUIDE.read_bytes()
            write_atomic(archive / "guide.md", guide)
            hashes["guide.md"] = digest(guide)
            if isinstance(state, ResearchState) and state.notebook_excerpt is not None:
                notebook = state.notebook_excerpt.encode()
                write_atomic(archive / "notebook.md", notebook)
                hashes["notebook.md"] = digest(notebook)
        command = self._ack_command(token)
        if self.project is None:
            instructions = self._workspace_instructions(state, command)
        else:
            instructions = self._project_instructions(binding, state, command)
        write_atomic(archive / "context.md", instructions.encode())
        hashes["context.md"] = digest(instructions.encode())
        manifest: dict[str, object] = {"schema_version": binding.version}
        if binding.version >= 2:
            manifest["scope"] = self.scope.to_data()
        if binding.version == 3:
            manifest["working_source"] = {
                "cwd": binding.cwd,
                "source_id": binding.source_id,
                "identity": binding.source_identity,
                "cwd_identity": binding.cwd_identity,
            }
        manifest.update(
            {
                "token": token,
                "fingerprint": state.fingerprint,
                "profile": binding.profile,
                "session_id": binding.session_id,
                "provider_session_id": binding.provider_session_id,
                "files": hashes,
            }
        )
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

    def _project_instructions(
        self, binding: Binding, state: ResearchState | WorkspaceState, command: str
    ) -> str:
        scope = ""
        if self.workspace_root and binding.version >= 2:
            scope = (
                f"Scope: Project: {self.project}. WORKSPACE.md is the shared charter, supplied "
                "read-only; workspace discussion, sibling projects and creation sources are not "
                f"resident (read them only on request). Save outputs under {self.runs}/. Scope "
                "is recorded data, not filesystem isolation.\n\n"
            )
        return (
            "# Research session context\n\n"
            f"Project: {self.project}\nWorkbench: {self.root}\n\n"
            + scope
            + self._source_instructions(binding)
            + _prefix_note()
            + "Read state.md, guide.md (how this project session works: the loop, what you may "
            "write and a `toulmin draft` command for every proposal) and the listed input "
            "snapshots before continuing. They contain the current recorded state, not an "
            "authorization to apply research decisions. The recorded next step is historical "
            "guidance; compare it with current objects.\n\n"
            + "\n".join(f"- inputs/{name}" for name in state.context_files)
            + (
                "\n- notebook.md (bounded, unconfirmed working notes)"
                if isinstance(state, ResearchState) and state.notebook_excerpt is not None
                else ""
            )
            + "\n\nAfter reading these files, record a context-read receipt with:\n\n```sh\n"
            + command
            + "\n```\n\nThe receipt does not approve research or guarantee comprehension. "
            "Show the supplied state card with ACTIONS as available choices, not action history. "
            "Retrieve further project objects only as needed. Keep model output in runs/; "
            "do not change formal objects, Brief, stage or confirmed handoff without explicit "
            "researcher review. Native permissions remain in force. After displaying the card, "
            "wait for researcher input.\n\n"
            + self._loop_instructions()
            + "Only when the researcher asks to end the research "
            "session, save a structured summary under runs/drafts/ according to "
            "roles/scribe.md. Run "
            + _command(
                "aoe", "handoff", str(self.project), "--root", str(self.root), "--input", "SUMMARY"
            )
            + " with --input pointing to that summary to generate an archived handoff draft. "
            "Show its contents and the exact returned runs/<archive>/draft.md path for "
            "researcher review. Only that generated draft is the --apply input; never "
            "suggest applying a research proposal or the source summary. Do not apply it "
            "yourself; the researcher decides it with `toulmin decide`. Closing a terminal is "
            "not confirmation.\n"
        )

    def _source_instructions(self, binding: Binding) -> str:
        source = self._source()
        if source is None:
            return ""
        return (
            "## Working source and research records\n\n"
            + _source_report(source)
            + f"\nThe native working directory is {source.path}; research records are under "
            f"{self.root / 'projects' / str(self.project)}. Read and follow the code "
            "repository's AGENTS.md and local development rules for source edits, tests and "
            "code commits. The workspace AGENTS.md and guide.md govern research records; "
            "their no-commit rule applies to the records workspace, not the external code "
            "repository. Keep native permission and trust prompts in force. Use absolute "
            "record paths and --root for Toulmin commands. Relative paths in guide.md "
            "refer to this research workspace, never the external cwd. Source and shared resource "
            "descriptions are distinct; neither creates Evidence or proves a revision. "
            "Chief uses separate worktrees; never redirect its implementation into this "
            "interactive checkout.\n\n"
            "The confirmed overview (when supplied) describes this existing project. Recent "
            "notebook context is unconfirmed working material, not an applied handoff or a "
            "complete transcript. Ask what the researcher wants to continue or investigate; "
            "do not force a stage or rewrite established goals. Help with concrete discussion, "
            "small experiments and code changes. For a substantial development task, offer a "
            "draft-task proposal for researcher's decide; it needs no first Claim.\n\n"
        )

    def _loop_instructions(self) -> str:
        """The project research loop (H6), now detailed in guide.md (R2)."""
        name, root = str(self.project), str(self.root)
        draft = _command("draft", "KIND", name, "--root", root)
        status = _command("status", name, "--root", root)
        dry_run = _command("review", name, "--root", root, "--dry-run")
        return (
            "Research loop (design section 7; guide.md has the steps and formats). Work "
            "question first: suggest the smallest next measurement and log it in "
            "runs/notebook.md; promote ideas to objects only when the researcher agrees, and "
            "ask briefly when a result or conclusion looks ready. The "
            f"GATES lines in state.md and `{status}` show G1/G2 readiness as information.\n"
            f"- `{draft}` writes every skeleton under {self.runs}/drafts/: claim, evidence, "
            "objection, decision, exploration, spec, and the proposals ruling (--object, "
            "repeatable for one ruling on several objects; --status), intake (--run R-NNN), "
            "review, brief (--section) and stage (--to). Fill every <fill: …> value, then move "
            f"the file, filename unchanged, to {self.runs}/proposals/; the researcher decides it "
            "with `toulmin decide` in their own terminal. Never create objects or write "
            "outcome files yourself.\n"
            "- A ruling may carry a status and its Response or Ruling text together; one "
            "Decision may back one ruling for several objects of one kind.\n"
            f"- Check a review round with `{dry_run}` before requesting it; only the "
            "researcher's apply starts it. Never review your own work.\n"
            "- Stage changes are the researcher's ruling: propose them (a Decision draft plus a "
            "stage proposal). Never edit PROJECT.md stage or status fields yourself.\n\n"
        )

    def _workspace_instructions(self, state: ResearchState | WorkspaceState, command: str) -> str:
        root = str(self.root)
        handoff = _command("aoe", "handoff", "--workspace", "--root", root, "--input", "SUMMARY")
        propose = _command("workspace", "propose", "--root", root, "--input", "runs/drafts/FILE")
        return (
            "# Workspace session context\n\n"
            f"Scope: Workspace\nWorkbench: {root}\n\n"
            "Read state.md and the listed input snapshots before continuing. They contain the "
            "current recorded workspace state, not an authorization to change it. The recorded "
            "next step is historical guidance; compare it with current files.\n\n"
            + "\n".join(f"- inputs/{name}" for name in state.context_files)
            + "\n\nAfter reading these files, record a context-read receipt with:\n\n```sh\n"
            + command
            + "\n```\n\nThe receipt does not approve research or guarantee comprehension. "
            "Show the supplied state card with ACTIONS as available choices, not action "
            "history, then wait for researcher input.\n\n"
            + _prefix_note()
            + "This session is the shared workspace. Projects have their own sessions; do not "
            "work on a project's objects here, and do not create a project. Scope is recorded "
            "data, not filesystem isolation.\n\n"
            "Keep everything you produce in root runs/. Record a bounded exploration as "
            "runs/<UTC stamp>-activity-<32 hex>/activity.md (workspace-formats.md section 5): "
            "keep the researcher's corrections and feedback in their own words under "
            "Researcher feedback, and state capture coverage honestly (full, selected, summary "
            "or unknown, with limits). You see only part of the native conversation; never "
            "claim a complete transcript.\n\n"
            "Direction, constraints, focus and shared resource descriptions change only "
            "through a reviewed packet: write a change input under runs/drafts/ (section 7.1), "
            f"run {propose}, show the packet path and diff, and say it awaits the researcher's "
            "decision with `toulmin decide` in their own terminal. Never apply or reject a "
            "packet yourself. When discussion settles a direction, constraint or resource, "
            "offer to prepare such a proposal; do not wait to be asked. A registered resource "
            "is not Evidence for any Claim.\n\n"
            "Only when the researcher asks to end the session, save a structured summary "
            "under runs/drafts/ (section 8: Done, Confirmed changes, Pending ideas, Open "
            f"questions; next step in metadata) and run {handoff} with --input pointing to it. "
            "List in confirmed_changes the receipt of every workspace change applied since the "
            "last handoff and do not call those changes pending; if the draft output warns "
            "that some are not cited, correct the summary and draft again. "
            "Show the returned runs/<archive>/draft.md path and contents. Only that generated "
            "draft is the --apply input: never a change input, a packet or the summary. Do not "
            "apply it yourself; the researcher decides it with `toulmin decide`. Pending ideas "
            "stay pending. Closing a terminal is not confirmation.\n"
        )

    def _verify_context(self, binding: Binding) -> None:
        if binding.version == 4:
            from toulmin.application.source_context import verify_context

            verify_context(self, binding)
            return
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
                or manifest.get("schema_version") != binding.version
                or (binding.version >= 2 and manifest.get("scope") != self.scope.to_data())
                or (
                    binding.version == 3
                    and manifest.get("working_source")
                    != {
                        "cwd": binding.cwd,
                        "source_id": binding.source_id,
                        "identity": binding.source_identity,
                        "cwd_identity": binding.cwd_identity,
                    }
                )
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
                    or receipt.get("schema_version") != binding.version
                    or (binding.version >= 2 and receipt.get("scope") != self.scope.to_data())
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
            self._checkout_available(client, observed.id)
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
        if binding.version == 4:
            local = self.directory / ".aoe/contexts" / str(binding.token) / "local.json"
            message += f" Machine-local cwd/receipt command: read {local}."
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
        state = scope_state(self.root, self.project)
        try:
            if self._source() is not None and read_source_catalog(self.root).schema_version == 2:
                from toulmin.application.source_context import fingerprint

                state = replace(state, fingerprint=fingerprint(self, state.fingerprint))
        except (OSError, ValueError) as error:
            state = replace(
                state,
                errors=(*state.errors, str(error)),
                fingerprint=digest((state.fingerprint + str(error)).encode()),
            )
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
                if binding.session_id is None:
                    raise FormatError("Context has no bound native session")
                session = self._client(binding).show(binding.session_id)
                self._check_session(session, binding)
                if session.agent_session_id != binding.provider_session_id:
                    status = "native conversation changed or unknown; refresh required"
                elif not session.agent_session_id and status == "acknowledged":
                    status = "acknowledged; native identity unavailable"
            except (AoEError, OSError, ValueError) as error:
                diagnostics.append(str(error))
                status = "session unavailable; " + status
        native = session.agent_session_id if session else None
        return WorkspaceView(
            state,
            binding,
            session,
            status,
            tuple(diagnostics),
            self.root / binding.context / "context.md" if binding.context else None,
            reported_model(binding.agent, native or binding.provider_session_id),
            reported_usage(binding.agent, native or binding.provider_session_id),
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
                raise FormatError(
                    ("Project" if self.project else "Workspace")
                    + " already bound; use explicit bind --replace"
                )
            self._unique(client.profile, session.id)
            self._checkout_available(client, session.id)
            if (
                previous
                and previous.session_id == session.id
                and previous.root == str(self.root)
                and previous.profile == client.profile
                and previous.agent == session.tool
                and (previous.version in {3, 4} or self._source() is None)
            ):
                if previous.profile != client.profile:
                    raise FormatError("Profile differs; use bind --replace")
                self._check_session(session, previous)
                binding = previous
            else:
                if previous is not None and previous.version == 4:
                    if previous.session_id and (
                        previous.session_id != session.id or previous.profile != client.profile
                    ):
                        old_client = (
                            client
                            if previous.profile == client.profile
                            else AoEClient(previous.profile)
                        )
                        old = next(
                            (
                                item
                                for item in old_client.list_sessions()
                                if item.id == previous.session_id
                            ),
                            None,
                        )
                        if old is not None and old.state == "live":
                            raise FormatError(
                                "Existing session is live; archive it in AoE before replacement"
                            )
                    history = self.repository.path(self.binding_relative).parent / "bindings"
                    history.mkdir(exist_ok=True)
                    write_atomic(history / f"{uuid4().hex}.json", self.binding_path.read_bytes())
                binding = self._new_binding(
                    client.profile, session.tool, session_id=session.id, title=session.title
                )
                self._save(binding)
            binding = self._sync_identity(binding, session)
            self._context(binding, self._state())
        # Binding is safe inside a busy native session: it prepares files, never sends into itself.
        return self.status()

    def open(
        self,
        agent: str | None = None,
        *,
        new_session: bool = False,
        fallback_agent: str = "codex",
        codex_sandbox: str | None = None,
        choose_codex_sandbox: Callable[[ResolvedSource, bool], str] | None = None,
    ) -> WorkspaceView:
        """Reuse the bound session, or create one with ``agent``.

        Without ``agent`` a new session uses the replaced binding's agent, else
        ``fallback_agent``. An existing binding keeps its own agent.
        """
        if agent is not None and agent not in {"codex", "claude"}:
            raise FormatError("Native agent must be codex or claude")
        if fallback_agent not in {"codex", "claude"}:
            raise FormatError("Native agent must be codex or claude")
        if codex_sandbox is not None:
            native_policy.validate_mode(codex_sandbox)
        choice = None
        if codex_sandbox is None and choose_codex_sandbox is not None:
            choice = self._choose_launch_policy(
                agent, new_session, fallback_agent, choose_codex_sandbox
            )
            if choice is not None:
                _, codex_sandbox = choice
        with self._lock():
            if choice is not None:
                self._revalidate_launch_choice(choice[0])
            state = self._state()
            binding = self._read()
            client = self._client(binding)
            self._unique(client.profile, "")
            replaced = binding
            created = False
            binding = self._opening_binding(binding, client, new_session)
            if binding is None:
                agent = agent or (replaced.agent if replaced else fallback_agent)
                available = client.list_sessions()
                self._checkout_available(client)
                binding = self._new_binding(
                    client.profile,
                    agent,
                    title=self._free_title(available),
                    known_ids=tuple(item.id for item in available),
                    message="Session creation started; do not create a duplicate",
                )
                sandbox = self._launch_policy(
                    binding, codex_sandbox, require_choice=choose_codex_sandbox is not None
                )
                self._checkout_available(client)
                if replaced is not None and replaced.version == 4:
                    history = self.repository.path(self.binding_relative).parent / "bindings"
                    history.mkdir(exist_ok=True)
                    write_atomic(history / f"{uuid4().hex}.json", self.binding_path.read_bytes())
                self._save(binding)
                try:
                    if binding.version == 1:
                        assert self.project is not None
                        session = client.create(self.root, self.project, agent)
                    elif binding.version in {3, 4}:
                        # Only opted-in launches add a sandbox argument. Keeping it out
                        # of the binding preserves v1/v2/v3 and manually configured AoE
                        # sessions. AoE persists --extra-args for resume/restart.
                        options = {"codex_sandbox": sandbox} if sandbox == "workspace-write" else {}
                        session = client.create(
                            Path(binding.cwd) if binding.cwd else self.root,
                            self.project,
                            agent,
                            title=binding.title,
                            add_directory=self.root,
                            **options,
                        )
                    else:
                        session = client.create(self.root, self.project, agent, title=binding.title)
                except AoEError as error:
                    sid = getattr(error, "session_id", None)
                    binding = replace(binding, session_id=sid, message=str(error))
                    self._save(binding)
                    raise
                binding = replace(binding, session_id=session.id, message="Session created")
                self._save(binding)
                created = True
            else:
                self._check_reused_policy(binding, codex_sandbox)
            if binding.session_id is None:
                candidates = self._creation_candidates(client, binding)
                if len(candidates) != 1:
                    retry = (
                        "; if AoE shows no such session, rerun open with --new-session"
                        if not candidates
                        else ""
                    )
                    raise FormatError(
                        "Creation outcome unresolved; inspect AoE and use bind --replace "
                        f"--session ID{retry}. No additional session was created"
                    )
                binding = replace(
                    binding, session_id=candidates[0].id, message="Recovered creation"
                )
                self._save(binding)
            assert binding.session_id is not None
            session = client.show(binding.session_id)
            self._check_session(session, binding)
            self._checkout_available(client, session.id)
            self._unique(client.profile, session.id)
            binding = self._sync_identity(binding, session)
            binding = self._context(binding, self._state() if binding.version == 4 else state)
        if created:
            assert binding.session_id is not None
            self._await_startup(client, binding.session_id)
        self._dispatch(client, expected_token=binding.token)
        return self.status()

    def _opening_binding(
        self, binding: Binding | None, client: AoEClient, new_session: bool
    ) -> Binding | None:
        """Read-only replacement eligibility, shared by observation and publication."""
        if binding and binding.session_id and new_session:
            old = next((s for s in client.list_sessions() if s.id == binding.session_id), None)
            if old is not None and old.state == "live":
                raise FormatError("Existing session is live; archive it in AoE before replacement")
            return None
        if (
            binding
            and binding.session_id is None
            and new_session
            and not self._creation_candidates(client, binding)
        ):
            # Retry only when the unresolved launch left no candidate (F06).
            return None
        return binding

    def _choose_launch_policy(
        self,
        agent: str | None,
        new_session: bool,
        fallback_agent: str,
        choose: Callable[[ResolvedSource, bool], str],
    ) -> tuple[_LaunchObservation, str] | None:
        with self._lock():
            binding = self._read()
            client = self._client(binding)
            if self._opening_binding(binding, client, new_session) is not None:
                return None
            selected = agent or (binding.agent if binding else fallback_agent)
            source = self._source()
            if selected != "codex" or source is None:
                return None
            inputs = self._launch_inputs()
            if self._read() != binding or self._source() != source:
                raise FormatError(
                    "Native launch inputs changed while observing permissions; retry open"
                )
            saved = native_policy.load(self.repository).get(self.project)
            if saved is not None and saved.matches(self.root, source):
                return None
            self._unique(client.profile, "")
            self._checkout_available(client)
            observed = self._launch_observation(binding, client, source)
            if observed.inputs != inputs:
                raise FormatError(
                    "Native launch files changed while observing permissions; retry open"
                )
        # Both the workspace binding and checkout flocks are released here. Nothing
        # has been published, so another open/decision can finish while the user thinks.
        requested = choose(source, saved is not None)
        native_policy.validate_mode(requested)
        return observed, requested

    def _launch_inputs(self) -> tuple[tuple[str, bytes | None], ...]:
        paths = (
            self.binding_relative,
            "sources.toml",
            "tools/sources.local.toml",
            native_policy.LOCAL,
        )
        inputs = []
        for relative in paths:
            path = self.repository.path(relative)
            image = self.repository.path(relative, "file").read_bytes() if path.exists() else None
            inputs.append((relative, image))
        return tuple(inputs)

    def _launch_observation(
        self, binding: Binding | None, client: AoEClient, source: ResolvedSource
    ) -> _LaunchObservation:
        inputs = self._launch_inputs()
        sessions = {
            (profile, session.id): session
            for profile, session in client.list_all_sessions()
            if session.path.resolve() == source.path.resolve()
        }
        if binding and binding.session_id:
            for session in client.list_sessions():
                if session.id == binding.session_id:
                    sessions[(client.profile, session.id)] = session
        return _LaunchObservation(
            source,
            native_policy.LaunchPolicy.choice("inherit", self.root, source),
            inputs,
            client.profile,
            tuple((profile, sessions[profile, sid]) for profile, sid in sorted(sessions)),
        )

    def _revalidate_launch_choice(self, observed: _LaunchObservation) -> None:
        # Recheck existing Repository guarantees after the unlocked interval; never
        # resolve a replacement symlink into a newly authorized records root.
        Repository(self.root)
        if filesystem_identity(self.root) != observed.directories.records_identity:
            raise FormatError(
                "Research records directory changed while choosing launch permissions"
            )
        source = self._source()
        if (
            source is None
            or source != observed.source
            or not observed.directories.matches(self.root, source)
        ):
            raise FormatError("Working source changed while choosing launch permissions")
        binding = self._read()
        current = self._launch_observation(binding, self._client(binding), source)
        if current != observed:
            raise FormatError(
                "Native launch state changed while choosing permissions; retry open to review "
                "the current state. This choice was not saved or launched"
            )

    def _check_reused_policy(self, binding: Binding, requested: str | None) -> None:
        if requested is None:
            # Reuse never reads or rewrites native launch settings, even for old/manual
            # sessions whose args Toulmin has never inspected.
            return
        source = self._source()
        if binding.agent != "codex" or source is None:
            raise FormatError("--codex-sandbox requires an external-source Codex project session")
        # A local preference is not proof of the args of an existing/manual session.
        # Even a repeated flag cannot be represented as changing that session's policy.
        raise FormatError(
            "Existing session permissions are preserved. Omit --codex-sandbox to reuse it; "
            "to select launch permissions, archive it in AoE, then open --new-session "
            "--codex-sandbox " + requested
        )

    def _launch_policy(
        self,
        binding: Binding,
        requested: str | None,
        *,
        require_choice: bool,
    ) -> str | None:
        source = self._source()
        if binding.agent != "codex" or source is None:
            if requested is not None:
                raise FormatError(
                    "--codex-sandbox requires an external-source Codex project session"
                )
            return None
        self._check_launch_source(binding, source)
        observed = native_policy.LaunchPolicy.choice("inherit", self.root, source)
        saved = native_policy.load(self.repository).get(self.project)
        matches = saved is not None and saved.matches(self.root, source)
        if requested is None and matches:
            assert saved is not None
            return saved.sandbox
        if requested is None:
            if saved is not None or require_choice:
                raise FormatError(
                    "Native launch policy is stale or changed during open; retry open to "
                    "choose --codex-sandbox workspace-write or inherit"
                )
            # Compatibility for direct application callers: no implicit opt-in.
            return None
        policy = replace(observed, sandbox=requested)
        current_source = self._source()
        self._check_launch_source(binding, current_source)
        assert current_source is not None
        if not policy.matches(self.root, current_source):
            raise FormatError(
                "Research records directory changed while choosing launch permissions; "
                "retry open and review --codex-sandbox for the current directories"
            )
        native_policy.save(self.repository, self.project, policy)
        return policy.sandbox

    def _check_launch_source(self, binding: Binding, source: ResolvedSource | None) -> None:
        if (
            source is None
            or binding.cwd != str(source.path.resolve())
            or binding.source_id != source.source_id
            or binding.source_identity != source.identity
            or binding.cwd_identity != filesystem_identity(source.path)
        ):
            raise FormatError(
                "Working source changed while choosing launch permissions; retry open "
                "and review --codex-sandbox for the current code and records directories"
            )

    def _await_startup(self, client: AoEClient, session_id: str) -> None:
        """Poll a new session until it can take input, outside the binding lock.

        Bounded: refusals only the researcher can clear (a menu, typed input) end the wait at
        once, and ``_dispatch`` repeats the full check under the lock before sending.
        """
        deadline = time.monotonic() + self.startup_wait
        while True:
            ready, reason = client.ready(session_id)
            if ready or not settling(reason) or time.monotonic() >= deadline:
                return
            time.sleep(self.startup_poll)

    def _checkout_available(self, client: AoEClient, own: str | None = None) -> None:
        if self._source() is None:
            return
        cwd = self._cwd()
        local = self.repository.path(SOURCE_LOCAL)
        if local.exists():
            bindings = parse_bindings(local.read_bytes())
            source = self._source()
            assert source is not None
            checkout_conflicts(bindings, source.source_id, cwd, filesystem_identity(cwd))
        identity = filesystem_identity(cwd)
        conflicts = []
        for profile, session in client.list_all_sessions():
            same = session.path.resolve() == cwd
            if not same and session.path.is_dir():
                same = filesystem_identity(session.path) == identity
            if (
                same
                and session.state == "live"
                and (session.id != own or profile != client.profile)
            ):
                conflicts.append(f"{profile}/{session.id}")
        if conflicts:
            raise FormatError(
                f"Working checkout {cwd} already has a live native session: "
                + ", ".join(conflicts)
                + (
                    "; archive it before opening another. Local "
                    "coordination cannot isolate arbitrary external writers"
                )
            )

    def _creation_candidates(self, client: AoEClient, binding: Binding) -> list[AoESession]:
        """New sessions that match an unresolved creation's path, tool and title."""
        return [
            item
            for item in client.list_sessions()
            if item.id not in binding.known_ids
            and item.path.resolve() == (Path(binding.cwd) if binding.cwd else self.root)
            and item.tool == binding.agent
            and item.title == (binding.title or f"Toulmin: {self.project}")
        ]

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

    def bound_session(self) -> Binding | None:
        """The saved binding when it names a session; read-only, no AoE call."""
        with self._lock():
            binding = self._read()
        return binding if binding and binding.session_id else None

    def notify(self, message: str) -> tuple[bool, str]:
        """Send one line to the bound native session when it is ready (R3); else say why.

        A notice is not context delivery: the binding, its context and receipt are unchanged,
        and nothing is sent into a busy session or over the researcher's unfinished input.
        """
        if "\n" in message or not message.strip():
            raise FormatError("A session notice is one nonempty line")
        binding = self.bound_session()
        if binding is None:
            return False, "no bound session"
        assert binding.session_id is not None
        try:
            client = self._client(binding)
            session = client.show(binding.session_id)
            self._check_session(session, binding)
            ready, reason = client.ready(binding.session_id)
            if not ready:
                return False, reason
            client.send(binding.session_id, message)
        except (AoEError, FormatError, OSError) as error:
            return False, str(error)
        return True, f"sent to {binding.agent} session {binding.session_id}"

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
            if binding.version == 4:
                from toulmin.application.source_context import acknowledge

                if binding.session_id is None:
                    raise FormatError("Context has no bound native session")
                session = self._client(binding).show(binding.session_id)
                self._check_session(session, binding)
                if session.agent_session_id != binding.provider_session_id:
                    raise FormatError("Native identity changed; refresh before acknowledging")
                acknowledge(self, binding)
                return self.status(check_session=False)
            receipt: dict[str, object] = {"schema_version": binding.version}
            if binding.version >= 2:
                receipt["scope"] = self.scope.to_data()
            receipt |= {
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
