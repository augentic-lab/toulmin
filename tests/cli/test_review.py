"""`toulmin review` against fake `claude`/`codex` executables; real tools are never run."""

import json
import os
import sys
import time

import pytest
from typer.testing import CliRunner

from toulmin.adapters.config import load_config
from toulmin.cli.app import app
from toulmin.core.codec import decode
from toulmin.protocols.inputs import resolve_inputs

RUNS = "projects/demo/runs"
REVIEW = (
    "Review prose.\n\n```yaml\n- label: draft-1\n  target: C-001\n  severity: major\n"
    "  content: The load is unspecified.\n  grounds: The brief names no trace.\n```\n"
)

FAKE_CLAUDE = """
import json, os, sys, time, uuid, pathlib, subprocess
mode = os.environ.get("FAKE_CLAUDE", "ok")
prompt = sys.stdin.read()
log = pathlib.Path(os.environ["FAKE_LOG"])
record = {"argv": sys.argv, "cwd": os.getcwd(), "files": os.listdir("."), "prompt": prompt}
(log / f"claude-{uuid.uuid4().hex}.json").write_text(json.dumps(record))
if mode == "timeout":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    (log / "child.pid").write_text(str(child.pid))
    time.sleep(60)
if mode == "fail":
    print("authentication failed", file=sys.stderr)
    sys.exit(3)
if mode == "badjson":
    print("not json")
    sys.exit(0)
result = {"empty": "", "error": "Rate limited", "prose": "Prose only."}.get(mode, REVIEW)
print(json.dumps({"type": "result", "is_error": mode == "error", "result": result,
                  "session_id": "sess-claude", "modelUsage": {"fake-claude-model": {}}}))
"""

FAKE_CODEX = """
import json, os, sys, uuid, pathlib
mode = os.environ.get("FAKE_CODEX", "ok")
prompt = sys.stdin.read()
log = pathlib.Path(os.environ["FAKE_LOG"])
record = {"argv": sys.argv, "cwd": os.getcwd(), "files": os.listdir("."), "prompt": prompt,
          "codex_home": os.environ.get("CODEX_HOME")}
(log / f"codex-{uuid.uuid4().hex}.json").write_text(json.dumps(record))
print(json.dumps({"type": "thread.started", "thread_id": "thread-codex"}))
if mode == "fail":
    print("usage limit reached", file=sys.stderr)
    sys.exit(1)
if mode != "silent":
    pathlib.Path(sys.argv[sys.argv.index("-o") + 1]).write_text(REVIEW)
"""

CONFIG = """
[review]
max_runs = {cap}
parallel = 2
timeout_seconds = {timeout}
personas = ["reviewer-skeptic", "reviewer-theorist"]
models = ["claude", "codex"]

[models.claude]
adapter = "claude-code"

[models.codex]
adapter = "codex"
model = "codex-test-model"
extra_args = ["--ignore-user-config"]
env = {{ CODEX_HOME = "~/.codex-toulmin" }}
"""


@pytest.fixture(autouse=True)
def no_operator_default(monkeypatch):
    monkeypatch.delenv("TOULMIN_ACTOR", raising=False)


@pytest.fixture
def fakes(tmp_path, monkeypatch):
    folder = tmp_path / "fake-bin"
    folder.mkdir()
    for name, body in (("claude", FAKE_CLAUDE), ("codex", FAKE_CODEX)):
        script = folder / name
        script.write_text(f"#!{sys.executable}\nREVIEW = {REVIEW!r}\n{body}")
        script.chmod(0o755)
    log = tmp_path / "fake-log"
    log.mkdir()
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_LOG", str(log))
    return log


@pytest.fixture
def bench(populated, fakes):
    configure(populated)
    (populated / "projects/demo/sessions/secret.md").write_text("DISCUSSION-HISTORY\n")
    return populated


def configure(root, cap=8, timeout=30):
    (root / "tools/models.toml").write_text(CONFIG.format(cap=cap, timeout=timeout))


def calls(log, tool):
    return [json.loads(path.read_text()) for path in sorted(log.glob(f"{tool}-*.json"))]


def review(root, *arguments, confirm=True):
    command = ["review", "demo", "--root", str(root), "--confirmed-by", "Tianchi YU"]
    return CliRunner().invoke(app, [*command, *arguments] + (["--confirm"] if confirm else []))


def files(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def runs(root):
    found = {}
    for path in sorted((root / RUNS).glob("R-*.md")):
        if path.stem != "R-001":
            document = decode(path.read_bytes())
            found[(document.header["role"], document.header["output"].rsplit("-", 1)[-1])] = (
                document
            )
    return found


def test_round_records_one_completed_run_per_pair_with_manifest_inputs(bench, fakes):
    result = review(bench)
    assert result.exit_code == 0, result.output
    assert "Plan: 4 sessions (cap 8, parallel 2)" in result.stdout
    assert result.stdout.count("completed") == 4 and "1 drafts ready for intake" in result.stdout
    recorded = runs(bench)
    assert sorted(recorded) == [
        ("reviewer-skeptic", "claude"),
        ("reviewer-skeptic", "codex"),
        ("reviewer-theorist", "claude"),
        ("reviewer-theorist", "codex"),
    ]
    for (persona, model), run in recorded.items():
        header = run.header
        assert header["status"] == "completed" and header["source"]["kind"] == "human"
        assert header["input_files"] == list(resolve_inputs(bench, "demo", persona).files)
        assert header["output"].endswith(f"-review-{persona}-{model}")
        assert header["model"] == ("fake-claude-model" if model == "claude" else "codex-test-model")
        assert header["session_id"] == ("sess-claude" if model == "claude" else "thread-codex")
        assert isinstance(header["duration_seconds"], int | float)
        archive = bench / header["output"]
        assert (archive / "output.md").read_text() == REVIEW
        prompt = (archive / "prompt.md").read_text()
        for path in header["input_files"]:
            assert f"<<<FILE {path}>>>" in prompt
        assert "DISCUSSION-HISTORY" not in prompt and "<<<FILE projects/demo/sessions" not in prompt
    assert not list((bench / "projects/demo/objections").glob("O-002.md"))  # review never intakes
    assert CliRunner().invoke(app, ["status", "demo", "--root", str(bench)]).exit_code == 0

    output = recorded[("reviewer-skeptic", "codex")].header["output"] + "/output.md"
    taken = CliRunner().invoke(
        app,
        ["intake", "demo", output, "--take", "draft-1", "--root", str(bench)]
        + ["--confirmed-by", "Tianchi YU", "--confirm"],
    )
    assert taken.exit_code == 0, taken.output
    source = decode((bench / "projects/demo/objections/O-002.md").read_bytes()).header["source"]
    assert source == {
        "kind": "run",
        "ref": recorded[("reviewer-skeptic", "codex")].header["id"],
        "path": output,
    }


def test_sessions_are_isolated_read_only_and_tool_free(bench, fakes):
    assert review(bench, "--personas", "reviewer-skeptic").exit_code == 0
    (claude,) = calls(fakes, "claude")
    (codex,) = calls(fakes, "codex")
    argv = claude["argv"][1:]
    assert argv[:6] == ["-p", "--output-format", "json", "--tools", "", "--safe-mode"]
    assert "--no-session-persistence" in argv and "--model" not in argv
    assert codex["argv"][1:5] == ["exec", "--sandbox", "read-only", "--ephemeral"]
    assert codex["argv"][codex["argv"].index("--model") + 1] == "codex-test-model"
    assert codex["argv"][-2:] == ["--ignore-user-config", "-"]
    assert codex["codex_home"] == os.path.expanduser("~/.codex-toulmin")
    assert "overrides any general reply-style" in codex["prompt"]
    for call in (claude, codex):
        assert call["files"] == [] and not call["cwd"].startswith(str(bench))
        assert call["prompt"] == claude["prompt"]  # same input for every model
        assert "<<<FILE roles/reviewer-skeptic.md>>>" in call["prompt"]


@pytest.mark.parametrize(
    ("variable", "mode", "failure", "log"),
    [
        ("FAKE_CLAUDE", "fail", "exit status 3: authentication failed", True),
        ("FAKE_CLAUDE", "empty", "produced no output", False),
        ("FAKE_CLAUDE", "badjson", "unreadable JSON output", True),
        ("FAKE_CLAUDE", "error", "the tool reported an error: Rate limited", True),
        ("FAKE_CODEX", "fail", "exit status 1: usage limit reached", True),
        ("FAKE_CODEX", "silent", "produced no output", True),
    ],
)
def test_failures_become_failed_runs(bench, monkeypatch, variable, mode, failure, log):
    monkeypatch.setenv(variable, mode)
    model = "claude" if variable == "FAKE_CLAUDE" else "codex"
    result = review(bench, "--personas", "reviewer-skeptic", "--models", model)
    assert result.exit_code == 1
    (run,) = runs(bench).values()
    assert run.header["status"] == "failed"
    archive = bench / run.header["output"]
    assert failure in run.body and (archive / "prompt.md").is_file()
    assert (archive / "tool.log").is_file() == log
    assert CliRunner().invoke(app, ["status", "demo", "--root", str(bench)]).exit_code == 0


def test_timeout_kills_the_session_and_its_children(bench, fakes, monkeypatch):
    configure(bench, timeout=1)
    monkeypatch.setenv("FAKE_CLAUDE", "timeout")
    started = time.monotonic()
    result = review(bench, "--personas", "reviewer-skeptic", "--models", "claude")
    assert result.exit_code == 1 and time.monotonic() - started < 20
    (run,) = runs(bench).values()
    assert run.header["status"] == "failed" and "timed out after 1 s" in run.body
    child = int((fakes / "child.pid").read_text())
    for _ in range(50):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail("the timed-out session's child process survived")


def test_output_without_a_draft_block_is_completed_but_flagged(bench, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "prose")
    result = review(bench, "--personas", "reviewer-skeptic", "--models", "claude")
    assert result.exit_code == 0, result.output
    assert "no usable draft block" in result.stdout
    (run,) = runs(bench).values()
    assert run.header["status"] == "completed" and "take drafts in by hand" in run.body


@pytest.mark.parametrize(
    ("arguments", "setup", "message"),
    [
        (["--models", "claude,codex,claude"], None, "duplicate"),
        (["--models", "gemini"], None, "gemini: model: not configured"),
        (["--personas", "synthesizer"], None, "expected a critique role"),
        (["--personas", "scribe"], None, "no input manifest"),
        (["--claim", "C-009"], None, "C-009: claim: not among the inputs"),
        ([], lambda root: configure(root, cap=3), "4 sessions exceed the run cap of 3"),
        ([], lambda root: (root / "tools/models.toml").unlink(), "run init to create"),
        (
            [],
            lambda root: (root / "tools/models.toml").write_text("[review]\nmax_runs = 0\n"),
            "review.max_runs: expected a positive integer",
        ),  # fmt: skip
        (
            [],
            lambda root: (root / "tools/models.toml").write_text(
                "[review]\nmax_runs = 2\ntimeout_seconds = 5\n[models.x]\nadapter = 'gemini'\n"
            ),
            "models.x.adapter: expected one of",
        ),  # fmt: skip
        (
            [],
            lambda root: (root / "tools/models.toml").write_text(
                CONFIG.format(cap=8, timeout=5) + "colour = 1\n"
            ),
            "models.codex.colour: unknown",
        ),
        (
            [],
            lambda root: (root / "tools/models.toml").write_text(
                CONFIG.format(cap=8, timeout=5).replace(
                    'adapter = "codex"', 'adapter = "codex"\ncommand = "no-such-tool"'
                )
            ),
            "command 'no-such-tool' not found on PATH",
        ),  # fmt: skip
        (
            [],
            lambda root: (root / "tools/models.toml").write_text(
                CONFIG.format(cap=8, timeout=5).replace('"~/.codex-toulmin"', "1")
            ),
            "models.codex.env: expected a table of string variables",
        ),
    ],
)
def test_invalid_rounds_start_nothing_and_write_nothing(bench, fakes, arguments, setup, message):
    if setup:
        setup(bench)
    before = files(bench)
    result = review(bench, *arguments)
    assert result.exit_code == 1
    assert message in result.output
    assert files(bench) == before and not list(fakes.iterdir())


def test_dry_run_and_missing_confirmation_start_nothing(bench, fakes):
    before = files(bench)
    dry = CliRunner().invoke(app, ["review", "demo", "--root", str(bench), "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "reviewer-theorist x codex -> projects/demo/runs/" in dry.stdout
    unconfirmed = review(bench, confirm=False)
    assert unconfirmed.exit_code == 1 and "explicit --confirm required" in unconfirmed.output
    anonymous = CliRunner().invoke(app, ["review", "demo", "--root", str(bench), "--confirm"])
    assert anonymous.exit_code == 2
    assert files(bench) == before and not list(fakes.iterdir())


def test_init_template_configures_both_adapters_within_the_cap(workbench):
    config = load_config(workbench)
    assert set(config.available) == {"claude", "codex"}
    assert len(config.personas) * len(config.models) <= config.max_runs
    for persona in config.personas:
        assert resolve_inputs(workbench, "demo", persona).operation == "critique"
