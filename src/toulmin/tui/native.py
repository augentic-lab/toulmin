"""Compact file-backed research board beside an unwrapped native CLI."""

from __future__ import annotations

import argparse
import re
from difflib import unified_diff
from pathlib import Path
from unicodedata import category

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Static

from toulmin.protocols.native import NativeSession, apply_native, load_native

_TERMINAL_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


def display_text(value: str) -> str:
    """Render research files as literal text without terminal or Unicode controls."""
    value = _TERMINAL_ESCAPE.sub("", value)
    return "".join(char for char in value if char in "\n\t" or category(char) not in {"Cc", "Cf"})


def can_apply(view: NativeSession) -> bool:
    return (
        view.status == "closed"
        and view.output_status == "completed"
        and view.proposal_status == "pending"
        and view.application_status in {"none", "applying"}
        and bool(view.draft)
    )


class ConfirmNativeBrief(ModalScreen[bool]):
    """Show the exact captured draft and diff before researcher confirmation."""

    DEFAULT_CSS = """
    ConfirmNativeBrief { align: center middle; background: $background 85%; }
    #confirmation { width: 100%; height: 100%; border: thick $warning; padding: 0 1; }
    #confirmation Static { height: auto; }
    #confirmation VerticalScroll { height: 1fr; }
    #confirmation Horizontal { height: auto; }
    #confirmation Button { width: 1fr; min-width: 8; }
    """
    BINDINGS = [("escape", "cancel", "Cancel"), ("d", "toggle_preview", "Draft / diff")]

    def __init__(self, view: NativeSession, *, allow_apply: bool) -> None:
        super().__init__()
        self.view = view
        self.allow_apply = allow_apply
        self.showing_diff = False
        self.diff = (
            "".join(
                unified_diff(
                    view.brief.splitlines(keepends=True),
                    (view.draft or "").splitlines(keepends=True),
                    fromfile="Saved Brief now",
                    tofile="Proposed Brief",
                )
            )
            or "(No changes from the saved Brief.)"
        )

    def compose(self) -> ComposeResult:
        with Vertical(id="confirmation"):
            yield Static(
                "Review proposed Brief. Confirming replaces brief.md; stage stays unchanged."
                if self.allow_apply
                else "Read-only draft preview. Escape returns to the board.",
                markup=False,
            )
            yield Button("Show changes", id="toggle-preview", compact=True)
            with VerticalScroll(id="preview-scroll"):
                yield Static(
                    display_text(self.view.draft or "(No draft.)"),
                    markup=False,
                    id="confirm-preview",
                )
            with Horizontal():
                yield Button("Cancel", id="cancel", compact=True)
                yield Button(
                    "Apply to Brief",
                    id="confirm-apply",
                    variant="warning",
                    disabled=not self.allow_apply,
                    compact=True,
                )

    def action_toggle_preview(self) -> None:
        self.showing_diff = not self.showing_diff
        value = self.diff if self.showing_diff else self.view.draft or "(No draft.)"
        self.query_one("#confirm-preview", Static).update(display_text(value))
        self.query_one("#toggle-preview", Button).label = (
            "Show draft" if self.showing_diff else "Show changes"
        )
        self.query_one("#preview-scroll", VerticalScroll).scroll_home(animate=False)

    @on(Button.Pressed)
    def choose(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "toggle-preview":
            self.action_toggle_preview()
        elif event.button.id == "cancel":
            self.dismiss(False)
        elif event.button.id == "confirm-apply" and self.allow_apply:
            self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class NativeBoard(App[None]):
    """Read project/session files; only explicit confirmation can publish a Brief."""

    CSS = """
    Screen { layout: vertical; }
    #stage, #pane-help, #next-action, #message { height: auto; padding: 0 1; }
    #stage { text-style: bold; color: $accent; }
    #files { height: 1fr; }
    #files Static { height: auto; padding: 0 1 1 1; }
    .heading { text-style: bold; }
    #draft-heading { color: $warning; }
    #actions { height: auto; }
    #actions Button { width: 1fr; min-width: 8; }
    """
    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("p", "preview", "Preview"),
        ("a", "apply", "Apply"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, root: Path, project: str, session: str, actor: str) -> None:
        super().__init__()
        self.root = root
        self.project = project
        self.session = session
        self.actor = actor
        self.view: NativeSession | None = None
        self._refresh_error = False

    def compose(self) -> ComposeResult:
        yield Static("Loading saved research state…", id="stage", markup=False)
        yield Static("Ctrl+b o: switch · z: zoom\nBoard q: close session", id="pane-help")
        yield Static("", id="next-action", markup=False)
        with VerticalScroll(id="files"):
            for name, heading in (
                ("goal", "Research goal"),
                ("draft", "Live draft — UNCONFIRMED"),
                ("brief", "Saved Brief"),
                ("provenance", "Session / Run provenance"),
            ):
                yield Static(heading, id=f"{name}-heading", classes="heading")
                yield Static("", id=name, markup=False)
        with Horizontal(id="actions"):
            yield Button("Refresh", id="refresh", compact=True)
            yield Button("Preview", id="preview", compact=True, disabled=True)
            yield Button("Apply…", id="apply", variant="warning", compact=True, disabled=True)
        yield Static("", id="message", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.action_refresh()
        self.set_interval(0.75, self.action_refresh)

    def action_refresh(self) -> None:
        try:
            view = load_native(self.root, self.project, self.session)
        except (OSError, ValueError) as error:
            self.view = None
            self._refresh_error = True
            self.query_one("#apply", Button).disabled = True
            self.query_one("#preview", Button).disabled = True
            self.query_one("#message", Static).update(
                display_text(f"Refresh refused; displayed files may be stale: {error}")
            )
            return
        self.view = view
        if self._refresh_error:
            self.query_one("#message", Static).update("")
            self._refresh_error = False
        self.query_one("#stage", Static).update(
            display_text(f"{view.project} · Research stage: {view.stage}")
        )
        for name, text in (
            ("goal", view.goal or "(No saved goal.)"),
            ("draft", view.draft or "(Request draft.md in the native CLI when ready.)"),
            ("brief", view.brief or "(No saved Brief.)"),
            ("provenance", self.provenance(view)),
        ):
            self.query_one(f"#{name}", Static).update(display_text(text))
        self.query_one("#draft-heading", Static).update(
            "Applied draft — archived"
            if view.proposal_status == "applied"
            else "Live draft — UNCONFIRMED"
            if view.status == "started"
            else "Archived draft — UNCONFIRMED"
        )
        self.query_one("#apply", Button).disabled = not can_apply(view)
        self.query_one("#preview", Button).disabled = not view.draft
        self.query_one("#next-action", Static).update(self.next_action(view))

    @staticmethod
    def provenance(view: NativeSession) -> str:
        state = "interrupted" if view.interrupted else view.output_status
        text = (
            f"{view.agent} · {state}\nSession: {view.id}\n"
            f"Run: {view.run or '(not archived yet)'}\n"
            f"Model: {view.model or '(not reported)'}\n"
            f"Proposal: {view.proposal_status}\nArchive: {view.archive}\n"
            "Native conversation: not captured"
        )
        if view.session_id:
            text += f"\nNative session: {view.session_id}"
        if view.exit_code is not None:
            text += f"\nExit code: {view.exit_code}"
        if view.failure:
            text += f"\nReason: {view.failure}"
        return text

    @staticmethod
    def next_action(view: NativeSession) -> str:
        if view.status == "started":
            return "Discuss in the native CLI; use /exit to archive before Apply."
        if view.proposal_status == "applied":
            return "Saved Brief updated. Draft and Run remain archived."
        if can_apply(view):
            return "Review draft and changes; Apply to Brief requires confirmation."
        if view.output_status == "failed":
            return "Session failed or interrupted; retained draft is preview only."
        return "No applicable Brief draft. Preview retained material or close the board."

    def action_preview(self) -> None:
        if self.view and can_apply(self.view):
            self.action_apply()
        elif self.view and self.view.draft and not isinstance(self.screen, ConfirmNativeBrief):
            self.push_screen(ConfirmNativeBrief(self.view, allow_apply=False))

    def action_apply(self) -> None:
        view = self.view
        if view is None or not can_apply(view) or isinstance(self.screen, ConfirmNativeBrief):
            return
        displayed = view.draft
        assert displayed is not None

        def confirmed(accepted: bool | None) -> None:
            if not accepted:
                return
            try:
                apply_native(self.root, self.project, self.session, displayed, self.actor)
                message = "Applied displayed draft to Brief; Run provenance preserved."
            except (OSError, ValueError) as error:
                message = f"Apply refused: {error}"
            self.action_refresh()
            self.query_one("#message", Static).update(display_text(message))

        self.push_screen(ConfirmNativeBrief(view, allow_apply=True), confirmed)

    @on(Button.Pressed)
    def pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh":
            self.action_refresh()
        elif event.button.id == "preview":
            self.action_preview()
        elif event.button.id == "apply":
            self.action_apply()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--actor", required=True)
    arguments = parser.parse_args()
    NativeBoard(arguments.root, arguments.project, arguments.session, arguments.actor).run()


if __name__ == "__main__":
    main()
