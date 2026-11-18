"""Read tools/models.toml (Q24): adapters, model names, run cap and timeouts.

Model names are plain strings handed to the tool; nothing here enumerates vendors.
"""

import json
import re
import tomllib
from dataclasses import dataclass, field
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
    effort: str | None = None

    @property
    def session_args(self) -> tuple[str, ...]:
        if self.effort is None:
            return self.extra_args
        if self.adapter.name == "codex":
            return (*self.extra_args, "-c", "model_reasoning_effort=" + json.dumps(self.effort))
        return (*self.extra_args, "--effort", self.effort)


@dataclass(frozen=True)
class ReviewProfile:
    name: str
    description: str
    personas: tuple[str, ...]
    models: tuple[str, ...]
    synthesizer: str


@dataclass(frozen=True)
class ReviewConfig:
    max_runs: int
    parallel: int
    timeout_seconds: float
    personas: tuple[str, ...]
    models: tuple[str, ...]
    available: dict[str, ModelConfig]
    profiles: dict[str, ReviewProfile] = field(default_factory=dict)


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

    top = table(data, "", {"review", "models", "profiles"})
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
        entry = table(entry, field, {"adapter", "model", "command", "extra_args", "env", "effort"})
        adapter = ADAPTERS.get(entry.get("adapter", ""))
        if adapter is None:
            raise fail(f"{field}.adapter", f"expected one of {sorted(ADAPTERS)}")
        model = entry.get("model", "")
        command = entry.get("command", adapter.default_command)
        if not isinstance(model, str) or not isinstance(command, str) or not command.strip():
            raise fail(field, "model and command must be strings; command nonempty")
        extra = names(entry.get("extra_args", []), f"{field}.extra_args")
        effort = entry.get("effort")
        if effort is not None and (
            not isinstance(effort, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", effort)
        ):
            raise fail(f"{field}.effort", "expected a lowercase effort name or omission")
        if effort is not None and any(
            token.split("=", 1)[0] == "--effort" or "model_reasoning_effort" in token
            for token in extra
        ):
            raise fail(f"{field}.effort", "conflicts with effort in extra_args")
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
        available[name] = ModelConfig(
            name, adapter, model.strip(), command, extra, variables, effort
        )
    profiles: dict[str, ReviewProfile] = {}
    entries = top.get("profiles", {})
    if not isinstance(entries, dict):
        raise fail("profiles", "expected a table")
    for name, value in entries.items():
        label = f"profiles.{name}"
        if not MODEL_NAME.fullmatch(name):
            raise fail(label, "expected lowercase letters, digits and hyphens")
        entry = table(value, label, {"description", "personas", "models", "synthesizer"})
        roles = names(entry.get("personas"), label + ".personas")
        chosen = names(entry.get("models"), label + ".models")
        synthesizer = entry.get("synthesizer")
        description = entry.get("description", "Only the listed roles are covered.")
        if not roles or len(set(roles)) != len(roles) or not all(roles):
            raise fail(label + ".personas", "expected nonempty unique role names")
        if not chosen or len(set(chosen)) != len(chosen) or not all(chosen):
            raise fail(label + ".models", "expected nonempty unique model names")
        if not isinstance(synthesizer, str) or not synthesizer.strip():
            raise fail(label + ".synthesizer", "explicit synthesizer model name required")
        if not isinstance(description, str) or not description.strip():
            raise fail(label + ".description", "expected nonempty text")
        for alias in (*chosen, synthesizer):
            if alias not in available:
                raise fail(label, f"model {alias!r} not configured")
            explicit_model(available[alias])
        profiles[name] = ReviewProfile(name, description, roles, chosen, synthesizer)
    return ReviewConfig(
        max_runs=int(positive(review.get("max_runs"), "review.max_runs", True)),
        parallel=int(positive(review.get("parallel", 1), "review.parallel", True)),
        timeout_seconds=positive(review.get("timeout_seconds"), "review.timeout_seconds", False),
        personas=names(review.get("personas", []), "review.personas"),
        models=names(review.get("models", []), "review.models"),
        available=available,
        profiles=profiles,
    )


def explicit_model(entry: ModelConfig) -> None:
    """Profiles must not hide native defaults or conflicting/fallback model selectors."""
    if not entry.model:
        raise FormatError(f"{entry.name}: profile requires an explicit model ID")
    if any(character.isspace() or ord(character) < 32 for character in entry.model):
        raise FormatError(f"{entry.name}: profile model ID must not contain whitespace or controls")
    if entry.adapter.name == "claude-code" and entry.model.removesuffix("[1m]") in {
        "default",
        "best",
        "opus",
        "sonnet",
        "haiku",
        "opusplan",
    }:
        raise FormatError(f"{entry.name}: profile requires a pinned model ID, not {entry.model}")
    for token in entry.extra_args:
        option = token.split("=", 1)[0]
        if option == "--effort" or "model_reasoning_effort" in token:
            raise FormatError(f"{entry.name}: profile effort must use the typed effort field")
        if option in {"--model", "-m", "--fallback-model", "--fallback-models"} or (
            token.startswith("-m") and token != "-m"
        ):
            raise FormatError(
                f"{entry.name}: model/fallback selector in extra_args conflicts with profile"
            )
