"""R1: prefilled proposal drafts and batch rulings; temporary workbenches only."""

import re
import shutil
from dataclasses import replace

import pytest
from typer.testing import CliRunner

from toulmin.cli.app import app
from toulmin.core.atomic import digest
from toulmin.core.codec import decode, encode
from toulmin.core.documents import FormatError
from toulmin.core.project_proposals import (
    Outcome,
    render_outcome,
    validate_brief_proposal,
    validate_intake_recommendation,
    validate_review_request,
    validate_ruling_proposal,
    validate_stage_proposal,
)
from toulmin.protocols import project_proposals
from toulmin.protocols.research_map import research_map
from toulmin.protocols.ruling import apply_ruling

FOLDER = "projects/demo/runs/proposals"
OUTPUT = "projects/demo/runs/20261031T100000Z-review/output.md"
DRAFTS = (
    "Review prose.\n\n```yaml\n- label: draft-1\n  target: C-001\n  severity: major\n"
    "  content: The load is unspecified.\n  grounds: No trace.\n"
    "- label: draft-2\n  target: C-001\n  severity: minor\n"
    "  content: The baseline is old.\n  grounds: 2019 kernel.\n```\n"
)


def draft(root, *args):
    result = CliRunner().invoke(app, ["draft", *args, "--root", str(root)])
    return result


def written(root, result):
    assert result.exit_code == 0, result.output
    path = root / result.stdout.strip()
    assert path.parent == root / "projects/demo/runs/drafts"
    return path


def propose(root, path, text):
    """Move a filled draft into proposals/ under its own name, as the agent would."""
    folder = root / FOLDER
    folder.mkdir(exist_ok=True)
    (folder / path.name).write_text(text)
    path.unlink()
    return f"{FOLDER}/{path.name}"


def second_objection(root):
    folder = root / "projects/demo/objections"
    text = (folder / "O-001.md").read_text().replace("id: O-001", "id: O-002")
    (folder / "O-002.md").write_text(text)


def decision(root, number, related):
    folder = root / "projects/demo/decisions"
    document = decode((folder / "D-001.md").read_bytes())
    header = {**document.header, "id": f"D-{number:03d}", "related": related}
    (folder / f"D-{number:03d}.md").write_bytes(encode(replace(document, header=header)))


def test_a_ruling_draft_shows_current_status_and_is_refused_until_filled(populated):
    path = written(populated, draft(populated, "ruling", "demo", "--object", "O-001"))
    assert path.name.startswith("ruling-")
    text = path.read_text()
    assert "object: O-001  # current status: open" in text
    assert '"<fill: answered | accepted | deferred>"' in text  # open itself is not offered
    assert "## Response\n<fill:" in text and "## Ruling\n<fill:" in text
    relative = propose(populated, path, text)
    shown = project_proposals.preview(populated, "demo", relative)
    assert shown.problems == (
        "unfilled <fill: ...> placeholder; ask the agent to finish the draft",
    )


def test_response_and_status_in_one_ruling(populated):
    path = written(
        populated,
        draft(populated, "ruling", "demo", "--object", "O-001", "--status", "answered",
              "--decision", "D-001"),
    )  # fmt: skip
    text = path.read_text()
    text = re.sub(r"## Why\n<fill:[^\n]*", "## Why\nThe drift run answers it.", text)
    text = re.sub(r"## Response\n<fill:[^\n]*", "## Response\nThe drift run covers it.", text)
    text = re.sub(r"\n## Ruling\n<fill:[^\n]*\n", "\n", text)
    relative = propose(populated, path, text)
    shown = project_proposals.preview(populated, "demo", relative)
    assert shown.problems == ()
    assert shown.change.status == "answered" and shown.change.sections == ("Response",)
    project_proposals.apply(populated, "demo", relative, "Researcher", shown.sha256, "a")
    objection = (populated / "projects/demo/objections/O-001.md").read_text()
    assert "status: answered" in objection and "The drift run covers it." in objection


def batch(root, decision_id="D-002"):
    second_objection(root)
    path = written(
        root,
        draft(root, "ruling", "demo", "--object", "O-001,O-002", "--status", "deferred",
              "--decision", decision_id),
    )  # fmt: skip
    text = path.read_text()
    assert "objects: [O-001, O-002]\n# current: O-001 open, O-002 open" in text
    text = re.sub(r"## Why\n<fill:[^\n]*", "## Why\nSet aside until the build stage.", text)
    text = re.sub(r"\n## Response\n<fill:[^\n]*\n", "\n", text)
    text = re.sub(r"## Ruling\n<fill:[^\n]*", "## Ruling\nDeferred: out of scope for now.", text)
    return propose(root, path, text)


def test_a_batch_ruling_rules_every_object_with_one_decision(populated):
    decision(populated, 2, ["O-001", "O-002"])
    relative = batch(populated)
    shown = project_proposals.preview(populated, "demo", relative)
    assert shown.problems == ()
    assert [change.object_id for change in shown.changes] == ["O-001", "O-002"]
    done = project_proposals.apply(populated, "demo", relative, "Researcher", shown.sha256, "a")
    assert done.result == "O-001, O-002"
    for name in ("O-001", "O-002"):
        text = (populated / f"projects/demo/objections/{name}.md").read_text()
        assert "status: deferred" in text and "Deferred: out of scope for now." in text
        assert "- D-002" in text or "[D-002]" in text
    assert not any(
        move.text.startswith("Inspect open objections")
        for move in research_map(populated, "demo").moves
    )


def test_a_batch_needs_a_decision_naming_every_object(populated):
    decision(populated, 2, ["O-001"])
    relative = batch(populated)
    shown = project_proposals.preview(populated, "demo", relative)
    assert "must name O-002" in shown.problems[0]


def test_an_interrupted_batch_rules_only_the_objects_left(populated):
    decision(populated, 2, ["O-001", "O-002"])
    relative = batch(populated)
    shown = project_proposals.preview(populated, "demo", relative)
    apply_ruling(populated, "demo", "O-001", "Researcher", True, status="deferred",
                 decision="D-002", texts=shown.ruling.texts)  # fmt: skip
    marker = Outcome(relative, shown.sha256, "applying", "Researcher", "2026-11-09T10:00:00Z",
                     "a", None, None)  # fmt: skip
    (populated / project_proposals.outcome_path(relative)).write_bytes(render_outcome(marker))
    again = project_proposals.preview(populated, "demo", relative)
    assert again.done == ("O-001",) and [c.object_id for c in again.changes] == ["O-002"]
    project_proposals.apply(populated, "demo", relative, "Researcher", again.sha256, "a")
    text = (populated / "projects/demo/objections/O-001.md").read_text()
    assert text.count("Deferred: out of scope for now.") == 1  # not added twice


def header(fields):
    body = "## Why\nBecause.\n"
    return decode(("---\nschema_version: 1\nkind: ruling-proposal\n" + fields + "---\n" + body)
                  .encode())  # fmt: skip


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        (
            "object: O-001\nobjects: [O-001, O-002]\nstatus: deferred\n",
            "object \\(one ID\\) or objects",
        ),
        ("objects: [O-001]\nstatus: deferred\n", "two or more"),
        ("objects: [C-001, O-001]\nstatus: deferred\n", "one kind"),
        ("objects: [C-001, C-002]\nlinks: {superseded_by: C-003}\n", "rule each separately"),
    ],
)
def test_batch_format_checks(fields, message):
    with pytest.raises(FormatError, match=message):
        validate_ruling_proposal(header(fields))


def test_an_intake_draft_lists_every_undecided_label(populated):
    (populated / OUTPUT).write_text(DRAFTS)
    path = written(populated, draft(populated, "intake", "demo", "--run", "R-001"))
    text = path.read_text()
    assert f'output: "{OUTPUT}"' in text
    assert "# draft-1 -> C-001, major: The load is unspecified." in text
    assert '- label: "draft-2"' in text
    filled = text.replace('"<fill: take | partly | reject>"', "take")
    filled = re.sub(r'"<fill: your grounds[^"]*"', '"Sound."', filled)
    filled = re.sub(r"\n## Notes\n<fill:[^\n]*\n", "\n", filled)
    recommendation = validate_intake_recommendation(decode(filled.encode()))
    assert [item.label for item in recommendation.items] == ["draft-1", "draft-2"]


def test_a_brief_draft_carries_the_digest_and_current_text(populated):
    brief = populated / "projects/demo/brief.md"
    path = written(populated, draft(populated, "brief", "demo", "--section", "Kill criteria"))
    text = path.read_text()
    assert f'base_sha256: "{digest(brief.read_bytes())}"' in text
    text = re.sub(r"## Why\n<fill:[^\n]*", "## Why\nName the kill criteria.", text)
    text = re.sub(r"## Kill criteria\n.*", "## Kill criteria\nStop if p99 gains < 5%.\n", text,
                  flags=re.S)  # fmt: skip
    assert validate_brief_proposal(decode(text.encode())).sections == {
        "Kill criteria": "Stop if p99 gains < 5%.\n"
    }
    relative = propose(populated, path, text)
    shown = project_proposals.preview(populated, "demo", relative)
    assert shown.problems == () and any("Stop if p99" in line for line in shown.diff)
    result = draft(populated, "brief", "demo", "--section", "Nonsense")
    assert result.exit_code == 1 and "brief.md has Problem" in result.output


def test_stage_and_review_drafts(populated):
    path = written(populated, draft(populated, "stage", "demo"))
    text = path.read_text()
    assert "from: explore\nto: critique\n" in text
    filled = re.sub(r'"<fill: D-NNN[^"]*"', "D-001", text)
    filled = re.sub(r"## Why\n<fill:[^\n]*", "## Why\nG1 holds.", filled)
    assert validate_stage_proposal(decode(filled.encode())).stage == "critique"
    assert draft(populated, "stage", "demo", "--to", "explore").exit_code == 1
    path = written(
        populated, draft(populated, "review", "demo", "--claim", "C-001", "--persona", "skeptic")
    )
    filled = re.sub(r"## Why now\n<fill:[^\n]*", "## Why now\nNew Claims.", path.read_text())
    request = validate_review_request(decode(filled.encode()))
    assert request.claims == ["C-001"] and request.personas == ["skeptic"]
    assert request.models is None
    assert draft(populated, "review", "demo", "--claim", "C-009").exit_code == 1


def test_options_belong_to_their_kinds(populated):
    before = sorted(populated.rglob("*"))
    for args in (
        ("claim", "demo", "--object", "O-001"),
        ("ruling", "demo"),
        ("ruling", "demo", "--object", "O-001", "--run", "R-001"),
        ("ruling", "demo", "--object", "O-001,E-001"),
        ("ruling", "demo", "--object", "O-001", "--status", "superseded"),
        ("ruling", "demo", "--object", "O-001", "--status", "open"),  # already open
        ("intake", "demo", "--run", "R-001"),  # the fixture output has no drafts
    ):
        result = draft(populated, *args)
        assert result.exit_code == 1, (args, result.output)
    assert sorted(populated.rglob("*")) == before  # nothing written on refusal
    shutil.rmtree(populated / "projects/demo/runs/drafts", ignore_errors=True)
