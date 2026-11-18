"""R11: read-only profile comparisons from temporary, archived fake-session records."""

import hashlib
import json
from dataclasses import replace

import pytest

from toulmin.core.codec import decode, encode
from toulmin.core.review_plan import PLAN_FILE, canonical, checksum
from toulmin.core.usage import USAGE_FILE, Usage, encode_usage
from toulmin.protocols.calibration import calibration
from toulmin.protocols.profile_calibration import render_profile_calibration
from toulmin.protocols.review import ReviewOutcome, ReviewTask, archive_review
from toulmin.protocols.review_intake import intake_review

RAW = (
    "Review.\n```yaml\n- label: a\n  target: C-001\n  severity: major\n"
    "  content: Missing workload.\n  grounds: No distribution.\n"
    "- label: b\n  target: C-001\n  severity: minor\n"
    "  content: Missing baseline.\n  grounds: None named.\n```\n"
)


def model(alias="sol", requested="requested-sol", effort="high"):
    return {
        "alias": alias,
        "adapter": "fake",
        "requested_model": requested,
        "effort": effort,
        "command": "fake-cli",
        "extra_args_sha256": checksum([]),
        "environment_sha256": checksum({}),
    }


def archive(
    root,
    suffix="one",
    *,
    profile="hypothesis",
    effort="high",
    synthesis=False,
    failed=False,
    duration=1.5,
    usage=None,
    reported="served-sol",
    failed_output=False,
    review_role="reviewer-skeptic",
):
    config = {
        "personas": [review_role, "reviewer-theorist"],
        "models": [model(effort=effort), model("opus", "requested-opus")],
        "synthesizer": model("sonnet", "requested-sonnet", "medium"),
        "max_runs": 5,
        "parallel": 2,
        "timeout_seconds": 30,
    }
    role = "synthesizer" if synthesis else review_role
    prompt = f"Exact archived prompt for {role}: {suffix}.\n"
    plan = {
        "schema_version": 1,
        "profile": profile,
        "description": "Recorded experimental configuration; no quality claim.",
        "round_id": "a" * 32,
        "configuration": config,
        "configuration_sha256": checksum(config),
        "role": role,
        "model_alias": "sonnet" if synthesis else "sol",
        "input_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "operation": "synthesis" if synthesis else "review",
        "review_sessions": 4,
        "synthesis_sessions": 1,
        "total_sessions": 5,
        "reported_model": None,
    }
    task = ReviewTask(
        role,
        plan["model_alias"],
        f"projects/demo/runs/20261118T100000Z-{suffix}",
        ("projects/demo/claims/C-001.md",),
        prompt,
        kind=plan["operation"],
        plan=canonical(plan),
    )
    outcome = ReviewOutcome(
        "" if failed and not failed_output else RAW,
        reported or "requested-sol",
        "fake-session-id",
        duration,
        "fixture failure" if failed else None,
        usage=usage,
        reported_model=reported,
    )
    result = archive_review(root, "demo", task, outcome, "Fixture researcher")
    return result, root / task.archive


def snapshot(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def test_custom_critique_role_is_counted_without_a_reviewer_prefix(populated):
    result, _ = archive(populated, review_role="skeptic")
    before = snapshot(populated)
    report = render_profile_calibration(populated, "demo")
    assert f"demo/{result.run}" in report
    assert "| skeptic | sol |" in report
    assert "No profile-record diagnostics." in report
    assert snapshot(populated) == before


def test_groups_separate_changed_configs_and_keep_execution_unknowns_explicit(populated):
    usage = Usage("fake", 100, 70, 10, None, 0.025)
    archive(populated, usage=usage)
    archive(populated, "synthesis", synthesis=True, usage=replace(usage, cost_usd=None))
    archive(populated, "failure", failed=True, duration=None, reported=None)
    _, changed = archive(populated, "changed", effort="medium", duration=2.0)
    before = snapshot(populated)
    text = render_profile_calibration(populated, "demo")
    assert text == render_profile_calibration(populated, "demo")
    assert snapshot(populated) == before
    assert text.count("### Profile: hypothesis\n") == 2
    assert "| 2 | 1 | 2 | 1 |" in text
    assert "| Aggregate session-seconds | 3.0 | 1 |" in text
    assert "| input_tokens | 200 | 1 |" in text
    assert "| cached_input_tokens | 140 | 1 |" in text
    assert "| output_tokens | 20 | 1 |" in text
    assert "| reasoning_output_tokens | 0 | 3 |" in text
    assert "| Provider-reported USD | 0.025000 | 2 |" in text
    assert "requested-sol | high | served-sol | served-sol" in text
    assert "requested-sol | high | unknown | requested-sol" in text
    assert "requested-sonnet | medium | served-sol | served-sol" in text
    sidecar = json.loads((changed / PLAN_FILE).read_bytes())
    assert sidecar["configuration_sha256"] in text
    assert sidecar["input_sha256"] in text
    assert "human adjudication time and subscription\nusage are unmeasured" in text
    assert "No automatic ranking or cost/quality conclusion" in text


def test_intake_counts_researcher_adoption_and_duplicates_without_correctness_claim(populated):
    result, folder = archive(populated)
    raw = folder.relative_to(populated).as_posix() + "/output.md"
    intake_review(
        populated, "demo", raw, "Researcher", True, take={"a": None}, duplicate={"b": "O-001"}
    )
    text = render_profile_calibration(populated)
    assert "| 2 | 1 | 0 | 0 | 1 | 0 |" in text
    assert (
        "Researcher intake decisions (not correctness; duplicates excluded from adoption)" in text
    )
    assert f"demo/{result.run}" in text


def test_legacy_runs_stay_in_old_calibration_and_are_ignored_here(populated):
    before = snapshot(populated)
    assert calibration(populated, "demo").groups[("review", "example-model", "reviewer")].runs == 1
    assert "No valid recorded review-profile Runs." in render_profile_calibration(populated)
    assert "demo/R-001: profile provenance not counted" not in render_profile_calibration(populated)
    assert snapshot(populated) == before


@pytest.mark.parametrize("corruption", ["json", "digest", "role", "operation", "alias", "identity"])
def test_malformed_or_misattributed_sidecars_are_diagnosed_without_repair(populated, corruption):
    _, folder = archive(populated)
    path = folder / PLAN_FILE
    plan = json.loads(path.read_bytes())
    if corruption == "json":
        path.write_text('{"schema_version": 1, "schema_version": 1}')
    else:
        if corruption == "digest":
            plan["configuration_sha256"] = "0" * 64
        elif corruption == "role":
            plan["role"] = "reviewer-theorist"
        elif corruption == "operation":
            plan["operation"] = "synthesis"
        elif corruption == "alias":
            plan["model_alias"] = "sonnet"
        else:
            plan["reported_model"] = "different-provider-report"
        path.write_bytes(canonical(plan))
    before = snapshot(populated)
    text = render_profile_calibration(populated)
    assert "profile provenance not counted" in text
    assert "No valid recorded review-profile Runs." in text
    assert snapshot(populated) == before


def test_modified_archived_prompt_fails_exact_digest_check(populated):
    _, folder = archive(populated)
    (folder / "prompt.md").write_text("Modified prompt.\n")
    before = snapshot(populated)
    text = render_profile_calibration(populated)
    assert "input_sha256 does not match archived prompt.md" in text
    assert snapshot(populated) == before


@pytest.mark.parametrize("filename", [PLAN_FILE, "prompt.md", "output.md", USAGE_FILE, "intake.md"])
def test_auxiliary_symlinks_are_rejected_without_reading_targets(populated, tmp_path, filename):
    _, folder = archive(populated)
    secret = tmp_path / "outside-private.txt"
    secret.write_text("PRIVATE-FILE-CONTENT-MUST-NOT-APPEAR")
    path = folder / filename
    path.unlink(missing_ok=True)
    path.symlink_to(secret)
    text = render_profile_calibration(populated)
    assert "symlinks forbidden" in text
    assert "PRIVATE-FILE-CONTENT-MUST-NOT-APPEAR" not in text
    assert path.is_symlink()


@pytest.mark.parametrize("cost", [float("nan"), float("inf"), -1.0])
def test_nonfinite_or_negative_usage_is_unknown_with_a_diagnostic(populated, cost):
    _, folder = archive(populated)
    path = folder / USAGE_FILE
    path.write_bytes(encode_usage(Usage("fake", 20, 10, 5, cost_usd=cost)))
    before = snapshot(populated)
    text = render_profile_calibration(populated)
    assert "usage not counted" in text and "expected nonnegative finite" in text
    assert "| input_tokens | 0 | 1 |" in text
    assert "| Provider-reported USD | 0.000000 | 1 |" in text
    assert snapshot(populated) == before


def test_missing_completed_output_is_diagnosed_but_failed_empty_output_is_valid(populated):
    _, folder = archive(populated)
    (folder / "output.md").unlink()
    archive(populated, "failed", failed=True)
    text = render_profile_calibration(populated)
    assert "profile provenance not counted" in text
    assert "| 1 | 0 | 0 | 1 |" in text


def test_run_output_escape_and_project_symlink_are_diagnosed(populated, tmp_path):
    result, _ = archive(populated)
    run = populated / f"projects/demo/runs/{result.run}.md"
    document = decode(run.read_bytes())
    document.header["output"] = "../outside"
    run.write_bytes(encode(document))
    (populated / "projects/foreign").symlink_to(tmp_path, target_is_directory=True)
    before = snapshot(populated)
    text = render_profile_calibration(populated)
    assert "expected portable root-relative path" in text
    assert "foreign: project not counted" in text and "symlinks forbidden" in text
    assert snapshot(populated) == before


def test_missing_profile_name_is_distinct_from_a_literal_custom_name(populated):
    archive(populated, profile=None)
    archive(populated, "named", profile="custom")
    text = render_profile_calibration(populated)
    assert "### Profile: (custom selection; no named profile)" in text
    assert "### Profile: custom\n" in text


def test_missing_intake_is_no_decision_while_corrupt_intake_is_unknown(populated):
    _, first = archive(populated)
    archive(populated, "no-intake")
    (first / "intake.md").write_text("broken intake record")
    before = snapshot(populated)
    text = render_profile_calibration(populated)
    assert "intake decisions not counted" in text
    assert "| 4 | 0 | 0 | 0 | 0 | 1 |" in text
    assert snapshot(populated) == before


def test_malformed_usage_json_reports_unknown_without_rewriting(populated):
    _, folder = archive(populated)
    path = folder / USAGE_FILE
    path.write_text('{"schema_version": 1, "input_tokens": "not-a-count"}')
    before = snapshot(populated)
    text = render_profile_calibration(populated)
    assert "usage not counted" in text
    assert "| input_tokens | 0 | 1 |" in text
    assert snapshot(populated) == before


def test_recorded_intake_from_a_failed_partial_answer_is_still_a_researcher_decision(populated):
    _, folder = archive(populated, failed=True, failed_output=True)
    raw = folder.relative_to(populated).as_posix() + "/output.md"
    intake_review(populated, "demo", raw, "Researcher", True, duplicate={"a": "O-001"})
    text = render_profile_calibration(populated)
    assert "| 1 | 0 | 0 | 1 |" in text
    assert "| 2 | 0 | 0 | 0 | 1 | 0 |" in text
