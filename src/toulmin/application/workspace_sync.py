"""S2: offline, read-only migration advice; git stays outside L1/L2."""

import os
import re
import shlex
from pathlib import Path

from toulmin.adapters.base import run_process
from toulmin.adapters.chief import read_config_file
from toulmin.core.documents import FormatError
from toulmin.core.repository import Repository

IGNORE_PATTERNS = (".aoe/", "tools/*.local.toml")
TRACKED_PATTERNS = (".aoe", "projects/*/.aoe", "projects/*/.aoe/*", "tools/*.local.toml")


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
        groups = {
            ".aoe"
            if path == ".aoe" or path.startswith(".aoe/")
            else "tools/*.local.toml"
            if path.startswith("tools/")
            else "projects/*/.aoe"
            if path.endswith("/.aoe")
            else "projects/*/.aoe/*"
            for path in tracked
        }
        if groups:
            # Suggest only matching groups, so an absent group cannot make git rm fail.
            command = shlex.join(
                ["git", "rm", "-r", "--cached", "--", *(p for p in TRACKED_PATTERNS if p in groups)]
            )
            notices.append("Tracked machine-local files: " + command)
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
