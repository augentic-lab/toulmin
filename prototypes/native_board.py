"""Disposable file-backed panel beside an unwrapped native CLI; no production imports."""

import argparse
import json
import os
import stat
import tempfile
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Static

MAX_BYTES = 256 * 1024


def read_file(workspace: Path, name: str) -> bytes | None:
    """Read bounded ordinary files without following a final symlink or blocking on a FIFO."""
    directory = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise ValueError(f"{name}: expected a regular file at most 256 KiB")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError(f"{name}: exceeds 256 KiB")
            data.decode("utf-8")
            return data
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def accept_draft(workspace: Path, displayed: bytes) -> None:
    """Publish the displayed bytes atomically, never replacing an existing acceptance."""
    if not displayed or len(displayed) > MAX_BYTES:
        raise ValueError("The displayed draft is empty or oversized")
    displayed.decode("utf-8")
    if read_file(workspace, "draft.md") != displayed:
        raise ValueError("Draft changed; refresh and review it before accepting")
    if read_file(workspace, "accepted-brief.md") is not None:
        raise ValueError("Accepted Brief already exists; it will not be overwritten")
    fd, temporary = tempfile.mkstemp(prefix=".accepted-", dir=workspace)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(displayed)
            stream.flush()
            os.fsync(stream.fileno())
        # A concurrent creation of the target fails instead of being overwritten.
        os.link(temporary, workspace / "accepted-brief.md", follow_symlinks=False)
    finally:
        os.unlink(temporary)


class ConfirmAcceptance(ModalScreen[bool]):
    DEFAULT_CSS = """
    ConfirmAcceptance { align: center middle; background: $background 80%; }
    #confirmation { width: 90%; height: 80%; border: thick $warning; padding: 1; }
    #confirmation VerticalScroll { height: 1fr; }
    #confirmation Horizontal { height: auto; }
    #confirmation Button { width: 1fr; min-width: 8; }
    """
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, draft: bytes) -> None:
        super().__init__()
        self.draft = draft

    def compose(self) -> ComposeResult:
        with Vertical(id="confirmation"):
            yield Static("Accept this displayed draft as the prototype Brief?")
            with VerticalScroll():
                yield Static(self.draft.decode("utf-8"), markup=False, id="confirm-preview")
            with Horizontal():
                yield Button("Cancel", id="cancel")
                yield Button("Confirm", variant="warning", id="confirm")

    @on(Button.Pressed)
    def choose(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")

    def action_cancel(self) -> None:
        self.dismiss(False)


class NativeBoard(App[None]):
    CSS = """
    Screen { layout: vertical; }
    #stage, #next-action, #message, #pane-help { height: auto; padding: 0 1; }
    #stage { text-style: bold; color: $accent; }
    #files { height: 1fr; }
    #files Static { padding: 0 1 1 1; }
    .heading { text-style: bold; }
    #draft-heading { color: $warning; }
    #accepted-heading { color: $success; }
    #actions { height: auto; }
    #actions Button { width: 1fr; min-width: 8; }
    """
    BINDINGS = [("r", "refresh", "Refresh"), ("a", "accept", "Accept"), ("q", "quit", "Quit")]

    def __init__(self, workspace: Path) -> None:
        super().__init__()
        self.workspace = workspace.absolute()
        self.displayed_draft: bytes | None = None

    def compose(self) -> ComposeResult:
        yield Static("Stage: Explore | Prototype", id="stage")
        yield Static("Ctrl+b o: switch | Ctrl+b z: zoom\nBoard q: quit both panes", id="pane-help")
        yield Static("Next action: discuss in the adjacent native CLI", id="next-action")
        with VerticalScroll(id="files"):
            for name, heading in (
                ("context", "Research question"),
                ("draft", "Draft — UNCONFIRMED"),
                ("accepted", "Accepted prototype Brief — separate from draft"),
                ("native", "Native CLI status"),
            ):
                yield Static(heading, id=f"{name}-heading", classes="heading")
                yield Static("", id=name, markup=False)
        with Horizontal(id="actions"):
            yield Button("Refresh", id="refresh")
            yield Button("Accept draft…", id="accept", variant="warning")
            yield Button("Quit", id="quit")
        yield Static("Plain prototype files only; no formal research objects.", id="message")
        yield Footer()

    def on_mount(self) -> None:
        self.action_refresh()
        self.set_interval(2, self.action_refresh)

    def action_refresh(self) -> None:
        draft = None
        accepted_exists = os.path.lexists(self.workspace / "accepted-brief.md")
        for name, filename in (
            ("context", "context.md"),
            ("draft", "draft.md"),
            ("accepted", "accepted-brief.md"),
            ("native", "native-exit.json"),
        ):
            try:
                data = read_file(self.workspace, filename)
                value = data.decode("utf-8") if data is not None else "(not present)"
                if (
                    name == "context"
                    and value.startswith(
                        ("# Disposable research trial\n\n## Question\n", "## Question\n")
                    )
                    and "\n## Collaboration\n" in value
                ):
                    value = (
                        value.split("## Question\n", 1)[1]
                        .split("\n## Collaboration\n", 1)[0]
                        .strip()
                    )
                if name == "native" and data is not None:
                    status = json.loads(data)
                    value = f"{status['agent']} exited with code {status['exit_code']}"
                if name == "draft":
                    draft = data
            except (OSError, ValueError, KeyError, TypeError) as error:
                value = f"Read refused: {error}"
            self.query_one(f"#{name}", Static).update(value)
        self.displayed_draft = draft
        self.query_one("#accept", Button).disabled = not draft or accepted_exists
        self.query_one("#next-action", Static).update(
            "Next action: continue native discussion or quit; acceptance is closed"
            if accepted_exists
            else (
                "Next action: review the unconfirmed draft; Accept requires confirmation"
                if draft
                else "Next action: discuss in the adjacent native CLI; request draft.md when ready"
            )
        )

    def action_accept(self) -> None:
        displayed = self.displayed_draft
        if (
            not displayed
            or self.query_one("#accept", Button).disabled
            or isinstance(self.screen, ConfirmAcceptance)
        ):
            return

        def confirmed(accepted: bool | None) -> None:
            if not accepted:
                return
            try:
                accept_draft(self.workspace, displayed)
                message = "Accepted displayed draft into accepted-brief.md (prototype only)."
            except (OSError, ValueError) as error:
                message = f"Acceptance refused: {error}"
            self.action_refresh()
            self.query_one("#message", Static).update(message)

        self.push_screen(ConfirmAcceptance(displayed), confirmed)

    @on(Button.Pressed)
    def pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh":
            self.action_refresh()
        elif event.button.id == "accept":
            self.action_accept()
        elif event.button.id == "quit":
            self.exit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    arguments = parser.parse_args()
    NativeBoard(arguments.workspace).run()


if __name__ == "__main__":
    main()
