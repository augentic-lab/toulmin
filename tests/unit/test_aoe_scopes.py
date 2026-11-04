"""WI5: workspace and child native sessions on a workspace root, with a fake AoE only.

Children here are synthetic prepared copies of the project template, not WI6 creation.
"""

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toulmin.adapters.aoe import AoEClient, AoEError, AoESession
from toulmin.application.aoe import AoEWorkspace
from toulmin.cli import aoe as aoe_cli
from toulmin.cli.app import app
from toulmin.cli.initialize import initialize, initialize_workspace
from toulmin.core.documents import FormatError
from toulmin.core.workspace import render_initial
from toulmin.protocols.workspace_change import apply as apply_change
from toulmin.protocols.workspace_change import propose

SID = "a" * 16
OTHER = "b" * 16
FOCUS = '  - target: charter\n    sections: {Focus: "Compare FIFO and SRPT first."}\n'


class FakeAoE(AoEClient):
    def __init__(self, root: Path, profile: str = "main"):
        self.profile = profile
        self.root = root
        self.sessions: dict[str, AoESession] = {}
        self.created: list[tuple[Path, str | None, str, str | None]] = []
        self.sent: list[tuple[str, str]] = []
        self.is_ready = True
        self.create_error: str | None = None

    def list_sessions(self):
        return tuple(self.sessions.values())

    def show(self, session_id):
        if session_id not in self.sessions:
            raise AoEError("No such session")
        return self.sessions[session_id]

    def current(self):
        return next(iter(self.sessions.values()))

    def add(self, session_id=SID, path=None, title="", native="native-a", tool="codex"):
        session = AoESession(session_id, path or self.root, tool, "live", "idle", native, title)
        self.sessions[session_id] = session
        return session

    def create(self, root, project, agent, *, title=None):
        # Real AoE refuses a title and path already used, even by an archived session (WI8 W3).
        if any(s.path == root and s.title == (title or "") for s in self.sessions.values()):
            raise AoEError("Session already exists with same title and path")
        self.created.append((root, project, agent, title))
        session = self.add(f"{len(self.created):016x}", root, title or "", tool=agent)
        if self.create_error == "unknown":
            raise AoEError("timeout", creation_uncertain=True)
        return session

    def ready(self, session_id):
        return self.is_ready, "idle" if self.is_ready else "trust prompt; open AoE and refresh"

    def send(self, session_id, message):
        self.sent.append((session_id, message))


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "serving"
    initialize_workspace(root, "Serving Research")
    return root


def add_child(root, name="scheduling"):
    template = root.parent / f"template-{name}"
    initialize(template, name)
    shutil.copytree(template / "projects" / name, root / "projects" / name)


@pytest.fixture
def fake(root):
    return FakeAoE(root)


def stored(root, project=None):
    relative = ".aoe/binding.json" if project is None else f"projects/{project}/.aoe/binding.json"
    return json.loads((root / relative).read_text())


def manifest(root, binding):
    return json.loads((root / binding["context"] / "manifest.json").read_text())


def write_change(root, name="change.md"):
    (root / "runs/drafts" / name).write_text(
        "---\nschema_version: 1\nkind: workspace-change-input\nscope: {kind: workspace}\n"
        f"supersedes: null\nsources: []\npins: []\nchanges:\n{FOCUS}"
        "---\n## Question\nFocus?\n\n## Unresolved assumptions\nNone.\n"
    )
    return f"runs/drafts/{name}"


# Workspace scope.


def test_workspace_open_creates_a_root_session_with_scoped_context(root, fake):
    view = AoEWorkspace(root, None, fake).open()
    assert fake.created == [(root, None, "codex", "Workspace: Serving Research")]
    binding = stored(root)
    assert binding["schema_version"] == 2 and binding["scope"] == {"kind": "workspace"}
    assert binding["title"] == "Workspace: Serving Research"
    assert list(binding)[:4] == ["schema_version", "scope", "title", "root"]
    assert "project" not in binding
    assert binding["context"].startswith("runs/") and binding["delivery"] == "submitted"
    data = manifest(root, binding)
    assert data["schema_version"] == 2 and data["scope"] == {"kind": "workspace"}
    assert sorted(data["files"]) == [
        "context.md", "inputs/AGENTS.md", "inputs/WORKSPACE.md", "state.md",
    ]  # fmt: skip
    context = (root / binding["context"] / "context.md").read_text()
    assert "aoe ack --workspace --root" in context
    assert "never claim a complete transcript" in context
    assert "not filesystem isolation" in context
    assert "Never apply or reject a packet yourself" in context
    assert "aoe handoff --workspace" in context
    card = (root / binding["context"] / "state.md").read_text()
    assert card.startswith("WORKSPACE\nServing Research | scope: Workspace | data: valid")
    assert "No confirmed direction yet." in card and "No projects yet." in card
    assert len(fake.sent) == 1 and view.context_status == "submitted"


def test_unchanged_reopen_does_not_resend_and_relevant_edits_go_stale(root, fake):
    service = AoEWorkspace(root, None, fake)
    service.open()
    context = stored(root)["context"]
    service.open()
    assert len(fake.sent) == 1 and stored(root)["context"] == context
    # Unrelated: a scratch draft and a child object do not change workspace freshness.
    (root / "runs/drafts/notes.md").write_text("scratch\n")
    assert service.status().context_status == "submitted"
    # A new pending packet and an applied change do.
    packet = propose(root, write_change(root))
    assert service.status().context_status.startswith("stale")
    service.refresh()
    assert len(fake.sent) == 2
    apply_change(root, packet.loaded.directory, "R", confirmed=True)
    assert service.status().context_status.startswith("stale")
    service.refresh()
    card = (root / stored(root)["context"] / "state.md").read_text()
    assert "FOCUS\nCompare FIFO and SRPT first." in card
    assert len(fake.sent) == 3


def test_acknowledgement_is_scoped_and_checked(root, fake):
    add_child(root)
    workspace = AoEWorkspace(root, None, fake)
    workspace.open()
    child = AoEWorkspace(root, "scheduling", fake)
    child.open()
    child_token = stored(root, "scheduling")["token"]
    with pytest.raises(FormatError, match="does not match the current context"):
        workspace.acknowledge(child_token)
    view = workspace.acknowledge(stored(root)["token"])
    assert view.context_status == "acknowledged"
    receipt = json.loads((root / stored(root)["context"] / "receipt.json").read_text())
    assert receipt["schema_version"] == 2 and receipt["scope"] == {"kind": "workspace"}
    assert stored(root, "scheduling")["delivery"] == "submitted"  # the child is untouched


def test_busy_session_is_not_sent_and_uncertain_creation_is_recovered(root, fake):
    fake.is_ready = False
    view = AoEWorkspace(root, None, fake).open()
    assert fake.sent == [] and stored(root)["delivery"] == "prepared"
    assert "trust prompt" in stored(root)["message"]
    assert view.context_status == "prepared"
    shutil.rmtree(root / ".aoe")
    fake.sessions.clear()
    fake.is_ready = True
    fake.create_error = "unknown"
    with pytest.raises(AoEError):
        AoEWorkspace(root, None, fake).open()
    assert stored(root)["session_id"] is None
    fake.create_error = None
    AoEWorkspace(root, None, fake).open()  # recovers by the recorded title; no new session
    assert len(fake.created) == 2 and stored(root)["session_id"] == f"{2:016x}"


def test_replacement_sessions_get_numbered_titles_aoe_accepts(root, fake):
    service = AoEWorkspace(root, None, fake)
    service.open()
    other = root.parent / "elsewhere"
    other.mkdir()
    fake.add("c" * 16, other, "Workspace: Serving Research (2)")  # another root: no clash
    for number in (2, 3):
        old = stored(root)["session_id"]
        fake.sessions[old] = replace(fake.sessions[old], state="archived")
        service.open(new_session=True)
        title = f"Workspace: Serving Research ({number})"
        assert fake.created[-1][3] == title and stored(root)["title"] == title
        assert stored(root)["session_id"] != old and stored(root)["delivery"] == "submitted"
    # An uncertain numbered creation is still recovered by its recorded title.
    old = stored(root)["session_id"]
    fake.sessions[old] = replace(fake.sessions[old], state="archived")
    fake.create_error = "unknown"
    with pytest.raises(AoEError):
        service.open(new_session=True)
    fake.create_error = None
    created = len(fake.created)
    service.open()
    assert len(fake.created) == created
    assert stored(root)["title"] == "Workspace: Serving Research (4)"
    assert stored(root)["session_id"] == f"{created:016x}"


def test_native_identity_change_requires_new_context(root, fake):
    service = AoEWorkspace(root, None, fake)
    service.open()
    first = stored(root)["context"]
    session = stored(root)["session_id"]
    fake.sessions[session] = replace(fake.sessions[session], agent_session_id="native-b")
    assert service.status().context_status.startswith("native conversation changed")
    service.refresh()
    assert stored(root)["context"] != first and stored(root)["provider_session_id"] == "native-b"


def test_workspace_session_must_be_at_the_root(root, fake):
    add_child(root)
    fake.add(SID, root / "projects/scheduling", "elsewhere")
    with pytest.raises(FormatError, match="workspace session's path must be the workbench root"):
        AoEWorkspace(root, None, fake).bind(SID)
    assert not (root / ".aoe/binding.json").exists()


# Two scopes side by side.


def test_child_on_a_workspace_root_gets_the_charter_not_workspace_discussion(root, fake):
    add_child(root)
    activity = root / "runs/20261104T093000Z-activity-6b1f0c2e9a4d4e7f8c3b2a1d0e9f8a7b"
    activity.mkdir()
    (activity / "activity.md").write_text("workspace discussion record\n")
    (root / "runs/drafts/workspace-notes.md").write_text("workspace scratch\n")
    AoEWorkspace(root, "scheduling", fake).open()
    binding = stored(root, "scheduling")
    assert binding["schema_version"] == 2
    assert binding["scope"] == {"kind": "project", "project": "scheduling"}
    assert binding["title"] == "Project: scheduling | Serving Research"
    assert fake.created[0] == (root, "scheduling", "codex", binding["title"])
    files = manifest(root, binding)["files"]
    assert "inputs/WORKSPACE.md" in files
    assert not any("activity" in name or "workspace-notes" in name for name in files)
    assert all(not name.startswith("inputs/runs/") for name in files)
    context = (root / binding["context"] / "context.md").read_text()
    assert "Scope: Project: scheduling." in context and "aoe ack scheduling" in context


def test_scopes_coexist_but_never_share_a_native_session(root, fake):
    add_child(root)
    fake.add(SID, root, "w")
    fake.add(OTHER, root, "c", native="native-c")
    AoEWorkspace(root, None, fake).bind(SID)
    with pytest.raises(FormatError, match="already bound to the workspace"):
        AoEWorkspace(root, "scheduling", fake).bind(SID)
    AoEWorkspace(root, "scheduling", fake).bind(OTHER)
    with pytest.raises(FormatError, match="already bound to project scheduling"):
        AoEWorkspace(root, None, fake).bind(OTHER, replace_existing=True)
    assert stored(root)["session_id"] == SID and stored(root, "scheduling")["session_id"] == OTHER
    assert fake.sent == []  # bind prepares files only


def test_version_one_binding_is_kept_until_explicit_replacement(tmp_path):
    legacy = tmp_path / "legacy"
    initialize(legacy, "scheduling")
    fake = FakeAoE(legacy)
    AoEWorkspace(legacy, "scheduling", fake).open()
    assert stored(legacy, "scheduling")["schema_version"] == 1
    assert fake.created[0][3] is None  # legacy title path: Toulmin: scheduling
    # Workspace state appears later (as adoption will do): the v1 binding stays v1.
    (legacy / "WORKSPACE.md").write_bytes(render_initial("Legacy Lab"))
    service = AoEWorkspace(legacy, "scheduling", fake)
    assert service.status().context_status.startswith("stale")  # WORKSPACE.md is now an input
    service.refresh()
    binding = stored(legacy, "scheduling")
    assert binding["schema_version"] == 1 and binding["project"] == "scheduling"
    assert manifest(legacy, binding)["schema_version"] == 1
    fake.add(OTHER, legacy, "replacement", native="native-r")
    AoEWorkspace(legacy, "scheduling", fake).bind(OTHER, replace_existing=True)
    replaced = stored(legacy, "scheduling")
    assert replaced["schema_version"] == 2 and replaced["title"] == "replacement"


def test_wrong_scope_binding_files_are_invalid(root, fake):
    add_child(root)
    AoEWorkspace(root, None, fake).open()
    binding = stored(root)
    target = root / "projects/scheduling/.aoe/binding.json"
    target.parent.mkdir()
    target.write_text(json.dumps(binding))
    view = AoEWorkspace(root, "scheduling", fake).status()
    assert view.context_status == "invalid binding"
    assert "scope does not match binding location" in view.diagnostics[0]
    # A version 2 binding whose manifest is version 1 is an invalid context.
    data = manifest(root, binding)
    data["schema_version"] = 1
    path = root / binding["context"] / "manifest.json"
    path.write_text(json.dumps(data, indent=2) + "\n")
    saved = stored(root)
    saved["manifest_sha256"] = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    (root / ".aoe/binding.json").write_text(json.dumps(saved, indent=2) + "\n")
    assert AoEWorkspace(root, None, fake).status().context_status == "invalid context"


def test_legacy_root_has_no_workspace_scope(tmp_path):
    legacy = tmp_path / "legacy"
    initialize(legacy, "scheduling")
    with pytest.raises(FormatError, match="workspace state not configured"):
        AoEWorkspace(legacy, None, FakeAoE(legacy))


# CLI selection and presentation.


@pytest.fixture
def cli(monkeypatch, fake):
    monkeypatch.setattr(aoe_cli, "AoEClient", lambda profile: fake)
    monkeypatch.setattr(
        aoe_cli,
        "AoEWorkspace",
        lambda root, project, client=None: AoEWorkspace(root, project, fake),
    )

    def run(*args):
        return CliRunner().invoke(app, ["aoe", *[str(arg) for arg in args]])

    return run


def test_cli_omitted_project_selects_the_workspace_even_with_one_child(root, cli, fake):
    add_child(root)
    result = cli("open", "--root", root)
    assert result.exit_code == 0, result.output
    assert result.output.startswith(f"Root: {root}\nScope: Workspace\n\nWORKSPACE\n")
    assert "scheduling | stage: explore" in result.output
    assert "Open project scheduling in its own session (not this one)." in result.output
    assert "Title: Workspace: Serving Research | binding version 2" in result.output
    assert fake.created[0][1] is None
    status = cli("status", "--workspace", "--root", root, "--offline")
    assert status.exit_code == 0, status.output
    assert "Scope: Workspace" in status.output
    child = cli("status", "scheduling", "--root", root, "--offline")
    assert "Scope: Project: scheduling" in child.output and "No saved binding." in child.output


def test_cli_conflicting_selectors_and_legacy_roots(root, cli, tmp_path):
    assert cli("status", "scheduling", "--workspace", "--root", root).exit_code == 2
    legacy = tmp_path / "legacy"
    initialize(legacy, "demo")
    result = cli("open", "--root", legacy)
    assert result.exit_code == 1
    assert "workspace state not configured" in result.output


def test_cli_stale_workspace_suggests_the_scoped_refresh(root, cli, fake):
    cli("open", "--root", root)
    propose(root, write_change(root))
    result = cli("status", "--root", root)
    assert "stale context; refresh required" in result.output
    assert f"toulmin aoe refresh --workspace --root {root}" in result.output
    assert len(fake.sent) == 1


def test_workspace_instructions_are_scope_aware_and_legacy_template_is_unchanged(root, tmp_path):
    text = (root / "AGENTS.md").read_text()
    for phrase in (
        "## Workspace and project scopes",
        "Scope is recorded data, not filesystem isolation",
        "never claim a complete transcript",
        "toulmin aoe handoff --workspace",
    ):
        assert phrase in text, phrase
    legacy = tmp_path / "legacy"
    initialize(legacy, "demo")
    shared = Path(__file__).resolve().parents[2] / "src/toulmin/cli/templates/AGENTS.md"
    assert (legacy / "AGENTS.md").read_bytes() == shared.read_bytes()
