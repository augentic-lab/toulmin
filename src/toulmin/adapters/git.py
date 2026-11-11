"""Offline git operations at L3, preserving the researcher's identity and hooks."""

from pathlib import Path

from toulmin.adapters.base import Finished, run_process


class GitError(ValueError):
    def __init__(self, result: Finished) -> None:
        self.result = result
        reason = result.stderr.strip() or result.stdout.strip() or "no diagnostic"
        super().__init__(f"git exited {result.exit_status}: {reason}")


def git(root: Path, *args: str, allowed: tuple[int, ...] = (0,), timeout: float = 15) -> Finished:
    # status must not refresh the index during a preview. Disallow lazy fetching in
    # partial clones too; all facts and objects must already be on this machine.
    result = run_process(
        ["git", "--literal-pathspecs", "-C", str(root), *args],
        "",
        timeout,
        root,
        env=(("GIT_OPTIONAL_LOCKS", "0"), ("GIT_NO_LAZY_FETCH", "1")),
    )
    if result.exit_status not in allowed:
        raise GitError(result)
    return result
