"""`toulmin synthesize` and `crossval` against fake model executables; real tools never run."""

import json
import os
import sys
import time

import pytest
from typer.testing import CliRunner

from toulmin.cli.app import app
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError
from toulmin.core.synthesis import parse_points, parse_synthesis
from toulmin.protocols.inputs import resolve_inputs

RUNS = "projects/demo/runs"
QUESTION = f"{RUNS}/drafts/question.md"

# One body for both fakes: it answers according to the role file inlined in the prompt.
RESPOND = r"""
import json, os, re, sys, uuid, pathlib
prompt = sys.stdin.read()
log = pathlib.Path(os.environ["FAKE_LOG"])
(log / f"{TOOL}-{uuid.uuid4().hex}.json").write_text(json.dumps({"prompt": prompt}))
if os.environ.get("FAKE_FAIL") == TOOL:
    print("tool failure", file=sys.stderr)
    sys.exit(2)
if "<<<FILE roles/synthesizer.md>>>" in prompt:
    items = re.findall(r"^  - (R-\d{3,}/[A-Za-z0-9_-]+)$", prompt, re.M)
    if os.environ.get("FAKE_SYNTH") == "missing":
        items = items[:-1]
    runs = {item.split("/")[0] for item in items}
    if len(runs) > 1:
        groups = [{"group": "g1", "kind": "agreement", "drafts": items, "note": "All agree."}]
    else:
        groups = [{"group": f"g{i}", "kind": "singleton", "drafts": [item], "note": "Alone."}
                  for i, item in enumerate(items)]
    block = "\n".join(
        f"- group: {g['group']}\n  kind: {g['kind']}\n  drafts: [{', '.join(g['drafts'])}]\n"
        f"  note: {g['note']}" for g in groups)
    text = f"Synthesis prose.\n\n```yaml\n{block}\n```\n"
elif "<<<FILE roles/crossval.md>>>" in prompt:
    text = ("Answer prose.\n\n```yaml\n- label: p1\n  position: Polling wastes cycles.\n"
            "  grounds: Arithmetic.\n  target: C-001\n- label: p2\n  position: It matters.\n"
            "  grounds: Assertion.\n```\n")
else:
    text = ("Review prose.\n\n```yaml\n- label: draft-1\n  target: C-001\n  severity: major\n"
            "  content: The load is unspecified.\n  grounds: No trace.\n```\n")
if TOOL == "claude":
    print(json.dumps({"result": text, "session_id": "s-claude", "is_error": False}))
else:
    if sys.argv[1:3] == ["login", "status"]:
        sys.exit(0)
    print(json.dumps({"type": "thread.started", "thread_id": "t-codex"}))
    pathlib.Path(sys.argv[sys.argv.index("-o") + 1]).write_text(text)
"""

CONFIG = """
[review]
max_runs = {cap}
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


@pytest.fixture(autouse=True)
def no_operator_default(monkeypatch):
    monkeypatch.delenv("TOULMIN_ACTOR", raising=False)
    monkeypatch.delenv("FAKE_FAIL", raising=False)
    monkeypatch.delenv("FAKE_SYNTH", raising=False)


@pytest.fixture
def fakes(tmp_path, monkeypatch):
    folder = tmp_path / "fake-bin"
    folder.mkdir()
    for tool in ("claude", "codex"):
        login = "" if tool == "claude" else (
            'import sys\nif sys.argv[1:3] == ["login", "status"]:\n    sys.exit(0)\n'
        )  # fmt: skip
        script = folder / tool
        script.write_text(f"#!{sys.executable}\nTOOL = {tool!r}\n{login}{RESPOND}")
        script.chmod(0o755)
    log = tmp_path / "fake-log"
    log.mkdir()
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_LOG", str(log))
    return log


def configure(root, cap=8):
    home = root.parent / "codex-home"
    home.mkdir(exist_ok=True)
    (root / "tools/models.toml").write_text(CONFIG.format(cap=cap, home=home))


@pytest.fixture
def bench(populated, fakes):
    configure(populated)
    (populated / "projects/demo/sessions/secret.md").write_text("DISCUSSION-HISTORY\n")
    drafts = populated / RUNS / "drafts"
    drafts.mkdir()
    (drafts / "question.md").write_text("Is idle polling a real cost at moderate load?\n")
    return populated


def invoke(root, *arguments, confirm=True):
    command = [*arguments, "--root", str(root), "--confirmed-by", "Tianchi YU"]
    return CliRunner().invoke(app, command + (["--confirm"] if confirm else []))


def run(root, run_id):
    return decode((root / RUNS / f"{run_id}.md").read_bytes())


def prompts(log, tool=None):
    pattern = f"{tool}-*.json" if tool else "*.json"
    return [json.loads(path.read_text())["prompt"] for path in sorted(log.glob(pattern))]


def files(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def reviewed(bench):
    result = invoke(bench, "review", "demo")
    assert result.exit_code == 0, result.output
    assert {run(bench, r).header["role"] for r in ("R-002", "R-003")} == {"reviewer-skeptic"}
    return bench


def test_synthesis_sees_only_the_named_outputs_and_records_its_rotation(reviewed, fakes):
    result = invoke(reviewed, "synthesize", "demo", "R-002", "R-003")
    assert result.exit_code == 0, result.output
    assert "1 groups (0 disagreement, 1 agreement, 0 singleton) covering 2 items" in result.stdout
    synthesis = run(reviewed, "R-004")
    header = synthesis.header
    outputs = [f"{run(reviewed, r).header['output']}/output.md" for r in ("R-002", "R-003")]
    manifest = list(resolve_inputs(reviewed, "demo", "synthesizer").files)
    assert header["role"] == "synthesizer" and header["input_files"] == manifest + outputs
    assert header["output"].endswith("-synthesis-claude")
    assert "chosen by rotation: first synthesis in this project" in synthesis.body
    assert "Sources: R-002, R-003." in synthesis.body
    (prompt,) = [text for text in prompts(fakes) if "<<<FILE roles/synthesizer.md>>>" in text]
    for path in outputs:
        assert f"<<<FILE {path}>>>" in prompt
    assert "Test fixture: archived model output." not in prompt  # R-001 was not named
    assert "DISCUSSION-HISTORY" not in prompt
    assert "  - R-002/draft-1\n" in prompt and "  - R-003/draft-1\n" in prompt
    assert not (reviewed / "projects/demo/objections/O-002.md").exists()


def test_rotation_is_deterministic_and_override_is_recorded(reviewed):
    order = []
    for extra in ([], [], ["--model", "claude"]):
        result = invoke(reviewed, "synthesize", "demo", "R-002", "R-003", *extra)
        assert result.exit_code == 0, result.output
        latest = max((reviewed / RUNS).glob("R-*.md"), key=lambda p: int(p.stem[2:]))
        order.append(decode(latest.read_bytes()))
        time.sleep(1.1)  # archive names are per second
    assert [doc.header["output"].rsplit("-", 1)[-1] for doc in order] == [
        "claude",
        "codex",
        "claude",
    ]
    assert "previous synthesis R-004 used claude; next of [claude, codex]" in order[1].body
    assert "chosen by --model override (rotation would choose claude" in order[2].body


def test_intake_goes_back_to_the_original_run_and_label(reviewed):
    assert invoke(reviewed, "synthesize", "demo", "R-002", "R-003").exit_code == 0
    synthesis = run(reviewed, "R-004").header["output"] + "/output.md"
    refused = invoke(reviewed, "intake", "demo", synthesis, "--take", "g1")
    assert refused.exit_code == 1
    assert "R-004 is a synthesizer output, not a review" in refused.output
    original = run(reviewed, "R-003").header["output"] + "/output.md"
    taken = invoke(reviewed, "intake", "demo", original, "--take", "draft-1")
    assert taken.exit_code == 0, taken.output
    source = decode((reviewed / "projects/demo/objections/O-002.md").read_bytes()).header["source"]
    assert source == {"kind": "run", "ref": "R-003", "path": original}


def test_an_incomplete_synthesis_is_archived_but_flagged(reviewed, monkeypatch):
    monkeypatch.setenv("FAKE_SYNTH", "missing")
    result = invoke(reviewed, "synthesize", "demo", "R-002", "R-003")
    assert result.exit_code == 0, result.output
    assert "no usable group block" in result.stdout and "items not grouped: R-003/draft-1" in (
        result.stdout
    )
    assert "compare the cited outputs by hand" in run(reviewed, "R-004").body


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["R-002"], "name at least two Runs"),
        (["R-002", "R-002"], "duplicate Run"),
        (["R-002", "R-001"], "R-001: projects/demo/runs/20261031T100000Z-review/output.md:1"),
        (["R-002", "O-001"], "O-001: run: expected a Run ID"),
        (["R-002", "R-009"], "R-009"),
        (["R-002", "R-003", "--model", "gemini"], "gemini: model: not configured"),
    ],
)
def test_invalid_syntheses_start_nothing(reviewed, fakes, arguments, message):
    before, calls = files(reviewed), len(prompts(fakes))
    result = invoke(reviewed, "synthesize", "demo", *arguments)
    assert result.exit_code == 1
    assert message in result.output
    assert files(reviewed) == before and len(prompts(fakes)) == calls


def test_failed_syntheses_and_crossval_answers_cannot_be_mixed_in(reviewed, fakes, monkeypatch):
    monkeypatch.setenv("FAKE_FAIL", "codex")
    failed = invoke(reviewed, "synthesize", "demo", "R-002", "R-003", "--model", "codex")
    assert failed.exit_code == 1 and run(reviewed, "R-004").header["status"] == "failed"
    stale = invoke(reviewed, "synthesize", "demo", "R-002", "R-004")
    assert stale.exit_code == 1 and "status is failed" in stale.output
    monkeypatch.delenv("FAKE_FAIL")
    assert invoke(reviewed, "crossval", "demo", QUESTION, "--no-synthesis").exit_code == 0
    mixed = invoke(reviewed, "synthesize", "demo", "R-002", "R-005")
    assert mixed.exit_code == 1 and "do not mix cross-validation answers" in mixed.output
    unconfirmed = invoke(reviewed, "synthesize", "demo", "R-005", "R-006", confirm=False)
    assert unconfirmed.exit_code == 1 and "explicit --confirm required" in unconfirmed.output


def test_crossval_asks_every_model_the_same_question_then_synthesizes(bench, fakes):
    result = invoke(bench, "crossval", "demo", QUESTION)
    assert result.exit_code == 0, result.output
    assert "then synthesis by claude (chosen by rotation" in result.stdout
    answers = [run(bench, r) for r in ("R-002", "R-003")]
    assert {doc.header["role"] for doc in answers} == {"crossval"}
    assert all(QUESTION in doc.header["input_files"] for doc in answers)
    claude, codex = (
        next(text for text in prompts(fakes, tool) if "<<<FILE roles/crossval.md>>>" in text)
        for tool in ("claude", "codex")
    )
    assert claude == codex and "Is idle polling a real cost" in claude
    synthesis = run(bench, "R-004")
    assert synthesis.header["role"] == "synthesizer"
    assert "covering 4 items" in result.stdout
    assert [path for path in synthesis.header["input_files"] if "crossval" in path] == [
        f"{doc.header['output']}/output.md" for doc in answers
    ]


def test_crossval_skips_synthesis_without_two_usable_answers(bench, monkeypatch):
    monkeypatch.setenv("FAKE_FAIL", "codex")
    result = invoke(bench, "crossval", "demo", QUESTION)
    assert result.exit_code == 1
    assert "Synthesis skipped: 1 usable answers" in result.stdout
    assert not (bench / RUNS / "R-004.md").exists()


@pytest.mark.parametrize(
    ("arguments", "setup", "message"),
    [
        (
            ["projects/demo/brief.md"],
            None,
            "expected a file directly in projects/demo/runs/drafts/",
        ),
        ([f"{RUNS}/drafts/none.md"], None, "none.md"),
        ([QUESTION], lambda root: configure(root, cap=2), "3 sessions exceed the run cap of 2"),
        ([QUESTION, "--models", "codex,codex"], None, "duplicate"),
        ([QUESTION, "--synthesizer", "gemini"], None, "gemini: model: not configured"),
    ],
)
def test_invalid_crossval_rounds_start_nothing(bench, fakes, arguments, setup, message):
    if setup:
        setup(bench)
    before = files(bench)
    result = invoke(bench, "crossval", "demo", *arguments)
    assert result.exit_code == 1
    assert message in result.output
    assert files(bench) == before and not prompts(fakes)


def test_cap_counts_the_synthesis_only_when_requested(bench):
    configure(bench, cap=2)
    result = invoke(bench, "crossval", "demo", QUESTION, "--no-synthesis")
    assert result.exit_code == 0, result.output
    assert not (bench / RUNS / "R-004.md").exists()


KNOWN = ["R-002/a", "R-002/b", "R-003/a"]


def block(text):
    return f"Prose.\n\n```yaml\n{text}```\n"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("- group: g1\n  kind: agreement\n  drafts: [R-002/a, R-002/b]\n  note: n\n",
         "agreement groups cite items from at least two Runs"),
        ("- group: g1\n  kind: singleton\n  drafts: [R-002/a, R-003/a]\n  note: n\n",
         "a singleton cites exactly one item"),
        ("- group: g1\n  kind: consensus\n  drafts: [R-002/a]\n  note: n\n", "kind: expected"),
        ("- group: g1\n  kind: singleton\n  drafts: [R-009/a]\n  note: n\n",
         "R-009/a is not an item of this round"),
        ("- group: g1\n  kind: singleton\n  drafts: [R-002/a]\n  note: n\n"
         "- group: g2\n  kind: singleton\n  drafts: [R-002/a]\n  note: n\n",
         "R-002/a already placed in group g1"),
        ("- group: g1\n  kind: singleton\n  drafts: [R-002/a]\n  note: n\n",
         "items not grouped: R-002/b, R-003/a"),
        ("- group: g1\n  kind: singleton\n  drafts: [R-002/a]\n  target: O-001\n  note: n\n",
         "groups[0].target"),
        ("- group: g1\n  kind: singleton\n  drafts: [x]\n  note: n\n", "expected R-NNN/label"),
        ("- group: g1\n  kind: singleton\n  drafts: [R-002/a]\n", "note: required field missing"),
    ],
)  # fmt: skip
def test_synthesis_block_contract(text, message):
    with pytest.raises(FormatError) as error:
        parse_synthesis(block(text), "out.md", KNOWN)
    assert message in str(error.value)


def test_point_block_contract():
    good = "- label: p1\n  position: x\n  grounds: y\n  target: C-002\n"
    (point,) = parse_points(block(good), "out.md")
    assert (point.label, point.target, point.uncertainty) == ("p1", "C-002", None)
    for text, message in (
        (good + good, "duplicate label p1"),
        ("- label: p1\n  position: x\n  grounds: y\n  severity: major\n", "severity: unknown"),
        ("- label: p1\n  position: x\n  grounds: y\n  target: other/C-001\n", "this project"),
    ):
        with pytest.raises(FormatError, match=message):
            parse_points(block(text), "out.md")
