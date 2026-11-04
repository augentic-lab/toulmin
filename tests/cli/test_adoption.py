"""WI7: previewed additive adoption of a legacy workbench (contract section 12).

Temporary legacy fixtures only (two projects, a cross-project reference, customized
instructions and configuration, an applied handoff and an AoE binding from a fake
client); no model, network, real session or real research project.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toulmin.adapters.aoe import AoEClient, AoEError, AoESession
from toulmin.application.aoe import AoEWorkspace
from toulmin.cli.app import app
from toulmin.cli.initialize import adoption_templates, initialize, initialize_workspace
from toulmin.core import workspace_journal
from toulmin.core.atomic import digest
from toulmin.core.documents import FormatError
from toulmin.protocols.adoption import SCOPE_HEADING, adopt, compute, scope_section
from toulmin.protocols.research_workspace import research_state
from toulmin.protocols.workspace_change import propose as propose_change
from toulmin.protocols.workspace_state import RootState, classify_root, workspace_status

runner = CliRunner()
REPO = Path(__file__).resolve().parents[2]
NAME = "Serving Research"
LOCAL = "\n## Local conventions\nCite measurements with their trace name.\n"


class FakeAoE(AoEClient):
    def __init__(self, root):
        self.root = root
        self.profile = "main"
        self.sessions: dict[str, AoESession] = {}
        self.created: list[str | None] = []
        self.sent: list[str] = []

    def list_sessions(self):
        return tuple(self.sessions.values())

    def show(self, session_id):
        if session_id not in self.sessions:
            raise AoEError("No such session")
        return self.sessions[session_id]

    def current(self):
        return next(iter(self.sessions.values()))

    def create(self, root, project, agent, *, title=None):
        self.created.append(project)
        session_id = f"{len(self.created):016x}"
        self.sessions[session_id] = AoESession(
            session_id, root, agent, "live", "idle", "native", title or f"Toulmin: {project}"
        )
        return self.sessions[session_id]

    def ready(self, session_id):
        return True, "idle"

    def send(self, session_id, message):
        self.sent.append(session_id)


def invoke(*args, env=None):
    return runner.invoke(app, [str(arg) for arg in args], env=env or {"TOULMIN_ACTOR": ""})


def tree(root):
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and not path.is_symlink()  # CLAUDE.md links to AGENTS.md
        and ".git" not in path.relative_to(root).parts[:1]
    }


@pytest.fixture
def legacy(populated):
    """Two projects, a cross reference, custom AGENTS/config, a handoff and a v1 binding."""
    root = populated
    initialize(root, "beta")
    brief = root / "projects/beta/brief.md"
    brief.write_text(brief.read_text() + "\nBuilds on [[demo/C-001]].\n")
    (root / "AGENTS.md").write_text((root / "AGENTS.md").read_text() + LOCAL)
    models = root / "tools/models.toml"
    models.write_text(models.read_text() + "\n# researcher's local alias notes\n")
    ignore = root / ".gitignore"
    lines = [line for line in ignore.read_text().splitlines() if "workspace" not in line]
    ignore.write_text("\n".join(line for line in lines if "creating" not in line) + "\n")
    drafted = invoke("handoff", "demo", "--root", root)
    assert drafted.exit_code == 0, drafted.output
    applied = invoke(
        "handoff", "demo", "--root", root, "--apply", drafted.stdout.strip(),
        "--confirmed-by", "Fixture Researcher", "--confirm",
    )  # fmt: skip
    assert applied.exit_code == 0, applied.output
    fake = FakeAoE(root)
    AoEWorkspace(root, "demo", fake).open()
    assert classify_root(root, {}).state == RootState.LEGACY
    return root


def plan_of(root, templates=None):
    return compute(root, NAME, templates or adoption_templates())


def confirm(root, value=None, actor="Tianchi YU", templates=None, **extra):
    templates = templates or adoption_templates()
    value = value or plan_of(root, templates).digest
    return adopt(root, NAME, templates, value, actor, **extra)


# Preview: read-only, deterministic, exact.


def test_preview_is_deterministic_read_only_and_names_every_change(legacy, tmp_path):
    before = tree(legacy)
    first, second = plan_of(legacy), plan_of(legacy)
    assert first.data == second.data and first.digest == digest(first.data)
    assert tree(legacy) == before
    text = first.data.decode()
    assert str(legacy) not in text and "2026" not in text  # no absolute path or time
    assert [change.path for change in first.changes] == [
        "AGENTS.md",
        ".gitignore",
        "runs/drafts/.gitkeep",
        "sessions/.gitkeep",
        "shared/resources/.gitkeep",
        "WORKSPACE.md",
    ]
    assert "absent: [WORKSPACE.md, runs, sessions, shared/resources, .aoe/binding.json]" in text
    assert "conflicts: []" in text and "Projects kept as they are: beta, demo." in text
    agents = next(change for change in first.changes if change.path == "AGENTS.md")
    assert (
        agents.after == agents.before + b"\n" + scope_section(adoption_templates().agents).encode()
    )
    assert f"+{SCOPE_HEADING}" in text
    gitignore = next(change for change in first.changes if change.path == ".gitignore")
    assert gitignore.after.startswith(gitignore.before)
    assert gitignore.after[len(gitignore.before) :] == (
        b".workspace-pending/\n.workspace-prepare-*/\n.workspace-completed-*/\n"
        b"projects/.creating-*/\n"
    )
    copy = tmp_path / "copy"
    copy.mkdir()
    for path, data in before.items():
        (copy / path).parent.mkdir(parents=True, exist_ok=True)
        (copy / path).write_bytes(data)
    assert plan_of(copy).data == first.data  # independent of location


def test_cli_preview_prints_the_plan_digest_and_exact_command(legacy):
    before = tree(legacy)
    result = invoke("workspace", "adopt", legacy, "--name", NAME)
    assert result.exit_code == 0, result.output
    plan = plan_of(legacy)
    for line in (
        f"Root: {legacy}",
        "Scope: Workspace (after adoption)",
        f"Plan digest: {plan.digest}",
        "## Changes",
        "Empty placeholders: runs/drafts/.gitkeep, sessions/.gitkeep, shared/resources/.gitkeep.",
        "## Conflicts\nNone.",
        f"--plan-digest {plan.digest} --confirmed-by ACTOR --confirm",
        "Preview only; nothing written.",
    ):
        assert line in result.stdout, line
    assert tree(legacy) == before
    refused = invoke("workspace", "adopt", legacy, "--plan-digest", plan.digest)
    assert refused.exit_code == 1 and "confirmation missing" in refused.output
    no_digest = invoke("workspace", "adopt", legacy, "--confirmed-by", "R", "--confirm")
    assert no_digest.exit_code == 2
    no_actor = invoke("workspace", "adopt", legacy, "--plan-digest", plan.digest, "--confirm")
    assert no_actor.exit_code == 2
    assert tree(legacy) == before


def test_pristine_released_files_are_replaced_and_absent_contract_created(tmp_path):
    root = tmp_path / "old"
    initialize(root, "demo")
    old_agents = b"# An earlier released template\n"
    old_contract = b"# An earlier released contract\n"
    (root / "AGENTS.md").write_bytes(old_agents)
    (root / "framework/workspace-formats.md").write_bytes(old_contract)
    templates = adoption_templates()
    released = {
        "AGENTS.md": templates.released["AGENTS.md"] | {digest(old_agents)},
        "framework/workspace-formats.md": templates.released["framework/workspace-formats.md"]
        | {digest(old_contract)},
    }
    templates = replace(templates, released=released)
    plan = plan_of(root, templates)
    changes = {change.path: change for change in plan.changes}
    assert changes["AGENTS.md"].after == templates.agents  # replaced, not appended
    assert changes["framework/workspace-formats.md"].after == templates.contract
    assert "packaged contract copy" in plan.data.decode()
    (root / "framework/workspace-formats.md").unlink()
    created = {change.path: change for change in plan_of(root, templates).changes}
    assert created["framework/workspace-formats.md"].before is None


def test_released_digests_cover_every_shipped_copy():
    released = adoption_templates().released
    shared = (REPO / "src/toulmin/cli/templates/AGENTS.md").read_bytes()
    workspace = (REPO / "src/toulmin/cli/workspace_templates/AGENTS.md").read_bytes()
    contract = (REPO / "docs/workspace-formats.md").read_bytes()
    assert digest(shared) in released["AGENTS.md"]
    assert digest(workspace) in released["AGENTS.md"]
    assert digest(contract) in released["framework/workspace-formats.md"]
    root_template = REPO / "src/toulmin/cli/templates/framework/workspace-formats.md"
    assert root_template.read_bytes() == contract


def test_a_freshly_initialized_legacy_root_gets_the_workspace_instructions(tmp_path):
    root = tmp_path / "plain"
    initialize(root, "demo")
    plan = plan_of(root)
    agents = next(change for change in plan.changes if change.path == "AGENTS.md")
    assert agents.after == adoption_templates().agents
    assert ".gitignore" not in {change.path for change in plan.changes}


# Conflicts and refusals leave every file intact.


@pytest.mark.parametrize(
    ("setup", "path", "reason"),
    [
        (lambda r: (r / "runs").mkdir() or (r / "runs/notes.md").write_text("x\n"), "runs",
         "never reclassifies"),
        (lambda r: (r / "sessions").mkdir() or (r / "sessions/old.md").write_text("x\n"),
         "sessions", "never reclassifies"),
        (lambda r: (r / "shared/resources").mkdir(parents=True)
         or (r / "shared/resources/a.md").write_text("x\n"), "shared/resources",
         "never reclassifies"),
        (lambda r: (r / "framework/workspace-formats.md").write_text("edited\n"),
         "framework/workspace-formats.md", "differs from every released copy"),
        (lambda r: (r / "AGENTS.md").write_text(
            (r / "AGENTS.md").read_text() + f"\n{SCOPE_HEADING}\nMine.\n"),
         "AGENTS.md", "already have"),
        (lambda r: (r / ".aoe").mkdir() or (r / ".aoe/binding.json").write_text("{}\n"),
         ".aoe/binding.json", "never reinterpreted"),
    ],
)  # fmt: skip
def test_conflicts_are_reported_and_cannot_be_confirmed(legacy, setup, path, reason):
    setup(legacy)
    before = tree(legacy)
    plan = plan_of(legacy)
    assert [(item.path, reason in item.reason) for item in plan.conflicts] == [(path, True)]
    result = invoke("workspace", "adopt", legacy, "--name", NAME)
    assert result.exit_code == 0 and "Cannot be confirmed: 1 conflict(s)" in result.stdout
    assert f"- {path}: " in result.stdout and "--plan-digest" not in result.stdout
    with pytest.raises(FormatError, match="plan has conflicts.*nothing written"):
        confirm(legacy, plan.digest)
    assert tree(legacy) == before


def test_empty_record_locations_are_not_conflicts(legacy):
    (legacy / "runs").mkdir()
    (legacy / "runs/.gitkeep").write_text("")
    (legacy / "shared/data").mkdir(parents=True)
    plan = plan_of(legacy)
    assert plan.conflicts == ()
    assert "runs" not in plan.data.decode().split("absent: [", 1)[1].split("]")[0]


def test_stale_and_malformed_digests_write_nothing(legacy):
    plan = plan_of(legacy)
    before = tree(legacy)
    for value, message in (
        (plan.digest[:15], "at least 16 hex digits"),
        (plan.digest.upper(), "at least 16 hex digits"),
        ("0" * 16 if not plan.digest.startswith("0" * 16) else "f" * 16, "plan changed"),
    ):
        with pytest.raises(FormatError, match=message):
            confirm(legacy, value)
    assert tree(legacy) == before
    (legacy / "AGENTS.md").write_text((legacy / "AGENTS.md").read_text() + "One more rule.\n")
    edited = tree(legacy)
    with pytest.raises(FormatError, match="plan changed since preview.*nothing written"):
        confirm(legacy, plan.digest)
    assert tree(legacy) == edited


@pytest.mark.parametrize("state", ["empty", "missing", "unrelated", "incomplete"])
def test_other_root_states_are_refused(tmp_path, state):
    root = tmp_path / state
    if state != "missing":
        root.mkdir()
    if state == "unrelated":
        (root / "notes.txt").write_text("mine\n")
    if state == "incomplete":
        initialize_workspace(root, NAME)
        (root / "WORKSPACE.md").unlink()
    result = invoke("workspace", "adopt", root)
    assert result.exit_code == 1
    expected = "does not exist" if state == "missing" else "not a legacy workbench"
    assert expected in result.output
    assert not (root / "WORKSPACE.md").exists()


def test_a_workspace_root_reports_it_is_configured(tmp_path):
    root = tmp_path / "fresh"
    initialize_workspace(root, NAME)
    result = invoke("workspace", "adopt", root)
    assert result.exit_code == 0
    assert "Workspace state: configured (WORKSPACE.md exists); nothing to adopt." in result.stdout
    with pytest.raises(FormatError, match="already configured"):
        adopt(root, NAME, adoption_templates(), "a" * 64, "Tianchi YU")


# Confirmed adoption: additive, exact, no model.


def test_confirmed_adoption_applies_exactly_the_plan(legacy):
    before = tree(legacy)
    plan = plan_of(legacy)
    binding = json.loads((legacy / "projects/demo/.aoe/binding.json").read_text())
    result = confirm(legacy, plan.digest[:16], approval_text="Adopt as previewed.")
    assert result.status == "adopted"
    after = tree(legacy)
    archive = result.directory
    assert archive.startswith("runs/") and "-adoption-" in archive
    assert (legacy / archive / "plan.md").read_bytes() == plan.data
    assert (legacy / archive / "seal").read_text() == plan.digest + "\n"
    receipt = result.receipt
    assert receipt.record == f"{archive}/plan.md" and receipt.record_sha256 == plan.digest
    assert receipt.disposition == "applied" and receipt.actor == "Tianchi YU"
    assert receipt.approval_text == "Adopt as previewed."
    assert [path for path, _, _ in receipt.results] == [c.path for c in plan.changes]
    changed = {path for path in after if before.get(path) != after[path]}
    planned = {change.path for change in plan.changes}
    assert changed == planned | {f"{archive}/{name}" for name in ("plan.md", "seal", "receipt.md")}
    for change in plan.changes:
        assert after[change.path] == change.after
    for path, data in before.items():
        if path not in planned:
            assert after[path] == data, path  # projects, bindings, contexts, config, roles
    assert not (legacy / ".aoe").exists() and not (legacy / workspace_journal.JOURNAL).exists()
    assert (legacy / "CLAUDE.md").is_symlink() and (legacy / "CLAUDE.md").readlink() == Path(
        "AGENTS.md"
    )
    report = workspace_status(legacy, {})
    assert report.root.state == RootState.WORKSPACE and report.errors == ()
    assert report.charter.name == NAME and report.charter.sections == ()
    assert [child.name for child in report.children] == ["beta", "demo"]
    assert report.history == () and report.proposals == ()
    for project in ("demo", "beta"):
        assert research_state(legacy, project).errors == ()
    assert json.loads((legacy / "projects/demo/.aoe/binding.json").read_text()) == binding


def test_existing_child_context_becomes_stale_but_is_never_rewritten(legacy):
    binding = json.loads((legacy / "projects/demo/.aoe/binding.json").read_text())
    archive = legacy / "projects/demo" / binding["context"]
    snapshot = tree(archive)
    fake = FakeAoE(legacy)
    fake.sessions = {binding["session_id"]: AoESession(
        binding["session_id"], legacy, "codex", "live", "idle", "native", "Toulmin: demo"
    )}  # fmt: skip
    assert AoEWorkspace(legacy, "demo", fake).status().context_status != "stale"
    confirm(legacy)
    view = AoEWorkspace(legacy, "demo", fake).status()
    assert view.context_status.startswith("stale")
    assert view.binding.version == 1
    assert tree(archive) == snapshot
    assert fake.created == [] and fake.sent == []


def test_repeat_with_the_same_digest_returns_the_receipt(legacy):
    plan = plan_of(legacy)
    first = confirm(legacy, plan.digest)
    receipt = (legacy / first.directory / "receipt.md").read_bytes()
    after = tree(legacy)
    again = confirm(legacy, plan.digest[:20], actor="Someone Else")
    assert again.status == "replayed" and again.receipt == first.receipt
    assert (
        tree(legacy) == after and (legacy / first.directory / "receipt.md").read_bytes() == receipt
    )
    with pytest.raises(FormatError, match="already configured"):
        confirm(legacy, "f" * 64 if not plan.digest.startswith("f") else "0" * 64)
    shown = invoke("workspace", "adopt", legacy)
    assert f"Adopted: {first.directory} by Tianchi YU" in shown.stdout
    cli = invoke(
        "workspace", "adopt", legacy, "--plan-digest", plan.digest, "--confirm",
        env={"TOULMIN_ACTOR": "Tianchi YU"},
    )  # fmt: skip
    assert cli.exit_code == 0 and "Already recorded; nothing written." in cli.stdout


def test_adopted_workspace_supports_the_workspace_operations(legacy):
    confirm(legacy)
    (legacy / "runs/drafts/focus.md").write_text(
        "---\nschema_version: 1\nkind: workspace-change-input\nscope: {kind: workspace}\n"
        "supersedes: null\nsources: []\npins: []\nchanges:\n  - target: charter\n"
        '    sections: {Direction: "Tail latency."}\n---\n## Question\nDirection?\n\n'
        "## Unresolved assumptions\nNone.\n"
    )
    assert propose_change(legacy, "runs/drafts/focus.md").status == "proposed"
    listing = invoke("status", "--root", legacy)
    assert listing.exit_code == 0 and "Workspace: Serving Research" in listing.stdout


def test_cli_confirm_reports_published_files_and_starts_nothing(legacy):
    plan = plan_of(legacy)
    result = invoke(
        "workspace", "adopt", legacy, "--name", NAME, "--plan-digest", plan.digest,
        "--confirmed-by", "Tianchi YU", "--confirm",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    for line in (
        "Disposition: applied by Tianchi YU",
        "Published: AGENTS.md",
        "Published: WORKSPACE.md",
        "No model or session was started.",
    ):
        assert line in result.stdout, line


# Interrupted adoption (section 10).


def crash_on(monkeypatch, name):
    original = workspace_journal.write_atomic

    def failing(path, data, **kwargs):
        if Path(path).name == name:
            raise OSError("simulated crash")
        return original(path, data, **kwargs)

    monkeypatch.setattr(workspace_journal, "write_atomic", failing)


@pytest.mark.parametrize("name", ["AGENTS.md", ".gitkeep", "seal", "WORKSPACE.md", "receipt.md"])
def test_interrupted_adoption_recovers_forward_with_the_first_actor(legacy, monkeypatch, name):
    plan = plan_of(legacy)
    crash_on(monkeypatch, name)
    with pytest.raises(OSError, match="simulated crash"):
        confirm(legacy, plan.digest, approval_text="Yes.")
    monkeypatch.undo()
    assert (legacy / workspace_journal.JOURNAL).exists()
    report = workspace_status(legacy, {})
    assert any("incomplete adoption" in error for error in report.errors)
    shown = invoke("workspace", "adopt", legacy)
    assert "State: adoption incomplete" in shown.stdout and plan.digest in shown.stdout
    with pytest.raises(FormatError, match="incomplete adoption of plan"):
        confirm(legacy, "0" * 16 if not plan.digest.startswith("0" * 16) else "1" * 16)
    result = confirm(legacy, plan.digest, actor="Someone Else")
    assert result.status == "recovered"
    assert "recovery keeps the first confirmation by Tianchi YU" in result.problems[0]
    assert result.receipt.actor == "Tianchi YU" and result.receipt.approval_text == "Yes."
    for change in plan.changes:
        assert (legacy / change.path).read_bytes() == change.after
    assert workspace_status(legacy, {}).errors == ()
    assert confirm(legacy, plan.digest).status == "replayed"


def test_external_edit_during_recovery_is_preserved(legacy, monkeypatch):
    plan = plan_of(legacy)
    crash_on(monkeypatch, "WORKSPACE.md")
    with pytest.raises(OSError):
        confirm(legacy, plan.digest)
    monkeypatch.undo()
    (legacy / "AGENTS.md").write_text("hand edit\n")
    with pytest.raises(FormatError, match="changed outside this publication"):
        confirm(legacy, plan.digest)
    assert (legacy / "AGENTS.md").read_text() == "hand edit\n"
    assert (legacy / workspace_journal.JOURNAL).exists()
    assert not (legacy / "WORKSPACE.md").exists()
