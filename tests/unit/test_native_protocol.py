"""Native context/draft provenance, explicit application and interrupted replay."""

import os

import pytest

from toulmin.core.codec import decode, encode
from toulmin.core.documents import FormatError
from toulmin.core.identifiers import ObjectId
from toulmin.core.repository import Repository
from toulmin.protocols import native
from toulmin.protocols.native import (
    apply_native,
    begin_native,
    finalize_native,
    list_native,
    load_native,
)

DRAFT = "# Proposed Brief\n\nAn uncertain research direction.\n"


def snapshot(root):
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def begin(root):
    return begin_native(root, "demo", "arbitrary-native-tool", "researcher")


def closed(root, draft=DRAFT, **kwargs):
    session = begin(root)
    if draft is not None:
        (session.workspace / "draft.md").write_bytes(draft.encode())
    return finalize_native(root, "demo", session.id, exit_code=0, **kwargs)


def run(root, session):
    repository = Repository(root)
    document = repository.load("demo", ObjectId.parse(session.run))
    repository.validate_links(document, "demo")
    return document


def test_open_and_list_do_not_write_or_start_anything(workbench):
    before = snapshot(workbench)
    assert list_native(workbench, "demo") == ()
    assert snapshot(workbench) == before
    session = begin(workbench)
    before = snapshot(workbench)
    assert load_native(workbench, "demo", session.id) == session
    assert list_native(workbench, "demo") == (session,)
    assert snapshot(workbench) == before
    assert session.status == "started"
    assert session.output_status == "running"
    assert session.draft is None and session.run is None
    assert not list((workbench / "projects/demo/runs").glob("R-*.md"))
    with pytest.raises(FormatError, match="unresolved"):
        begin(workbench)


@pytest.mark.parametrize("finalized", [False, True])
def test_moved_workbench_preserves_context_reopens_and_applies(workbench, finalized):
    session = begin(workbench)
    (session.workspace / "draft.md").write_text(DRAFT)
    context = (session.directory / "context.md").read_bytes()
    assert str(workbench) not in session.context
    assert "Research workspace: the current working directory" in session.context
    if finalized:
        session = finalize_native(workbench, "demo", session.id, 0)
    moved = workbench.with_name("moved-workbench")
    workbench.rename(moved)
    reopened = load_native(moved, "demo", session.id)
    assert reopened.context.encode() == context
    assert reopened.root == moved
    assert reopened.workspace == moved / session.workspace.relative_to(workbench)
    assert reopened.directory.joinpath("context.md").read_bytes() == context
    if not finalized:
        reopened = finalize_native(moved, "demo", session.id, 0)
    assert reopened.archive.joinpath("context.md").read_bytes() == context
    applied = apply_native(moved, "demo", session.id, DRAFT, "researcher")
    assert applied.application_status == "applied" and applied.brief == DRAFT
    assert applied.directory.joinpath("context.md").read_bytes() == context
    assert len(list((moved / "projects/demo/runs").glob("R-*.md"))) == 1
    assert list_native(moved, "demo") == (applied,)


def test_inputs_context_and_baseline_are_frozen_but_research_copy_is_mutable(workbench):
    charter_path = workbench / "projects/demo/PROJECT.md"
    charter = decode(charter_path.read_bytes())
    charter.header["last_handoff"] = "previous.md"
    charter_path.write_bytes(encode(charter))
    handoff = workbench / "projects/demo/sessions/previous.md"
    handoff.write_bytes(b"# Previous handoff\nA known uncertainty.\n")
    session = begin(workbench)
    assert (session.workspace / "context.md").read_text() == session.context
    assert "# Previous handoff" in session.context
    assert "draft.md" in session.context
    assert "native conversation and provider cache are not captured" in session.context
    assert "Do not write the saved Brief" in session.context
    (workbench / "AGENTS.md").write_text("Changed instructions.\n")
    (workbench / "projects/demo/brief.md").write_text("Changed saved Brief.\n")
    handoff.write_text("Changed handoff.\n")
    (session.workspace / "context.md").write_text("Mutable research scratch.\n")
    reopened = load_native(workbench, "demo", session.id)
    assert reopened.context == session.context
    assert reopened.before == session.before
    assert reopened.brief == "Changed saved Brief.\n"
    task = decode((session.directory / "session.md").read_bytes())
    assert [entry["source"] for entry in task.header["inputs"]] == [
        "AGENTS.md",
        "projects/demo/PROJECT.md",
        "projects/demo/brief.md",
        "projects/demo/sessions/previous.md",
    ]


def test_live_preview_cannot_apply_until_native_exit(workbench):
    session = begin(workbench)
    path = session.workspace / "draft.md"
    path.write_text(DRAFT)
    assert load_native(workbench, "demo", session.id).draft == DRAFT
    before = snapshot(workbench)
    with pytest.raises(FormatError, match="only a closed"):
        apply_native(workbench, "demo", session.id, DRAFT, "researcher")
    assert snapshot(workbench) == before


def test_finalization_preserves_raw_draft_diagnostics_and_honest_run(workbench):
    raw = "# Draft\r\nUncertainty retained.\r\n"
    diagnostic = b"\x1b[31mpartial terminal output\x1b[0m\xff\r\n"
    session = closed(workbench, raw, diagnostic=diagnostic)
    assert session.status == "closed" and session.output_status == "completed"
    assert session.proposal_status == "invalid"
    assert session.model is None and session.session_id is None
    assert (session.archive / "draft.md").read_bytes() == raw.encode()
    assert (session.directory / "frozen-draft.md").read_bytes() == raw.encode()
    assert (session.archive / "terminal-diagnostic.log").read_bytes() == diagnostic
    document = run(workbench, session)
    assert document.header["model"] == "arbitrary-native-tool native (model not reported)"
    assert document.header["session_id"] is None
    assert document.header["duration_seconds"] is None
    assert "native conversation/transcript was not captured" in document.body
    assert "not a complete transcript" in document.body
    assert document.header["input_files"][-1].endswith("/context.md")
    (session.workspace / "draft.md").write_text("Modified after native exit.\n")
    assert load_native(workbench, "demo", session.id).draft == raw
    assert finalize_native(workbench, "demo", session.id, exit_code=9).run == session.run
    assert len(list((workbench / "projects/demo/runs").glob("R-*.md"))) == 1


def test_explicit_reported_metadata_is_provenance_data(workbench):
    session = closed(workbench, model="model-from-operator", native_session_id="session-reported")
    document = run(workbench, session)
    assert document.header["model"] == "model-from-operator"
    assert document.header["session_id"] == "session-reported"


@pytest.mark.parametrize("draft", [None, "", "\n \n"])
def test_success_without_nonempty_draft_is_a_completed_session_not_invented_output(
    workbench, draft
):
    session = closed(workbench, draft)
    assert session.output_status == "completed" and session.proposal_status == "none"
    assert session.draft == draft
    assert "No nonempty Brief draft was returned" in run(workbench, session).body
    assert (session.archive / "draft.md").exists() == (draft is not None)


@pytest.mark.parametrize("exit_code,interrupted", [(7, False), (0, True), (None, False)])
def test_unsuccessful_session_retains_partial_draft_without_applicable_proposal(
    workbench, exit_code, interrupted
):
    session = begin(workbench)
    (session.workspace / "draft.md").write_text(DRAFT)
    session = finalize_native(workbench, "demo", session.id, exit_code, interrupted)
    assert session.output_status == "failed" and session.failure
    assert session.draft == DRAFT and session.proposal_status == "none"
    assert run(workbench, session).header["status"] == "failed"
    with pytest.raises(FormatError, match="successful"):
        apply_native(workbench, "demo", session.id, DRAFT, "researcher")


def test_explicit_application_preserves_before_after_and_exact_confirmation(workbench):
    session = closed(workbench)
    before = snapshot(workbench)
    with pytest.raises(FormatError, match="displayed draft changed"):
        apply_native(workbench, "demo", session.id, DRAFT + "New edit", "researcher")
    assert snapshot(workbench) == before
    applied = apply_native(workbench, "demo", session.id, DRAFT, "researcher")
    assert applied.proposal_status == "applied" and applied.application_status == "applied"
    assert (workbench / "projects/demo/brief.md").read_text() == DRAFT
    assert (session.directory / "before.md").read_text() == session.before
    assert (session.directory / "after.md").read_text() == DRAFT
    intent = decode((session.directory / "application.md").read_bytes())
    assert intent.header["actor"] == "researcher" and intent.header["run"] == session.run
    before = snapshot(workbench)
    assert apply_native(workbench, "demo", session.id, DRAFT, "researcher") == applied
    assert snapshot(workbench) == before
    (workbench / "projects/demo/brief.md").write_text("A later researcher edit.\n")
    apply_native(workbench, "demo", session.id, DRAFT, "researcher")
    assert (workbench / "projects/demo/brief.md").read_text() == "A later researcher edit.\n"


def test_stale_brief_and_invalid_references_refuse_without_mutation(workbench):
    session = closed(workbench, "# Draft\nMissing [[C-999]].\n")
    assert session.proposal_status == "invalid"
    before = snapshot(workbench)
    with pytest.raises(FormatError, match="C-999"):
        apply_native(workbench, "demo", session.id, session.draft, "researcher")
    assert snapshot(workbench) == before
    other = closed(workbench)
    assert other.id != session.id  # Closed pending proposals permit a new branch.
    brief = workbench / "projects/demo/brief.md"
    brief.write_text("External edit.\n")
    before = snapshot(workbench)
    with pytest.raises(FormatError, match="saved Brief changed"):
        apply_native(workbench, "demo", other.id, DRAFT, "researcher")
    assert snapshot(workbench) == before


def test_finalize_recovery_reuses_durable_output_and_existing_run(workbench, monkeypatch):
    session = begin(workbench)
    (session.workspace / "draft.md").write_text(DRAFT)
    original = native._write

    def crash(repository, relative, doc, replace=False):
        if relative.endswith("/session.md") and replace:
            raise OSError("simulated death after Run publication")
        return original(repository, relative, doc, replace)

    with monkeypatch.context() as patch:
        patch.setattr(native, "_write", crash)
        with pytest.raises(OSError, match="simulated death"):
            finalize_native(workbench, "demo", session.id, 0)
    assert len(list((workbench / "projects/demo/runs").glob("R-*.md"))) == 1
    (session.workspace / "draft.md").write_text("Changed since crash.\n")
    preview = load_native(workbench, "demo", session.id)
    assert preview.status == "started" and preview.draft == DRAFT and preview.run is None
    recovered = finalize_native(workbench, "demo", session.id, 99, True)
    assert recovered.draft == DRAFT and recovered.output_status == "completed"
    assert recovered.run == "R-001"
    assert len(list((workbench / "projects/demo/runs").glob("R-*.md"))) == 1


@pytest.mark.parametrize("crash_point", ["brief", "application"])
def test_application_recovery_resumes_exact_intent(workbench, monkeypatch, crash_point):
    session = closed(workbench)
    original_write = native._write
    original_atomic = native.write_atomic

    def crash_write(repository, relative, doc, replace=False):
        if crash_point == "application" and relative.endswith("/application.md") and replace:
            raise OSError("application interrupted")
        return original_write(repository, relative, doc, replace)

    def crash_atomic(path, data, *, replace=False):
        if crash_point == "brief" and path == workbench / "projects/demo/brief.md":
            raise OSError("brief interrupted")
        return original_atomic(path, data, replace=replace)

    with monkeypatch.context() as patch:
        patch.setattr(native, "_write", crash_write)
        patch.setattr(native, "write_atomic", crash_atomic)
        with pytest.raises(OSError, match="interrupted"):
            apply_native(workbench, "demo", session.id, DRAFT, "researcher")
    preview = load_native(workbench, "demo", session.id)
    assert preview.application_status == "applying"
    with pytest.raises(FormatError, match="different actor"):
        apply_native(workbench, "demo", session.id, DRAFT, "someone-else")
    applied = apply_native(workbench, "demo", session.id, DRAFT, "researcher")
    assert applied.application_status == "applied" and applied.brief == DRAFT


def test_external_edit_during_apply_is_never_overwritten(workbench, monkeypatch):
    session = closed(workbench)
    original = native._ensure

    def external_edit(repository, relative, data):
        original(repository, relative, data)
        if relative.endswith("/after.md"):
            (workbench / "projects/demo/brief.md").write_text("Concurrent external edit.\n")

    with monkeypatch.context() as patch:
        patch.setattr(native, "_ensure", external_edit)
        with pytest.raises(FormatError, match="neither saved before"):
            apply_native(workbench, "demo", session.id, DRAFT, "researcher")
    assert (workbench / "projects/demo/brief.md").read_text() == "Concurrent external edit.\n"
    assert load_native(workbench, "demo", session.id).application_status == "applying"


@pytest.mark.parametrize("session_id", ["../escape", "/tmp/escape", "", "session", "x\\y"])
def test_invalid_session_ids_refuse_without_writes(workbench, session_id):
    before = snapshot(workbench)
    with pytest.raises(FormatError):
        load_native(workbench, "demo", session_id)
    assert snapshot(workbench) == before


@pytest.mark.parametrize("kind", ["symlink", "fifo", "directory", "invalid-utf8", "oversize"])
def test_native_draft_reads_reject_unsafe_or_invalid_files_without_archiving(workbench, kind):
    session = begin(workbench)
    path = session.workspace / "draft.md"
    if kind == "symlink":
        path.symlink_to(workbench / "projects/demo/brief.md")
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind == "directory":
        path.mkdir()
    elif kind == "invalid-utf8":
        path.write_bytes(b"\xff")
    else:
        path.write_bytes(b"x" * (native.MAX_FILE_BYTES + 1))
    with pytest.raises(FormatError):
        finalize_native(workbench, "demo", session.id, 0)
    assert not (session.directory / "close.md").exists()
    assert not session.archive.exists()


@pytest.mark.parametrize("target", ["input-0.md", "before.md", "context.md"])
def test_frozen_context_tampering_is_a_data_error(workbench, target):
    session = begin(workbench)
    (session.directory / target).write_text("Changed frozen source.\n")
    with pytest.raises(FormatError, match="hash mismatch|differs"):
        load_native(workbench, "demo", session.id)


def test_archived_draft_and_diagnostic_tampering_refuse_apply(workbench):
    session = closed(workbench, diagnostic=b"partial diagnostic")
    (session.archive / "terminal-diagnostic.log").write_bytes(b"Changed")
    with pytest.raises(FormatError, match="diagnostic differs"):
        apply_native(workbench, "demo", session.id, DRAFT, "researcher")
    assert (workbench / "projects/demo/brief.md").read_text() == session.before
