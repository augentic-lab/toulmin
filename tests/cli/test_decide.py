"""WX4: ``toulmin decide`` walks pending items one at a time; temporary workbenches only."""

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toulmin.cli import decide
from toulmin.cli.app import app
from toulmin.cli.initialize import initialize_workspace
from toulmin.core.codec import decode
from toulmin.core.proposals import validate_receipt
from toulmin.protocols import project_creation, workspace_change, workspace_handoff
from toulmin.protocols.handoff import draft_handoff

DOCS = Path(__file__).resolve().parents[2] / "docs"
FOCUS = '  - target: charter\n    sections: {Focus: "Compare FIFO and SRPT first."}\n'
SUMMARY = "runs/drafts/handoff.md"


def creation_input():
    text = (DOCS / "workspace-formats.md").read_text()
    parts = [part.split("\n````", 1)[0] + "\n" for part in text.split("````markdown\n")[1:]]
    block = next(part for part in parts if "kind: project-creation-input" in part)
    return re.sub(r"sources:\n(  - .*\n)+pins:\n(  - .*\n)+", "sources: []\npins: []\n", block)


def write(root, relative, text):
    (root / relative).write_text(text)
    return relative


def change(root, name="change.md"):
    return write(
        root,
        f"runs/drafts/{name}",
        "---\nschema_version: 1\nkind: workspace-change-input\nscope: {kind: workspace}\n"
        f"supersedes: null\nsources: []\npins: []\nchanges:\n{FOCUS}"
        "---\n## Question\nFocus?\n\n## Unresolved assumptions\nNone.\n",
    )


def summary(root, relative=SUMMARY, done="Discussed focus."):
    return write(
        root,
        relative,
        "---\nschema_version: 1\nkind: workspace-handoff-input\nsession_id: null\n"
        'confirmed_changes: []\nnext_step: "Decide the focus proposal."\n---\n'
        f"## Done\n{done}\n\n## Confirmed changes\nNone.\n\n"
        "## Pending ideas\n- Focus on FIFO vs SRPT (proposed).\n\n## Open questions\nNone.\n",
    )


@pytest.fixture(autouse=True)
def researcher(monkeypatch):
    monkeypatch.delenv("TOULMIN_ACTOR", raising=False)
    monkeypatch.setattr(decide, "_interactive", lambda: True)


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "serving"
    initialize_workspace(root, "Serving Research")
    return root


@pytest.fixture
def pending(root):
    """One pending change, one pending creation and one pending workspace handoff draft."""
    packet = workspace_change.propose(root, change(root)).loaded.directory
    project = write(root, "runs/drafts/project.md", creation_input())
    creation = project_creation.propose(root, "scheduling", project).loaded.directory
    handoff = workspace_handoff.draft(root, summary(root)).loaded.path
    return packet, creation, handoff


def run(root, answers="", *extra):
    args = ["decide", "--root", str(root), *extra]
    return CliRunner().invoke(app, args, input=answers)


def receipt(root, packet):
    path = root / packet / "receipt.md"
    return validate_receipt(decode(path.read_bytes(), str(path))) if path.exists() else None


def test_nothing_pending_says_so(root):
    result = run(root)
    assert result.exit_code == 0 and "Nothing awaits your decision." in result.output


def test_without_a_terminal_it_lists_and_changes_nothing(root, pending, monkeypatch):
    monkeypatch.setattr(decide, "_interactive", lambda: False)
    before = sorted(path.relative_to(root) for path in root.rglob("*"))
    result = run(root, "", "--confirmed-by", "Tianchi YU")
    assert result.exit_code == 0, result.output
    assert "Awaiting your decision: 3 item(s)." in result.output
    for label, path in zip(
        ("Workspace change", "Child creation", "Workspace handoff"), pending, strict=True
    ):
        assert f"  {label}: {path}" in result.output
    assert "nothing changed" in result.output
    assert sorted(path.relative_to(root) for path in root.rglob("*")) == before


def test_an_actor_is_required_before_anything_is_decided(root, pending):
    result = run(root, "a\n")
    assert result.exit_code == 2 and "actor" in result.output
    assert receipt(root, pending[0]) is None


def test_apply_reject_and_stale_handoff_regeneration_in_one_pass(root, pending):
    packet, creation, handoff = pending
    charter = (root / "WORKSPACE.md").read_text()
    result = run(root, "a\nr\nscope unclear\na\n", "--confirmed-by", "Tianchi YU")
    assert result.exit_code == 0, result.output
    # Previews come without the copy-paste command lines.
    assert "Apply: toulmin" not in result.output and "Create: toulmin" not in result.output
    applied = receipt(root, packet)
    assert applied.disposition == "applied" and applied.actor == "Tianchi YU"
    assert applied.approval_text == "toulmin decide: a"
    assert "Compare FIFO and SRPT first." in (root / "WORKSPACE.md").read_text()
    assert (root / "WORKSPACE.md").read_text() != charter
    rejected = receipt(root, creation)
    assert rejected.disposition == "rejected" and rejected.reason == "scope unclear"
    assert not (root / "projects/scheduling").exists()
    # The handoff drafted before the change went stale; it was regenerated and applied.
    assert "Regenerated from the same summary" in result.output
    assert (
        "Note: applied in this run but not cited by this summary (the record will not list "
        f"them): {packet}/receipt.md\n"
    ) in result.output
    regenerated = re.search(r"Regenerated from the same summary: (\S+)", result.output)[1]
    assert regenerated != handoff
    sessions = list((root / "sessions").glob("*.md"))
    assert len(sessions) == 1
    record = sessions[0].read_text()
    assert f"source_draft: {regenerated}" in record  # never the stale draft
    assert "Applied: 2 | Rejected: 1 | Skipped: 0 | Failed: 0" in result.output


def test_skip_and_quit_leave_items_pending(root, pending):
    result = run(root, "s\nq\n", "--confirmed-by", "Tianchi YU")
    assert result.exit_code == 0, result.output
    assert "Applied: 0 | Rejected: 0 | Skipped: 1 | Failed: 0 | Not shown: 1" in result.output
    assert "run `toulmin decide` again" in result.output
    assert receipt(root, pending[0]) is None and receipt(root, pending[1]) is None
    again = run(root, "q\n", "--confirmed-by", "Tianchi YU")
    assert "Awaiting your decision: 3 item(s)." in again.output


def test_a_refused_packet_offers_no_apply(root):
    packet = workspace_change.propose(root, change(root)).loaded.directory
    workspace_change.propose(root, change(root, "other.md"))
    (root / "WORKSPACE.md").write_text((root / "WORKSPACE.md").read_text() + "\nEdited.\n")
    result = run(root, "a\ns\ns\n", "--confirmed-by", "Tianchi YU")
    assert "Refused now:" in result.output
    assert "Choose one of: reject, skip, quit" in result.output
    assert receipt(root, packet) is None


def test_a_second_handoff_is_superseded_by_the_one_just_applied(root):
    drafts = {
        workspace_handoff.draft(root, summary(root)).loaded.path,
        workspace_handoff.draft(root, summary(root, "runs/drafts/b.md", "Other.")).loaded.path,
    }
    result = run(root, "a\n", "--confirmed-by", "Tianchi YU")
    assert result.exit_code == 0, result.output
    shown = re.findall(r"\] Workspace handoff: (\S+)", result.output)
    assert set(shown) == drafts  # same-second drafts have no fixed order
    assert "Superseded by the workspace handoff applied in this run; skipped." in result.output
    record = next((root / "sessions").glob("*.md")).read_text()
    assert f"source_draft: {shown[0]}" in record and shown[1] not in record


def test_a_changed_summary_is_not_regenerated(root):
    packet = workspace_change.propose(root, change(root)).loaded.directory
    workspace_handoff.draft(root, summary(root))
    summary(root, done="Rewritten after drafting.")
    result = run(root, "a\n", "--confirmed-by", "Tianchi YU")
    assert result.exit_code == 0, result.output
    assert receipt(root, packet).disposition == "applied"
    assert f"Not regenerated: summary {SUMMARY} changed since drafting" in result.output
    assert not (root / "sessions").exists() or not list((root / "sessions").glob("*.md"))


def test_project_handoffs_are_decided_and_stale_ones_not_offered(workbench, monkeypatch):
    first = draft_handoff(workbench, "demo").relative_to(workbench).as_posix()
    second = draft_handoff(workbench, "demo").relative_to(workbench).as_posix()
    monkeypatch.setenv("TOULMIN_ACTOR", "Tianchi YU")
    result = run(workbench, "a\n")
    assert result.exit_code == 0, result.output
    assert f"Project handoff: {first}" in result.output
    assert "superseded by the handoff of this project applied in this run" in result.output
    project = (workbench / "projects/demo/PROJECT.md").read_text()
    assert "last_handoff: " in project and "last_handoff: null" not in project
    # Both drafts are now stale or applied: nothing is offered again.
    again = run(workbench)
    assert "Nothing awaits your decision." in again.output
    assert "Not offered: 1 stale handoff draft(s)" in again.output
    assert second


def test_a_failing_item_is_reported_and_the_walk_continues(root, pending, monkeypatch):
    original = workspace_change.apply

    def broken(root_, value, actor, *, confirmed, **options):
        if confirmed:
            raise ValueError("disk full (fixture)")
        return original(root_, value, actor, confirmed=confirmed, **options)

    monkeypatch.setattr(decide.workspace_change, "apply", broken)
    result = run(root, "a\ns\ns\n", "--confirmed-by", "Tianchi YU")
    assert result.exit_code == 1
    assert "disk full (fixture)" in result.output and "stays pending" in result.output
    assert "Failed: 1" in result.output and receipt(root, pending[0]) is None
