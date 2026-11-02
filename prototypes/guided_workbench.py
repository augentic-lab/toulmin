"""Disposable UI-R2 walkthrough: in-memory sample data, no model or project writes."""

from dataclasses import dataclass

from textual import events, on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Footer, Label, Select, Static, TextArea

VIEWS = ("Overview", "Explore", "Review", "Resolve", "Validate")
INITIAL_BRIEF = (
    "Question: Would caching repeated reads reduce p95 query latency?\n\n"
    "Compare cache on/off under the same read workload.\n"
    "Unknown: workload size, hit rate, warm-up and prior work."
)
STATEMENT = "Caching repeated reads reduces p95 latency under equal load."
ISSUE = "Cache warm-up and hit rate are unspecified."
PLAN = (
    "Baseline: cache disabled, same query trace and concurrency.\n"
    "Procedure: warm the cache, record hit rate, repeat both runs.\n"
    "Measure: p95 latency and variability.\n"
    "Refute if: the improvement disappears under equal conditions."
)


@dataclass
class Sample:
    created: bool = False
    brief: str = ""
    working_brief: str = INITIAL_BRIEF
    statement: bool = False
    review_brief: str = ""
    issue: bool = False
    plan: str = ""
    working_plan: str = PLAN
    next_step: str = ""
    handoff: bool = False
    resume_view: str = "Explore"

    @property
    def reviewed(self) -> bool:
        return bool(self.review_brief)

    @property
    def stale(self) -> bool:
        return self.reviewed and self.review_brief != self.brief

    @property
    def recommendation(self) -> tuple[str, str]:
        if self.handoff:
            return self.next_step, self.resume_view
        if self.issue:
            if self.plan:
                return "Run the experiment outside Toulmin; then record results.", "Validate"
            return "Define warm-up and hit rate before collecting evidence.", "Validate"
        if self.reviewed:
            return "Decide whether the reviewer suggestion needs tracking.", "Resolve"
        if self.brief:
            return "Choose a statement and prepare an exploratory review.", "Review"
        return "Define the comparison and save a short brief.", "Explore"


class GuidedWorkbench(App[None]):
    """A clickable wireframe, deliberately separate from the installed application."""

    TITLE = "Toulmin / workflow prototype"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        ("f2", "context", "Context"),
        ("escape", "overview", "Overview"),
        ("ctrl+q", "quit", "Exit demo"),
    ]
    CSS = """
    Screen { background: #15191d; color: #deded9; }
    #header { height: 1; padding: 0 1; background: #20262c; }
    #brand { width: 1fr; content-align: left middle; height: 1; text-style: bold; }
    #header Button { height: 1; min-height: 1; border: none; margin: 0; }
    #end-session { width: 16; }
    #project-home { width: 7; min-width: 7; }
    #status { height: 1; padding: 0 1; color: #b2b9be; }
    #switcher { height: 3; padding: 0 1; }
    #selector { width: 1fr; }
    #context-button { width: 17; }
    #body { height: 1fr; }
    #rail { width: 17; padding: 1; border-right: solid #414a51; }
    #rail Button { width: 100%; height: 2; min-width: 0; border: none;
      background: transparent; content-align: left middle; margin: 0; }
    #rail Button.current { background: #333f49; text-style: bold; }
    #task { width: 1fr; }
    #content { padding: 1 2; height: 1fr; }
    #content Label { height: auto; margin-bottom: 1; text-style: bold; color: #d7e5ec; }
    #content Static { height: auto; margin-bottom: 1; }
    TextArea { height: 9; min-height: 5; margin-bottom: 1; border: solid #697782;
      background: #1c2228; }
    #actions { height: 3; padding: 0 1; }
    Button { width: auto; min-width: 10; margin-right: 1; border: tall #515e68;
      background: #252e35; color: #deded9; }
    Button.-primary { border: tall #aec6d5; background: #334754; }
    Button:focus { text-style: bold; border: tall #e2e8eb; }
    #context { width: 33; padding: 1 2; border-left: solid #414a51; }
    #context-title { height: auto; margin-bottom: 1; text-style: bold; }
    #context-text { height: auto; }
    Footer { background: #20262c; }
    .medium #context { display: none; }
    .medium.context-open #context { display: block; width: 1fr; }
    .medium.context-open #task { display: none; }
    .compact #rail { display: none; }
    .compact #header { height: 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.sample = Sample()
        self.view = "Home"
        self.context_open = False
        self.return_focus: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="header"):
            yield Label("TOULMIN / cache-study", id="brand")
            yield Button("Home", id="project-home", compact=True)
            yield Button("End Session", id="end-session", compact=True)
        yield Static("", id="status", markup=False)
        with Horizontal(id="switcher"):
            yield Select(
                [(v, v) for v in VIEWS], value="Overview", allow_blank=False, id="selector"
            )
            yield Button("F2 Context", id="context-button", compact=True)
        with Horizontal(id="body"):
            with Vertical(id="rail"):
                for view in VIEWS:
                    yield Button(view, id=f"nav-{view.lower()}", compact=True)
            with Vertical(id="task"):
                yield VerticalScroll(id="content")
                yield Horizontal(id="actions")
            with VerticalScroll(id="context"):
                yield Label("CONTEXT", id="context-title")
                yield Static("", id="context-text", markup=False)
        yield Footer()

    async def on_mount(self) -> None:
        await self.show("Home")

    def on_resize(self, event: events.Resize) -> None:
        self.set_class(event.size.width < 110, "medium")
        self.set_class(event.size.width < 80 or event.size.height < 24, "compact")
        if self.query("#rail"):
            self.layout_controls()

    def layout_controls(self) -> None:
        working = self.sample.created and self.view not in {"Home", "Setup"}
        self.query_one("#rail").display = working and not self.has_class("compact")
        self.query_one("#switcher").display = working and self.has_class("medium")
        self.query_one("#selector").display = self.has_class("compact")
        self.query_one("#end-session", Button).disabled = not working
        self.query_one("#nav-resolve", Button).label = (
            "Resolve 1 open"
            if self.sample.issue
            else "Resolve 1 new"
            if self.sample.reviewed
            else "Resolve"
        )
        for name in VIEWS:
            self.query_one(f"#nav-{name.lower()}").set_class(
                ("Overview" if self.view == "Reopen" else self.view) == name, "current"
            )

    def retain_edit(self) -> None:
        editors = self.query("#editor")
        if not editors:
            return
        value = self.query_one("#editor", TextArea).text
        if self.view == "Explore":
            self.sample.working_brief = value
        elif self.view == "Validate":
            self.sample.working_plan = value
        elif self.view == "Handoff":
            self.sample.next_step = value

    def page(self) -> tuple[str, str, str | None, list[tuple[str, str]], str]:
        s = self.sample
        next_step, _ = s.recommendation
        if self.view == "Home":
            return (
                "A place to pick up your research",
                "Try a small cache-latency question.\n\n"
                "This is a clickable wireframe. All answers and records are simulated; "
                "nothing survives exiting the demo.",
                None,
                [("create", "Restart Sample" if s.created else "New Sample Project")]
                + ([("open", "Open Sample")] if s.created else []),
                "SAMPLE CASE\n\nWould caching repeated reads lower p95 latency?\n\n"
                "No models, project files or experimental results are used.",
            )
        if self.view == "Setup":
            return (
                "Start with a question",
                "PROJECT\ncache-study\n\nGOAL\nCompare query latency with and without caching.\n\n"
                "MOTIVATION\nRepeated reads may be expensive.\n\n"
                "These setup values are prefilled for this walkthrough.",
                None,
                [("initialize", "Create Sample"), ("home", "Back")],
                "CREATION EFFECT\n\nStart a draft brief.\nNo model call.\n"
                "Research stage stays Explore.",
            )
        if self.view in {"Overview", "Reopen"}:
            title = "Welcome back: your next step is ready" if s.handoff else "What to work on next"
            return (
                title,
                f"NEXT STEP\n{next_step}\n\n"
                f"NEEDS ATTENTION\n{self.attention()}\n\n"
                "RESEARCH MAP\nExplore > Critique > Brief final > Build > Accept > Done\n\n"
                "You are in Explore. A scoped review does not advance the stage.",
                None,
                [("resume", "Resume Task"), ("readiness", "Stage Readiness")],
                "LATEST OUTPUTS\n\n"
                f"Brief: {'saved in demo' if s.brief else 'draft'}\n"
                f"Review: {'sample output' if s.reviewed else 'not started'}\n"
                f"Issue: {'open' if s.issue else 'not recorded'}\n"
                f"Plan: {'saved in demo' if s.plan else 'not saved'}\n"
                "Verified evidence: none\n\nNo gate decision has been made.",
            )
        if self.view == "Explore":
            return (
                "Define the comparison",
                "What would make the cache-on/off comparison fair?\n\n"
                "SAMPLE ASSISTANT\nUse the same workload and concurrency. Specify warm-up, "
                "hit rate and a result that would refute the idea.\n\n"
                "Edit the working brief below. Navigation retains edits in this demo.",
                s.working_brief,
                [("save-brief", "Save Brief"), ("go-review", "Prepare Review")],
                "SAVED BRIEF\n\n"
                + (s.brief or "No brief published yet.")
                + "\n\nSaving publishes the edited brief; it does not establish the claim.",
            )
        if self.view == "Review":
            if not s.brief:
                return (
                    "A review needs a saved brief",
                    "Save a brief before selecting a statement.",
                    None,
                    [("explore", "Write Brief")],
                    "No review input has been selected.",
                )
            if not s.statement:
                return (
                    "Choose what should be challenged",
                    "PROPOSED STATEMENT\n" + STATEMENT + "\n\n"
                    "Why keep it separately? Evidence and objections can target "
                    "this exact wording.\n\n"
                    "The sample offers one statement. It remains unproven.",
                    None,
                    [("statement", "Save Statement"), ("explore", "Edit Brief")],
                    "SOURCE\nSaved brief / comparison\n\nG1 coverage is incomplete:\n"
                    "magnitude and novelty remain unknown. An exploratory review is still useful.",
                )
            if s.reviewed:
                return (
                    "Review output is available",
                    "1 sample output; no new model calls.\n\n"
                    + ISSUE
                    + ("\n\nSTALE INPUT: the brief changed after this review." if s.stale else "")
                    + "\n\nA saved review is not a resolved issue or a gate decision.",
                    None,
                    [("resolve", "Inspect Suggestion"), ("explore", "Return to Explore")],
                    "REVIEW INPUT SNAPSHOT\n\n" + s.review_brief,
                )
            return (
                "Check the review plan",
                "REVIEWER\nSkeptic / fixed sample answer\n\n"
                "INPUTS\nSaved brief + selected statement"
                "\n\nEXCLUDED\nExploration conversation and other reviews\n\n"
                "1 simulated session; no quota use. Formal G1 remains unmet.",
                None,
                [("run-review", "Start Sample Review"), ("explore", "Edit Brief")],
                "SELECTED STATEMENT\n\n"
                + STATEMENT
                + "\n\nResult: archived-output simulation only. No issue is created automatically.",
            )
        if self.view == "Resolve":
            if not s.reviewed:
                return (
                    "No review suggestions yet",
                    "Prepare a scoped review first.",
                    None,
                    [("go-review", "Prepare Review")],
                    "No issue is inferred from an empty list.",
                )
            return (
                "Plan a response to the issue"
                if s.issue
                else "Does this suggestion need tracking?",
                ISSUE
                + "\n\nWHY IT MATTERS\nWithout these controls, the comparison may mislead.\n\n"
                + (
                    "RECORDED ISSUE: O-001 / Major / Open\n"
                    "A plan or response alone will not close it."
                    if s.issue
                    else "UNTRIAGED SUGGESTION\nRecord it as an open issue, or leave it pending."
                )
                + ("\n\nThe source review used an earlier brief." if s.stale else ""),
                None,
                (
                    [("validate", "Plan a Test"), ("explore", "Return to Explore")]
                    if s.issue
                    else [("record", "Record Issue"), ("overview", "Leave Pending")]
                ),
                "SOURCE TRAIL\n\nR-001 / draft-1\n  -> C-001 (proposed)\n"
                + ("  -> O-001 (open)\n" if s.issue else "  -> not yet an Objection\n")
                + "\nVerified evidence: none\nDecision: none\n\nAll IDs here are sample labels.",
            )
        if self.view == "Validate":
            if not s.issue:
                return (
                    "Choose a question to validate",
                    "This walkthrough plans a test for O-001.",
                    None,
                    [("resolve", "Inspect Review")],
                    "No experiment has run.",
                )
            return (
                "Make the uncertainty testable",
                "Define the conditions that would change your mind.\n"
                + ("PLAN SAVED IN DEMO. Next: run it outside Toulmin.\n" if s.plan else "")
                + "Saving this plan leaves O-001 open; it creates no evidence.",
                s.working_plan,
                [("save-plan", "Save Test Plan"), ("resolve", "Back to Issue")],
                "TARGET\n\nC-001: "
                + STATEMENT
                + "\n\nO-001: warm-up and hit rate\n\nPlan != result != verified evidence"
                "\n\nResult recording and stage rulings are outside this wireframe.",
            )
        if self.view == "Readiness":
            return (
                "G1: ready for formal Critique?",
                "NEEDS JUDGMENT\nProblem: described, not established\n"
                "Mechanism: one proposed statement\n\nMISSING\nMagnitude estimate\n"
                "Novelty comparison\n\nNo advance action is offered. Keep exploring or run a "
                "scoped review. Visiting Review does not change the stage.",
                None,
                [("explore", "Keep Exploring"), ("overview", "Back to Overview")],
                "GATE AUTHORITY\n\nThe researcher makes a separate recorded Decision.\n\n"
                "This sample never advances PROJECT.stage.",
            )
        if self.view == "Handoff":
            return (
                "Leave a useful next step",
                "REVIEW BEFORE SAVING\n" + self.attention() + "\n\n"
                "Edit the next action below. Save + Preview Reopen demonstrates the next "
                "session in memory; it does not write a real handoff.",
                s.next_step or s.recommendation[0],
                [("save-handoff", "Save + Preview Reopen"), ("overview", "Keep Working")],
                "SESSION BOUNDARY\n\nUnresolved issues stay open.\n"
                "No stage changes.\nNo Git commit."
                "\n\nCtrl+Q exits and discards this entire simulation.",
            )
        raise ValueError(self.view)

    def attention(self) -> str:
        s = self.sample
        if s.issue:
            return "O-001 is open. " + (
                "A test is planned; no results yet."
                if s.plan
                else "Warm-up and hit rate need a plan."
            )
        if s.reviewed:
            return "1 review suggestion needs your decision; no Objection recorded."
        return "Magnitude and novelty are unknown. Nothing has been verified."

    async def show(self, view: str) -> None:
        self.retain_edit()
        self.view = view
        self.context_open = False
        self.remove_class("context-open")
        title, body, editor, actions, context = self.page()
        content = self.query_one("#content", VerticalScroll)
        buttons = self.query_one("#actions", Horizontal)
        await content.remove_children()
        await buttons.remove_children()
        await content.mount(Label(title), Static(body, markup=False))
        if editor is not None:
            await content.mount(TextArea(editor, id="editor", tab_behavior="focus"))
        await buttons.mount(
            *[
                Button(label, id=key, variant="primary" if i == 0 else "default", compact=True)
                for i, (key, label) in enumerate(actions)
            ]
        )
        self.query_one("#context-text", Static).update(context)
        self.query_one("#status", Static).update("DEMO: memory only / no models  |  Stage: Explore")
        self.layout_controls()
        if view in VIEWS:
            self.query_one("#selector", Select).value = view
        content.scroll_home(animate=False)
        self.query_one(f"#{actions[0][0]}", Button).focus()

    @on(Select.Changed, "#selector")
    async def select_view(self, event: Select.Changed) -> None:
        if isinstance(event.value, str) and event.value != self.view and self.sample.created:
            await self.show(event.value)

    @on(Button.Pressed)
    async def pressed(self, event: Button.Pressed) -> None:
        key = event.button.id or ""
        s = self.sample
        if key.startswith("nav-"):
            await self.show(key[4:].title())
            return
        targets = {
            "create": "Setup",
            "home": "Home",
            "project-home": "Home",
            "open": "Overview",
            "overview": "Overview",
            "explore": "Explore",
            "go-review": "Review",
            "resolve": "Resolve",
            "validate": "Validate",
            "readiness": "Readiness",
            "end-session": "Handoff",
        }
        if key in targets:
            if key == "create":
                self.sample = Sample()
            await self.show(targets[key])
        elif key == "context-button":
            self.action_context()
        elif key == "initialize":
            s.created = True
            await self.show("Overview")
        elif key == "resume":
            await self.show(s.recommendation[1])
        elif key in {"save-brief", "save-plan", "save-handoff"}:
            self.retain_edit()
            value = self.query_one("#editor", TextArea).text.strip()
            if not value:
                self.notify("Write a nonempty value before saving.", severity="warning")
                return
            if key == "save-brief":
                s.brief = value
                await self.show("Review")
            elif key == "save-plan":
                s.plan = value
                await self.show("Validate")
            else:
                s.next_step = value
                s.resume_view = s.recommendation[1]
                s.handoff = True
                await self.show("Reopen")
        elif key == "statement":
            s.statement = True
            await self.show("Review")
        elif key == "run-review":
            s.review_brief = s.brief
            await self.show("Resolve")
        elif key == "record":
            s.issue = True
            await self.show("Resolve")

    def action_context(self) -> None:
        if not self.has_class("medium"):
            self.query_one("#context").focus()
            return
        self.context_open = not self.context_open
        if self.context_open:
            self.return_focus = self.focused.id if self.focused else None
        self.set_class(self.context_open, "context-open")
        if self.context_open:
            self.query_one("#context", VerticalScroll).focus()
        elif self.return_focus:
            matches = self.query(f"#{self.return_focus}")
            if matches:
                matches.first().focus()

    async def action_overview(self) -> None:
        if self.context_open:
            self.action_context()
        elif self.sample.created:
            await self.show("Overview")


if __name__ == "__main__":
    GuidedWorkbench().run()
