"""Implementation integrity checks for the ignored launch-policy store (fake tools only)."""

import os
import shutil
from dataclasses import replace

import pytest

from toulmin.adapters.aoe import AoEClient, AoEError
from toulmin.application import native_policy
from toulmin.application.aoe import AoEWorkspace
from toulmin.application.native_policy import LOCAL, LaunchPolicy, load, save
from toulmin.application.sources import ResolvedSource
from toulmin.cli.initialize import initialize, initialize_workspace
from toulmin.core.documents import FormatError
from toulmin.core.repository import Repository


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "records 'quoted' Unicode 研究"
    source = tmp_path / "code 'quoted' Unicode 研究"
    initialize_workspace(root, "Temporary records")
    source.mkdir()
    resolved = ResolvedSource("code", "demo", "directory", "working", source, "v1", "identity")
    return Repository(root), resolved


def test_round_trip_is_private_and_preserves_other_project_choices(store):
    repository, source = store
    first = LaunchPolicy.choice("workspace-write", repository.root, source)
    save(repository, "demo", first)
    second = LaunchPolicy.choice("inherit", repository.root, source)
    save(repository, "another", second)
    assert load(repository) == {"demo": first, "another": second}
    assert os.stat(repository.root / LOCAL).st_mode & 0o777 == 0o600
    assert first.matches(repository.root, source)
    assert first.matches(repository.root, replace(source, version="ordinary code edits"))
    assert not first.matches(repository.root, replace(source, source_id="other"))
    assert not first.matches(repository.root, replace(source, identity="replaced"))


@pytest.mark.parametrize(
    "damage",
    [
        "bool-version",
        "mode",
        "relative-cwd",
        "unknown-key",
        "project",
        "duplicate",
        "utf8",
        "large",
    ],
)
def test_invalid_local_configuration_is_not_repaired_or_overwritten(store, damage):
    repository, source = store
    policy = LaunchPolicy.choice("workspace-write", repository.root, source)
    save(repository, "demo", policy)
    path = repository.root / LOCAL
    text = path.read_text()
    if damage == "bool-version":
        text = text.replace("schema_version = 1", "schema_version = true")
    elif damage == "mode":
        text = text.replace('sandbox = "workspace-write"', "sandbox = 1")
    elif damage == "relative-cwd":
        text = "\n".join(
            'cwd = "relative"' if line.startswith("cwd =") else line for line in text.splitlines()
        )
    elif damage == "unknown-key":
        text += 'approval_policy = "never"\n'
    elif damage == "project":
        text = text.replace('[projects."demo"]', '[projects."../escape"]')
    elif damage == "duplicate":
        text += 'sandbox = "inherit"\n'
    elif damage == "large":
        text += "#" + "x" * 1_000_000
    path.write_bytes(b"\xff" if damage == "utf8" else text.encode())
    original = path.read_bytes()
    with pytest.raises(FormatError, match="native.local.toml"):
        load(repository)
    with pytest.raises(FormatError, match="native.local.toml"):
        save(repository, "another", policy)
    assert path.read_bytes() == original


def test_failed_atomic_save_preserves_last_good_settings(store, monkeypatch):
    repository, source = store
    policy = LaunchPolicy.choice("workspace-write", repository.root, source)
    save(repository, "demo", policy)
    before = (repository.root / LOCAL).read_bytes()

    def fail(*args, **kwargs):
        raise OSError("simulated interrupted publication")

    monkeypatch.setattr(native_policy, "write_atomic", fail)
    with pytest.raises(OSError, match="interrupted"):
        save(repository, "another", policy)
    assert (repository.root / LOCAL).read_bytes() == before
    assert load(repository) == {"demo": policy}


def test_same_records_path_replaced_with_another_directory_invalidates_grant(store):
    repository, source = store
    policy = LaunchPolicy.choice("workspace-write", repository.root, source)
    repository.root.rename(repository.root.with_name("original records preserved"))
    repository.root.mkdir()
    assert not policy.matches(repository.root, source)


def test_symlinked_tools_directory_cannot_redirect_local_configuration(store, tmp_path):
    repository, source = store
    policy = LaunchPolicy.choice("workspace-write", repository.root, source)
    original = repository.root / "tools"
    outside = tmp_path / "unrelated"
    original.rename(outside)
    original.symlink_to(outside, target_is_directory=True)
    with pytest.raises(FormatError, match="symlinks forbidden"):
        save(repository, "demo", policy)
    assert not (outside / "native.local.toml").exists()


@pytest.mark.parametrize("mode", ["workspace-write", "inherit"])
@pytest.mark.parametrize("changed", ["source", "records"])
def test_directory_change_during_choice_is_refused_before_policy_or_session_write(
    store, tmp_path, monkeypatch, mode, changed
):
    repository, source = store
    # A valid child fixture without sharing any approved test support.
    template = tmp_path / "template"
    initialize(template, "demo")
    shutil.copytree(template / "projects/demo", repository.root / "projects/demo")
    other = tmp_path / "other source"
    other.mkdir()

    class NoLaunch(AoEClient):
        profile = "disposable"

        def __init__(self):
            pass

        def list_sessions(self):
            return ()

        def list_all_sessions(self):
            return ()

        def create(self, *args, **kwargs):
            raise AssertionError("A changed source must not be launched")

    service = AoEWorkspace(repository.root, "demo", NoLaunch())
    monkeypatch.setattr(service, "_source", lambda: source)

    def choose(observed, stale):
        assert observed == source and not stale
        if changed == "source":
            monkeypatch.setattr(service, "_source", lambda: replace(source, path=other))
        else:
            repository.root.rename(repository.root.with_name("original records preserved"))
            repository.root.mkdir()
        return mode

    with pytest.raises(FormatError, match="source changed|records directory changed"):
        service.open(choose_codex_sandbox=choose)
    assert not (repository.root / LOCAL).exists()
    assert not service.binding_path.exists()


@pytest.mark.parametrize(
    "agent,mode,project,add_records",
    [
        ("claude", "workspace-write", "demo", True),
        ("codex", "danger-full-access", "demo", True),
        ("codex", "read-only", "demo", True),
        ("codex", "workspace-write", None, True),
        ("codex", "workspace-write", "demo", False),
    ],
)
def test_adapter_rejects_inapplicable_sandbox_before_aoe_mutation(
    tmp_path, monkeypatch, agent, mode, project, add_records
):
    # Avoid executable discovery entirely; an invalid invocation must never execute.
    adapter = object.__new__(AoEClient)

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid policy must never reach AoE")

    monkeypatch.setattr(adapter, "_run", forbidden)
    with pytest.raises(AoEError, match="codex_sandbox"):
        adapter.create(
            tmp_path,
            project,
            agent,
            title="Temporary project",
            add_directory=tmp_path if add_records else None,
            codex_sandbox=mode,
        )


def test_codex_diagnostics_do_not_prescribe_codex_flags_for_claude():
    reason = AoEClient._not_prompt(
        "claude", "Error: failed to load configuration\n" + "\n" * 60 + "Pane is dead (status 1)\n"
    )
    assert "failed to load configuration" in reason
    assert "--new-session" in reason and "--codex-sandbox" not in reason


def test_invalid_native_choice_is_validated_before_entry_can_initialize(tmp_path):
    from typer.testing import CliRunner

    from toulmin.cli.app import app

    root = tmp_path / "missing research"
    result = CliRunner().invoke(
        app, ["open", "--root", str(root), "--codex-sandbox", "danger-full-access"]
    )
    assert result.exit_code == 2 and "workspace-write or inherit" in result.output
    assert not root.exists()


def test_workspace_permission_flag_is_refused_before_offering_initialization(tmp_path):
    from typer.testing import CliRunner

    from toulmin.cli.app import app

    root = tmp_path / "missing workspace"
    result = CliRunner().invoke(
        app, ["open", "--root", str(root), "--codex-sandbox", "workspace-write"]
    )
    assert result.exit_code == 2 and "external-source project" in result.output
    assert not root.exists()
