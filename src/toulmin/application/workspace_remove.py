"""Remove a whole workspace: its AoE sessions, its folder and its list entry.

Researcher-invoked only. The plan is read-only and lists everything that would be lost; the
removal refuses while a Chief task or a session is still working, and it never touches code
repositories, Chief state or git remotes. AoE sessions go to AoE's trash, not a purge.
"""

import json
import os
import shutil
import tarfile
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from toulmin.adapters.aoe import AoEError, AoESession
from toulmin.adapters.chief import ChiefClient, ChiefTaskMissing, load_config
from toulmin.application.workspace_sync import GitState, git_state
from toulmin.cli.registry import charter_name, normal
from toulmin.core.workspace import CHARTER_FILE
from toulmin.protocols.build import build_facts

Kind = Literal["workspace", "legacy"]
FINISHED = {"done", "abandoned"}  # Chief task states that hold no running worker
GONE = {"trashed"}  # AoE states already removed by `aoe remove`


class RemovalError(ValueError):
    """The folder is not something this command may delete."""


class Sessions(Protocol):
    profile: str

    def list_sessions(self) -> tuple[AoESession, ...]: ...

    def show(self, session_id: str) -> AoESession: ...

    def remove(self, session_id: str) -> None: ...


@dataclass(frozen=True)
class Session:
    profile: str
    id: str
    title: str
    state: str
    status: str | None


@dataclass(frozen=True)
class Task:
    project: str | None  # None: found in the Chief home by its paths, not a build record
    id: str
    state: str | None


@dataclass(frozen=True)
class RemovalPlan:
    root: Path
    name: str
    kind: Kind
    projects: tuple[str, ...]
    files: int
    size: int
    git: GitState | None
    sessions: tuple[Session, ...]
    tasks: tuple[Task, ...]
    blockers: tuple[str, ...]
    losses: tuple[str, ...]  # what exists nowhere else once the folder is gone
    notes: tuple[str, ...] = field(default=())


def _kind(root: Path) -> tuple[str, Kind]:
    if os.path.lexists(root / CHARTER_FILE):
        name = charter_name(root)
        if name is None:
            raise RemovalError(f"{root}: {CHARTER_FILE} is unreadable; inspect it by hand")
        return name, "workspace"
    if (
        (root / "AGENTS.md").is_file()
        and (root / "framework/formats.md").is_file()
        and (root / "projects").is_dir()
    ):
        return root.name, "legacy"
    raise RemovalError(f"{root}: not a Toulmin workspace (no {CHARTER_FILE}); nothing removed")


def checked_root(path: Path) -> Path:
    """An existing, real workspace folder that is not a home or system directory."""
    root = normal(path)
    if root.is_symlink():
        raise RemovalError(f"{root}: a symbolic link; give the folder it points to")
    if not root.is_dir():
        raise RemovalError(f"{root}: no such folder")
    protected = {Path("/"), normal(Path.home())}
    if root in protected or root.parent == root:
        raise RemovalError(f"{root}: refusing to remove a home or system directory")
    return root


def _projects(root: Path) -> tuple[str, ...]:
    folder = root / "projects"
    if folder.is_symlink() or not folder.is_dir():
        return ()
    return tuple(
        sorted(
            path.name
            for path in folder.iterdir()
            if path.is_dir() and not path.is_symlink() and (path / "PROJECT.md").is_file()
        )
    )


def _usage(root: Path) -> tuple[int, int]:
    files = size = 0
    for directory, folders, names in os.walk(root):
        for name in (*folders, *names):
            try:
                info = os.lstat(os.path.join(directory, name))
            except OSError:
                continue
            files += name in names
            size += info.st_size
    return files, size


def _bindings(root: Path, projects: tuple[str, ...]) -> tuple[dict[str, str], list[str]]:
    """Session ID → profile from saved bindings; read loosely so a damaged one is reported."""
    found: dict[str, str] = {}
    notes = []
    for relative in (
        ".aoe/binding.json",
        *(f"projects/{name}/.aoe/binding.json" for name in projects),
    ):
        path = root / relative
        if not path.exists():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            session, profile = value.get("session_id"), value.get("profile")
            if session is not None and not (isinstance(session, str) and isinstance(profile, str)):
                raise ValueError("session_id/profile not text")
        except (OSError, ValueError, AttributeError) as error:
            notes.append(f"{relative}: binding not read ({error}); sessions found by path only")
            continue
        if session:
            found[session] = profile
    return found, notes


def _inside(path: Path, root: Path) -> bool:
    path = normal(path)
    return path == root or root in path.parents


def _sessions(
    root: Path,
    bound: dict[str, str],
    profiles: set[str],
    client: Callable[[str], Sessions],
) -> tuple[list[Session], list[str]]:
    sessions: dict[str, Session] = {}
    blockers = []
    for profile in sorted(profiles | set(bound.values())):
        try:
            aoe = client(profile)
            listed = aoe.list_sessions()
        except (AoEError, OSError) as error:
            blockers.append(f"AoE profile {profile}: sessions not listed ({error})")
            continue
        for item in listed:
            if item.state in GONE or item.id in sessions:
                continue
            if not (_inside(item.path, root) or bound.get(item.id) == profile):
                continue
            status = item.status
            if item.state == "live" and status is None:
                try:
                    status = aoe.show(item.id).status
                except (AoEError, OSError) as error:
                    blockers.append(f"{item.id}: AoE status not read ({error})")
            sessions[item.id] = Session(profile, item.id, item.title, item.state, status)
            if status == "running":
                blockers.append(
                    f"session {item.id} ({item.title or profile}) is running; "
                    "let it finish or stop it first"
                )
    return list(sessions.values()), blockers


def _chief_tasks(root: Path, projects: tuple[str, ...]) -> tuple[list[Task], list[str]]:
    tasks: dict[str, Task] = {}
    blockers = []
    try:
        client = ChiefClient(root, load_config(root))
    except (OSError, ValueError) as error:
        client = None
        config_error = str(error)
    for project in (None, *projects):
        try:
            from toulmin.application.engineering_tasks import engineering_task_ids

            facts = build_facts(root, project) if project is not None else ()
            task_ids = {fact.task_id for fact in facts if fact.task_id is not None}
            task_ids.update(engineering_task_ids(root, project))
        except (OSError, ValueError) as error:
            blockers.append(f"{project}: build records not read ({error})")
            continue
        for task_id in sorted(task_ids):
            if client is None:
                blockers.append(f"{task_id}: Chief state not read ({config_error})")
                continue
            try:
                state = client.read_task(task_id).state
            except ChiefTaskMissing:
                state = None
            except (OSError, ValueError) as error:
                blockers.append(f"{task_id}: Chief state not read ({error})")
                continue
            tasks[task_id] = Task(project, task_id, state)
    # Tasks started directly with `chief new` inside the workspace have no build record.
    if client is not None:
        folder = client.config.home / "tasks"
        for path in sorted(folder.glob("*/task.json")) if folder.is_dir() else ():
            try:
                raw = json.loads(path.read_bytes())
            except (OSError, ValueError):
                continue
            if not isinstance(raw, dict) or path.parent.name in tasks:
                continue
            places = [raw.get(key) for key in ("repo", "worktree")]
            if any(
                isinstance(item, str) and Path(item).is_absolute() and _inside(Path(item), root)
                for item in places
            ):
                state = raw.get("state")
                tasks[path.parent.name] = Task(
                    None, path.parent.name, state if isinstance(state, str) else None
                )
    for task in tasks.values():
        if task.state is not None and task.state not in FINISHED:
            blockers.append(
                f"Chief task {task.id} is {task.state}; finish it (`chief close {task.id}` or "
                "--abandon) first"
            )
    return list(tasks.values()), blockers


def _losses(git: GitState | None) -> list[str]:
    if git is None:
        return ["not a git repository: no copy of these files exists elsewhere"]
    if git.error:
        return [f"git state not read ({git.error}); assume nothing exists elsewhere"]
    losses = []
    if not git.has_head:
        losses.append("no commits: no copy of these files exists elsewhere")
    elif git.upstream is None:
        losses.append(f"branch {git.branch} has no upstream: its commits exist only here")
    elif git.ahead:
        losses.append(f"{git.ahead} commit(s) not pushed to {git.upstream}")
    if git.changes:
        losses.append(f"{len(git.changes)} uncommitted file(s)")
    return losses


def plan_removal(
    path: Path,
    client: Callable[[str], Sessions],
    *,
    default_profile: str,
    here: Path | None = None,
) -> RemovalPlan:
    """Read-only: what removing this workspace would do and what blocks it."""
    root = checked_root(path)
    name, kind = _kind(root)
    projects = _projects(root)
    blockers = []
    current = normal(here or Path.cwd())
    if _inside(current, root):
        blockers.append("your shell is inside this workspace; run the command from elsewhere")
    bound, notes = _bindings(root, projects)
    sessions, session_blockers = _sessions(root, bound, {default_profile}, client)
    tasks, task_blockers = _chief_tasks(root, projects)
    files, size = _usage(root)
    git = git_state(root)
    return RemovalPlan(
        root,
        name,
        kind,
        projects,
        files,
        size,
        git,
        tuple(sessions),
        tuple(tasks),
        tuple(blockers + session_blockers + task_blockers),
        tuple(_losses(git)),
        tuple(notes),
    )


def write_archive(root: Path, target: Path) -> int:
    """A gzip tar of the whole folder (symbolic links stored as links); never overwrites."""
    target = normal(target)
    if os.path.lexists(target):
        raise RemovalError(f"{target}: already exists; choose another archive name")
    if _inside(target, root):
        raise RemovalError(f"{target}: inside the workspace that will be removed")
    if not target.parent.is_dir():
        raise RemovalError(f"{target.parent}: no such folder for the archive")
    handle = tempfile.NamedTemporaryFile(
        dir=target.parent, prefix=".toulmin-archive-", delete=False
    )
    handle.close()
    temporary = Path(handle.name)
    try:
        with tarfile.open(temporary, "w:gz") as archive:
            archive.add(root, arcname=root.name)
        os.link(temporary, target)  # fails instead of replacing a file created meanwhile
    finally:
        temporary.unlink(missing_ok=True)
    return target.stat().st_size


def remove_sessions(plan: RemovalPlan, client: Callable[[str], Sessions], done: list[str]) -> None:
    """Move each session to AoE's trash, recording each in ``done``; stop at a failure."""
    for session in plan.sessions:
        client(session.profile).remove(session.id)
        done.append(session.id)


def delete_folder(root: Path) -> None:
    """Delete the checked folder; symbolic links inside are removed, never followed."""
    shutil.rmtree(checked_root(root))
