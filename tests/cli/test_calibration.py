"""C5: adoption rates derived from Runs, intake records and Objections; fake tools only."""

import json
import os
import sys

import pytest
from typer.testing import CliRunner

from toulmin.cli.app import app
from toulmin.core.codec import decode
from toulmin.protocols.calibration import calibration, render

RUNS = "projects/demo/runs"

FAKE = r"""
import json, os, sys, pathlib
if sys.argv[1:3] == ["login", "status"]:
    sys.exit(0)
sys.stdin.read()
if os.environ.get("FAKE_FAIL") == TOOL:
    print("usage limit reached", file=sys.stderr)
    sys.exit(2)
text = ("Review prose.\n\n```yaml\n- label: draft-1\n  target: C-001\n  severity: major\n"
        "  content: The load is unspecified.\n  grounds: No trace.\n"
        "- label: draft-2\n  target: C-001\n  severity: minor\n"
        "  content: The baseline is old.\n  grounds: It predates batching.\n```\n")
if TOOL == "claude":
    print(json.dumps({"result": text, "session_id": "s", "is_error": False,
                      "modelUsage": {"fake-claude-model": {}}}))
else:
    print(json.dumps({"type": "thread.started", "thread_id": "t"}))
    pathlib.Path(sys.argv[sys.argv.index("-o") + 1]).write_text(text)
    print(json.dumps({"type": "turn.completed", "usage": {
        "input_tokens": 5000, "cached_input_tokens": 4000, "output_tokens": 600}}))
"""

CONFIG = """
[review]
max_runs = 8
parallel = 2
timeout_seconds = 30
personas = ["reviewer-skeptic"]
models = ["claude", "codex"]

[models.claude]
adapter = "claude-code"

[models.codex]
adapter = "codex"
model = "fake-codex-model"
env = {{ CODEX_HOME = "{home}" }}
"""


@pytest.fixture
def bench(populated, tmp_path, monkeypatch):
    monkeypatch.delenv("TOULMIN_ACTOR", raising=False)
    monkeypatch.delenv("FAKE_FAIL", raising=False)
    folder = tmp_path / "fake-bin"
    folder.mkdir()
    for tool in ("claude", "codex"):
        script = folder / tool
        script.write_text(f"#!{sys.executable}\nTOOL = {tool!r}\n{FAKE}")
        script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ['PATH']}")
    home = tmp_path / "codex-home"
    home.mkdir()
    (populated / "tools/models.toml").write_text(CONFIG.format(home=home))
    return populated


def invoke(root, *arguments):
    return CliRunner().invoke(app, [*arguments, "--root", str(root)])


def confirmed(root, *arguments):
    return invoke(root, *arguments, "--confirmed-by", "Researcher", "--confirm")


def output(root, run_id):
    return decode((root / RUNS / f"{run_id}.md").read_bytes()).header["output"] + "/output.md"


def run_of(root, model):
    """Sessions run in parallel, so Run numbers follow completion order; find by model."""
    for path in sorted((root / RUNS).glob("R-*.md")):
        if decode(path.read_bytes()).header["model"] == model:
            return path.stem
    raise AssertionError(model)


def files(root):
    return {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


@pytest.fixture
def decided(bench):
    """claude: take draft-1, reject draft-2. codex: draft-1 at another severity, draft-2 open."""
    assert confirmed(bench, "review", "demo").exit_code == 0
    first = output(bench, run_of(bench, "fake-claude-model"))
    claude = confirmed(bench, "intake", "demo", first, "--take", "draft-1",
                       "--reject", "draft-2=Out of scope.")  # fmt: skip
    assert claude.exit_code == 0, claude.output
    codex = confirmed(
        bench,
        "intake",
        "demo",
        output(bench, run_of(bench, "fake-codex-model")),
        "--take",
        "draft-1:minor",
    )
    assert codex.exit_code == 0, codex.output
    return bench


def table(text, title):
    section = text.split(f"## {title}\n\n", 1)[1].split("\n\n", 1)[0]
    return [line for line in section.splitlines()[2:]]


def test_report_counts_outcomes_per_model_role_and_operation(decided):
    before = files(decided)
    result = invoke(decided, "calibration")
    assert result.exit_code == 0, result.output
    text = result.stdout
    assert files(decided) == before  # printing writes nothing
    assert table(text, "Review drafts by model and role")[1:] == [
        "| fake-claude-model | reviewer-skeptic | 2 | 1 | 0 | 1 | 0 | 0 | 50% |",
        "| fake-codex-model | reviewer-skeptic | 2 | 0 | 1 | 0 | 0 | 1 | 100% |",
    ]
    assert "| review | example-model | reviewer | 1 | 1 | 0 |" in text
    assert table(text, "Review drafts by role")[-1] == (
        "| reviewer-skeptic | 4 | 1 | 1 | 1 | 0 | 1 | 67% |"
    )
    assert table(text, "Objections created from review drafts, by current status") == [
        "| fake-claude-model | reviewer-skeptic | 1 | 0 | 0 | 0 |",
        "| fake-codex-model | reviewer-skeptic | 1 | 0 | 0 | 0 |",
    ]
    usage = text.split("## Token usage by operation\n", 1)[1].split("\n## ", 1)[0]
    assert usage.strip().splitlines()[-3:] == [
        "| review | example-model | reviewer | 1 | 0 | - | - | - |",
        "| review | fake-claude-model | reviewer-skeptic | 1 | 0 | - | - | - |",
        "| review | fake-codex-model | reviewer-skeptic | 1 | 1 | 5000 | 4000 | 600 |",
    ]  # R6: only what a tool reported
    # The example Run's output has no draft block: reported, never guessed.
    assert "demo/R-001: drafts not counted" in text


def test_duplicates_are_separate_and_excluded_from_adoption_and_objection_status(decided):
    before = (
        render(calibration(decided), None)
        .split("## Objections created from review drafts, by current status", 1)[1]
        .split("## Token usage", 1)[0]
    )
    source = output(decided, run_of(decided, "fake-codex-model"))
    result = confirmed(decided, "intake", "demo", source, "--duplicate", "draft-2=O-001")
    assert result.exit_code == 0, result.output
    report = calibration(decided)
    tally = report.groups[("review", "fake-codex-model", "reviewer-skeptic")]
    assert (tally.drafts, tally.partly, tally.duplicate, tally.rejected, tally.pending) == (
        2,
        1,
        1,
        0,
        0,
    )
    text = render(report, None)
    assert "| Duplicate |" in text
    assert "| fake-codex-model | reviewer-skeptic | 2 | 0 | 1 | 0 | 1 | 0 | 100% |" in text
    assert "fake-codex-model: re-found existing Objections: 1" in text
    assert "A duplicate re-finds an existing Objection; it is neither adopted nor rejected." in text
    assert (
        text.split("## Objections created from review drafts, by current status", 1)[1].split(
            "## Token usage", 1
        )[0]
        == before
    )


def test_only_duplicates_have_no_adoption_denominator(bench):
    assert confirmed(bench, "review", "demo").exit_code == 0
    source = output(bench, run_of(bench, "fake-codex-model"))
    result = confirmed(
        bench,
        "intake",
        "demo",
        source,
        "--duplicate",
        "draft-1=O-001",
        "--duplicate",
        "draft-2=O-001",
    )
    assert result.exit_code == 0, result.output
    text = render(calibration(bench), None)
    assert "| fake-codex-model | reviewer-skeptic | 2 | 0 | 0 | 0 | 2 | 0 | - |" in text


def test_objection_status_follows_later_rulings(decided):
    claude = run_of(decided, "fake-claude-model")
    path = next(
        item
        for item in sorted((decided / "projects/demo/objections").glob("O-*.md"))
        if decode(item.read_bytes()).header["source"].get("ref") == claude
    )
    path.write_text(
        path.read_text()
        .replace("status: open", "status: answered")
        .replace("## Response\n", "## Response\nThe trace is now named.\n")
    )
    report = calibration(decided, "demo")
    key = ("review", "fake-claude-model", "reviewer-skeptic")
    assert report.groups[key].objections == {"answered": 1}


def test_failed_runs_are_counted_without_drafts(bench, monkeypatch):
    monkeypatch.setenv("FAKE_FAIL", "codex")
    confirmed(bench, "review", "demo")
    report = calibration(bench)
    failed = report.groups[("review", "fake-codex-model", "reviewer-skeptic")]
    assert (failed.runs, failed.completed, failed.failed, failed.drafts) == (1, 0, 1, 0)


def test_write_regenerates_the_same_report_under_global_calibration(decided):
    first = invoke(decided, "calibration", "--write")
    assert first.exit_code == 0, first.output
    path = decided / "global/calibration/calibration.md"
    assert "Written: global/calibration/calibration.md" in first.stdout
    text = path.read_text()
    assert text.startswith("# Calibration report\n") and "Regenerate with" in text
    path.write_text("edited by hand\n")
    assert invoke(decided, "calibration", "--write").exit_code == 0
    assert path.read_text() == text  # derived from files only; hand edits do not survive
    scoped = invoke(decided, "calibration", "--project", "demo", "--write")
    assert scoped.exit_code == 0, scoped.output
    assert (
        "Scope: project demo (demo)"
        in (decided / "global/calibration/calibration-demo.md").read_text()
    )


def test_an_unknown_project_is_an_error(bench):
    result = invoke(bench, "calibration", "--project", "missing")
    assert result.exit_code == 1 and "missing" in result.output


def test_empty_workbench_renders_a_complete_report(workbench):
    text = render(calibration(workbench), None)
    assert "| - | - | - | 0 | 0 | 0 |" in text and "Nothing; every file was readable." in text
    json.dumps(text)  # plain text, nothing else
