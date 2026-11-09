"""H4: review-round requests and intake recommendations in ``toulmin decide``.

Fake ``claude``/``codex`` executables answer by role; real tools are never run.
"""

import json
import os
import sys

import pytest
from typer.testing import CliRunner

from toulmin.cli import decide
from toulmin.cli.app import app
from toulmin.core.codec import decode
from toulmin.core.project_proposals import Outcome, render_outcome, validate_outcome
from toulmin.protocols import project_proposals

RUNS = "projects/demo/runs"
FOLDER = f"{RUNS}/proposals"

RESPOND = r"""
import json, os, re, sys, uuid, pathlib
if sys.argv[1:3] == ["login", "status"]:
    sys.exit(0)
prompt = sys.stdin.read()
log = pathlib.Path(os.environ["FAKE_LOG"])
(log / f"{TOOL}-{uuid.uuid4().hex}.json").write_text(json.dumps({"prompt": prompt}))
if "<<<FILE roles/synthesizer.md>>>" in prompt:
    items = re.findall(r"^  - (R-\d{3,}/[A-Za-z0-9_-]+)$", prompt, re.M)
    text = ("Synthesis prose.\n\n```yaml\n- group: g1\n  kind: agreement\n"
            f"  drafts: [{', '.join(items)}]\n  note: All agree.\n```\n")
else:
    text = ("Review prose.\n\n```yaml\n- label: draft-1\n  target: C-001\n  severity: major\n"
            "  content: The load is unspecified.\n  grounds: No trace.\n"
            "- label: draft-2\n  target: C-001\n  severity: minor\n"
            "  content: The baseline is old.\n  grounds: It predates batching.\n```\n")
if TOOL == "claude":
    print(json.dumps({"result": text, "session_id": "s-claude", "is_error": False}))
else:
    print(json.dumps({"type": "thread.started", "thread_id": "t-codex"}))
    pathlib.Path(sys.argv[sys.argv.index("-o") + 1]).write_text(text)
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
env = {{ CODEX_HOME = "{home}" }}
"""

REQUEST = (
    "---\nschema_version: 1\nkind: review-request\npersonas: [reviewer-skeptic]\n"
    "claims: [C-001]\n---\n## Why now\nC-001 was revised; it has not been reviewed since.\n"
)


@pytest.fixture(autouse=True)
def researcher(monkeypatch):
    monkeypatch.delenv("TOULMIN_ACTOR", raising=False)
    monkeypatch.setattr(decide, "_interactive", lambda: True)


@pytest.fixture
def fakes(tmp_path, monkeypatch):
    folder = tmp_path / "fake-bin"
    folder.mkdir()
    for tool in ("claude", "codex"):
        script = folder / tool
        script.write_text(f"#!{sys.executable}\nTOOL = {tool!r}\n{RESPOND}")
        script.chmod(0o755)
    log = tmp_path / "fake-log"
    log.mkdir()
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_LOG", str(log))
    return log


@pytest.fixture
def bench(populated, fakes):
    home = populated.parent / "codex-home"
    home.mkdir()
    (populated / "tools/models.toml").write_text(CONFIG.format(home=home))
    return populated


@pytest.fixture
def reviewed(bench):
    command = ["review", "demo", "--root", str(bench), "--confirmed-by", "R", "--confirm"]
    result = CliRunner().invoke(app, command)
    assert result.exit_code == 0, result.output
    return bench


def put(root, name, text):
    folder = root / FOLDER
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(text)
    return f"{FOLDER}/{name}"


def run(root, answers=""):
    args = ["decide", "--root", str(root), "--confirmed-by", "Researcher"]
    return CliRunner().invoke(app, args, input=answers)


def sessions(log):
    return sorted(path.name.split("-")[0] for path in log.glob("*.json"))


def outcome(root, relative):
    path = root / project_proposals.outcome_path(relative)
    return validate_outcome(decode(path.read_bytes(), str(path)))


def header(root, run_id):
    return decode((root / RUNS / f"{run_id}.md").read_bytes()).header


def output(root, run_id):
    return header(root, run_id)["output"] + "/output.md"


def recommendation(path, *entries):
    lines = "".join(f"  - {json.dumps(entry, ensure_ascii=False)}\n" for entry in entries)
    return (
        "---\nschema_version: 1\nkind: intake-recommendation\n"
        f"output: {path}\nrecommendations:\n{lines}---\n## Notes\nSynthesis g1 groups both.\n"
    )


def test_a_review_request_starts_only_on_apply_then_synthesizes(bench, fakes):
    relative = put(bench, "review-20261106T100000Z-c1.md", REQUEST)
    result = run(bench, "s\n")
    assert "Review round request: " + relative in result.stdout
    assert "Plan: 2 sessions" in result.stdout and "then synthesis by" in result.stdout
    assert "uses quota" in result.stdout
    assert sessions(fakes) == []  # previewing and skipping start nothing
    result = run(bench, "a\n")
    assert result.exit_code == 0, result.output
    assert len(sessions(fakes)) == 3  # two reviews, then one synthesis
    assert header(bench, "R-004")["role"] == "synthesizer"
    recorded = outcome(bench, relative)
    assert recorded.disposition == "applied" and recorded.approval_text == "toulmin decide: a"
    assert recorded.result == "reviews R-002 completed, R-003 completed; synthesis R-004 completed"
    assert "Nothing awaits your decision." in run(bench).stdout
    # The synthesis placement is shown beside each label of a later intake recommendation.
    put(
        bench,
        "intake-20261106T110000Z.md",
        recommendation(
            output(bench, "R-002"),
            {"label": "draft-1", "outcome": "take", "reason": "Shared by both reviews."},
            {"label": "draft-2", "outcome": "reject", "reason": "Out of scope."},
        ),
    )
    shown = run(bench, "s\ns\n").stdout
    assert "    Synthesis: R-004 g1 agreement with R-002/draft-2, R-003/draft-1" in shown
    assert ": All agree." in shown


def test_an_invalid_or_unplannable_request_starts_nothing(bench, fakes):
    put(bench, "review-20261106T100000Z-a.md", REQUEST.replace("## Why now\n", "## Notes\n"))
    put(bench, "review-20261106T100001Z-b.md", REQUEST.replace("[reviewer-skeptic]", "[nobody]"))
    result = run(bench, "a\ns\nr\nNo such persona.\n")
    assert "body.Why now" in result.stdout
    assert "Choose one of: reject, skip, quit" in result.stdout
    assert "Problem: " in result.stdout.split("[2/2]")[1]
    assert sessions(fakes) == []
    assert outcome(bench, f"{FOLDER}/review-20261106T100001Z-b.md").reason == "No such persona."


def test_an_interrupted_round_is_recorded_never_started_again(reviewed, fakes):
    relative = put(reviewed, "review-20261106T100000Z.md", REQUEST)
    sha = project_proposals.preview(reviewed, "demo", relative).sha256
    marker = Outcome(
        relative, sha, "applying", "Researcher", "2000-01-01T00:00:00Z", "a", None, None
    )
    (reviewed / project_proposals.outcome_path(relative)).write_bytes(render_outcome(marker))
    before = sessions(fakes)
    result = run(reviewed, "a\n")
    assert result.exit_code == 0, result.output
    assert "never started again" in result.stdout and "R-001, R-002, R-003" in result.stdout
    assert sessions(fakes) == before
    assert outcome(reviewed, relative).result == "interrupted; Runs archived: R-001, R-002, R-003"


def test_intake_is_decided_label_by_label_against_the_recommendation(reviewed):
    first = output(reviewed, "R-002")
    relative = put(
        reviewed,
        "intake-20261106T100000Z-r2.md",
        recommendation(
            first,
            {
                "label": "draft-1",
                "outcome": "take",
                "severity": "minor",
                "reason": "Real but small.",
            },
            {"label": "draft-2", "outcome": "reject", "reason": "Batching is out of scope."},
        ),
    )
    result = run(reviewed, "a\nr\n\n")  # as recommended; reject, keeping the proposed reason
    assert result.exit_code == 0, result.output
    assert "Review output: " + first + " (R-002)" in result.stdout
    assert "Recommended: take as minor - Real but small." in result.stdout
    assert "draft-1: partly as O-002 (R-002)" in result.stdout  # a severity override is partly
    assert "draft-2: rejected (R-002)" in result.stdout
    created = decode((reviewed / "projects/demo/objections/O-002.md").read_bytes()).header
    assert created["severity"] == "minor" and created["source"]["ref"] == "R-002"
    assert created["confirmed_by"]["actor"] == "Researcher"
    record = decode((reviewed / first.replace("output.md", "intake.md")).read_bytes())
    assert "Batching is out of scope." in str(record.header)
    assert outcome(reviewed, relative).result == first.replace("output.md", "intake.md")


def test_skipped_labels_stay_pending_and_quit_records_nothing(reviewed):
    second = output(reviewed, "R-003")
    relative = put(
        reviewed,
        "intake-20261106T100000Z-r3.md",
        recommendation(
            second,
            {"label": "draft-1", "outcome": "take", "reason": "Unspecified load is fatal-ish."},
            {"label": "draft-2", "outcome": "take", "reason": "Old baseline."},
        ),
    )
    result = run(reviewed, "o\nfatal\nq\n")
    assert "Nothing recorded for this output" in result.stdout
    assert not (reviewed / second.replace("output.md", "intake.md")).exists()
    result = run(reviewed, "t\ns\n")
    assert result.exit_code == 0, result.output
    assert "draft-1: taken as O-002 (R-003)" in result.stdout
    assert "stays pending" in result.stdout
    assert "Applied: 0 |" in result.stdout and "| Partly recorded: 1" in result.stdout
    assert not (reviewed / project_proposals.outcome_path(relative)).exists()
    result = run(reviewed, "r\nNot convinced.\n")  # only draft-2 is asked again
    assert "draft-1: already taken" in result.stdout and "(1/1) draft-2" in result.stdout
    assert outcome(reviewed, relative).disposition == "applied"


def test_a_recommendation_must_cover_every_label_of_a_review_output(reviewed):
    put(
        reviewed,
        "intake-20261106T100000Z-a.md",
        recommendation(
            output(reviewed, "R-002"), {"label": "draft-1", "outcome": "take", "reason": "x"}
        ),
    )
    put(
        reviewed,
        "intake-20261106T100001Z-b.md",
        recommendation(
            output(reviewed, "R-003"), {"label": "draft-9", "outcome": "take", "reason": "x"}
        ),
    )
    put(
        reviewed,
        "intake-20261106T100002Z-c.md",
        recommendation(
            output(reviewed, "R-002").replace("output.md", "missing.md"),
            {"label": "draft-1", "outcome": "take", "reason": "x"},
        ),
    )
    result = run(reviewed, "s\ns\ns\n")
    assert "no recommendation for draft-2; cover every label" in result.stdout
    assert "draft-9: no such draft label" in result.stdout
    assert "missing.md" in result.stdout
    assert not (reviewed / "projects/demo/objections/O-002.md").exists()


def test_inventory_follows_the_loop_order(populated):
    for name in (
        "review-20261106T100000Z.md",
        "ruling-20261106T100000Z.md",
        "claim-20261106T100000Z.md",
        "intake-20261106T100000Z.md",
    ):
        put(populated, name, "x\n")
    kinds = [item.kind for item in project_proposals.inventory(populated, "demo").items]
    assert kinds == ["intake", "claim", "ruling", "review"]
