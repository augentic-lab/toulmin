"""Read tools/models.toml (Q24): adapters, model names, run cap and timeouts.

Model names are plain strings handed to the tool; nothing here enumerates vendors.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from toulmin.adapters.base import Adapter
from toulmin.adapters.claude_code import ClaudeCode
from toulmin.adapters.codex import Codex
from toulmin.core.documents import FormatError
from toulmin.protocols.review import MODEL_NAME

CONFIG = "tools/models.toml"
ADAPTERS: dict[str, Adapter] = {adapter.name: adapter for adapter in (ClaudeCode(), Codex())}


@dataclass(frozen=True)
class ModelConfig:
    name: str
    adapter: Adapter
    model: str
    command: str
    extra_args: tuple[str, ...]
    env: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ReviewConfig:
    max_runs: int
    parallel: int
    timeout_seconds: float
    personas: tuple[str, ...]
    models: tuple[str, ...]
    available: dict[str, ModelConfig]


def load_config(root: Path) -> ReviewConfig:
    path = root / CONFIG
    if path.is_symlink() or not path.is_file():
        raise FormatError(f"{path}: expected a regular file; run init to create the template")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise FormatError(f"{path}: {error}") from error

    def fail(field: str, message: str) -> FormatError:
        return FormatError(f"{path}: {field}: {message}")

    def table(value: Any, field: str, keys: set[str]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise fail(field, "expected a table")
        unknown = sorted(set(value) - keys)
        if unknown:
            raise fail(f"{field}.{unknown[0]}", "unknown field")
        return value

    def names(value: Any, field: str) -> tuple[str, ...]:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise fail(field, "expected a list of strings")
        return tuple(value)

    def positive(value: Any, field: str, integer: bool) -> float:
        kinds: tuple[type, ...] = (int,) if integer else (int, float)
        if type(value) not in kinds or not value > 0 or value == float("inf"):
            raise fail(field, "expected a positive " + ("integer" if integer else "number"))
        return float(value)

    top = table(data, "", {"review", "models"})
    review = table(top.get("review"), "review", {"max_runs", "parallel", "timeout_seconds",
                                                 "personas", "models"})  # fmt: skip
    available: dict[str, ModelConfig] = {}
    models = top.get("models", {})
    if not isinstance(models, dict):
        raise fail("models", "expected a table")
    for name, entry in models.items():
        field = f"models.{name}"
        if not MODEL_NAME.fullmatch(name):
            raise fail(field, "expected lowercase letters, digits and hyphens")
        entry = table(entry, field, {"adapter", "model", "command", "extra_args", "env"})
        adapter = ADAPTERS.get(entry.get("adapter", ""))
        if adapter is None:
            raise fail(f"{field}.adapter", f"expected one of {sorted(ADAPTERS)}")
        model = entry.get("model", "")
        command = entry.get("command", adapter.default_command)
        if not isinstance(model, str) or not isinstance(command, str) or not command.strip():
            raise fail(field, "model and command must be strings; command nonempty")
        extra = names(entry.get("extra_args", []), f"{field}.extra_args")
        env = entry.get("env", {})
        if not isinstance(env, dict) or not all(
            isinstance(key, str) and key and "=" not in key and isinstance(value, str)
            for key, value in env.items()
        ):
            raise fail(f"{field}.env", "expected a table of string variables")
        variables = tuple(
            (key, str(Path(value).expanduser()) if value.startswith("~") else value)
            for key, value in sorted(env.items())
        )
        available[name] = ModelConfig(name, adapter, model.strip(), command, extra, variables)
    return ReviewConfig(
        max_runs=int(positive(review.get("max_runs"), "review.max_runs", True)),
        parallel=int(positive(review.get("parallel", 1), "review.parallel", True)),
        timeout_seconds=positive(review.get("timeout_seconds"), "review.timeout_seconds", False),
        personas=names(review.get("personas", []), "review.personas"),
        models=names(review.get("models", []), "review.models"),
        available=available,
    )
