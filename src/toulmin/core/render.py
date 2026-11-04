"""Deterministic YAML front matter for generated workspace records.

Generated files are reviewed as text and digested byte for byte, so rendering must be
stable: fields in contract order, mappings in flow style, and a string left plain only
when the restricted reader loads it back as the same string.
"""

import json
import re
from typing import Any

from toulmin.core.codec import load_restricted

PLAIN = re.compile(r"[A-Za-z0-9_./-]+")


def scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if type(value) is int:
        return str(value)
    if isinstance(value, str):
        if PLAIN.fullmatch(value):
            loaded, _ = load_restricted(f"v: {value}\n", "<render>", 1)
            if loaded == {"v": value}:
                return value
        return json.dumps(value, ensure_ascii=False)
    raise TypeError(f"cannot render {type(value).__name__}")


def flow(value: Any) -> str:
    if isinstance(value, dict):
        return "{" + ", ".join(f"{key}: {flow(item)}" for key, item in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(flow(item) for item in value) + "]"
    return scalar(value)


def header(fields: list[tuple[str, Any]]) -> str:
    """Render ``---``-delimited front matter; lists of mappings become block lists."""
    lines = ["---"]
    for key, value in fields:
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            lines.append(f"{key}:")
            lines.extend(f"  - {flow(item)}" for item in value)
        else:
            lines.append(f"{key}: {flow(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def fence(content: str, info: str = "") -> str:
    """Fence content with one more backtick than its longest run (at least three)."""
    longest = max((len(run) for run in re.findall(r"`+", content)), default=0)
    marker = "`" * max(3, longest + 1)
    if not content.endswith("\n"):
        content += "\n"
    return f"{marker}{info}\n{content}{marker}\n"
