import os

import pytest
from typer.testing import CliRunner

from toulmin.cli.app import app
from toulmin.core import atomic
from toulmin.core.codec import decode, encode

TEXT = "projects/demo/runs/drafts/text.md"


@pytest.fixture(autouse=True)
def no_operator_default(monkeypatch):
    monkeypatch.delenv("TOULMIN_ACTOR", raising=False)


@pytest.fixture
def bench(populated):
    (populated / "projects/demo/runs/drafts").mkdir()
    (populated / TEXT).write_text("The workload trace now includes drift.\n")
    return populated


def files(root):
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def rule(root, object_id, *extra, confirm=True):
    command = ["rule", "demo", object_id, "--root", str(root), "--confirmed-by", "Tianchi YU"]
    return CliRunner().invoke(app, command + list(extra) + (["--confirm"] if confirm else []))


def load(root, relative):
    return decode((root / relative).read_bytes())


OBJECTION = "projects/demo/objections/O-001.md"
CLAIM = "projects/demo/claims/C-001.md"


def test_answering_an_objection_records_response_status_and_decision(bench):
    result = rule(bench, "O-001", "--status", "answered", "--decision", "D-001", "--response", TEXT)
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[:2] == [
        OBJECTION,
        "O-001: open -> answered by D-001; added to Response",
    ]
    doc = load(bench, OBJECTION)
    assert doc.header["status"] == "answered"
    assert doc.header["decisions"] == ["D-001"]
    assert doc.body.endswith("## Response\nThe workload trace now includes drift.\n\n## Ruling")
    status = CliRunner().invoke(app, ["status", "demo", "--root", str(bench)])
    assert "Open objections: none" in status.stdout


def test_response_alone_needs_no_decision_and_keeps_status(bench):
    result = rule(bench, "O-001", "--response", TEXT)
    assert result.exit_code == 0, result.output
    assert "status unchanged (open)" in result.stdout
    doc = load(bench, OBJECTION)
    assert doc.header["status"] == "open" and "decisions" not in doc.header


@pytest.mark.parametrize(
    ("status", "options", "message"),
    [
        ("answered", [], "body.Response: required for this status"),
        ("accepted", ["--response", TEXT], "body.Ruling: required for this status"),
        ("deferred", [], "body.Ruling: required for this status"),
    ],
)
def test_objection_conditional_sections_are_enforced(bench, status, options, message):
    before = files(bench)
    result = rule(bench, "O-001", "--status", status, "--decision", "D-001", *options)
    assert result.exit_code == 1
    assert message in result.output
    assert files(bench) == before


@pytest.mark.parametrize("status", ["accepted", "deferred"])
def test_accepting_or_deferring_with_ruling(bench, status):
    result = rule(bench, "O-001", "--status", status, "--decision", "D-001", "--ruling", TEXT)
    assert result.exit_code == 0, result.output
    assert load(bench, OBJECTION).header["status"] == status


def test_claim_ruling_reports_conditions_without_choosing_status(bench):
    result = rule(bench, "C-001", "--status", "accepted", "--decision", "D-001")
    assert result.exit_code == 0, result.output
    assert "C-001: proposed -> accepted by D-001" in result.stdout
    assert "Notice: C-001: stored=accepted does not meet supported conditions" in result.stdout
    doc = load(bench, CLAIM)
    assert doc.header["status"] == "accepted" and doc.header["decisions"] == ["D-001"]


def test_existing_decision_is_not_duplicated(bench):
    assert rule(bench, "C-001", "--status", "challenged", "--decision", "D-001").exit_code == 0
    assert rule(bench, "C-001", "--status", "refuted", "--decision", "D-001").exit_code == 0
    assert load(bench, CLAIM).header["decisions"] == ["D-001"]


def superseded(root):
    path = root / "projects/demo/decisions/D-002.md"
    text = (root / "projects/demo/decisions/D-001.md").read_text()
    text = text.replace("id: D-001", "id: D-002").replace("status: active", "status: superseded")
    path.write_text(text.replace("related:", "superseded_by: D-001\nrelated:"))


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (["--status", "answered", "--response", TEXT], "requires a researcher Decision"),
        (["--status", "answered", "--decision", "D-009", "--response", TEXT], "D-009"),
        (["--status", "answered", "--decision", "C-001", "--response", TEXT], "Decision reference"),
        (["--status", "answered", "--decision", "D-002", "--response", TEXT], "only an active"),
        (["--status", "open", "--decision", "D-001"], "already open"),
        (["--status", "closed", "--decision", "D-001"], "expected one of"),
        ([], "nothing to record"),
        (["--section", f"Content={TEXT}"], "rule may add to"),
        (["--response", "projects/demo/runs/drafts/missing.md"], "expected existing regular file"),
        (["--response", "../outside.md"], "path"),
    ],
)
def test_invalid_rulings_write_nothing(bench, options, message):
    superseded(bench)
    before = files(bench)
    result = rule(bench, "O-001", *options)
    assert result.exit_code == 1
    assert message in result.output
    assert files(bench) == before


def test_decision_must_name_the_object(bench):
    before = files(bench)
    result = rule(bench, "S-001", "--status", "in-progress", "--decision", "D-001")
    assert result.exit_code == 1
    assert "related: must name S-001" in result.output
    assert files(bench) == before


@pytest.mark.parametrize(
    ("object_id", "message"),
    [("R-001", "immutable"), ("C-404", "C-404"), ("other/C-001", "id:"), ("C-1", "id:")],
)
def test_runs_missing_and_foreign_objects_are_rejected(bench, object_id, message):
    before = files(bench)
    result = rule(bench, object_id, "--status", "failed", "--decision", "D-001")
    assert result.exit_code == 1
    assert message in result.output
    assert files(bench) == before


def test_confirmation_and_actor_are_required(bench):
    before = files(bench)
    unconfirmed = rule(bench, "O-001", "--response", TEXT, confirm=False)
    assert unconfirmed.exit_code == 1 and "explicit researcher confirmation" in unconfirmed.output
    command = ["rule", "demo", "O-001", "--root", str(bench), "--response", TEXT, "--confirm"]
    assert CliRunner().invoke(app, command).exit_code == 2
    assert files(bench) == before
    with_default = CliRunner().invoke(app, command, env={"TOULMIN_ACTOR": "Tianchi YU"})
    assert with_default.exit_code == 0, with_default.output


@pytest.mark.parametrize(
    "text",
    ["", "   \n", "## Injected\nheading\n", "<fill: response>\n"],
)
def test_bad_section_text_writes_nothing(bench, text):
    (bench / TEXT).write_text(text)
    before = files(bench)
    result = rule(bench, "O-001", "--response", TEXT)
    assert result.exit_code == 1
    assert files(bench) == before


def test_comments_order_unrelated_sections_and_fences_are_preserved(bench):
    path = bench / OBJECTION
    original = path.read_text()
    header, body = original[4:].split("\n---\n", 1)
    header = header.replace("severity: major", "severity: major  # reviewer's call")
    body = body.replace(
        "## Response\n",
        "```text\n## Response\nfenced, not a section\n```\n\n## Response\n",
    )
    path.write_text("---\n" + header + "\n---\n" + body + "\n\n## Notes\nKeep me.\n")
    result = rule(bench, "O-001", "--status", "answered", "--decision", "D-001", "--response", TEXT)
    assert result.exit_code == 0, result.output
    updated = path.read_text()
    assert "severity: major  # reviewer's call" in updated
    assert "```text\n## Response\nfenced, not a section\n```\n" in updated
    assert updated.endswith("## Ruling\n\n## Notes\nKeep me.\n")
    lines = updated.splitlines()
    assert lines.index("status: answered") < lines.index("target: C-001")
    # Every byte before the real Response heading (after the fence) is unchanged.
    real = "```\n\n## Response\n"
    assert updated.split("\n---\n", 1)[1].startswith(
        body.split(real)[0] + real + "The workload trace now includes drift.\n"
    )


def test_nonempty_section_keeps_old_text_and_appends(bench):
    assert rule(bench, "O-001", "--response", TEXT).exit_code == 0
    (bench / TEXT).write_text("Second response after new data.\n")
    assert rule(bench, "O-001", "--response", TEXT).exit_code == 0
    body = load(bench, OBJECTION).body
    assert body.endswith(
        "## Response\nThe workload trace now includes drift.\n\n"
        "Second response after new data.\n\n## Ruling"
    )


def test_missing_reason_section_is_added_for_invalidation(bench):
    result = rule(
        bench,
        "E-001",
        "--status",
        "invalidated",
        "--decision",
        "D-003",
        "--section",
        f"Invalidation={TEXT}",
    )
    assert result.exit_code == 1  # D-003 does not exist yet
    decision = load(bench, "projects/demo/decisions/D-001.md")
    decision.header.update(id="D-003", related=["E-001"])
    (bench / "projects/demo/decisions/D-003.md").write_bytes(encode(decision))
    result = rule(
        bench,
        "E-001",
        "--status",
        "invalidated",
        "--decision",
        "D-003",
        "--section",
        f"Invalidation={TEXT}",
    )
    assert result.exit_code == 0, result.output
    assert load(bench, "projects/demo/evidence/E-001.md").body.endswith(
        "\n\n## Invalidation\nThe workload trace now includes drift.\n"
    )


def test_failed_replace_keeps_original_and_no_temporary_file(bench, monkeypatch):
    before = files(bench)

    def fail(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(atomic.os, "replace", fail)
    result = rule(bench, "O-001", "--response", TEXT)
    assert result.exit_code == 1
    assert files(bench) == before
    assert not (bench / "projects/demo/.toulmin-new.lock").exists()


def test_held_lock_blocks_ruling_without_removing_lock(bench):
    lock = bench / "projects/demo/.toulmin-new.lock"
    lock.mkdir()
    before = files(bench)
    result = rule(bench, "O-001", "--response", TEXT)
    assert result.exit_code == 1 and "holds the lock" in result.output
    assert files(bench) == before and lock.is_dir()
    os.rmdir(lock)


def test_absolute_section_file_inside_root_is_accepted(bench):
    result = rule(bench, "O-001", "--response", str(bench / TEXT))
    assert result.exit_code == 0, result.output


def test_external_edit_during_ruling_is_refused(bench, monkeypatch):
    from toulmin.protocols import ruling

    real = ruling.put_section
    path = bench / OBJECTION

    def edit_meanwhile(body, name, content):
        path.write_text(path.read_text() + "\nEdited in an editor.\n")
        return real(body, name, content)

    monkeypatch.setattr(ruling, "put_section", edit_meanwhile)
    result = rule(bench, "O-001", "--response", TEXT)
    assert result.exit_code == 1 and "changed while ruling" in result.output
    assert path.read_text().endswith("Edited in an editor.\n")
