import pytest
from typer.testing import CliRunner

from toulmin.cli.app import app
from toulmin.core.codec import decode, encode
from toulmin.core.documents import FormatError
from toulmin.core.review import parse_review

ARCHIVE = "projects/demo/runs/20261031T100000Z-review"
OUTPUT = f"{ARCHIVE}/output.md"
RECORD = f"{ARCHIVE}/intake.md"
OBJECTIONS = "projects/demo/objections"

BLOCK = """\
Prose review text stays opaque.

```yaml
- label: draft-1
  target: C-001
  severity: major
  content: |
    The workload mix is not stated.
  grounds: Section 2 names no trace.
  uncertainty: The trace may exist elsewhere.
- label: draft-2
  target: C-001
  severity: major
  content: The p99 window is undefined.
  grounds: No window length is given.
- label: draft-3
  target: C-001
  severity: minor
  content: A wording nit.
  grounds: Style.
```
"""


@pytest.fixture(autouse=True)
def no_operator_default(monkeypatch):
    monkeypatch.delenv("TOULMIN_ACTOR", raising=False)


@pytest.fixture
def bench(populated):
    (populated / OUTPUT).write_text(BLOCK)
    return populated


def files(root):
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def load(root, relative):
    return decode((root / relative).read_bytes(), relative)


def intake(root, *arguments, confirm=True):
    command = ["intake", "demo", OUTPUT, *arguments, "--root", str(root)]
    command += ["--confirmed-by", "Tianchi YU"] + (["--confirm"] if confirm else [])
    return CliRunner().invoke(app, command)


def status(root, *extra):
    return CliRunner().invoke(app, ["status", "demo", "--root", str(root), *extra])


def test_take_override_and_reject_create_objections_and_one_record(bench):
    result = intake(bench, "--take", "draft-1,draft-2:minor", "--reject", "draft-3=style only")
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == [
        RECORD,
        "draft-1: taken as O-002 (R-001)",
        "draft-2: partly as O-003 (R-001)",
        "draft-3: rejected (R-001)",
    ]
    taken = load(bench, f"{OBJECTIONS}/O-002.md")
    assert taken.header["source"] == {"kind": "run", "ref": "R-001", "path": OUTPUT}
    assert taken.header["confirmed_by"]["actor"] == "Tianchi YU"
    assert taken.header["status"] == "open" and taken.header["severity"] == "major"
    assert taken.body == (
        "## Content\nThe workload mix is not stated.\n\nGrounds: Section 2 names no trace.\n\n"
        "Uncertainty: The trace may exist elsewhere.\n\n## Response\n\n## Ruling\n"
    )
    assert load(bench, f"{OBJECTIONS}/O-003.md").header["severity"] == "minor"
    record = load(bench, RECORD).header
    assert record["run"] == "R-001" and record["output"] == OUTPUT
    rows = [
        (o["label"], o["outcome"], o.get("object"), o.get("reason")) for o in record["outcomes"]
    ]
    assert rows == [
        ("draft-1", "taken", "O-002", None),
        ("draft-2", "partly", "O-003", None),
        ("draft-3", "rejected", None, "style only"),
    ]
    assert status(bench).exit_code == 0


def test_partial_intake_leaves_a_pending_notice_until_every_draft_is_settled(bench):
    assert status(bench).exit_code == 0
    assert "pending intake" not in status(bench).stdout  # no record yet: nothing claimed
    assert intake(bench, "--take", "draft-1").exit_code == 0
    report = status(bench)
    assert report.exit_code == 0, report.output
    assert "Notice: R-001: review drafts pending intake: draft-2, draft-3" in report.stdout
    assert intake(bench, "--reject", "draft-2=duplicate", "--reject", "draft-3=nit").exit_code == 0
    assert "pending intake" not in status(bench).stdout


def test_partly_links_an_objection_written_by_hand_from_the_same_output(bench):
    result = intake(bench, "--partly", "draft-2=O-001")
    assert result.exit_code == 0, result.output
    assert "draft-2: partly as O-001 (R-001)" in result.stdout
    assert not (bench / f"{OBJECTIONS}/O-002.md").exists()
    assert load(bench, RECORD).header["outcomes"][0]["object"] == "O-001"


def test_replay_is_idempotent_and_outcomes_are_never_changed(bench):
    assert intake(bench, "--take", "draft-1,draft-2:minor").exit_code == 0
    before = files(bench)
    replay = intake(bench, "--take", "draft-1", "--take", "draft-2:minor")
    assert replay.exit_code == 0, replay.output
    assert "draft-1: already-taken as O-002 (R-001)" in replay.stdout
    assert "draft-2: already-partly as O-003 (R-001)" in replay.stdout
    assert files(bench) == before
    changed = intake(bench, "--reject", "draft-1=changed my mind")
    assert changed.exit_code == 1 and "already taken; an outcome is never changed" in changed.output
    assert files(bench) == before


def test_replay_recovers_an_objection_created_before_the_record_was_written(bench):
    assert intake(bench, "--take", "draft-1").exit_code == 0
    (bench / RECORD).unlink()  # simulate an interruption between the two writes
    result = intake(bench, "--take", "draft-1,draft-2")
    assert result.exit_code == 0, result.output
    assert "draft-1: taken as O-002 (R-001)" in result.stdout
    assert "draft-2: taken as O-003 (R-001)" in result.stdout
    assert sorted(p.name for p in (bench / OBJECTIONS).glob("O-*.md")) == [
        "O-001.md",
        "O-002.md",
        "O-003.md",
    ]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--take", "draft-9"], "draft-9: no such draft label"),
        (["--take", "draft-1:huge"], "severity: expected one of"),
        (["--take", "draft-1", "--reject", "draft-1=no"], "given more than one outcome"),
        (["--partly", "draft-1=C-001"], "expected an Objection ID"),
        (["--partly", "draft-1=O-009"], "O-009"),
        (["--reject", "draft-1="], "expected LABEL=VALUE"),
        ([], "nothing to record"),
    ],
)
def test_invalid_requests_write_nothing(bench, arguments, message):
    before = files(bench)
    result = intake(bench, *arguments)
    assert result.exit_code != 0
    assert message in result.output
    assert files(bench) == before


def test_missing_target_and_foreign_partly_source_write_nothing(bench):
    (bench / OUTPUT).write_text(
        BLOCK.replace("target: C-001\n  severity: minor", "target: C-404\n  severity: minor")
    )
    before = files(bench)
    missing = intake(bench, "--take", "draft-1,draft-3")
    assert missing.exit_code == 1 and "draft-3: target C-404:" in missing.output
    other = load(bench, f"{OBJECTIONS}/O-001.md")
    other.header["source"] = {"kind": "human", "actor": "Tianchi YU"}
    (bench / f"{OBJECTIONS}/O-001.md").write_bytes(encode(other))
    before = files(bench)
    foreign = intake(bench, "--partly", "draft-1=O-001")
    assert foreign.exit_code == 1 and "must cite R-001" in foreign.output
    assert files(bench) == before


def test_confirmation_and_actor_are_required(bench):
    before = files(bench)
    unconfirmed = intake(bench, "--take", "draft-1", confirm=False)
    assert unconfirmed.exit_code == 1 and "explicit researcher confirmation" in unconfirmed.output
    anonymous = CliRunner().invoke(
        app, ["intake", "demo", OUTPUT, "--take", "draft-1", "--root", str(bench), "--confirm"]
    )
    assert anonymous.exit_code == 2 and "--confirmed-by" in anonymous.output
    assert files(bench) == before


def test_output_must_belong_to_exactly_one_run(bench):
    stray = "projects/demo/runs/20261101T000000Z-review/output.md"
    (bench / stray).parent.mkdir()
    (bench / stray).write_text(BLOCK)
    before = files(bench)
    result = CliRunner().invoke(
        app,
        ["intake", "demo", stray, "--take", "draft-1", "--root", str(bench)]
        + ["--confirmed-by", "Tianchi YU", "--confirm"],
    )
    assert result.exit_code == 1 and "found none" in result.output
    outside = CliRunner().invoke(
        app,
        ["intake", "demo", "projects/demo/brief.md", "--take", "draft-1", "--root", str(bench)]
        + ["--confirmed-by", "Tianchi YU", "--confirm"],
    )
    assert (
        outside.exit_code == 1 and "expected projects/demo/runs/<archive>/<file>" in outside.output
    )
    assert files(bench) == before


DRAFT = "- label: d1\n  target: C-001\n  severity: major\n  content: c\n  grounds: g\n"


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("No block at all.\n", "out.md:1: drafts: no final fenced yaml block"),
        ('```yaml\n- label: d1\n  content: "a" b\n```\n', "out.md:3: drafts:"),
        ("```yaml\n{}\n```\n", "expected a nonempty list"),
        ("```yaml\n" + DRAFT + "  extra: x\n```\n", "out.md:2: drafts[0].extra: unknown field"),
        (
            "```yaml\n" + DRAFT.replace("  grounds: g\n", "") + "```\n",
            "drafts[0].grounds: required",
        ),
        ("```yaml\n" + DRAFT.replace("C-001", "O-001") + "```\n", "drafts[0].target"),
        ("```yaml\n" + DRAFT.replace("major", "huge") + "```\n", "drafts[0].severity"),
        ("```yaml\n" + DRAFT + DRAFT + "```\n", "out.md:7: drafts[1].label: duplicate label d1"),
        (
            "```yaml\n"
            + DRAFT.replace("content: c", "content: |\n    ## Response\n    x")
            + "```\n",
            "level-two headings",
        ),  # fmt: skip
        (
            "```yaml\n- label: d1\n  <<: {target: C-001}\n```\n",
            "out.md:3: drafts[0].<<: merge keys forbidden",
        ),
        ("```yaml\n" + DRAFT.replace("label: d1", "label: d 1") + "```\n", "drafts[0].label"),
    ],
)
def test_parse_errors_name_the_location(raw, message):
    with pytest.raises(FormatError) as error:
        parse_review(raw, "out.md")
    assert message in str(error.value)


def test_only_the_last_top_level_yaml_block_counts():
    raw = (
        "```yaml\nnot: drafts\n```\n\n````markdown\n```yaml\nnested: example\n```\n````\n\n"
        "```yml\n" + DRAFT + "```\n"
    )
    (draft,) = parse_review(raw, "out.md")
    assert (draft.label, draft.line) == ("d1", 12)


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda h: h["outcomes"][0].update(label="draft-9"), "draft-9: no such draft"),
        (lambda h: h["outcomes"][0].update(object="O-009"), "O-009 does not cite this output"),
        (lambda h: h.update(run="R-002"), "expected the Run whose output is"),
        (lambda h: h["outcomes"][0].pop("by"), "outcomes[0].by"),
        (lambda h: h["outcomes"].append(dict(h["outcomes"][0])), "duplicate outcome"),
    ],
)
def test_status_rejects_corrupt_intake_records(bench, edit, message):
    assert intake(bench, "--take", "draft-1").exit_code == 0
    record = load(bench, RECORD)
    edit(record.header)
    (bench / RECORD).write_bytes(encode(record))
    report = status(bench)
    assert report.exit_code == 1
    assert message in report.output


def test_verbose_status_lists_settled_objections_with_their_decisions(bench):
    objection = load(bench, f"{OBJECTIONS}/O-001.md")
    objection.header.update(status="answered", decisions=["D-001"])
    objection.body = objection.body.replace("## Response\n", "## Response\nThe trace is named.\n")
    (bench / f"{OBJECTIONS}/O-001.md").write_bytes(encode(objection))
    report = status(bench, "-v")
    assert report.exit_code == 0, report.output
    lines = report.stdout.splitlines()
    assert "Settled objections:" in lines
    assert lines[lines.index("Settled objections:") + 1] == (
        "  O-001 | answered | target=C-001 | by D-001"
    )
    assert "Settled objections:" not in status(bench).stdout
