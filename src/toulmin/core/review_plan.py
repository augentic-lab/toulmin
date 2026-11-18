"""Tool-independent provenance for an explicitly configured review round (R11).

Sidecars are auxiliary archived records; they never change research object schemas
or become inputs to an independent reviewer. No provider-specific control lives here.
"""

import hashlib
import json
import math
import re
from typing import Any

from toulmin.core.documents import FormatError

PLAN_FILE = "review-plan.json"
SHA = re.compile(r"[0-9a-f]{64}")
KEYS = {
    "schema_version",
    "profile",
    "description",
    "round_id",
    "configuration",
    "configuration_sha256",
    "role",
    "model_alias",
    "input_sha256",
    "operation",
    "review_sessions",
    "synthesis_sessions",
    "total_sessions",
    "reported_model",
}


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    ).encode()


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def decode_plan(data: bytes, location: str = PLAN_FILE) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key " + key)
            result[key] = value
        return result

    try:
        if len(data) > 1_000_000:
            raise ValueError("plan exceeds 1 MB")
        value = json.loads(data, object_pairs_hook=pairs)
        if not isinstance(value, dict) or set(value) != KEYS:
            raise ValueError("invalid plan fields")
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("expected version 1")
        for key in ("configuration_sha256", "input_sha256"):
            if not isinstance(value[key], str) or SHA.fullmatch(value[key]) is None:
                raise ValueError("invalid " + key)
        if not isinstance(value["round_id"], str) or not re.fullmatch(
            r"[0-9a-f]{32}", value["round_id"]
        ):
            raise ValueError("invalid round identity")
        for key in ("description", "role", "model_alias"):
            if not isinstance(value[key], str) or not value[key].strip():
                raise ValueError("empty " + key)
        for key in ("profile", "reported_model"):
            if value[key] is not None and (
                not isinstance(value[key], str) or not value[key].strip()
            ):
                raise ValueError("invalid " + key)
        config = value["configuration"]
        if (
            not isinstance(config, dict)
            or set(config)
            != {"personas", "models", "synthesizer", "max_runs", "parallel", "timeout_seconds"}
            or checksum(config) != value["configuration_sha256"]
        ):
            raise ValueError("invalid configuration or digest")
        for key in ("personas", "models"):
            if not isinstance(config[key], list) or not config[key]:
                raise ValueError("empty configuration " + key)
        if not all(isinstance(role, str) and role for role in config["personas"]):
            raise ValueError("invalid personas")
        if len(set(config["personas"])) != len(config["personas"]):
            raise ValueError("duplicate personas")
        for key in ("max_runs", "parallel"):
            if type(config[key]) is not int or config[key] < 1:
                raise ValueError("invalid configuration " + key)
        duration = config["timeout_seconds"]
        if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
            raise ValueError("invalid configuration timeout")
        entries = [*config["models"], config["synthesizer"]]
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {
                "alias",
                "adapter",
                "requested_model",
                "effort",
                "command",
                "extra_args_sha256",
                "environment_sha256",
            }:
                raise ValueError("invalid model entry")
            for key in ("alias", "adapter", "command"):
                if not isinstance(entry[key], str) or not entry[key]:
                    raise ValueError("invalid model " + key)
            if not isinstance(entry["requested_model"], str):
                raise ValueError("invalid requested model")
            if entry["effort"] is not None and not isinstance(entry["effort"], str):
                raise ValueError("invalid effort")
            if "/" in entry["command"] or "\\" in entry["command"]:
                raise ValueError("machine path in public plan")
            for key in ("extra_args_sha256", "environment_sha256"):
                if not isinstance(entry[key], str) or SHA.fullmatch(entry[key]) is None:
                    raise ValueError("invalid model digest")
        aliases = [entry["alias"] for entry in config["models"]]
        if len(set(aliases)) != len(aliases):
            raise ValueError("duplicate model aliases")
        if value["model_alias"] not in {entry["alias"] for entry in entries}:
            raise ValueError("model alias not in plan")
        if value["operation"] not in {"review", "synthesis"}:
            raise ValueError("invalid operation")
        if value["operation"] == "review" and value["role"] not in config["personas"]:
            raise ValueError("role not in plan")
        if value["operation"] == "review" and value["model_alias"] not in aliases:
            raise ValueError("review model not selected")
        if value["operation"] == "synthesis" and (
            value["role"] != "synthesizer" or value["model_alias"] != config["synthesizer"]["alias"]
        ):
            raise ValueError("synthesis selection mismatch")
        for key in ("review_sessions", "synthesis_sessions", "total_sessions"):
            if type(value[key]) is not int or value[key] < 1:
                raise ValueError("invalid session counts")
        if (
            value["review_sessions"] != len(config["personas"]) * len(config["models"])
            or value["synthesis_sessions"] != 1
            or value["total_sessions"] != value["review_sessions"] + 1
        ):
            raise ValueError("inconsistent session counts")
        if value["total_sessions"] > config["max_runs"]:
            raise ValueError("plan exceeds quota cap")
        return value
    except (ValueError, UnicodeError, TypeError, OverflowError) as error:
        raise FormatError(f"{location}: invalid review plan: {error}") from error
