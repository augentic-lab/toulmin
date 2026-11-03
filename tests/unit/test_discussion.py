"""Durability, provenance and confirmation boundaries for collaborative sessions."""

import pytest

from toulmin.core.codec import decode, encode
from toulmin.core.documents import FormatError
from toulmin.core.identifiers import ObjectId
from toulmin.core.repository import Repository
from toulmin.protocols import discussion
from toulmin.protocols.discussion import (
    apply_proposal,
    begin_turn,
    dismiss_proposal,
    finish_turn,
    get_turn_files,
    get_turn_prompt,
    load_discussion,
    preview_context,
    recover_turn,
    save_proposal_draft,
)
from toulmin.protocols.review import ReviewOutcome


def outcome(text="A useful answer", failure=None):
    return ReviewOutcome(text, "reported-model", "session-123", 1.25, failure, "tool diagnostics")


def snapshot(root):
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def request(root, turn):
    return root / "projects/demo/runs/conversations/main" / turn.id


def brief_proposal(root):
    turn = begin_turn(root, "demo", "Prepare the report", "local", "researcher", "brief")
    finish_turn(root, "demo", turn.id, outcome("# Proposed brief\nAn uncertain hypothesis.\n"))
    return turn


def test_read_restart_is_read_only_and_does_not_create_history(workbench):
    before = snapshot(workbench)
    assert load_discussion(workbench, "demo").turns == ()
    assert "<<<CONVERSATION>>>" in preview_context(workbench, "demo")
    assert snapshot(workbench) == before
    assert not (workbench / "projects/demo/runs/conversations").exists()
    turn = begin_turn(workbench, "demo", "Research question", "local", "researcher")
    before = snapshot(workbench)
    assert load_discussion(workbench, "demo").turns == (turn,)
    assert snapshot(workbench) == before
    assert not list((workbench / "projects/demo/runs").glob("R-*.md"))
    with pytest.raises(FormatError, match="unresolved"):
        begin_turn(workbench, "demo", "Another question", "local", "researcher")
    assert snapshot(workbench) == before


def test_multi_turn_context_exact_prompt_and_frozen_provenance(workbench):
    base = preview_context(workbench, "demo")
    first = begin_turn(workbench, "demo", "First user input", "first-local", "researcher")
    prompt = get_turn_prompt(workbench, "demo", first.id)
    assert prompt.startswith(base)
    assert "First user input" in prompt
    assert "<<<FILE AGENTS.md>>>" in prompt
    assert "<<<FILE projects/demo/PROJECT.md>>>" in prompt
    assert "<<<FILE projects/demo/brief.md>>>" in prompt
    before = (workbench / "projects/demo/brief.md").read_bytes()
    first = finish_turn(workbench, "demo", first.id, outcome("First assistant answer"))
    (workbench / "projects/demo/brief.md").write_text("# Changed by researcher\n")
    second_base = preview_context(workbench, "demo")
    second = begin_turn(workbench, "demo", "Second user input", "other-local", "researcher")
    second_prompt = get_turn_prompt(workbench, "demo", second.id)
    assert second_prompt.startswith(second_base)
    assert "First user input" in second_prompt and "First assistant answer" in second_prompt
    assert "# Changed by researcher" in second_prompt
    assert request(workbench, first).joinpath("before.md").read_bytes() == before
    assert first.run == "R-001"
    repository = Repository(workbench)
    run = repository.load("demo", ObjectId.parse(first.run))
    repository.validate_links(run, "demo")
    assert run.header["role"] == "explorer"
    assert run.header["model"] == "reported-model"
    assert run.header["session_id"] == "session-123"
    assert run.header["input_files"] == list(get_turn_files(workbench, "demo", first.id))
    assert repository.path(first.archive + "/prompt.md").read_text() == prompt
    assert all("/conversations/main/" in path for path in run.header["input_files"])
    assert [turn.id for turn in load_discussion(workbench, "demo").turns] == [first.id, second.id]


def test_failed_partial_and_empty_output_are_preserved_not_authoritative(workbench):
    first = begin_turn(workbench, "demo", "The original question", "local", "researcher")
    first = finish_turn(
        workbench, "demo", first.id, outcome("UNRELIABLE-PARTIAL", "cancelled by researcher")
    )
    assert first.status == "failed" and first.text == "UNRELIABLE-PARTIAL"
    assert first.failure == "cancelled by researcher"
    assert (workbench / first.archive / "output.md").read_text() == "UNRELIABLE-PARTIAL"
    assert (workbench / first.archive / "tool.log").read_text() == "tool diagnostics"
    context = preview_context(workbench, "demo")
    assert "The original question" in context and "cancelled by researcher" in context
    assert "UNRELIABLE-PARTIAL" not in context
    second = begin_turn(workbench, "demo", "Try another approach", "local", "researcher")
    second = finish_turn(workbench, "demo", second.id, outcome(""))
    assert second.status == "failed" and "no output" in second.failure
    assert len(list((workbench / "projects/demo/runs").glob("R-*.md"))) == 2


def test_finalize_is_idempotent_after_run_published_before_task_update(workbench, monkeypatch):
    turn = begin_turn(workbench, "demo", "Question", "local", "researcher")
    original = discussion._write

    def interrupt(repository, relative, document, replace=False):
        if relative.endswith("/task.md") and replace:
            raise OSError("injected crash after Run publication")
        original(repository, relative, document, replace)

    with monkeypatch.context() as patch:
        patch.setattr(discussion, "_write", interrupt)
        with pytest.raises(OSError, match="injected crash"):
            finish_turn(workbench, "demo", turn.id, outcome())
    before = snapshot(workbench)
    assert load_discussion(workbench, "demo").turns[0].status == "running"
    assert snapshot(workbench) == before
    recovered = recover_turn(workbench, "demo", turn.id, "researcher")
    assert recovered.status == "completed" and recovered.run == "R-001"
    assert recovered.text == "A useful answer"
    assert finish_turn(workbench, "demo", turn.id, outcome("Different replay")) == recovered
    assert len(list((workbench / "projects/demo/runs").glob("R-*.md"))) == 1


def test_explicit_orphan_recovery_creates_failed_run_without_reinvocation(workbench):
    turn = begin_turn(workbench, "demo", "Question", "local", "researcher")
    result = recover_turn(workbench, "demo", turn.id, "researcher")
    assert result.status == "failed" and "without retry" in result.failure
    assert request(workbench, turn).joinpath("recovery.md").exists()
    assert recover_turn(workbench, "demo", turn.id, "researcher") == result
    assert len(list((workbench / "projects/demo/runs").glob("R-*.md"))) == 1


def test_pending_proposal_draft_restart_and_confirmation_boundary(workbench):
    brief = workbench / "projects/demo/brief.md"
    saved = brief.read_bytes()
    charter = (workbench / "projects/demo/PROJECT.md").read_bytes()
    turn = brief_proposal(workbench)
    assert brief.read_bytes() == saved
    proposal = load_discussion(workbench, "demo").proposal
    assert proposal.id == turn.id and proposal.before.encode() == saved
    assert proposal.status == "pending"
    with pytest.raises(FormatError, match="pending brief proposal"):
        begin_turn(workbench, "demo", "Another proposal", "local", "researcher", "brief")
    save_proposal_draft(workbench, "demo", turn.id, text="# Edited proposal\n")
    assert load_discussion(workbench, "demo").proposal.text == "# Edited proposal\n"
    assert brief.read_bytes() == saved
    apply_proposal(workbench, "demo", turn.id, text="# Edited proposal\n", actor="researcher")
    assert brief.read_text() == "# Edited proposal\n"
    assert load_discussion(workbench, "demo").proposal is None
    assert (workbench / "projects/demo/PROJECT.md").read_bytes() == charter
    assert not list((workbench / "projects/demo/claims").glob("*.md"))
    application = decode(request(workbench, turn).joinpath("application.md").read_bytes())
    assert application.header["actor"] == "researcher" and application.header["run"] == "R-001"
    assert application.header["status"] == "applied"
    assert request(workbench, turn).joinpath("before.md").read_bytes() == saved
    assert request(workbench, turn).joinpath("after.md").read_text() == "# Edited proposal\n"
    before = snapshot(workbench)
    apply_proposal(workbench, "demo", turn.id, "# Edited proposal\n", "researcher")
    assert snapshot(workbench) == before
    next_turn = begin_turn(workbench, "demo", "Next question", "local", "researcher")
    assert "# Edited proposal" in get_turn_prompt(workbench, "demo", next_turn.id)


def test_external_brief_conflict_creates_no_apply_intent(workbench):
    turn = brief_proposal(workbench)
    brief = workbench / "projects/demo/brief.md"
    brief.write_text("# External edit\n")
    before = snapshot(workbench)
    with pytest.raises(FormatError, match="brief conflict"):
        apply_proposal(workbench, "demo", turn.id, "# Proposed replacement\n", "researcher")
    assert snapshot(workbench) == before
    assert brief.read_text() == "# External edit\n"
    assert load_discussion(workbench, "demo").proposal.status == "pending"


@pytest.mark.parametrize("crash_after_replace", [False, True])
def test_interrupted_application_recovers_exact_after_image(
    workbench, monkeypatch, crash_after_replace
):
    turn = brief_proposal(workbench)
    replacement = "# Approved edited brief\n"
    save_proposal_draft(workbench, "demo", turn.id, "# Earlier saved working draft\n")
    original = discussion.write_atomic

    def interrupt(path, data, *, replace=False):
        if path == workbench / "projects/demo/brief.md":
            if crash_after_replace:
                original(path, data, replace=replace)
            raise OSError("injected brief write interruption")
        original(path, data, replace=replace)

    with monkeypatch.context() as patch:
        patch.setattr(discussion, "write_atomic", interrupt)
        with pytest.raises(OSError, match="injected"):
            apply_proposal(workbench, "demo", turn.id, replacement, "researcher")
    before = snapshot(workbench)
    pending = load_discussion(workbench, "demo").proposal
    assert pending.status == "pending" and pending.applying
    assert pending.text == replacement
    assert snapshot(workbench) == before
    save_proposal_draft(workbench, "demo", turn.id, replacement)
    assert snapshot(workbench) == before
    with pytest.raises(FormatError, match="interrupted"):
        save_proposal_draft(workbench, "demo", turn.id, "# Different")
    with pytest.raises(FormatError, match="interrupted"):
        dismiss_proposal(workbench, "demo", turn.id, "researcher")
    with pytest.raises(FormatError, match="different text or actor"):
        apply_proposal(workbench, "demo", turn.id, "# Different", "researcher")
    apply_proposal(workbench, "demo", turn.id, replacement, "researcher")
    assert (workbench / "projects/demo/brief.md").read_text() == replacement
    assert load_discussion(workbench, "demo").proposal is None


def test_interrupted_application_external_change_refuses_overwrite(workbench, monkeypatch):
    turn = brief_proposal(workbench)
    original = discussion.write_atomic

    def interrupt(path, data, *, replace=False):
        if path.name == "brief.md":
            raise OSError("injected")
        original(path, data, replace=replace)

    with monkeypatch.context() as patch:
        patch.setattr(discussion, "write_atomic", interrupt)
        with pytest.raises(OSError):
            apply_proposal(workbench, "demo", turn.id, "# Approved", "researcher")
    (workbench / "projects/demo/brief.md").write_text("# Concurrent external edit")
    before = snapshot(workbench)
    with pytest.raises(FormatError, match="brief conflict"):
        apply_proposal(workbench, "demo", turn.id, "# Approved", "researcher")
    assert snapshot(workbench) == before


def test_dismiss_keeps_provenance_and_allows_new_turn(workbench):
    turn = brief_proposal(workbench)
    brief = (workbench / "projects/demo/brief.md").read_bytes()
    dismiss_proposal(workbench, "demo", turn.id, "researcher")
    before = snapshot(workbench)
    dismiss_proposal(workbench, "demo", turn.id, "researcher")
    assert snapshot(workbench) == before
    assert load_discussion(workbench, "demo").proposal is None
    assert request(workbench, turn).joinpath("proposal.md").exists()
    assert (workbench / "projects/demo/brief.md").read_bytes() == brief
    with pytest.raises(FormatError, match="no applicable"):
        apply_proposal(workbench, "demo", turn.id, "# Wrong", "researcher")
    second = begin_turn(workbench, "demo", "Continue", "local", "researcher")
    assert len(load_discussion(workbench, "demo").turns) == 2
    assert second.id > turn.id


@pytest.mark.parametrize(
    "target", ["AGENTS.md", "projects/demo/brief.md", "projects/demo/runs/conversations"]
)
def test_symlink_inputs_and_history_refused(workbench, tmp_path, target):
    path = workbench / target
    outside = tmp_path / "outside"
    outside.mkdir()
    if path.exists():
        path.unlink()
        destination = outside / "data.md"
        destination.write_text("external data")
    else:
        destination = outside
    path.symlink_to(destination)
    before = snapshot(outside)
    with pytest.raises(FormatError, match="symlinks forbidden"):
        begin_turn(workbench, "demo", "Question", "local", "researcher")
    assert snapshot(outside) == before


def test_request_paths_and_corrupt_snapshot_refused(workbench):
    with pytest.raises(FormatError, match="invalid request ID"):
        recover_turn(workbench, "demo", "../../brief.md", "researcher")
    turn = begin_turn(workbench, "demo", "Question", "local", "researcher")
    request(workbench, turn).joinpath("input-0.md").write_text("tampered snapshot")
    before = snapshot(workbench)
    with pytest.raises(FormatError, match="hash mismatch"):
        load_discussion(workbench, "demo")
    assert snapshot(workbench) == before


def test_long_context_refuses_instead_of_truncating(workbench):
    (workbench / "projects/demo/brief.md").write_text("x" * discussion.LIMIT)
    before = snapshot(workbench)
    with pytest.raises(FormatError, match="no history was truncated"):
        begin_turn(workbench, "demo", "Question", "local", "researcher")
    assert snapshot(workbench) == before


def test_unknown_auxiliary_version_is_not_repaired(workbench):
    turn = begin_turn(workbench, "demo", "Question", "local", "researcher")
    path = request(workbench, turn) / "task.md"
    document = decode(path.read_bytes())
    document.header["schema_version"] = 2
    path.write_bytes(encode(document))
    before = snapshot(workbench)
    with pytest.raises(FormatError, match="version 1"):
        load_discussion(workbench, "demo")
    assert snapshot(workbench) == before


def test_pending_proposal_does_not_interrupt_conversation(workbench):
    turn = brief_proposal(workbench)
    save_proposal_draft(workbench, "demo", turn.id, "# Working draft")
    followup = begin_turn(workbench, "demo", "Question this assumption", "local", "researcher")
    prompt = get_turn_prompt(workbench, "demo", followup.id)
    assert "BRIEF PROPOSAL [pending" in prompt
    assert f"<<<UNCONFIRMED WORKING BRIEF {turn.id}; applying=False>>>" in prompt
    assert "# Working draft" in prompt
    assert "# Proposed brief" in prompt
    assert "separate from the saved brief" in prompt
    assert (workbench / "projects/demo/brief.md").read_text() != "# Working draft"
    finish_turn(workbench, "demo", followup.id, outcome("Reconsider the premise"))
    assert load_discussion(workbench, "demo").proposal.id == turn.id
    assert load_discussion(workbench, "demo").proposal.text == "# Working draft"
    with pytest.raises(FormatError, match="pending brief proposal"):
        begin_turn(workbench, "demo", "New report", "local", "researcher", "brief")


def test_handoff_is_frozen_and_validated_from_frozen_charter(workbench):
    charter_path = workbench / "projects/demo/PROJECT.md"
    charter = decode(charter_path.read_bytes())
    charter.header["last_handoff"] = "resume.md"
    charter_path.write_bytes(encode(charter))
    session = workbench / "projects/demo/sessions/resume.md"
    session.write_text("# Resume context\nSaved next experiment.\n")
    base = preview_context(workbench, "demo")
    turn = begin_turn(workbench, "demo", "Resume the experiment", "local", "researcher")
    prompt = get_turn_prompt(workbench, "demo", turn.id)
    assert prompt.startswith(base)
    assert "<<<FILE projects/demo/sessions/resume.md>>>" in prompt
    assert "Saved next experiment." in prompt
    assert len(get_turn_files(workbench, "demo", turn.id)) == 7
    charter.header["last_handoff"] = None
    charter_path.write_bytes(encode(charter))
    session.write_text("# External handoff edit\n")
    assert get_turn_prompt(workbench, "demo", turn.id) == prompt
    finish_turn(workbench, "demo", turn.id, outcome())
    assert "Saved next experiment." in request(workbench, turn).joinpath("input-3.md").read_text()


@pytest.mark.parametrize("content", ["# Brief\n[[C-999]]", "# Brief\n[[unclosed", "# Brief\r\n"])
def test_apply_rejects_invalid_references_and_line_endings_before_writes(workbench, content):
    turn = brief_proposal(workbench)
    before = snapshot(workbench)
    with pytest.raises(FormatError):
        apply_proposal(workbench, "demo", turn.id, content, "researcher")
    assert snapshot(workbench) == before


def test_apply_uses_existing_fenced_reference_rules(workbench):
    turn = brief_proposal(workbench)
    content = "# Brief\n```\n[[C-999]]\n```\n    [[example]]\n"
    apply_proposal(workbench, "demo", turn.id, content, "researcher")
    assert (workbench / "projects/demo/brief.md").read_text() == content


@pytest.mark.parametrize("operation", ["explore", "brief"])
def test_raw_tool_output_is_byte_exact_including_crlf(workbench, operation):
    raw = "\n\n# 答案\r\nA line.\r\n\n"
    turn = begin_turn(workbench, "demo", "Question", "local", "researcher", operation)
    completed = finish_turn(workbench, "demo", turn.id, outcome(raw))
    assert completed.text == raw
    assert (workbench / turn.archive / "output.md").read_bytes() == raw.encode()
    assert load_discussion(workbench, "demo").turns[0].text == raw
    if operation == "brief":
        assert load_discussion(workbench, "demo").proposal.text == raw
        with pytest.raises(FormatError, match="LF line endings"):
            apply_proposal(workbench, "demo", turn.id, raw, "researcher")
        apply_proposal(workbench, "demo", turn.id, raw.replace("\r\n", "\n"), "researcher")


@pytest.mark.parametrize(
    "field,value", [("status", []), ("operation", {}), ("run", []), ("inputs", None)]
)
def test_corrupted_field_types_raise_domain_error_without_writes(workbench, field, value):
    turn = begin_turn(workbench, "demo", "Question", "local", "researcher")
    path = request(workbench, turn) / "task.md"
    document = decode(path.read_bytes())
    document.header[field] = value
    path.write_bytes(encode(document))
    before = snapshot(workbench)
    with pytest.raises(FormatError):
        load_discussion(workbench, "demo")
    assert snapshot(workbench) == before


def test_corrupt_prompt_is_not_used_or_repaired(workbench):
    turn = begin_turn(workbench, "demo", "Question", "local", "researcher")
    request(workbench, turn).joinpath("prompt.md").write_text("different prompt")
    before = snapshot(workbench)
    with pytest.raises(FormatError, match="frozen request hash mismatch"):
        get_turn_prompt(workbench, "demo", turn.id)
    assert snapshot(workbench) == before


def test_proposal_cannot_be_rebound_to_another_run(workbench):
    first = begin_turn(workbench, "demo", "Explore", "local", "researcher")
    finish_turn(workbench, "demo", first.id, outcome())
    turn = brief_proposal(workbench)
    path = request(workbench, turn) / "proposal.md"
    document = decode(path.read_bytes())
    document.header["run"] = "R-001"
    path.write_bytes(encode(document))
    before = snapshot(workbench)
    with pytest.raises(FormatError, match="must match"):
        apply_proposal(workbench, "demo", turn.id, "# Rebound", "researcher")
    assert snapshot(workbench) == before


def test_apply_final_metadata_interruption_resumes_confirmed_image(workbench, monkeypatch):
    turn = brief_proposal(workbench)
    save_proposal_draft(workbench, "demo", turn.id, "# Earlier working draft")
    confirmed = "# Confirmed after image\n"
    original = discussion._write

    def interrupt(repository, relative, document, replace=False):
        if relative.endswith("/proposal.md") and replace:
            raise OSError("injected proposal metadata interruption")
        original(repository, relative, document, replace)

    with monkeypatch.context() as patch:
        patch.setattr(discussion, "_write", interrupt)
        with pytest.raises(OSError, match="metadata interruption"):
            apply_proposal(workbench, "demo", turn.id, confirmed, "researcher")
    pending = load_discussion(workbench, "demo").proposal
    assert pending.applying and pending.text == confirmed
    assert (workbench / "projects/demo/brief.md").read_text() == confirmed
    before = snapshot(workbench)
    save_proposal_draft(workbench, "demo", turn.id, confirmed)
    assert snapshot(workbench) == before
    apply_proposal(workbench, "demo", turn.id, confirmed, "researcher")
    assert load_discussion(workbench, "demo").proposal is None


def test_external_edit_during_apply_intent_is_not_overwritten(workbench, monkeypatch):
    turn = brief_proposal(workbench)
    original = discussion._write
    brief = workbench / "projects/demo/brief.md"
    external = "# External edit while intent was prepared\n"

    def edit_during_intent(repository, relative, document, replace=False):
        original(repository, relative, document, replace)
        if relative.endswith("/application.md") and not replace:
            brief.write_text(external)

    monkeypatch.setattr(discussion, "_write", edit_during_intent)
    with pytest.raises(FormatError, match="brief conflict"):
        apply_proposal(workbench, "demo", turn.id, "# Confirmed replacement\n", "researcher")
    assert brief.read_text() == external
    pending = load_discussion(workbench, "demo").proposal
    assert pending.applying and pending.text == "# Confirmed replacement\n"
    assert request(workbench, turn).joinpath("after.md").read_text() == pending.text
