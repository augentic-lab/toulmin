"""L3 repository scaffolding, including instruction-file adapters and local Git."""

import errno
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from toulmin.core.atomic import handoff_mutex
from toulmin.core.codec import decode
from toulmin.core.identifiers import validate_project_name
from toulmin.core.workspace import CHARTER_FILE, render_initial, validate_charter, validate_name
from toulmin.protocols.adoption import AdoptionTemplates
from toulmin.protocols.workspace_state import RootState, classify_root

# Empty record locations of a fresh workspace (docs/workspace-formats.md, section 12).
WORKSPACE_DIRECTORIES = ("projects", "runs/drafts", "sessions", "shared/resources")


def _templates(project: str | None) -> dict[Path, bytes]:
    """Read package data, so installed wheels need no source checkout.

    Without a project, the project template is left out and the workspace record
    locations are added: a workspace starts with no child, guessed goal or object.
    """
    templates = files("toulmin.cli").joinpath("templates")
    result: dict[Path, bytes] = {}

    def collect(source: Traversable, relative: Path) -> None:
        # Traversable includes archive-backed resources, not just filesystem paths.
        for child in sorted(source.iterdir(), key=lambda item: item.name):
            if project is None and relative == Path("projects"):
                continue
            destination = relative / child.name.replace("PROJECT_NAME", project or "")
            if child.is_dir():
                collect(child, destination)
            elif project is not None:
                result[destination] = child.read_bytes().replace(b"{{project}}", project.encode())
            else:
                result[destination] = child.read_bytes()

    collect(templates, Path())
    if project is None:
        # A workspace root gets scope-aware instructions from a separate template; the
        # shared AGENTS.md stays unchanged, so legacy workbenches keep matching it.
        workspace = files("toulmin.cli").joinpath("workspace_templates", "AGENTS.md")
        result[Path("AGENTS.md")] = workspace.read_bytes()
        for directory in WORKSPACE_DIRECTORIES:
            result[Path(directory) / ".gitkeep"] = b""
    return result


def workspace_setup() -> dict[str, bytes]:
    """Expected setup files of a workspace root (without WORKSPACE.md), for classification."""
    return {path.as_posix(): content for path, content in _templates(None).items()}


def adoption_templates() -> AdoptionTemplates:
    """Packaged inputs of legacy adoption: current files and every released copy's digest."""
    package = files("toulmin.cli")
    released = json.loads(package.joinpath("workspace_templates", "released.json").read_text())
    return AdoptionTemplates(
        package.joinpath("workspace_templates", "AGENTS.md").read_bytes(),
        package.joinpath("templates", "framework", "workspace-formats.md").read_bytes(),
        {path: frozenset(values) for path, values in released.items()},
        workspace_setup(),
    )


def _ancestors(path: Path) -> Iterator[Path]:
    yield from reversed(path.parents)
    yield path


def _check_directory(path: Path) -> None:
    for item in _ancestors(path):
        if item.is_symlink():
            raise ValueError(f"Directory symlink is not allowed: {item}")
        if item.exists() and not item.is_dir():
            raise ValueError(f"Expected directory: {item}")


def _git_environment() -> dict[str, str]:
    # A caller's GIT_DIR or GIT_WORK_TREE must not redirect this initialization.
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def _run_git(git: str, *arguments: str) -> str:
    result = subprocess.run(
        [git, *arguments], capture_output=True, text=True, env=_git_environment(), check=False
    )
    if result.returncode:
        raise RuntimeError(f"Git initialization failed: {result.stderr.strip()}")
    return result.stdout.strip()


def initialize(root: Path, project: str) -> int:
    """Legacy project route: workbench templates plus one template project.

    Refused on a workspace root, where children are added by reviewed creation only.
    """
    validate_project_name(project)
    if ".." in root.parts:
        raise ValueError("Workbench root must not contain '..'")
    root = root.absolute()
    _check_directory(root)
    if os.path.lexists(root / CHARTER_FILE):
        raise ValueError(
            f"{root} is a workspace root: init --project is refused there. Children are "
            "added by reviewed creation (toulmin project propose/create)"
        )
    return _publish(root, _templates(project))


@dataclass(frozen=True)
class WorkspaceInit:
    root: Path
    name: str
    created: int
    existing: bool
    remnants: tuple[str, ...] = ()


def initialize_workspace(root: Path, name: str | None = None) -> WorkspaceInit:
    """Create a project-free workspace; on a workspace root, report it and write nothing.

    Allowed on missing, empty and incomplete-init roots. WORKSPACE.md is published
    last, so its presence means setup finished. Edited files are never compared or
    rewritten on an existing workspace; legacy and unrelated roots are refused.
    """
    if ".." in root.parts:
        raise ValueError("Workbench root must not contain '..'")
    root = root.absolute()
    _check_directory(root)
    if name is not None:
        validate_name(name)
    with handoff_mutex(root):
        report = classify_root(root, workspace_setup())
        if report.state == RootState.WORKSPACE:
            path = root / CHARTER_FILE
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"{path}: expected a regular file; init does not repair it")
            try:
                charter = validate_charter(decode(path.read_bytes(), str(path)))
            except ValueError as error:
                raise ValueError(f"{error}; init does not repair an existing charter") from error
            if name is not None and name != charter.name:
                raise ValueError(
                    f"{root} is already the workspace {charter.name!r}; init does not rename "
                    "it (renaming is a reviewed charter change)"
                )
            return WorkspaceInit(root, charter.name, 0, True, report.remnants)
        if report.state == RootState.LEGACY and report.unexpected:
            raise ValueError(
                f"{root} has workbench files but no WORKSPACE.md and no projects (unexpected "
                f"or modified: {', '.join(report.unexpected)}); nothing written. If this is an "
                "interrupted init, restore those files and rerun"
            )
        if report.state == RootState.LEGACY:
            raise ValueError(
                f"{root} is an existing workbench without workspace state; init does not "
                "upgrade it. Project commands keep working; preview adoption with "
                f"`toulmin workspace adopt {root}`"
            )
        if report.state == RootState.UNRELATED:
            listed = ", ".join(report.unexpected)
            raise ValueError(
                f"{root} is not empty and not a Toulmin workspace (unexpected or modified: "
                f"{listed}); nothing written. Choose an empty directory"
            )
        try:
            chosen = validate_name(name if name is not None else root.name)
        except ValueError as error:
            raise ValueError(f"{error}; pass --name") from error
        created = _publish(root, _templates(None), (root / CHARTER_FILE, render_initial(chosen)))
        return WorkspaceInit(root, chosen, created, False, report.remnants)


def _publish(
    root: Path, contents: dict[Path, bytes], final: tuple[Path, bytes] | None = None
) -> int:
    """Preflight the entire plan, then publish complete files with exclusive creation.

    Roll back entries created by this invocation on ordinary I/O errors. Existing
    files are never rewritten, even when identical. A hard interruption can leave
    a subset of files or Git metadata requiring inspection before rerunning. The
    optional final file is published after everything else, including Git.
    """
    link = root / "CLAUDE.md"
    directories = {root}
    missing: dict[Path, bytes] = {}
    for relative, content in contents.items():
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Invalid template path: {relative}")
        path = root / relative
        _check_directory(path.parent)
        directories.update(parent for parent in path.parents if parent.is_relative_to(root))
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError(f"Expected regular file: {path}")
        if path.exists():
            if path.read_bytes() != content:
                raise ValueError(f"Conflicting file (kept unchanged): {path}")
        else:
            missing[path] = content
    if link.is_symlink():
        if link.readlink() != Path("AGENTS.md"):
            raise ValueError(f"Conflicting symlink: {link}")
    elif link.exists():
        raise ValueError(f"Expected CLAUDE.md symlink: {link}")
    create_link = not link.is_symlink()
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git executable not found; install Git before running init")
    git_dir = root / ".git"
    _check_directory(git_dir)
    create_git = not git_dir.exists()
    if not create_git:
        bare = _run_git(git, f"--git-dir={git_dir}", "rev-parse", "--is-bare-repository")
        if bare != "false":
            raise ValueError(f"Expected a non-bare Git repository: {git_dir}")
    if final is not None and os.path.lexists(final[0]):
        raise ValueError(f"Conflicting file (kept unchanged): {final[0]}")
    if not missing and not create_link and not create_git and final is None:
        return 0

    staging_parent = next(path for path in reversed(list(_ancestors(root))) if path.exists())
    with tempfile.TemporaryDirectory(prefix=".toulmin-init-", dir=staging_parent) as temporary:
        staging = Path(temporary)
        staged: dict[Path, Path] = {}
        for index, (path, content) in enumerate(missing.items()):
            source = staging / str(index)
            source.write_bytes(content)
            staged[path] = source
        if final is not None:
            final_source = staging / "final"
            final_source.write_bytes(final[1])
        if create_git:
            _run_git(
                git,
                "init",
                "--quiet",
                "--template=",
                "--initial-branch=main",
                str(staging / "repo"),
            )

        created_files: list[Path] = []
        created_dirs: list[Path] = []
        try:
            for directory in sorted(directories, key=lambda path: (len(path.parts), str(path))):
                for parent in _ancestors(directory):
                    _check_directory(parent)
                    if not parent.exists():
                        parent.mkdir()
                        created_dirs.append(parent)
            for path, source in staged.items():
                _check_directory(path.parent)
                os.link(source, path)
                created_files.append(path)
            if create_link:
                _check_directory(root)
                link.symlink_to("AGENTS.md")
                created_files.append(link)
            if create_git:
                # mkdir claims ownership before copying; never overwrite a raced .git.
                git_dir.mkdir()
                created_dirs.append(git_dir)
                shutil.copytree(staging / "repo" / ".git", git_dir, dirs_exist_ok=True)
            if final is not None:
                os.link(final_source, final[0])
                created_files.append(final[0])
        except (OSError, ValueError) as error:
            cleanup_errors = []
            for path in reversed(created_files):
                try:
                    path.unlink()
                except OSError as cleanup_error:
                    cleanup_errors.append(str(cleanup_error))
            for directory in reversed(created_dirs):
                try:
                    if directory == git_dir:
                        shutil.rmtree(directory)
                    else:
                        directory.rmdir()
                except OSError as cleanup_error:
                    # A concurrent writer's files are not ours to remove.
                    if cleanup_error.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
                        cleanup_errors.append(str(cleanup_error))
            if cleanup_errors:
                raise RuntimeError(
                    f"{error}; cleanup incomplete: {'; '.join(cleanup_errors)}"
                ) from error
            raise
    return len(created_files) + len(created_dirs)
