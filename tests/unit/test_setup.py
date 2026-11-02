"""File-backed setup, conflict handling and explicit recovery without model calls."""

from pathlib import Path

import pytest

from toulmin.application import workspace
from toulmin.application.workspace import WorkspaceService
from toulmin.cli.initialize import initialize
from toulmin.core.atomic import handoff_mutex
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError, sections
from toulmin.core.project import validate_project


def files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def test_create_reopen_preserves_input_and_existing_research_files(tmp_path):
    root = tmp_path / "workbench"
    service = WorkspaceService()
    view = service.create_project(root, "demo", "Measure queueing", "Latency harms workloads.")
    assert (view.goal, view.motivation, view.stage) == (
        "Measure queueing",
        "Latency harms workloads.",
        "explore",
    )
    assert not view.diagnostics
    assert not view.setup_pending
    assert view.last_handoff is None
    assert view.next_step
    assert not view.open_objections
    validate_project(decode((root / "projects/demo/PROJECT.md").read_bytes()), "demo")
    before = files(root)
    assert service.open_project(root, "demo") == view
    assert service.list_projects(root) == ["demo"]
    assert files(root) == before


def test_import_retains_exact_external_source_and_supports_markdown_headings(tmp_path):
    source = tmp_path / "idea.MD"
    data = "# Idea\r\n## Problem\r\n研究动机\r\n## Why now\r\nNew hardware.\r\n".encode()
    source.write_bytes(data)
    motivation = data.decode().replace("\r\n", "\n").strip()
    root = tmp_path / "workbench"
    service = WorkspaceService()
    created = service.create_project(root, "demo", "Test the idea", motivation, source)
    assert not created.diagnostics
    assert created.motivation == motivation
    brief_sections = sections(workspace.Document({}, created.brief))
    assert "Problem" in brief_sections and "Why now" in brief_sections
    assert source.read_bytes() == data
    assert (root / "projects/demo/runs/setup/source.md").read_bytes() == data
    source.unlink()
    assert service.open_project(root, "demo").motivation == motivation


@pytest.mark.parametrize(
    "goal,motivation",
    [
        ("", "Motivation"),
        ("Goal", ""),
        ("Goal\n## Constraints\nOops", "Why"),
        ("\n".join(["goal"] * 40), "Why"),
        ("Goal", "bad\rtext"),
        ("Goal", "bad\x00text"),
    ],
)
def test_bad_values_refused_before_mutation(tmp_path, goal, motivation):
    root = tmp_path / "new"
    with pytest.raises(ValueError):
        WorkspaceService().create_project(root, "demo", goal, motivation)
    assert not root.exists()


@pytest.mark.parametrize("suffix,data", [(".pdf", b"unsupported"), (".txt", b"\xff")])
def test_bad_import_refused_before_mutation(tmp_path, suffix, data):
    source = tmp_path / ("source" + suffix)
    source.write_bytes(data)
    root = tmp_path / "new"
    with pytest.raises(ValueError):
        WorkspaceService().create_project(root, "demo", "Goal", "Why", source)
    assert not root.exists()
    assert source.read_bytes() == data


def test_create_refuses_existing_project_without_touching_it(tmp_path):
    root = tmp_path / "workbench"
    service = WorkspaceService()
    service.create_project(root, "demo", "Goal", "Why")
    before = files(root)
    with pytest.raises(FileExistsError):
        service.create_project(root, "demo", "New goal", "New why")
    assert files(root) == before


def test_open_existing_edited_templates_never_calls_initialize(tmp_path, monkeypatch):
    root = tmp_path / "workbench"
    initialize(root, "demo")
    (root / "AGENTS.md").write_text("Edited by researcher\n")
    (root / "roles/reviewer.md").write_text("Custom reviewer\n")
    (root / "projects/demo/brief.md").write_text("## Problem\n\nCurrent motivation\n")
    before = files(root)

    def forbidden(*args):
        raise AssertionError("Opening must never initialize")

    monkeypatch.setattr(workspace, "initialize", forbidden)
    view = WorkspaceService().open_project(root, "demo")
    assert view.motivation == "Current motivation"
    assert not view.diagnostics
    assert not view.setup_pending
    assert files(root) == before


def test_completed_setup_does_not_hide_later_brief_edits(tmp_path):
    root = tmp_path / "workbench"
    service = WorkspaceService()
    service.create_project(root, "demo", "Goal", "Original motivation")
    (root / "projects/demo/brief.md").write_text("## Problem\n\nRevised motivation\n")
    view = service.open_project(root, "demo")
    assert view.motivation == "Revised motivation"
    assert not view.diagnostics


def interrupt_brief(root, monkeypatch):
    original = workspace.write_atomic

    def fail(path, data, *, replace=False):
        if path == root / "projects/demo/brief.md":
            raise OSError("interrupted publication")
        original(path, data, replace=replace)

    monkeypatch.setattr(workspace, "write_atomic", fail)
    with pytest.raises(OSError, match="interrupted publication"):
        WorkspaceService().create_project(root, "demo", "Goal", "Why")
    monkeypatch.setattr(workspace, "write_atomic", original)


def test_interrupted_setup_reopens_pending_and_resumes_without_init(tmp_path, monkeypatch):
    root = tmp_path / "workbench"
    interrupt_brief(root, monkeypatch)
    service = WorkspaceService()
    pending = service.open_project(root, "demo")
    assert pending.setup_pending
    assert pending.goal == "Goal" and pending.motivation == "Why"
    assert any("Resume Setup" in message for message in pending.diagnostics)

    def forbidden(*args):
        raise AssertionError("Recovering publication must not reinitialize")

    monkeypatch.setattr(workspace, "initialize", forbidden)
    view = service.resume_setup(root, "demo")
    assert not view.setup_pending
    assert not view.diagnostics
    assert view.motivation == "Why"
    before = files(root)
    assert service.resume_setup(root, "demo") == view
    assert files(root) == before


def test_intent_survives_initialization_failure_and_can_resume(tmp_path, monkeypatch):
    root = tmp_path / "workbench"
    original = workspace.initialize

    def fail(*args):
        raise OSError("init interrupted")

    monkeypatch.setattr(workspace, "initialize", fail)
    with pytest.raises(OSError, match="init interrupted"):
        WorkspaceService().create_project(root, "demo", "Goal", "Why")
    assert (root / "projects/demo/runs/setup/intent.md").is_file()
    pending = WorkspaceService().open_project(root, "demo")
    assert pending.setup_pending
    assert pending.goal == "Goal"
    monkeypatch.setattr(workspace, "initialize", original)
    assert not WorkspaceService().resume_setup(root, "demo").diagnostics


def test_preparation_failure_leaves_no_project_to_block_retry(tmp_path, monkeypatch):
    root = tmp_path / "workbench"
    original = workspace.write_atomic

    def fail(path, data, *, replace=False):
        if path.name == "intent.md":
            raise OSError("disk full")
        original(path, data, replace=replace)

    monkeypatch.setattr(workspace, "write_atomic", fail)
    with pytest.raises(OSError, match="disk full"):
        WorkspaceService().create_project(root, "demo", "Goal", "Why")
    assert not (root / "projects/demo").exists()
    monkeypatch.setattr(workspace, "write_atomic", original)
    assert not WorkspaceService().create_project(root, "demo", "Goal", "Why").diagnostics


def test_pending_setup_refuses_external_edit_before_mutating_any_target(tmp_path, monkeypatch):
    root = tmp_path / "workbench"
    interrupt_brief(root, monkeypatch)
    (root / "projects/demo/brief.md").write_text("Researcher's external edit\n")
    before = files(root)
    with pytest.raises(ValueError, match="refusing overwrite"):
        WorkspaceService().resume_setup(root, "demo")
    assert files(root) == before


def test_corrupted_journal_refused_and_reported_without_repair(tmp_path, monkeypatch):
    root = tmp_path / "workbench"
    interrupt_brief(root, monkeypatch)
    (root / "projects/demo/runs/setup/project-after.md").write_text("corrupt")
    before = files(root)
    view = WorkspaceService().open_project(root, "demo")
    assert view.setup_pending
    assert any("checksum mismatch" in message for message in view.diagnostics)
    with pytest.raises(ValueError, match="checksum mismatch"):
        WorkspaceService().resume_setup(root, "demo")
    assert files(root) == before


def test_root_project_and_target_symlinks_cannot_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root_link = tmp_path / "linked"
    root_link.symlink_to(outside, target_is_directory=True)
    service = WorkspaceService()
    with pytest.raises(ValueError, match="symlinks"):
        service.create_project(root_link, "demo", "Goal", "Why")
    with pytest.raises(ValueError):
        service.create_project(tmp_path / "root", "../outside", "Goal", "Why")
    root = tmp_path / "root"
    root.mkdir()
    (root / "projects").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        service.create_project(root, "demo", "Goal", "Why")
    assert not list(outside.iterdir())


def test_pending_target_symlink_refuses_recovery_without_touching_source(tmp_path, monkeypatch):
    root = tmp_path / "workbench"
    interrupt_brief(root, monkeypatch)
    external = tmp_path / "external.md"
    external.write_text("untouched\n")
    target = root / "projects/demo/brief.md"
    target.unlink()
    target.symlink_to(external)
    with pytest.raises(ValueError, match="symlinks"):
        WorkspaceService().resume_setup(root, "demo")
    assert external.read_text() == "untouched\n"


def test_open_corrupt_charter_returns_diagnostics_and_preserves_files(tmp_path):
    root = tmp_path / "workbench"
    initialize(root, "demo")
    (root / "projects/demo/PROJECT.md").write_bytes(b"bad header")
    before = files(root)
    view = WorkspaceService().open_project(root, "demo")
    assert view.diagnostics
    assert view.stage == "unknown"
    assert files(root) == before


def test_concurrent_setup_is_refused_before_root_creation(tmp_path):
    root = tmp_path / "new"
    with handoff_mutex(root):
        with pytest.raises(FormatError, match="writer holds"):
            WorkspaceService().create_project(root, "demo", "Goal", "Why")
    assert not root.exists()


def test_list_excludes_invalid_names_and_symlink_projects(tmp_path):
    root = tmp_path / "workbench"
    initialize(root, "demo")
    (root / "projects/.hidden").mkdir()
    (root / "projects/UPPERCASE").mkdir()
    (root / "projects/alias").symlink_to(root / "projects/demo", target_is_directory=True)
    assert WorkspaceService().list_projects(root) == ["demo"]
    assert WorkspaceService().list_projects(tmp_path / "missing") == []


def test_source_changed_after_preview_refused_before_mutation(tmp_path):
    source = tmp_path / "idea.md"
    source.write_text("Changed source\n")
    root = tmp_path / "new"
    with pytest.raises(ValueError, match="source changed since preview"):
        WorkspaceService().create_project(
            root, "demo", "Goal", "Why", source, expected_source_sha256="0" * 64
        )
    assert not root.exists()


def test_nonregular_source_refused_without_blocking(tmp_path):
    import os

    source = tmp_path / "idea.md"
    os.mkfifo(source)
    root = tmp_path / "new"
    with pytest.raises(ValueError, match="regular source file"):
        WorkspaceService().create_project(root, "demo", "Goal", "Why", source)
    assert not root.exists()


def test_explicit_import_may_copy_external_source_symlink_without_modifying_it(tmp_path):
    source = tmp_path / "original.md"
    source.write_bytes(b"Original source\r\n")
    link = tmp_path / "chosen.md"
    link.symlink_to(source)
    root = tmp_path / "workbench"
    view = WorkspaceService().create_project(root, "demo", "Goal", "Why", link)
    assert not view.diagnostics
    assert (root / "projects/demo/runs/setup/source.md").read_bytes() == source.read_bytes()
    assert link.is_symlink()
    assert source.read_bytes() == b"Original source\r\n"


def test_invalid_setup_source_metadata_opens_with_diagnostics(tmp_path):
    from toulmin.core.codec import encode

    root = tmp_path / "workbench"
    service = WorkspaceService()
    service.create_project(root, "demo", "Goal", "Why")
    path = root / "projects/demo/runs/setup/intent.md"
    intent = decode(path.read_bytes())
    intent.header["source_file"] = ["source.md"]
    path.write_bytes(encode(intent))
    before = files(root)
    view = service.open_project(root, "demo")
    assert any("source_file" in message for message in view.diagnostics)
    assert files(root) == before


def test_new_project_refuses_conflicting_existing_global_templates_and_preserves_them(tmp_path):
    root = tmp_path / "workbench"
    service = WorkspaceService()
    service.create_project(root, "first", "Goal", "Why")
    agent = root / "AGENTS.md"
    agent.write_text("Custom instructions\n")
    first = files(root / "projects/first")
    with pytest.raises(ValueError, match="Conflicting file"):
        service.create_project(root, "second", "New goal", "New motivation")
    assert agent.read_text() == "Custom instructions\n"
    assert files(root / "projects/first") == first
    view = service.open_project(root, "second")
    assert view.setup_pending
    assert view.goal == "New goal"
