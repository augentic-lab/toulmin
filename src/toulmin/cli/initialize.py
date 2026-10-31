"""L3 repository scaffolding, including instruction-file adapters and local Git."""

import errno
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from toulmin.core.identifiers import validate_project_name


def _templates(project: str) -> dict[Path, bytes]:
    """Read package data, so installed wheels need no source checkout."""
    templates = files("toulmin.cli").joinpath("templates")
    result: dict[Path, bytes] = {}

    def collect(source: Traversable, relative: Path) -> None:
        # Traversable includes archive-backed resources, not just filesystem paths.
        for child in sorted(source.iterdir(), key=lambda item: item.name):
            destination = relative / child.name.replace("PROJECT_NAME", project)
            if child.is_dir():
                collect(child, destination)
            else:
                result[destination] = child.read_bytes().replace(b"{{project}}", project.encode())

    collect(templates, Path())
    return result


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
    """Preflight the entire plan, then publish complete files with exclusive creation.

    Roll back entries created by this invocation on ordinary I/O errors. Existing
    files are never rewritten, even when identical. A hard interruption can leave
    a subset of files or Git metadata requiring inspection before rerunning.
    """
    validate_project_name(project)
    if ".." in root.parts:
        raise ValueError("Workbench root must not contain '..'")
    root = root.absolute()
    _check_directory(root)
    contents = _templates(project)
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
    if not missing and not create_link and not create_git:
        return 0

    staging_parent = next(path for path in reversed(list(_ancestors(root))) if path.exists())
    with tempfile.TemporaryDirectory(prefix=".toulmin-init-", dir=staging_parent) as temporary:
        staging = Path(temporary)
        staged: dict[Path, Path] = {}
        for index, (path, content) in enumerate(missing.items()):
            source = staging / str(index)
            source.write_bytes(content)
            staged[path] = source
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
