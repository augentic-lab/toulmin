import subprocess
import sys

import pytest
from typer.testing import CliRunner

from toulmin.cli.app import app
from toulmin.core import handoff_transaction as transaction
from toulmin.core.atomic import digest, handoff_mutex
from toulmin.core.codec import decode, encode
from toulmin.core.documents import Document
from toulmin.core.handoffs import validate_handoff
from toulmin.protocols.status import project_status


def invoke(root, *arguments):
    return CliRunner().invoke(app, ["handoff", "demo", "--root", str(root), *arguments])


def summary(root, next_step="Respond to O-001", **fields):
    path = root / "projects/demo/runs/manual/summary.md"
    path.parent.mkdir(exist_ok=True)
    header = {
        "session_id": "fixture-session",
        "recent_decisions": ["D-001"],
        "next_step": next_step,
    }
    header.update(fields)
    path.write_bytes(
        encode(
            Document(
                header,
                "## Done\nRead C-001 and archived its review.\n\n"
                "## Decisions\nD-001 retained; further ruling is pending.\n\n"
                "## Open questions\nO-001 remains open.\n",
            )
        )
    )
    return str(path.relative_to(root))


def create(root, input_path=None):
    result = invoke(root, *(["--input", input_path] if input_path else []))
    assert result.exit_code == 0, result.output
    return result.stdout.strip()


def apply(root, draft, confirm=True):
    return invoke(
        root,
        "--apply",
        draft,
        "--confirmed-by",
        "Fixture Researcher",
        *(["--confirm"] if confirm else []),
    )


def files(root):
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def test_default_draft_has_explicit_unknowns_and_only_writes_runs(populated):
    before = files(populated)
    path = create(populated)
    document = decode((populated / path).read_bytes())
    validate_handoff(document, "demo")
    assert "/runs/" in path and path.endswith("/draft.md")
    assert document.header["session_id"] is None
    assert document.header["recent_decisions"] == []
    assert document.body.count("Unknown:") == 3
    assert document.header["base_project_sha256"] == digest(
        (populated / "projects/demo/PROJECT.md").read_bytes()
    )
    after = files(populated)
    assert all(after[key] == value for key, value in before.items())
    assert set(after) - set(before) == {path}


def test_input_summary_and_confirmed_apply_preserve_body_comments_and_stage(populated):
    charter = populated / "projects/demo/PROJECT.md"
    charter.write_text(
        charter.read_text()
        .replace("schema_version: 1", "# Researcher comment\nschema_version: 1")
        .replace("stage: explore", "stage: critique # researcher-owned gate")
        .replace("## Goal\n", "## Goal\n手写目标，不得改写。\n")
    )
    original = decode(charter.read_bytes())
    draft = create(populated, summary(populated))
    draft_bytes = (populated / draft).read_bytes()
    result = apply(populated, draft)
    assert result.exit_code == 0, result.output
    current = decode(charter.read_bytes())
    assert current.body == original.body
    assert current.header["stage"] == "critique"
    assert current.header["next_step"] == "Respond to O-001"
    assert current.header["recent_decisions"] == ["D-001"]
    assert "# Researcher comment" in charter.read_text()
    assert "# researcher-owned gate" in charter.read_text()
    record = populated / "projects/demo/sessions" / current.header["last_handoff"]
    session = decode(record.read_bytes())
    validate_handoff(session, "demo", applied=True)
    assert session.header["source_sha256"] == digest(draft_bytes)
    assert session.header["applied_by"] == "Fixture Researcher"
    assert session.header["session_id"] == "fixture-session"
    assert (populated / draft).read_bytes() == draft_bytes
    assert not project_status(populated, "demo").errors
    assert not (populated / "projects/demo/.handoff-pending").exists()


def test_unconfirmed_apply_leaves_every_file_unchanged(populated):
    draft = create(populated)
    before = files(populated)
    result = apply(populated, draft, confirm=False)
    assert result.exit_code == 1
    assert "explicit researcher confirmation" in result.stderr
    assert files(populated) == before


def test_project_changed_since_draft_refuses_overwrite(populated):
    draft = create(populated)
    charter = populated / "projects/demo/PROJECT.md"
    charter.write_text(charter.read_text().replace("## Goal\n", "## Goal\nNew handwritten goal.\n"))
    before = files(populated)
    result = apply(populated, draft)
    assert result.exit_code == 1
    assert "PROJECT changed since drafting" in result.stderr
    assert files(populated) == before


def test_repeat_apply_is_noop_even_after_a_newer_handoff(populated):
    first = create(populated, summary(populated))
    assert apply(populated, first).exit_code == 0
    second = create(populated, summary(populated, next_step="Next session's work"))
    assert apply(populated, second).exit_code == 0
    before = files(populated)
    assert apply(populated, first).exit_code == 0
    assert apply(populated, second).exit_code == 0
    assert files(populated) == before
    assert len(list((populated / "projects/demo/sessions").glob("*.md"))) == 2


@pytest.mark.parametrize(
    "fields",
    [
        {"recent_decisions": ["C-001"]},
        {"recent_decisions": ["D-999"]},
        {"stage": "build"},
        {"schema_version": 2},
        {"session_id": ""},
        {"next_step": ""},
    ],
)
def test_invalid_input_does_not_create_draft(populated, fields):
    source = summary(populated)
    path = populated / source
    document = decode(path.read_bytes())
    document.header.update(fields)
    path.write_bytes(encode(document))
    before = files(populated)
    result = invoke(populated, "--input", source)
    assert result.exit_code == 1
    assert files(populated) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("project", "other"),
        ("base_project_sha256", "invalid"),
        ("schema_version", 2),
        ("stage", "build"),
    ],
)
def test_invalid_archived_draft_cannot_change_state(populated, field, value):
    draft = create(populated)
    path = populated / draft
    document = decode(path.read_bytes())
    document.header[field] = value
    path.write_bytes(encode(document))
    before = files(populated)
    result = apply(populated, draft)
    assert result.exit_code == 1
    assert field in result.stderr
    assert files(populated) == before


@pytest.mark.parametrize(
    "arguments",
    [
        ["--confirm"],
        ["--confirmed-by", "X"],
        ["--apply", "draft.md"],
        ["--apply", "draft.md", "--input", "input.md", "--confirmed-by", "X"],
    ],
)
def test_mutually_exclusive_modes_and_missing_arguments_are_usage_errors(populated, arguments):
    assert invoke(populated, *arguments).exit_code == 2


def test_input_and_apply_paths_are_confined(populated, tmp_path):
    draft = create(populated)
    alias = populated / "projects/demo/runs/alias.md"
    alias.symlink_to(populated / draft)
    before = files(populated)
    for path in ("../outside.md", str(populated / draft), "projects/demo/runs/alias.md"):
        assert apply(populated, path).exit_code == 1
    outside_runs = populated / "draft.md"
    outside_runs.write_bytes((populated / draft).read_bytes())
    assert apply(populated, "draft.md").exit_code == 1
    assert all(files(populated)[key] == value for key, value in before.items())


@pytest.mark.parametrize("checkpoint", ["session", "project"])
def test_process_death_releases_mutex_and_retry_recovers_once(populated, checkpoint):
    draft = create(populated, summary(populated))
    script = """
import os, sys
from pathlib import Path
from toulmin.core import handoff_transaction as tx
from toulmin.protocols.handoff import apply_handoff
original = tx.write_atomic
def interrupted(path, data, **kwargs):
    original(path, data, **kwargs)
    session = sys.argv[3] == 'session' and path.parent.name == 'sessions'
    project = sys.argv[3] == 'project' and path.name == 'PROJECT.md'
    if session or project:
        os._exit(73)
tx.write_atomic = interrupted
apply_handoff(Path(sys.argv[1]), 'demo', sys.argv[2], 'Fixture Researcher', True)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(populated), draft, checkpoint],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 73, result.stderr
    assert (populated / "projects/demo/.handoff-pending/intent.md").is_file()
    assert project_status(populated, "demo").errors
    recovered = apply(populated, draft)
    assert recovered.exit_code == 0, recovered.output
    assert not (populated / "projects/demo/.handoff-pending").exists()
    assert not project_status(populated, "demo").errors
    assert len(list((populated / "projects/demo/sessions").glob("*.md"))) == 1
    before = files(populated)
    assert apply(populated, draft).exit_code == 0
    assert files(populated) == before


def interrupted_project_write(root, draft, monkeypatch):
    original = transaction.write_atomic

    def fail(path, data, **kwargs):
        if path.name == "PROJECT.md":
            raise OSError("injected PROJECT write failure")
        return original(path, data, **kwargs)

    monkeypatch.setattr(transaction, "write_atomic", fail)
    result = apply(root, draft)
    assert result.exit_code == 1 and "injected PROJECT" in result.stderr
    monkeypatch.setattr(transaction, "write_atomic", original)


def test_io_failure_retains_original_and_complete_recovery_images(populated, monkeypatch):
    draft = create(populated, summary(populated))
    charter = populated / "projects/demo/PROJECT.md"
    original = charter.read_bytes()
    interrupted_project_write(populated, draft, monkeypatch)
    pending = populated / "projects/demo/.handoff-pending"
    assert charter.read_bytes() == original
    assert (pending / "before.md").read_bytes() == original
    assert (pending / "draft.md").read_bytes() == (populated / draft).read_bytes()
    assert apply(populated, draft).exit_code == 0


def test_external_edit_after_failure_is_preserved_and_recovery_is_refused(populated, monkeypatch):
    draft = create(populated)
    interrupted_project_write(populated, draft, monkeypatch)
    charter = populated / "projects/demo/PROJECT.md"
    charter.write_text(charter.read_text() + "Researcher's new notes.\n")
    edited = charter.read_bytes()
    result = apply(populated, draft)
    assert result.exit_code == 1 and "refusing recovery overwrite" in result.stderr
    assert charter.read_bytes() == edited
    assert (populated / "projects/demo/.handoff-pending").exists()


def test_corrupt_journal_and_different_draft_do_not_silently_recover(populated, monkeypatch):
    first = create(populated)
    second = create(populated)
    interrupted_project_write(populated, first, monkeypatch)
    assert "another draft" in apply(populated, second).stderr
    pending = populated / "projects/demo/.handoff-pending"
    (pending / "after.md").write_text("corrupt image")
    result = apply(populated, first)
    assert result.exit_code == 1 and "checksum mismatch" in result.stderr
    assert pending.exists()


def test_existing_session_conflict_is_never_overwritten(populated, monkeypatch):
    draft = create(populated)
    interrupted_project_write(populated, draft, monkeypatch)
    session = next((populated / "projects/demo/sessions").glob("*.md"))
    session.write_text("Researcher's conflicting file\n")
    assert apply(populated, draft).exit_code == 1
    assert session.read_text() == "Researcher's conflicting file\n"


def test_orphan_session_without_journal_is_not_reported_as_applied(populated, monkeypatch):
    import shutil

    draft = create(populated)
    interrupted_project_write(populated, draft, monkeypatch)
    shutil.rmtree(populated / "projects/demo/.handoff-pending")
    before = files(populated)
    result = apply(populated, draft)
    assert result.exit_code == 1 and "not linked from PROJECT" in result.stderr
    assert files(populated) == before


def test_existing_decision_sequence_is_preserved_including_duplicates(populated):
    charter = populated / "projects/demo/PROJECT.md"
    document = decode(charter.read_bytes())
    document.header["recent_decisions"] = ["D-001", "D-001"]
    charter.write_bytes(encode(document))
    draft = create(populated, summary(populated))
    assert apply(populated, draft).exit_code == 0
    assert decode(charter.read_bytes()).header["recent_decisions"] == ["D-001", "D-001"]


def test_mutated_source_is_detected_by_status_and_replay(populated):
    draft = create(populated)
    assert apply(populated, draft).exit_code == 0
    path = populated / draft
    path.write_text(path.read_text() + "Changed after confirmation.\n")
    assert project_status(populated, "demo").errors
    assert apply(populated, draft).exit_code == 1


def test_an_active_handoff_mutex_refuses_second_writer(populated):
    draft = create(populated)
    with handoff_mutex(populated / "projects/demo"):
        result = apply(populated, draft)
        assert result.exit_code == 1 and "another handoff writer" in result.stderr


def test_existing_object_writer_lock_is_not_removed(populated):
    draft = create(populated)
    lock = populated / "projects/demo/.toulmin-new.lock"
    lock.mkdir()
    result = apply(populated, draft)
    assert result.exit_code == 1 and "object writer" in result.stderr
    assert lock.is_dir()


def test_failure_while_preparing_leaves_public_files_unchanged(populated, monkeypatch):
    draft = create(populated)
    before = files(populated)
    original = transaction.write_atomic

    def fail(path, data, **kwargs):
        if path.name == "after.md":
            raise OSError("cannot stage after image")
        return original(path, data, **kwargs)

    monkeypatch.setattr(transaction, "write_atomic", fail)
    result = apply(populated, draft)
    assert result.exit_code == 1 and "cannot stage" in result.stderr
    assert files(populated) == before
    assert not (populated / "projects/demo/.handoff-pending").exists()


def test_recovery_rejects_stage_changes_even_with_updated_journal_checksums(populated, monkeypatch):
    draft = create(populated)
    interrupted_project_write(populated, draft, monkeypatch)
    pending = populated / "projects/demo/.handoff-pending"
    after = decode((pending / "after.md").read_bytes())
    after.header["stage"] = "build"
    after_bytes = encode(after)
    (pending / "after.md").write_bytes(after_bytes)
    session = decode((pending / "session.md").read_bytes())
    session.header["project_sha256"] = digest(after_bytes)
    session_bytes = encode(session)
    (pending / "session.md").write_bytes(session_bytes)
    intent = decode((pending / "intent.md").read_bytes())
    intent.header.update(after_sha256=digest(after_bytes), session_sha256=digest(session_bytes))
    (pending / "intent.md").write_bytes(encode(intent))
    original = (populated / "projects/demo/PROJECT.md").read_bytes()
    result = apply(populated, draft)
    assert result.exit_code == 1 and "researcher-owned content or stage" in result.stderr
    assert (populated / "projects/demo/PROJECT.md").read_bytes() == original
