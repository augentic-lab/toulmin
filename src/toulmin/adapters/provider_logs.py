"""Which model a native session reported, read from that CLI's own session log (WX3).

Only the model name and reasoning effort are extracted; no conversation content leaves this
module. The log formats belong to the native CLIs and may change: anything missing or
unrecognized means "not reported", never an error. This is provenance for display only and
never a control branch.
"""

import json
import os
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROVIDER_ID = re.compile(r"[A-Za-z0-9-]{8,64}")
MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@\[\]-]{0,99}")
EFFORT = re.compile(r"[a-z][a-z_-]{0,31}")
BLOCK = 1 << 18
TAIL_LIMIT = 16 << 20  # newest records are at the end; older history is not scanned


@dataclass(frozen=True)
class ModelReport:
    model: str
    effort: str | None
    log: str  # the session log the values came from


def _home(variable: str, default: str) -> Path:
    value = os.environ.get(variable, "")
    return Path(value) if value and Path(value).is_absolute() else Path.home() / default


def session_log(agent: str, provider_id: str) -> Path | None:
    """The newest session log of ``provider_id``; the ID pattern keeps globbing literal."""
    if not PROVIDER_ID.fullmatch(provider_id):
        return None
    if agent == "codex":
        found = _home("CODEX_HOME", ".codex").glob(f"sessions/*/*/*/rollout-*-{provider_id}.jsonl")
    elif agent == "claude":
        found = _home("CLAUDE_CONFIG_DIR", ".claude").glob(f"projects/*/{provider_id}.jsonl")
    else:
        return None
    candidates = [path for path in found if path.is_file() and not path.is_symlink()]
    return max(candidates, key=lambda path: path.stat().st_mtime, default=None)


def _lines_from_end(path: Path) -> Iterator[bytes]:
    with path.open("rb") as handle:
        position = handle.seek(0, os.SEEK_END)
        scanned = 0
        partial = b""
        while position > 0 and scanned < TAIL_LIMIT:
            size = min(BLOCK, position)
            position -= size
            handle.seek(position)
            lines = (handle.read(size) + partial).split(b"\n")
            scanned += size
            partial = lines[0]  # may continue in the previous block
            yield from reversed(lines[1:])
        if position == 0 and partial:
            yield partial


def _codex(record: dict[str, Any]) -> tuple[Any, Any] | None:
    payload = record.get("payload")
    if record.get("type") != "turn_context" or not isinstance(payload, dict):
        return None
    return payload.get("model"), payload.get("effort")


def _claude(record: dict[str, Any]) -> tuple[Any, Any] | None:
    message = record.get("message")
    if record.get("type") != "assistant" or not isinstance(message, dict):
        return None
    return message.get("model"), record.get("effort")


READERS: dict[str, Callable[[dict[str, Any]], tuple[Any, Any] | None]] = {
    "codex": _codex,
    "claude": _claude,
}


def reported_model(agent: str, provider_id: str | None) -> ModelReport | None:
    """The model of the latest turn recorded for this native conversation, if any."""
    reader = READERS.get(agent)
    if reader is None or provider_id is None:
        return None
    try:
        log = session_log(agent, provider_id)
        if log is None:
            return None
        for line in _lines_from_end(log):
            try:
                record = json.loads(line)
            except ValueError:
                continue
            values = reader(record) if isinstance(record, dict) else None
            if values is None:
                continue
            model, effort = values
            # Synthetic placeholders such as "<synthetic>" fail the pattern and are skipped.
            if isinstance(model, str) and MODEL.fullmatch(model):
                valid = isinstance(effort, str) and EFFORT.fullmatch(effort)
                return ModelReport(model, effort if valid else None, str(log))
    except OSError:
        return None
    return None
