"""Interaction checks for the disposable wireframe, not production research behavior."""

import asyncio
import runpy
from pathlib import Path

import pytest

pytest.importorskip("textual")
from textual.widgets import Button, Static, TextArea

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[2] / "prototypes/guided_workbench.py"))
GuidedWorkbench = MODULE["GuidedWorkbench"]


async def activate(app, pilot, key):
    button = app.query_one(f"#{key}", Button)
    button.focus()
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.parametrize("size", [(120, 36), (80, 24), (60, 20)])
def test_walkthrough_and_resume_without_files(tmp_path, monkeypatch, size):
    monkeypatch.chdir(tmp_path)

    async def scenario():
        app = GuidedWorkbench()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            for key in ("create", "initialize", "resume"):
                await activate(app, pilot, key)
            assert app.view == "Explore"
            app.query_one("#editor", TextArea).load_text("A fair cache comparison.\n中文 input.")
            for key in ("save-brief", "statement", "run-review"):
                await activate(app, pilot, key)
            assert app.view == "Resolve"
            assert app.sample.reviewed and not app.sample.issue
            await activate(app, pilot, "overview")  # Leaving a suggestion pending is allowed.
            assert "suggestion needs" in app.attention()
            for key in ("resume", "record", "validate"):
                await activate(app, pilot, key)
            assert app.sample.issue
            plan = app.query_one("#editor", TextArea)
            plan.load_text("Use a fixed trace; measure hit rate and p95 variability.")
            # Context switching retains both unsaved edits and the focused editor.
            plan.focus()
            await pilot.press("f2", "f2")
            assert app.query_one("#editor", TextArea).text.startswith("Use a fixed")
            if size[0] < 110:
                assert app.focused.id == "editor"
            for key in ("save-plan", "end-session"):
                await activate(app, pilot, key)
            app.query_one("#editor", TextArea).load_text("Run the controlled cache comparison.")
            await activate(app, pilot, "save-handoff")
            assert app.view == "Reopen"
            assert "Run the controlled" in app.page()[1]
            assert app.sample.issue and app.sample.plan
            assert "Stage: Explore" in str(app.query_one("#status", Static).render())
            await activate(app, pilot, "resume")
            assert app.view == "Validate"
            await pilot.press("ctrl+q")
        assert not list(tmp_path.iterdir())

    asyncio.run(scenario())


def test_navigation_retains_draft_and_marks_review_stale():
    async def scenario():
        app = GuidedWorkbench()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            for key in ("create", "initialize", "resume", "save-brief", "statement", "run-review"):
                await activate(app, pilot, key)
            await activate(app, pilot, "nav-explore")
            app.query_one("#editor", TextArea).load_text("Changed workload.")
            await pilot.press("escape")
            await activate(app, pilot, "nav-explore")
            assert app.query_one("#editor", TextArea).text == "Changed workload."
            assert not app.sample.stale  # Working text is not the published input.
            await activate(app, pilot, "save-brief")
            assert app.sample.stale and "STALE INPUT" in app.page()[1]
            await pilot.press("escape")
            await activate(app, pilot, "readiness")
            assert "MISSING" in app.page()[1]
            assert not app.query("#advance-stage")

    asyncio.run(scenario())


@pytest.mark.parametrize("size", [(120, 36), (80, 24), (60, 20)])
def test_primary_actions_are_visible_and_clickable(size):
    async def scenario():
        app = GuidedWorkbench()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            for key in (
                "create",
                "initialize",
                "resume",
                "save-brief",
                "statement",
                "run-review",
                "record",
                "validate",
                "save-plan",
                "end-session",
                "save-handoff",
            ):
                button = app.query_one(f"#{key}", Button)
                region = button.region
                assert region.width > 0 and region.height > 0
                assert region.x >= 0 and region.right <= size[0]
                assert region.y >= 0 and region.bottom <= size[1]
                assert await pilot.click(f"#{key}")
                await pilot.pause()
            assert app.view == "Reopen"

    asyncio.run(scenario())


def test_early_handoff_returns_to_explore_and_restart_clears_sample():
    async def scenario():
        app = GuidedWorkbench()
        async with app.run_test(size=(60, 20)) as pilot:
            await pilot.pause()
            for key in ("create", "initialize", "end-session", "save-handoff", "resume"):
                await activate(app, pilot, key)
            assert app.view == "Explore"
            editor = app.query_one("#editor", TextArea)
            editor.focus()
            await pilot.pause()
            await pilot.press("x")
            assert editor.text.startswith("x")
            assert editor.region.intersection(app.query_one("#content").content_region).height >= 3
            for key in ("project-home", "open"):
                await activate(app, pilot, key)
            assert app.sample.handoff
            for key in ("project-home", "create", "initialize"):
                await activate(app, pilot, key)
            assert not app.sample.handoff and not app.sample.brief

    asyncio.run(scenario())
