"""S2: offline migration advice and workspace-local configuration on disposable fixtures."""

import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from toulmin.adapters.base import Finished
from toulmin.adapters.chief import load_config
from toulmin.application import workspace_sync
from toulmin.application.aoe import render_scope, scope_state
from toulmin.application.workspace_sync import sync_notices
from toulmin.cli import entry
from toulmin.cli.app import app
from toulmin.cli.initialize import initialize, initialize_workspace
from toulmin.core.documents import FormatError


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout


def tree(root):
    return {
        p.relative_to(root): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and not p.is_symlink()
    }


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root = tmp_path / "workspace"
    initialize_workspace(root, "Sync fixture")
    return root


def test_new_workspace_ignores_root_and_project_sessions_and_local_tools(workspace):
    root = workspace
    paths = [".aoe/binding.json", "projects/demo/.aoe/binding.json", "tools/chief.local.toml"]
    for name in paths:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n")
    assert git(root, "check-ignore", "--", *paths).splitlines() == paths
    assert not git(root, "ls-files", "--", *paths)
    assert sync_notices(root) == ()


def test_local_chief_config_overrides_keys_and_merges_repos(workspace):
    root = workspace
    base = root / "tools/chief.toml"
    base.write_text(
        'command = "old-chief"\nhome = "/old/state"\ntool = "codex"\ntrust = false\n'
        "verify_timeout_seconds = 600\nbudget = {rounds = 8, hours = 2}\n"
        '[repos]\na = "/old/a"\nb = "/old/b"\n'
    )
    old = load_config(root)
    assert old.command == ("old-chief",) and old.repos == {"a": "/old/a", "b": "/old/b"}
    local = root / "tools/chief.local.toml"
    local.write_text(
        'command = "local-chief --fixture"\nhome = "~/chief-fixture"\ntool = "claude"\n'
        "trust = true\nverify_timeout_seconds = 7\nbudget = {rounds = 2, hours = 0.5}\n"
        '[repos]\na = "~/code-a"\nc = "/local/c"\n'
    )
    config = load_config(root)
    assert config.command == ("local-chief", "--fixture") and config.tool == "claude"
    assert config.home == Path("~/chief-fixture").expanduser()
    assert config.trust and config.verify_timeout_seconds == 7
    assert config.budget == {"rounds": 2, "hours": 0.5}
    assert config.repos == {"a": str(Path("~/code-a").expanduser()), "b": "/old/b", "c": "/local/c"}
    local.unlink()
    assert load_config(root) == old


def test_local_only_partial_config_keeps_portable_defaults(workspace):
    root = workspace
    (root / "tools/chief.local.toml").write_text('[repos]\ndemo = "~/code-demo"\n')
    config = load_config(root)
    assert config.tool == "codex" and config.budget == {"rounds": 15, "hours": 4}
    assert config.repos == {"demo": str(Path("~/code-demo").expanduser())}
    (root / "tools/chief.toml").write_text('tool = "claude"\ntrust = true\n')
    assert load_config(root).tool == "claude" and load_config(root).trust


@pytest.mark.parametrize("home_file", ["chief.toml", "chief.local.toml"])
def test_inactive_environment_default_does_not_override_a_configured_home(
    workspace, monkeypatch, home_file
):
    monkeypatch.setenv("AOE_CHIEF_HOME", "invalid-relative-default")
    (workspace / "tools" / home_file).write_text('home = "/fixture/state"\n')
    if home_file == "chief.toml":
        (workspace / "tools/chief.local.toml").write_text('[repos]\ndemo = "/code"\n')
    assert load_config(workspace).home == Path("/fixture/state")


@pytest.mark.parametrize("filename", ["chief.toml", "chief.local.toml"])
@pytest.mark.parametrize(
    "bad",
    [
        "not TOML",
        'tool = "unknown"',
        'home = "relative"',
        'command = " "',
        'trust = "true"',
        "budget = {rounds = 1}",
        "verify_timeout_seconds = -1",
        '[repos]\ndemo = "relative"',
        "[repos]\ndemo = 1",
    ],
)
def test_config_errors_name_the_origin_even_when_the_other_file_overrides_it(
    workspace, filename, bad
):
    root = workspace
    (root / "tools/chief.toml").write_text('tool = "codex"\n')
    (root / "tools/chief.local.toml").write_text('tool = "claude"\n')
    (root / "tools" / filename).write_text(bad + "\n")
    with pytest.raises(FormatError) as error:
        load_config(root)
    assert str(root / "tools" / filename) in str(error.value)


@pytest.mark.parametrize("filename", ["chief.toml", "chief.local.toml"])
def test_config_refuses_symlink_files(workspace, tmp_path, filename):
    target = tmp_path / "outside.toml"
    target.write_text('tool = "claude"\n')
    (workspace / "tools" / filename).symlink_to(target)
    with pytest.raises(FormatError, match=filename):
        load_config(workspace)


@pytest.mark.parametrize(
    "missing", [(".aoe/",), ("tools/*.local.toml",), (".aoe/", "tools/*.local.toml")]
)
def test_missing_patterns_are_exact_lines_and_advice_does_not_rewrite_ignore(workspace, missing):
    root = workspace
    path = root / ".gitignore"
    path.write_text(
        "# local edits\n"
        + "".join(p + "\n" for p in workspace_sync.IGNORE_PATTERNS if p not in missing)
    )
    before = tree(root)
    assert sync_notices(root) == (
        "Machine-local files are not ignored: add these lines to .gitignore: " + ", ".join(missing),
    )
    assert tree(root) == before


def test_similar_ignore_patterns_do_not_count_as_exact_patterns(workspace):
    (workspace / ".gitignore").write_text("/.aoe/\ntools/*.local.toml \n# .aoe/\n")
    assert sync_notices(workspace) == (
        "Machine-local files are not ignored: add these lines to .gitignore: "
        ".aoe/, tools/*.local.toml",
    )


@pytest.mark.parametrize(
    "paths,command",
    [
        ([".aoe/binding.json"], "git rm -r --cached -- .aoe"),
        (["projects/demo/.aoe/binding.json"], "git rm -r --cached -- 'projects/*/.aoe/*'"),
        (["tools/chief.local.toml"], "git rm -r --cached -- 'tools/*.local.toml'"),
        (
            [".aoe/binding.json", "projects/demo/.aoe/binding.json", "tools/chief.local.toml"],
            "git rm -r --cached -- .aoe 'projects/*/.aoe/*' 'tools/*.local.toml'",
        ),
    ],
)
def test_tracked_machine_paths_get_a_working_exact_index_only_command(workspace, paths, command):
    root = workspace
    for value in paths:
        path = root / value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n")
    git(root, "add", "-f", "--", *paths)
    before = tree(root)
    assert sync_notices(root) == ("Tracked machine-local files: " + command,)
    assert tree(root) == before
    # Execute the printed suggestion only in this disposable fixture to verify its semantics.
    git(root, *shlex.split(command)[1:])
    assert not git(root, "ls-files", "--", *workspace_sync.TRACKED_PATTERNS)
    assert all((root / value).is_file() for value in paths)


@pytest.mark.parametrize("key", ['[repos]\ndemo = "/code"', 'home = "/state"', 'command = "chief"'])
@pytest.mark.parametrize("remote", [False, True])
def test_machine_keys_need_remote_before_migration_advice(workspace, key, remote):
    root = workspace
    (root / "tools/chief.toml").write_text(key + "\n")
    if remote:
        git(root, "remote", "add", "origin", "../never-contacted.git")
    expected = (
        "Machine paths in tools/chief.toml; move them to tools/chief.local.toml before syncing",
    )
    assert sync_notices(root) == (expected if remote else ())


def test_portable_settings_and_local_machine_keys_need_no_path_migration(workspace):
    git(workspace, "remote", "add", "origin", "../never-contacted.git")
    (workspace / "tools/chief.toml").write_text('tool = "claude"\ntrust = true\n')
    (workspace / "tools/chief.local.toml").write_text('[repos]\ndemo = "/code"\n')
    assert sync_notices(workspace) == ()


def test_no_dot_git_means_no_hints_or_external_commands(workspace, monkeypatch):
    root = workspace
    shutil.rmtree(root / ".git")
    (root / ".gitignore").unlink()
    (root / "tools/chief.toml").write_text('home = "/machine"\n')

    def forbidden(*args, **kwargs):
        raise AssertionError("git called without a workspace .git directory")

    monkeypatch.setattr(workspace_sync, "run_process", forbidden)
    assert sync_notices(root) == ()


def test_hint_git_reads_only_workspace_git_configuration(workspace, tmp_path, monkeypatch):
    private = tmp_path / "unused-user-gitconfig"
    private.write_text("invalid configuration that git must not read\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(private))
    assert sync_notices(workspace) == ()


@pytest.mark.parametrize("mode", ["exit", "timeout", "oserror"])
def test_git_failure_is_one_nonblocking_skipped_line(workspace, monkeypatch, mode):
    def broken(*args, **kwargs):
        if mode == "oserror":
            raise OSError("fixture git missing")
        return Finished(None if mode == "timeout" else 2, "", "fixture failure\n", 0)

    monkeypatch.setattr(workspace_sync, "run_process", broken)
    notices = sync_notices(workspace)
    assert len(notices) == 1 and notices[0].startswith("Machine-local sync check skipped:")
    assert ("timed out" if mode == "timeout" else "fixture") in notices[0]
    result = CliRunner().invoke(app, ["status", "--root", str(workspace)])
    assert result.exit_code == 0 and notices[0] in result.stdout

    def opened(root, project, *args, **kwargs):
        typer.echo(render_scope(scope_state(root, project)))

    monkeypatch.setattr(entry, "open_scope", opened)
    result = CliRunner().invoke(app, ["open", "--root", str(workspace)])
    assert result.exit_code == 0 and notices[0] in result.stdout


@pytest.mark.parametrize("project", [None, "demo"])
def test_status_and_open_notices_include_all_three_advisories(
    workspace, tmp_path, monkeypatch, project
):
    root = workspace
    if project:
        source = tmp_path / "legacy"
        initialize(source, project)
        shutil.copytree(source / "projects" / project, root / "projects" / project)
    (root / ".gitignore").write_text("# old ignore\n")
    (root / ".aoe").mkdir()
    (root / ".aoe/binding.json").write_text("fixture\n")
    git(root, "add", ".aoe/binding.json")
    git(root, "remote", "add", "origin", "../never-contacted.git")
    (root / "tools/chief.toml").write_text('[repos]\ndemo = "/fixture/code"\n')
    expected = sync_notices(root)
    assert len(expected) == 3

    def opened(root, project, *args, **kwargs):
        typer.echo(render_scope(scope_state(root, project)))

    monkeypatch.setattr(entry, "open_scope", opened)
    runner = CliRunner()
    for command in ("status", "open"):
        args = [command, *([project] if project else []), "--root", str(root)]
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
        if command == "open":
            assert "NOTICES" in result.stdout
        for notice in expected:
            assert notice in result.stdout
