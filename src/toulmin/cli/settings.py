"""User preferences and workbench discovery for the CLI (WX2).

Preferences are the researcher's own defaults (actor, AoE profile, native CLI, attach). They
live outside every workbench, are never research data and never override a command flag or
a saved binding. Precedence: flag > saved binding > environment variable > config > default.
"""

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from toulmin.core.workspace import CHARTER_FILE

ACTOR_VARIABLE = "TOULMIN_ACTOR"
PROFILE_VARIABLE = "AGENT_OF_EMPIRES_PROFILE"
AGENTS = ("codex", "claude")
DEFAULT_PROFILE = "main"
DEFAULT_AGENT = "codex"
PROFILE_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")
EXAMPLE = """\
actor = "Your Name"     # default for --confirmed-by
[aoe]
profile = "main"        # AoE profile for new sessions
agent = "codex"         # native CLI for new sessions: codex or claude
attach = true           # attach after open
"""


class SettingsError(ValueError):
    """The configuration file exists but cannot be used; it is never repaired."""


@dataclass(frozen=True)
class Settings:
    path: Path
    loaded: bool
    actor: str | None = None
    profile: str | None = None
    agent: str | None = None
    attach: bool | None = None


def config_path() -> Path:
    """``$XDG_CONFIG_HOME/toulmin/config.toml``; a relative XDG value is ignored per the spec."""
    base = os.environ.get("XDG_CONFIG_HOME", "")
    home = Path(base) if base and Path(base).is_absolute() else Path.home() / ".config"
    return home / "toulmin" / "config.toml"


def _table(value: Any, where: str, allowed: set[str], path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SettingsError(f"{path}: {where} must be a table")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise SettingsError(f"{path}: unknown setting(s) {', '.join(unknown)} in {where}")
    return value


def _text(value: Any, name: str, path: Path) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SettingsError(f"{path}: {name} must be a non-empty string")
    return value


def load_settings() -> Settings:
    path = config_path()
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return Settings(path, False)
    except OSError as error:
        raise SettingsError(f"{path}: cannot read ({error.strerror or error})") from error
    try:
        document = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise SettingsError(f"{path}: invalid TOML ({error})") from error
    top = _table(document, "the file", {"actor", "aoe"}, path)
    aoe = _table(top.get("aoe", {}), "[aoe]", {"profile", "agent", "attach"}, path)
    profile = _text(aoe.get("profile"), "aoe.profile", path)
    if profile is not None and not PROFILE_NAME.fullmatch(profile):
        raise SettingsError(f"{path}: aoe.profile must match [A-Za-z0-9_-]{{1,64}}")
    agent = _text(aoe.get("agent"), "aoe.agent", path)
    if agent is not None and agent not in AGENTS:
        raise SettingsError(f"{path}: aoe.agent must be codex or claude")
    attach = aoe.get("attach")
    if attach is not None and not isinstance(attach, bool):
        raise SettingsError(f"{path}: aoe.attach must be true or false")
    return Settings(path, True, _text(top.get("actor"), "actor", path), profile, agent, attach)


def settings() -> Settings:
    """Load preferences at the CLI boundary; an unusable file stops the command."""
    try:
        return load_settings()
    except SettingsError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error


def resolve_actor(value: str | None) -> str | None:
    """--confirmed-by, else $TOULMIN_ACTOR, else the configured actor."""
    if value is not None:
        return value
    return os.environ.get(ACTOR_VARIABLE) or settings().actor


ACTOR_HINT = f"pass --confirmed-by, set {ACTOR_VARIABLE} or set actor in the toulmin config"


def default_profile() -> str | None:
    """The profile for a scope without a saved binding: environment, then config."""
    return os.environ.get(PROFILE_VARIABLE) or settings().profile


def default_agent() -> str:
    return settings().agent or DEFAULT_AGENT


def default_attach() -> bool:
    return settings().attach is True


def _workbench(candidate: Path) -> bool:
    try:
        return os.path.lexists(candidate / CHARTER_FILE) or (
            (candidate / "AGENTS.md").is_file()
            and (candidate / "framework/formats.md").is_file()
            and (candidate / "projects").is_dir()
        )
    except OSError:
        return False


def find_workbench(start: Path) -> Path | None:
    """The nearest workspace or legacy workbench root at or above ``start``."""
    start = start.absolute()
    return next((path for path in (start, *start.parents) if _workbench(path)), None)


def discover_root(ctx: typer.Context, param: typer.CallbackParam, value: Path) -> Path:
    """An omitted --root means the nearest workbench at or above the current directory.

    An explicit --root (even ``.``) is used as given. A root found above the current
    directory is announced on stderr so that a wrong guess is visible.
    """
    if ctx.resilient_parsing or param.name is None:
        return value
    source = ctx.get_parameter_source(param.name)
    if source is None or source.name != "DEFAULT":  # typer vendors click privately
        return value
    try:
        here = Path.cwd()
    except OSError:
        return value
    found = find_workbench(here)
    if found is None or found == here:
        return value
    typer.echo(f"Using workbench root {found} (found above the current directory)", err=True)
    return found


def root_option(text: str) -> Any:
    return typer.Option(
        "--root",
        help=f"{text} Omitted: the nearest workbench at or above the current directory.",
        callback=discover_root,
    )
