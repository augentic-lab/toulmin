"""S2: offline, read-only migration advice; git stays outside L1/L2."""

import os
import re
import shlex
import time
from dataclasses import dataclass
from pathlib import Path

from toulmin.adapters.base import run_process
from toulmin.adapters.chief import read_config_file
from toulmin.adapters.git import git
from toulmin.core.documents import FormatError
from toulmin.core.repository import Repository

IGNORE_PATTERNS = (".aoe/", "tools/*.local.toml")
TRACKED_PATTERNS = (".aoe", "projects/*/.aoe", "projects/*/.aoe/*", "tools/*.local.toml")


@dataclass(frozen=True)
class GitChange:
    path: str
    status: str
    original: str | None = None


@dataclass(frozen=True)
class GitState:
    branch: str = "detached HEAD"
    changes: tuple[GitChange, ...] = ()
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    operations: tuple[str, ...] = ()
    unmerged: bool = False
    fetched_at: float | None = None
    error: str | None = None
    has_head: bool = False

    @property
    def warning(self) -> str | None:
        warnings = [f"{operation} in progress" for operation in self.operations]
        if self.unmerged:
            warnings.append("unmerged paths")
        if self.behind:
            warnings.append(
                f"diverged from {self.upstream}: reconcile before writing; "
                "never merge histories that both created objects"
                if self.ahead
                else "pull before writing: git pull --ff-only"
            )
        return "; ".join(warnings) or None

    def line(self) -> str:
        if self.error:
            return f"git: state not read ({self.error})"
        tracking = (
            f"{self.ahead} ahead / {self.behind} behind {self.upstream}"
            if self.upstream
            else "no upstream"
        )
        if self.fetched_at is None:
            fetched = "never fetched"
        else:
            seconds = max(0, int(time.time() - self.fetched_at))
            age = f"{seconds // 3600} h" if seconds >= 3600 else f"{seconds // 60} min"
            fetched = "last fetch " + age + " ago"
        return (
            f"git: {self.branch}, {len(self.changes)} uncommitted files, {tracking} ({fetched})"
            + ("; " + self.warning if self.warning else "")
        )


def git_changes(output: str) -> tuple[GitChange, ...]:
    """Porcelain v1 -z puts a rename destination before its original name."""
    fields = iter(output.split("\0"))
    result = []
    for field in fields:
        if not field:
            continue
        if len(field) < 4 or field[2] != " ":
            raise FormatError("invalid git status porcelain record")
        status, path = field[:2], field[3:]
        original = next(fields, None) if "R" in status or "C" in status else None
        if ("R" in status or "C" in status) and not original:
            raise FormatError("invalid git status rename record")
        result.append(GitChange(path, status, original))
    return tuple(result)


def git_state(root: Path) -> GitState | None:
    """Local refs only; read-only queries, including an index-refresh-free status."""
    if not os.path.lexists(root / ".git"):
        return None
    try:
        top = git(root, "rev-parse", "--show-toplevel").stdout.strip()
        if Path(top).resolve() != root.resolve():
            raise FormatError("workspace must be the git worktree root")
        changes = git_changes(
            git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
        )
        branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD", allowed=(0, 1))
        name = branch.stdout.strip() if branch.exit_status == 0 else "detached HEAD"
        has_head = (
            git(root, "rev-parse", "--verify", "--quiet", "HEAD", allowed=(0, 1)).exit_status == 0
        )
        upstream = None
        ahead = behind = 0
        if has_head and branch.exit_status == 0:
            tracking = git(
                root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", allowed=(0, 128)
            )
            if tracking.exit_status == 0:
                upstream = tracking.stdout.strip()
                counts = git(
                    root, "rev-list", "--left-right", "--count", "HEAD...@{u}"
                ).stdout.split()
                ahead, behind = map(int, counts)
            elif "no upstream configured" not in tracking.stderr:
                raise FormatError(tracking.stderr.strip() or "upstream not readable")
        directory = Path(git(root, "rev-parse", "--git-dir").stdout.strip())
        if not directory.is_absolute():
            directory = root / directory
        operations = tuple(
            name
            for name, markers in (
                ("merge", ("MERGE_HEAD",)),
                ("rebase", ("rebase-merge", "rebase-apply")),
                ("cherry-pick", ("CHERRY_PICK_HEAD", "sequencer")),
            )
            if any((directory / marker).exists() for marker in markers)
        )
        fetch = directory / "FETCH_HEAD"
        return GitState(
            name,
            changes,
            upstream,
            ahead,
            behind,
            operations,
            any(item.status in {"DD", "AU", "UD", "UA", "DU", "AA", "UU"} for item in changes),
            fetch.stat().st_mtime if fetch.exists() else None,
            has_head=has_head,
        )
    except (OSError, ValueError) as error:
        return GitState(error=" ".join(str(error).split()))


def machine_local(path: str) -> bool:
    parts = Path(path).parts
    return (
        ".aoe" in parts
        or len(parts) == 2
        and parts[0] == "tools"
        and parts[1].endswith(".local.toml")
    )


def tracked_notice(paths: list[str]) -> str:
    groups = {
        ".aoe"
        if path == ".aoe" or path.startswith(".aoe/")
        else "tools/*.local.toml"
        if path.startswith("tools/")
        else "projects/*/.aoe"
        if path.endswith("/.aoe")
        else "projects/*/.aoe/*"
        for path in paths
    }
    command = shlex.join(
        ["git", "rm", "-r", "--cached", "--", *(p for p in TRACKED_PATTERNS if p in groups)]
    )
    return "Tracked machine-local files: " + command


def sync_notices(root: Path) -> tuple[str, ...]:
    """At most three advisory lines; no index, ignore file or network mutations."""
    if not (root / ".git").is_dir():
        return ()
    try:
        repository = Repository(root)
        repository.path(".git", "directory")
        ignore = repository.path(".gitignore")
        lines = ignore.read_text(encoding="utf-8").splitlines() if ignore.exists() else []
        missing = [pattern for pattern in IGNORE_PATTERNS if pattern not in lines]
        notices = []
        if missing:
            notices.append(
                "Machine-local files are not ignored: add these lines to .gitignore: "
                + ", ".join(missing)
            )
        # NUL separation preserves filenames; glob arguments are git pathspecs, not a shell.
        result = run_process(
            ["git", "-C", str(repository.root), "ls-files", "-z", "--", *TRACKED_PATTERNS],
            "",
            15,
            repository.root,
            env=(("GIT_CONFIG_GLOBAL", os.devnull), ("GIT_CONFIG_NOSYSTEM", "1")),
        )
        if result.exit_status != 0:
            reason = (
                "git ls-files timed out"
                if result.exit_status is None
                else f"git ls-files exited {result.exit_status}"
            )
            raise FormatError(f"{reason}: {result.stderr.strip() or 'no diagnostic'}")
        tracked = [path for path in result.stdout.split("\0") if path]
        if tracked:
            # Suggest only matching groups, so an absent group cannot make git rm fail.
            notices.append(tracked_notice(tracked))
        config = repository.path(".git/config")
        remote = config.read_text(encoding="utf-8") if config.exists() else ""
        if re.search(r'^\s*\[remote\s+"', remote, re.MULTILINE):
            portable = read_config_file(repository.root, "tools/chief.toml")
            if {"repos", "home", "command"} & portable.keys():
                notices.append(
                    "Machine paths in tools/chief.toml; move them to tools/chief.local.toml "
                    "before syncing"
                )
        return tuple(notices)
    except (OSError, ValueError) as error:
        return ("Machine-local sync check skipped: " + " ".join(str(error).split()),)
