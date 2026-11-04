"""WI4: workspace handoff drafts, confirmed session records and file-based entry.

Temporary workspaces only; no AoE client, model, network or real research project.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toulmin.cli.app import app
from toulmin.cli.initialize import initialize, initialize_workspace
from toulmin.core import workspace_journal
from toulmin.core.atomic import digest
from toulmin.core.documents import FormatError
from toulmin.protocols import workspace_handoff
from toulmin.protocols.workspace_change import apply as apply_change
from toulmin.protocols.workspace_change import propose, reject
from toulmin.protocols.workspace_handoff import apply, draft, latest_handoff

runner = CliRunner()
DOCS = Path(__file__).resolve().parents[2] / "docs"
ACTIVITY = "runs/20261104T093000Z-activity-6b1f0c2e9a4d4e7f8c3b2a1d0e9f8a7b/activity.md"
FIRST = "runs/20261104T100000Z-proposal-0d9e8c7b6a5f4e3d2c1b0a9f8e7d6c5b"
PACKET = "runs/20261104T101500Z-proposal-a41c9e07d3b24f5e9b6c8d7e1f203a4b"
CHANGE = "runs/drafts/workspace-direction.md"
TRACE = "shared/data/synthetic-queue-trace"
FOCUS = '  - target: charter\n    sections: {Focus: "Compare FIFO and SRPT first."}\n'
INPUT = "runs/drafts/workspace-handoff.md"
DRAFT = "runs/20261104T113000Z-handoff-5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b/draft.md"
RECEIPT = f"{PACKET}/receipt.md"


def blocks():
    text = (DOCS / "workspace-formats.md").read_text()
    parts = [part.split("\n````", 1)[0] + "\n" for part in text.split("````markdown\n")[1:]]

    def one(*needles, without="\0"):
        found = [p for p in parts if all(n in p for n in needles) and without not in p]
        assert len(found) == 1, needles
        return found[0].encode()

    return {
        "input": one("kind: workspace-handoff-input"),
        "draft": one("kind: workspace-handoff\n", without="source_draft:"),
        "record": one("kind: workspace-handoff\n", "source_draft:"),
        "charter": one("charter_revision: 1", "last_handoff: 2026"),
    }


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def example_block(*needles):
    text = (DOCS / "workspace-formats.md").read_text()
    parts = [part.split("\n````", 1)[0] + "\n" for part in text.split("````markdown\n")[1:]]
    found = [part for part in parts if all(needle in part for needle in needles)]
    assert len(found) == 1, needles
    return found[0].encode()


@pytest.fixture
def root(tmp_path):
    """The contract fixture (as in the WI3 tests): workspace, synthetic trace, activity."""
    root = tmp_path / "serving"
    initialize_workspace(root, "Serving Research")
    (root / TRACE).mkdir(parents=True)
    (root / TRACE / "trace.csv").write_text("arrival_us,service_us\n0,180\n240,95\n410,620\n")
    (root / TRACE / "README.md").write_text(
        "Synthetic single-queue trace for the WS3 fixture. Not a measurement.\n"
    )
    (root / ACTIVITY).parent.mkdir(parents=True)
    (root / ACTIVITY).write_bytes(example_block("kind: workspace-activity"))
    return root


def contents(root):
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.relative_to(root).parts[0] != "runs"
    }


def confirm(root, packet, actor="Tianchi YU", **extra):
    return apply_change(root, packet, actor, confirmed=True, **extra)


def invoke(*args, env=None):
    return runner.invoke(app, [str(arg) for arg in args], env=env or {"TOULMIN_ACTOR": ""})


def write_input(root, changes, name="change.md"):
    text = (
        "---\nschema_version: 1\nkind: workspace-change-input\nscope: {kind: workspace}\n"
        f"supersedes: null\nsources: []\npins: []\nchanges:\n{changes}"
        "---\n## Question\nChange it?\n\n## Unresolved assumptions\nNone.\n"
    )
    (root / "runs/drafts" / name).write_text(text)
    return f"runs/drafts/{name}"


@pytest.fixture
def applied(root):
    """The WI3 contract change applied: the charter has a direction and one receipt."""
    data = example_block("kind: workspace-change-input")
    (root / CHANGE).write_bytes(data.replace(f"supersedes: {FIRST}".encode(), b"supersedes: null"))
    propose(root, CHANGE, at("2026-11-04T10:00:00"), FIRST.rsplit("-", 1)[1])
    (root / CHANGE).write_bytes(data)
    propose(root, CHANGE, at("2026-11-04T10:15:00"), PACKET.rsplit("-", 1)[1])
    confirm(root, PACKET, now=at("2026-11-04T10:20:00"))
    return root


def summary(root, name="summary.md", *, header="", body=None):
    sections = body or (
        "## Done\nTalked.\n\n## Confirmed changes\nNone.\n\n"
        "## Pending ideas\n- Caching (unconfirmed).\n\n## Open questions\nNone.\n"
    )
    text = (
        "---\nschema_version: 1\nkind: workspace-handoff-input\n"
        + (header or 'next_step: "Plan the next discussion."\n')
        + "---\n"
        + sections
    )
    (root / "runs/drafts" / name).write_text(text)
    return f"runs/drafts/{name}"


def precise(text):
    return datetime.fromisoformat(text.removesuffix("Z")).replace(tzinfo=UTC)


def example(root):
    """Draft and apply the contract's section 8 example with its fixed time and id."""
    (root / INPUT).write_bytes(blocks()["input"])
    outcome = draft(root, INPUT, precise("2026-11-04T11:30:00.412Z"), DRAFT.split("-")[-1][:32])
    return outcome


# Draft: sealed, readable, nothing else written.


def test_contract_example_is_reproduced_byte_for_byte(applied):
    expected = blocks()
    record_block = expected["record"]
    before = contents(applied)
    outcome = example(applied)
    assert outcome.loaded.path == DRAFT
    content = (applied / DRAFT).read_bytes()
    assert content == expected["draft"]
    assert (applied / DRAFT).parent.joinpath("seal").read_text() == digest(content) + "\n"
    assert contents(applied) == before  # drafting writes only its runs/ directory
    result = apply(
        applied, DRAFT, "Tianchi YU", confirmed=True, now=precise("2026-11-04T11:35:00.108Z")
    )
    assert result.status == "applied"
    assert result.record == f"sessions/20261104T113500Z-{digest(content)}.md"
    assert (applied / result.record).read_bytes() == record_block
    assert (applied / "WORKSPACE.md").read_bytes() == expected["charter"]
    assert not (applied / workspace_journal.JOURNAL).exists()
    assert latest_handoff(applied).filename == result.record.removeprefix("sessions/")


def test_draft_cli_shows_scope_summary_and_apply_command(applied):
    path = summary(applied, header=f'confirmed_changes: [{RECEIPT}]\nnext_step: "Next."\n')
    result = invoke("aoe", "handoff", "--root", applied, "--input", path)
    assert result.exit_code == 0, result.output
    for line in (
        f"Root: {applied}",
        "Scope: Workspace",
        f"Confirmed changes: {RECEIPT}",
        "Next step: Next.",
        "## Pending ideas\n- Caching (unconfirmed).",
        "pending ideas stay pending",
        "--apply runs/",
        "--confirmed-by ACTOR --confirm",
    ):
        assert line in result.stdout, line
    explicit = invoke("aoe", "handoff", "--workspace", "--root", applied, "--input", path)
    assert explicit.exit_code == 0, explicit.output
    both = invoke("aoe", "handoff", "scheduling", "--workspace", "--root", applied, "--input", path)
    assert both.exit_code == 2


FOUR = "## Done\nx\n\n## Confirmed changes\nx\n\n## Pending ideas\nx\n\n## Open questions\nx\n"
MISSING_RECEIPT = PACKET.replace("a41c", "ffff") + "/receipt.md"


@pytest.mark.parametrize(
    ("header", "body", "message"),
    [
        ("", FOUR + "\n## Next step\nx\n", "body.Next step: generated"),
        ("", FOUR.split("\n## Open questions")[0] + "\n", "body.Open questions"),
        (f"confirmed_changes: [{MISSING_RECEIPT}]\n", None, "expected existing"),
        ("session_id: 7\n", None, "session_id"),
    ],
)
def test_malformed_summaries_are_refused_without_repair(applied, header, body, message):
    path = summary(applied, header=header + 'next_step: "N."\n', body=body)
    before = (applied / path).read_bytes()
    with pytest.raises(FormatError, match=message):
        draft(applied, path)
    assert (applied / path).read_bytes() == before
    assert not list((applied / "runs").glob("*-handoff-*"))


def test_wrong_inputs_name_the_expected_kind(applied):
    change = write_input(applied, FOCUS)
    with pytest.raises(FormatError, match="workspace change input; use workspace propose"):
        draft(applied, change)
    (applied / "runs/drafts/project.md").write_text(
        "---\nsession_id: null\nrecent_decisions: []\nnext_step: x\n---\n## Done\nx\n"
    )
    with pytest.raises(FormatError, match="project handoff summary; use aoe handoff PROJECT"):
        draft(applied, "runs/drafts/project.md")
    with pytest.raises(FormatError, match="review packet"):
        draft(applied, PACKET)
    (applied / "projects/x").mkdir()
    (applied / "projects/x/summary.md").write_text("x\n")
    with pytest.raises(FormatError, match="belongs to that project"):
        draft(applied, "projects/x/summary.md")


def test_confirmed_changes_must_be_applied_receipts(applied):
    other = propose(applied, write_input(applied, FOCUS))
    reject(applied, other.loaded.directory, "No.", "R")
    path = summary(
        applied,
        header=f'confirmed_changes: [{other.loaded.directory}/receipt.md]\nnext_step: "N."\n',
    )
    with pytest.raises(FormatError, match="expected an applied receipt; found rejected"):
        draft(applied, path)


def test_next_step_is_inherited_or_required(applied):
    path = summary(applied, header="session_id: null\n")
    with pytest.raises(FormatError, match="next_step: required"):
        draft(applied, path)
    first = draft(applied, summary(applied, "first.md"))
    apply(applied, first.loaded.path, "R", confirmed=True)
    inherited = draft(applied, path)
    assert inherited.loaded.draft.next_step == "Plan the next discussion."


# Apply: only continuity fields, idempotent, stale and wrong drafts refused.


def test_apply_changes_only_continuity_fields_and_sessions(applied, tmp_path):
    template = tmp_path / "template"
    initialize(template, "scheduling")
    (template / "projects/scheduling").rename(applied / "projects/scheduling")
    charter = applied / "WORKSPACE.md"
    # A hand-quoted name must survive byte for byte: only two header lines change.
    charter.write_text(
        charter.read_text().replace('name: "Serving Research"', "name: 'Serving Research'")
    )
    outcome = draft(applied, summary(applied))
    lines_before = charter.read_text().splitlines()
    before = contents(applied)
    result = invoke(
        "aoe", "handoff", "--root", applied, "--apply", outcome.loaded.path,
        "--confirmed-by", "Tianchi YU", "--confirm",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert "Changed: WORKSPACE.md next_step and last_handoff only" in result.stdout
    after = contents(applied)
    changed = {key for key in after if before.get(key) != after[key]}
    record = next(key for key in changed if key.startswith("sessions/"))
    assert changed == {"WORKSPACE.md", record}
    lines_after = charter.read_text().splitlines()
    differing = [b for a, b in zip(lines_before, lines_after, strict=True) if a != b]
    assert [line.split(":")[0] for line in differing] == ["next_step", "last_handoff"]
    assert "name: 'Serving Research'" in lines_after
    assert "- Caching (unconfirmed)." in (applied / record).read_text()  # still pending, quoted


def test_preview_missing_confirmation_and_actor(applied):
    outcome = draft(applied, summary(applied))
    before = contents(applied)
    args = ("aoe", "handoff", "--root", applied, "--apply", outcome.loaded.path)
    preview = invoke(*args)
    assert preview.exit_code == 0, preview.output
    assert "Preview only; nothing written." in preview.stdout
    refused = invoke(*args, "--confirmed-by", "R")
    assert refused.exit_code == 1 and "confirmation missing" in refused.stderr
    assert invoke(*args, "--confirm").exit_code == 2
    assert contents(applied) == before


def test_repeat_apply_returns_the_original_record(applied):
    outcome = draft(applied, summary(applied))
    first = apply(applied, outcome.loaded.path, "Tianchi YU", confirmed=True)
    state = contents(applied)
    again = invoke(
        "aoe", "handoff", "--root", applied, "--apply", outcome.loaded.path,
        "--confirmed-by", "Someone Else", "--confirm",
    )  # fmt: skip
    assert again.exit_code == 0, again.output
    assert "Already applied; nothing written." in again.stdout
    assert f"Record: {first.record}" in again.stdout
    assert contents(applied) == state
    assert 'applied_by: "Tianchi YU"' in (applied / first.record).read_text()


def test_history_chain_keeps_every_record_and_replays_older_drafts(applied):
    one = draft(applied, summary(applied, "one.md"))
    first = apply(applied, one.loaded.path, "R", confirmed=True)
    two = draft(applied, summary(applied, "two.md", header='next_step: "Second."\n'))
    second = apply(applied, two.loaded.path, "R", confirmed=True)
    record = (applied / second.record).read_text()
    assert f"previous_handoff: {first.record.removeprefix('sessions/')}" in record
    assert apply(applied, one.loaded.path, "R", confirmed=True).record == first.record
    history = workspace_handoff.chain(applied)
    assert [item.filename for item in history] == [
        second.record.removeprefix("sessions/"),
        first.record.removeprefix("sessions/"),
    ]
    status = invoke("status", "--root", applied, "--verbose")
    assert "Recorded next step: Second." in status.stdout
    assert f"{one.loaded.path} | applied" in status.stdout


def test_stale_drafts_are_shown_and_refused(applied):
    old = draft(applied, summary(applied, "old.md"))
    newer = draft(applied, summary(applied, "newer.md"))
    apply(applied, newer.loaded.path, "R", confirmed=True)
    status = invoke("status", "--root", applied)
    assert f"{old.loaded.path} | stale" in status.stdout
    assert f"{newer.loaded.path} | applied" not in status.stdout  # applied is not pending work
    before = contents(applied)
    with pytest.raises(FormatError, match="changed since drafting.*stale draft"):
        apply(applied, old.loaded.path, "R", confirmed=True)
    assert contents(applied) == before
    # A charter change also makes an unapplied draft stale.
    later = draft(applied, summary(applied, "later.md"))
    change = propose(applied, write_input(applied, FOCUS))
    confirm(applied, change.loaded.directory)
    with pytest.raises(FormatError, match="stale draft"):
        apply(applied, later.loaded.path, "R", confirmed=True)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (INPUT, "an input or an applied record"),
        (PACKET, "review packet"),
        ("projects/scheduling/runs/20261104T113000Z-handoff-abc/draft.md", "project handoff draft"),
        ("runs/20261104T113000Z-handoff-" + "0" * 32, "No such file|expected existing"),
    ],
)
def test_wrong_artifacts_are_refused(applied, value, message):
    with pytest.raises(FormatError, match=message):
        apply(applied, value, "R", confirmed=True)


def test_edited_or_rescoped_drafts_are_refused(applied):
    outcome = draft(applied, summary(applied))
    path = applied / outcome.loaded.path
    original = path.read_bytes()
    path.write_bytes(original.replace(b"Talked.", b"Talked a lot."))
    with pytest.raises(FormatError, match="seal mismatch"):
        apply(applied, outcome.loaded.path, "R", confirmed=True)
    rescoped = original.replace(b"scope: {kind: workspace}", b"scope: {kind: project, project: x}")
    path.write_bytes(rescoped)
    (path.parent / "seal").write_text(digest(rescoped) + "\n")
    with pytest.raises(FormatError, match="scope"):
        apply(applied, outcome.loaded.path, "R", confirmed=True)


# Recovery and file-only entry.


def crash_before(monkeypatch, suffix):
    real = workspace_journal.write_atomic

    def write(path, data, *, replace=False):
        if Path(path).as_posix().endswith(suffix) and ".workspace-" not in str(path):
            raise OSError("simulated crash")
        return real(path, data, replace=replace)

    monkeypatch.setattr(workspace_journal, "write_atomic", write)


@pytest.mark.parametrize("suffix", [".md", "WORKSPACE.md"])
def test_interrupted_apply_is_incomplete_then_recovers_once(applied, monkeypatch, suffix):
    outcome = draft(applied, summary(applied))
    crash_before(monkeypatch, suffix if suffix == "WORKSPACE.md" else f"{outcome.loaded.seal}.md")
    with pytest.raises(OSError, match="simulated crash"):
        apply(applied, outcome.loaded.path, "Tianchi YU", confirmed=True)
    monkeypatch.undo()
    status = invoke("status", "--root", applied)
    assert status.exit_code == 1
    assert "incomplete workspace-handoff" in status.stderr
    assert f"{outcome.loaded.path} | incomplete" in status.stdout
    assert "orphan" not in status.stderr  # the journal explains the record
    preview = invoke("aoe", "handoff", "--root", applied, "--apply", outcome.loaded.path)
    assert "State: publication incomplete" in preview.stdout
    with pytest.raises(FormatError, match="incomplete workspace publication"):
        draft(applied, summary(applied, "other.md"))
    result = apply(applied, outcome.loaded.path, "Someone Else", confirmed=True)
    assert result.status == "recovered"
    assert "recovery keeps the first confirmation by Tianchi YU" in result.problems[0]
    assert latest_handoff(applied).record.applied_by == "Tianchi YU"
    assert apply(applied, outcome.loaded.path, "R", confirmed=True).status == "replayed"
    assert invoke("status", "--root", applied).exit_code == 0


def test_crash_before_retire_finishes_on_rerun(applied, monkeypatch):
    outcome = draft(applied, summary(applied))
    monkeypatch.setattr(
        workspace_journal, "retire", lambda repository: (_ for _ in ()).throw(OSError("crash"))
    )
    with pytest.raises(OSError):
        apply(applied, outcome.loaded.path, "R", confirmed=True)
    monkeypatch.undo()
    assert (applied / workspace_journal.JOURNAL).is_dir()
    assert apply(applied, outcome.loaded.path, "R", confirmed=True).status == "recovered"
    assert not (applied / workspace_journal.JOURNAL).exists()


def test_external_edit_during_recovery_is_preserved(applied, monkeypatch):
    outcome = draft(applied, summary(applied))
    crash_before(monkeypatch, "WORKSPACE.md")
    with pytest.raises(OSError):
        apply(applied, outcome.loaded.path, "R", confirmed=True)
    monkeypatch.undo()
    charter = applied / "WORKSPACE.md"
    charter.write_text(charter.read_text() + "\nResearcher's note.\n")
    with pytest.raises(FormatError, match="changed outside this publication.*journal kept"):
        apply(applied, outcome.loaded.path, "R", confirmed=True)
    assert charter.read_text().endswith("Researcher's note.\n")
    assert (applied / workspace_journal.JOURNAL).is_dir()


def test_entry_uses_only_the_latest_applied_record(applied):
    pending = draft(applied, summary(applied))
    assert latest_handoff(applied) is None  # an unconfirmed draft never substitutes
    orphan = applied / "sessions" / f"20261104T120000Z-{'ab' * 32}.md"
    orphan.write_text("---\nkind: workspace-handoff\n---\nUnlinked.\n")
    assert latest_handoff(applied) is None
    status = invoke("status", "--root", applied)
    assert status.exit_code == 1
    assert "orphan session record" in status.stderr
    assert "Last handoff: none (no applied workspace handoff)" in status.stdout
    assert orphan.read_text().endswith("Unlinked.\n")  # preserved
    orphan.unlink()
    result = apply(applied, pending.loaded.path, "R", confirmed=True)
    assert latest_handoff(applied).filename == result.record.removeprefix("sessions/")


# Compatibility: project handoffs, zero children and legacy roots.


def test_workspace_with_zero_children_hands_off(root):
    charter = root / "WORKSPACE.md"
    path = summary(root)
    outcome = draft(root, path)
    apply(root, outcome.loaded.path, "R", confirmed=True)
    assert "charter_revision: 0" in charter.read_text()
    assert 'next_step: "Plan the next discussion."' in charter.read_text()
    assert sorted(p.name for p in (root / "projects").iterdir()) == [".gitkeep"]


def test_project_handoff_in_a_workspace_is_unchanged(applied, tmp_path):
    template = tmp_path / "template"
    initialize(template, "scheduling")
    (template / "projects/scheduling").rename(applied / "projects/scheduling")
    charter = (applied / "WORKSPACE.md").read_bytes()
    result = invoke("aoe", "handoff", "scheduling", "--root", applied)
    assert result.exit_code == 0, result.output
    path = result.stdout.strip()
    assert path.startswith("projects/scheduling/runs/") and path.endswith("/draft.md")
    applied_result = invoke(
        "aoe", "handoff", "scheduling", "--root", applied, "--apply", path,
        "--confirmed-by", "R", "--confirm",
    )  # fmt: skip
    assert applied_result.exit_code == 0, applied_result.output
    assert applied_result.stdout.strip().startswith("projects/scheduling/sessions/")
    assert (applied / "WORKSPACE.md").read_bytes() == charter
    assert not [p for p in (applied / "sessions").iterdir() if p.name != ".gitkeep"]
    with pytest.raises(FormatError, match="project handoff draft"):
        apply(applied, path, "R", confirmed=True)


def test_legacy_root_has_no_workspace_handoff(tmp_path):
    legacy = tmp_path / "legacy"
    initialize(legacy, "scheduling")
    (legacy / "runs/drafts").mkdir(parents=True)
    path = summary(legacy)
    result = invoke("aoe", "handoff", "--root", legacy, "--input", path)
    assert result.exit_code == 1
    assert "workspace state not configured" in result.stderr
