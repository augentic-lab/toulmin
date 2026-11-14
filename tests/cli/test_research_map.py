"""V2: the research map, its shared rule table and --watch; temporary workbenches only."""

import json

from typer.testing import CliRunner

from toulmin.cli import research_map as view
from toulmin.cli.app import app
from toulmin.protocols.research_map import (
    AGENT,
    EITHER,
    YOU,
    Facts,
    next_moves,
    research_map,
)
from toulmin.protocols.research_workspace import render_state, research_state
from toulmin.protocols.status import GateItem, GateReadiness

OUTPUT = "projects/demo/runs/20261031T100000Z-review/output.md"
DRAFTS = (
    "Review prose.\n\n```yaml\n- label: draft-1\n  target: C-001\n  severity: major\n"
    "  content: The load is unspecified.\n  grounds: No trace.\n```\n"
)


def run(root, *arguments, columns=80):
    args = ["map", *arguments, "--root", str(root)]
    return CliRunner().invoke(app, args, env={"COLUMNS": str(columns)})


def snapshot(root):
    return {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_an_empty_project_shows_stage_gate_and_first_move(workbench):
    before = snapshot(workbench)
    result = run(workbench, "demo", columns=120)
    assert result.exit_code == 0, result.output
    text = result.stdout
    assert "● explore ─G1─ ○ critique ─G2─ ○ brief-final" in text
    assert "G1 -> critique  0/4  (advice; the stage changes only by your ruling)" in text
    assert "Waiting on you (toulmin decide): nothing" in text
    # P0 (question first): the first move is a measurement, not Claims drafted to fill G1.
    assert "  1 agent  Suggest and run the smallest next measurement for the project" in text
    assert "Draft the missing core Claims" not in text
    assert "Argument: no Claims yet." in text
    assert snapshot(workbench) == before  # read-only


def test_the_tree_links_evidence_objections_specs_and_plans(populated):
    result = run(populated, "demo", columns=200)
    assert result.exit_code == 0, result.output
    text = result.stdout
    assert "\nC-001 problem · core · proposed  " in text
    assert "├─ E-001 supports · " in text
    assert "├─ O-001 major · OPEN · ← R-001 example-model/reviewer  " in text
    assert "├─ S-001 spec · todo" in text
    assert "└─ plan: Measure the queueing-delay distribution" in text
    assert "Decisions\n  D-001 active  " in text
    assert (
        "Inspect open objections and draft responses or rulings for the researcher: O-001" in text
    )


def test_review_drafts_wait_for_intake_until_a_recommendation_covers_them(populated):
    (populated / OUTPUT).write_text(DRAFTS)
    report = research_map(populated, "demo")
    assert report.undecided == (("R-001", ("draft-1",)),)
    assert report.moves[0].text.startswith("Recommend intake for the review drafts of R-001")
    folder = populated / "projects/demo/runs/proposals"
    folder.mkdir()
    entry = json.dumps({"label": "draft-1", "outcome": "take", "reason": "Sound."})
    (folder / "intake-20261109T100000Z.md").write_text(
        "---\nschema_version: 1\nkind: intake-recommendation\n"
        f"output: {OUTPUT}\nrecommendations:\n  - {entry}\n---\n## Notes\nOne draft.\n"
    )
    report = research_map(populated, "demo")
    assert report.moves[0].text == "Run `toulmin decide` for 1 pending proposal(s)."
    assert not any(move.text.startswith("Recommend intake") for move in report.moves)
    text = run(populated, "demo", columns=200).stdout
    assert "Waiting on you (toulmin decide): 1\n  Intake recommendation: intake-" in text
    assert "Review drafts without intake: R-001: draft-1" in text


def gate(name, enters, met, *items):
    return GateReadiness(name, enters, met, tuple(items))


def facts(**changes):
    values = dict(
        stage="explore",
        invalid=False,
        gates=(),
        proposals=0,
        undecided=(),
        uncovered=(),
        objections=(),
        current_claims=False,
        reviewed=False,
    )
    values.update(changes)
    return Facts(**values)


def test_rule_table_rows_in_order():
    invalid = next_moves(facts(invalid=True, proposals=3))
    assert [(move.actor, move.how) for move in invalid] == [(YOU, "edit the files")]
    missing = gate("G1", "critique", False, GateItem("core novelty Claim (novelty)", False, ""))
    moves = next_moves(facts(proposals=2, gates=(missing,)))
    assert [move.actor for move in moves] == [YOU, AGENT]
    assert moves[0].text == "Run `toulmin decide` for 2 pending proposal(s)."
    assert moves[1].text.endswith("core novelty Claim (novelty)).")
    met = gate("G1", "critique", True)
    assert next_moves(facts(gates=(met,)))[0].text.startswith("G1 conditions hold")
    # Undecided review drafts may still block the gate: no stage suggestion yet.
    waiting = next_moves(facts(gates=(met,), undecided=(("R-002", ("d",)),), uncovered=("R-002",)))
    assert [move.how for move in waiting] == ["runs/proposals/intake-…"]
    g2 = gate(
        "G2",
        "brief-final",
        False,
        GateItem("no open fatal or major Objection", False, "O-001 (major)"),
        GateItem("C-001 supported or planned", False, "no verified support"),
        GateItem("Kill criteria written in brief.md", False, "empty"),
    )
    critique = facts(stage="critique", gates=(g2,), current_claims=True)
    moves = next_moves(facts(**{**critique.__dict__, "objections": (("O-001", "major"),)}))
    assert [move.how for move in moves] == [
        "runs/proposals/ruling-…",
        "runs/proposals/review-…",
        "runs/proposals/brief-…",
    ]
    reviewed = next_moves(facts(**{**critique.__dict__, "reviewed": True}))
    assert reviewed[-1].text == "Work toward G2: C-001 supported or planned (no verified support)."
    assert next_moves(facts(stage="build"))[0].actor == EITHER
    assert next_moves(facts(gates=(gate("G1", "critique", None),)))[0].actor == EITHER


def test_the_state_card_shows_the_same_suggestions(populated):
    card = render_state(research_state(populated, "demo"))
    moves = [move for move in research_map(populated, "demo").moves if move.actor != EITHER]
    assert moves
    for move in moves:
        who = "Agent" if move.actor == AGENT else "Researcher"
        assert f"- {who}: {move.text}" in card


def test_narrow_and_ascii_output(populated):
    result = run(populated, "demo", "--ascii", columns=48)
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert all(view.width_of(line) <= 48 for line in lines), lines
    assert lines[1] == "Stage 1/6: explore; next critique via G1"
    assert "●" not in result.stdout and "├" not in result.stdout and "|- E-001" in result.stdout


def test_claim_filter_and_unknown_claim(populated):
    text = run(populated, "demo", "--claim", "C-001", columns=200).stdout
    assert "C-001 problem" in text and "Decisions" not in text
    text = run(populated, "demo", "--claim", "C-009").stdout
    assert "C-009 is not a current Claim of demo." in text
    assert run(populated, "demo", "--claim", "nonsense").exit_code == 2


def test_invalid_data_is_shown_and_fails(populated):
    (populated / "projects/demo/claims/C-009.md").write_text("not a claim\n")
    result = run(populated, "demo")
    assert result.exit_code == 1
    assert "(data INVALID: partial view)" in result.stdout and "\nErrors\n" in result.stdout
    assert "Resolve the reported file errors" in result.stdout


def test_the_project_follows_the_current_directory(populated, monkeypatch):
    monkeypatch.chdir(populated / "projects/demo/claims")
    result = CliRunner().invoke(app, ["map"], env={"COLUMNS": "80"})
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("demo\n")


def test_workspace_scope_lists_projects(populated):
    result = run(populated)
    assert result.exit_code == 0, result.output
    assert "Waiting on you at the workspace (toulmin decide): nothing" in result.stdout
    assert "  demo\n    ● explore" in result.stdout
    assert "0 to decide; next: Inspect open objections" in result.stdout


def test_watch_redraws_only_when_files_change(populated):
    folder = populated / "projects/demo"
    marks = iter([1, 1, 2, 2, 3])
    shown: list[str] = []
    drawn = view.watch(
        lambda: "map\n", lambda: next(marks), 0.0, shown.append, sleep=lambda _: None, limit=5
    )
    assert drawn == 3 and shown[0].startswith(view.CLEAR)
    before = view.signature(folder)
    archive = populated / "projects/demo/runs/20261031T100000Z-review"
    (archive / "nested").mkdir()
    (archive / "nested/raw.log").write_text("model chatter")  # deep archive content: ignored
    assert view.signature(folder) == before
    (populated / "projects/demo/objections/O-001.md").write_text(
        (populated / "projects/demo/objections/O-001.md").read_text() + "\n"
    )
    assert view.signature(folder) != before
