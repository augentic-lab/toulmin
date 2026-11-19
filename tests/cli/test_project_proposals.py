"""H3: object drafts and ruling proposals decided in ``toulmin decide``; temporary files only."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from toulmin.cli import decide
from toulmin.cli.app import app
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError
from toulmin.core.identifiers import ObjectKind
from toulmin.core.project_proposals import (
    Outcome,
    render_outcome,
    validate_outcome,
    validate_ruling_proposal,
)
from toulmin.protocols import project_proposals
from toulmin.protocols.intake import create_object
from toulmin.protocols.research_workspace import render_state, research_state

FOLDER = "projects/demo/runs/proposals"
CLAIM = (
    "---\nschema_version: 1\nstatus: proposed\ntype: mechanism\nimportance: core\n"
    "source: {kind: human, actor: Agent}\n---\n"
    "## Statement\nSRPT reduces tail latency under bursty arrivals.\n\n"
    "## Scope\nSingle GPU serving.\n"
)
DECISION = (
    "---\nschema_version: 1\nstatus: active\nsource: {kind: human, actor: Agent}\n"
    "related: [O-001]\n---\n## Context\nThe objection was discussed.\n\n"
    "## Choice\nAnswer it with the drift experiment.\n\n## Rejected alternatives\nDefer it.\n\n"
    "## Rationale\nThe experiment addresses the drift case directly.\n"
)


def ruling(decision="decision-20261105T100000Z-answer.md", why="The drift run answers it."):
    return (
        "---\nschema_version: 1\nkind: ruling-proposal\nobject: O-001\nstatus: answered\n"
        f"decision: {decision}\n---\n## Why\n{why}\n\n## Response\n"
        "The drift experiment covers the drifting workload.\n"
    )


def put(root, name, text):
    folder = root / FOLDER
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(text)
    return f"{FOLDER}/{name}"


def snapshot(root):
    return {path: path.read_bytes() for path in Path(root).rglob("*") if path.is_file()}


def outcome(root, relative):
    path = root / project_proposals.outcome_path(relative)
    return validate_outcome(decode(path.read_bytes(), str(path)))


@pytest.fixture(autouse=True)
def researcher(monkeypatch):
    monkeypatch.delenv("TOULMIN_ACTOR", raising=False)
    monkeypatch.setattr(decide, "_interactive", lambda: True)


def run(root, answers=""):
    args = ["decide", "--root", str(root), "--confirmed-by", "Researcher"]
    return CliRunner().invoke(app, args, input=answers)


def test_ruling_proposal_format_is_checked():
    def check(text):
        return validate_ruling_proposal(decode(text.encode(), "ruling.md"))

    parsed = check(ruling())
    assert parsed.object == "O-001" and parsed.status == "answered"
    assert set(parsed.texts) == {"Response"} and "drift run" in parsed.why
    with pytest.raises(FormatError, match="body.Why"):
        check(ruling(why=""))
    with pytest.raises(FormatError, match="body.Content"):
        check(ruling() + "\n## Content\nNot a ruling section.\n")
    with pytest.raises(FormatError, match="nothing to rule"):
        check("---\nschema_version: 1\nkind: ruling-proposal\nobject: O-001\n---\n## Why\nx\n")


def test_an_object_draft_is_created_only_when_applied(populated):
    relative = put(populated, "claim-20261105T100000Z-srpt.md", CLAIM)
    before = snapshot(populated)
    state = research_state(populated, "demo")
    assert state.proposals == (relative,) and state.errors == ()
    card = render_state(state)
    assert (
        "PROPOSALS\n" in card
        and "- Researcher: Run `toulmin decide` for 1 pending proposal(s)." in card
    )
    assert relative not in state.draft_files
    result = run(populated, "s\n")
    assert "Object draft: " + relative in result.stdout
    assert "New Claim · core mechanism" in result.stdout
    assert "Effect    creates C-002 (proposed); nothing else changes" in result.stdout
    assert snapshot(populated) == before  # preview and skip write nothing
    result = run(populated, "a\n")
    assert result.exit_code == 0, result.output
    assert "Created: C-002" in result.stdout
    created = decode((populated / "projects/demo/claims/C-002.md").read_bytes())
    assert created.header["confirmed_by"]["actor"] == "Researcher"
    recorded = outcome(populated, relative)
    assert (recorded.disposition, recorded.result) == ("applied", "C-002")
    assert recorded.approval_text == "toulmin decide: a"
    assert (populated / relative).read_text() == CLAIM  # the proposal is never edited
    assert "Nothing awaits your decision." in run(populated).stdout
    assert research_state(populated, "demo").proposals == ()


def test_a_rejected_draft_records_the_reason_and_creates_nothing(populated):
    relative = put(populated, "claim-20261105T100000Z.md", CLAIM)
    result = run(populated, "r\nNot the claim we discussed.\n")
    assert result.exit_code == 0, result.output
    assert not (populated / "projects/demo/claims/C-002.md").exists()
    recorded = outcome(populated, relative)
    assert recorded.disposition == "rejected"
    assert recorded.reason == "Not the claim we discussed." and recorded.result is None


def test_an_invalid_draft_offers_no_apply_and_writes_nothing(populated):
    put(
        populated,
        "claim-20261105T100000Z.md",
        CLAIM.replace("status: proposed", "status: supported"),
    )
    put(populated, "notes.md", "scratch\n")
    before = snapshot(populated)
    result = run(populated, "a\ns\n")
    assert "Problem: " in result.stdout and "initial states" in result.stdout
    assert "Choose one of: reject, skip, view all, quit" in result.stdout
    assert f"Not offered: {FOLDER}/notes.md: not named" in result.stdout
    assert snapshot(populated) == before


def test_a_ruling_uses_the_decision_proposal_applied_before_it(populated):
    decision = put(populated, "decision-20261105T100000Z-answer.md", DECISION)
    proposal = put(populated, "ruling-20261105T100001Z-answer.md", ruling())
    result = run(populated, "a\na\n")
    assert result.exit_code == 0, result.output
    assert result.stdout.index("Object draft") < result.stdout.index("Ruling proposal")
    assert "Ruling · O-001: open → answered" in result.stdout
    assert "Effect    status open → answered; adds Response; backed by D-002" in result.stdout
    assert "Created: D-002" in result.stdout and "Ruled: O-001" in result.stdout
    ruled = decode((populated / "projects/demo/objections/O-001.md").read_bytes())
    assert ruled.header["status"] == "answered" and "D-002" in ruled.header["decisions"]
    assert "drift experiment covers" in ruled.body and "drift run answers" not in ruled.body
    assert outcome(populated, decision).result == "D-002"
    assert outcome(populated, proposal).result == "O-001"


def test_a_ruling_waits_while_its_decision_proposal_is_undecided(populated):
    put(populated, "decision-20261105T100000Z-answer.md", DECISION)
    put(populated, "ruling-20261105T100001Z-answer.md", ruling())
    before = snapshot(populated)
    result = run(populated, "s\ns\n")
    assert "is not decided yet; decide it first" in result.stdout
    assert snapshot(populated) == before


def test_apply_refuses_a_proposal_changed_since_the_preview(populated):
    relative = put(populated, "claim-20261105T100000Z.md", CLAIM)
    shown = project_proposals.preview(populated, "demo", relative)
    (populated / relative).write_text(CLAIM.replace("Single GPU", "Two GPU"))
    with pytest.raises(FormatError, match="changed since the preview"):
        project_proposals.apply(populated, "demo", relative, "Researcher", shown.sha256, "a")
    with pytest.raises(FormatError, match="changed since the preview"):
        project_proposals.reject(populated, "demo", relative, "Researcher", "no", shown.sha256)
    assert not (populated / project_proposals.outcome_path(relative)).exists()


def test_an_interrupted_application_is_recorded_not_repeated(populated):
    relative = put(populated, "claim-20261105T100000Z.md", CLAIM)
    sha = project_proposals.preview(populated, "demo", relative).sha256
    marker = Outcome(
        relative, sha, "applying", "Researcher", "2026-11-05T09:00:00Z", "a", None, None
    )
    (populated / project_proposals.outcome_path(relative)).write_bytes(render_outcome(marker))
    create_object(populated, "demo", ObjectKind.CLAIM, relative, "Researcher", True)
    assert research_state(populated, "demo").proposals == (f"{relative} (interrupted application)",)
    with pytest.raises(FormatError, match="interrupted application"):
        project_proposals.reject(populated, "demo", relative, "Researcher", "no", sha)
    result = run(populated, "a\n")
    assert result.exit_code == 0, result.output
    assert "It already produced C-002" in result.stdout
    assert not (populated / "projects/demo/claims/C-003.md").exists()
    assert outcome(populated, relative).result == "C-002"


def test_an_interrupted_application_with_nothing_produced_runs_once(populated):
    relative = put(populated, "claim-20261105T100000Z.md", CLAIM)
    sha = project_proposals.preview(populated, "demo", relative).sha256
    marker = Outcome(
        relative, sha, "applying", "Researcher", "2026-11-05T09:00:00Z", "a", None, None
    )
    (populated / project_proposals.outcome_path(relative)).write_bytes(render_outcome(marker))
    result = run(populated, "a\n")
    assert "Nothing it would have produced was found" in result.stdout
    assert "Created: C-002" in result.stdout
    assert outcome(populated, relative).disposition == "applied"


def test_a_second_decider_cannot_apply_the_same_proposal(populated):
    relative = put(populated, "claim-20261105T100000Z.md", CLAIM)
    sha = project_proposals.preview(populated, "demo", relative).sha256
    project_proposals.apply(populated, "demo", relative, "Researcher", sha, "a")
    with pytest.raises(FormatError, match="already applied"):
        project_proposals.apply(populated, "demo", relative, "Researcher", sha, "a")
    assert not (populated / "projects/demo/claims/C-003.md").exists()


# UX6: summary-first previews.


def test_decide_shows_what_changes_and_v_shows_all_before_applying(populated):
    put(populated, "claim-20261105T100000Z.md", CLAIM)
    result = run(populated, "v\na\n")
    assert result.exit_code == 0, result.output
    summary, _, full = result.stdout.partition("[a]pply / [r]eject / [s]kip / [v]iew all / [q]uit")
    assert "  1  New Claim · core mechanism  (demo)" in summary  # the opening overview
    assert "── [1/1] New Claim · core mechanism ─" in summary
    assert "Statement SRPT reduces tail latency under bursty arrivals." in summary
    assert "Effect    creates C-002 (proposed); nothing else changes" in summary
    assert "## Scope" not in summary and "Single GPU serving." not in summary
    assert "## Scope\nSingle GPU serving." in full  # v printed every line
    assert "Created: C-" in full


def test_a_ruling_shows_the_objection_it_answers(populated):
    decision = (
        "---\nschema_version: 1\nstatus: active\nsource: {kind: human, actor: Agent}\n"
        "related: [O-001]\n---\n## Context\nc\n\n## Choice\nAnswer it.\n\n"
        "## Rejected alternatives\nr\n\n## Rationale\nr\n"
    )
    put(populated, "decision-20261105T100000Z-answer.md", decision)
    put(populated, "ruling-20261105T100001Z-answer.md", ruling())
    result = run(populated, "s\ns\n")
    ruling_screen = result.stdout.split("[2/2]")[1]
    assert "O-001     (major · open · on C-001) " in ruling_screen
    assert "Response  The drift experiment covers the drifting workload." in ruling_screen
    assert "Why       The drift run answers it." in ruling_screen


def test_full_flag_prints_proposals_without_the_view_choice(populated):
    put(populated, "ruling-20261105T100000Z.md", ruling())
    result = CliRunner().invoke(
        app,
        ["decide", "--root", str(populated), "--confirmed-by", "Researcher", "--full"],
        input="s\n",
    )
    assert "## Response\nThe drift experiment covers the drifting workload." in result.stdout
    assert "[v]iew all" not in result.stdout


def test_summary_of_a_ruling_names_its_response_and_why():
    from toulmin.protocols.proposal_summary import proposal_summary

    found = proposal_summary(ruling())
    assert found.facts == (("object", "O-001"), ("status", "answered"))
    assert found.main == ("Response", "The drift experiment covers the drifting workload.")
    assert found.why == "The drift run answers it."
    assert proposal_summary("no front matter\n").facts == ()


def test_decide_colours_headers_and_effects_only_on_a_terminal(monkeypatch):
    from toulmin.cli import decide
    from toulmin.protocols.proposal_view import ProposalView, Row

    view = ProposalView(
        "New Claim", (Row("Statement", "S.", main=True), Row("Effect", "creates C-2"))
    )
    monkeypatch.setattr(decide, "colour_enabled", lambda: False)
    plain = decide.header("[1/2]", "New Claim", "demo", 40)
    assert plain.startswith("── [1/2] New Claim ─") and plain.endswith(" demo") and len(plain) == 40
    assert "\x1b[" not in "".join(decide.view_lines(view, 60))
    monkeypatch.setattr(decide, "colour_enabled", lambda: True)
    assert "\x1b[1m[1/2] New Claim\x1b[0m" in decide.header("[1/2]", "New Claim", "demo", 40)
    assert "\x1b[32mcreates C-2\x1b[0m" in "".join(decide.view_lines(view, 60))


def test_group_apply_lists_each_member_and_records_each_outcome(populated):
    first = put(populated, "claim-20261105T100000Z-a.md", CLAIM)
    second = put(populated, "claim-20261105T100001Z-b.md", CLAIM.replace("SRPT", "FIFO"))
    result = run(populated, "g\ny\n")
    assert result.exit_code == 0, result.output
    assert "g applies this and 1 more alike (listed first)." in result.stdout
    assert "[a]pply / [r]eject / [s]kip / [g]roup apply / [v]iew all / [q]uit" in result.stdout
    assert "Group apply: 2 items, each exactly as previewed:" in result.stdout
    assert "  2. New Claim · core mechanism — creates the next ID (proposed)" in result.stdout
    assert result.stdout.count("Created: C-00") == 2 and "[2/2]" not in result.stdout
    for proposal in (first, second):
        outcome = (populated / project_proposals.outcome_path(proposal)).read_text()
        assert "disposition: applied" in outcome and "toulmin decide: g" in outcome


def test_declining_a_group_decides_the_item_alone(populated):
    put(populated, "claim-20261105T100000Z-a.md", CLAIM)
    put(populated, "claim-20261105T100001Z-b.md", CLAIM.replace("SRPT", "FIFO"))
    before = snapshot(populated)
    result = run(populated, "g\nn\ns\ns\n")
    assert result.exit_code == 0, result.output
    assert "Nothing applied; deciding this item alone." in result.stdout
    assert "Skipped: 2" in result.stdout and snapshot(populated) == before
