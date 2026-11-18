"""L3 profile selection, nonsecret preview provenance and approval fingerprints."""

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from toulmin.adapters.config import ModelConfig, ReviewConfig, explicit_model
from toulmin.core.documents import FormatError
from toulmin.core.review_plan import canonical, checksum, decode_plan
from toulmin.protocols.review import ReviewTask


@dataclass(frozen=True)
class Selection:
    profile: str | None
    description: str
    personas: list[str]
    models: list[str]
    synthesizer: str | None


def select(
    config: ReviewConfig,
    personas: list[str] | None,
    models: list[str] | None,
    profile: str | None,
    synthesizer: str | None,
) -> Selection:
    chosen = config.profiles.get(profile) if profile is not None else None
    if profile is not None and chosen is None:
        raise FormatError(f"profile {profile!r} not configured in tools/models.toml")
    roles = (
        personas if personas is not None else list(chosen.personas if chosen else config.personas)
    )
    aliases = models if models is not None else list(chosen.models if chosen else config.models)
    synth = synthesizer if synthesizer is not None else chosen.synthesizer if chosen else None
    if chosen:
        for name in [*aliases, *([synth] if synth is not None else [])]:
            if name not in config.available:
                raise FormatError(f"model {name!r} not configured")
            explicit_model(config.available[name])
    return Selection(
        profile, chosen.description if chosen else "Custom review selection", roles, aliases, synth
    )


def model_snapshot(entry: ModelConfig) -> dict[str, Any]:
    return {
        "alias": entry.name,
        "adapter": entry.adapter.name,
        "requested_model": entry.model,
        "effort": entry.effort,
        "command": Path(entry.command).name,
        "extra_args_sha256": checksum(entry.extra_args),
        "environment_sha256": checksum(entry.env),
    }


def trace_plan(
    config: ReviewConfig, tasks: tuple[ReviewTask, ...], selection: Selection, synthesizer: str
) -> tuple[dict[str, Any], str]:
    snapshot = {
        "personas": selection.personas,
        "models": [model_snapshot(config.available[name]) for name in selection.models],
        "synthesizer": model_snapshot(config.available[synthesizer]),
        "max_runs": config.max_runs,
        "parallel": config.parallel,
        "timeout_seconds": config.timeout_seconds,
    }
    fingerprint = checksum(
        {
            "configuration": snapshot,
            "profile": selection.profile,
            "description": selection.description,
            # Public provenance keeps only basenames; approval must still bind the
            # actual executable paths, even when two paths share a basename.
            "commands": {
                name: config.available[name].command for name in {*selection.models, synthesizer}
            },
            "inputs": [
                (task.persona, task.model, hashlib.sha256(task.prompt.encode()).hexdigest())
                for task in tasks
            ],
        }
    )
    base = {
        "schema_version": 1,
        "profile": selection.profile,
        "description": selection.description,
        "round_id": uuid4().hex,
        "configuration": snapshot,
        "configuration_sha256": checksum(snapshot),
        "review_sessions": len(tasks),
        "synthesis_sessions": 1,
        "total_sessions": len(tasks) + 1,
        "reported_model": None,
    }
    return base, fingerprint


def traced(task: ReviewTask, base: dict[str, Any]) -> ReviewTask:
    value = {
        **base,
        "role": task.persona,
        "model_alias": task.model,
        "operation": task.kind,
        "input_sha256": hashlib.sha256(task.prompt.encode()).hexdigest(),
    }
    raw = canonical(value)
    decode_plan(raw)
    return replace(task, plan=raw)
