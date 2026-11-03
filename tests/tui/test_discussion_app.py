"""Production discussion UI against durable protocols; no real model invocation."""

import asyncio

import pytest

pytest.importorskip("textual", reason="install Toulmin's tui extra")

from textual.widgets import Button, Select, Static, TextArea

from toulmin.application.discussion import DiscussionService
from toulmin.application.workspace import WorkspaceService
from toulmin.protocols.discussion import begin_turn, finish_turn, preview_context
from toulmin.protocols.review import ReviewOutcome
from toulmin.tui.app import (
    ApplyBrief,
    ContextPreview,
    DocumentView,
    HomeScreen,
    SessionControls,
    ToulminApp,
    WorkspaceScreen,
)


class ControlledDiscussion(DiscussionService):
    """A test owns completion timing; the real file protocols own every record."""

    def __init__(self):
        super().__init__(actor="researcher")
        self.calls = []
        self.request = None
        self.running = False
        self.closed = False
        self.fresh_calls = []
        self.context_calls = []

    def models(self, root):
        return ("test-model",)

    def context(self, root, project, model=None, *, fresh=False):
        self.context_calls.append((model, fresh))
        return preview_context(root, project)

    def start(self, root, project, text, model, operation="explore", *, fresh=False):
        turn = begin_turn(root, project, text, model, self.actor, operation)
        self.calls.append((project, text, operation))
        self.fresh_calls.append(fresh)
        self.request = (root, project, turn.id)
        self.running = True
        return turn.id

    def active(self, root, project):
        return self.running

    def finish(self, text="Test response", failure=None):
        root, project, request = self.request
        finish_turn(root, project, request, ReviewOutcome(text, "test-model", None, 0.1, failure))
        self.running = False

    def stop(self, root, project):
        self.finish("", "Cancelled by researcher")

    def close(self):
        if self.running:
            self.stop(*self.request[:2])
        self.closed = True


def prepare(tmp_path):
    root = tmp_path / "workbench"
    WorkspaceService().create_project(root, "demo", "Understand queues", "Tail latency matters")
    discussion = ControlledDiscussion()
    return root, discussion


def test_durable_two_turns_context_and_no_calls_on_open(tmp_path):
    async def scenario():
        root, discussion = prepare(tmp_path)
        app = ToulminApp(root=root, project="demo", discussion=discussion)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, WorkspaceScreen)
            assert discussion.calls == []
            screen.query_one("#composer", TextArea).load_text("What should we measure?")
            await pilot.click("#send-message")
            assert discussion.running
            assert (
                "Waiting for the final response"
                in screen.query_one("#transcript", DocumentView)._markdown
            )
            discussion.finish("Measure queue depth before changing concurrency.")
            await pilot.pause(0.5)
            screen.query_one("#composer", TextArea).load_text("What would falsify that?")
            await pilot.click("#send-message")
            assert len(discussion.calls) == 2
            discussion.finish("Low queue depth while latency rises would challenge it.")
            await pilot.pause(0.5)
            await pilot.click("#show-context")
            assert isinstance(app.screen, ContextPreview)
            assert app.screen.context == discussion.context(root, "demo")
            assert "What should we measure?" in app.screen.context
            assert "Measure queue depth" in app.screen.context
            await pilot.press("escape")
        reopened = ControlledDiscussion()
        app = ToulminApp(root=root, project="demo", discussion=reopened)
        async with app.run_test() as pilot:
            await pilot.pause()
            content = app.screen.query_one("#transcript", DocumentView)._markdown
            assert "What should we measure?" in content
            assert "What would falsify that?" in content
            assert "Low queue depth" in content
            assert reopened.calls == []

    asyncio.run(asyncio.wait_for(scenario(), timeout=25))


def test_running_job_survives_navigation_and_stop_is_responsive(tmp_path):
    async def scenario():
        root, discussion = prepare(tmp_path)
        app = ToulminApp(root=root, project="demo", discussion=discussion)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.screen
            screen.query_one("#composer", TextArea).load_text("Investigate queueing")
            await pilot.click("#send-message")
            screen.query_one("#composer", TextArea).load_text("Keep this unfinished question")
            screen.choose_step("Review")
            assert discussion.running
            screen.choose_step("Explore")
            await pilot.press("f2", "f2")
            assert screen.query_one("#composer", TextArea).text == "Keep this unfinished question"
            await pilot.click("#stop-message")
            assert not discussion.running
            assert (
                "Cancelled by researcher" in screen.query_one("#transcript", DocumentView)._markdown
            )
            assert len(discussion.calls) == 1
            screen.action_back()
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)
            app.switch_screen(WorkspaceScreen(app.service.open_project(root, "demo")))
            await pilot.pause()
            assert (
                app.screen.query_one("#composer", TextArea).text == "Keep this unfinished question"
            )

    asyncio.run(asyncio.wait_for(scenario(), timeout=20))


def test_proposal_saved_draft_and_explicit_application(tmp_path):
    async def scenario():
        root, discussion = prepare(tmp_path)
        brief = root / "projects/demo/brief.md"
        original = brief.read_bytes()
        app = ToulminApp(root=root, project="demo", discussion=discussion)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            screen = app.screen
            await pilot.click("#propose-brief")
            assert discussion.calls[0][2] == "brief"
            discussion.finish("# Brief\n\nA proposed queue experiment.\n")
            await pilot.pause(0.5)
            assert brief.read_bytes() == original
            assert screen.query_one("#brief-tab", Select).value == "Proposed"
            editor = screen.query_one("#proposal-editor", TextArea)
            editor.load_text("# Brief\n\nThe researcher edited this experiment.\n")
            await pilot.pause(0.7)
            assert discussion.load(root, "demo").proposal.text == editor.text
            screen.query_one("#brief-tab", Select).value = "Changes"
            await pilot.pause()
            assert (
                "+The researcher edited"
                in screen.query_one("#brief-changes", DocumentView)._markdown
            )
            await pilot.click("#apply-brief")
            assert isinstance(app.screen, ApplyBrief)
            assert app.screen.actor == "researcher"
            assert brief.read_bytes() == original
            await pilot.press("escape")
            assert brief.read_bytes() == original
            await pilot.click("#apply-brief")
            await pilot.click("#confirm-apply")
            await pilot.pause()
            assert brief.read_text() == editor.text
            assert screen.view.stage == "explore"
            assert discussion.load(root, "demo").proposal is None

    asyncio.run(asyncio.wait_for(scenario(), timeout=25))


@pytest.mark.parametrize("size", [(120, 36), (80, 24), (60, 20)])
def test_compact_model_controls_and_retained_composer(tmp_path, size):
    async def scenario():
        root, discussion = prepare(tmp_path)
        app = ToulminApp(root=root, project="demo", discussion=discussion)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, WorkspaceScreen)
            if size == (120, 36):
                for name in ("#navigation", "#main-pane", "#inspector"):
                    assert screen.query_one(name).display
            for name in ("#send-message", "#stop-message", "#show-context", "#propose-brief"):
                control = screen.query_one(name, Button)
                assert control.region.height > 0
                assert control.region.x >= 0
                assert control.region.right <= size[0]
                assert control.region.bottom <= size[1]
            screen.query_one("#composer", TextArea).load_text("One\nTwo")
            screen.query_one("#composer", TextArea).focus()
            screen.query_one("#composer", TextArea).cursor_location = (1, 3)
            await pilot.press("enter", *"Three")
            assert screen.query_one("#composer", TextArea).text.endswith("\nThree")
            await pilot.press("f2", "f2")
            assert screen.query_one("#composer", TextArea).text.endswith("\nThree")
            await pilot.click("#show-context")
            assert isinstance(app.screen, ContextPreview)
            await pilot.press("escape")
            assert discussion.calls == []
            screen.query_one("#composer", TextArea).focus()
            await pilot.press("ctrl+enter")
            assert len(discussion.calls) == 1
            discussion.finish("Keyboard submission received")

    asyncio.run(asyncio.wait_for(scenario(), timeout=20))


def test_interrupted_turn_requires_explicit_recovery(tmp_path):
    async def scenario():
        root, discussion = prepare(tmp_path)
        begin_turn(root, "demo", "Saved before interruption", "test-model", "researcher")
        app = ToulminApp(root=root, project="demo", discussion=discussion)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert discussion.calls == []
            assert screen.query_one("#send-message", Button).disabled
            assert screen.query_one("#recover-discussion", Button).display
            assert "Interrupted" in str(screen.query_one("#discussion-status", Static).render())
            await pilot.click("#recover-discussion")
            assert not screen.query_one("#send-message", Button).disabled
            assert (
                "explicitly recovered without retry"
                in screen.query_one("#transcript", DocumentView)._markdown
            )
            assert discussion.calls == []

    asyncio.run(asyncio.wait_for(scenario(), timeout=20))


def test_confirmed_quit_stops_and_archives_active_attempt(tmp_path):
    async def scenario():
        root, discussion = prepare(tmp_path)
        app = ToulminApp(root=root, project="demo", discussion=discussion)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.screen.query_one("#composer", TextArea).load_text("Keep this request")
            await pilot.click("#send-message")
            await pilot.press("ctrl+q", "escape")
            assert discussion.running
            assert not discussion.closed
            await pilot.press("ctrl+q")
            await pilot.click("#confirm-quit")
            assert discussion.closed
            assert not discussion.running
        turn = discussion.load(root, "demo").turns[-1]
        assert turn.user == "Keep this request"
        assert turn.status == "failed"
        assert "Cancelled" in turn.failure
        assert len(discussion.calls) == 1

    asyncio.run(asyncio.wait_for(scenario(), timeout=20))


def test_interrupted_application_reopens_with_explicit_resume(tmp_path, monkeypatch):
    from toulmin.protocols import discussion as protocol

    async def scenario():
        root, discussion = prepare(tmp_path)
        brief = root / "projects/demo/brief.md"
        original = brief.read_bytes()
        original_write = protocol.write_atomic
        fail_once = True

        def interrupted_write(path, data, replace=False):
            nonlocal fail_once
            if path == brief and fail_once:
                fail_once = False
                raise OSError("Injected interruption before replacing brief")
            return original_write(path, data, replace=replace)

        monkeypatch.setattr(protocol, "write_atomic", interrupted_write)
        app = ToulminApp(root=root, project="demo", discussion=discussion)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            screen = app.screen
            await pilot.click("#propose-brief")
            discussion.finish("# Brief\n\nA confirmed experiment.\n")
            await pilot.pause(0.5)
            await pilot.click("#apply-brief")
            await pilot.click("#confirm-apply")
            await pilot.pause()
            assert brief.read_bytes() == original
            assert screen.query_one("#proposal-editor", TextArea).read_only
            assert "Resume Apply" in str(screen.query_one("#apply-brief", Button).label)
            assert "Application interrupted" in str(
                screen.query_one("#proposal-state", Static).render()
            )
            assert screen.query_one("#dismiss-proposal", Button).disabled
            assert screen.flush_proposal()
            screen.action_back()
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)
        reopened = ControlledDiscussion()
        app = ToulminApp(root=root, project="demo", discussion=reopened)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert screen.query_one("#proposal-editor", TextArea).read_only
            assert "Resume Apply" in str(screen.query_one("#apply-brief", Button).label)
            await pilot.click("#apply-brief")
            assert isinstance(app.screen, ApplyBrief)
            await pilot.click("#confirm-apply")
            await pilot.pause()
            assert brief.read_text() == "# Brief\n\nA confirmed experiment.\n"
            assert reopened.load(root, "demo").proposal is None
            assert reopened.calls == []

    asyncio.run(asyncio.wait_for(scenario(), timeout=25))


def test_finalized_task_error_offers_recovery_without_an_orphan(tmp_path, monkeypatch):
    async def scenario():
        root, discussion = prepare(tmp_path)
        discussion.start(root, "demo", "A saved request", "test-model")
        discussion.finish("A fully archived response")
        problem = {"message": "Finalization sync failed; inspect and Recover."}
        recover = discussion.recover

        def error(root, project):
            return problem["message"]

        def resolve(root, project):
            recover(root, project)
            problem["message"] = None

        monkeypatch.setattr(discussion, "error", error)
        monkeypatch.setattr(discussion, "recover", resolve)
        app = ToulminApp(root=root, project="demo", discussion=discussion)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert screen.query_one("#send-message", Button).disabled
            assert screen.query_one("#recover-discussion", Button).display
            assert not screen.query_one("#recover-discussion", Button).disabled
            await pilot.click("#recover-discussion")
            assert not screen.query_one("#send-message", Button).disabled
            assert not screen.query_one("#recover-discussion", Button).display
            assert len(discussion.calls) == 1

    asyncio.run(asyncio.wait_for(scenario(), timeout=20))


def test_small_inspector_shows_proposal_and_clickable_apply(tmp_path):
    from xml.etree import ElementTree

    async def scenario():
        root, discussion = prepare(tmp_path)
        discussion.start(root, "demo", "Propose a brief", "test-model", operation="brief")
        discussion.finish(
            "# Compact draft marker\n\nA readable proposal.\n\nKeep uncertainty visible.\n"
        )
        app = ToulminApp(root=root, project="demo", discussion=discussion)
        async with app.run_test(size=(60, 20)) as pilot:
            await pilot.pause()
            await pilot.press("f2")
            await pilot.pause()
            screen = app.screen
            editor = screen.query_one("#proposal-editor", TextArea)
            viewport = screen.query_one("#inspector-scroll").content_region
            assert editor.region.intersection(viewport).height >= 5
            visible = "".join(ElementTree.fromstring(app.export_screenshot()).itertext())
            assert "Compact" in visible and "draft" in visible and "marker" in visible
            apply = screen.query_one("#apply-brief", Button)
            assert apply.region.height == 1
            assert apply.region.y >= 0 and apply.region.bottom <= 20
            assert await pilot.click("#apply-brief")
            assert isinstance(app.screen, ApplyBrief)
            await pilot.press("escape")
            assert discussion.load(root, "demo").proposal is not None

    asyncio.run(asyncio.wait_for(scenario(), timeout=20))


def test_send_flushes_pending_proposal_before_freezing_prompt(tmp_path):
    from toulmin.protocols.discussion import get_turn_prompt

    async def scenario():
        root, discussion = prepare(tmp_path)
        discussion.start(root, "demo", "Draft an experiment", "test-model", operation="brief")
        discussion.finish("# Brief\n\nAn earlier experiment.\n")
        app = ToulminApp(root=root, project="demo", discussion=discussion)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            screen = app.screen
            screen.query_one("#composer", TextArea).load_text("Discuss the edited experiment")
            edited = "# Brief\n\nThe latest pending experiment marker.\n"
            screen.query_one("#proposal-editor", TextArea).load_text(edited)
            screen.proposal_changed()
            assert "Saving draft" in str(screen.query_one("#proposal-state", Static).render())
            # Send synchronously before the 400 ms autosave timer can run.
            screen.action_send()
            assert len(discussion.calls) == 2
            prompt = get_turn_prompt(*discussion.request)
            assert edited in prompt
            assert discussion.load(root, "demo").proposal.text == edited
            discussion.finish("I used the latest pending draft.")

    asyncio.run(asyncio.wait_for(scenario(), timeout=20))


def test_shutdown_timer_does_not_refresh_dismantling_workspace(tmp_path, monkeypatch):
    async def scenario():
        root, discussion = prepare(tmp_path)
        app = ToulminApp(root=root, project="demo", discussion=discussion)
        close_all = app._close_all

        async def close_with_queued_poll():
            # Exercise the actual shutdown boundary before it tears down widgets.
            assert not app.is_running
            screen = app.screen

            def forbidden_refresh():
                pytest.fail("A queued poll refreshed a workspace during teardown")

            monkeypatch.setattr(screen, "refresh_discussion", forbidden_refresh)
            app.poll_discussion()
            await close_all()

        monkeypatch.setattr(app, "_close_all", close_with_queued_poll)
        async with app.run_test() as pilot:
            await pilot.pause()
        app.poll_discussion()  # Already-queued work is harmless after screens are gone.

    asyncio.run(asyncio.wait_for(scenario(), timeout=15))


def test_idle_poll_does_not_reload_archives_but_completion_and_errors_do(tmp_path, monkeypatch):
    async def scenario():
        root, discussion = prepare(tmp_path)
        app = ToulminApp(root=root, project="demo", discussion=discussion)
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.screen
            original_load = discussion.load
            reads = []
            problem = {"message": None}

            def load(root, project):
                reads.append((root, project))
                return original_load(root, project)

            monkeypatch.setattr(discussion, "load", load)
            monkeypatch.setattr(discussion, "error", lambda *_: problem["message"])
            for _ in range(3):
                app.poll_discussion()
            assert reads == []
            screen.query_one("#composer", TextArea).load_text("Run one request")
            screen.action_send()
            assert screen._active
            reads.clear()
            discussion.finish("The completed answer is visible")
            app.poll_discussion()
            assert len(reads) == 1
            assert not screen._active
            assert (
                "The completed answer is visible"
                in screen.query_one("#transcript", DocumentView)._markdown
            )
            app.poll_discussion()
            assert len(reads) == 1
            problem["message"] = "Archiving failed; Recover is required."
            app.poll_discussion()
            assert len(reads) == 2
            assert screen.query_one("#recover-discussion", Button).display
            assert screen.query_one("#send-message", Button).disabled
            app.poll_discussion()
            assert len(reads) == 2
            problem["message"] = "A different finalization error"
            app.poll_discussion()
            assert len(reads) == 3

    asyncio.run(asyncio.wait_for(scenario(), timeout=15))


def test_session_rebuild_is_explicit_pending_and_only_consumed_by_send(tmp_path):
    async def scenario():
        root, discussion = prepare(tmp_path)
        app = ToulminApp(root=root, project="demo", discussion=discussion)
        async with app.run_test(size=(60, 20)) as pilot:
            await pilot.pause()
            screen = app.screen
            await pilot.press("f3")
            assert isinstance(app.screen, SessionControls)
            for name in ("#session-rebuild", "#session-continue", "#session-close"):
                control = app.screen.query_one(name, Button)
                assert control.region.height > 0
                assert control.region.bottom <= 20
                assert control.region.right <= 60
            assert discussion.calls == []
            assert await pilot.click("#session-rebuild")
            assert screen.fresh_session
            assert "rebuild" in str(screen.query_one("#discussion-status", Static).render())
            await pilot.click("#show-context")
            assert isinstance(app.screen, ContextPreview)
            assert discussion.context_calls[-1] == ("test-model", True)
            await pilot.press("escape")
            screen.action_back()
            await pilot.pause()
            app.switch_screen(WorkspaceScreen(app.service.open_project(root, "demo")))
            await pilot.pause()
            screen = app.screen
            assert screen.fresh_session
            screen.propose_brief()
            assert discussion.fresh_calls == [False]
            assert screen.fresh_session
            discussion.finish("# Brief\n\nPending proposal.\n")
            screen.refresh_discussion()
            screen.query_one("#composer", TextArea).load_text("Rebuild this conversation")
            screen.action_send()
            assert discussion.fresh_calls == [False, True]
            assert not screen.fresh_session
            discussion.finish("Rebuilt response")
            await pilot.press("f3")
            await pilot.click("#session-rebuild")
            await pilot.press("f3")
            await pilot.click("#session-continue")
            assert not screen.fresh_session
            assert len(discussion.calls) == 2

    asyncio.run(asyncio.wait_for(scenario(), timeout=25))


def test_session_metadata_is_visible_in_transcript_and_details(tmp_path, monkeypatch):
    from dataclasses import replace

    async def scenario():
        root, discussion = prepare(tmp_path)
        discussion.start(root, "demo", "Continue our research", "test-model")
        discussion.finish("An archived answer")
        load = discussion.load
        session_id = "native-session-1234567890"

        def load_with_session(root, project):
            view = load(root, project)
            turn = replace(
                view.turns[0],
                session_mode="resume",
                session_reason="resume",
                session_id=session_id,
            )
            return replace(view, turns=(turn,))

        monkeypatch.setattr(discussion, "load", load_with_session)
        app = ToulminApp(root=root, project="demo", discussion=discussion)
        async with app.run_test(size=(60, 20)) as pilot:
            await pilot.pause()
            screen = app.screen
            transcript = screen.query_one("#transcript", DocumentView)._markdown
            assert "Session: resume" in transcript
            assert session_id[:12] in transcript
            await pilot.press("f3")
            summary = str(app.screen.query_one("#session-summary", Static).render())
            assert "Mode: resume" in summary
            assert "Reason: resume" in summary
            assert session_id in summary
            await pilot.press("escape")
            assert len(discussion.calls) == 1

    asyncio.run(asyncio.wait_for(scenario(), timeout=15))
