"""R3/R4: decide closes the loop (next moves, optional session notice) and suggests a handoff
and a fresh session after a stage ruling. Temporary workbenches and fake sessions only."""

import shlex
import sys
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from toulmin.cli import decide
from toulmin.cli.app import app
from toulmin.protocols.handoff import apply_handoff, draft_handoff
from toulmin.protocols.research_map import research_map

FOLDER = "projects/demo/runs/proposals"
CLAIM = (
    "---\nschema_version: 1\nstatus: proposed\ntype: mechanism\nimportance: core\n"
    "source: {kind: human, actor: Agent}\n---\n## Statement\nSRPT cuts p99 under bursts.\n"
)
DECISION = (
    "---\nschema_version: 1\nstatus: active\nsource: {kind: human, actor: Agent}\n"
    "related: [C-001]\n---\n## Context\nCore Claims written.\n\n## Choice\nEnter critique.\n\n"
    "## Rejected alternatives\nKeep exploring.\n\n## Rationale\nReady to be attacked.\n"
)
STAGE = (
    "---\nschema_version: 1\nkind: stage-proposal\nfrom: explore\nto: critique\n"
    "decision: decision-20261109T100000Z-critique.md\n---\n## Why\nTime to attack them.\n"
)


@pytest.fixture(autouse=True)
def researcher(monkeypatch):
    monkeypatch.delenv("TOULMIN_ACTOR", raising=False)
    monkeypatch.setattr(decide, "_interactive", lambda: True)


class Sessions:
    """Stands in for AoEWorkspace: records notices, never reaches AoE."""

    def __init__(self, bound=True, ready=True):
        self.bound, self.ready, self.sent = bound, ready, []

    def __call__(self, root, project):
        sessions = self

        class Workspace:
            def bound_session(self):
                if not sessions.bound:
                    return None
                return SimpleNamespace(profile="sim", session_id="a" * 16, agent="codex")

            def notify(self, message):
                if not sessions.ready:
                    return False, "Native input contains text"
                sessions.sent.append((project, message))
                return True, "sent to codex session " + "a" * 16

        return Workspace()


def put(root, name, text):
    folder = root / FOLDER
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(text)


def run(root, answers, *flags):
    args = ["decide", "--root", str(root), "--confirmed-by", "Researcher", *flags]
    return CliRunner().invoke(app, args, input=answers)


def test_decide_ends_with_next_moves_and_no_prompt_without_a_session(populated, monkeypatch):
    sessions = Sessions(bound=False)
    monkeypatch.setattr(decide, "AoEWorkspace", sessions)
    put(populated, "claim-20261109T100000Z-srpt.md", CLAIM)
    result = run(populated, "a\n")
    assert result.exit_code == 0, result.output
    assert "Next for demo (advice; you rule):" in result.stdout
    moves = research_map(populated, "demo").moves
    assert all(move.text in result.stdout for move in moves)
    assert "Tell the demo session" not in result.stdout and not sessions.sent


@pytest.mark.parametrize(
    ("answers", "flags", "sent"),
    [("a\ny\n", (), True), ("a\nn\n", (), False), ("a\n", ("--no-notify",), False),
     ("a\n", ("--notify",), True)],
)  # fmt: skip
def test_the_notice_is_the_researchers_choice(populated, monkeypatch, answers, flags, sent):
    sessions = Sessions()
    monkeypatch.setattr(decide, "AoEWorkspace", sessions)
    put(populated, "claim-20261109T100000Z-srpt.md", CLAIM)
    result = run(populated, answers, *flags)
    assert result.exit_code == 0, result.output
    assert ("Tell the demo session what you decided" in result.stdout) == (not flags)
    assert bool(sessions.sent) == sent
    if sent:
        project, message = sessions.sent[0]
        assert project == "demo" and "\n" not in message
        assert "applied claim-20261109T100000Z-srpt.md (C-002)" in message
        assert "Notice sent to codex session" in result.stdout


def test_a_busy_session_gets_no_notice_and_the_researcher_is_told(populated, monkeypatch):
    monkeypatch.setattr(decide, "AoEWorkspace", Sessions(ready=False))
    put(populated, "claim-20261109T100000Z-srpt.md", CLAIM)
    result = run(populated, "a\n", "--notify")
    assert "Notice not sent: Native input contains text. Tell the agent yourself." in result.stdout


def test_a_stage_ruling_suggests_a_handoff_and_a_fresh_session(populated, monkeypatch):
    sessions = Sessions()
    monkeypatch.setattr(decide, "AoEWorkspace", sessions)
    put(populated, "decision-20261109T100000Z-critique.md", DECISION)
    put(populated, "stage-20261109T100001Z-critique.md", STAGE)
    result = run(populated, "a\na\n", "--notify")
    assert result.exit_code == 0, result.output
    assert "Stage is now critique. Suggested before the next stage's work:" in result.stdout
    assert (
        "aoe -p sim session archive aaaaaaaaaaaaaaaa, then toulmin open demo --new-session"
        in result.stdout
    )
    moves = research_map(populated, "demo").moves
    assert moves[0].text.startswith("The stage critique is past G1")  # R5: the fixture lacks G1
    assert moves[1].text.startswith("Prepare a handoff draft: the stage changed to critique")
    message = sessions.sent[0][1]
    assert "The stage is now critique: prepare a handoff draft now" in message
    prefix = shlex.join([sys.executable, "-m", "toulmin"])
    assert f"`{prefix} aoe handoff demo --root " in message


def test_the_handoff_row_clears_once_a_handoff_is_applied_after_the_stage(populated, monkeypatch):
    monkeypatch.setattr(decide, "AoEWorkspace", Sessions(bound=False))
    put(populated, "decision-20261109T100000Z-critique.md", DECISION)
    put(populated, "stage-20261109T100001Z-critique.md", STAGE)
    run(populated, "a\na\n")
    assert any(
        move.text.startswith("Prepare a handoff draft")
        for move in research_map(populated, "demo").moves
    )
    draft = draft_handoff(populated, "demo").relative_to(populated).as_posix()
    apply_handoff(populated, "demo", draft, "Researcher", True)
    report = research_map(populated, "demo")
    assert not report.errors
    assert not any(move.text.startswith("Prepare a handoff draft") for move in report.moves)


def test_a_long_notice_stays_one_line():
    notes = [f"applied claim-{index}.md (C-{index:03d})" for index in range(12)]
    message = decide.notice(decide.Path("/w"), "demo", notes, None)
    assert "\n" not in message and "and 4 more" in message and "C-008" not in message
