"""Disposable UI-R3 inquiry walkthrough: in-memory sample data, no model or project writes."""

from dataclasses import dataclass, field

from textual import events, on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Footer, Label, Select, Static, TextArea

VIEWS = ("Overview", "Explore", "Review", "Resolve", "Validate")
INITIAL_BRIEF = (
    "Observation: some repeated queries are slow (reported, not verified).\n\n"
    "Possible explanation: repeated computation. Alternatives: I/O or locks.\n"
    "Question: where is the time actually spent? No caching benefit is established."
)
STATEMENT = "Caching repeated reads reduces p95 latency under equal load."
ISSUE = "Cache warm-up and hit rate are unspecified."


HYPOTHESES = (
    "H1: repeated computation dominates; inspect CPU stacks.\n"
    "H2: I/O waits dominate; inspect wait-time attribution.\n"
    "H3: lock contention dominates; inspect blocked stacks.\n"
    "These are competing explanations, not established Claims."
)
CHECKS = {
    "data": (
        "Inspect existing data",
        "Existing traces may distinguish CPU work from waiting.",
        "Inspect a representative slow-query trace.\n"
        "Compare CPU stacks, I/O waits and lock waits.\n"
        "Change direction if repeated computation is not prominent.",
    ),
    "papers": (
        "Read related work",
        "A known baseline may already address repeated queries.",
        "Find the closest approach to repeated-query reuse.\n"
        "Check its workload assumptions and baseline in the original source.\n"
        "Change direction if our claimed difference is already covered.",
    ),
    "experiment": (
        "Plan a small test",
        "A controlled comparison can separate hypotheses.",
        "Hold workload and concurrency fixed; measure CPU and wait time.\n"
        "Repeat the comparison and inspect variability.\n"
        "Change direction if the proposed effect disappears under controls.",
    ),
}
MATERIALS = {
    "data": (
        "Sample A: repeated-computation stacks are prominent; I/O and lock waits are rare.\n"
        "Limit: one short trace. This does not prove caching would help.",
        "Sample B: I/O waits are prominent; repeated-computation stacks are rare.\n"
        "Limit: one short trace. Consider I/O before a computation cache.",
        "Sample C: mixed stacks with too few samples for attribution.\n"
        "Limit: current data cannot distinguish the explanations.",
    ),
    "papers": (
        "Fictional note A: an earlier approach reuses repeated computation.\n"
        "Check its assumptions before choosing a baseline. This is not a real citation.",
        "Fictional note B: the closest approach addresses I/O waits, not computation.\n"
        "Its relevance depends on our workload. This is not a real citation.",
        "Fictional note C: the source is unavailable; only a summary exists.\n"
        "Do not infer novelty from an unchecked summary. This is not a real citation.",
    ),
    "experiment": (
        "Sample A: repeated CPU work decreases under the control; latency is still noisy.\n"
        "Repeat the test before attributing a latency improvement.",
        "Sample B: removing repeated work leaves latency unchanged; I/O waits dominate.\n"
        "The original explanation may not account for the slowdown.",
        "Sample C: workload and concurrency differed between runs.\n"
        "This comparison cannot support a causal interpretation.",
    ),
}


@dataclass
class Sample:
    created: bool = False
    brief: str = ""
    working_brief: str = INITIAL_BRIEF
    statement: bool = False
    review_brief: str = ""
    issue: bool = False
    plan: str = ""
    working_plan: str = ""
    next_step: str = ""
    handoff: bool = False
    resume_view: str = "Explore"
    hypotheses: str = ""
    working_hypotheses: str = HYPOTHESES
    feedback: str = ""
    working_feedback: str = ""
    choice: str = ""
    material_index: int = 0
    material_loaded: bool = False
    material_plan: str = ""
    interpretation: str = ""
    interpretation_source: str = ""
    interpretation_plan: str = ""
    reasoning: str = ""
    working_reasoning: str = ""
    history: list[str] = field(default_factory=list)

    @property
    def material(self) -> str:
        return MATERIALS[self.choice][self.material_index] if self.choice else ""

    @property
    def current_interpretation(self) -> str:
        if (
            self.material_plan == self.plan == self.interpretation_plan
            and self.interpretation_source == self.material
        ):
            return self.interpretation
        return ""

    @property
    def interpretation_label(self) -> str:
        return {
            "lead": "Promising lead; needs testing",
            "redirect": "Reconsider the explanation",
            "uncertain": "Insufficient material",
        }.get(self.current_interpretation, "Needs your judgment")

    @property
    def uncertainty(self) -> str:
        if self.current_interpretation == "lead":
            return "Does this lead survive a representative, controlled comparison?"
        if self.current_interpretation == "redirect":
            return "Which alternative better explains the observed slowdown?"
        if self.current_interpretation == "uncertain":
            return "What additional material would distinguish the explanations?"
        return "Repeated computation, I/O or locks: where is time actually spent?"

    @property
    def why(self) -> str:
        if self.current_interpretation:
            return "Your rationale: " + self.reasoning
        if self.choice:
            return CHECKS[self.choice][1]
        return "A cache is premature until the cause of the slowdown is better understood."

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
        if self.reviewed and not self.issue:
            return "Decide whether the reviewer suggestion needs tracking.", "Resolve"
        if self.current_interpretation == "lead":
            return "Design a controlled follow-up; a promising lead is not a conclusion.", "Actions"
        if self.current_interpretation == "redirect":
            return "Revisit the competing explanations before pursuing caching.", "Hypotheses"
        if self.current_interpretation == "uncertain":
            return "Choose a better source or a more discriminating check.", "Actions"
        if self.material_loaded and self.material_plan == self.plan:
            return "Inspect the material and record your interpretation.", "Material"
        if self.choice and self.plan:
            return "Carry out the check; preview sample material in this demo.", "Material"
        if self.choice:
            return "Specify the smallest check and what would change your mind.", "Validate"
        if self.hypotheses:
            return "Choose an inexpensive check to distinguish the explanations.", "Actions"
        return "Separate the reported observation from possible explanations.", "Explore"


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

    @property
    def work_view(self) -> str:
        return {
            "Reopen": "Overview",
            "Readiness": "Overview",
            "Handoff": "Overview",
            "Hypotheses": "Explore",
            "Feedback": "Explore",
            "Actions": "Explore",
            "Material": "Validate",
            "Interpret": "Validate",
        }.get(self.view, self.view)

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
            self.query_one(f"#nav-{name.lower()}").set_class(self.work_view == name, "current")

    def retain_edit(self) -> None:
        editors = self.query("#editor")
        if not editors:
            return
        value = self.query_one("#editor", TextArea).text
        if self.view == "Explore":
            self.sample.working_brief = value
        elif self.view == "Validate":
            self.sample.working_plan = value
        elif self.view == "Hypotheses":
            self.sample.working_hypotheses = value
        elif self.view == "Feedback":
            self.sample.working_feedback = value
        elif self.view == "Interpret":
            self.sample.working_reasoning = value
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
                "SAMPLE CASE\n\nWhy are some repeated queries slow?\n\n"
                "No models, project files or experimental results are used.",
            )
        if self.view == "Setup":
            return (
                "Start with a question",
                "PROJECT\ncache-study\n\nGOAL\nUnderstand the cause of slow repeated queries.\n\n"
                "MOTIVATION\nRepeated computation is only one possible explanation.\n\n"
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
                f"KEY UNKNOWN\n{s.uncertainty}\n\n"
                f"NEXT STEP\n{next_step}\nWHY\n{s.why}\n\n"
                f"NEEDS ATTENTION\n{self.attention()}\n\n"
                "RESEARCH MAP\nExplore > Critique > Brief final > Build > Accept > Done\n\n"
                "You are in Explore. A scoped review does not advance the stage.",
                None,
                [
                    ("resume", "Resume Task"),
                    ("choose-action", "Other Actions"),
                    ("readiness", "Readiness"),
                ],
                "LATEST OUTPUTS\n\n"
                f"Brief: {'saved in demo' if s.brief else 'draft'}\n"
                f"Review: {'sample output' if s.reviewed else 'not started'}\n"
                f"Issue: {'open' if s.issue else 'not recorded'}\n"
                f"Plan: {'saved in demo' if s.plan else 'not saved'}\n"
                f"Material: {'fixture only' if s.material_loaded else 'none'}\n"
                f"Interpretation: {s.interpretation_label}\n"
                "Verified evidence: none\n\nNo gate decision has been made.",
            )
        if self.view == "Explore":
            return (
                "What was observed, and what is only an explanation?",
                "REPORTED OBSERVATION: some repeated queries are slow.\n"
                "A computation cache is one possible approach, not the starting conclusion.\n\n"
                + ("BRIEF SAVED IN DEMO. Keep exploring or choose a check.\n\n" if s.brief else "")
                + "Edit the observation, assumptions and open questions. Saving stays here.",
                s.working_brief,
                [
                    ("save-brief", "Save Brief"),
                    ("hypotheses", "Compare Ideas"),
                    ("choose-action", "Other Actions"),
                ],
                "CURRENT BASIS\nReported observation only; no real measurements.\n\n"
                "AI HELP\nCompare Ideas shows a fixed sample suggestion. You can edit it or "
                "record a correction.\n\n"
                + ("YOUR FEEDBACK\n" + s.feedback if s.feedback else "No feedback recorded yet."),
            )
        if self.view == "Hypotheses":
            return (
                "Compare explanations before choosing a solution",
                "SAMPLE AI SUGGESTION / not generated from your edits\n"
                "Inspect the alternatives below. Remove unsuitable ones or add your own.\n"
                + (
                    "Your correction is retained in Context; revise the draft accordingly.\n"
                    if s.feedback
                    else ""
                )
                + "Save records your working hypotheses, not formal Claims or evidence.",
                s.working_hypotheses,
                [
                    ("save-hypotheses", "Save Ideas"),
                    ("feedback", "Give Feedback"),
                    ("choose-action", "Choose Check"),
                ],
                "CONTEXT FOR DISCUSSION\n"
                + (s.brief or s.working_brief)
                + "\n\nYOUR FEEDBACK\n"
                + (s.feedback or "None yet.")
                + "\n\nNo model is called; edits and corrections are yours.",
            )
        if self.view == "Feedback":
            return (
                "Correct the interpretation or add a constraint",
                "For example: this workload is disk-bound, or a new experiment is too costly.\n"
                "The demo retains your exact words beside the hypotheses. No AI revision is "
                "invented; edit the proposal yourself after recording the feedback.",
                s.working_feedback,
                [("save-feedback", "Record Feedback"), ("hypotheses", "Back to Ideas")],
                "FEEDBACK EFFECT\nChanges discussion context only.\n"
                "It does not change a Claim, evidence grade or research stage.",
            )
        if self.view == "Actions":
            return (
                "Choose how to reduce the uncertainty",
                s.uncertainty + "\n\n"
                "INSPECT DATA: use existing traces before collecting more.\n\n"
                "READ PAPERS: check what is known and identify a meaningful baseline.\n\n"
                "SMALL TEST: hold conditions fixed and distinguish explanations.\n\n"
                "Review remains available in the navigation, but is not required. "
                "Selecting a new check starts a new draft; earlier notes remain in Context.",
                None,
                [
                    ("check-data", "Inspect Data"),
                    ("check-papers", "Read Papers"),
                    ("check-experiment", "Small Test"),
                ],
                "YOUR CHOICE\nPlans need no Claim or reviewer first.\n\n"
                + s.why
                + "\n\nRECENT NOTES\n"
                + ("\n\n".join(s.history[-3:]) or "None yet."),
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
            if not s.choice:
                return (
                    "Choose a small check, even before review",
                    "Start from data, related work or a small experiment. "
                    "No Objection is required.",
                    None,
                    [("choose-action", "Choose Check"), ("explore", "Back to Explore")],
                    "VALIDATION IS EARLY WORK\n"
                    "A check can change which question is worth pursuing.",
                )
            return (
                CHECKS[s.choice][0],
                "Define the source, comparison and result that would change your direction.\n"
                + (
                    "PLAN SAVED IN DEMO. Use Sample Material to illustrate the next step.\n"
                    if s.plan
                    else ""
                )
                + "A saved plan establishes no result. Any recorded issue stays open.",
                s.working_plan,
                (
                    [
                        ("material", "Sample Material"),
                        ("save-plan", "Save Plan"),
                        ("choose-action", "Other Check"),
                    ]
                    if s.plan
                    else [("save-plan", "Save Plan"), ("choose-action", "Other Check")]
                ),
                "WHY THIS CHECK\n"
                + CHECKS[s.choice][1]
                + "\n\nTARGET UNKNOWN\n"
                + s.uncertainty
                + "\n\nNo experiment runs here. Sample materials are fictional, not evidence.",
            )
        if self.view == "Material":
            if not s.plan:
                return (
                    "A check needs a plan",
                    "Choose or save the check before viewing fixtures.",
                    None,
                    [("validate", "Plan Check")],
                    "No material has been evaluated.",
                )
            return (
                "Inspect the material before drawing a conclusion",
                "FICTIONAL MATERIAL / not a measurement or verified source\n\n"
                + s.material
                + "\n\nTry another fixture to explore a different outcome. "
                "Interpretation is your choice; the fixture never updates it automatically.",
                None,
                [
                    ("interpret", "Interpret"),
                    ("cycle-material", "Other Fixture"),
                    ("validate", "Back to Plan"),
                ],
                "APPROVED SAMPLE PLAN\n" + s.plan + "\n\n"
                "CURRENT INTERPRETATION\n"
                + s.interpretation_label
                + "\n\nVerified evidence: none\nStage: Explore",
            )
        if self.view == "Interpret":
            return (
                "What does this material justify doing next?",
                "Write your reason and remaining uncertainty, then choose.\n"
                "A promising lead needs another check; changing direction is a valid outcome.\n"
                "Insufficient material is not a failure. No formal research status changes.",
                s.working_reasoning,
                [
                    ("judge-lead", "Test This Lead"),
                    ("judge-redirect", "Change Direction"),
                    ("judge-uncertain", "Need More Data"),
                ],
                "MATERIAL UNDER REVIEW\n"
                + s.material
                + "\n\nRecord a researcher's interpretation, not an AI verdict.",
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
                "Include why this action matters and what result would change direction. "
                "Save + Preview Reopen demonstrates the next "
                "session in memory; it does not write a real handoff.",
                s.next_step
                or (
                    s.recommendation[0]
                    + "\nWhy: "
                    + s.why
                    + "\nChange direction if: not yet specified in this handoff."
                ),
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
        return (
            "Your interpretation: " + s.interpretation_label + ". "
            if s.current_interpretation
            else "The cause is not established. "
        ) + "Magnitude and novelty remain unknown; verified evidence: none."

    async def show(self, view: str) -> None:
        self.retain_edit()
        self.view = view
        if view == "Material" and self.sample.plan:
            self.sample.material_loaded = True
            self.sample.material_plan = self.sample.plan
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
        if self.work_view in VIEWS:
            self.query_one("#selector", Select).value = self.work_view
        content.scroll_home(animate=False)
        self.query_one(f"#{actions[0][0]}", Button).focus()

    @on(Select.Changed, "#selector")
    async def select_view(self, event: Select.Changed) -> None:
        if isinstance(event.value, str) and event.value != self.work_view and self.sample.created:
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
            "hypotheses": "Hypotheses",
            "feedback": "Feedback",
            "choose-action": "Actions",
            "material": "Material",
            "interpret": "Interpret",
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
        elif key.startswith("check-"):
            self.retain_edit()
            if s.choice:
                s.history.append("Earlier " + CHECKS[s.choice][0] + ": " + s.working_plan)
            s.choice = key[6:]
            s.working_plan = CHECKS[s.choice][2]
            s.plan = ""
            s.material_loaded = False
            s.material_plan = ""
            s.interpretation_source = ""
            s.material_index = 0
            s.handoff = False
            s.next_step = ""
            await self.show("Validate")
        elif key == "cycle-material":
            s.material_index = (s.material_index + 1) % len(MATERIALS[s.choice])
            s.handoff = False
            await self.show("Material")
        elif key.startswith("judge-"):
            self.retain_edit()
            if not s.working_reasoning.strip():
                self.notify("Record your reason before choosing a direction.", severity="warning")
                return
            s.interpretation = key[6:]
            s.interpretation_source = s.material
            s.interpretation_plan = s.plan
            s.reasoning = s.working_reasoning.strip()
            s.history.append(
                s.material + "\nYour choice: " + s.interpretation + "\nReason: " + s.reasoning
            )
            s.handoff = False
            s.next_step = ""
            await self.show("Overview")
        elif key == "resume":
            await self.show(s.recommendation[1])
        elif key in {"save-brief", "save-plan", "save-handoff", "save-hypotheses", "save-feedback"}:
            self.retain_edit()
            value = self.query_one("#editor", TextArea).text.strip()
            if not value:
                self.notify("Write a nonempty value before saving.", severity="warning")
                return
            if key == "save-brief":
                s.brief = value
                await self.show("Explore")
            elif key == "save-plan":
                s.plan = value
                await self.show("Validate")
            elif key == "save-hypotheses":
                s.hypotheses = value
                await self.show("Hypotheses")
            elif key == "save-feedback":
                s.feedback = value
                await self.show("Hypotheses")
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
