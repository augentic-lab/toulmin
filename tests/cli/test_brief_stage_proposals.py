"""H5: Brief proposals and stage proposals decided in ``toulmin decide``; temporary files only."""

import hashlib

import pytest
from typer.testing import CliRunner

from toulmin.cli import decide
from toulmin.cli.app import app
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError
from toulmin.core.project_proposals import Outcome, render_outcome, validate_outcome
from toulmin.protocols import project_proposals
from toulmin.protocols.handoff import draft_handoff
from toulmin.protocols.status import project_status

FOLDER = "projects/demo/runs/proposals"
BRIEF = "projects/demo/brief.md"
PROJECT = "projects/demo/PROJECT.md"
DECISION = (
    "---\nschema_version: 1\nstatus: active\nsource: {kind: human, actor: Agent}\n"
    "related: [C-001]\n---\n## Context\nThe core Claims are written.\n\n"
    "## Choice\nEnter critique.\n\n## Rejected alternatives\nKeep exploring.\n\n"
    "## Rationale\nThe framing is stable enough to be attacked.\n"
)


def sha(root, relative=BRIEF):
    return hashlib.sha256((root / relative).read_bytes()).hexdigest()


def brief(base, sections="## Kill criteria\nStop if [[C-001]] improves p99 by less than 5%.\n"):
    return (
        f'---\nschema_version: 1\nkind: brief-proposal\nbase_sha256: "{base}"\n---\n'
        f"## Why\nG2 needs written kill criteria.\n\n{sections}"
    )


def stage(decision="decision-20261109T100000Z-critique.md", current="explore", to="critique"):
    return (
        f"---\nschema_version: 1\nkind: stage-proposal\nfrom: {current}\nto: {to}\n"
        f"decision: {decision}\n---\n## Why\nThe core Claims exist; time to attack them.\n"
    )


def put(root, name, text):
    folder = root / FOLDER
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(text)
    return f"{FOLDER}/{name}"


def outcome(root, relative):
    path = root / project_proposals.outcome_path(relative)
    return validate_outcome(decode(path.read_bytes(), str(path)))


def snapshot(root):
    return {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


@pytest.fixture(autouse=True)
def researcher(monkeypatch):
    monkeypatch.delenv("TOULMIN_ACTOR", raising=False)
    monkeypatch.setattr(decide, "_interactive", lambda: True)


def run(root, answers=""):
    args = ["decide", "--root", str(root), "--confirmed-by", "Researcher"]
    return CliRunner().invoke(app, args, input=answers)


def test_a_brief_proposal_replaces_only_its_sections_after_a_diff(populated):
    original = (populated / BRIEF).read_text()
    sections = (
        "## Problem\nTail latency under bursts ([[C-001]]).\n\n"
        "## Kill criteria\nStop if [[C-001]] improves p99 by less than 5%.\n"
    )
    relative = put(populated, "brief-20261109T100000Z.md", brief(sha(populated), sections))
    before = snapshot(populated)
    result = run(populated, "s\n")
    assert "Brief proposal: " + relative in result.stdout
    assert "  +Stop if [[C-001]] improves p99 by less than 5%." in result.stdout
    assert "  --- brief.md (now)" in result.stdout
    assert snapshot(populated) == before
    result = run(populated, "a\n")
    assert result.exit_code == 0, result.output
    assert f"Updated: {BRIEF}" in result.stdout
    text = (populated / BRIEF).read_text()
    assert "## Kill criteria\nStop if [[C-001]] improves p99 by less than 5%.\n" in text
    assert "## Problem\nTail latency under bursts ([[C-001]]).\n\n## Why now\n" in text
    assert "G2 needs written kill criteria" not in text  # the Why is never written
    unchanged = original.split("## Why now")[1].split("## Kill criteria")[0]
    assert unchanged in text
    g2 = next(gate for gate in project_status(populated, "demo").gates if gate.gate == "G2")
    assert any(item.label.startswith("Kill criteria") and item.met for item in g2.items)
    assert outcome(populated, relative).result == BRIEF


def test_a_stale_or_invalid_brief_proposal_writes_nothing(populated):
    put(populated, "brief-20261109T100000Z-stale.md", brief("f" * 64))
    put(
        populated,
        "brief-20261109T100001Z-ref.md",
        brief(sha(populated), "## Kill criteria\n[[C-099]]\n"),
    )
    put(
        populated, "brief-20261109T100002Z-name.md", brief(sha(populated), "## Budget\nTwo GPUs.\n")
    )
    before = snapshot(populated)
    result = run(populated, "a\ns\ns\ns\n")
    assert "brief.md changed since this proposal was drafted" in result.stdout
    assert "Choose one of: reject, skip, quit" in result.stdout
    assert "C-099" in result.stdout.split("[2/3]")[1]
    assert "Budget: expected exactly one such section" in result.stdout
    assert snapshot(populated) == before


def test_an_interrupted_brief_application_is_only_recorded(populated):
    relative = put(populated, "brief-20261109T100000Z.md", brief(sha(populated)))
    shown = project_proposals.preview(populated, "demo", relative)
    marker = Outcome(
        relative, shown.sha256, "applying", "R", "2026-11-09T09:00:00Z", "a", None, None
    )
    (populated / project_proposals.outcome_path(relative)).write_bytes(render_outcome(marker))
    assert shown.after is not None
    (populated / BRIEF).write_bytes(shown.after)  # the write happened; the outcome did not
    result = run(populated, "a\n")
    assert result.exit_code == 0, result.output
    assert f"It already produced {BRIEF}" in result.stdout
    assert (populated / BRIEF).read_bytes() == shown.after
    assert outcome(populated, relative).disposition == "applied"


def test_a_stage_ruling_creates_its_decision_then_writes_stage(populated):
    workbench = populated
    decision = put(workbench, "decision-20261109T100000Z-critique.md", DECISION)
    proposal = put(workbench, "stage-20261109T100001Z-critique.md", stage())
    draft_handoff(workbench, "demo")  # drafted before the ruling: stale afterwards
    result = run(workbench, "a\na\n")
    assert result.exit_code == 0, result.output
    assert "Created: D-002" in result.stdout
    assert "Stage: explore -> critique, backed by D-002" in result.stdout
    assert "G1 readiness (advice; the ruling is yours): not met" in result.stdout
    assert "  -stage: explore" in result.stdout and "  +stage: critique" in result.stdout
    assert "Stage ruled: stage critique (D-002)" in result.stdout
    assert "changed by the stage ruling in this run" in result.stdout
    charter = decode((workbench / PROJECT).read_bytes()).header
    assert charter["stage"] == "critique" and charter["recent_decisions"][-1] == "D-002"
    assert outcome(workbench, decision).result == "D-002"
    assert outcome(workbench, proposal).result == "stage critique (D-002)"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (stage(current="critique", to="brief-final"), "PROJECT.md stage is explore, not critique"),
        (stage(decision="D-009"), "D-009"),
        (stage(to="explore"), "expected a stage other than from"),
        (stage(to="finished"), "expected one of explore"),
        (stage().replace("## Why\n", "## Notes\n"), "body.Why"),
    ],
)
def test_invalid_stage_proposals_write_nothing(workbench, text, message):
    put(workbench, "stage-20261109T100001Z.md", text)
    before = snapshot(workbench)
    result = run(workbench, "s\n")
    assert message in result.stdout
    assert "[r]eject / [s]kip / [q]uit" in result.stdout
    assert snapshot(workbench) == before


def test_a_stage_ruling_waits_for_its_decision_and_needs_an_active_one(populated):
    put(populated, "decision-20261109T100000Z-critique.md", DECISION)
    put(populated, "stage-20261109T100001Z-critique.md", stage())
    result = run(populated, "s\ns\n")
    assert "is not decided yet; decide it first" in result.stdout
    path = populated / "projects/demo/decisions/D-001.md"
    path.write_text(path.read_text().replace("status: active", "status: superseded"))
    with pytest.raises(FormatError):
        project_proposals.apply(populated, "demo", f"{FOLDER}/stage-20261109T100001Z-critique.md",
                                "R", "0" * 64, "a")  # fmt: skip
    assert decode((populated / PROJECT).read_bytes()).header["stage"] == "explore"
