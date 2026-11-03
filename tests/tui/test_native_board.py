"""Native research board behavior with file-backed test state, never a model CLI."""

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("textual", reason="install Toulmin's tui extra")

from textual.widgets import Button, Static

from toulmin.tui import native
from toulmin.tui.native import ConfirmNativeBrief, NativeBoard, display_text


def visible(app, selector):
    return str(app.screen.query_one(selector, Static).render())


def state(tmp_path, **changes):
    values = dict(
        id="native-test",
        root=tmp_path,
        project="queues",
        workspace=tmp_path / "workspace",
        context="Research context",
        goal="Find where query time is spent",
        stage="explore",
        brief="Saved research Brief\n",
        before="Saved research Brief\n",
        draft="Proposed research Brief\n",
        status="started",
        output_status="running",
        run=None,
        proposal_status="pending",
        application_status="none",
        archive=tmp_path / "runs" / "native-test",
        agent="codex",
        actor="researcher",
        failure=None,
        exit_code=None,
        interrupted=False,
        model=None,
        session_id=None,
    )
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("size", [(38, 24), (80, 24), (120, 36)])
def test_live_refresh_then_archived_explicit_apply(tmp_path, monkeypatch, size):
    current = state(tmp_path)
    calls = []
    brief = tmp_path / "brief.md"
    brief.write_text(current.brief)
    monkeypatch.setattr(native, "load_native", lambda *args: current)

    def apply(root, project, session, displayed, actor):
        calls.append((root, project, session, displayed, actor))
        brief.write_text(displayed)
        current.brief = displayed
        current.proposal_status = "applied"
        current.application_status = "applied"
        return current

    monkeypatch.setattr(native, "apply_native", apply)

    async def scenario():
        app = NativeBoard(tmp_path, "queues", "native-test", "researcher")
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert "Research stage: explore" in visible(app, "#stage")
            assert current.goal in visible(app, "#goal")
            assert "Proposed research" in visible(app, "#draft")
            assert "Saved research" in visible(app, "#brief")
            assert "not archived yet" in visible(app, "#provenance")
            assert app.query_one("#apply", Button).disabled
            for selector in ("#refresh", "#preview", "#apply"):
                region = app.query_one(selector).region
                assert 0 <= region.x < region.right <= size[0]
                assert 0 <= region.y < region.bottom <= size[1]
            await pilot.press("a")
            assert not isinstance(app.screen, ConfirmNativeBrief)
            await pilot.press("p")
            assert isinstance(app.screen, ConfirmNativeBrief)
            assert app.screen.query_one("#confirm-apply", Button).disabled
            await pilot.press("escape")
            current.status = "closed"
            current.output_status = "completed"
            current.run = "R-003"
            current.exit_code = 0
            await pilot.pause(0.9)
            assert "R-003" in visible(app, "#provenance")
            assert not app.query_one("#apply", Button).disabled
            await pilot.press("a")
            assert isinstance(app.screen, ConfirmNativeBrief)
            assert "Proposed research Brief" in visible(app, "#confirm-preview")
            await pilot.press("d")
            assert "--- Saved Brief now" in visible(app, "#confirm-preview")
            assert "+Proposed research Brief" in visible(app, "#confirm-preview")
            for selector in ("#cancel", "#confirm-apply", "#toggle-preview"):
                region = app.screen.query_one(selector).region
                assert 0 <= region.x < region.right <= size[0]
                assert 0 <= region.y < region.bottom <= size[1]
            await pilot.press("escape")
            assert not calls
            assert brief.read_text() == "Saved research Brief\n"
            await pilot.press("p")
            app.screen.query_one("#confirm-apply", Button).focus()
            await pilot.press("enter")
            await pilot.pause()
            assert calls == [(tmp_path, "queues", "native-test", current.draft, "researcher")]
            assert brief.read_text() == current.draft
            assert "Applied displayed draft" in visible(app, "#message")
            assert app.query_one("#apply", Button).disabled
            assert "Applied draft" in visible(app, "#draft-heading")
            await pilot.press("q")
        assert not app.is_running

    asyncio.run(scenario())


@pytest.mark.parametrize("conflict", ["draft", "brief"])
def test_captured_confirmation_and_protocol_refusal(tmp_path, monkeypatch, conflict):
    current = state(tmp_path, status="closed", output_status="completed", run="R-003")
    original = current.draft
    calls = []
    monkeypatch.setattr(native, "load_native", lambda *args: current)

    def apply(root, project, session, displayed, actor):
        calls.append(displayed)
        raise ValueError("External file changed; review again")

    monkeypatch.setattr(native, "apply_native", apply)

    async def scenario():
        app = NativeBoard(tmp_path, "queues", "native-test", "researcher")
        async with app.run_test(size=(38, 24)) as pilot:
            await pilot.pause()
            await pilot.press("a")
            if conflict == "draft":
                current.draft = "External draft update\n"
            else:
                current.brief = "External saved Brief update\n"
            app.action_refresh()
            assert original.strip() in visible(app, "#confirm-preview")
            app.screen.query_one("#confirm-apply", Button).focus()
            await pilot.press("enter")
            await pilot.pause()
            assert calls == [original]
            assert "Apply refused: External file changed" in visible(app, "#message")

    asyncio.run(scenario())


@pytest.mark.parametrize("interrupted", [True, False])
def test_failed_or_interrupted_session_preserves_preview(tmp_path, monkeypatch, interrupted):
    current = state(
        tmp_path,
        status="closed",
        output_status="failed",
        run="R-004",
        failure="Cancelled by researcher" if interrupted else "CLI exited with code 2",
        exit_code=130 if interrupted else 2,
        interrupted=interrupted,
    )
    monkeypatch.setattr(native, "load_native", lambda *args: current)

    async def scenario():
        app = NativeBoard(tmp_path, "queues", "native-test", "researcher")
        async with app.run_test(size=(38, 24)) as pilot:
            await pilot.pause()
            assert current.failure in visible(app, "#provenance")
            assert ("interrupted" if interrupted else "failed") in visible(app, "#provenance")
            assert app.query_one("#apply", Button).disabled
            assert "preview only" in visible(app, "#next-action")
            await pilot.press("p")
            assert current.draft.strip() in visible(app, "#confirm-preview")
            assert app.screen.query_one("#confirm-apply", Button).disabled

    asyncio.run(scenario())


def test_literal_text_controls_and_read_failure(tmp_path, monkeypatch):
    current = state(tmp_path, goal="[bold]literal[/bold]\x1b[31m red\x07\x9b\u202e")
    monkeypatch.setattr(native, "load_native", lambda *args: current)

    async def scenario():
        app = NativeBoard(tmp_path, "queues", "native-test", "researcher")
        async with app.run_test(size=(38, 24)) as pilot:
            await pilot.pause()
            goal = visible(app, "#goal")
            assert "[bold]literal[/bold] red" in goal
            assert all(char not in goal for char in "\x1b\x07\x9b\u202e")
            previous = visible(app, "#draft")

            def refuse(*args):
                raise ValueError("unsafe [link]file[/link]\x1b[31m")

            monkeypatch.setattr(native, "load_native", refuse)
            app.action_refresh()
            assert "Refresh refused" in visible(app, "#message")
            assert visible(app, "#draft") == previous
            assert app.view is None
            assert app.query_one("#apply", Button).disabled
            assert app.query_one("#preview", Button).disabled

    asyncio.run(scenario())


def test_display_text_preserves_unicode_and_strips_terminal_controls():
    assert display_text("研究\n\t[red]\x1b]8;;https://x\x07link\x1b]8;;\x07\x7f") == (
        "研究\n\t[red]link"
    )


@pytest.mark.parametrize("external_edit", [False, True])
def test_real_protocol_archiving_and_confirmed_publication(tmp_path, external_edit):
    from toulmin.application.workspace import WorkspaceService
    from toulmin.protocols.native import begin_native, finalize_native, load_native

    root = tmp_path / "workbench"
    WorkspaceService().create_project(root, "queues", "Understand queue cost", "Latency matters")
    session = begin_native(root, "queues", "codex", "researcher")
    draft = session.brief + "\nProposal from native exploration.\n"
    (session.workspace / "draft.md").write_text(draft)
    brief = root / "projects" / "queues" / "brief.md"
    before = brief.read_text()

    async def scenario():
        app = NativeBoard(root, "queues", session.id, "researcher")
        async with app.run_test(size=(38, 24)) as pilot:
            await pilot.pause()
            assert app.query_one("#apply", Button).disabled
            closed = finalize_native(root, "queues", session.id, exit_code=0)
            app.action_refresh()
            assert closed.run in visible(app, "#provenance")
            assert not app.query_one("#apply", Button).disabled
            await pilot.press("a")
            assert brief.read_text() == before
            if external_edit:
                brief.write_text(before + "\nExternal researcher edit.\n")
            app.screen.query_one("#confirm-apply", Button).focus()
            await pilot.press("enter")
            await pilot.pause()
            if external_edit:
                assert "conflict" in visible(app, "#message")
                assert brief.read_text().endswith("External researcher edit.\n")
                assert load_native(root, "queues", session.id).proposal_status == "pending"
            else:
                assert brief.read_text() == draft
                assert load_native(root, "queues", session.id).proposal_status == "applied"
                assert app.query_one("#apply", Button).disabled

    asyncio.run(scenario())
