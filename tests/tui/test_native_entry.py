"""Native entry preserves the current project and requires a deliberate choice."""

import asyncio

import pytest

pytest.importorskip("textual")

from textual.widgets import Button

from toulmin.application.workspace import WorkspaceService
from toulmin.protocols.native import begin_native, finalize_native
from toulmin.tui.app import NativeChoice, ToulminApp, WorkspaceScreen


def test_f4_offers_native_cli_without_starting_it(tmp_path, monkeypatch):
    async def scenario():
        root = tmp_path / "workbench"
        WorkspaceService().create_project(root, "topic", "Understand latency", "Repeated delays")
        native = begin_native(root, "topic", "codex", "researcher")
        finalize_native(root, "topic", native.id, 0)
        app = ToulminApp(root=root, project="topic")
        calls = []
        monkeypatch.setattr(WorkspaceScreen, "open_native", lambda self, *args: calls.append(args))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("f4")
            await pilot.pause()
            assert isinstance(app.screen, NativeChoice)
            assert calls == []
            assert app.screen.sessions[0][0] == native.id
            await pilot.click("#native-claude")
            await pilot.pause()
            assert calls == [("claude", None, False)]
            await pilot.press("f4", "escape")
            assert len(calls) == 1

    asyncio.run(scenario())


def test_native_choice_compact_controls_are_reachable(tmp_path):
    async def scenario():
        root = tmp_path / "workbench"
        WorkspaceService().create_project(root, "topic", "Goal", "Motivation")
        app = ToulminApp(root=root, project="topic")
        async with app.run_test(size=(60, 20)) as pilot:
            await pilot.pause()
            await pilot.press("f4")
            await pilot.pause()
            button = app.screen.query_one("#native-codex", Button)
            button.scroll_visible(immediate=True)
            await pilot.pause()
            assert button.region.intersection(app.screen.region).height > 0
            await pilot.press("escape")
            assert isinstance(app.screen, WorkspaceScreen)

    asyncio.run(scenario())


def test_returning_from_native_reloads_saved_brief(tmp_path, monkeypatch):
    from contextlib import nullcontext

    import toulmin.application.native as runtime

    async def scenario():
        root = tmp_path / "workbench"
        WorkspaceService().create_project(root, "topic", "Goal", "Motivation")
        brief = root / "projects/topic/brief.md"
        updated = brief.read_text() + "\nConfirmed native research result.\n"
        calls = []

        def launch(*args, **kwargs):
            calls.append((args, kwargs))
            brief.write_text(updated)

        monkeypatch.setattr(runtime, "launch_native", launch)
        app = ToulminApp(root=root, project="topic")
        monkeypatch.setattr(app, "suspend", nullcontext)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.screen.open_native("codex", None, False)
            await pilot.pause()
            assert app.screen.view.brief == updated
            assert calls[0][0] == (root, "topic", "codex")
            assert calls[0][1]["actor"] == app.discussion.actor

    asyncio.run(scenario())
