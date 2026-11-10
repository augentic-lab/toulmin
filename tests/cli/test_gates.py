"""H2: G1/G2 readiness in ``status``; R5: G3-G5, deferred advice and stage warnings.

Read-only, temporary workbenches only.
"""

from dataclasses import replace
from pathlib import Path

from typer.testing import CliRunner

from toulmin.cli.app import app
from toulmin.core.codec import decode, encode
from toulmin.core.inspection import inspect_project
from toulmin.core.repository import Repository
from toulmin.protocols.research_map import move_facts, next_moves, research_map
from toulmin.protocols.research_workspace import render_state, research_state
from toulmin.protocols.status import NO_BLOCKING, project_status

BRIEF = "projects/demo/brief.md"


def claim(root, number, kind, *, importance="core", status="proposed", plan=None, **extra):
    """A copy of the example Claim with the given type, importance and status."""
    source = root / "projects/demo/claims/C-001.md"
    document = decode(source.read_bytes())
    document.header.update(id=f"C-{number:03d}", type=kind, importance=importance, status=status)
    document.header.update(extra)
    if plan is None:
        document.header.pop("validation_plan", None)
    else:
        document.header["validation_plan"] = plan
    path = root / f"projects/demo/claims/C-{number:03d}.md"
    path.write_bytes(encode(document))


def verified(root, target="C-001"):
    path = root / "projects/demo/evidence/E-001.md"
    document = decode(path.read_bytes())
    document.header.update(grade="verified", status="valid", direction="supports", target=target)
    document.header["verification"] = {
        "method": "test fixture",
        "result": "fixture result",
        "artifacts": ["projects/demo/runs/20261031T100000Z-review/output.md"],
    }
    path.write_bytes(encode(document))


def objection(root, severity, status="open"):
    path = root / "projects/demo/objections/O-001.md"
    document = decode(path.read_bytes())
    document.header.update(severity=severity, status=status)
    document.body = (
        "## Content\nFixture objection.\n\n## Response\nFixture response.\n\n"
        "## Ruling\nFixture ruling.\n"
    )
    path.write_bytes(encode(document))


def kill_criteria(root, text):
    path = root / BRIEF
    path.write_text(path.read_text().replace("## Kill criteria\n", f"## Kill criteria\n{text}"))


def gates(root):
    return {gate.gate: gate for gate in project_status(root, "demo").gates}


def items(gate):
    return {item.label: (item.met, item.detail) for item in gate.items}


def test_empty_project_meets_neither_gate(workbench):
    result = gates(workbench)
    assert result["G1"].met is False and result["G1"].enters == "critique"
    assert not any(item.met for item in result["G1"].items)
    assert result["G2"].met is False and result["G2"].enters == "brief-final"
    assert items(result["G2"])["core Claims supported or planned"] == (False, "no core Claims")
    assert items(result["G2"])["Kill criteria written in brief.md"] == (False, "empty")


def test_g1_needs_one_current_core_claim_of_each_type(populated):
    claim(populated, 1, "problem")
    claim(populated, 2, "magnitude")
    claim(populated, 3, "mechanism", importance="secondary")  # secondary does not count
    claim(populated, 4, "novelty")
    claim(
        populated, 5, "mechanism", status="superseded", superseded_by="C-001", decisions=["D-001"]
    )
    g1 = gates(populated)["G1"]
    assert g1.met is False
    found = items(g1)
    assert found["core problem Claim (the problem exists)"] == (True, "C-001")
    assert found["core mechanism Claim (the approach works)"] == (False, "")
    claim(populated, 3, "mechanism")
    assert gates(populated)["G1"].met is True


def test_g2_conditions(populated):
    claim(populated, 1, "problem")  # no plan, model-asserted evidence only
    claim(populated, 2, "magnitude", plan="Measure it.")
    claim(populated, 3, "novelty", status="refuted", decisions=["D-001"])
    objection(populated, "major")
    kill_criteria(populated, "<!-- fill in later -->\n")
    g2 = items(gates(populated)["G2"])
    assert g2["no open fatal or major Objection"] == (False, "O-001 (major)")
    assert g2["C-001 supported or planned"] == (False, "no verified support and no validation_plan")
    assert g2["C-002 supported or planned"] == (True, "validation_plan set")
    assert g2["C-003 supported or planned"] == (False, "refuted")
    assert g2["Kill criteria written in brief.md"] == (False, "empty")
    verified(populated)
    objection(populated, "minor")  # an open minor objection does not block G2
    claim(populated, 3, "novelty", status="superseded", superseded_by="C-002", decisions=["D-001"])
    kill_criteria(populated, "Stop if the tail improves by less than 5%.\n")
    result = gates(populated)["G2"]
    assert items(result)["C-001 supported or planned"] == (True, "verified support E-001")
    assert result.met is True


def test_cli_shows_readiness_and_changes_nothing(populated):
    before = {path: path.read_bytes() for path in Path(populated).rglob("*") if path.is_file()}
    stage = (populated / "projects/demo/PROJECT.md").read_text()
    result = CliRunner().invoke(app, ["status", "demo", "--root", str(populated)])
    assert result.exit_code == 0, result.output
    assert "Gates (readiness from files; the stage changes only by your ruling):" in result.stdout
    assert "  G1 -> critique: not met\n" in result.stdout
    assert "    [x] core problem Claim (the problem exists): C-001\n" in result.stdout
    assert "    [ ] core novelty Claim (novelty)\n" in result.stdout
    assert "  G2 -> brief-final: not met\n" in result.stdout
    after = {path: path.read_bytes() for path in Path(populated).rglob("*") if path.is_file()}
    assert after == before and (populated / "projects/demo/PROJECT.md").read_text() == stage


def test_invalid_data_makes_readiness_unknown(populated):
    (populated / "projects/demo/claims/C-009.md").write_text("not a claim\n")
    result = CliRunner().invoke(app, ["status", "demo", "--root", str(populated)])
    assert result.exit_code == 1
    assert "G1 -> critique: unknown (data invalid)" in result.stdout
    assert all(gate.met is None for gate in project_status(populated, "demo").gates)


# R5

G3_S1 = "S-001 maps to a Claim with executable acceptance"
G4_S1 = "S-001 completion reported with test Evidence"
G5_S1 = "S-001 passed on a verifier's independent run"


def edit(root, relative, **fields):
    path = root / relative
    document = decode(path.read_bytes())
    document.header.update(fields)
    path.write_bytes(encode(document))
    return document


def spec(root, **fields):
    return edit(root, "projects/demo/specs/S-001.md", **fields)


def stage(root, value):
    edit(root, "projects/demo/PROJECT.md", stage=value)


def test_without_specs_g3_to_g5_need_one(workbench):
    result = gates(workbench)
    for name, enters in (("G3", "build"), ("G4", "accept"), ("G5", "done")):
        assert result[name].enters == enters and result[name].met is False
        assert items(result[name]) == {"at least one Spec": (False, "no Specs")}


def test_g3_needs_a_current_claim_and_a_runnable_check(populated):
    assert items(gates(populated)["G3"])[G3_S1] == (True, "C-001")  # backticked command
    path = populated / "projects/demo/specs/S-001.md"
    document = decode(path.read_bytes())
    document.body = document.body.replace("`python replay.py --seed 7 --trace drift.json`", "it")
    path.write_bytes(encode(document))
    met, detail = items(gates(populated)["G3"])[G3_S1]
    assert not met and "name no command" in detail
    path.write_text(
        path.read_text().replace(
            "Acceptance criteria\n", "Acceptance criteria\n```sh\nmake check\n```\n"
        )
    )
    claim(populated, 1, "problem", status="refuted", decisions=["D-001"])
    assert items(gates(populated)["G3"])[G3_S1] == (
        False,
        "targets C-001, which is no longer current",
    )
    claim(populated, 1, "problem")
    claim(populated, 2, "problem")
    claim(populated, 1, "problem", status="superseded", superseded_by="C-002", decisions=["D-001"])
    assert items(gates(populated)["G3"])[G3_S1] == (True, "C-001 via its successor C-002")


def test_g4_needs_reported_completion_with_test_evidence(populated):
    assert items(gates(populated)["G4"])[G4_S1] == (False, "status todo")
    spec(populated, status="awaiting-acceptance")
    assert items(gates(populated)["G4"])[G4_S1] == (
        False,
        "status awaiting-acceptance; no valid supporting Evidence listed",
    )
    spec(populated, evidence=["E-001"])  # model-asserted test report is enough for G4
    assert gates(populated)["G4"].met is True


def test_g5_needs_verified_evidence_from_a_verifier_run(populated):
    verified(populated)
    spec(populated, status="passed", evidence=["E-001"])
    met, detail = items(gates(populated)["G5"])[G5_S1]
    assert not met and "from a Run with role verifier" in detail  # R-001 is a reviewer Run
    edit(populated, "projects/demo/runs/R-001.md", role="verifier")
    assert items(gates(populated)["G5"])[G5_S1] == (True, "E-001")
    edit(populated, "projects/demo/evidence/E-001.md", grade="model-asserted")
    assert gates(populated)["G5"].met is False


def test_deferred_majors_stay_visible_at_g2(populated):
    objection(populated, "major", "deferred")
    met, detail = items(gates(populated)["G2"])[NO_BLOCKING]
    assert met and detail == "advice: deferred O-001 (major) still stand; revisit them before build"


def test_a_stage_past_unheld_gates_is_warned_everywhere_and_never_changed(populated):
    stage(populated, "done")
    before = {path: path.read_bytes() for path in Path(populated).rglob("*") if path.is_file()}
    report = project_status(populated, "demo")
    assert [warning.split(" (", 1)[0] for warning in report.stage_warnings] == [
        f"Stage done is past G{number}"
        for number in (1, 2, 4, 5)  # S-001 meets G3
    ]
    result = CliRunner().invoke(app, ["status", "demo", "--root", str(populated)])
    assert "Warning: Stage done is past G5 (enters done), which does not hold" in result.stdout
    assert "the researcher rules whether to keep it or return the project" in result.stdout
    moves = research_map(populated, "demo").moves
    assert moves[0].actor == "you" and moves[0].text.startswith("The stage done is past G1")
    card = render_state(research_state(populated, "demo"))
    assert "WARNING: Stage done is past G4 (enters accept)" in card
    shown = CliRunner().invoke(app, ["map", "demo", "--root", str(populated)])
    assert "G5 -> done  0/1  (behind the stage, NOT held)" in shown.stdout
    after = {path: path.read_bytes() for path in Path(populated).rglob("*") if path.is_file()}
    assert after == before


def test_moves_follow_the_build_stages(populated):
    stage(populated, "build")
    found = project_status(populated, "demo").gates
    facts = replace(
        move_facts(populated, "demo", inspect_project(Repository(populated), "demo"), found, ()),
        gates=tuple(gate for gate in found if gate.gate == "G4"),  # G1/G2 rows aside
        objections=(),
    )
    assert next_moves(facts)[0].text.startswith("Work toward G4: the implementer finishes")
    spec(populated, status="awaiting-acceptance", evidence=["E-001"])
    found = project_status(populated, "demo").gates
    held = replace(facts, gates=tuple(gate for gate in found if gate.gate == "G4"))
    assert next_moves(held)[0].text.startswith("G4 conditions hold")
    stage(populated, "explore")
    result = CliRunner().invoke(app, ["status", "demo", "--root", str(populated)])
    assert "  G3 -> build: met (later)\n" in result.stdout  # folded while far ahead
    assert G3_S1 not in result.stdout
    verbose = CliRunner().invoke(app, ["status", "demo", "--root", str(populated), "--verbose"])
    assert G3_S1 in verbose.stdout
