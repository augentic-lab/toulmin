"""H2: G1/G2 readiness in ``status``; read-only, temporary workbenches only."""

from pathlib import Path

from typer.testing import CliRunner

from toulmin.cli.app import app
from toulmin.core.codec import decode, encode
from toulmin.protocols.status import project_status

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
