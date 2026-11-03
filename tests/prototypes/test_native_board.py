"""Headless checks for the disposable native split panel; no provider CLI calls."""

import asyncio
import os
import runpy
from pathlib import Path

import pytest

pytest.importorskip("textual")
from textual.widgets import Button, Static

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[2] / "prototypes/native_board.py"))
NativeBoard = MODULE["NativeBoard"]
read_file = MODULE["read_file"]
accept_draft = MODULE["accept_draft"]


def visible(app, selector):
    return str(app.screen.query_one(selector, Static).render())


async def activate(app, pilot, selector):
    app.screen.query_one(selector, Button).focus()
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.parametrize("size", [(36, 36), (40, 24), (80, 24)])
def test_display_refresh_cancel_confirm_and_quit(tmp_path, size):
    (tmp_path / "context.md").write_text("Question: where is query time spent?\n")
    draft = b"Unconfirmed research proposal.\n"
    (tmp_path / "draft.md").write_bytes(draft)

    async def scenario():
        app = NativeBoard(tmp_path)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert "Stage: Explore" in visible(app, "#stage")
            assert "Question: where" in visible(app, "#context")
            assert "UNCONFIRMED" in visible(app, "#draft-heading")
            assert "Unconfirmed research" in visible(app, "#draft")
            assert "not present" in visible(app, "#accepted")
            for selector in ("#refresh", "#accept", "#quit"):
                region = app.query_one(selector).region
                assert 0 <= region.x and region.right <= size[0]
                assert 0 <= region.y and region.bottom <= size[1]
            await pilot.press("tab")
            assert app.focused is not None
            await pilot.press("a")
            assert "Unconfirmed research" in visible(app, "#confirm-preview")
            for selector in ("#confirm", "#cancel"):
                region = app.screen.query_one(selector).region
                assert 0 <= region.x and region.right <= size[0]
                assert 0 <= region.y and region.bottom <= size[1]
            assert not (tmp_path / "accepted-brief.md").exists()
            await pilot.press("escape")
            assert not (tmp_path / "accepted-brief.md").exists()
            await activate(app, pilot, "#accept")
            await activate(app, pilot, "#confirm")
            assert (tmp_path / "accepted-brief.md").read_bytes() == draft
            assert "Unconfirmed research" in visible(app, "#accepted")
            assert "prototype only" in visible(app, "#message")
            assert "continue native discussion" in visible(app, "#next-action")
            assert app.query_one("#accept", Button).disabled
            await pilot.press("a")
            assert app.screen.id == "_default"
            (tmp_path / "native-exit.json").write_text('{"agent":"demo","exit_code":3}')
            await pilot.press("r")
            assert "demo exited with code 3" in visible(app, "#native")
            await pilot.press("q")
        assert not app.is_running

    asyncio.run(scenario())


@pytest.mark.parametrize("conflict", ["draft", "accepted", "draft-symlink", "accepted-symlink"])
def test_confirm_refuses_stale_or_external_change(tmp_path, conflict):
    original = b"Displayed draft\n"
    (tmp_path / "draft.md").write_bytes(original)
    outside = tmp_path / "outside.md"
    outside.write_text("External content\n")

    async def scenario():
        app = NativeBoard(tmp_path)
        async with app.run_test(size=(40, 30)) as pilot:
            await pilot.pause()
            await pilot.press("a")
            if conflict.endswith("symlink"):
                target = tmp_path / (
                    "draft.md" if conflict == "draft-symlink" else "accepted-brief.md"
                )
                target.unlink(missing_ok=True)
                target.symlink_to(outside)
            else:
                target = tmp_path / ("draft.md" if conflict == "draft" else "accepted-brief.md")
                target.write_text("External update\n")
            await activate(app, pilot, "#confirm")
            assert "Acceptance refused" in visible(app, "#message")
            assert outside.read_text() == "External content\n"
            if conflict.startswith("accepted"):
                assert target.read_text() in {"External update\n", "External content\n"}
            else:
                assert not (tmp_path / "accepted-brief.md").exists()
            assert not list(tmp_path.glob(".accepted-*"))

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo", "oversized", "encoding"])
def test_bad_draft_is_visibly_refused(tmp_path, kind):
    draft = tmp_path / "draft.md"
    if kind == "symlink":
        outside = tmp_path / "outside"
        outside.write_text("Never follow this")
        draft.symlink_to(outside)
    elif kind == "directory":
        draft.mkdir()
    elif kind == "fifo":
        os.mkfifo(draft)
    else:
        draft.write_bytes(b"x" * (256 * 1024 + 1) if kind == "oversized" else b"\xff")

    async def scenario():
        app = NativeBoard(tmp_path)
        async with app.run_test(size=(40, 24)) as pilot:
            await pilot.pause()
            assert "Read refused" in visible(app, "#draft")
            assert app.query_one("#accept", Button).disabled
            await pilot.press("a")
            assert not (tmp_path / "accepted-brief.md").exists()

    asyncio.run(scenario())


def test_acceptance_rejects_symlink_workspace_and_oversized_payload(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    link = tmp_path / "link"
    link.symlink_to(workspace, target_is_directory=True)
    with pytest.raises(OSError):
        read_file(link, "draft.md")
    with pytest.raises(ValueError, match="oversized"):
        accept_draft(workspace, b"x" * (256 * 1024 + 1))
    assert not list(workspace.iterdir())


def test_atomic_publication_preserves_a_concurrent_acceptance(tmp_path, monkeypatch):
    draft = b"Displayed draft\n"
    (tmp_path / "draft.md").write_bytes(draft)
    link = os.link

    def concurrent_creation(source, target, **kwargs):
        Path(target).write_text("Concurrent acceptance\n")
        return link(source, target, **kwargs)

    monkeypatch.setattr(os, "link", concurrent_creation)
    with pytest.raises(FileExistsError):
        accept_draft(tmp_path, draft)
    assert (tmp_path / "accepted-brief.md").read_text() == "Concurrent acceptance\n"
    assert not list(tmp_path.glob(".accepted-*"))


@pytest.mark.parametrize("generated", [True, False])
def test_question_display_hides_only_generated_collaboration_instructions(tmp_path, generated):
    question = "Where is repeated-query time spent?"
    context = (
        "# Disposable research trial\n\n## Question\n"
        + question
        + "\n\n## Collaboration\n"
        + "Long native tool instructions.\n" * 50
        if generated
        else "Custom context, retained in full.\nSecond line.\n"
    )
    (tmp_path / "context.md").write_text(context)

    async def scenario():
        app = NativeBoard(tmp_path)
        async with app.run_test(size=(36, 24)) as pilot:
            await pilot.pause()
            assert visible(app, "#context") == (question if generated else context)
            assert "Research question" in visible(app, "#context-heading")
            assert (tmp_path / "context.md").read_text() == context
            if generated:
                draft = app.query_one("#draft-heading").region
                assert 0 <= draft.y and draft.bottom <= 24

    asyncio.run(scenario())
