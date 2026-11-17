"""O1/O2/O5 source linking, immutable inventory, decisions and interrupted publication."""

import json
import subprocess
from dataclasses import replace

import pytest

from toulmin.application.onboarding import add_source, prepare
from toulmin.application.sources import bind_source, inspect_source, resolve_working_source
from toulmin.cli.initialize import initialize_workspace
from toulmin.core import workspace_journal
from toulmin.core.atomic import digest
from toulmin.core.documents import FormatError
from toulmin.core.sources import CATALOG, LOCAL, Source, parse_catalog, read_catalog, render_catalog
from toulmin.protocols import context_change, onboarding


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "research"
    initialize_workspace(root)
    return root


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source"
    path.mkdir()
    (path / "README.md").write_text("Existing prototype.\n")
    (path / "package").mkdir()
    (path / "package" / "main.py").write_text("print('hello')\n")
    (path / "other").mkdir()
    (path / "other" / "notes.md").write_text("Design notes.\n")
    return path


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True).stdout


def init_git(source):
    git(source, "init", "-q")
    git(source, "config", "user.name", "Fixture")
    git(source, "config", "user.email", "fixture@example.invalid")
    git(source, "add", ".")
    git(source, "commit", "-qm", "Fixture baseline")


def applied(root, source, project="demo"):
    packet = prepare(root, source, project)
    assert (
        onboarding.apply(root, packet.loaded.directory, "Operator", confirmed=True).status
        == "created"
    )
    return packet


def test_inventory_nongit_multiple_directories_secrets_and_links(workspace, source, tmp_path):
    (source / ".env").write_text("SUPER_SECRET=unsafe")
    (source / "credentials.json").write_text("unsafe")
    (source / "node_modules").mkdir()
    (source / "node_modules" / "ignored.md").write_text("unsafe")
    outside = tmp_path / "outside.md"
    outside.write_text("unsafe")
    (source / "link.md").symlink_to(outside)
    data = inspect_source(workspace, source)
    inventory = json.loads(data.inventory)
    names = {entry["path"] for entry in inventory["files"]}
    assert names == {"README.md", "package/main.py", "other/notes.md"}
    assert b"unsafe" not in data.inventory
    assert not inventory["truncated"]


def test_git_inventory_preserves_dirty_and_ignores_untracked(workspace, source):
    (source / ".gitignore").write_text("ignored.txt\n")
    init_git(source)
    (source / "ignored.txt").write_text("unsafe")
    (source / "README.md").write_text("Dirty researcher text.\n")
    before = git(source, "status", "--porcelain=v1")
    inspection = inspect_source(workspace, source)
    assert inspection.kind == "git"
    assert "README.md" in json.loads(inspection.inventory)["status"]
    assert b"Dirty researcher text" in inspection.inventory
    assert b"ignored.txt" not in inspection.inventory
    applied(workspace, source)
    assert git(source, "status", "--porcelain=v1") == before
    assert (source / "README.md").read_text() == "Dirty researcher text.\n"


def test_prepare_then_confirm_no_claims_or_machine_paths_in_archive(workspace, source):
    packet = prepare(workspace, source, "demo", overview="# Structure\nSee package/main.py.\n")
    assert not (workspace / "projects/demo").exists()
    assert not (workspace / CATALOG).exists()
    assert onboarding.apply(workspace, packet.loaded.directory, None).status == "preview"
    assert (
        onboarding.apply(workspace, packet.loaded.directory, "Operator", confirmed=True).status
        == "created"
    )
    assert (workspace / "projects/demo/overview.md").read_text().startswith("# Structure")
    assert not list((workspace / "projects/demo/claims").glob("*.md"))
    resolved = resolve_working_source(workspace, "demo")
    assert resolved is not None and resolved.path == source
    for path in (workspace / "runs").rglob("*"):
        if path.is_file():
            assert str(source).encode() not in path.read_bytes(), path
    assert str(source) in (workspace / LOCAL).read_text()
    assert (
        onboarding.apply(workspace, packet.loaded.directory, "Operator", confirmed=True).status
        == "replayed"
    )
    assert onboarding.onboarding_context_files(workspace, "demo")


def test_shared_source_id_across_two_project_associations(workspace, source):
    applied(workspace, source, "first")
    applied(workspace, source, "second")
    first, second = read_catalog(workspace)
    assert first.source_id == second.source_id
    assert first.project != second.project
    assert resolve_working_source(workspace, "first").path == source
    assert resolve_working_source(workspace, "second").path == source


def test_catalog_duplicate_conflicting_identity_and_two_working_rejected():
    source = Source("source-one", "first", "git", "working", "git:abc")
    data = render_catalog((source, replace(source, project="second")))
    assert len(parse_catalog(data)) == 2
    with pytest.raises(FormatError, match="identity"):
        render_catalog((source, replace(source, project="second", identity="git:def")))
    with pytest.raises(FormatError, match="at most one"):
        render_catalog((source, replace(source, source_id="source-two")))


def test_two_clones_can_have_separate_reference_and_working_bindings(workspace, source, tmp_path):
    init_git(source)
    target = tmp_path / "working"
    subprocess.run(["git", "clone", "-q", str(source), str(target)], check=True)
    packet = prepare(workspace, source, "demo", work_at=target)
    onboarding.apply(workspace, packet.loaded.directory, "Operator", confirmed=True)
    sources = read_catalog(workspace)
    assert {s.role for s in sources} == {"reference", "working"}
    assert len({s.source_id for s in sources}) == 2
    assert resolve_working_source(workspace, "demo").path == target


def test_source_overlap_and_symlinks_refused_before_mutation(workspace, source, tmp_path):
    with pytest.raises(FormatError, match="non-overlapping"):
        prepare(workspace, workspace, "demo")
    alias = tmp_path / "alias"
    alias.symlink_to(source, target_is_directory=True)
    with pytest.raises(FormatError, match="symlinks"):
        prepare(workspace, alias, "demo")
    assert not (workspace / CATALOG).exists()


def test_stale_catalog_and_tampered_inventory_refused(workspace, source):
    packet = prepare(workspace, source, "demo")
    (workspace / CATALOG).write_bytes(render_catalog(()))
    with pytest.raises(FormatError, match="changed since"):
        onboarding.apply(workspace, packet.loaded.directory, "Operator", confirmed=True)
    inventory = workspace / packet.loaded.directory / "inventory/1.json"
    inventory.write_text("tampered")
    with pytest.raises(FormatError, match="inventory changed"):
        onboarding.load(workspace, packet.loaded.directory)
    assert not (workspace / "projects/demo").exists()


def test_rejection_never_creates_project(workspace, source):
    packet = prepare(workspace, source, "demo")
    assert (
        onboarding.reject(workspace, packet.loaded.directory, "Operator", "Scope unclear").status
        == "rejected"
    )
    with pytest.raises(FormatError, match="rejected"):
        onboarding.apply(workspace, packet.loaded.directory, "Operator", confirmed=True)
    assert not (workspace / "projects/demo").exists()


def test_interrupted_publication_recovers_without_second_child(workspace, source, monkeypatch):
    packet = prepare(workspace, source, "demo")
    real_finish = onboarding.finish
    monkeypatch.setattr(
        onboarding, "finish", lambda repo: (_ for _ in ()).throw(OSError("power loss"))
    )
    with pytest.raises(OSError, match="power loss"):
        onboarding.apply(workspace, packet.loaded.directory, "Operator", confirmed=True)
    assert (workspace / workspace_journal.JOURNAL).is_dir()
    monkeypatch.setattr(onboarding, "finish", real_finish)
    assert onboarding.apply(workspace, packet.loaded.directory, None).status == "incomplete"
    assert (
        onboarding.apply(
            workspace, packet.loaded.directory, "Other Operator", confirmed=True
        ).status
        == "recovered"
    )
    assert resolve_working_source(workspace, "demo").path == source
    receipt = (workspace / packet.loaded.directory / "receipt.md").read_text()
    assert "Other Operator" not in receipt


def test_clone_without_local_paths_has_inventory_and_requires_bind(workspace, source):
    applied(workspace, source)
    (workspace / LOCAL).unlink()
    for path in (workspace / "tools").glob("onboard-*.local.toml"):
        path.unlink()
    assert onboarding.onboarding_context_files(workspace, "demo")
    with pytest.raises(FormatError, match="local path missing"):
        resolve_working_source(workspace, "demo")
    source_id = read_catalog(workspace)[0].source_id
    bind_source(workspace, source_id, source)
    assert resolve_working_source(workspace, "demo").path == source


def test_rebind_wrong_identity_refused(workspace, source, tmp_path):
    applied(workspace, source)
    wrong = tmp_path / "wrong"
    wrong.mkdir()
    (wrong / "README.md").write_text("different")
    with pytest.raises(FormatError, match="identity mismatch"):
        bind_source(workspace, read_catalog(workspace)[0].source_id, wrong)


def test_overview_changes_only_on_confirmation_and_retains_history(workspace, source):
    applied(workspace, source)
    proposal = context_change.propose_overview(
        workspace,
        "demo",
        "# Components\npackage/main.py\n",
        rationale="Inventory reviewed",
        goal="Measure prototype latency.",
    )
    before = (workspace / "projects/demo/PROJECT.md").read_bytes()
    assert context_change.apply(workspace, proposal.loaded.directory, None).status == "preview"
    assert not (workspace / "projects/demo/overview.md").exists()
    context_change.apply(workspace, proposal.loaded.directory, "Operator", confirmed=True)
    assert (workspace / "projects/demo/overview.md").exists()
    assert b"Measure prototype latency" in (workspace / "projects/demo/PROJECT.md").read_bytes()
    assert (workspace / proposal.loaded.directory / "before/2").read_bytes() == before
    assert "+Measure prototype latency" in proposal.loaded.body


def test_overview_stale_and_arbitrary_stage_edit_refused(workspace, source):
    applied(workspace, source)
    proposal = context_change.propose_overview(
        workspace, "demo", "# Structure\n", rationale="reviewed", goal="Measure it."
    )
    base = workspace / proposal.loaded.directory
    after = base / "after/2"
    after.write_bytes(after.read_bytes().replace(b"stage: explore", b"stage: build"))
    packet = json.loads((base / "packet.md").read_bytes())
    packet["images"][1]["after"] = digest(after.read_bytes())
    data = json.dumps(packet).encode()
    (base / "packet.md").write_bytes(data)
    (base / "seal").write_text(digest(data) + "\n")
    with pytest.raises(FormatError, match="metadata or stage"):
        context_change.load(workspace, proposal.loaded.directory)


def test_add_working_direction_and_role_changes_are_reviewed(workspace, source, tmp_path):
    applied(workspace, source)
    target = tmp_path / "next-direction"
    target.mkdir()
    (target / "README.md").write_text("A new direction.\n")
    proposal = add_source(
        workspace, "demo", target, working=True, rationale="Continue in new direction"
    )
    assert resolve_working_source(workspace, "demo").path == source
    context_change.apply(workspace, proposal.loaded.directory, "Operator", confirmed=True)
    assert resolve_working_source(workspace, "demo").path == target
    sources = read_catalog(workspace)
    old = next(s for s in sources if s.role == "reference")
    role = context_change.propose_source_role(
        workspace, "demo", old.source_id, rationale="Return to baseline"
    )
    context_change.apply(workspace, role.loaded.directory, "Operator", confirmed=True)
    assert resolve_working_source(workspace, "demo").path == source
    for path in (workspace / "runs").rglob("*"):
        if path.is_file():
            assert str(target).encode() not in path.read_bytes(), path


def test_nongit_ignore_rules_exclude_files_and_directories(workspace, source):
    (source / ".gitignore").write_text("ignored.txt\nother/\n")
    (source / "ignored.txt").write_text("private ignored text")
    inventory = json.loads(inspect_source(workspace, source).inventory)
    names = {item["path"] for item in inventory["files"]}
    assert "README.md" in names and "package/main.py" in names
    assert "ignored.txt" not in names and "other/notes.md" not in names


def test_changed_nongit_source_retains_shared_logical_identity(workspace, source):
    applied(workspace, source, "first")
    (source / "README.md").write_text("Changed researcher's ongoing work.\n")
    applied(workspace, source, "second")
    sources = read_catalog(workspace)
    assert sources[0].source_id == sources[1].source_id
    assert sources[0].identity == sources[1].identity


def test_underlying_creation_cannot_bypass_linked_onboarding(workspace, source):
    from toulmin.protocols import project_creation

    packet = prepare(workspace, source, "demo")
    with pytest.raises(FormatError, match="complete onboarding packet"):
        project_creation.create(
            workspace, "demo", packet.loaded.creation, "Operator", confirmed=True
        )
    assert not (workspace / "projects/demo").exists()


def test_missing_source_at_confirmation_never_creates_child(workspace, source):
    packet = prepare(workspace, source, "demo")
    moved = source.with_name("moved-source")
    source.rename(moved)
    with pytest.raises(FormatError, match="disappeared"):
        onboarding.apply(workspace, packet.loaded.directory, "Operator", confirmed=True)
    assert not (workspace / "projects/demo").exists()


def test_unfilled_overview_is_never_promoted(workspace, source):
    applied(workspace, source)
    with pytest.raises(FormatError, match="unfilled"):
        context_change.propose_overview(
            workspace, "demo", "# Structure\n<fill: components>", rationale="Unedited draft"
        )
    assert not (workspace / "projects/demo/overview.md").exists()
