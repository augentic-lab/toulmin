"""Which model a native session reported, read from that CLI's own session log (WX3).

Only the model name and reasoning effort (and, R6, token counts) are extracted; no
conversation content leaves this module. The log formats belong to the native CLIs and may
change: anything missing or unrecognized means "not reported", never an error. This is
provenance for display only and never a control branch.
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


@dataclass(frozen=True)
class SessionUsage:
    """A native conversation's token totals as its own log records them (R6); display only."""

    requests: int | None  # model requests counted (Claude logs); None when the log has no count
    input_tokens: int  # all input, cached included
    cached_input_tokens: int
    output_tokens: int
    context_tokens: int | None  # input of the latest request: the context now carried
    context_window: int | None
    log: str


def _int(source: object, name: str) -> int:
    value = source.get(name) if isinstance(source, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _codex_usage(log: Path) -> SessionUsage | None:
    """The newest ``token_count`` event carries the conversation's running total."""
    for line in _lines_from_end(log):
        try:
            record = json.loads(line)
        except ValueError:
            continue
        payload = record.get("payload") if isinstance(record, dict) else None
        if not isinstance(payload, dict) or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        if not isinstance(info, dict) or not isinstance(info.get("total_token_usage"), dict):
            continue
        total, last = info["total_token_usage"], info.get("last_token_usage")
        window = info.get("model_context_window")
        return SessionUsage(
            None,
            _int(total, "input_tokens"),
            _int(total, "cached_input_tokens"),
            _int(total, "output_tokens"),
            _int(last, "input_tokens") if isinstance(last, dict) else None,
            window if isinstance(window, int) and not isinstance(window, bool) else None,
            str(log),
        )
    return None


def _claude_usage(log: Path) -> SessionUsage | None:
    """Sum per request: a streamed reply logs one record per content block, same usage."""
    requests: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for line in _lines_from_end(log):
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict) or record.get("type") != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        usage, key = message.get("usage"), message.get("id")
        if isinstance(usage, dict) and isinstance(key, str) and key not in requests:
            requests[key] = usage
            order.append(key)  # newest first
    if not requests:
        return None

    def inputs(usage: dict[str, Any]) -> int:
        names = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
        return sum(_int(usage, name) for name in names)

    values = list(requests.values())
    return SessionUsage(
        len(values),
        sum(inputs(usage) for usage in values),
        sum(_int(usage, "cache_read_input_tokens") for usage in values),
        sum(_int(usage, "output_tokens") for usage in values),
        inputs(requests[order[0]]),
        None,
        str(log),
    )


USAGE_READERS: dict[str, Callable[[Path], SessionUsage | None]] = {
    "codex": _codex_usage,
    "claude": _claude_usage,
}


def reported_usage(agent: str, provider_id: str | None) -> SessionUsage | None:
    """Token totals of this native conversation from its log (the newest 16 MiB for Claude)."""
    reader = USAGE_READERS.get(agent)
    if reader is None or provider_id is None:
        return None
    try:
        log = session_log(agent, provider_id)
        return None if log is None else reader(log)
    except OSError:
        return None
