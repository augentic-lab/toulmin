import pytest
from typer.testing import CliRunner

from toulmin.cli.app import app
from toulmin.core.codec import decode, encode
from toulmin.core.documents import FormatError
from toulmin.core.schema import validate

CLAIMS = "projects/demo/claims"


@pytest.fixture(autouse=True)
def no_operator_default(monkeypatch):
    monkeypatch.delenv("TOULMIN_ACTOR", raising=False)


def files(root):
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def load(root, relative):
    return decode((root / relative).read_bytes(), relative)


def copy(root, source, target, **changes):
    document = load(root, source)
    document.header.update(id=target.rsplit("/", 1)[-1].removesuffix(".md"), **changes)
    (root / target).write_bytes(encode(document))


def decision(root, number, related):
    copy(
        root,
        "projects/demo/decisions/D-001.md",
        f"projects/demo/decisions/D-{number:03}.md",
        related=related,
    )


@pytest.fixture
def bench(populated):
    copy(populated, f"{CLAIMS}/C-001.md", f"{CLAIMS}/C-002.md")
    decision(populated, 2, ["C-001", "C-002", "O-001"])
    brief = populated / "projects/demo/brief.md"
    brief.write_text(brief.read_text().replace("## Problem\n", "## Problem\nSee [[C-001]].\n"))
    return populated


def rule(root, *arguments):
    command = ["rule", "demo", *arguments, "--root", str(root), "--confirmed-by", "Tianchi YU"]
    return CliRunner().invoke(app, [*command, "--confirm"])


def status(root, *extra):
    return CliRunner().invoke(app, ["status", "demo", "--root", str(root), *extra])


SUPERSEDE = ["C-001", "--status", "superseded", "--superseded-by", "C-002", "--decision", "D-002"]


def test_supersede_records_link_and_status_points_dependents_to_successor(bench):
    result = rule(bench, *SUPERSEDE)
    assert result.exit_code == 0, result.output
    assert "C-001: proposed -> superseded by D-002; linked superseded_by=C-002" in result.stdout
    text = (bench / f"{CLAIMS}/C-001.md").read_text()
    header = load(bench, f"{CLAIMS}/C-001.md").header
    assert header["status"] == "superseded" and header["superseded_by"] == "C-002"
    assert header["decisions"] == ["D-002"]
    assert text.index("superseded_by:") < text.index("decisions:")

    report = status(bench, "-v")
    assert report.exit_code == 0, report.output
    lines = report.stdout.splitlines()
    assert not any(line.startswith("  C-001 |") for line in lines)
    assert lines[lines.index("Superseded:") + 1] == "  C-001 -> C-002"
    for expected in (
        "O-001: target is superseded C-001 (current: C-002); rule it or raise it against C-002",
        "E-001: target is superseded C-001 (current: C-002); it does not count for C-002",
        "S-001: target is superseded C-001 (current: C-002); researcher review needed",
        "brief.md:6: [[C-001]] is superseded (current: C-002)",
    ):
        assert f"Notice: {expected}" in lines
    assert not any("challenged but no open" in line for line in lines)


def test_chains_resolve_to_the_current_claim(bench):
    assert rule(bench, *SUPERSEDE).exit_code == 0
    copy(bench, f"{CLAIMS}/C-002.md", f"{CLAIMS}/C-003.md")
    decision(bench, 3, ["C-002", "C-003"])
    assert rule(bench, "C-002", "--status", "superseded", "--superseded-by", "C-003",
                "--decision", "D-003").exit_code == 0  # fmt: skip
    report = status(bench)
    assert "  C-001 -> C-002 -> C-003" in report.stdout.splitlines()
    assert "(current: C-003)" in report.stdout


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["C-001", "--status", "superseded", "--decision", "D-002"], "required for superseded"),
        (
            ["C-001", "--status", "challenged", "--superseded-by", "C-002", "--decision", "D-002"],
            "allowed only when status is superseded",
        ),
        (
            ["C-001", "--status", "superseded", "--superseded-by", "C-001", "--decision", "D-002"],
            "expected another claim",
        ),
        (
            ["C-001", "--status", "superseded", "--superseded-by", "other/C-002"]
            + ["--decision", "D-002"],
            "successor must be in project demo",
        ),
        (
            ["C-001", "--status", "superseded", "--superseded-by", "C-009", "--decision", "D-002"],
            "C-009",
        ),
        (
            ["C-001", "--status", "superseded", "--superseded-by", "O-001", "--decision", "D-002"],
            "expected another claim",
        ),
        (
            ["C-001", "--status", "superseded", "--superseded-by", "C-002", "--decision", "D-001"],
            "related: must name C-002",
        ),
        (["C-001", "--superseded-by", "C-002"], "links require a researcher Decision"),
        (["C-001", "--adopted-as", "C-002", "--decision", "D-002"], "not a field rule can set"),
    ],
)
def test_invalid_supersessions_write_nothing(bench, arguments, message):
    before = files(bench)
    result = rule(bench, *arguments)
    assert result.exit_code == 1
    assert message in result.output
    assert files(bench) == before


def test_superseded_is_final_and_links_are_never_replaced(bench):
    assert rule(bench, *SUPERSEDE).exit_code == 0
    copy(bench, f"{CLAIMS}/C-002.md", f"{CLAIMS}/C-003.md")
    decision(bench, 3, ["C-001", "C-002", "C-003"])
    before = files(bench)
    final = rule(bench, "C-001", "--status", "proposed", "--decision", "D-003")
    assert final.exit_code == 1 and "final for rule" in final.output
    onto_old = rule(bench, "C-003", "--status", "superseded", "--superseded-by", "C-001",
                    "--decision", "D-003")  # fmt: skip
    assert onto_old.exit_code == 1 and "successor is itself superseded" in onto_old.output
    assert files(bench) == before


def test_hand_edited_cycles_and_foreign_successors_are_data_errors(bench):
    for number, successor in ((1, "C-002"), (2, "C-001")):
        copy(
            bench,
            f"{CLAIMS}/C-00{number}.md",
            f"{CLAIMS}/C-00{number}.md",
            status="superseded",
            superseded_by=successor,
            decisions=["D-002"],
        )
    report = status(bench)
    assert report.exit_code == 1
    assert "revision cycle C-001 -> C-002 -> C-001" in report.output

    copy(bench, f"{CLAIMS}/C-002.md", f"{CLAIMS}/C-002.md", status="proposed")
    document = load(bench, f"{CLAIMS}/C-002.md")
    del document.header["superseded_by"], document.header["decisions"]
    (bench / f"{CLAIMS}/C-002.md").write_bytes(encode(document))
    assert status(bench).exit_code == 0
    copy(bench, f"{CLAIMS}/C-001.md", f"{CLAIMS}/C-001.md", superseded_by="demo/C-002")
    assert status(bench).exit_code == 0  # own-project prefix is the same Claim
    (bench / "projects/other").mkdir()
    copy(bench, f"{CLAIMS}/C-001.md", f"{CLAIMS}/C-001.md", superseded_by="other/C-002")
    assert status(bench).exit_code == 1


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"status": "superseded", "superseded_by": "C-002"}, "decisions"),
        ({"status": "superseded", "decisions": ["D-002"]}, "required for superseded claim"),
        ({"superseded_by": "C-002"}, "allowed only when status is superseded"),
        ({"status": "superseded", "superseded_by": "C-001", "decisions": ["D-002"]}, "itself"),
        ({"status": "superseded", "superseded_by": "O-001", "decisions": ["D-002"]}, "claim"),
    ],
)
def test_claim_schema_conditions(example_docs, changes, message):
    document = next(doc for doc in example_docs.values() if doc.header["id"] == "C-001")
    document.header.update(changes)
    with pytest.raises(FormatError, match=message):
        validate(decode(encode(document)))


def test_rule_sets_exploration_and_spec_links(bench):
    decision(bench, 3, ["X-001", "S-001", "C-001"])
    adopted = rule(bench, "X-001", "--status", "adopted", "--adopted-as", "C-001",
                   "--decision", "D-003")  # fmt: skip
    assert adopted.exit_code == 0, adopted.output
    assert load(bench, "projects/demo/explorations/X-001.md").header["adopted_as"] == "C-001"
    replaced = rule(bench, "X-001", "--adopted-as", "C-002", "--decision", "D-003")
    assert replaced.exit_code == 1 and "rule never replaces" in replaced.output

    for _ in range(2):
        linked = rule(bench, "S-001", "--evidence", "E-001", "--decision", "D-003")
        assert linked.exit_code == 0, linked.output
    spec = load(bench, "projects/demo/specs/S-001.md").header
    assert spec["evidence"] == ["E-001"] and spec["status"] == "todo"
    missing = rule(bench, "S-001", "--evidence", "E-009", "--decision", "D-003")
    assert missing.exit_code == 1


def test_decision_can_be_superseded_by_the_decision_that_cites_it(bench):
    result = rule(bench, "D-001", "--status", "superseded", "--superseded-by", "D-002",
                  "--decision", "D-002")  # fmt: skip
    assert result.exit_code == 1 and "related: must name D-001" in result.output
    decision(bench, 3, ["D-001"])
    result = rule(bench, "D-001", "--status", "superseded", "--superseded-by", "D-003",
                  "--decision", "D-003")  # fmt: skip
    assert result.exit_code == 0, result.output
    assert load(bench, "projects/demo/decisions/D-001.md").header["superseded_by"] == "D-003"
