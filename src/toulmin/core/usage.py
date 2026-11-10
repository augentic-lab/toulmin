"""Token usage reported by one independent model session (R6): the usage.json archive file.

An archive file beside output.md, not an object and not a Run field, so the v1 formats are
unchanged. Counts are what the tool reported, never estimates: a field the tool did not
report is null, and a session that reported nothing has no usage.json at all.
``input_tokens`` counts all input, cached included (Codex reports it that way; Claude Code
reports uncached, cache-read and cache-creation input separately, which are summed here).
``reported`` keeps the tool's own record verbatim so nothing is lost in that normalization.
"""

import json
from dataclasses import dataclass, field
from typing import Any

USAGE_FILE = "usage.json"
COUNTS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")


@dataclass(frozen=True)
class Usage:
    tool: str  # adapter name, e.g. claude or codex
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    reasoning_output_tokens: int | None = None
    cost_usd: float | None = None  # only when the tool reports it
    reported: dict[str, Any] = field(default_factory=dict)


def _count(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"expected a nonnegative integer or null, got {value!r}")
    return value


def encode_usage(usage: Usage) -> bytes:
    data = {
        "schema_version": 1,
        "tool": usage.tool,
        **{name: getattr(usage, name) for name in COUNTS},
        "cost_usd": usage.cost_usd,
        "reported": usage.reported,
    }
    return (json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n").encode()


def decode_usage(raw: bytes, location: str = "usage.json") -> Usage:
    try:
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("expected an object with schema_version 1")
        tool = data.get("tool")
        if not isinstance(tool, str) or not tool.strip():
            raise ValueError("tool: expected a nonempty string")
        counts = {name: _count(data.get(name)) for name in COUNTS}
        cost = data.get("cost_usd")
        if cost is not None and (isinstance(cost, bool) or not isinstance(cost, int | float)):
            raise ValueError("cost_usd: expected a number or null")
        reported = data.get("reported", {})
        if not isinstance(reported, dict):
            raise ValueError("reported: expected an object")
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"{location}: {error}") from error
    return Usage(tool, **counts, cost_usd=cost, reported=reported)


def _number(source: dict[str, Any], name: str) -> int | None:
    value = source.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def claude_usage(result: dict[str, Any]) -> Usage | None:
    """From Claude Code's final ``result`` event (``usage``, ``modelUsage``, cost)."""
    usage = result.get("usage")
    if not isinstance(usage, dict):
        return None
    parts = [
        _number(usage, name)
        for name in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    ]
    total = sum(part for part in parts if part is not None) if parts[0] is not None else None
    cost = result.get("total_cost_usd")
    reported = {"usage": usage}
    if isinstance(result.get("modelUsage"), dict):
        reported["modelUsage"] = result["modelUsage"]
    return Usage(
        "claude",
        total,
        parts[1],
        _number(usage, "output_tokens"),
        None,
        float(cost) if isinstance(cost, int | float) and not isinstance(cost, bool) else None,
        reported,
    )


def codex_usage(events: list[dict[str, Any]]) -> Usage | None:
    """From Codex ``exec --json`` ``turn.completed`` events, summed over the turns."""
    turns = [
        event["usage"]
        for event in events
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict)
    ]
    if not turns:
        return None

    def total(name: str) -> int | None:
        values = [_number(turn, name) for turn in turns]
        known = [value for value in values if value is not None]
        return sum(known) if len(known) == len(values) else None

    return Usage(
        "codex",
        total("input_tokens"),
        total("cached_input_tokens"),
        total("output_tokens"),
        total("reasoning_output_tokens"),
        None,
        {"turns": turns},
    )
