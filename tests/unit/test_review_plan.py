"""Auxiliary profile records reject corrupt authority/provenance without any CLI."""

import copy
import hashlib
import json

import pytest

from toulmin.core.documents import FormatError
from toulmin.core.review_plan import decode_plan


def canonical(value):
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    ).encode()


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def record():
    def model(alias):
        return dict(
            alias=alias,
            adapter="fixture",
            requested_model="exact-id-" + alias,
            effort="high",
            command="fixture-command",
            extra_args_sha256=sha([]),
            environment_sha256=sha([]),
        )

    config = dict(
        personas=["reviewer-skeptic"],
        models=[model("a"), model("b")],
        synthesizer=model("s"),
        max_runs=3,
        parallel=2,
        timeout_seconds=10,
    )
    return dict(
        schema_version=1,
        profile="hypothesis",
        description="Bounded fixture",
        round_id="a" * 32,
        configuration=config,
        configuration_sha256=sha(config),
        role="reviewer-skeptic",
        model_alias="a",
        input_sha256="b" * 64,
        operation="review",
        review_sessions=2,
        synthesis_sessions=1,
        total_sessions=3,
        reported_model=None,
    )


def test_valid_auxiliary_record_has_no_vendor_or_model_enum():
    value = record()
    assert decode_plan(canonical(value)) == value
    value["configuration"]["models"][0]["adapter"] = "custom-tool"
    value["configuration_sha256"] = sha(value["configuration"])
    assert decode_plan(canonical(value)) == value


@pytest.mark.parametrize(
    "damage",
    [
        "version-bool",
        "extra-field",
        "bad-hash",
        "duplicate-roles",
        "duplicate-aliases",
        "review-using-synthesis-only",
        "synthesis-using-reviewer",
        "bad-synthesis-role",
        "wrong-count",
        "count-bool",
        "quota-overrun",
        "timeout-bool",
        "timeout-negative",
        "parallel-bool",
        "machine-command",
        "nontext-model",
        "missing-profile",
        "role-mismatch",
    ],
)
def test_corrupt_auxiliary_records_fail_as_domain_errors(damage):
    value = record()
    config = value["configuration"]
    if damage == "version-bool":
        value["schema_version"] = True
    elif damage == "extra-field":
        value["unknown"] = 1
    elif damage == "bad-hash":
        value["input_sha256"] = []
    elif damage == "duplicate-roles":
        config["personas"] *= 2
    elif damage == "duplicate-aliases":
        config["models"][1]["alias"] = "a"
    elif damage == "review-using-synthesis-only":
        value["model_alias"] = "s"
    elif damage == "synthesis-using-reviewer":
        value["operation"] = "synthesis"
        value["role"] = "synthesizer"
    elif damage == "bad-synthesis-role":
        value["operation"] = "synthesis"
        value["model_alias"] = "s"
    elif damage == "wrong-count":
        value["total_sessions"] = 4
    elif damage == "count-bool":
        value["review_sessions"] = True
    elif damage == "quota-overrun":
        config["max_runs"] = 2
    elif damage == "timeout-bool":
        config["timeout_seconds"] = True
    elif damage == "timeout-negative":
        config["timeout_seconds"] = -1
    elif damage == "parallel-bool":
        config["parallel"] = True
    elif damage == "machine-command":
        config["models"][0]["command"] = "/home/private/tool"
    elif damage == "nontext-model":
        config["models"][0]["requested_model"] = []
    elif damage == "missing-profile":
        value.pop("profile")
    else:
        value["role"] = "unselected-role"
    value["configuration_sha256"] = sha(config)
    with pytest.raises(FormatError):
        decode_plan(canonical(value))


def test_duplicate_json_keys_and_nonfinite_timeout_are_diagnosed():
    raw = canonical(record())
    with pytest.raises(FormatError, match="duplicate key"):
        decode_plan(
            raw.replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1')
        )
    value = copy.deepcopy(record())
    value["configuration"]["timeout_seconds"] = float("inf")
    with pytest.raises(FormatError):
        decode_plan(json.dumps(value).encode())
