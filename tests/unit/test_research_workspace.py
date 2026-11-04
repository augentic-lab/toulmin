"""Current-state cards preserve file authority without adopting draft claims."""

from pathlib import Path

import pytest

from toulmin.core.codec import decode, encode
from toulmin.protocols.handoff import apply_handoff, draft_handoff
from toulmin.protocols.research_workspace import render_state, research_state
from toulmin.protocols.review_intake import intake_review


def edit(root: Path, relative: str, **values: str) -> None:
    path = root / "projects/demo" / relative
    document = decode(path.read_bytes())
    document.header.update(values)
    if relative.startswith("objections/") and values.get("status") == "answered":
        document.body = (
            "## Content\nFixture objection.\n\n## Response\nFixture response.\n\n"
            "## Ruling\nFixture ruling.\n"
        )
    path.write_bytes(encode(document))


def tree(root: Path) -> dict[str, tuple[object, ...]]:
    result = {}
    for path in (root, *sorted(root.rglob("*"))):
        info = path.lstat()
        content = (
            path.readlink() if path.is_symlink() else path.read_bytes() if path.is_file() else None
        )
        result[path.relative_to(root).as_posix()] = (info.st_mode, info.st_mtime_ns, content)
    return result


def test_empty_state_is_valid_read_only_and_has_only_current_context(workbench):
    before = tree(workbench)
    state = research_state(workbench, "demo")
    assert not state.errors
    assert state.objects == ()
    assert state.stage == "explore"
    assert state.last_handoff is None
    assert state.context_files == (
        "AGENTS.md",
        "projects/demo/PROJECT.md",
        "projects/demo/brief.md",
    )
    card = render_state(state)
    assert "QUESTION\nGoal:" in card
    assert "CONFIRMED\nStored object statuses" in card
    assert "Historical suggestion" in card
    assert "No applied handoff" in card
    assert render_state(research_state(workbench, "demo")) == card
    assert tree(workbench) == before


def test_status_edits_refresh_fingerprint_and_available_actions(populated):
    previous = research_state(populated, "demo")
    assert not previous.errors
    assert "Inspect open objections" in render_state(previous)
    edit(populated, "objections/O-001.md", status="answered")
    current = research_state(populated, "demo")
    assert not current.errors
    assert ("O-001", "answered") in current.objects
    assert previous.fingerprint != current.fingerprint
    assert "Inspect open objections" not in render_state(current)
    assert "Inspect open objections" in render_state(previous)


def test_recorded_next_step_is_never_live_completion_inference(populated):
    edit(populated, "PROJECT.md", next_step="Respond to O-001")
    edit(populated, "objections/O-001.md", status="answered")
    state = research_state(populated, "demo")
    assert not state.errors
    card = render_state(state)
    assert state.recorded_next_step == "Respond to O-001"
    assert "RECORDED NEXT STEP\nRespond to O-001\nHistorical suggestion" in card
    actions = card.split("ACTIONS\n", 1)[1]
    assert "Respond to O-001" not in actions


def test_only_applied_latest_handoff_enters_context(workbench):
    first = draft_handoff(workbench, "demo")
    old = apply_handoff(
        workbench, "demo", first.relative_to(workbench).as_posix(), "Fixture Researcher", True
    )
    second = draft_handoff(workbench, "demo")
    latest = apply_handoff(
        workbench, "demo", second.relative_to(workbench).as_posix(), "Fixture Researcher", True
    )
    conversations = workbench / "projects/demo/runs/conversations/main"
    conversations.mkdir(parents=True)
    (conversations / "transcript.md").write_text("Untrusted historical conversation")
    (workbench / "projects/demo/sessions/newer-unapplied.md").write_text("Not applied")
    state = research_state(workbench, "demo")
    assert not state.errors
    assert state.last_handoff == latest.relative_to(workbench).as_posix()
    assert state.context_files == (
        "AGENTS.md",
        "projects/demo/PROJECT.md",
        latest.relative_to(workbench).as_posix(),
        "projects/demo/brief.md",
    )
    assert old.relative_to(workbench).as_posix() not in state.context_files
    (conversations / "transcript.md").write_text("Changed raw history")
    assert research_state(workbench, "demo").fingerprint == state.fingerprint
    latest.write_text(latest.read_text() + "\nChanged applied handoff.\n")
    changed = research_state(workbench, "demo")
    assert changed.errors
    assert changed.fingerprint != state.fingerprint


def test_drafts_refresh_state_but_are_never_formal_or_claimed_pending(workbench):
    before = research_state(workbench, "demo")
    directory = workbench / "projects/demo/runs/drafts"
    directory.mkdir()
    draft = directory / "claim.md"
    draft.write_text("## Statement\nA yet unconfirmed idea.\n")
    state = research_state(workbench, "demo")
    assert not state.errors
    assert state.objects == () and state.pending_review == ()
    assert state.draft_files == ("projects/demo/runs/drafts/claim.md",)
    assert state.fingerprint != before.fingerprint
    assert "confirmation is not inferred" in render_state(state)
    assert "pending intake" not in render_state(state)
    draft.write_text("Changed working proposal\n")
    assert research_state(workbench, "demo").fingerprint != state.fingerprint


def test_brief_changes_refresh_fingerprint_and_raw_archives_do_not(workbench):
    before = research_state(workbench, "demo")
    output = workbench / "projects/demo/runs/20261031T100000Z-review/output.md"
    output.write_text("Raw output does not enter the current-state context")
    cache = workbench / "projects/demo/.integration-cache"
    cache.mkdir()
    (cache / "session.json").write_text("{}")
    generated = workbench / "projects/demo/runs/20261104T100000Z-aoe-context-fixture"
    generated.mkdir()
    (generated / "context.md").write_text("Regenerated model context")
    (generated / "state.md").write_text("A prior state card")
    (generated / "manifest.json").write_text("{}")
    (generated / "inputs").mkdir()
    (generated / "inputs/brief.md").write_text("Frozen brief")
    assert research_state(workbench, "demo").fingerprint == before.fingerprint
    (workbench / "projects/demo/brief.md").write_text("# Updated brief\n")
    assert research_state(workbench, "demo").fingerprint != before.fingerprint


def test_review_pending_comes_from_validated_intake_not_arbitrary_drafts(populated):
    output = "projects/demo/runs/20261031T100000Z-review/output.md"
    (populated / output).write_text(
        "```yaml\n"
        "- label: draft-1\n  target: C-001\n  severity: major\n"
        "  content: Question one\n  grounds: Missing measurement\n"
        "- label: draft-2\n  target: C-001\n  severity: minor\n"
        "  content: Question two\n  grounds: Ambiguous wording\n"
        "```\n"
    )
    assert research_state(populated, "demo").pending_review == ()
    intake_review(
        populated,
        "demo",
        output,
        "Fixture Researcher",
        True,
        reject={"draft-1": "Not needed"},
    )
    state = research_state(populated, "demo")
    assert not state.errors
    assert state.pending_review == ("R-001: draft-2",)
    assert "choose intake outcomes" in render_state(state)
    intake_review(
        populated,
        "demo",
        output,
        "Fixture Researcher",
        True,
        reject={"draft-2": "Already clear"},
    )
    settled = research_state(populated, "demo")
    assert settled.pending_review == () and not settled.errors
    assert settled.fingerprint != state.fingerprint
    assert "choose intake outcomes" not in render_state(settled)


@pytest.mark.parametrize("target", ["claims/C-001.md", "brief.md", "PROJECT.md"])
def test_malformed_research_data_is_visible_and_not_repaired(populated, target):
    path = populated / "projects/demo" / target
    path.write_text("[[C-999]]\n" if target == "brief.md" else "bad document\n")
    before = tree(populated)
    state = research_state(populated, "demo")
    assert state.errors
    card = render_state(state)
    assert "data: INVALID" in card and "ERRORS\n" in card
    assert "Continue research discussion" not in card
    assert tree(populated) == before


@pytest.mark.parametrize("target", ["brief.md", "claims/C-001.md", "runs/drafts"])
def test_symlinks_fail_visibly_without_reading_outside(populated, tmp_path, target):
    path = populated / "projects/demo" / target
    outside = tmp_path / "private"
    outside.write_text("SECRET-OUTSIDE")
    if path.exists():
        path.unlink()
    path.symlink_to(outside)
    before = tree(populated)
    state = research_state(populated, "demo")
    assert state.errors and "symlinks forbidden" in "\n".join(state.errors)
    assert "SECRET-OUTSIDE" not in render_state(state)
    assert tree(populated) == before


def test_invalid_project_and_root_return_diagnostics(workbench, tmp_path):
    assert research_state(workbench, "../outside").errors
    assert research_state(tmp_path / "absent", "demo").errors


def test_interrupted_write_is_incomplete_and_read_only(workbench):
    valid = research_state(workbench, "demo")
    (workbench / "projects/demo/.handoff-pending").mkdir()
    before = tree(workbench)
    state = research_state(workbench, "demo")
    assert state.errors and "interrupted application" in "\n".join(state.errors)
    assert valid.fingerprint != state.fingerprint
    assert tree(workbench) == before


def test_archive_draft_directory_is_reported_instead_of_silently_skipped(workbench):
    (workbench / "projects/demo/runs/20261031T100000Z-review/draft.md").mkdir()
    state = research_state(workbench, "demo")
    assert state.errors and "expected regular file" in "\n".join(state.errors)


def test_relevant_object_edits_never_mutate_the_files(populated):
    before = tree(populated)
    state = research_state(populated, "demo")
    assert len(state.objects) == 7 and not state.errors
    assert "records, not scientific validation" in render_state(state)
    assert tree(populated) == before
