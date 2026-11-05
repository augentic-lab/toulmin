"""Known workspaces, so ``toulmin open`` can find them from anywhere (WX6).

A user-level cache, never research data: it lives outside every workbench, records only
paths, display names and when each was last opened, and decides nothing. Deleting it loses
only the list; workspaces are registered again as they are opened. Recognition always
re-checks the folder: an entry counts as a workbench only while its files are there now.
"""

import json
import os
import re
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import typer

from toulmin.core.codec import decode
from toulmin.core.workspace import CHARTER_FILE, validate_charter

SCHEMA_VERSION = 1
MOMENT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
NAME_LIMIT = 200

State = Literal["workspace", "legacy", "damaged", "missing"]


class RegistryError(ValueError):
    """The registry file exists but cannot be used; it is never overwritten or repaired."""


@dataclass(frozen=True)
class Entry:
    path: Path
    name: str  # as last seen; display only
    last_opened: str | None  # None: found by a scan and not opened since


@dataclass(frozen=True)
class Known:
    entry: Entry
    state: State
    name: str  # the live WORKSPACE.md name when readable, else the stored one


def registry_path() -> Path:
    """``$XDG_STATE_HOME/toulmin/workspaces.json``; a relative XDG value is ignored."""
    base = os.environ.get("XDG_STATE_HOME", "")
    home = Path(base) if base and Path(base).is_absolute() else Path.home() / ".local/state"
    return home / "toulmin" / "workspaces.json"


def normal(path: Path) -> Path:
    """The identity of an entry: absolute and lexically normalized, symlinks not followed."""
    return Path(os.path.normpath(path.expanduser().absolute()))


def _name(value: Any, where: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > NAME_LIMIT
        or any(ord(character) < 32 for character in value)
    ):
        raise RegistryError(f"{where}: name: expected a short single-line text")
    return value


def _entry(value: Any, where: str) -> Entry:
    if not isinstance(value, dict) or set(value) != {"path", "name", "last_opened"}:
        raise RegistryError(f"{where}: expected exactly path, name and last_opened")
    path, opened = value["path"], value["last_opened"]
    if not isinstance(path, str) or "\x00" in path or not Path(path).is_absolute():
        raise RegistryError(f"{where}: path: expected an absolute path")
    if normal(Path(path)) != Path(path):
        raise RegistryError(f"{where}: path: expected a normalized path")
    if opened is not None and not (isinstance(opened, str) and MOMENT.fullmatch(opened)):
        raise RegistryError(f"{where}: last_opened: expected YYYY-MM-DDTHH:MM:SSZ or null")
    return Entry(Path(path), _name(value["name"], where), opened)


def load() -> tuple[Entry, ...]:
    """The stored entries; a missing file is an empty list."""
    path = registry_path()
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return ()
    except OSError as error:
        raise RegistryError(f"{path}: unreadable ({error})") from error
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise RegistryError(f"{path}: not valid JSON ({error})") from error
    if not isinstance(value, dict) or set(value) != {"schema_version", "workspaces"}:
        raise RegistryError(f"{path}: expected exactly schema_version and workspaces")
    if type(value["schema_version"]) is not int or value["schema_version"] != SCHEMA_VERSION:
        raise RegistryError(f"{path}: schema_version: expected {SCHEMA_VERSION}")
    if not isinstance(value["workspaces"], list):
        raise RegistryError(f"{path}: workspaces: expected a list")
    entries = tuple(
        _entry(item, f"{path}: workspaces[{index}]")
        for index, item in enumerate(value["workspaces"])
    )
    if len({entry.path for entry in entries}) != len(entries):
        raise RegistryError(f"{path}: workspaces: duplicate paths")
    return entries


def _write(entries: Iterable[Entry]) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema_version": SCHEMA_VERSION,
        "workspaces": [
            {"path": str(entry.path), "name": entry.name, "last_opened": entry.last_opened}
            for entry in entries
        ],
    }
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=".workspaces-", delete=False
    )
    try:
        with handle:
            json.dump(document, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        # Concurrent writers may lose an entry; acceptable for a cache rebuilt by use.
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def _now(now: datetime | None) -> str:
    return (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def remember(root: Path, name: str, *, opened: bool = True, now: datetime | None = None) -> bool:
    """Add or refresh one entry; False when it was already known (a scan changes nothing)."""
    key = normal(root)
    entries = list(load())
    found = next((index for index, entry in enumerate(entries) if entry.path == key), None)
    previous = entries[found] if found is not None else None
    if previous is not None and not opened:
        return False
    stamp = _now(now) if opened else None
    entry = Entry(key, _name(name, str(key)), stamp)
    if found is None:
        entries.append(entry)
    else:
        entries[found] = entry
    _write(entries)
    return previous is None


def forget(path: Path) -> bool:
    """Remove one entry; the folder itself is never touched."""
    key = normal(path)
    entries = load()
    kept = [entry for entry in entries if entry.path != key]
    if len(kept) == len(entries):
        return False
    _write(kept)
    return True


def charter_name(root: Path) -> str | None:
    """The WORKSPACE.md name, or None when the file is absent or unreadable."""
    path = root / CHARTER_FILE
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return validate_charter(decode(path.read_bytes(), str(path))).name
    except (OSError, ValueError):
        return None


def _legacy(root: Path) -> bool:
    return (
        (root / "AGENTS.md").is_file()
        and (root / "framework/formats.md").is_file()
        and (root / "projects").is_dir()
    )


def inspect(entry: Entry) -> Known:
    """What the folder is now; the stored entry is never trusted for this."""
    try:
        if os.path.lexists(entry.path / CHARTER_FILE):
            name = charter_name(entry.path)
            return Known(entry, "workspace" if name else "damaged", name or entry.name)
        if _legacy(entry.path):
            return Known(entry, "legacy", entry.name)
    except OSError:
        pass
    return Known(entry, "missing", entry.name)


def known() -> list[Known]:
    """Entries by most recently opened (never-opened last), then path."""
    entries = sorted(load(), key=lambda entry: str(entry.path))
    entries.sort(key=lambda entry: entry.last_opened or "", reverse=True)
    return [inspect(entry) for entry in entries]


def note(root: Path) -> None:
    """Register a workbench a command just used; a failure is a notice, never an error."""
    name = charter_name(root) or normal(root).name or str(normal(root))
    try:
        remember(root, name)
    except (OSError, RegistryError) as error:
        typer.echo(f"Notice: workspace list not updated: {error}", err=True)
