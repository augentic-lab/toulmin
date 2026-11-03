"""Headless UI1 acceptance; no model processes or real research projects."""

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("textual", reason="install Toulmin's tui extra to test the terminal UI")

from textual.widgets import Button, Input, ListView, Select, Static, TextArea

from toulmin.application.workspace import WorkspaceService
from toulmin.tui.app import (
    DocumentView,
    FileBrowser,
    HelpScreen,
    HomeScreen,
    ImportPreview,
    OpenScreen,
    QuitScreen,
    SetupScreen,
    ToulminApp,
    WorkspaceScreen,
    safe_text,
)


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


@pytest.mark.parametrize("size", [(120, 36), (80, 24), (60, 20)])
def test_keyboard_create_reopen_and_quit(tmp_path, size):
    async def scenario():
        root = tmp_path / "workbench"
        app = ToulminApp(root=root)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)
            await pilot.press("enter")
            assert isinstance(app.screen, SetupScreen)
            assert app.focused.id == "setup-slug"
            await pilot.press(*"latency", "tab", *"Understand queues", "enter", *"Measure tails")
            assert (
                app.screen.query_one("#setup-goal", TextArea).text
                == "Understand queues\nMeasure tails"
            )
            await pilot.press("tab", *"Users wait too long")
            for _ in range(4):
                await pilot.press("tab")
            assert app.focused.id == "create-project"
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, WorkspaceScreen)
            assert app.screen.view.goal == "Understand queues\nMeasure tails"
            assert app.screen.view.motivation == "Users wait too long"
            assert "Users wait too long" in app.screen.view.brief
            assert app.screen.view.setup_pending is False
            saved = snapshot(root)
            await pilot.press("escape")
            assert isinstance(app.screen, HomeScreen)
            await pilot.press("tab", "enter")
            await pilot.pause()
            assert isinstance(app.screen, OpenScreen)
            assert len(app.screen.query_one("#project-list", ListView).children) == 1
            await pilot.press("enter")
            await pilot.pause()
            assert app.focused.id == "resume-project"
            await pilot.press("enter")
            assert isinstance(app.screen, WorkspaceScreen)
            assert app.screen.view.goal == "Understand queues\nMeasure tails"
            assert snapshot(root) == saved
            await pilot.press("ctrl+q")
            assert isinstance(app.screen, QuitScreen)
            await pilot.press("escape")
            assert isinstance(app.screen, WorkspaceScreen)
            await pilot.press("ctrl+q", "tab", "enter")
            await pilot.pause()
            assert not app.is_running

    asyncio.run(scenario())


@pytest.mark.parametrize("suffix", [".md", ".txt"])
def test_import_preview_edits_motivation_and_preserves_original(tmp_path, suffix):
    async def scenario():
        root = tmp_path / "workbench"
        source = tmp_path / f"idea{suffix}"
        raw = "# Original idea\r\n\r\n延迟 matters.\r\n".encode()
        source.write_bytes(raw)
        app = ToulminApp(root=root)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            screen = app.screen
            screen.query_one("#setup-slug", Input).value = "imported"
            screen.query_one("#setup-goal", TextArea).load_text("Measure queueing")
            screen.query_one("#import-path", Input).value = str(source)
            screen.query_one("#preview-import", Button).focus()
            await pilot.press("enter")
            assert isinstance(app.screen, ImportPreview)
            preview = app.screen.query_one("#import-preview", TextArea)
            assert "延迟 matters." in preview.text
            preview.load_text("Edited motivation from the imported idea.")
            app.screen.query_one("#use-import", Button).focus()
            await pilot.press("enter")
            assert isinstance(app.screen, SetupScreen)
            assert screen.source_path == source
            screen.query_one("#create-project", Button).focus()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, WorkspaceScreen)
            assert app.screen.view.motivation == "Edited motivation from the imported idea."
            assert source.read_bytes() == raw
            assert (root / f"projects/imported/runs/setup/source{suffix}").read_bytes() == raw

    asyncio.run(scenario())


def test_changed_import_refuses_creation_until_previewed_again(tmp_path):
    async def scenario():
        root = tmp_path / "workbench"
        source = tmp_path / "idea.md"
        source.write_text("First source", encoding="utf-8")
        app = ToulminApp(root=root)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            screen = app.screen
            screen.query_one("#setup-slug", Input).value = "demo"
            screen.query_one("#setup-goal", TextArea).load_text("Research goal")
            screen.preview_path(str(source))
            await pilot.pause()
            app.screen.query_one("#use-import", Button).focus()
            await pilot.press("enter")
            source.write_text("Changed source", encoding="utf-8")
            screen.query_one("#create-project", Button).focus()
            await pilot.press("enter")
            assert isinstance(app.screen, SetupScreen)
            assert "source changed" in str(screen.query_one("#setup-error", Static).render())
            assert not root.exists()

    asyncio.run(scenario())


def test_import_errors_cancel_browser_and_safe_setup_exit(tmp_path):
    async def scenario():
        app = ToulminApp(root=tmp_path / "workbench")
        async with app.run_test(size=(60, 20)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            screen = app.screen
            screen.query_one("#setup-goal", TextArea).load_text("Keep my form")
            screen.query_one("#import-path", Input).value = str(tmp_path / "idea.pdf")
            screen.query_one("#preview-import", Button).focus()
            await pilot.press("enter")
            assert "Unsupported format" in str(screen.query_one("#setup-error", Static).render())
            binary = tmp_path / "broken.txt"
            binary.write_bytes(b"\xff")
            screen.preview_path(str(binary))
            assert "utf-8" in str(screen.query_one("#setup-error", Static).render())
            screen.query_one("#browse-import", Button).focus()
            await pilot.press("enter")
            assert isinstance(app.screen, FileBrowser)
            await pilot.press("escape")
            assert app.screen is screen
            await pilot.press("ctrl+q")
            assert isinstance(app.screen, QuitScreen)
            await pilot.press("escape")
            assert screen.query_one("#setup-goal", TextArea).text == "Keep my form"
            await pilot.press("escape")
            await pilot.press("escape")
            assert app.screen is screen
            assert not (tmp_path / "workbench").exists()

    asyncio.run(scenario())


def test_navigation_inspector_and_live_resize_are_read_only(tmp_path):
    async def scenario():
        root = tmp_path / "workbench"
        WorkspaceService().create_project(root, "demo", "Find bottlenecks", "Tail latency matters")
        saved = snapshot(root)
        app = ToulminApp(root=root, project="demo")
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, WorkspaceScreen)
            assert screen.query_one("#inspector").display
            screen.query_one("#step-list", ListView).focus()
            await pilot.press("down", "enter")
            assert screen.step == "Brief"
            assert (
                "Tail latency matters" in screen.query_one("#main-content", DocumentView)._markdown
            )
            await pilot.press("f2")
            assert not screen.query_one("#inspector").display
            await pilot.resize_terminal(80, 24)
            await pilot.pause()
            assert screen.has_class("medium")
            await pilot.press("f2")
            assert screen.query_one("#inspector").display
            assert not screen.query_one("#main-pane").display
            await pilot.resize_terminal(60, 20)
            await pilot.pause()
            assert screen.has_class("compact")
            assert not screen.query_one("#navigation").display
            assert not screen.query_one("#resize-notice").display
            screen.query_one("#step-select", Select).focus()
            await pilot.press("enter", "down", "enter")
            assert screen.step == "Key Claims"
            assert screen.query_one("#main-pane").display
            assert not screen.query_one("#inspector").display
            screen.choose_step("Explore")
            assert screen.query_one("#composer", TextArea).display
            assert not screen.query_one("#send-message", Button).disabled
            for step in ["Review", "Resolve", "Handoff"]:
                screen.choose_step(step)
                assert "coming later" in screen.query_one("#main-content", DocumentView)._markdown
            await pilot.press("f1")
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("escape", "ctrl+q")
            assert isinstance(app.screen, QuitScreen)
            await pilot.press("escape")
            await pilot.resize_terminal(120, 36)
            await pilot.pause()
            assert not screen.has_class("compact")
            assert not screen.has_class("medium")
            assert snapshot(root) == saved

    asyncio.run(scenario())


def test_diagnostics_keep_corrupt_project_inspectable_without_writes(tmp_path):
    async def scenario():
        root = tmp_path / "workbench"
        service = WorkspaceService()
        service.create_project(root, "demo", "Find bottlenecks", "Tail latency matters")
        charter = root / "projects/demo/PROJECT.md"
        charter.write_bytes(b"broken project header\n")
        saved = snapshot(root)
        app = ToulminApp(root=root, project="demo")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, WorkspaceScreen)
            assert app.screen.view.diagnostics
            assert "Diagnostics" in app.screen.query_one("#main-content", DocumentView)._markdown
            assert "Tail latency matters" in app.screen.view.brief
            assert snapshot(root) == saved

    asyncio.run(scenario())


def test_missing_explicit_project_opens_picker_with_error(tmp_path):
    async def scenario():
        app = ToulminApp(root=tmp_path, project="missing")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, OpenScreen)
            assert "missing" in str(app.screen.query_one("#open-error", Static).render())

    asyncio.run(scenario())


def test_rendered_text_strips_terminal_controls():
    assert safe_text("ok\x1b[31mred\x1b[0m\x00\r\n") == "okred\n"


def test_explicit_resume_setup_finishes_saved_intent(tmp_path):
    async def scenario():
        root = tmp_path / "workbench"
        service = WorkspaceService()
        service.create_project(root, "demo", "Find bottlenecks", "Tail latency matters")
        marker = root / "projects/demo/runs/setup/complete"
        marker.unlink()
        app = ToulminApp(root=root, project="demo", service=service)
        async with app.run_test(size=(60, 20)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, WorkspaceScreen)
            assert screen.view.setup_pending
            assert screen.step == "Setup"
            screen.query_one("#resume-setup", Button).focus()
            await pilot.press("enter")
            assert not screen.view.setup_pending
            assert marker.exists()
            assert not screen.query_one("#resume-setup", Button).display

    asyncio.run(scenario())


def test_failed_second_open_clears_previous_selection(tmp_path, monkeypatch):
    async def scenario():
        root = tmp_path / "workbench"
        service = WorkspaceService()
        service.create_project(root, "alpha", "First goal", "First motivation")
        service.create_project(root, "beta", "Second goal", "Second motivation")
        app = ToulminApp(root=root, service=service)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("tab", "enter")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, OpenScreen)
            await pilot.press("enter")
            assert screen.selected_view.project == "alpha"

            def fail_open(*args, **kwargs):
                raise ValueError("beta is no longer accessible")

            monkeypatch.setattr(service, "open_project", fail_open)
            screen.query_one("#project-list", ListView).focus()
            await pilot.press("down", "enter")
            assert screen.selected_view is None
            assert screen.query_one("#resume-project", Button).disabled
            assert "beta" in str(screen.query_one("#open-error", Static).render())

    asyncio.run(scenario())


def test_setup_git_failure_is_reported_without_crashing(tmp_path, monkeypatch):
    def fail_create(*args, **kwargs):
        raise RuntimeError("Git initialization failed")

    async def scenario():
        root = tmp_path / "workbench"
        service = WorkspaceService()
        monkeypatch.setattr(service, "create_project", fail_create)
        app = ToulminApp(root=root, service=service)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            screen = app.screen
            screen.query_one("#create-project", Button).focus()
            await pilot.press("enter")
            assert isinstance(app.screen, SetupScreen)
            assert "Git initialization failed" in str(
                screen.query_one("#setup-error", Static).render()
            )
            assert not root.exists()

    asyncio.run(scenario())
