"""Source sessions use local fixtures and fake AoE only; no native tools are launched."""

import json
import shutil
from dataclasses import replace

import pytest

from toulmin.adapters.aoe import AoEClient, AoEError, AoESession
from toulmin.application.aoe import AoEWorkspace, scope_state
from toulmin.application.sources import filesystem_identity
from toulmin.application.workspace_remove import _sessions
from toulmin.cli.initialize import initialize, initialize_workspace
from toulmin.core.documents import FormatError
from toulmin.core.sources import Source, render_bindings, render_catalog


class SourceAoE(AoEClient):
    def __init__(self, root):
        self.profile = "main"
        self.root = root
        self.sessions = {}
        self.other_profiles = []
        self.sent = []
        self.created = []

    def list_sessions(self):
        return tuple(self.sessions.values())

    def list_all_sessions(self):
        return tuple((self.profile, s) for s in self.sessions.values()) + tuple(self.other_profiles)

    def show(self, session_id):
        if session_id not in self.sessions:
            raise AoEError("missing")
        return self.sessions[session_id]

    def current(self):
        return next(iter(self.sessions.values()))

    def create(self, root, project, agent, *, title=None, add_directory=None):
        self.created.append((root, project, agent, add_directory))
        sid = f"{len(self.created):016x}"
        session = AoESession(sid, root, agent, "live", "idle", "native-" + sid, title or "")
        self.sessions[sid] = session
        return session

    def ready(self, session_id):
        return True, "idle"

    def send(self, session_id, message):
        self.sent.append((session_id, message))


def add_child(root, name):
    template = root.parent / ("template-" + name)
    initialize(template, name)
    shutil.copytree(template / "projects" / name, root / "projects" / name)


def associate(root, path, project="demo", source_id="code"):
    sources = [Source(source_id, project, "directory", "working", "directory-fixture")]
    (root / "sources.toml").write_bytes(render_catalog(tuple(sources)))
    (root / "tools/sources.local.toml").write_bytes(
        render_bindings({source_id: (str(path), filesystem_identity(path))})
    )


@pytest.fixture
def setup(tmp_path):
    root, source = tmp_path / "records", tmp_path / "source"
    initialize_workspace(root, "Research")
    add_child(root, "demo")
    source.mkdir()
    (source / "AGENTS.md").write_text("Use this repository's tests and commit policy.\n")
    associate(root, source)
    return root, source, SourceAoE(root)


def test_source_native_cwd_receipt_and_records_are_separate(setup):
    root, source, fake = setup
    project = root / "projects/demo"
    (project / "overview.md").write_text("Confirmed existing implementation.\n")
    (project / "runs/notebook.md").write_text("Unconfirmed observation.\n")
    service = AoEWorkspace(root, "demo", fake)
    view = service.open()
    assert fake.created == [(source, "demo", "codex", root)]
    assert view.binding.version == 3
    assert view.binding.cwd == str(source)
    assert view.binding.source_id == "code"
    context = view.context_path.read_text()
    assert "repository's AGENTS.md" in context and "draft-task" in context
    assert "no-commit rule applies to the records workspace" in context
    archive = view.context_path.parent
    assert (archive / "inputs/projects/demo/overview.md").exists()
    assert (archive / "inputs/sources.toml").exists()
    assert not (archive / "inputs/tools/sources.local.toml").exists()
    assert "Unconfirmed working notebook" in (archive / "notebook.md").read_text()
    assert "unversioned directory" in context
    acknowledged = service.acknowledge(view.binding.token)
    assert acknowledged.context_status == "acknowledged"
    service.open()
    assert len(fake.sent) == 1
    stored = json.loads((root / "projects/demo/.aoe/binding.json").read_text())
    assert stored["schema_version"] == 3 and stored["cwd"] == str(source)
    assert not list(source.glob("runs/*"))


def test_changed_source_needs_explicit_archived_session_replacement(setup, tmp_path):
    root, source, fake = setup
    service = AoEWorkspace(root, "demo", fake)
    first = service.open()
    second = tmp_path / "new-source"
    second.mkdir()
    associate(root, second)
    with pytest.raises(FormatError, match="Working source changed"):
        service.open()
    with pytest.raises(FormatError, match="Working source changed"):
        service.refresh()
    with pytest.raises(FormatError, match="Existing session is live"):
        service.open(new_session=True)
    fake.sessions[first.session.id] = replace(first.session, state="archived")
    view = service.open(new_session=True)
    assert view.binding.cwd == str(second) and len(fake.created) == 2
    assert [s[0] for s in fake.sent] == [first.session.id, view.session.id]


@pytest.mark.parametrize("other_profile", [False, True])
def test_live_checkout_conflicts_across_scopes_and_profiles(setup, other_profile):
    root, source, fake = setup
    existing = AoESession("a" * 16, source, "claude", "live", "idle", "native-other", "Other")
    if other_profile:
        fake.other_profiles.append(("another-profile", existing))
    else:
        fake.sessions[existing.id] = existing
    with pytest.raises(FormatError, match="already has a live native session"):
        AoEWorkspace(root, "demo", fake).open()
    assert not fake.created and not fake.sent
    assert not (root / "projects/demo/.aoe/binding.json").exists()


def test_wrong_cwd_and_missing_mapping_never_receive_context(setup):
    root, source, fake = setup
    session = AoESession("a" * 16, root, "codex", "live", "idle", "native", "wrong cwd")
    fake.sessions[session.id] = session
    service = AoEWorkspace(root, "demo", fake)
    with pytest.raises(FormatError, match="path differs"):
        service.bind(session.id)
    assert not fake.sent
    (root / "tools/sources.local.toml").unlink()
    with pytest.raises(FormatError, match="local path missing"):
        service.open()
    assert not fake.created


def test_legacy_binding_is_not_retargeted_when_source_added(setup):
    root, source, fake = setup
    catalog = (root / "sources.toml").read_bytes()
    (root / "sources.toml").unlink()
    service = AoEWorkspace(root, "demo", fake)
    original = service.open()
    assert original.binding.version == 2
    (root / "sources.toml").write_bytes(catalog)
    with pytest.raises(FormatError, match="configured after this session"):
        service.open()
    assert len(fake.sent) == 1
    fake.sessions[original.session.id] = replace(original.session, state="archived")
    updated = service.open(new_session=True)
    assert updated.binding.version == 3 and updated.session.path == source


def test_notebook_recovery_is_bounded_unconfirmed_and_changes_freshness(setup):
    root, source, fake = setup
    notebook = root / "projects/demo/runs/notebook.md"
    notebook.write_text("omitted-first-line\n" + "x" * 20000 + "\nrecent observation\n")
    service = AoEWorkspace(root, "demo", fake)
    view = service.open()
    excerpt = (view.context_path.parent / "notebook.md").read_text()
    assert "omitted-first-line" not in excerpt
    assert "recent observation" in excerpt and "earlier text omitted" in excerpt
    assert len(excerpt.encode()) < 9000
    assert not (view.context_path.parent / "inputs/projects/demo/runs/notebook.md").exists()
    before = scope_state(root, "demo").fingerprint
    notebook.write_text("New working observation.\n")
    assert scope_state(root, "demo").fingerprint != before
    assert service.status().context_status.startswith("stale")


def test_removal_finds_bound_external_session_without_treating_source_as_records(setup):
    root, source, fake = setup
    view = AoEWorkspace(root, "demo", fake).open()
    sessions, blockers = _sessions(root, {view.session.id: "main"}, {"main"}, lambda _: fake)
    assert not blockers
    assert [s.id for s in sessions] == [view.session.id]
    assert source.is_dir() and (source / "AGENTS.md").exists()


def test_working_notebook_does_not_allocate_run_ids_or_exempt_other_bad_records(setup):
    from toulmin.core.identifiers import ObjectKind
    from toulmin.core.inspection import inspect_project
    from toulmin.core.repository import Repository

    root, source, fake = setup
    runs = root / "projects/demo/runs"
    (runs / "notebook.md").write_text("Freeform working observations.\n")
    repository = Repository(root)
    assert not inspect_project(repository, "demo").errors
    assert str(repository.next_id("demo", ObjectKind.RUN)) == "R-001"
    (runs / "notes.md").write_text("This is not an allowed formal Run.\n")
    assert inspect_project(repository, "demo").errors
    with pytest.raises(FormatError, match="invalid object filename"):
        repository.next_id("demo", ObjectKind.RUN)


def test_map_presents_confirmed_overview_logical_source_and_historical_next_step(setup):
    from toulmin.cli.research_map import Glyphs, render_project
    from toulmin.protocols.research_map import research_map

    root, source, fake = setup
    (root / "projects/demo/overview.md").write_text("Existing scheduler supports FIFO.\n")
    report = research_map(root, "demo")
    rendered = render_project(report, [], 120, Glyphs(True))
    assert "Overview (confirmed context)" in rendered
    assert "Existing scheduler supports FIFO." in rendered
    assert "code: working directory" in rendered and "not Evidence" in rendered
    assert "Recorded next step (historical):" in rendered


def test_git_source_report_distinguishes_catalog_digest_and_observed_revision(
    monkeypatch, tmp_path
):
    import subprocess

    from toulmin.application import aoe
    from toulmin.application.sources import ResolvedSource

    calls = []
    outputs = iter(["abc123\n", "main\n", " M module.py\n?? test_new.py\n"])

    def run(argv, **kwargs):
        calls.append(argv)
        assert kwargs["stdin"] == subprocess.DEVNULL
        return subprocess.CompletedProcess(argv, 0, next(outputs), "")

    monkeypatch.setattr(aoe.subprocess, "run", run)
    source = ResolvedSource("code", "demo", "git", "working", tmp_path, "catalog-sha", "git-root")
    report = aoe._source_report(source)
    assert "Catalog version: catalog-sha" in report
    assert "HEAD: abc123" in report and "Branch: main" in report
    assert "Worktree changes: 2" in report
    assert all("--no-optional-locks" in argv for argv in calls)
    assert all("fetch" not in argv for argv in calls)


def test_checkout_lock_serializes_cross_workspace_native_open(setup):
    from toulmin.core.atomic import handoff_mutex

    root, source, fake = setup
    with handoff_mutex(source / ".toulmin-native-writer"):
        with pytest.raises(FormatError, match="another handoff writer"):
            AoEWorkspace(root, "demo", fake).open()
    assert not fake.created and not fake.sent


def test_rebound_replaced_directory_with_same_path_needs_native_replacement(setup):
    root, source, fake = setup
    service = AoEWorkspace(root, "demo", fake)
    view = service.open()
    source.rename(source.with_name("original-source"))
    source.mkdir()
    associate(root, source)
    with pytest.raises(FormatError, match="Working source changed"):
        service.open()
    with pytest.raises(FormatError, match="stale"):
        service.acknowledge(view.binding.token)
    assert len(fake.created) == 1 and len(fake.sent) == 1


def test_task_draft_is_visible_in_state_and_map_without_creating_scientific_objects(setup):
    from toulmin.cli.research_map import Glyphs, render_project
    from toulmin.protocols.engineering_tasks import write_task_draft
    from toulmin.protocols.research_map import research_map
    from toulmin.protocols.research_workspace import render_state, research_state

    root, source, fake = setup
    draft = write_task_draft(root, "demo", source="code")
    state = research_state(root, "demo")
    assert not state.errors and not state.objects
    assert draft.name in render_state(state)
    report = research_map(root, "demo")
    assert draft.name in render_project(report, [], 120, Glyphs(True))
    assert "Engineering task draft" in "\n".join(report.task_summaries)
