import re
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from toulmin.cli.app import app
from toulmin.core.codec import decode, encode
from toulmin.core.documents import DIRECTORIES, Document
from toulmin.core.identifiers import ObjectKind
from toulmin.protocols.drafting import write_draft

OUTPUT = "projects/demo/runs/20261031T100000Z-review/output.md"
HUMAN = {"kind": "human", "actor": "Tianchi YU"}
FROM_RUN = {"kind": "run", "ref": "R-001", "path": OUTPUT}
FILLED = {
    ObjectKind.CLAIM: {"source": HUMAN, "type": "problem", "importance": "core"},
    ObjectKind.EVIDENCE: {
        "source": HUMAN,
        "target": "C-001",
        "direction": "supports",
        "kind": "measurement",
        "grade": "intuition",
        "provenance": [{"description": "Archived output", "path": OUTPUT}],
    },
    ObjectKind.OBJECTION: {"source": FROM_RUN, "target": "C-001", "severity": "major"},
    ObjectKind.DECISION: {"source": HUMAN, "related": ["C-001"]},
    ObjectKind.EXPLORATION: {"source": FROM_RUN, "lens": "alternative mechanism"},
    ObjectKind.SPEC: {"source": HUMAN, "target": "C-001"},
    ObjectKind.RUN: {
        "source": HUMAN,
        "status": "completed",
        "model": "example-model",
        "role": "reviewer",
        "output": "projects/demo/runs/20261031T100000Z-review",
    },
}


@pytest.fixture(autouse=True)
def no_operator_default(monkeypatch):
    # The operator's real default confirmer must not leak into expectations.
    monkeypatch.delenv("TOULMIN_ACTOR", raising=False)


def files(root):
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def draft(root, kind, *extra, env=None):
    result = CliRunner().invoke(
        app, ["draft", str(kind), "demo", "--root", str(root), *extra], env=env
    )
    assert result.exit_code == 0, result.output
    relative = result.stdout.strip()
    return relative, root / relative


def new(root, kind, relative, *extra, env=None):
    command = ["new", str(kind), "demo", "--root", str(root), "--input", relative, *extra]
    return CliRunner().invoke(app, command, env=env)


def fill(path, kind):
    document = decode(path.read_bytes(), str(path))
    document.header.update(FILLED[kind])
    body = re.sub(r"<fill: [^>]*>", "Filled by the researcher.", document.body)
    path.write_bytes(encode(Document(document.header, body)))


@pytest.mark.parametrize("kind", list(ObjectKind))
def test_draft_writes_only_a_skeleton_that_intake_rejects_until_filled(populated, kind):
    before = files(populated)
    relative, path = draft(populated, kind)
    assert re.fullmatch(rf"projects/demo/runs/drafts/{kind}-\d{{8}}T\d{{6}}Z\.md", relative)
    assert set(files(populated)) - set(before) == {relative}
    assert f"toulmin new {kind} demo" in path.read_text()
    decode(path.read_bytes(), str(path))  # strict YAML subset, comments allowed

    result = new(populated, kind, relative, "--confirmed-by", "Tianchi YU", "--confirm")
    assert result.exit_code == 1
    assert "unfilled <fill: ...> placeholder" in result.output
    assert re.search(rf"{re.escape(relative)}:\d+: ", result.output)
    assert files(populated) == {**before, relative: path.read_bytes()}


@pytest.mark.parametrize("kind", list(ObjectKind))
def test_filled_skeleton_passes_intake_for_every_kind(populated, kind):
    relative, path = draft(populated, kind)
    fill(path, kind)
    result = new(populated, kind, relative, "--confirmed-by", "Tianchi YU", "--confirm")
    assert result.exit_code == 0, result.output
    created = populated / "projects/demo" / DIRECTORIES[kind]
    assert (populated / result.stdout.strip()).parent == created


def test_placeholder_in_any_body_section_is_located(populated):
    relative, path = draft(populated, ObjectKind.DECISION)
    fill(path, ObjectKind.DECISION)
    path.write_text(path.read_text().replace("## Rationale\n", "## Rationale\n<fill: why>\n"))
    result = new(populated, "decision", relative, "--confirmed-by", "X", "--confirm")
    assert result.exit_code == 1
    assert "body.Rationale: unfilled" in result.output


def test_drafts_never_overwrite_and_keep_distinct_names(workbench):
    moment = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
    first = write_draft(workbench, "demo", ObjectKind.CLAIM, "cause", now=moment)
    first.write_text("researcher edits\n")
    second = write_draft(workbench, "demo", ObjectKind.CLAIM, "cause", now=moment)
    assert first.name == "claim-20261102T120000Z-cause.md"
    assert second.name == "claim-20261102T120000Z-cause-2.md"
    assert first.read_text() == "researcher edits\n"
    assert not list(first.parent.glob(".draft-*"))


@pytest.mark.parametrize("name", ["../x", "a/b", "-x", "", "x" * 65, "名前"])
def test_bad_names_and_actors_write_nothing(workbench, name):
    before = files(workbench)
    result = CliRunner().invoke(
        app, ["draft", "claim", "demo", "--root", str(workbench), "--name", name]
    )
    assert result.exit_code == 1
    result = CliRunner().invoke(
        app,
        ["draft", "claim", "demo", "--root", str(workbench)],
        env={"TOULMIN_ACTOR": "two\nlines"},
    )
    assert result.exit_code == 1
    assert files(workbench) == before
    assert not (workbench / "projects/demo/runs/drafts").exists()


def test_symlinked_drafts_directory_is_rejected(workbench, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (workbench / "projects/demo/runs/drafts").symlink_to(outside)
    result = CliRunner().invoke(app, ["draft", "claim", "demo", "--root", str(workbench)])
    assert result.exit_code == 1
    assert list(outside.iterdir()) == []


def test_unknown_project_is_rejected(workbench):
    result = CliRunner().invoke(app, ["draft", "claim", "other", "--root", str(workbench)])
    assert result.exit_code == 1


def test_default_actor_prefills_draft_and_confirms_intake(populated):
    env = {"TOULMIN_ACTOR": "Tianchi YU"}
    relative, path = draft(populated, ObjectKind.CLAIM, env=env)
    assert 'actor: "Tianchi YU"' in path.read_text()
    text = path.read_text()
    text = re.sub(r'type: "[^"]*"', "type: problem", text)
    text = re.sub(r'importance: "[^"]*"', "importance: core", text)
    path.write_text(text.replace("<fill: one testable statement>", "A statement."))

    assert new(populated, "claim", relative, "--confirm").exit_code == 2
    unconfirmed = new(populated, "claim", relative, env=env)
    assert unconfirmed.exit_code == 1 and "explicit researcher confirmation" in unconfirmed.output
    result = new(populated, "claim", relative, "--confirm", env=env)
    assert result.exit_code == 0, result.output
    created = decode((populated / result.stdout.strip()).read_bytes())
    assert created.header["confirmed_by"]["actor"] == "Tianchi YU"
    explicit = new(populated, "claim", relative, "--confirmed-by", "Other", "--confirm", env=env)
    created = decode((populated / explicit.stdout.strip()).read_bytes())
    assert created.header["confirmed_by"]["actor"] == "Other"


def test_absolute_input_inside_root_is_accepted(populated):
    relative, path = draft(populated, ObjectKind.CLAIM)
    fill(path, ObjectKind.CLAIM)
    result = new(populated, "claim", str(path), "--confirmed-by", "X", "--confirm")
    assert result.exit_code == 0, result.output


def test_status_ignores_drafts_directory(populated):
    draft(populated, ObjectKind.CLAIM)
    result = CliRunner().invoke(app, ["status", "demo", "--root", str(populated)])
    assert result.exit_code == 0, result.output


def test_handoff_apply_uses_default_actor(workbench):
    created = CliRunner().invoke(app, ["handoff", "demo", "--root", str(workbench)])
    assert created.exit_code == 0, created.output
    applied = CliRunner().invoke(
        app,
        [
            "handoff",
            "demo",
            "--root",
            str(workbench),
            "--apply",
            created.stdout.strip(),
            "--confirm",
        ],
        env={"TOULMIN_ACTOR": "Tianchi YU"},
    )
    assert applied.exit_code == 0, applied.output
    session = decode((workbench / applied.stdout.strip()).read_bytes())
    assert session.header["applied_by"] == "Tianchi YU"
