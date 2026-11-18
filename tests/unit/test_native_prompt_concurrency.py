"""Supervisor O3 regressions: an unlocked chooser must not consume stale consent."""

import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from toulmin.adapters.aoe import AoEClient, AoESession
from toulmin.application.aoe import AoEWorkspace
from toulmin.application.native_policy import LOCAL, LaunchPolicy, load, save
from toulmin.application.sources import filesystem_identity
from toulmin.cli.initialize import initialize, initialize_workspace
from toulmin.core.documents import FormatError
from toulmin.core.repository import Repository
from toulmin.core.sources import Source, render_bindings, render_catalog


class DisposableAoE(AoEClient):
    def __init__(self):
        self.profile = "fixture"
        self.sessions = {}
        self.created = []

    def list_sessions(self):
        return tuple(self.sessions.values())

    def list_all_sessions(self):
        return tuple((self.profile, session) for session in self.sessions.values())

    def show(self, sid):
        return self.sessions[sid]

    def create(self, cwd, project, agent, *, title=None, add_directory=None, codex_sandbox=None):
        sid = f"{len(self.created) + 1:016x}"
        session = AoESession(sid, cwd, agent, "live", "idle", "fake-" + sid, title or "")
        self.sessions[sid] = session
        self.created.append((cwd, codex_sandbox))
        return session

    def ready(self, sid):
        return True, "fixture idle"

    def send(self, sid, message):
        pass


def associate(root, source, source_id="code"):
    (root / "sources.toml").write_bytes(
        render_catalog((Source(source_id, "demo", "directory", "working", "fixture-identity"),))
    )
    (root / "tools/sources.local.toml").write_bytes(
        render_bindings({source_id: (str(source), filesystem_identity(source))})
    )


@pytest.fixture
def setup(tmp_path):
    root, source = tmp_path / "records", tmp_path / "code"
    initialize_workspace(root, "Disposable records")
    template = tmp_path / "template"
    initialize(template, "demo")
    shutil.copytree(template / "projects/demo", root / "projects/demo")
    source.mkdir()
    associate(root, source)
    fake = DisposableAoE()
    return root, source, fake, AoEWorkspace(root, "demo", fake)


def test_separate_process_can_acquire_workspace_and_checkout_locks_during_chooser(setup):
    root, source, fake, service = setup
    script = """
import sys
from pathlib import Path
from toulmin.core.atomic import handoff_mutex
with handoff_mutex(Path(sys.argv[1]) / '.aoe-binding-writer'):
    with handoff_mutex(Path(sys.argv[2]) / '.toulmin-native-writer'):
        print('both locks acquired')
"""

    def choose(observed, stale):
        result = subprocess.run(
            [sys.executable, "-c", script, str(root), str(source)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "both locks acquired"
        return "workspace-write"

    view = service.open(choose_codex_sandbox=choose)
    assert fake.created == [(source, "workspace-write")]
    assert view.binding.delivery == "submitted"


def test_concurrent_open_wins_without_stale_policy_overwrite_or_duplicate_writer(setup):
    root, source, fake, service = setup
    winner = []

    def choose(observed, stale):
        winner.append(AoEWorkspace(root, "demo", fake).open(codex_sandbox="inherit"))
        return "workspace-write"

    with pytest.raises(FormatError, match="changed while choosing"):
        service.open(choose_codex_sandbox=choose)
    assert fake.created == [(source, None)]
    assert load(Repository(root))["demo"].sandbox == "inherit"
    assert service.bound_session().session_id == winner[0].session.id


def test_policy_change_without_binding_is_not_overwritten_by_unlocked_chooser(setup):
    root, source, fake, service = setup
    written = []

    def choose(observed, stale):
        other = AoEWorkspace(root, "demo", fake)
        with other._lock():
            save(other.repository, "demo", LaunchPolicy.choice("inherit", root, observed))
            written.append((root / LOCAL).read_bytes())
        return "workspace-write"

    with pytest.raises(FormatError, match="changed while choosing"):
        service.open(choose_codex_sandbox=choose)
    assert (root / LOCAL).read_bytes() == written[0]
    assert not fake.created and not service.binding_path.exists()


def test_unbound_native_writer_appearing_during_chooser_is_not_duplicated(setup):
    root, source, fake, service = setup

    def choose(observed, stale):
        with AoEWorkspace(root, "demo", fake)._lock():
            fake.create(source, "demo", "codex", title="Manual fixture session")
        return "workspace-write"

    with pytest.raises(FormatError, match="changed while choosing"):
        service.open(choose_codex_sandbox=choose)
    assert fake.created == [(source, None)]
    assert not (root / LOCAL).exists() and not service.binding_path.exists()


@pytest.mark.parametrize("changed", ["source", "catalog", "checkout", "records"])
def test_directory_or_catalog_change_in_unlocked_interval_refuses_before_mutation(
    setup, tmp_path, changed
):
    root, source, fake, service = setup

    def choose(observed, stale):
        # This must be an actual unlocked interval, not just a before/after identity check.
        with AoEWorkspace(root, "demo", fake)._lock():
            if changed == "source":
                other = tmp_path / "new code"
                other.mkdir()
                associate(root, other, "new-code")
            elif changed == "catalog":
                (root / "sources.toml").write_bytes(
                    render_catalog(
                        (
                            Source("code", "demo", "directory", "working", "fixture-identity"),
                            Source("reference", "demo", "directory", "reference", "other-identity"),
                        )
                    )
                )
            elif changed == "checkout":
                source.rename(tmp_path / "preserved checkout")
                source.mkdir()
                associate(root, source)
            else:
                original = tmp_path / "preserved records"
                root.rename(original)
                shutil.copytree(original, root)
        return "workspace-write"

    with pytest.raises(FormatError, match="changed while choosing"):
        service.open(choose_codex_sandbox=choose)
    assert not fake.created and not (root / LOCAL).exists()
    assert not service.binding_path.exists()


def test_archived_session_revived_during_chooser_refuses_replacement(setup):
    root, source, fake, service = setup
    first = service.open(codex_sandbox="inherit")
    sid = first.session.id
    fake.sessions[sid] = replace(first.session, state="archived")
    (root / LOCAL).unlink()
    original = service.binding_path.read_bytes()

    def choose(observed, stale):
        with AoEWorkspace(root, "demo", fake)._lock():
            fake.sessions[sid] = replace(fake.sessions[sid], state="live")
        return "workspace-write"

    with pytest.raises(FormatError, match="changed while choosing"):
        service.open(new_session=True, choose_codex_sandbox=choose)
    assert len(fake.created) == 1 and service.binding_path.read_bytes() == original
    assert not (root / LOCAL).exists()


def test_equivalent_relative_and_absolute_roots_reuse_policy_and_binding(setup, monkeypatch):
    root, source, fake, service = setup
    first = service.open(codex_sandbox="workspace-write")
    policy = (root / LOCAL).read_bytes()
    monkeypatch.chdir(root.parent)
    relative = AoEWorkspace(Path(root.name), "demo", fake)
    assert relative.root == service.root == root
    assert relative.open().session.id == first.session.id
    assert len(fake.created) == 1 and (root / LOCAL).read_bytes() == policy


def test_relative_symlink_root_is_still_refused(setup, tmp_path, monkeypatch):
    root, source, fake, service = setup
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FormatError, match="symlinks forbidden"):
        AoEWorkspace(Path("alias"), "demo", fake)
    assert not fake.created


def test_reuse_does_not_reinterpret_changed_local_policy_or_prompt(setup, tmp_path):
    root, source, fake, service = setup
    original = service.open(codex_sandbox="inherit")
    unrelated = tmp_path / "unrelated.toml"
    unrelated.write_text("Do not read or write this through the launch policy\n")
    (root / LOCAL).unlink()
    (root / LOCAL).symlink_to(unrelated)

    def forbidden(*args):
        raise AssertionError("Reusing a session must not ask about new launch permissions")

    assert service.open(choose_codex_sandbox=forbidden).session.id == original.session.id
    assert len(fake.created) == 1 and (root / LOCAL).is_symlink()
    assert unrelated.read_text() == "Do not read or write this through the launch policy\n"


def test_new_claude_session_does_not_read_codex_policy_or_invoke_chooser(setup, tmp_path):
    root, source, fake, service = setup
    unrelated = tmp_path / "unrelated.toml"
    unrelated.write_text("Not a Codex policy\n")
    (root / LOCAL).symlink_to(unrelated)

    def forbidden(*args):
        raise AssertionError("Claude must not ask about Codex permissions")

    view = service.open("claude", choose_codex_sandbox=forbidden)
    assert view.session.tool == "claude" and fake.created == [(source, None)]
    assert (root / LOCAL).is_symlink() and unrelated.read_text() == "Not a Codex policy\n"


def test_saved_policy_lost_between_observation_and_publication_does_not_fall_back_to_inherit(
    setup, monkeypatch
):
    root, source, fake, service = setup
    original = service.open(codex_sandbox="workspace-write")
    fake.sessions[original.session.id] = replace(original.session, state="archived")
    before = service.binding_path.read_bytes()
    observe = service._choose_launch_policy

    def lose_policy(*args):
        result = observe(*args)
        assert result is None  # A valid saved policy did not require a prompt.
        (root / LOCAL).unlink()
        return result

    def forbidden(*args):
        raise AssertionError("A saved valid policy should not require a chooser")

    monkeypatch.setattr(service, "_choose_launch_policy", lose_policy)
    with pytest.raises(FormatError, match="changed during open"):
        service.open(new_session=True, choose_codex_sandbox=forbidden)
    assert len(fake.created) == 1 and service.binding_path.read_bytes() == before
    assert not (root / LOCAL).exists()


@pytest.mark.parametrize(
    "old,new",
    [
        (
            "Error adding directories: historical failure",
            "Error: managed requirements.toml refusal",
        ),
        (
            "Error: old configuration failure",
            "Error adding directories: latest writable roots refusal",
        ),
    ],
)
def test_dead_pane_uses_latest_relevant_error_not_earlier_history(old, new):
    reason = AoEClient._not_prompt(
        "codex", old + "\n" + new + "\n" * 60 + "Pane is dead (status 1)\n"
    )
    assert new in reason and old not in reason
    assert "--new-session" in reason
