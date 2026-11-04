"""WX2: user preferences, workbench discovery and ``toulmin open``.

Temporary directories and fake AoE only; the user's real config is isolated by conftest.
"""

import pytest
from typer.testing import CliRunner

from toulmin.cli import aoe, decide, entry, settings
from toulmin.cli.app import app
from toulmin.cli.initialize import initialize, initialize_workspace


@pytest.fixture(autouse=True)
def no_real_aoe(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("A real AoE adapter must not be constructed in CLI tests")

    monkeypatch.setattr(aoe, "AoEClient", refuse)
    for name in ("TOULMIN_ACTOR", "AGENT_OF_EMPIRES_PROFILE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def opened(monkeypatch):
    """Record what ``aoe open`` would receive instead of touching AoE."""
    calls = []

    def execute(root, project, profile, action, *, attach=False, **options):
        class Service:
            def open(self, agent=None, *, new_session=False, fallback_agent="codex"):
                calls.append(
                    {
                        "root": root,
                        "project": project,
                        "profile": profile,
                        "agent": agent or fallback_agent,
                        "new_session": new_session,
                        "attach": attach,
                    }
                )

        action(Service())

    monkeypatch.setattr(aoe, "_execute", execute)
    return calls


def configure(text):
    path = settings.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def run(*args, cwd=None, monkeypatch=None, prompt=None):
    if cwd is not None:
        monkeypatch.chdir(cwd)
    return CliRunner().invoke(app, list(args), input=prompt)


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "serving"
    initialize_workspace(root, "Serving Research")
    return root


# Configuration.


def test_absent_config_gives_defaults_and_full_config_is_read():
    current = settings.load_settings()
    assert not current.loaded and current.actor is None and current.attach is None
    configure(
        'actor = "Fixture Researcher"\n[aoe]\nprofile = "trial-1"\nagent = "claude"\n'
        "attach = true\n"
    )
    current = settings.load_settings()
    assert current.loaded
    assert (current.actor, current.profile, current.agent, current.attach) == (
        "Fixture Researcher", "trial-1", "claude", True,
    )  # fmt: skip


@pytest.mark.parametrize(
    "text",
    [
        "actor = \n",
        'actr = "typo"\n',
        '[aoe]\nprofle = "main"\n',
        "aoe = 3\n",
        'actor = ""\n',
        '[aoe]\nprofile = "bad profile"\n',
        '[aoe]\nagent = "gemini"\n',
        '[aoe]\nattach = "yes"\n',
    ],
)
def test_unusable_config_is_refused_without_repair(text):
    path = configure(text)
    with pytest.raises(settings.SettingsError):
        settings.load_settings()
    result = CliRunner().invoke(app, ["config", "show"])
    assert result.exit_code == 1 and f"Error: {path}" in result.output
    assert path.read_text() == text


def test_relative_xdg_config_home_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative/dir")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert settings.config_path() == tmp_path / ".config/toulmin/config.toml"


def test_actor_precedence_is_flag_then_environment_then_config(monkeypatch):
    assert settings.resolve_actor(None) is None
    configure('actor = "Config Actor"\n')
    assert settings.resolve_actor(None) == "Config Actor"
    monkeypatch.setenv("TOULMIN_ACTOR", "Environment Actor")
    assert settings.resolve_actor(None) == "Environment Actor"
    assert settings.resolve_actor("Flag Actor") == "Flag Actor"


def test_confirming_commands_take_the_configured_actor(workspace):
    args = ["workspace", "reject", "--draft", "runs/missing", "--reason", "r", "--confirm"]
    result = CliRunner().invoke(app, [*args, "--root", str(workspace)])
    assert result.exit_code == 2 and "actor in the toulmin config" in result.output
    configure('actor = "Config Actor"\n')
    result = CliRunner().invoke(app, [*args, "--root", str(workspace)])
    assert result.exit_code == 1 and "actor" not in result.output  # past the actor check


def test_config_show_names_each_source(monkeypatch):
    result = CliRunner().invoke(app, ["config", "show"])
    assert result.exit_code == 0, result.output
    assert "(not found)" in result.output and "actor: - (unset)" in result.output
    assert "aoe.profile: main (default)" in result.output
    assert "aoe.attach: false (default)" in result.output and "Example " in result.output
    configure('actor = "Config Actor"\n[aoe]\nprofile = "cfg"\nagent = "claude"\n')
    monkeypatch.setenv("AGENT_OF_EMPIRES_PROFILE", "env-profile")
    result = CliRunner().invoke(app, ["config", "show"])
    assert "(loaded)" in result.output and "Example " not in result.output
    assert "actor: Config Actor (config)" in result.output
    assert "aoe.profile: env-profile ($AGENT_OF_EMPIRES_PROFILE)" in result.output
    assert "aoe.agent: claude (config)" in result.output


def test_aoe_profile_default_is_environment_then_config(workspace, monkeypatch):
    seen = []

    def service(root, project, client=None, *, default_profile=None):
        seen.append((client, default_profile))

    monkeypatch.setattr(aoe, "AoEWorkspace", service)
    aoe._workspace(workspace, None, None)
    configure('[aoe]\nprofile = "cfg"\n')
    aoe._workspace(workspace, None, None)
    monkeypatch.setenv("AGENT_OF_EMPIRES_PROFILE", "env-profile")
    aoe._workspace(workspace, None, None)
    aoe._workspace(workspace, None, None, offline=True)
    assert seen == [(None, None), (None, "cfg"), (None, "env-profile"), (None, None)]


# Workbench discovery for --root.


def test_omitted_root_finds_the_workbench_above_and_says_so(workspace, monkeypatch):
    nested = workspace / "shared/notes/deep"
    nested.mkdir(parents=True)
    result = run("status", cwd=nested, monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.output
    assert f"Using workbench root {workspace}" in result.output
    assert f"Root: {workspace}\n" in result.output
    result = run("status", cwd=workspace, monkeypatch=monkeypatch)
    assert result.exit_code == 0 and "Using workbench root" not in result.output


def test_explicit_root_and_no_workbench_keep_the_old_behaviour(workspace, tmp_path, monkeypatch):
    nested = workspace / "shared/notes"
    nested.mkdir(parents=True)
    result = run("status", "--root", ".", cwd=nested, monkeypatch=monkeypatch)
    assert result.exit_code == 1 and "Using workbench root" not in result.output
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    result = run("status", cwd=outside, monkeypatch=monkeypatch)
    assert result.exit_code == 1 and "not initialized" in result.output


def test_legacy_project_directory_finds_its_workbench(workbench, monkeypatch):
    result = run("status", "demo", cwd=workbench / "projects/demo", monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.output
    assert f"Using workbench root {workbench}" in result.output


# toulmin open.


def test_open_offers_nothing_without_a_terminal(tmp_path, monkeypatch, opened):
    empty = tmp_path / "fresh"
    empty.mkdir()
    result = run("open", cwd=empty, monkeypatch=monkeypatch)
    assert result.exit_code == 1
    assert f"Create one with: toulmin init {empty}" in result.output
    assert list(empty.iterdir()) == [] and opened == []


@pytest.mark.parametrize(("answer", "created"), [("y\n", True), ("n\n", False), ("\n", False)])
def test_open_initializes_only_on_an_explicit_yes(tmp_path, monkeypatch, opened, answer, created):
    empty = tmp_path / "fresh"
    empty.mkdir()
    monkeypatch.setattr(entry, "_interactive", lambda: True)
    result = run("open", cwd=empty, monkeypatch=monkeypatch, prompt=answer)
    assert "and open its session? [y/N]" in result.output
    assert (empty / "WORKSPACE.md").exists() is created
    if created:
        assert result.exit_code == 0, result.output
        assert opened == [
            {"root": empty, "project": None, "profile": None, "agent": "codex",
             "new_session": False, "attach": False},
        ]  # fmt: skip
    else:
        assert result.exit_code == 1 and "Nothing created." in result.output
        assert list(empty.iterdir()) == [] and opened == []


def test_open_refuses_unrelated_directories_and_project_before_init(tmp_path, monkeypatch, opened):
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "notes.txt").write_text("someone else's file\n")
    monkeypatch.setattr(entry, "_interactive", lambda: True)
    result = run("open", cwd=busy, monkeypatch=monkeypatch, prompt="y\n")
    assert result.exit_code == 1 and "not a Toulmin workbench" in result.output
    empty = tmp_path / "fresh"
    empty.mkdir()
    result = run("open", "scheduling", cwd=empty, monkeypatch=monkeypatch, prompt="y\n")
    assert result.exit_code == 1 and "no workspace yet" in result.output
    assert sorted(path.name for path in busy.iterdir()) == ["notes.txt"]
    assert list(empty.iterdir()) == [] and opened == []


def test_open_selects_workspace_or_the_child_you_are_in(workspace, monkeypatch, opened):
    child = workspace / "projects/scheduling/notes"
    child.mkdir(parents=True)
    assert run("open", cwd=workspace / "shared", monkeypatch=monkeypatch).exit_code == 0
    assert run("open", cwd=child, monkeypatch=monkeypatch).exit_code == 0
    assert run("open", "other", cwd=child, monkeypatch=monkeypatch).exit_code == 0
    explicit = run("open", "--root", str(workspace), cwd=child, monkeypatch=monkeypatch)
    assert explicit.exit_code == 0
    assert [(call["root"], call["project"]) for call in opened] == [
        (workspace, None), (workspace, "scheduling"), (workspace, "other"), (workspace, None),
    ]  # fmt: skip


def test_open_on_a_legacy_workbench_needs_a_project(workbench, monkeypatch, opened):
    result = run("open", cwd=workbench, monkeypatch=monkeypatch)
    assert result.exit_code == 1 and "toulmin workspace adopt" in result.output
    result = run("open", cwd=workbench / "projects/demo", monkeypatch=monkeypatch)
    assert result.exit_code == 0, result.output
    assert [(call["root"], call["project"]) for call in opened] == [(workbench, "demo")]


def test_open_uses_preferences_and_flags_win(workspace, monkeypatch, opened):
    configure('[aoe]\nagent = "claude"\nattach = true\n')
    assert run("open", cwd=workspace, monkeypatch=monkeypatch).exit_code == 0
    flags = ("--agent", "codex", "--no-attach", "--profile", "trial", "--new-session")
    assert run("open", *flags, cwd=workspace, monkeypatch=monkeypatch).exit_code == 0
    assert [(c["agent"], c["attach"], c["profile"], c["new_session"]) for c in opened] == [
        ("claude", True, None, False), ("codex", False, "trial", True),
    ]  # fmt: skip


def test_open_notes_items_awaiting_decision(workspace, monkeypatch, opened):
    items = (decide.Item("change", "runs/a"), decide.Item("handoff", "runs/b/draft.md"))
    monkeypatch.setattr(entry, "inventory", lambda root: decide.Inventory(items, 0))
    result = run("open", cwd=workspace, monkeypatch=monkeypatch)
    assert "Awaiting your decision: 2 item(s); run `toulmin decide`." in result.output


def test_open_and_config_are_registered():
    runner = CliRunner()
    output = runner.invoke(app, ["--help"]).output
    assert "open" in output and "config" in output
    assert runner.invoke(app, ["open", "--help"]).exit_code == 0
    assert "--attach" in runner.invoke(app, ["aoe", "open", "--help"]).output


def test_legacy_init_fixture_is_still_a_workbench(tmp_path):
    root = tmp_path / "legacy"
    initialize(root, "demo")
    assert settings.find_workbench(root / "projects/demo/claims") == root
