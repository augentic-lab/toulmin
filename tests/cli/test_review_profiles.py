"""R11 bounded round planning and approval against fake providers only."""

import hashlib
import json
import os
import sys
from pathlib import Path
from shutil import which

import pytest
from typer.testing import CliRunner

from tests.cli import test_review_proposals as legacy
from toulmin.adapters.config import load_config
from toulmin.cli import decide
from toulmin.cli.app import app
from toulmin.core.codec import decode
from toulmin.core.project_proposals import validate_review_request
from toulmin.core.review_plan import PLAN_FILE, decode_plan

ALL = '["reviewer-skeptic", "reviewer-industry", "reviewer-theorist", "reviewer-why-not-x"]'
PROFILES = """
[profiles.hypothesis]
description = "Hypothesis focus; engineering and alternatives omitted"
personas = ["reviewer-skeptic", "reviewer-theorist"]
models = ["claude", "codex"]
synthesizer = "claude"
[profiles.full]
description = "Four roles"
personas = ALL_ROLES
models = ["claude", "codex"]
synthesizer = "codex"
""".replace("ALL_ROLES", ALL)


@pytest.fixture
def profiles(populated, tmp_path, monkeypatch):
    folder = tmp_path / "fake-profile-bin"
    folder.mkdir()
    body = legacy.RESPOND.replace(
        '{"prompt": prompt}',
        '{"prompt": prompt, "argv": sys.argv, "cwd": os.getcwd(), "files": os.listdir(".")}',
    ).replace(
        '"is_error": False',
        '"is_error": False, "modelUsage": {os.environ.get("FAKE_SERVED_MODEL", '
        'sys.argv[sys.argv.index("--model")+1]): {}}, '
        '"usage": {"input_tokens": 10, "output_tokens": 20}, "total_cost_usd": 0.01',
    )
    for tool in ("claude", "codex"):
        script = folder / tool
        script.write_text(f"#!{sys.executable}\nTOOL={tool!r}\n{body}")
        script.chmod(0o755)
    log = tmp_path / "profile-log"
    log.mkdir()
    home = tmp_path / "profile-codex-home"
    home.mkdir()
    monkeypatch.setenv("PATH", str(folder) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.delenv("TOULMIN_ACTOR", raising=False)
    monkeypatch.setattr(decide, "_interactive", lambda: True)
    config = (
        legacy.CONFIG.format(home=home)
        .replace(
            'adapter = "claude-code"',
            'adapter = "claude-code"\nmodel = "fixture-claude"\neffort = "medium"',
        )
        .replace(
            'adapter = "codex"',
            'adapter = "codex"\nmodel = "fixture-codex"\neffort = "high"',
        )
        + PROFILES
    )
    (populated / "tools/models.toml").write_text(config)
    (populated / "projects/demo/sessions/private.md").write_text("COORDINATOR-SECRET")
    return populated, log


def invoke(root, *args, input=None):
    return CliRunner().invoke(app, [*args, "--root", str(root)], input=input)


def tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def request(root):
    return legacy.put(
        root,
        "review-20261118T100000Z-profile.md",
        legacy.REQUEST.replace("personas: [reviewer-skeptic]", "profile: hypothesis"),
    )


def test_profile_preview_shows_concrete_selection_coverage_and_total_without_writes(profiles):
    root, log = profiles
    before = tree(root)
    result = invoke(root, "review", "demo", "--profile", "hypothesis", "--dry-run")
    assert result.exit_code == 0, result.output
    for value in (
        "Profile: hypothesis",
        "fixture-claude",
        "fixture-codex",
        "effort medium",
        "effort high",
        "4 reviews + at most 1 synthesis = 5",
        "synthesis model claude",
        "reviewer-industry",
        "reviewer-why-not-x",
        "model/account access is not verified",
    ):
        assert value in result.output
    assert tree(root) == before and list(log.iterdir()) == []


def test_full_profile_refuses_eight_session_cap_but_nine_is_explicit(profiles):
    root, log = profiles
    before = tree(root)
    result = invoke(root, "review", "demo", "--profile", "full", "--dry-run")
    assert result.exit_code == 1 and "9 sessions" in result.output
    assert tree(root) == before and list(log.iterdir()) == []
    p = root / "tools/models.toml"
    p.write_text(p.read_text().replace("max_runs = 8", "max_runs = 9"))
    result = invoke(root, "review", "demo", "--profile", "full", "--dry-run")
    assert result.exit_code == 0 and "8 reviews + at most 1 synthesis = 9" in result.output
    assert list(log.iterdir()) == []


def test_profile_overrides_are_explicit_and_legacy_review_only_stays_unchanged(profiles):
    root, log = profiles
    result = invoke(
        root,
        "review",
        "demo",
        "--profile",
        "hypothesis",
        "--personas",
        "reviewer-skeptic",
        "--models",
        "codex",
        "--synthesizer",
        "codex",
        "--dry-run",
    )
    assert result.exit_code == 0, result.output
    assert "1 reviews + at most 1 synthesis = 2" in result.output
    assert "synthesis model codex" in result.output
    result = invoke(root, "review", "demo", "--dry-run")
    assert result.exit_code == 0 and "Plan: 2 sessions" in result.output
    assert "then synthesis" not in result.output and list(log.iterdir()) == []


def test_draft_persists_plain_profile_and_synthesizer_names_without_starting(profiles):
    root, log = profiles
    result = invoke(
        root, "draft", "review", "demo", "--profile", "hypothesis", "--synthesizer", "codex"
    )
    assert result.exit_code == 0, result.output
    path = root / result.output.strip().splitlines()[0]
    request_data = validate_review_request(decode(path.read_bytes()))
    assert request_data.profile == "hypothesis" and request_data.synthesizer == "codex"
    assert request_data.models is None and request_data.personas is None
    assert list(log.iterdir()) == []


def test_profile_request_accepts_the_same_names_as_configuration(profiles):
    root, log = profiles
    config = root / "tools/models.toml"
    config.write_text(config.read_text().replace("profiles.hypothesis", "profiles.1-hypothesis"))
    result = invoke(root, "draft", "review", "demo", "--profile", "1-hypothesis")
    assert result.exit_code == 0, result.output
    path = root / result.output.strip().splitlines()[0]
    assert validate_review_request(decode(path.read_bytes())).profile == "1-hypothesis"
    assert list(log.iterdir()) == []


@pytest.mark.parametrize(
    "change,problem",
    [
        (
            lambda s: s.replace('synthesizer = "claude"', 'synthesizer = "missing"'),
            "not configured",
        ),
        (lambda s: s.replace('synthesizer = "claude"', 'synthesizer = ""'), "synthesizer"),
        (lambda s: s.replace('model = "fixture-claude"', 'model = ""'), "explicit model"),
        (lambda s: s.replace('model = "fixture-claude"', 'model = "opus"'), "pinned model"),
        (lambda s: s.replace('model = "fixture-claude"', 'model = "opus[1m]"'), "pinned model"),
        (lambda s: s.replace('model = "fixture-claude"', 'model = "two words"'), "whitespace"),
        (lambda s: s.replace('effort = "high"', "effort = true"), "effort"),
        (lambda s: s.replace('effort = "high"', 'effort = ""'), "effort"),
        (
            lambda s: s.replace(
                'effort = "high"',
                'effort = "high"\nextra_args=["-c", "model_reasoning_effort=low"]',
            ),
            "conflicts",
        ),
        (
            lambda s: s.replace(
                'effort = "medium"', 'effort = "medium"\nextra_args=["--model", "other"]'
            ),
            "conflicts with profile",
        ),
        (
            lambda s: s.replace(
                'effort = "medium"', 'effort = "medium"\nextra_args=["--fallback-model", "other"]'
            ),
            "conflicts with profile",
        ),
        (
            lambda s: s.replace(
                'models = ["claude", "codex"]\nsynthesizer',
                'models = ["claude", "claude"]\nsynthesizer',
            ),
            "unique",
        ),
        (
            lambda s: s.replace(
                'description = "Four roles"', 'description = "Four roles"\nunknown=true'
            ),
            "unknown field",
        ),
    ],
)
def test_invalid_profile_config_starts_nothing_and_writes_nothing(profiles, change, problem):
    root, log = profiles
    p = root / "tools/models.toml"
    p.write_text(change(p.read_text()))
    before = tree(root)
    result = invoke(root, "review", "demo", "--profile", "hypothesis", "--dry-run")
    assert result.exit_code == 1 and problem in result.output, result.output
    assert tree(root) == before and list(log.iterdir()) == []


def test_unknown_profile_draft_does_not_publish_partial_file(profiles):
    root, log = profiles
    before = tree(root)
    result = invoke(root, "draft", "review", "demo", "--profile", "missing")
    assert result.exit_code == 1 and "not configured" in result.output
    assert tree(root) == before and list(log.iterdir()) == []


@pytest.mark.parametrize("choice", ["s\n", "r\nNot needed\n"])
def test_decide_skip_or_reject_starts_no_sessions(profiles, choice):
    root, log = profiles
    request(root)
    result = invoke(root, "decide", "--confirmed-by", "Researcher", "--no-notify", input=choice)
    assert result.exit_code == 0, result.output
    assert "4 reviews + at most 1 synthesis = 5" in result.output and list(log.iterdir()) == []


@pytest.mark.parametrize(
    "change", ["model", "synthesizer", "effort", "input", "environment", "synth-role", "command"]
)
def test_changed_plan_after_preview_refuses_before_marker_or_sessions(
    profiles, monkeypatch, change
):
    root, log = profiles
    relative = request(root)
    if change == "command":
        p = root / "tools/models.toml"
        executable = which("claude")
        assert executable is not None
        alternate = root / "other-bin" / "claude"
        alternate.parent.mkdir()
        alternate.write_bytes(Path(executable).read_bytes())
        alternate.chmod(0o755)
        p.write_text(
            p.read_text().replace(
                'adapter = "claude-code"',
                'adapter = "claude-code"\ncommand = ' + json.dumps(executable),
            )
        )

    def choose(self, choices):
        p = root / "tools/models.toml"
        s = p.read_text()
        if change == "model":
            p.write_text(s.replace("fixture-codex", "other-codex"))
        elif change == "synthesizer":
            p.write_text(s.replace('synthesizer = "claude"', 'synthesizer = "codex"'))
        elif change == "effort":
            p.write_text(s.replace('effort = "high"', 'effort = "low"'))
        elif change == "synth-role":
            p = root / "roles/synthesizer.md"
            p.write_text(p.read_text() + "\nA different synthesis criterion.\n")
        elif change == "environment":
            p.write_text(s.replace('effort = "medium"', 'effort = "medium"\nenv={EXTRA="changed"}'))
        elif change == "command":
            p.write_text(s.replace(json.dumps(executable), json.dumps(str(alternate))))
        else:
            p = root / "projects/demo/brief.md"
            p.write_text(p.read_text() + "\nA new input detail.\n")
        return "a"

    monkeypatch.setattr(decide.Run, "_choose", choose)
    result = invoke(root, "decide", "--confirmed-by", "Researcher", "--no-notify")
    assert result.exit_code == 0, result.output
    assert "changed since preview; nothing started" in result.output
    assert not (root / relative.replace(".md", ".outcome.md")).exists()
    assert list(log.iterdir()) == []


def test_applied_profile_runs_exact_isolated_sessions_and_archives_provenance(profiles):
    root, log = profiles
    request(root)
    result = invoke(root, "decide", "--confirmed-by", "Researcher", "--no-notify", input="a\n")
    assert result.exit_code == 0, result.output
    records = [json.loads(p.read_text()) for p in log.glob("*.json")]
    assert len(records) == 5
    snapshots = []
    for path in (root / "projects/demo/runs").glob("R-*.md"):
        doc = decode(path.read_bytes())
        archive = root / doc.header["output"]
        plan = archive / PLAN_FILE
        if not plan.exists():
            continue
        value = decode_plan(plan.read_bytes())
        snapshots.append(value)
        assert value["role"] == doc.header["role"]
        assert (
            value["input_sha256"]
            == hashlib.sha256((archive / "prompt.md").read_bytes()).hexdigest()
        )
        assert value["profile"] == "hypothesis" and value["total_sessions"] == 5
        assert str(root).encode() not in plan.read_bytes()
    assert len(snapshots) == 5 and len({s["round_id"] for s in snapshots}) == 1
    assert len({s["configuration_sha256"] for s in snapshots}) == 1
    assert len([s for s in snapshots if s["operation"] == "synthesis"]) == 1
    for record in records:
        assert "COORDINATOR-SECRET" not in record["prompt"]
        assert PLAN_FILE not in record["files"]
        if record["argv"][0].endswith("claude"):
            assert record["argv"][record["argv"].index("--effort") + 1] == "medium"
        else:
            assert 'model_reasoning_effort="high"' in record["argv"]
    assert not list((root / "projects/demo/objections").glob("O-002.md"))


def test_profile_failure_reports_actual_model_and_never_substitutes(profiles, monkeypatch):
    root, log = profiles
    monkeypatch.setenv("FAKE_SERVED_MODEL", "unexpected-model")
    result = invoke(
        root,
        "review",
        "demo",
        "--profile",
        "hypothesis",
        "--models",
        "claude",
        "--confirm",
        "--confirmed-by",
        "R",
    )
    assert result.exit_code == 1, result.output
    assert len(list(log.glob("*.json"))) == 2  # both reviews fail; synthesis skipped
    assert "provider reported model" in result.output
    for path in (root / "projects/demo/runs").glob("R-*.md"):
        doc = decode(path.read_bytes())
        if doc.header["role"] == "implementer":
            continue
        if doc.header["output"].endswith("20261031T100000Z-review"):
            continue
        assert doc.header["status"] == "failed" and doc.header["model"] == "unexpected-model"
        assert (root / doc.header["output"] / "output.md").is_file()


def test_typed_effort_is_additive_to_legacy_configuration(profiles):
    root, _ = profiles
    config = load_config(root)
    assert config.available["claude"].session_args == ("--effort", "medium")
    assert config.available["codex"].session_args == ("-c", 'model_reasoning_effort="high"')


def test_profile_does_not_depend_on_legacy_rotation_defaults(profiles):
    root, _ = profiles
    p = root / "tools/models.toml"
    p.write_text(p.read_text().replace('models = ["claude", "codex"]', "models = []", 1))
    result = invoke(root, "review", "demo", "--profile", "hypothesis", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "synthesis model claude" in result.output


def test_invalid_synthesizer_manifest_refuses_before_any_review(profiles):
    root, log = profiles
    (root / "roles/synthesizer.md").unlink()
    before = tree(root)
    result = invoke(
        root, "review", "demo", "--profile", "hypothesis", "--confirm", "--confirmed-by", "R"
    )
    assert result.exit_code == 1
    assert tree(root) == before and not list(log.iterdir())


def test_coordinator_edits_during_review_do_not_enter_synthesis(profiles, monkeypatch):
    from toulmin.adapters import review as adapter

    root, log = profiles
    planned = adapter.prepare_round(
        root, "demo", None, None, None, lambda _: None, profile="hypothesis"
    )
    original = adapter._execute

    def changed(root, project, config, tasks, actor, echo):
        completed = original(root, project, config, tasks, actor, echo)
        if tasks[0].kind == "review":
            p = root / "roles/synthesizer.md"
            p.write_text(p.read_text() + "\nUNAPPROVED-SYNTHESIZER-EDIT\n")
            p = root / "projects/demo/brief.md"
            p.write_text(p.read_text() + "\nUNAPPROVED-BRIEF-EDIT\n")
        return completed

    monkeypatch.setattr(adapter, "_execute", changed)
    result = adapter.execute_round(planned, "Researcher", lambda _: None)
    assert result.synthesis is not None and result.synthesis.status == "completed"
    messages = [json.loads(p.read_text())["prompt"] for p in log.glob("*.json")]
    assert len(messages) == 5
    assert all(
        "UNAPPROVED-SYNTHESIZER-EDIT" not in prompt and "UNAPPROVED-BRIEF-EDIT" not in prompt
        for prompt in messages
    )


def test_bounded_comparison_preserves_common_inputs_and_records_five_vs_nine(profiles):
    import shutil

    root, log = profiles
    broader = root.with_name("full-profile-comparison")
    shutil.copytree(root, broader)
    config = broader / "tools/models.toml"
    config.write_text(config.read_text().replace("max_runs = 8", "max_runs = 9"))
    for workspace, profile, expected in ((root, "hypothesis", 5), (broader, "full", 9)):
        result = invoke(
            workspace,
            "review",
            "demo",
            "--profile",
            profile,
            "--confirm",
            "--confirmed-by",
            "Fixture researcher",
        )
        assert result.exit_code == 0, result.output
        plans = [
            decode_plan(path.read_bytes())
            for path in (workspace / "projects/demo/runs").glob(f"*/{PLAN_FILE}")
        ]
        assert len(plans) == expected
        assert all(plan["total_sessions"] == expected for plan in plans)

    def inputs(workspace):
        return {
            (p["role"], p["model_alias"]): p["input_sha256"]
            for path in (workspace / "projects/demo/runs").glob(f"*/{PLAN_FILE}")
            if (p := decode_plan(path.read_bytes()))["operation"] == "review"
        }

    focused, full = inputs(root), inputs(broader)
    assert len(focused) == 4 and len(full) == 8
    assert all(full[key] == digest for key, digest in focused.items())
    assert len(list(log.glob("*.json"))) == 14
