"""WI6: reviewed child creation with an initial Brief, provenance and a linked receipt.

Temporary workspaces and a fake AoE client only; no model, network or real project.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toulmin.adapters.aoe import AoEClient, AoEError, AoESession
from toulmin.application.aoe import AoEWorkspace
from toulmin.cli.app import app
from toulmin.cli.initialize import initialize, initialize_workspace
from toulmin.core import workspace_journal
from toulmin.core.atomic import digest
from toulmin.core.documents import FormatError
from toulmin.protocols import project_creation
from toulmin.protocols.project_creation import create, propose, reject
from toulmin.protocols.research_workspace import research_state
from toulmin.protocols.workspace_change import apply as apply_change
from toulmin.protocols.workspace_change import propose as propose_change
from toulmin.protocols.workspace_context import render_workspace, workspace_research
from toulmin.protocols.workspace_handoff import apply as apply_handoff
from toulmin.protocols.workspace_handoff import draft
from toulmin.protocols.workspace_state import workspace_status

runner = CliRunner()
DOCS = Path(__file__).resolve().parents[2] / "docs"
ACTIVITY = "runs/20261104T093000Z-activity-6b1f0c2e9a4d4e7f8c3b2a1d0e9f8a7b/activity.md"
FIRST = "runs/20261104T100000Z-proposal-0d9e8c7b6a5f4e3d2c1b0a9f8e7d6c5b"
CHANGE_PACKET = "runs/20261104T101500Z-proposal-a41c9e07d3b24f5e9b6c8d7e1f203a4b"
CHANGE = "runs/drafts/workspace-direction.md"
TRACE = "shared/data/synthetic-queue-trace"
HANDOFF_INPUT = "runs/drafts/workspace-handoff.md"
HANDOFF_DRAFT = "runs/20261104T113000Z-handoff-5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b"
INPUT = "runs/drafts/project-scheduling.md"
PACKET = "runs/20261104T140000Z-project-c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8"
STAGING = "projects/.creating-c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8"
CHILD = "projects/scheduling"
SID = "a" * 16


def blocks():
    text = (DOCS / "workspace-formats.md").read_text()
    parts = [part.split("\n````", 1)[0] + "\n" for part in text.split("````markdown\n")[1:]]

    def one(*needles, start=""):
        found = [
            part
            for part in parts
            if part.startswith(start) and all(needle in part for needle in needles)
        ]
        assert len(found) == 1, needles
        return found[0].encode()

    return {
        "activity": one("kind: workspace-activity"),
        "change": one("kind: workspace-change-input"),
        "handoff": one("kind: workspace-handoff-input"),
        "input": one("kind: project-creation-input"),
        "packet": one("kind: project-creation\n"),
        "charter": one(start="---\nschema_version: 1\nproject: scheduling\nstage: explore"),
        "record": one("kind: project-creation-record"),
        "receipt": one("kind: workspace-receipt", "project-c3b2a1f0"),
    }


def at(text):
    return datetime.fromisoformat(text.removesuffix("Z")).replace(tzinfo=UTC)


@pytest.fixture
def root(tmp_path):
    """The contract fixture through section 8: direction, trace and one applied handoff."""
    examples = blocks()
    root = tmp_path / "serving"
    initialize_workspace(root, "Serving Research")
    (root / TRACE).mkdir(parents=True)
    (root / TRACE / "trace.csv").write_text("arrival_us,service_us\n0,180\n240,95\n410,620\n")
    (root / TRACE / "README.md").write_text(
        "Synthetic single-queue trace for the WS3 fixture. Not a measurement.\n"
    )
    (root / ACTIVITY).parent.mkdir(parents=True)
    (root / ACTIVITY).write_bytes(examples["activity"])
    data = examples["change"]
    (root / CHANGE).write_bytes(data.replace(f"supersedes: {FIRST}".encode(), b"supersedes: null"))
    propose_change(root, CHANGE, at("2026-11-04T10:00:00"), FIRST.rsplit("-", 1)[1])
    (root / CHANGE).write_bytes(data)
    propose_change(root, CHANGE, at("2026-11-04T10:15:00"), CHANGE_PACKET.rsplit("-", 1)[1])
    apply_change(root, CHANGE_PACKET, "Tianchi YU", confirmed=True, now=at("2026-11-04T10:20:00"))
    (root / HANDOFF_INPUT).write_bytes(examples["handoff"])
    outcome = draft(root, HANDOFF_INPUT, at("2026-11-04T11:30:00.412"), HANDOFF_DRAFT[-32:])
    apply_handoff(
        root, outcome.loaded.path, "Tianchi YU", confirmed=True, now=at("2026-11-04T11:35:00.108")
    )
    (root / INPUT).write_bytes(examples["input"])
    return root


def example(root):
    return propose(root, "scheduling", INPUT, at("2026-11-04T14:00:00"), PACKET[-32:])


def confirm(root, packet=PACKET, actor="Tianchi YU", name="scheduling", **extra):
    extra.setdefault("now", at("2026-11-04T14:10:00"))
    return create(root, name, packet, actor, confirmed=True, **extra)


def outside(root, *skip):
    """Every file outside runs/ and the given prefixes, by path."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and path.relative_to(root).parts[0] != "runs"
        and not any(str(path.relative_to(root)).startswith(prefix) for prefix in skip)
    }


def tree(directory):
    return {
        str(path.relative_to(directory)): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def invoke(*args, env=None):
    return runner.invoke(app, [str(arg) for arg in args], env=env or {"TOULMIN_ACTOR": ""})


def creation_input(root, name="other", *, header="", body="# Research brief\n\nFraming.\n"):
    fields = {
        "project": name,
        "supersedes": "null",
        "question": '"Q?"',
        "motivation": '"M."',
        "included": '["One thing"]',
        "excluded": "[]",
        "assumptions": "[]",
        "open_questions": "[]",
        "goal": '"G."',
        "constraints": '"C."',
        "next_step": '"N."',
        "sources": "[]",
        "pins": "[]",
        "relationships": "[]",
    }
    for line in header.splitlines():
        key, value = line.split(": ", 1)
        fields[key] = value
    text = "---\nschema_version: 1\nkind: project-creation-input\n"
    text += "".join(f"{key}: {value}\n" for key, value in fields.items())
    path = f"runs/drafts/create-{name}.md"
    (root / path).write_text(text + "---\n" + body)
    return path


# Propose and preview: sealed, readable, no child.


def test_contract_example_is_reproduced_byte_for_byte(root):
    expected = blocks()
    before = outside(root)
    outcome = example(root)
    assert outcome.loaded.directory == PACKET
    packet = (root / PACKET / "packet.md").read_bytes()
    assert packet == expected["packet"]
    assert (root / PACKET / "seal").read_text() == digest(packet) + "\n"
    assert (root / PACKET / "input.md").read_bytes() == expected["input"]
    assert (root / PACKET / "targets/PROJECT.md").read_bytes() == expected["charter"]
    assert (root / PACKET / "targets/brief.md").read_bytes() == expected["input"].split(
        b"---\n", 2
    )[2]
    assert sorted(path.name for path in (root / PACKET / "sources").iterdir()) == ["1.md", "2.md"]
    assert outside(root) == before and not (root / CHILD).exists()
    result = confirm(root, approval_text="Create scheduling as previewed.")
    assert result.status == "created"
    assert (root / PACKET / "receipt.md").read_bytes() == expected["receipt"]
    assert (root / CHILD / "runs/creation/creation.md").read_bytes() == expected["record"]
    assert (root / CHILD / "PROJECT.md").read_bytes() == expected["charter"]
    assert not (root / workspace_journal.JOURNAL).exists()
    assert not (root / STAGING).exists()


def test_created_child_is_complete_valid_and_claim_free(root):
    example(root)
    before = outside(root, CHILD)
    confirm(root)
    files = tree(root / CHILD)
    assert sorted(files) == [
        "PROJECT.md",
        "brief.md",
        *(f"{folder}/.gitkeep" for folder in ("claims", "decisions", "evidence", "explorations")),
        "objections/.gitkeep",
        "runs/.gitkeep",
        "runs/creation/creation.md",
        "runs/creation/packet.md",
        "runs/creation/seal",
        "runs/creation/sources/1.md",
        "runs/creation/sources/2.md",
        "sessions/.gitkeep",
        "specs/.gitkeep",
    ]
    assert files["runs/creation/packet.md"] == (root / PACKET / "packet.md").read_bytes()
    assert files["runs/creation/sources/1.md"] == (root / ACTIVITY).read_bytes()
    assert outside(root, CHILD) == before  # WORKSPACE.md, resources, sessions untouched
    state = research_state(root, "scheduling")
    assert state.errors == () and state.stage == "explore" and state.objects == ()
    assert "projects/scheduling/runs/creation/creation.md" in state.context_files
    status = invoke("status", "scheduling", "--root", root)
    assert status.exit_code == 0 and "Claims: none" in status.output
    report = workspace_status(root, {})
    assert [(child.name, child.stage) for child in report.children] == [("scheduling", "explore")]
    assert report.errors == ()
    assert ("runs/" + PACKET[5:], "creation", "applied") in {
        (item.path, item.kind, item.disposition) for item in report.proposals
    }


def test_cli_propose_and_preview_show_the_reviewed_files_and_write_nothing(root):
    result = invoke("project", "propose", "scheduling", "--root", root, "--input", INPUT)
    assert result.exit_code == 0, result.output
    packet = next(path for path in (root / "runs").iterdir() if "-project-" in path.name)
    for line in (
        f"Root: {root}",
        "Scope: Workspace",
        "Creates: projects/scheduling/ (absent until confirmed)",
        "## Question\nDoes queue scheduling policy",
        "Approved initial framing; hypotheses below are unproven.",
        "- Bursty arrivals dominate p99 (unverified)",
        "No native session is started.",
        f"--from runs/{packet.name} --confirmed-by ACTOR --confirm",
        "toulmin project reject scheduling",
    ):
        assert line in result.stdout, line
    before = tree(root)
    preview = invoke(
        "project", "create", "scheduling", "--root", root, "--from", f"runs/{packet.name}"
    )
    assert preview.exit_code == 0 and "Preview only; nothing written." in preview.stdout
    assert "## Scope\nIncluded:\n- One request queue on one node" in preview.stdout
    refused = invoke(
        "project", "create", "scheduling", "--root", root, "--from", f"runs/{packet.name}",
        "--confirmed-by", "Tianchi YU",
    )  # fmt: skip
    assert refused.exit_code == 1 and "confirmation missing" in refused.output
    missing_actor = invoke(
        "project", "create", "scheduling", "--root", root, "--from", f"runs/{packet.name}",
        "--confirm",
    )  # fmt: skip
    assert missing_actor.exit_code == 2
    assert tree(root) == before and not (root / CHILD).exists()


def test_cli_create_reports_the_separate_open_action(root):
    example(root)
    result = invoke(
        "project", "create", "scheduling", "--root", root, "--from", PACKET, "--confirm",
        env={"TOULMIN_ACTOR": "Tianchi YU"},
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    for line in (
        "Disposition: applied by Tianchi YU",
        "Published: projects/scheduling/PROJECT.md",
        f"Receipt: {PACKET}/receipt.md",
        "No native session was started; this workspace conversation is unchanged.",
        f"Open it in its own session: toulmin aoe open scheduling --root {root}",
    ):
        assert line in result.stdout, line
    again = invoke(
        "project", "create", "scheduling", "--root", root, "--from", PACKET,
        "--confirmed-by", "Someone Else", "--confirm",
    )  # fmt: skip
    assert again.exit_code == 0 and "Already recorded; nothing written." in again.stdout
    assert "applied by Tianchi YU" in again.stdout


@pytest.mark.parametrize(
    ("header", "body", "message"),
    [
        ("included: []", None, "included: expected list with at least one item"),
        ('question: "Two\\nlines"', None, "question: expected one line"),
        ('goal: "## Goal"', None, "goal: must not contain '## ' headings"),
        ("relationships: [{project: missing, note: x}]", None, "missing: no such project"),
        ("relationships: [{project: other, note: x}]", None, "related to itself"),
        ("supersedes: runs/drafts/x.md", None, "expected a child creation packet"),
        ("", "", "body: the initial Brief is required"),
        ("", "# Brief\n\nSee [[C-001]].\n", "unqualified reference"),
        ("", "# Brief\n\nSee [[ghost/C-001]].\n", "[[ghost/C-001]]"),
        ('constraints: "' + "x\\n" * 40 + '"', None, "PROJECT.md must fit within 40 lines"),
        ("sources: [{path: runs/drafts/nothing.md, coverage: full}]", None, "nothing.md"),
    ],
)
def test_invalid_inputs_are_refused_without_writing(root, header, body, message):
    path = creation_input(root, header=header, **({} if body is None else {"body": body}))
    before = tree(root)
    with pytest.raises((FormatError, OSError), match=None) as error:
        propose(root, "other", path)
    assert message in str(error.value)
    assert tree(root) == before


def test_input_and_command_names_must_agree(root):
    with pytest.raises(FormatError, match="the input creates scheduling, the command names other"):
        propose(root, "other", INPUT)
    example(root)
    with pytest.raises(FormatError, match="creates scheduling, not other; rerun with NAME"):
        confirm(root, name="other")
    assert not (root / CHILD).exists() and not (root / "projects/other").exists()


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (CHANGE_PACKET, "workspace change packet; use workspace apply"),
        (f"{HANDOFF_DRAFT}/draft.md", "handoff draft; use aoe handoff --apply"),
        (INPUT, "is an input, not a reviewed packet; run project propose"),
        ("runs/20261104T140000Z-other-c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8", "creation packet"),
    ],
)
def test_wrong_artifacts_are_refused(root, value, message):
    with pytest.raises(FormatError, match=message):
        create(root, "scheduling", value, None, confirmed=False)


def test_a_creation_packet_is_refused_by_workspace_apply(root):
    example(root)
    with pytest.raises(FormatError, match="child creation packet; use project create"):
        apply_change(root, PACKET, "Tianchi YU", confirmed=True)


@pytest.mark.parametrize("name", ["packet.md", "targets/brief.md", "input.md", "sources/1.md"])
def test_edited_packets_are_invalid(root, name):
    example(root)
    path = root / PACKET / name
    path.write_bytes(path.read_bytes() + b"edit\n")
    with pytest.raises(FormatError, match="propose again"):
        confirm(root)
    assert not (root / CHILD).exists()
    assert "invalid" in {item.disposition for item in workspace_status(root, {}).proposals} or (
        name != "packet.md"
    )


# Repeats, occupied names, supersession and staleness.


def test_repeat_create_returns_the_same_child_and_receipt(root):
    example(root)
    first = confirm(root)
    child, receipt = tree(root / CHILD), (root / PACKET / "receipt.md").read_bytes()
    again = confirm(root, actor="Someone Else", now=at("2026-11-05T09:00:00"))
    assert again.status == "replayed" and again.receipt == first.receipt
    assert tree(root / CHILD) == child
    assert (root / PACKET / "receipt.md").read_bytes() == receipt


def test_another_packet_for_an_occupied_name_never_replaces_it(root):
    example(root)
    second = creation_input(root, "scheduling")
    other = propose(root, "scheduling", second, at("2026-11-04T14:05:00"))
    confirm(root)
    child = tree(root / CHILD)
    preview = create(root, "scheduling", other.loaded.directory, None, confirmed=False)
    assert any(f"created from {PACKET}/packet.md by Tianchi YU" in p for p in preview.problems)
    with pytest.raises(FormatError, match="occupied by a project created from"):
        confirm(root, other.loaded.directory)
    with pytest.raises(FormatError, match="projects/scheduling: occupied"):
        propose(root, "scheduling", second)
    assert tree(root / CHILD) == child
    assert not (root / other.loaded.directory / "receipt.md").exists()


def test_existing_legacy_style_child_is_never_replaced(root, tmp_path):
    initialize(tmp_path / "template", "other")
    (root / "projects/other").mkdir()
    for path, data in tree(tmp_path / "template/projects/other").items():
        (root / "projects/other" / path).parent.mkdir(parents=True, exist_ok=True)
        (root / "projects/other" / path).write_bytes(data)
    with pytest.raises(FormatError, match="occupied by an existing project; never replaced"):
        propose(root, "other", creation_input(root))


def test_revision_supersedes_and_only_the_successor_can_be_created(root):
    example(root)
    revised = creation_input(root, "scheduling", header=f"supersedes: {PACKET}")
    successor = propose(root, "scheduling", revised, at("2026-11-04T14:05:00"))
    with pytest.raises(FormatError, match=f"superseded by {successor.loaded.directory}"):
        confirm(root)
    dispositions = {item.path: item.disposition for item in workspace_status(root, {}).proposals}
    assert dispositions[PACKET] == "superseded"
    assert dispositions[successor.loaded.directory] == "pending"
    with pytest.raises(FormatError, match="already superseded"):
        propose(root, "scheduling", revised)
    confirm(root, successor.loaded.directory)
    assert (root / CHILD / "brief.md").read_text() == "# Research brief\n\nFraming.\n"


def test_changed_sources_and_broken_pins_refuse_but_unrelated_edits_do_not(root):
    example(root)
    (root / "AGENTS.md").write_text((root / "AGENTS.md").read_text() + "\nLocal rule.\n")
    (root / "framework/principles.md").write_text("customized\n")
    focus = (
        "---\nschema_version: 1\nkind: workspace-change-input\nscope: {kind: workspace}\n"
        "supersedes: null\nsources: []\npins: []\nchanges:\n  - target: charter\n"
        '    sections: {Focus: "FIFO first."}\n---\n## Question\nFocus?\n\n'
        "## Unresolved assumptions\nNone.\n"
    )
    (root / "runs/drafts/focus.md").write_text(focus)
    focused = propose_change(root, "runs/drafts/focus.md")
    apply_change(root, focused.loaded.directory, "Tianchi YU", confirmed=True)
    activity = (root / ACTIVITY).read_bytes()
    (root / ACTIVITY).write_bytes(activity + b"\nLater note.\n")
    (root / TRACE / "trace.csv").write_text("changed\n")
    preview = create(root, "scheduling", PACKET, None, confirmed=False)
    assert any("selected source changed since propose" in p for p in preview.problems)
    assert any("broken pin synthetic-queue-trace revision 1" in p for p in preview.problems)
    with pytest.raises(FormatError, match="Nothing written; preview a refreshed proposal"):
        confirm(root)
    assert not (root / CHILD).exists()
    (root / ACTIVITY).write_bytes(activity)
    (root / TRACE / "trace.csv").write_text("arrival_us,service_us\n0,180\n240,95\n410,620\n")
    assert confirm(root).status == "created"
    assert (root / "framework/principles.md").read_text() == "customized\n"
    assert "Local rule." in (root / "AGENTS.md").read_text()


# Rejection.


def test_reject_is_final_and_changes_nothing_else(root):
    example(root)
    before = tree(root)
    refused = invoke(
        "project", "reject", "scheduling", "--root", root, "--from", PACKET,
        "--reason", "Too early", "--confirmed-by", "Tianchi YU",
    )  # fmt: skip
    assert refused.exit_code == 1 and "confirmation missing" in refused.output
    result = invoke(
        "project", "reject", "scheduling", "--root", root, "--from", PACKET,
        "--reason", "Too early", "--confirmed-by", "Tianchi YU", "--confirm",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert "Disposition: rejected by Tianchi YU" in result.stdout
    assert "aoe open" not in result.stdout
    after = tree(root)
    assert set(after) - set(before) == {f"{PACKET}/receipt.md"}
    assert reject(root, "scheduling", PACKET, "again", "X").status == "replayed"
    with pytest.raises(FormatError, match="rejected by Tianchi YU"):
        confirm(root)
    assert not (root / CHILD).exists()


def test_a_created_child_cannot_be_rejected(root):
    example(root)
    confirm(root)
    with pytest.raises(FormatError, match="already created"):
        reject(root, "scheduling", PACKET, "no", "Tianchi YU")


# Interrupted publication (section 10).


def crash_on(monkeypatch, predicate):
    original = workspace_journal.write_atomic

    def failing(path, data, **kwargs):
        if predicate(Path(path)):
            raise OSError("simulated crash")
        return original(path, data, **kwargs)

    monkeypatch.setattr(workspace_journal, "write_atomic", failing)


@pytest.mark.parametrize(
    "point",
    [
        lambda path: path.name == "PROJECT.md",  # nothing published yet
        lambda path: path.name == "seal",  # staging partly written
        lambda path: path.name == "receipt.md",  # child renamed, receipt missing
    ],
)
def test_interrupted_creation_is_incomplete_then_recovers_once(root, monkeypatch, point):
    example(root)
    crash_on(monkeypatch, point)
    with pytest.raises(OSError, match="simulated crash"):
        confirm(root, approval_text="Yes.")
    monkeypatch.undo()
    assert (root / workspace_journal.JOURNAL).exists()
    report = workspace_status(root, {})
    assert {item.path: item.disposition for item in report.proposals}[PACKET] == "incomplete"
    if (root / CHILD).exists():
        assert [(c.name, c.error) for c in report.children] == [
            ("scheduling", "creation incomplete")
        ]
        assert any("creation incomplete" in e for e in research_state(root, "scheduling").errors)
        listing = invoke("status", "--root", root)
        assert "scheduling | stage=creation incomplete" in listing.output
    preview = create(root, "scheduling", PACKET, None, confirmed=False)
    assert preview.status == "incomplete"
    with pytest.raises(FormatError, match="incomplete project-create"):
        apply_change(root, CHANGE_PACKET, "Tianchi YU", confirmed=True)
    result = confirm(root, actor="Someone Else", now=at("2026-11-05T09:00:00"))
    assert result.status == "recovered"
    assert "ignored; recovery keeps the first confirmation by Tianchi YU" in result.problems[0]
    assert result.receipt.actor == "Tianchi YU" and result.receipt.approval_text == "Yes."
    assert result.receipt.at == "2026-11-04T14:10:00Z"
    assert not (root / workspace_journal.JOURNAL).exists() and not (root / STAGING).exists()
    assert research_state(root, "scheduling").errors == ()
    assert confirm(root).status == "replayed"


def test_leftover_temporaries_in_staging_are_discarded(root, monkeypatch):
    example(root)
    crash_on(monkeypatch, lambda path: path.name == "seal")
    with pytest.raises(OSError):
        confirm(root)
    monkeypatch.undo()
    (root / STAGING / ".handoff-abc.tmp").write_bytes(b"partial")
    assert confirm(root).status == "recovered"
    assert not any(name.endswith(".tmp") for name in tree(root / CHILD))


@pytest.mark.parametrize("where", ["staging", "child"])
def test_external_edits_during_recovery_are_preserved(root, monkeypatch, where):
    example(root)
    name = "seal" if where == "staging" else "receipt.md"
    crash_on(monkeypatch, lambda path: path.name == name)
    with pytest.raises(OSError):
        confirm(root)
    monkeypatch.undo()
    base = root / (STAGING if where == "staging" else CHILD)
    (base / "brief.md").write_text("edited by hand\n")
    (base / "notes.md").write_text("extra\n")
    with pytest.raises(FormatError, match="changed outside this publication|journal kept"):
        confirm(root)
    assert (base / "brief.md").read_text() == "edited by hand\n"
    assert (base / "notes.md").exists() and (root / workspace_journal.JOURNAL).exists()
    assert not (root / PACKET / "receipt.md").exists()


def test_missing_journal_with_a_created_child_is_refused(root, monkeypatch):
    example(root)
    crash_on(monkeypatch, lambda path: path.name == "receipt.md")
    with pytest.raises(OSError):
        confirm(root)
    monkeypatch.undo()
    workspace_journal.retire(project_creation.Repository(root))  # removed by hand
    with pytest.raises(
        FormatError, match="created from this packet by Tianchi YU.*nothing written"
    ):
        confirm(root)
    assert not (root / PACKET / "receipt.md").exists()


# Native launch is separate and retryable (F06, A09/A10).


class FakeAoE(AoEClient):
    def __init__(self, root):
        self.root = root
        self.profile = "main"
        self.sessions: dict[str, AoESession] = {}
        self.created: list[tuple[str | None, str | None]] = []
        self.sent: list[tuple[str, str]] = []
        self.fail = False

    def list_sessions(self):
        return tuple(self.sessions.values())

    def show(self, session_id):
        if session_id not in self.sessions:
            raise AoEError("No such session")
        return self.sessions[session_id]

    def current(self):
        return next(iter(self.sessions.values()))

    def create(self, root, project, agent, *, title=None):
        if self.fail:
            raise AoEError("launch failed")
        self.created.append((project, title))
        session_id = f"{len(self.created):016x}"
        session = AoESession(session_id, root, agent, "live", "idle", "native", title or "")
        self.sessions[session_id] = session
        return session

    def ready(self, session_id):
        return True, "idle"

    def send(self, session_id, message):
        self.sent.append((session_id, message))


def test_failed_launch_keeps_the_child_and_retries_only_the_open(root):
    fake = FakeAoE(root)
    AoEWorkspace(root, None, fake).open()
    workspace_binding = (root / ".aoe/binding.json").read_bytes()
    example(root)
    with pytest.raises(FormatError, match="expected existing directory"):
        AoEWorkspace(root, "scheduling", fake).open()  # no child yet
    confirm(root)
    child = tree(root / CHILD)
    fake.fail = True
    with pytest.raises(AoEError, match="launch failed"):
        AoEWorkspace(root, "scheduling", fake).open()
    assert research_state(root, "scheduling").errors == ()
    # Only the operational binding (AOE3 creation recovery) is added; research files stay.
    assert {k: v for k, v in tree(root / CHILD).items() if not k.startswith(".aoe/")} == child
    fake.fail = False
    with pytest.raises(FormatError, match="rerun open with --new-session"):
        AoEWorkspace(root, "scheduling", fake).open()  # never a silent duplicate
    assert fake.created == [(None, "Workspace: Serving Research")]
    view = AoEWorkspace(root, "scheduling", fake).open(new_session=True)
    assert view.binding is not None
    assert fake.created[-1] == ("scheduling", "Project: scheduling | Serving Research")
    binding = json.loads((root / CHILD / ".aoe/binding.json").read_text())
    manifest = json.loads((root / binding["context"] / "manifest.json").read_text())
    assert "inputs/projects/scheduling/runs/creation/creation.md" in manifest["files"]
    assert not any("sources/" in name for name in manifest["files"])
    assert (root / ".aoe/binding.json").read_bytes() == workspace_binding
    assert confirm(root).status == "replayed"


def test_an_incomplete_child_cannot_be_opened(root, monkeypatch):
    example(root)
    crash_on(monkeypatch, lambda path: path.name == "receipt.md")
    with pytest.raises(OSError):
        confirm(root)
    monkeypatch.undo()
    fake = FakeAoE(root)
    with pytest.raises(FormatError, match="creation incomplete"):
        AoEWorkspace(root, "scheduling", fake).open()
    assert fake.created == []


def test_workspace_card_lists_pending_creation_and_the_propose_action(root):
    example(root)
    card = render_workspace(workspace_research(root))
    assert f"{PACKET} | creation | pending" in card
    assert "toulmin project propose NAME --input FILE" in card
    confirm(root)
    card = render_workspace(workspace_research(root))
    assert "scheduling | stage: explore" in card
    assert "Open project scheduling in its own session (not this one)." in card


def test_legacy_roots_have_no_child_creation(tmp_path):
    legacy = tmp_path / "legacy"
    initialize(legacy, "demo")
    (legacy / "runs/drafts").mkdir(parents=True)
    path = creation_input(legacy)
    with pytest.raises(FormatError, match="workspace state not configured"):
        propose(legacy, "other", path)
    result = invoke("project", "propose", "other", "--root", legacy, "--input", path)
    assert result.exit_code == 1 and "workspace state not configured" in result.output


def test_new_session_retry_is_refused_while_a_matching_session_may_exist(root):
    example(root)
    confirm(root)
    fake = FakeAoE(root)
    fake.fail = True
    with pytest.raises(AoEError):
        AoEWorkspace(root, "scheduling", fake).open()
    title = "Project: scheduling | Serving Research"
    for session_id in ("c" * 16, "d" * 16):
        fake.sessions[session_id] = AoESession(
            session_id, root, "codex", "live", "idle", "n", title
        )
    fake.fail = False
    with pytest.raises(FormatError, match="Creation outcome unresolved; inspect AoE"):
        AoEWorkspace(root, "scheduling", fake).open(new_session=True)
    assert fake.created == []
