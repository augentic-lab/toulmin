"""R8 B2: Chief configuration, bounded CLI calls and read-only recovery lookup.

No import of Chief's code. Workspace chief.toml/chief.local.toml supply configuration;
Chief's own configuration and authentication files are never opened.
"""

import json
import os
import re
import shlex
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from toulmin.adapters.base import Finished, run_process
from toulmin.core.build import BuildReview, BuildTask
from toulmin.core.documents import FormatError
from toulmin.core.repository import Repository

NEW_TIMEOUT = 120.0
DEFAULT_VERIFY_TIMEOUT_SECONDS = 600.0


@dataclass(frozen=True)
class ChiefConfig:
    command: tuple[str, ...]
    home: Path
    tool: str
    budget: dict[str, int | float]
    repos: dict[str, str]
    trust: bool = False
    verify_timeout_seconds: float = DEFAULT_VERIFY_TIMEOUT_SECONDS


def read_config_file(root: Path, name: str) -> dict[str, Any]:
    """Read an optional workspace file through the same confinement checks as other data."""
    try:
        path = Repository(root).path(name)
        with path.open("rb") as stream:
            raw = tomllib.load(stream)
    except FileNotFoundError:
        raw = {}
    except (OSError, ValueError) as error:
        raise FormatError(f"{root / name}: Chief configuration: {error}") from error
    return raw


def _parse_config(
    raw: dict[str, Any], path: Path, *, fallback_home: str | None = None
) -> ChiefConfig:
    command = raw.get("command", "python3 ~/aoe-chief/chief.py")
    if not isinstance(command, str) or not command.strip() or "\x00" in command:
        raise FormatError(f"{path}: command: expected a command string")
    try:
        argv = tuple(os.path.expanduser(part) for part in shlex.split(command))
    except ValueError as error:
        raise FormatError(f"{path}: command: {error}") from error
    if not argv:
        raise FormatError(f"{path}: command: expected an executable")
    home = raw.get("home", "")
    if not isinstance(home, str) or "\x00" in home:
        raise FormatError(f"{path}: home: expected an absolute path or empty string")
    try:
        home_path = Path(
            home or fallback_home or os.environ.get("AOE_CHIEF_HOME") or "~/.local/state/aoe-chief"
        ).expanduser()
    except RuntimeError as error:
        raise FormatError(f"{path}: home: {error}") from error
    if not home_path.is_absolute():
        raise FormatError(f"{path}: home: expected an absolute path")
    tool = raw.get("tool", "codex")
    if tool not in ("codex", "claude", "antigravity"):
        raise FormatError(f"{path}: tool: Chief supports codex, claude or antigravity")
    trust = raw.get("trust", False)
    if type(trust) is not bool:
        raise FormatError(f"{path}: trust: expected true or false")
    budget = raw.get("budget", {"rounds": 15, "hours": 4})
    if not isinstance(budget, dict) or set(budget) != {"rounds", "hours"}:
        raise FormatError(f"{path}: budget: expected rounds and hours")
    if type(budget["rounds"]) is not int or budget["rounds"] <= 0:
        raise FormatError(f"{path}: budget.rounds: expected a positive integer")
    if type(budget["hours"]) not in {int, float} or not 0 < budget["hours"] < float("inf"):
        raise FormatError(f"{path}: budget.hours: expected a positive finite number")
    timeout = raw.get("verify_timeout_seconds", DEFAULT_VERIFY_TIMEOUT_SECONDS)
    if type(timeout) not in {int, float} or not 0 < timeout < float("inf"):
        raise FormatError(f"{path}: verify_timeout_seconds: expected a positive finite number")
    repos = raw.get("repos", {})
    if not isinstance(repos, dict) or any(not isinstance(value, str) for value in repos.values()):
        raise FormatError(f"{path}: repos: expected project names mapped to absolute paths")
    repos = {name: os.path.expanduser(value) for name, value in repos.items()}
    if any(not Path(value).is_absolute() or "\x00" in value for value in repos.values()):
        raise FormatError(f"{path}: repos: expected project names mapped to absolute paths")
    return ChiefConfig(argv, home_path, tool, dict(budget), dict(repos), trust, float(timeout))


def load_config(root: Path) -> ChiefConfig:
    """Validate each source, then overlay local keys; repositories merge by project."""
    base = read_config_file(root, "tools/chief.toml")
    local = read_config_file(root, "tools/chief.local.toml")
    # Check each file's explicit values independently; select environment defaults only
    # after overlaying, so an overridden default cannot reject a valid machine setting.
    _parse_config(base, root / "tools/chief.toml", fallback_home="/")
    _parse_config(local, root / "tools/chief.local.toml", fallback_home="/")
    merged = {**base, **local, "repos": {**base.get("repos", {}), **local.get("repos", {})}}
    origin = "tools/chief.local.toml" if "home" in local else "tools/chief.toml"
    return _parse_config(merged, root / origin)


class ChiefClient:
    def __init__(self, root: Path, config: ChiefConfig) -> None:
        self.root = root
        self.config = config

    def task(self, task_id: str) -> dict[str, Any] | None:
        """Only the exact task.json used for collision checks and interrupted recovery."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", task_id):
            raise FormatError("task_id: expected a safe Chief task identifier")
        path = self.config.home / "tasks" / task_id / "task.json"
        try:
            raw = json.loads(path.read_bytes())
        except FileNotFoundError:
            if path.parent.exists():
                raise FormatError(
                    f"{path}: Chief task directory exists without task.json"
                ) from None
            return None
        except (OSError, ValueError) as error:
            raise FormatError(f"{path}: Chief state not read: {error}") from error
        if not isinstance(raw, dict):
            raise FormatError(f"{path}: Chief state not read: expected an object")
        return raw

    def read_task(self, task_id: str) -> BuildTask:
        """Read the documented fields only; never infer missing values or task state."""
        try:
            raw = self.task(task_id)
        except (OSError, ValueError) as error:
            raise FormatError(f"Chief state not read: {error}") from error
        if raw is None:
            raise FormatError(
                f"Chief state not read: {self.config.home}/tasks/{task_id}/task.json missing"
            )

        def value(data: dict[str, Any], name: str) -> str | None:
            item = data.get(name)
            if item is not None and (not isinstance(item, str) or not item.strip()):
                raise FormatError(f"{task_id}: Chief state not read: {name} must be text or null")
            return item

        review = raw.get("review")
        if review is None:
            review = {}
        if not isinstance(review, dict):
            raise FormatError(f"{task_id}: Chief state not read: review must be an object or null")
        return BuildTask(
            state=value(raw, "state"),
            kickoff_at="kickoff_at" in raw,
            review=BuildReview(
                *(value(review, key) for key in ("verdict", "summary", "head", "by"))
            ),
            **{
                key: value(raw, key)
                for key in ("branch", "base", "worktree", "session_id", "tool", "repo", "closed_at")
            },
        )

    def check_repository(self, repo: str, base_branch: str | None) -> None:
        path = Path(repo)
        if not path.is_absolute() or not path.is_dir():
            raise FormatError(f"{repo}: repository: expected an existing absolute git work tree")
        result = run_process(
            ["git", "-C", repo, "rev-parse", "--is-inside-work-tree"], "", 15, self.root
        )
        if result.exit_status != 0 or result.stdout.strip() != "true":
            raise FormatError(f"{repo}: repository: expected a git work tree")
        if base_branch is not None:
            result = run_process(
                [
                    "git",
                    "-C",
                    repo,
                    "rev-parse",
                    "--verify",
                    "--end-of-options",
                    f"{base_branch}^{{commit}}",
                ],
                "",
                15,
                self.root,
            )
            if result.exit_status != 0:
                raise FormatError(f"{repo}: base_branch: {base_branch} is not an existing commit")

    def new(
        self, contract: Path, task_id: str, base_branch: str | None, *, trust: bool = False
    ) -> Finished:
        argv = [*self.config.command, "new", "--from", str(contract), "--id", task_id]
        if base_branch is not None:
            argv += ["--base-branch", base_branch]
        if trust:
            argv.append("--trust")
        return run_process(
            argv, "", NEW_TIMEOUT, self.root, env=(("AOE_CHIEF_HOME", str(self.config.home)),)
        )
