"""Interaction checks for the disposable wireframe, not production research behavior."""

import asyncio
import runpy
from pathlib import Path

import pytest

pytest.importorskip("textual")
from textual.widgets import Button, Select, Static, TextArea

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[2] / "prototypes/guided_workbench.py"))
GuidedWorkbench = MODULE["GuidedWorkbench"]


async def activate(app, pilot, key):
    button = app.query_one(f"#{key}", Button)
    button.focus()
    await pilot.press("enter")
    await pilot.pause()


async def start(app, pilot):
    await pilot.pause()
    for key in ("create", "initialize", "resume"):
        await activate(app, pilot, key)
    assert app.view == "Explore"


def assert_exploratory(app):
    assert not app.sample.statement
    assert not app.sample.reviewed
    assert not app.sample.issue
    assert "Stage: Explore" in str(app.query_one("#status", Static).render())
    assert not app.query("#advance-stage")


@pytest.mark.parametrize("size", [(120, 36), (80, 24), (60, 20)])
def test_walkthrough_and_resume_without_files(tmp_path, monkeypatch, size):
    monkeypatch.chdir(tmp_path)

    async def scenario():
        app = GuidedWorkbench()
        async with app.run_test(size=size) as pilot:
            await start(app, pilot)
            app.query_one("#editor", TextArea).load_text("Repeated queries are slow.\n中文 input.")
            await activate(app, pilot, "save-brief")
            assert app.view == "Explore"
            assert_exploratory(app)
            for key in ("hypotheses", "save-hypotheses", "choose-action", "check-data"):
                await activate(app, pilot, key)
                if key == "hypotheses" and size[0] < 80:
                    assert app.query_one("#selector", Select).value == "Explore"
            plan = app.query_one("#editor", TextArea)
            plan.load_text("Inspect a fixed trace; compare CPU work, I/O and lock waits.")
            plan.focus()
            await pilot.press("f2", "f2")
            assert app.query_one("#editor", TextArea).text.startswith("Inspect a fixed")
            if size[0] < 110:
                assert app.focused.id == "editor"
            for key in ("save-plan", "material", "interpret"):
                await activate(app, pilot, key)
                if key in {"material", "interpret"} and size[0] < 80:
                    assert app.query_one("#selector", Select).value == "Validate"
            app.query_one("#editor", TextArea).load_text(
                "CPU stacks suggest repeated work; one short trace needs confirmation."
            )
            await activate(app, pilot, "judge-lead")
            assert app.view == "Overview"
            assert app.sample.current_interpretation == "lead"
            assert_exploratory(app)
            await activate(app, pilot, "end-session")
            app.query_one("#editor", TextArea).load_text(
                "Repeat attribution on representative traces."
            )
            await activate(app, pilot, "save-handoff")
            assert app.view == "Reopen"
            assert "Repeat attribution" in app.page()[1]
            assert app.sample.plan and app.sample.reasoning
            await activate(app, pilot, "resume")
            assert app.view == "Actions"
            await pilot.press("ctrl+q")
        assert not list(tmp_path.iterdir())

    asyncio.run(scenario())


@pytest.mark.parametrize("choice", ["data", "papers", "experiment"])
def test_checks_are_available_before_brief_claim_or_review(choice):
    async def scenario():
        app = GuidedWorkbench()
        async with app.run_test(size=(120, 36)) as pilot:
            await start(app, pilot)
            await activate(app, pilot, "nav-validate")
            assert app.view == "Validate"
            await activate(app, pilot, "choose-action")
            assert {button.id for button in app.query("#actions Button")} == {
                "check-data",
                "check-papers",
                "check-experiment",
            }
            await activate(app, pilot, f"check-{choice}")
            assert app.sample.choice == choice
            assert app.query_one("#editor", TextArea).text
            await activate(app, pilot, "save-plan")
            assert app.sample.plan
            assert not app.sample.material_loaded
            assert not app.sample.current_interpretation
            await activate(app, pilot, "material")
            assert app.sample.material_loaded
            assert "FICTIONAL MATERIAL" in app.page()[1]
            assert app.sample.material in app.page()[1]
            assert not app.sample.brief
            assert_exploratory(app)

    asyncio.run(scenario())


def test_feedback_and_unsaved_edits_survive_navigation_without_fake_regeneration():
    async def scenario():
        app = GuidedWorkbench()
        async with app.run_test(size=(80, 24)) as pilot:
            await start(app, pilot)
            app.query_one("#editor", TextArea).load_text(
                "Reported observation, not a proven cause."
            )
            await activate(app, pilot, "hypotheses")
            draft = "H1: I/O dominates.\nH2: lock contention is plausible."
            app.query_one("#editor", TextArea).load_text(draft)
            await pilot.press("escape")
            await activate(app, pilot, "nav-explore")
            assert (
                app.query_one("#editor", TextArea).text
                == "Reported observation, not a proven cause."
            )
            await activate(app, pilot, "hypotheses")
            assert app.query_one("#editor", TextArea).text == draft
            await activate(app, pilot, "save-hypotheses")
            await activate(app, pilot, "feedback")
            feedback = "中文约束: inspect existing data; no budget for another experiment."
            app.query_one("#editor", TextArea).load_text(feedback)
            await pilot.press("escape")
            await activate(app, pilot, "nav-explore")
            for key in ("hypotheses", "feedback"):
                await activate(app, pilot, key)
            assert app.query_one("#editor", TextArea).text == feedback
            await activate(app, pilot, "save-feedback")
            assert app.view == "Hypotheses"
            assert app.sample.feedback == feedback
            assert app.sample.hypotheses == draft
            assert app.query_one("#editor", TextArea).text == draft
            assert feedback in app.page()[4]
            assert "not generated from your edits" in app.page()[1]
            assert_exploratory(app)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("fixture", "judgment", "destination"),
    [
        (0, "lead", "Actions"),
        (1, "redirect", "Hypotheses"),
        (2, "uncertain", "Actions"),
        (0, "redirect", "Hypotheses"),
    ],
)
def test_divergent_material_needs_researcher_interpretation(fixture, judgment, destination):
    async def scenario():
        app = GuidedWorkbench()
        async with app.run_test(size=(80, 24)) as pilot:
            await start(app, pilot)
            for key in ("choose-action", "check-data", "save-plan", "material"):
                await activate(app, pilot, key)
            for _ in range(fixture):
                await activate(app, pilot, "cycle-material")
            assert app.sample.material_index == fixture
            assert not app.sample.current_interpretation
            assert app.sample.recommendation[1] == "Material"
            await activate(app, pilot, "interpret")
            reason = f"My interpretation of fixture {fixture}: follow up, with limitations."
            app.query_one("#editor", TextArea).load_text(reason)
            await activate(app, pilot, f"judge-{judgment}")
            assert app.view == "Overview"
            assert app.sample.current_interpretation == judgment
            assert app.sample.reasoning == reason
            assert reason in app.page()[1]
            assert app.sample.recommendation[1] == destination
            assert_exploratory(app)
            # Changing material invalidates the conclusion until the researcher judges again.
            await activate(app, pilot, "nav-validate")
            await activate(app, pilot, "material")
            previous = app.sample.material
            await activate(app, pilot, "cycle-material")
            assert app.sample.material != previous
            assert not app.sample.current_interpretation
            assert app.sample.reasoning == reason
            assert app.sample.recommendation[1] == "Material"

    asyncio.run(scenario())


def test_blank_interpretation_reason_is_refused_for_every_outcome():
    async def scenario():
        app = GuidedWorkbench()
        async with app.run_test(size=(80, 24)) as pilot:
            await start(app, pilot)
            for key in ("choose-action", "check-experiment", "save-plan", "material", "interpret"):
                await activate(app, pilot, key)
            app.query_one("#editor", TextArea).load_text(" \n\t")
            for judgment in ("lead", "redirect", "uncertain"):
                await activate(app, pilot, f"judge-{judgment}")
                assert app.view == "Interpret"
                assert not app.sample.current_interpretation
                assert not app.sample.reasoning
                assert not app.sample.history
            assert_exploratory(app)

    asyncio.run(scenario())


def test_changed_plan_does_not_revalidate_old_interpretation_when_material_is_opened():
    async def scenario():
        app = GuidedWorkbench()
        async with app.run_test(size=(120, 36)) as pilot:
            await start(app, pilot)
            for key in ("choose-action", "check-data", "save-plan", "material", "interpret"):
                await activate(app, pilot, key)
            app.query_one("#editor", TextArea).load_text(
                "One trace suggests a lead, pending replication."
            )
            await activate(app, pilot, "judge-lead")
            material = app.sample.material
            assert app.sample.current_interpretation == "lead"
            await activate(app, pilot, "nav-validate")
            app.query_one("#editor", TextArea).load_text(
                "Inspect ten representative traces instead."
            )
            await activate(app, pilot, "save-plan")
            assert not app.sample.current_interpretation
            await activate(app, pilot, "material")
            assert app.sample.material == material
            assert not app.sample.current_interpretation
            assert app.sample.recommendation[1] == "Material"
            assert app.sample.history

    asyncio.run(scenario())


def test_new_check_clears_stale_handoff_but_preserves_prior_notes():
    async def scenario():
        app = GuidedWorkbench()
        async with app.run_test(size=(120, 36)) as pilot:
            await start(app, pilot)
            for key in ("choose-action", "check-data", "save-plan", "material", "interpret"):
                await activate(app, pilot, key)
            app.query_one("#editor", TextArea).load_text(
                "Existing traces are too short to attribute time."
            )
            await activate(app, pilot, "judge-uncertain")
            await activate(app, pilot, "end-session")
            app.query_one("#editor", TextArea).load_text("Old next step: inspect another trace.")
            await activate(app, pilot, "save-handoff")
            assert app.sample.handoff and app.sample.next_step
            for key in ("nav-validate", "material", "interpret"):
                await activate(app, pilot, key)
            app.query_one("#editor", TextArea).load_text(
                "Reconsidering: inspect I/O as an alternative."
            )
            await activate(app, pilot, "judge-redirect")
            assert not app.sample.handoff and not app.sample.next_step
            await activate(app, pilot, "end-session")
            app.query_one("#editor", TextArea).load_text("Old next step: inspect I/O traces.")
            await activate(app, pilot, "save-handoff")
            for key in ("choose-action", "check-papers"):
                await activate(app, pilot, key)
            assert app.sample.choice == "papers"
            assert not app.sample.plan and not app.sample.material_loaded
            assert not app.sample.current_interpretation
            assert not app.sample.handoff and not app.sample.next_step
            assert "Existing traces are too short" in "\n".join(app.sample.history)
            assert "Earlier Inspect existing data" in "\n".join(app.sample.history)
            await activate(app, pilot, "end-session")
            assert "Old next step" not in app.query_one("#editor", TextArea).text

    asyncio.run(scenario())


def test_review_is_optional_and_changed_brief_marks_its_input_stale():
    async def scenario():
        app = GuidedWorkbench()
        async with app.run_test(size=(80, 24)) as pilot:
            await start(app, pilot)
            await activate(app, pilot, "save-brief")
            assert app.view == "Explore"
            assert_exploratory(app)
            for key in ("nav-review", "statement", "run-review"):
                await activate(app, pilot, key)
            assert app.view == "Resolve"
            assert app.sample.reviewed and not app.sample.issue
            await activate(app, pilot, "overview")
            assert "suggestion needs" in app.attention()
            for key in (
                "resume",
                "record",
                "validate",
                "choose-action",
                "check-experiment",
                "save-plan",
            ):
                await activate(app, pilot, key)
            assert app.sample.issue
            await activate(app, pilot, "nav-explore")
            app.query_one("#editor", TextArea).load_text("Changed workload.")
            await pilot.press("escape")
            await activate(app, pilot, "nav-explore")
            assert app.query_one("#editor", TextArea).text == "Changed workload."
            assert not app.sample.stale
            await activate(app, pilot, "save-brief")
            assert app.view == "Explore" and app.sample.stale
            await activate(app, pilot, "nav-review")
            assert "STALE INPUT" in app.page()[1]
            await pilot.press("escape")
            await activate(app, pilot, "readiness")
            assert "MISSING" in app.page()[1]
            assert "Stage: Explore" in str(app.query_one("#status", Static).render())
            assert not app.query("#advance-stage")

    asyncio.run(scenario())


@pytest.mark.parametrize("size", [(120, 36), (80, 24), (60, 20)])
def test_primary_actions_are_visible_and_clickable(size):
    async def scenario():
        app = GuidedWorkbench()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            route = (
                "create",
                "initialize",
                "resume",
                "save-brief",
                "hypotheses",
                "feedback",
                "save-feedback",
                "save-hypotheses",
                "choose-action",
                "check-data",
                "save-plan",
                "material",
                "cycle-material",
                "interpret",
                "judge-uncertain",
                "end-session",
                "save-handoff",
            )
            for key in route:
                if key in {"save-feedback", "judge-uncertain"}:
                    app.query_one("#editor", TextArea).load_text(
                        "Need representative material first."
                    )
                # Include alternative actions that this path does not take.
                for button in app.query("#actions Button"):
                    region = button.region
                    assert region.width > 0 and region.height > 0, button.id
                    assert region.x >= 0 and region.right <= size[0], button.id
                    assert region.y >= 0 and region.bottom <= size[1], button.id
                assert await pilot.click(f"#{key}"), key
                await pilot.pause()
            assert app.view == "Reopen"
            assert_exploratory(app)

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
            for key in ("hypotheses", "save-hypotheses", "project-home", "open"):
                await activate(app, pilot, key)
            assert app.sample.hypotheses and app.sample.handoff
            for key in ("project-home", "create", "initialize"):
                await activate(app, pilot, key)
            assert not app.sample.handoff and not app.sample.brief and not app.sample.hypotheses
            assert not app.sample.feedback and not app.sample.choice and not app.sample.history

    asyncio.run(scenario())
