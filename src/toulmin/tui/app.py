"""Conversation-led workbench with file-backed research state and explicit application."""

from __future__ import annotations

import re
from difflib import unified_diff
from hashlib import sha256
from os import environ
from pathlib import Path
from typing import cast

from rich.markdown import Markdown as RichMarkdown
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Footer,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    Static,
    TextArea,
)

from toulmin.application.discussion import DiscussionService
from toulmin.application.workspace import ProjectView, WorkspaceService
from toulmin.protocols.discussion import Turn

STEPS = ("Setup", "Explore", "Brief", "Key Claims", "Review", "Resolve", "Handoff")
VIEW_LABELS = {"Setup": "Project", "Explore": "Discussion", "Key Claims": "Claims"}
_TERMINAL_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


def safe_text(value: str) -> str:
    """Keep research text readable without interpreting terminal control sequences."""
    value = _TERMINAL_ESCAPE.sub("", value)
    return "".join(char for char in value if char in "\n\t" or ord(char) >= 32)


def controller(screen: Screen[None]) -> ToulminApp:
    return cast(ToulminApp, screen.app)


class DocumentView(Static):
    """Render file-backed Markdown synchronously without a background executor."""

    def __init__(self, markdown: str = "", *, id: str | None = None) -> None:
        self._markdown = markdown
        super().__init__(RichMarkdown(markdown), id=id)

    def show_document(self, markdown: str) -> None:
        self._markdown = markdown
        super().update(RichMarkdown(markdown))


class ShellScreen(Screen[None]):
    """Shared branding and Escape behavior for full-screen views."""

    BINDINGS = [Binding("escape", "back", "Back")]

    def brand(self, subtitle: str) -> Static:
        mark = "[]" if controller(self).ascii_borders else "▟"
        return Static(f"{mark} TOULMIN  /  {subtitle}", id="brand", markup=False)

    def action_back(self) -> None:
        if len(self.app.screen_stack) > 2:
            self.app.pop_screen()


class HomeScreen(ShellScreen):
    def compose(self) -> ComposeResult:
        yield self.brand("RESEARCH WORKBENCH")
        with VerticalScroll(id="home-scroll"):
            with Vertical(id="home-card"):
                wordmark = (
                    "+-+\n| |  TOULMIN\n+-+"
                    if controller(self).ascii_borders
                    else "▗▄▖\n▐ ▌  TOULMIN\n▝▀▘"
                )
                yield Static(wordmark, id="wordmark", markup=False)
                yield Static(
                    "A place to shape a question.\nA record of why you believe it.", id="tagline"
                )
                yield Button("New Project", id="new-project", variant="primary")
                yield Button("Open Project", id="open-project")
                yield Static("Explore together. Save changes when you are ready.", classes="muted")
        yield Static(str(controller(self).root), id="home-root", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#new-project", Button).focus()

    @on(Button.Pressed, "#new-project")
    def new_project(self) -> None:
        self.app.push_screen(SetupScreen(controller(self).root))

    @on(Button.Pressed, "#open-project")
    def open_project(self) -> None:
        self.app.push_screen(OpenScreen(controller(self).root))


class ImportPreview(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, path: Path, content: str) -> None:
        super().__init__()
        self.source_path = path
        self.content = content

    def compose(self) -> ComposeResult:
        with Vertical(id="preview-dialog", classes="dialog"):
            yield Label("IMPORT PREVIEW", classes="dialog-title")
            yield Static(str(self.source_path), markup=False, classes="muted")
            yield Static("Edit the motivation below. The original source bytes will be archived.")
            yield TextArea(self.content, id="import-preview", tab_behavior="focus")
            with Horizontal(classes="actions"):
                yield Button("Use as Motivation", id="use-import", variant="primary")
                yield Button("Cancel", id="cancel-import")

    @on(Button.Pressed, "#use-import")
    def accept(self) -> None:
        self.dismiss(self.query_one("#import-preview", TextArea).text)

    @on(Button.Pressed, "#cancel-import")
    def action_cancel(self) -> None:
        self.dismiss(None)


class FileItem(ListItem):
    def __init__(self, path: Path, label: str) -> None:
        super().__init__(Label(label, markup=False))
        self.path = path


class FileBrowser(ModalScreen[Path | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, directory: Path) -> None:
        super().__init__()
        self.directory = directory

    def compose(self) -> ComposeResult:
        with Vertical(id="browser-dialog", classes="dialog"):
            yield Label("CHOOSE A MARKDOWN OR TEXT FILE", classes="dialog-title")
            yield Input(str(self.directory), id="browser-root", placeholder="Directory")
            yield ListView(id="file-tree")
            yield Static("Arrows navigate · Enter opens · Escape cancels", classes="muted")
            yield Button("Cancel", id="cancel-browser")

    @on(Input.Submitted, "#browser-root")
    async def directory_changed(self, event: Input.Submitted) -> None:
        path = Path(event.value).expanduser()
        if path.is_dir():
            self.directory = path
            await self.load_directory()
        else:
            self.notify("Choose an existing directory.", severity="error")

    async def on_mount(self) -> None:
        await self.load_directory()
        self.query_one("#file-tree", ListView).focus()

    async def load_directory(self) -> None:
        listing = self.query_one("#file-tree", ListView)
        try:
            entries = sorted(self.directory.iterdir(), key=lambda path: path.name.casefold())
            items = [FileItem(self.directory.parent, "../")]
            for entry in entries:
                if entry.is_dir():
                    items.append(FileItem(entry, safe_text(entry.name) + "/"))
                elif entry.is_file() and entry.suffix.lower() in {".md", ".txt"}:
                    items.append(FileItem(entry, safe_text(entry.name)))
        except OSError as exc:
            self.notify(safe_text(str(exc)), severity="error")
            return
        await listing.clear()
        await listing.extend(items)
        listing.index = 0
        self.query_one("#browser-root", Input).value = str(self.directory)

    @on(ListView.Selected, "#file-tree")
    async def file_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, FileItem):
            return
        if event.item.path.is_dir():
            self.directory = event.item.path
            await self.load_directory()
        else:
            self.dismiss(event.item.path)

    @on(Button.Pressed, "#cancel-browser")
    def action_cancel(self) -> None:
        self.dismiss(None)


class SetupScreen(ShellScreen):
    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root
        self.source_path: Path | None = None
        self.source_digest: str | None = None

    def compose(self) -> ComposeResult:
        yield self.brand("NEW PROJECT")
        with VerticalScroll(id="setup-form"):
            yield Label("Start with a question", classes="page-title")
            yield Static(
                "Your words are saved to the project. No model will be called.", classes="muted"
            )
            yield Label("Workbench location")
            yield Input(str(self.root), id="setup-root", placeholder="/path/to/workbench")
            yield Label("Project slug")
            yield Input(id="setup-slug", placeholder="e.g. tail-latency")
            yield Label("Goal · required, keep it short (the project charter has a 40-line limit)")
            yield TextArea(
                id="setup-goal",
                placeholder="What do you want to understand or achieve?",
                tab_behavior="focus",
            )
            yield Label("Motivation · required")
            yield TextArea(
                id="setup-motivation",
                placeholder="Why does this problem matter, and why now?",
                tab_behavior="focus",
            )
            yield Label("Import from file · optional UTF-8 .md / .txt")
            with Horizontal(id="import-controls"):
                yield Input(id="import-path", placeholder="Path to a Markdown or text file")
                yield Button("Preview", id="preview-import")
                yield Button("Browse", id="browse-import")
            yield Static("No source imported.", id="import-status", markup=False, classes="muted")
            yield Static("", id="setup-error", markup=False, classes="error")
        with Horizontal(classes="actions", id="setup-actions"):
            yield Button("Create Project", id="create-project", variant="primary")
            yield Button("Cancel", id="cancel-setup")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#setup-slug", Input).focus()

    @on(Button.Pressed, "#preview-import")
    def preview_import(self) -> None:
        self.preview_path(self.query_one("#import-path", Input).value)

    def preview_path(self, raw_path: str) -> None:
        error = self.query_one("#setup-error", Static)
        try:
            if not raw_path.strip():
                raise ValueError("Choose a file to preview.")
            path = Path(raw_path).expanduser().resolve()
            if path.suffix.lower() not in {".md", ".txt"}:
                raise ValueError("Unsupported format. Choose a UTF-8 .md or .txt file.")
            if not path.is_file():
                raise ValueError("Choose an existing regular file.")
            source = path.read_bytes()
            content = source.decode("utf-8")
        except (OSError, ValueError) as exc:
            error.update(safe_text(str(exc)))
            return
        error.update("")

        def use_content(value: str | None) -> None:
            if value is not None:
                self.source_path = path
                self.source_digest = sha256(source).hexdigest()
                self.query_one("#setup-motivation", TextArea).load_text(value)
                self.query_one("#import-path", Input).value = str(path)
                self.query_one("#import-status", Static).update(
                    f"Source selected: {safe_text(str(path))}"
                )

        self.app.push_screen(ImportPreview(path, safe_text(content)), use_content)

    @on(Button.Pressed, "#browse-import")
    def browse_import(self) -> None:
        value = self.query_one("#import-path", Input).value
        directory = Path(value).expanduser().parent if value else Path.cwd()

        def selected(path: Path | None) -> None:
            if path is not None:
                self.preview_path(str(path))

        self.app.push_screen(FileBrowser(directory), selected)

    @on(Button.Pressed, "#create-project")
    def create_project(self) -> None:
        app = controller(self)
        try:
            if self.source_path is not None:
                current_digest = sha256(self.source_path.read_bytes()).hexdigest()
                if current_digest != self.source_digest:
                    raise ValueError(
                        "The import source changed. Preview it again before creating the project."
                    )
            root = Path(self.query_one("#setup-root", Input).value).expanduser()
            view = app.service.create_project(
                root,
                self.query_one("#setup-slug", Input).value,
                self.query_one("#setup-goal", TextArea).text,
                self.query_one("#setup-motivation", TextArea).text,
                source_path=self.source_path,
                expected_source_sha256=self.source_digest,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            self.query_one("#setup-error", Static).update(safe_text(str(exc)))
            self.notify(
                "Project setup needs attention. See the message below the form.", severity="error"
            )
            return
        app.root = view.root
        app.switch_screen(WorkspaceScreen(view))

    @on(Button.Pressed, "#cancel-setup")
    def cancel_setup(self) -> None:
        self.app.push_screen(DiscardSetup(), self._discard_setup)

    def _discard_setup(self, discard: bool | None) -> None:
        if discard:
            self.app.pop_screen()

    def action_back(self) -> None:
        self.cancel_setup()


class DiscardSetup(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Keep Editing")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog small-dialog"):
            yield Label("LEAVE SETUP?", classes="dialog-title")
            yield Static("These form values have not been saved. Leaving discards them.")
            with Horizontal(classes="actions"):
                yield Button("Keep Editing", id="keep-setup", variant="primary")
                yield Button("Discard", id="discard-setup", variant="error")

    @on(Button.Pressed, "#keep-setup")
    def action_cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#discard-setup")
    def discard(self) -> None:
        self.dismiss(True)


class ProjectItem(ListItem):
    def __init__(self, project: str) -> None:
        super().__init__(Label(project, markup=False))
        self.project = project


class OpenScreen(ShellScreen):
    def __init__(self, root: Path, initial_error: str = "") -> None:
        super().__init__()
        self.root = root
        self.initial_error = initial_error
        self.selected_view: ProjectView | None = None

    def compose(self) -> ComposeResult:
        yield self.brand("OPEN PROJECT")
        with Horizontal(id="open-root-row"):
            yield Input(str(self.root), id="open-root", placeholder="Workbench location")
            yield Button("Find Projects", id="find-projects")
        yield Static(self.initial_error, id="open-error", markup=False, classes="error")
        with Horizontal(id="open-content"):
            with Vertical(id="project-list-pane"):
                yield Label("PROJECTS", classes="panel-title")
                yield ListView(id="project-list")
            with VerticalScroll(id="project-preview-pane"):
                yield DocumentView(
                    "Select a project to inspect its saved state.", id="project-preview"
                )
        with Horizontal(classes="actions"):
            yield Button("Resume", id="resume-project", variant="primary", disabled=True)
            yield Button("Cancel", id="cancel-open")
        yield Footer()

    async def on_mount(self) -> None:
        await self.load_projects()
        self.query_one("#project-list", ListView).focus()

    @on(Button.Pressed, "#find-projects")
    @on(Input.Submitted, "#open-root")
    async def load_projects(self) -> None:
        self.selected_view = None
        self.query_one("#resume-project", Button).disabled = True
        listing = self.query_one("#project-list", ListView)
        await listing.clear()
        self.query_one("#project-preview", DocumentView).show_document(
            "Select a project to inspect its saved state."
        )
        try:
            raw_root = self.query_one("#open-root", Input).value.strip()
            if not raw_root:
                raise ValueError("Enter a workbench location.")
            self.root = Path(raw_root).expanduser()
            projects = controller(self).service.list_projects(self.root)
            await listing.extend(ProjectItem(project) for project in projects)
            if projects:
                listing.index = 0
            message = "" if projects else "No projects found at this location."
            if self.initial_error:
                message = self.initial_error
                self.initial_error = ""
            self.query_one("#open-error", Static).update(message)
        except (OSError, ValueError) as exc:
            self.query_one("#open-error", Static).update(safe_text(str(exc)))

    @on(ListView.Selected, "#project-list")
    def select_project(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, ProjectItem):
            return
        self.selected_view = None
        self.query_one("#resume-project", Button).disabled = True
        try:
            view = controller(self).service.open_project(self.root, event.item.project)
        except (OSError, ValueError, RuntimeError) as exc:
            self.query_one("#open-error", Static).update(safe_text(str(exc)))
            return
        self.selected_view = view
        self.query_one("#project-preview", DocumentView).show_document(project_summary(view))
        self.query_one("#resume-project", Button).disabled = False
        self.query_one("#resume-project", Button).focus()

    @on(Button.Pressed, "#resume-project")
    def resume_project(self) -> None:
        if self.selected_view is not None:
            controller(self).root = self.selected_view.root
            self.app.switch_screen(WorkspaceScreen(self.selected_view))

    @on(Button.Pressed, "#cancel-open")
    def cancel(self) -> None:
        self.app.pop_screen()


def project_summary(view: ProjectView) -> str:
    issues = "\n".join(f"- {safe_text(issue)}" for issue in view.diagnostics)
    objections = "\n".join(f"- {safe_text(issue)}" for issue in view.open_objections)
    return (
        f"# {safe_text(view.project)}\n\nResearch stage: **{safe_text(view.stage)}**\n\n"
        f"## Goal\n{safe_text(view.goal) or 'No goal saved.'}\n\n"
        f"## Last handoff\n{safe_text(view.last_handoff or 'No handoff recorded.')}\n\n"
        f"## Next step\n{safe_text(view.next_step) or 'No next step recorded.'}\n\n"
        f"## Open objections\n{objections or 'No open objections in validated objects.'}\n\n"
        f"## Data issues\n{issues or 'No validation diagnostics reported.'}\n\n"
        + (
            "**Setup is incomplete. Resume Setup is available in the workspace.**"
            if view.setup_pending
            else ""
        )
    )


class ContextPreview(ModalScreen[None]):
    BINDINGS = [Binding("escape", "close", "Close")]

    def __init__(self, context: str) -> None:
        super().__init__()
        self.context = context

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label("CONTEXT FOR THE NEXT SEND", classes="dialog-title")
            yield Static(
                "These saved inputs accompany your new message on the next Send. "
                "A resumed session retains earlier inputs; a rebuild supplies the full context. "
                "Your current composer is appended on Send. The exact request is archived.",
                markup=False,
            )
            with VerticalScroll():
                yield Static(safe_text(self.context), markup=False, id="context-content")
            yield Button("Close", id="close-context")

    @on(Button.Pressed, "#close-context")
    def action_close(self) -> None:
        self.dismiss(None)


class SessionControls(ModalScreen[bool | None]):
    BINDINGS = [Binding("escape", "close", "Close")]

    def __init__(self, model: str, latest: Turn | None, fresh: bool) -> None:
        super().__init__()
        self.model = model
        self.latest = latest
        self.fresh = fresh

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog", id="session-dialog"):
            yield Label("EXPLORATION SESSION", classes="dialog-title")
            with VerticalScroll(id="session-details"):
                latest = self.latest
                next_send = "rebuild from files" if self.fresh else "continue when available"
                details = (
                    f"Selected model: {self.model}\n"
                    f"Next Send: {next_send}"
                    "\nPreference lasts only in this running app.\n\n"
                )
                if latest is None:
                    details += "No exploration request yet."
                else:
                    details += (
                        f"Latest request model: {latest.model}\n"
                        f"Mode: {latest.session_mode or 'legacy / full file context'}\n"
                        f"Reason: {latest.session_reason or 'not recorded'}\n"
                        f"Native session ID: {latest.session_id or 'none reported'}\n"
                    )
                details += (
                    "\nIf native session storage is missing or repeatedly fails, choose Rebuild. "
                    "This uses the archived conversation. No model runs until Send. "
                    "Brief proposals always use a separate fresh session."
                )
                yield Static(safe_text(details), markup=False, id="session-summary")
            with Vertical(id="session-actions"):
                yield Button("Rebuild on next Send", id="session-rebuild", compact=True)
                yield Button("Continue session", id="session-continue", compact=True)
                yield Button("Close", id="session-close", compact=True)

    @on(Button.Pressed, "#session-rebuild")
    def rebuild(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#session-continue")
    def continue_session(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#session-close")
    def action_close(self) -> None:
        self.dismiss(None)


class ApplyBrief(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, actor: str) -> None:
        super().__init__()
        self.actor = actor

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog small-dialog"):
            yield Label("APPLY TO BRIEF?", classes="dialog-title")
            yield Static(
                f"Researcher: {safe_text(self.actor)}\n\n"
                "Replace the saved brief with your edited proposal. "
                "The previous version and your confirmation are archived. "
                "An external edit will prevent replacement. Research stage stays unchanged.",
                markup=False,
            )
            with Horizontal(classes="actions"):
                yield Button("Cancel", id="cancel-apply", variant="primary")
                yield Button("Apply to Brief", id="confirm-apply")

    @on(Button.Pressed, "#cancel-apply")
    def action_cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#confirm-apply")
    def confirm(self) -> None:
        self.dismiss(True)


class WorkspaceScreen(ShellScreen):
    BINDINGS = [
        Binding("f2", "inspector", "Inspector"),
        Binding("f3", "session", "Session", priority=True),
        Binding("ctrl+enter", "send", "Send", priority=True),
        Binding("escape", "back", "Home"),
    ]

    def __init__(self, view: ProjectView) -> None:
        super().__init__(classes="workspace-screen")
        self.view = view
        self.step = "Setup" if view.setup_pending else "Explore"
        self.inspector_requested: bool | None = None
        self._discussion_signature = ""
        self._proposal_id: str | None = None
        self._proposal_before = ""
        self._proposal_status = ""
        self._proposal_applying = False
        self._proposal_loading = False
        self._draft_dirty = False
        self._active = False
        self._interrupted = False
        self._load_error = ""
        self._read_failed = False
        self._service_error = False
        self._observed_service_error: str | None = None
        self._model_error = ""
        self._latest_exploration: Turn | None = None

    def compose(self) -> ComposeResult:
        yield self.brand(self.view.project)
        yield Static("", id="workspace-status", markup=False)
        with Horizontal(id="workspace-toolbar"):
            yield Button("Home", id="workspace-home", compact=True)
            yield Select(
                [(VIEW_LABELS.get(name, name), name) for name in STEPS],
                value=self.step,
                allow_blank=False,
                id="step-select",
                compact=True,
            )
            yield Button("F2 Inspector", id="toggle-inspector", compact=True)
        yield Static("F2 switches brief / discussion · Views are optional", id="resize-notice")
        with Horizontal(id="workspace-body"):
            with Vertical(id="navigation"):
                yield Label("RESEARCH", classes="panel-title")
                with VerticalScroll(id="research-scroll"):
                    yield DocumentView(id="research-state")
                yield Label("VIEWS · OPTIONAL", classes="panel-title")
                yield ListView(
                    *(ListItem(Label(VIEW_LABELS.get(name, name))) for name in STEPS),
                    id="step-list",
                )
            with Vertical(id="main-pane", classes="pane"):
                yield Label("", id="main-title", classes="panel-title")
                with VerticalScroll(id="main-scroll"):
                    yield DocumentView(id="main-content")
                    yield DocumentView(id="transcript")
                    yield Button("Resume Setup", id="resume-setup", variant="primary")
            with Vertical(id="inspector", classes="pane"):
                yield Select(
                    [(name, name) for name in ("Saved", "Proposed", "Changes")],
                    value="Saved",
                    allow_blank=False,
                    id="brief-tab",
                    compact=True,
                )
                with VerticalScroll(id="inspector-scroll"):
                    yield DocumentView(id="brief-content")
                    yield DocumentView(id="brief-changes")
                    yield TextArea(id="proposal-editor", tab_behavior="focus")
                    yield Static("", id="proposal-state", markup=False, classes="muted")
                with Horizontal(id="proposal-actions"):
                    yield Button("Apply to Brief", id="apply-brief", compact=True)
                    yield Button("Dismiss", id="dismiss-proposal", compact=True)
        yield Static("", id="discussion-status", markup=False)
        yield TextArea(
            id="composer",
            placeholder="Discuss the question · Enter inserts a newline",
            tab_behavior="focus",
        )
        with Horizontal(id="discussion-controls"):
            yield Select([], prompt="Configure model", id="discussion-model", compact=True)
            yield Button("Send", id="send-message", compact=True, variant="primary")
            yield Button("Stop", id="stop-message", compact=True)
            yield Button("Context", id="show-context", compact=True)
            yield Button("Propose Brief", id="propose-brief", compact=True)
            yield Button("Recover", id="recover-discussion", compact=True)
        yield Footer()

    def on_mount(self) -> None:
        self.load_brief()
        app = controller(self)
        self.query_one("#composer", TextArea).load_text(
            app.composers.get((self.view.root, self.view.project), "")
        )
        try:
            models = app.discussion.models(self.view.root)
            self.query_one("#discussion-model", Select).set_options(
                [(name, name) for name in models]
            )
            if models:
                self.query_one("#discussion-model", Select).value = models[0]
            else:
                self._model_error = "Configure a discussion model in models.toml before sending."
        except (OSError, ValueError, RuntimeError) as exc:
            self._model_error = safe_text(str(exc))
        self.refresh_view()
        self.refresh_discussion()
        self.query_one("#step-list", ListView).index = STEPS.index(self.step)
        self.update_layout()
        if self.view.setup_pending:
            self.query_one("#resume-setup", Button).focus()
        else:
            self.query_one("#composer", TextArea).focus()

    def load_brief(self) -> None:
        self.query_one("#brief-content", DocumentView).show_document(
            safe_text(self.view.brief) or "No brief saved."
        )

    def on_resize(self, event: events.Resize) -> None:
        self.update_layout(event.size.width, event.size.height)

    def update_layout(self, width: int | None = None, height: int | None = None) -> None:
        width = self.app.size.width if width is None else width
        height = self.app.size.height if height is None else height
        compact = width < 80 or height < 24
        medium = not compact and width < 120
        self.set_class(compact, "compact")
        self.set_class(medium, "medium")
        visible = self.inspector_requested
        if visible is None:
            visible = not compact and not medium
        self.set_class(visible, "inspector-visible")
        if compact and self.is_mounted:
            focused = self.app.focused
            if focused is not None and focused.id == "step-list":
                self.query_one("#step-select", Select).focus()

    @on(ListView.Selected, "#step-list")
    def step_selected(self, event: ListView.Selected) -> None:
        index = self.query_one("#step-list", ListView).index
        if index is not None:
            self.choose_step(STEPS[index])

    @on(Select.Changed, "#step-select")
    def step_changed(self, event: Select.Changed) -> None:
        if isinstance(event.value, str):
            self.choose_step(event.value)

    def choose_step(self, step: str) -> None:
        self.step = step
        self.query_one("#step-select", Select).value = step
        self.query_one("#step-list", ListView).index = STEPS.index(step)
        if self.has_class("compact") or self.has_class("medium"):
            self.inspector_requested = False
            self.update_layout()
        self.refresh_view()

    def refresh_view(self) -> None:
        view = self.view
        state = "SETUP PENDING" if view.setup_pending else "SAVED FILES"
        if view.diagnostics:
            state = "DIAGNOSTICS · READ ONLY"
        self.query_one("#workspace-status", Static).update(
            f"Research stage: {safe_text(view.stage)}  │  {state}"
        )
        objections = "\n".join(f"- {safe_text(issue)}" for issue in view.open_objections)
        self.query_one("#research-state", DocumentView).show_document(
            f"**Stage:** {safe_text(view.stage)}\n\n"
            f"### Goal\n{safe_text(view.goal) or 'No goal saved.'}\n\n"
            f"### Open objections\n{objections or 'None recorded.'}\n\n"
            "### Next step\n"
            + (safe_text(view.next_step) or "Continue discussion; propose a brief when ready.")
        )
        self.query_one("#main-title", Label).update(
            "DISCUSSION" if self.step == "Explore" else self.step.upper()
        )
        self.query_one("#resume-setup", Button).display = (
            view.setup_pending and self.step == "Setup"
        )
        diagnostic = ""
        if view.diagnostics:
            diagnostic = (
                "## Diagnostics\n\n"
                + "\n".join(f"- {safe_text(issue)}" for issue in view.diagnostics)
                + "\n\nWrites are disabled. Existing files remain available for inspection.\n\n"
            )
        if self.step == "Setup":
            content = (
                f"## Goal\n\n{safe_text(view.goal) or 'No goal saved.'}\n\n"
                f"## Motivation\n\n{safe_text(view.motivation) or 'No motivation recorded.'}\n\n"
                + (
                    "Setup is incomplete. Resume uses the saved setup intent.\n\n"
                    if view.setup_pending
                    else "Setup values are saved.\n\n"
                )
                + "Project files remain editable with your text editor."
            )
        elif self.step == "Explore":
            content = (
                ""
                if self._discussion_signature
                else (
                    "Discuss the question below. **Send** starts a model call. "
                    "**Context** shows the saved brief and conversation supplied to the model."
                )
            )
        elif self.step == "Brief":
            content = (
                "Saved document · Propose Brief creates an archived draft; "
                "apply it explicitly in the inspector.\n\n---\n\n"
                + (safe_text(view.brief) or "No brief saved.")
            )
        elif self.step == "Key Claims":
            content = (
                "## Key Claims · coming later\n\n"
                "Candidate extraction and confirmation are not implemented here. "
                "Claims are optional at this point; continue discussion whenever useful. "
                "Existing objects remain accessible through the CLI and project files."
            )
        elif self.step == "Review":
            content = (
                "## Independent Review · coming later\n\n"
                "Use the existing `toulmin review` CLI for independent review. "
                "No review starts when you open this view."
            )
        elif self.step == "Resolve":
            content = (
                f"## Open objections\n\n{objections or 'None recorded.'}\n\n"
                "## Resolve · coming later\n\n"
                "Use `toulmin intake` and `toulmin rule` for explicit researcher choices."
            )
        else:
            content = (
                "## Last recorded handoff\n\n"
                f"{safe_text(view.last_handoff or 'No handoff recorded.')}\n\n"
                f"## Next step\n\n{safe_text(view.next_step) or 'No next step recorded.'}\n\n"
                "### Handoff authoring · coming later\n\n"
                "Use `toulmin handoff` for a confirmed handoff. "
                "Leaving does not create a handoff or Git commit."
            )
        self.query_one("#main-content", DocumentView).show_document(diagnostic + content)
        self.query_one("#transcript").display = self.step == "Explore"
        self.query_one("#composer").display = self.step == "Explore"
        self.update_controls()

    def refresh_discussion(self) -> None:
        """Reload durable output without resetting either editor or scroll on each tick."""
        app = controller(self)
        try:
            discussion = app.discussion.load(self.view.root, self.view.project)
            active = app.discussion.active(self.view.root, self.view.project)
            error = app.discussion.error(self.view.root, self.view.project)
        except (OSError, ValueError, RuntimeError) as exc:
            self._load_error = safe_text(str(exc))
            self._read_failed = True
            self.update_controls()
            return
        self._load_error = ""
        self._read_failed = False
        self._service_error = bool(error)
        self._observed_service_error = error
        self._active = active
        self._interrupted = (
            any(turn.status == "running" for turn in discussion.turns) and not active
        )
        self._latest_exploration = next(
            (turn for turn in reversed(discussion.turns) if turn.operation == "explore"), None
        )
        signature = repr((discussion, active))
        if signature != self._discussion_signature:
            self._discussion_signature = signature
            parts = []
            for turn in discussion.turns:
                label = (
                    "Interrupted / resolve before sending"
                    if (turn.status == "running" and not active)
                    else turn.status
                )
                parts.append(
                    f"### You · {safe_text(turn.operation)}\n\n{safe_text(turn.user)}\n\n"
                    f"### {safe_text(turn.model)} · {safe_text(label)}\n\n"
                    + (
                        f"Session: {safe_text(turn.session_mode)} · "
                        f"{safe_text(turn.session_reason or 'reason unavailable')}"
                        + (f" · ID {safe_text(turn.session_id[:12])}" if turn.session_id else "")
                        + "\n\n"
                        if turn.session_mode
                        else ""
                    )
                    + (
                        safe_text(turn.text)
                        or (
                            "Waiting for the final response…"
                            if active and turn.status == "running"
                            else "No completed response."
                        )
                    )
                    + (f"\n\nFailure: {safe_text(turn.failure)}" if turn.failure else "")
                    + (f"\n\nSaved as {safe_text(turn.run)}." if turn.run else "")
                )
            self.query_one("#transcript", DocumentView).show_document("\n\n---\n\n".join(parts))
            proposal = discussion.proposal
            if proposal is not None:
                changed = self._proposal_id != proposal.id
                self._proposal_id = proposal.id
                self._proposal_before = proposal.before
                self._proposal_status = proposal.status
                self._proposal_applying = proposal.applying
                if proposal.applying:
                    self._draft_dirty = False
                if changed or not self._draft_dirty:
                    editor = self.query_one("#proposal-editor", TextArea)
                    if editor.text != proposal.text:
                        self._proposal_loading = True
                        editor.load_text(proposal.text)
                        self.call_after_refresh(self._finish_proposal_loading)
                if changed:
                    self.query_one("#brief-tab", Select).value = "Proposed"
            else:
                self._proposal_id = None
                self._proposal_status = ""
                self._proposal_applying = False
            self.update_proposal()
        if error:
            self._load_error = safe_text(error)
        self.update_controls()

    def _finish_proposal_loading(self) -> None:
        self._proposal_loading = False

    def update_controls(self) -> None:
        if not self.is_mounted:
            return
        blocked = bool(self.view.diagnostics or self.view.setup_pending or self._load_error)
        model = self.query_one("#discussion-model", Select).value
        unavailable = blocked or bool(self._model_error) or not isinstance(model, str)
        self.query_one("#send-message", Button).disabled = (
            unavailable or self._active or self._interrupted
        )
        self.query_one("#propose-brief", Button).disabled = (
            unavailable or self._active or self._interrupted or self._proposal_status == "pending"
        )
        self.query_one("#stop-message", Button).disabled = not self._active
        self.query_one("#recover-discussion", Button).display = (
            self._interrupted or self._service_error
        )
        self.query_one("#recover-discussion", Button).disabled = (
            bool(self.view.diagnostics or self.view.setup_pending)
            or self._active
            or self._read_failed
        )
        if self._load_error:
            status = self._load_error
        elif self.view.diagnostics or self.view.setup_pending:
            status = "Read only · resolve diagnostics / finish Setup before sending."
        elif self._interrupted:
            status = (
                "Interrupted / resolve before sending · Recover archives failure; Send retries."
            )
        elif self._active:
            status = (
                "Running · waiting for the final response · Stop cancels and archives this attempt."
            )
        else:
            status = self._model_error or (
                "Next Send: rebuild from files · F3 Session"
                if self.fresh_session
                else "Ready · continue session when available · F3 Session"
            )
        self.query_one("#discussion-status", Static).update(status)
        pending = self._proposal_id is not None and self._proposal_status == "pending"
        self.query_one("#proposal-editor", TextArea).read_only = (
            blocked or self._active or self._proposal_applying
        )
        self.query_one("#apply-brief", Button).disabled = not pending or blocked or self._active
        self.query_one("#dismiss-proposal", Button).disabled = (
            not pending or blocked or self._active or self._proposal_applying
        )

    @on(Select.Changed, "#discussion-model")
    def model_changed(self) -> None:
        self.update_controls()

    @on(TextArea.Changed, "#composer")
    def composer_changed(self) -> None:
        controller(self).composers[(self.view.root, self.view.project)] = self.query_one(
            "#composer", TextArea
        ).text

    @on(Button.Pressed, "#send-message")
    def action_send(self) -> None:
        self.start_turn("explore")

    @property
    def fresh_session(self) -> bool:
        return (self.view.root, self.view.project) in controller(self).fresh_sessions

    def action_session(self) -> None:
        model = self.query_one("#discussion-model", Select).value

        def choose(fresh: bool | None) -> None:
            if fresh is not None:
                key = (self.view.root, self.view.project)
                if fresh:
                    controller(self).fresh_sessions.add(key)
                else:
                    controller(self).fresh_sessions.discard(key)
                self.update_controls()

        self.app.push_screen(
            SessionControls(
                model if isinstance(model, str) else "none selected",
                self._latest_exploration,
                self.fresh_session,
            ),
            choose,
        )

    @on(Button.Pressed, "#propose-brief")
    def propose_brief(self) -> None:
        self.start_turn("brief")

    def start_turn(self, operation: str) -> None:
        button = "#send-message" if operation == "explore" else "#propose-brief"
        if self.query_one(button, Button).disabled:
            return
        editor = self.query_one("#composer", TextArea)
        text = editor.text.strip()
        if operation == "explore" and not text:
            self.notify("Write a message before sending.", severity="warning")
            return
        if operation == "brief" and not text:
            text = "Propose an updated brief based on the saved brief and full discussion."
        model = self.query_one("#discussion-model", Select).value
        if not isinstance(model, str):
            return
        if not self.flush_proposal():
            return
        try:
            controller(self).discussion.start(
                self.view.root,
                self.view.project,
                text,
                model,
                operation=operation,
                fresh=self.fresh_session if operation == "explore" else False,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            self.notify(safe_text(str(exc)), severity="error", timeout=10)
            return
        if operation == "explore":
            controller(self).fresh_sessions.discard((self.view.root, self.view.project))
        editor.load_text("")
        self.choose_step("Explore")
        self.refresh_discussion()
        self.query_one("#main-scroll", VerticalScroll).scroll_end(animate=False)

    @on(Button.Pressed, "#stop-message")
    def stop_message(self) -> None:
        try:
            controller(self).discussion.stop(self.view.root, self.view.project)
        except (OSError, ValueError, RuntimeError) as exc:
            self.notify(safe_text(str(exc)), severity="error")
        self.refresh_discussion()

    @on(Button.Pressed, "#recover-discussion")
    def recover_discussion(self) -> None:
        try:
            controller(self).discussion.recover(self.view.root, self.view.project)
        except (OSError, ValueError, RuntimeError) as exc:
            self.notify(safe_text(str(exc)), severity="error")
        self.refresh_discussion()

    @on(Button.Pressed, "#show-context")
    def show_context(self) -> None:
        model = self.query_one("#discussion-model", Select).value
        try:
            context = controller(self).discussion.context(
                self.view.root,
                self.view.project,
                model if isinstance(model, str) else None,
                fresh=self.fresh_session,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            self.notify(safe_text(str(exc)), severity="error")
            return
        self.app.push_screen(ContextPreview(context))

    @on(Select.Changed, "#brief-tab")
    def brief_tab_changed(self) -> None:
        self.update_proposal()

    def update_proposal(self) -> None:
        tab = self.query_one("#brief-tab", Select).value
        pending = self._proposal_id is not None and self._proposal_status == "pending"
        self.query_one("#brief-content").display = tab == "Saved"
        self.query_one("#proposal-editor").display = tab == "Proposed" and pending
        self.query_one("#brief-changes").display = tab == "Changes"
        editor = self.query_one("#proposal-editor", TextArea)
        changes = (
            "".join(
                unified_diff(
                    self._proposal_before.splitlines(keepends=True),
                    editor.text.splitlines(keepends=True),
                    fromfile="Saved brief at proposal",
                    tofile="Edited proposal",
                )
            )
            if self._proposal_id
            else "No proposal yet. Use Propose Brief when ready."
        )
        self.query_one("#brief-changes", DocumentView).show_document(
            f"```diff\n{safe_text(changes)}\n```"
        )
        blocked = bool(self.view.diagnostics or self.view.setup_pending or self._load_error)
        editor.read_only = blocked or self._active or self._proposal_applying
        self.query_one("#apply-brief", Button).disabled = not pending or blocked or self._active
        self.query_one("#dismiss-proposal", Button).disabled = (
            not pending or blocked or self._active or self._proposal_applying
        )
        self.query_one("#apply-brief", Button).label = (
            "Resume Apply" if self._proposal_applying else "Apply to Brief"
        )
        if self._proposal_applying:
            self.query_one("#proposal-state", Static).update(
                "Application interrupted · confirmed text is preserved. "
                "Resume Apply completes the saved change; editing and dismissal are paused."
            )
            return
        self.query_one("#proposal-state", Static).update(
            ("Saving draft…" if self._draft_dirty else "Draft saved under runs/")
            if pending
            else (f"Proposal {self._proposal_status}." if self._proposal_id else "No proposal yet.")
        )

    @on(TextArea.Changed, "#proposal-editor")
    def proposal_changed(self) -> None:
        if (
            self._proposal_loading
            or self._proposal_applying
            or not self._proposal_id
            or self._proposal_status != "pending"
        ):
            return
        self._draft_dirty = True
        self.update_proposal()
        self.set_timer(0.4, self.flush_proposal)

    def flush_proposal(self) -> bool:
        if self._proposal_applying or not self._draft_dirty or self._proposal_id is None:
            return True
        try:
            controller(self).discussion.save_draft(
                self.view.root,
                self.view.project,
                self._proposal_id,
                self.query_one("#proposal-editor", TextArea).text,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            self.query_one("#proposal-state", Static).update(f"Save failed: {safe_text(str(exc))}")
            return False
        self._draft_dirty = False
        self.update_proposal()
        return True

    @on(Button.Pressed, "#apply-brief")
    def apply_brief(self) -> None:
        if self.query_one("#apply-brief", Button).disabled or not self.flush_proposal():
            return
        proposal_id = self._proposal_id
        text = self.query_one("#proposal-editor", TextArea).text
        app = controller(self)

        def confirmed(value: bool | None) -> None:
            if not value or proposal_id is None:
                return
            try:
                app.discussion.apply(self.view.root, self.view.project, proposal_id, text)
                self.view = app.service.open_project(self.view.root, self.view.project)
            except (OSError, ValueError, RuntimeError) as exc:
                self.notify(safe_text(str(exc)), severity="error", timeout=10)
                self.refresh_discussion()
                return
            self.load_brief()
            self.query_one("#brief-tab", Select).value = "Saved"
            self.refresh_view()
            self.refresh_discussion()
            self.notify("Brief applied; previous version and confirmation archived.")

        self.app.push_screen(ApplyBrief(app.discussion.actor), confirmed)

    @on(Button.Pressed, "#dismiss-proposal")
    def dismiss_proposal(self) -> None:
        if self._proposal_id is None or not self.flush_proposal():
            return
        try:
            controller(self).discussion.dismiss(
                self.view.root, self.view.project, self._proposal_id
            )
        except (OSError, ValueError, RuntimeError) as exc:
            self.notify(safe_text(str(exc)), severity="error")
        self.refresh_discussion()

    @on(Button.Pressed, "#resume-setup")
    def resume_setup(self) -> None:
        try:
            self.view = controller(self).service.resume_setup(self.view.root, self.view.project)
        except (OSError, ValueError, RuntimeError) as exc:
            self.notify(safe_text(str(exc)), severity="error", timeout=10)
            return
        self.load_brief()
        self.refresh_view()

    @on(Button.Pressed, "#toggle-inspector")
    def action_inspector(self) -> None:
        self.inspector_requested = not self.has_class("inspector-visible")
        self.update_layout()
        if self.has_class("compact") or self.has_class("medium"):
            self.query_one("#toggle-inspector", Button).focus()

    @on(Button.Pressed, "#workspace-home")
    def action_back(self) -> None:
        if self.flush_proposal():
            self.app.switch_screen(HomeScreen())


class QuitScreen(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        setup_open = any(isinstance(screen, SetupScreen) for screen in self.app.screen_stack)
        with Vertical(classes="dialog small-dialog"):
            yield Label("LEAVE THE WORKBENCH?", classes="dialog-title")
            yield Static(
                "Setup form values have not been saved and will be discarded."
                if setup_open
                else "Saved project files stay on disk. "
                "This creates no handoff or Git commit. "
                "Active model jobs will be stopped and archived before exit."
            )
            yield Static(
                "Handoff authoring is coming later; the CLI remains available.", classes="muted"
            )
            with Vertical(id="quit-actions"):
                yield Button("Cancel", id="cancel-quit", variant="primary")
                yield Button("Handoff · Unavailable", id="quit-handoff", disabled=True)
                yield Button("Stop jobs & Quit without Handoff", id="confirm-quit")

    @on(Button.Pressed, "#cancel-quit")
    def action_cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#confirm-quit")
    def confirm(self) -> None:
        self.dismiss(True)


class HelpScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape", "close", "Close"), Binding("f1", "close", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog small-dialog"):
            yield Label("KEYBOARD GUIDE", classes="dialog-title")
            with VerticalScroll():
                yield Static(
                    "Tab / Shift+Tab   Move focus\n"
                    "Arrows            Navigate projects and optional views\n"
                    "Enter             Activate a focused control\n"
                    "Enter in editors  Insert a newline\n"
                    "Ctrl+Enter        Send a discussion message\n"
                    "F2                Toggle brief / proposal inspector\n"
                    "F3                Exploration session / rebuild next Send\n"
                    "Escape            Close a dialog / go back\n"
                    "Ctrl+Q            Review quit options\n\n"
                    "Below 120 columns the inspector is toggled.\n"
                    "Below 80 columns or 24 rows use the view selector.\n\n"
                    "Send / Propose Brief explicitly starts a model call.\n"
                    "Stop cancels that project’s job and archives failure.\n"
                    "Quit stops and archives active jobs. Applying a proposal\n"
                    "requires confirmation. Review/handoff use the CLI.",
                    markup=False,
                )
            yield Button("Close", id="close-help", variant="primary")

    @on(Button.Pressed, "#close-help")
    def action_close(self) -> None:
        self.dismiss(None)


class ToulminApp(App[None]):
    """Optional Textual entry point, backed by the same project service as the CLI."""

    TITLE = "Toulmin"
    CSS_PATH = "theme.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("ctrl+q", "request_quit", "Quit", priority=True),
        Binding("f1", "help", "Help", priority=True),
    ]

    def __init__(
        self,
        root: Path | None = None,
        project: str | None = None,
        service: WorkspaceService | None = None,
        discussion: DiscussionService | None = None,
    ) -> None:
        super().__init__()
        self.root = root or Path.cwd()
        self.project = project
        self.service = service or WorkspaceService()
        self.discussion = discussion or DiscussionService()
        self.composers: dict[tuple[Path, str], str] = {}
        self.fresh_sessions: set[tuple[Path, str]] = set()
        self.ascii_borders = environ.get("TOULMIN_ASCII", "").lower() in {"1", "true", "yes"}

    def on_mount(self) -> None:
        self.set_class(self.ascii_borders, "ascii")
        self.call_after_refresh(self.show_initial_screen)
        self.set_interval(0.4, self.poll_discussion)

    def poll_discussion(self) -> None:
        # Shutdown stops the app pump before removing children; is_mounted alone
        # can remain true while a queued timer sees a partially dismantled screen.
        if not self.is_running or not self.screen_stack:
            return
        # A switched-out screen can remain mounted briefly while its children leave.
        # Jobs belong to the service; only the current workspace needs repainting.
        screen = self.screen
        if isinstance(screen, WorkspaceScreen) and screen.is_mounted:
            try:
                active = self.discussion.active(screen.view.root, screen.view.project)
                error = self.discussion.error(screen.view.root, screen.view.project)
            except (OSError, ValueError, RuntimeError):
                screen.refresh_discussion()
                return
            # Read archives while running and once on completion/error changes.
            # Idle external edits are loaded when reopening the project.
            if active or screen._active or error != screen._observed_service_error:
                screen.refresh_discussion()

    def on_unmount(self) -> None:
        self.discussion.close()

    def show_initial_screen(self) -> None:
        if self.project is None:
            self.push_screen(HomeScreen())
            return
        try:
            view = self.service.open_project(self.root, self.project)
        except (OSError, ValueError) as exc:
            self.push_screen(OpenScreen(self.root, safe_text(str(exc))))
        else:
            self.push_screen(WorkspaceScreen(view))

    def action_request_quit(self) -> None:
        if isinstance(self.screen, QuitScreen):
            return

        def quit_if_confirmed(confirmed: bool | None) -> None:
            if confirmed:
                for screen in self.screen_stack:
                    if isinstance(screen, WorkspaceScreen) and not screen.flush_proposal():
                        return
                self.discussion.close()
                self.exit()

        self.push_screen(QuitScreen(), quit_if_confirmed)

    def action_help(self) -> None:
        if not isinstance(self.screen, HelpScreen):
            self.push_screen(HelpScreen())


def launch(root: Path | None = None, project: str | None = None) -> None:
    """Run the optional terminal interface; the CLI imports this function lazily."""
    app = ToulminApp(root=root, project=project)
    try:
        app.run()
    finally:
        app.discussion.close()
