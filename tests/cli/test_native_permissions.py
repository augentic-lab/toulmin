"""O3 acceptance contract: explicit project-local Codex permissions and recovery.

Proposed CLI: open/aoe open --codex-sandbox workspace-write|inherit.
Proposed ignored execution file: tools/native.local.toml (versioned, project scoped).
The file's internal table layout is deliberately left to implementation. A saved
grant must be tied to the chosen source/checkout and records root, not transferable
to another checkout just because the project name matches.

Only AoE's transport is faked: real CLI routing, binding/context handling and native
argument construction execute. No provider, research workspace or global config is
accessed. Simulated AoE resume/restart checks its stored launch arguments; it is
not evidence that the installed AoE or Codex has passed live acceptance.
"""

import json
import os
import shlex
import shutil
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from toulmin.adapters import aoe as adapter
from toulmin.adapters.aoe import AoEClient, AoEError
from toulmin.application import aoe as application
from toulmin.application.aoe import AoEWorkspace
from toulmin.application.sources import filesystem_identity
from toulmin.cli import aoe as cli
from toulmin.cli import entry
from toulmin.cli.app import app
from toulmin.cli.initialize import initialize, initialize_workspace
from toulmin.core.sources import Source, render_bindings, render_catalog


class RecordedAoE(AoEClient):
    """Run the real adapter above a fail-closed, in-memory AoE command transport."""

    def __init__(self):
        self.profile = "o3-disposable"
        self.command = "never-executed-aoe"
        self.rows = {}
        self.calls = []
        self.launches = []
        self.saved_args = {}
        self.screens = {}
        self.default_screen = "› "
        self.lose_add_response = False

    def _run(self, *args, timeout=15.0):
        self.calls.append(args)
        if args[0] == "list":
            return json.dumps(list(self.rows.values()))
        if args[:2] == ("session", "show"):
            return json.dumps(self.rows[args[2]])
        if args[:2] == ("session", "capture"):
            return self.screens.get(args[2], self.default_screen)
        if args[0] == "add":
            sid = f"{len(self.launches) + 1:016x}"
            extra = (
                shlex.split(args[args.index("--extra-args") + 1]) if "--extra-args" in args else []
            )
            self.saved_args[sid] = tuple(extra)
            self.launches.append((sid, Path(args[1]), tuple(extra)))
            self.rows[sid] = {
                "id": sid,
                "profile": self.profile,
                "path": args[1],
                "tool": args[args.index("--tool") + 1],
                "state": "live",
                "status": "idle",
                "agent_session_id": "native-" + sid,
                "title": args[args.index("-t") + 1],
            }
            if self.lose_add_response:
                self.lose_add_response = False
                raise AoEError("Simulated lost add response", creation_uncertain=True)
            return f"Added session: {sid}\n"
        if args[0] == "send":
            assert args[1] == "--no-revive", "Context delivery must never revive a session"
            return ""
        raise AssertionError(f"Unexpected AoE operation (no real fallback permitted): {args}")

    def attach(self, session_id):
        self.calls.append(("attach-fixture-only", session_id))
        return 0

    def relaunch_in_aoe(self, session_id, *, fresh_identity):
        """Model external AoE resume/restart using exactly its saved arguments."""
        self.rows[session_id]["state"] = "live"
        if fresh_identity:
            self.rows[session_id]["agent_session_id"] += "-restarted"
        return self.saved_args[session_id]

    @property
    def sends(self):
        return [call for call in self.calls if call[0] == "send"]


def snapshot(root):
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def add_child(root, name):
    template = root.parent / ("template-" + name)
    if not template.exists():
        initialize(template, name)
    shutil.copytree(template / "projects" / name, root / "projects" / name)


def associate(root, source, project="demo", source_id="code"):
    # Synthetic source metadata avoids Git/provider subprocesses entirely.
    catalog = Source(source_id, project, "directory", "working", "directory-fixture")
    (root / "sources.toml").write_bytes(render_catalog((catalog,)))
    (root / "tools/sources.local.toml").write_bytes(
        render_bindings({source_id: (str(source), filesystem_identity(source))})
    )


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / "research records with spaces"
    source = tmp_path / "source code 'quoted' with spaces"
    initialize_workspace(root, "O3 disposable research")
    add_child(root, "demo")
    source.mkdir()
    (source / "AGENTS.md").write_text("Disposable fixture. No native model may run.\n")
    associate(root, source)
    fake = RecordedAoE()
    monkeypatch.setattr(cli, "AoEClient", lambda *args, **kwargs: fake)
    monkeypatch.setattr(application, "AoEClient", lambda *args, **kwargs: fake)
    monkeypatch.setattr(adapter.time, "sleep", lambda _: None)
    monkeypatch.setattr(AoEWorkspace, "startup_wait", 0)
    # The CLI boundary owns this check, following entry/decide conventions.
    monkeypatch.setattr(cli, "_interactive", lambda: False, raising=False)
    monkeypatch.setattr(entry, "_interactive", lambda: False)
    monkeypatch.delenv("AGENT_OF_EMPIRES_PROFILE", raising=False)
    monkeypatch.chdir(tmp_path)

    # Canary homes are disposable. Assert *all* their bytes stay unchanged, including
    # no newly created configuration, rather than inspecting the researcher's homes.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    homes = [home, Path(os.environ["CODEX_HOME"]), Path(os.environ["XDG_CONFIG_HOME"])]
    for base in homes:
        config = base / "config.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(
            '# sentinel: native/global settings must survive\nsandbox_mode = "read-only"\n'
        )
    aoe_config = home / ".config/agent-of-empires/config.toml"
    aoe_config.parent.mkdir(parents=True)
    aoe_config.write_text("# sentinel AoE profile\n[profiles.main]\n")
    before = [(base, snapshot(base)) for base in homes]
    source_before = snapshot(source)
    yield SimpleNamespace(root=root, source=source, fake=fake, monkeypatch=monkeypatch)
    assert snapshot(source) == source_before, "Opening must not write source files"
    for base, original in before:
        assert snapshot(base) == original, f"Global/native configuration changed: {base}"


def run(setup, *options, project="demo", aoe=False, answer=None, agent="codex"):
    args = ["aoe", "open"] if aoe else ["open"]
    if project is not None:
        args.append(project)
    elif aoe:
        args.append("--workspace")
    return CliRunner().invoke(
        app,
        [*args, "--root", str(setup.root), "--agent", agent, "--no-attach", *options],
        input=answer,
    )


def policy_path(setup):
    return setup.root / "tools/native.local.toml"


def binding_path(setup, project="demo"):
    return setup.root / f"projects/{project}/.aoe/binding.json"


def opt_in(setup, **kwargs):
    result = run(setup, "--codex-sandbox", "workspace-write", **kwargs)
    assert result.exit_code == 0, result.output
    sid, cwd, args = setup.fake.launches[-1]
    assert cwd == setup.source
    assert args == ("--sandbox", "workspace-write", "--add-dir", str(setup.root))
    assert "--ask-for-approval" not in args
    assert "--dangerously-bypass-approvals-and-sandbox" not in args
    return sid


@pytest.mark.parametrize("aoe", [False, True])
def test_noninteractive_unknown_policy_requires_actionable_explicit_choice(setup, aoe):
    prompts = []

    def forbidden_prompt(*args, **kwargs):
        prompts.append(args)
        raise AssertionError("Noninteractive opening must not prompt")

    setup.monkeypatch.setattr(cli.typer, "confirm", forbidden_prompt)
    setup.monkeypatch.setattr(cli.typer, "prompt", forbidden_prompt)
    result = run(setup, aoe=aoe)
    assert result.exit_code != 0, result.output
    assert "--codex-sandbox" in result.output
    assert "workspace-write" in result.output and "inherit" in result.output
    assert str(setup.source) in result.output and str(setup.root) in result.output
    assert not setup.fake.launches and not setup.fake.sends
    assert not prompts
    assert not policy_path(setup).exists() and not binding_path(setup).exists()


@pytest.mark.parametrize(
    "answer,mode", [("y\n", "workspace-write"), ("n\n", "inherit"), ("\n", "inherit")]
)
def test_interactive_choice_explains_both_roots_and_defaults_to_inherit(setup, answer, mode):
    setup.monkeypatch.setattr(cli, "_interactive", lambda: True, raising=False)
    setup.monkeypatch.setattr(entry, "_interactive", lambda: True)
    prompts = []
    original_confirm = cli.typer.confirm

    def confirm(*args, **kwargs):
        assert not setup.fake.launches, "Permission choice must precede native launch"
        prompts.append(args)
        return original_confirm(*args, **kwargs)

    setup.monkeypatch.setattr(cli.typer, "confirm", confirm)
    result = run(setup, answer=answer)
    assert result.exit_code == 0, result.output
    assert str(setup.source) in result.output and str(setup.root) in result.output
    assert "writ" in result.output.lower() and "workspace-write" in result.output
    assert "inherit" in result.output.lower()
    assert len(prompts) == 1
    expected = ("--add-dir", str(setup.root))
    if mode == "workspace-write":
        expected = ("--sandbox", "workspace-write", *expected)
    assert setup.fake.launches[-1][2] == expected
    assert mode in policy_path(setup).read_text()
    # The saved decision prevents a repeat prompt, including in later noninteractive use.
    setup.monkeypatch.setattr(cli, "_interactive", lambda: False)
    repeated = run(setup)
    assert repeated.exit_code == 0, repeated.output
    assert len(setup.fake.launches) == 1 and len(prompts) == 1


def test_aborted_interactive_choice_never_launches_or_persists_a_grant(setup):
    setup.monkeypatch.setattr(cli, "_interactive", lambda: True, raising=False)
    setup.monkeypatch.setattr(entry, "_interactive", lambda: True)
    result = run(setup, answer="")
    assert result.exit_code != 0, result.output
    assert not setup.fake.launches and not setup.fake.sends
    assert not policy_path(setup).exists() and not binding_path(setup).exists()


@pytest.mark.parametrize("aoe", [False, True])
def test_explicit_opt_in_is_ignored_project_local_and_persists_across_service_instances(setup, aoe):
    def formal_files():
        return {
            name: data
            for name, data in snapshot(setup.root / "projects/demo").items()
            if not name.startswith(("runs/", ".aoe/"))
        }

    formal = formal_files()
    sid = opt_in(setup, aoe=aoe)
    policy = policy_path(setup)
    document = tomllib.loads(policy.read_text())
    assert document["schema_version"] == 1
    assert "demo" in policy.read_text() and "workspace-write" in policy.read_text()
    assert "tools/*.local.toml" in (setup.root / ".gitignore").read_text()
    assert formal_files() == formal
    assert not any(
        name.endswith("native.local.toml") for name in snapshot(setup.root / "projects/demo/runs")
    ), "Local execution configuration must not be archived as research input"
    saved = policy.read_bytes()
    # A fresh application object reuses the binding; no second session or grants.
    view = AoEWorkspace(setup.root, "demo", setup.fake).open()
    assert view.session.id == sid and len(setup.fake.launches) == 1
    assert policy.read_bytes() == saved
    assert view.binding.version == 3
    assert view.binding.delivery == "submitted", "Native startup is not acknowledgment"
    assert not list((setup.root / "projects/demo/runs").rglob("receipt.json"))


def test_new_project_does_not_inherit_another_projects_permission_choice(setup):
    opt_in(setup)
    add_child(setup.root, "sibling")
    # Both children can share a logical source; archive demo to avoid the writer guard.
    setup.fake.rows[setup.fake.launches[0][0]]["state"] = "archived"
    original = Source("code", "demo", "directory", "working", "directory-fixture")
    sibling = Source("code", "sibling", "directory", "working", "directory-fixture")
    (setup.root / "sources.toml").write_bytes(render_catalog((original, sibling)))
    result = run(setup, project="sibling")
    assert result.exit_code != 0 and "--codex-sandbox" in result.output
    assert len(setup.fake.launches) == 1
    assert not binding_path(setup, "sibling").exists()


def test_saved_opt_in_applies_to_explicit_archived_replacement_without_reprompt(setup):
    first = opt_in(setup)
    policy = policy_path(setup).read_bytes()
    setup.fake.rows[first]["state"] = "archived"
    result = run(setup, "--new-session")
    assert result.exit_code == 0, result.output
    second, cwd, args = setup.fake.launches[-1]
    assert second != first and cwd == setup.source
    assert args == setup.fake.saved_args[first]
    assert policy_path(setup).read_bytes() == policy
    assert len(setup.fake.launches) == 2


@pytest.mark.parametrize("restart", [False, True], ids=["resume", "restart"])
def test_aoe_resume_or_restart_keeps_saved_launch_args_without_reconfiguring_session(
    setup, restart
):
    sid = opt_in(setup)
    expected = setup.fake.saved_args[sid]
    policy = policy_path(setup).read_bytes()
    assert setup.fake.relaunch_in_aoe(sid, fresh_identity=restart) == expected
    result = run(setup)
    assert result.exit_code == 0, result.output
    assert len(setup.fake.launches) == 1
    assert setup.fake.saved_args[sid] == expected
    assert policy_path(setup).read_bytes() == policy
    binding = json.loads(binding_path(setup).read_text())
    assert binding["session_id"] == sid
    assert binding["provider_session_id"] == setup.fake.rows[sid]["agent_session_id"]
    assert binding["delivery"] == "submitted"
    assert len(setup.fake.sends) == (2 if restart else 1)
    assert not any(
        call[0] in {"restart", "resume", "config", "remove"} for call in setup.fake.calls
    )


def test_restrictive_opt_out_persists_native_flags_without_sandbox_override(setup):
    result = run(setup, "--codex-sandbox", "inherit")
    assert result.exit_code == 0, result.output
    sid, cwd, args = setup.fake.launches[-1]
    assert cwd == setup.source and args == ("--add-dir", str(setup.root))
    assert "inherit" in policy_path(setup).read_text()
    setup.fake.rows[sid]["state"] = "archived"
    repeated = run(setup, "--new-session")
    assert repeated.exit_code == 0, repeated.output
    assert setup.fake.launches[-1][2] == args


@pytest.mark.parametrize("state", ["live", "archived"])
def test_policy_change_never_reconfigures_existing_binding_without_explicit_replacement(
    setup, state
):
    initial = run(setup, "--codex-sandbox", "inherit")
    assert initial.exit_code == 0, initial.output
    sid = setup.fake.launches[-1][0]
    setup.fake.rows[sid]["state"] = state
    before_policy = policy_path(setup).read_bytes()
    before_binding = binding_path(setup).read_bytes()
    result = run(setup, "--codex-sandbox", "workspace-write")
    assert result.exit_code != 0, result.output
    assert "--new-session" in result.output
    assert len(setup.fake.launches) == 1 and setup.fake.saved_args[sid] == (
        "--add-dir",
        str(setup.root),
    )
    assert policy_path(setup).read_bytes() == before_policy
    assert binding_path(setup).read_bytes() == before_binding
    explicit = run(setup, "--codex-sandbox", "workspace-write", "--new-session")
    if state == "live":
        assert explicit.exit_code != 0 and "archive" in explicit.output.lower()
        assert policy_path(setup).read_bytes() == before_policy
    else:
        assert explicit.exit_code == 0, explicit.output
        assert setup.fake.launches[-1][2] == (
            "--sandbox",
            "workspace-write",
            "--add-dir",
            str(setup.root),
        )


def test_existing_manually_configured_v3_session_is_reused_without_permission_prompt_or_edits(
    setup,
):
    # The pre-feature application path constructs an old v3 binding. Its AoE arguments
    # are manually configured and deliberately differ from Toulmin's proposed policy.
    view = AoEWorkspace(setup.root, "demo", setup.fake).open()
    sid = view.session.id
    custom = ("--sandbox", "read-only", "-c", 'model_reasoning_effort="high"')
    setup.fake.saved_args[sid] = custom
    before = binding_path(setup).read_bytes()
    result = run(setup)
    assert result.exit_code == 0, result.output
    assert setup.fake.saved_args[sid] == custom and len(setup.fake.launches) == 1
    assert binding_path(setup).read_bytes() == before
    assert not policy_path(setup).exists()


@pytest.mark.parametrize("legacy", [False, True], ids=["v2-workspace", "v1-legacy"])
def test_old_non_source_bindings_keep_native_behavior_and_version(setup, legacy):
    (setup.root / "sources.toml").unlink()
    if legacy:
        (setup.root / "WORKSPACE.md").unlink()
    result = run(setup)
    assert result.exit_code == 0, result.output
    assert setup.fake.launches[-1][1:] == (setup.root, ())
    assert json.loads(binding_path(setup).read_text())["schema_version"] == (1 if legacy else 2)
    assert not policy_path(setup).exists()


@pytest.mark.parametrize("explicit", [False, True])
def test_claude_unaffected_and_codex_choice_never_applied_to_claude(setup, explicit):
    if explicit:
        first = opt_in(setup)
        setup.fake.rows[first]["state"] = "archived"
    result = run(setup, *(["--new-session"] if explicit else []), agent="claude")
    assert result.exit_code == 0, result.output
    assert setup.fake.launches[-1][1:] == (setup.source, ("--add-dir", str(setup.root)))
    assert not any("--sandbox" in arg for arg in setup.fake.launches[-1][2])
    if not explicit:
        assert not policy_path(setup).exists()


@pytest.mark.parametrize("value", ["read-only", "danger-full-access", "typo"])
def test_unsupported_cli_policy_is_rejected_before_native_or_local_mutation(setup, value):
    result = run(setup, "--codex-sandbox", value)
    assert result.exit_code != 0
    assert not setup.fake.launches and not policy_path(setup).exists()
    assert not binding_path(setup).exists()


@pytest.mark.parametrize("damage", ["toml", "version", "mode"])
def test_invalid_saved_policy_is_actionable_and_never_silently_repaired(setup, damage):
    sid = opt_in(setup)
    setup.fake.rows[sid]["state"] = "archived"
    path = policy_path(setup)
    if damage == "toml":
        path.write_text("this is not [valid TOML\n")
    elif damage == "version":
        path.write_text("schema_version = 999\n")
    else:
        path.write_text(path.read_text().replace("workspace-write", "danger-full-access"))
    before = path.read_bytes()
    binding = binding_path(setup).read_bytes()
    result = run(setup, "--new-session")
    assert result.exit_code != 0, result.output
    assert "native.local.toml" in result.output
    assert path.read_bytes() == before and binding_path(setup).read_bytes() == binding
    assert len(setup.fake.launches) == 1


def test_saved_grant_is_stale_after_source_change_and_needs_a_new_explicit_choice(setup, tmp_path):
    sid = opt_in(setup)
    setup.fake.rows[sid]["state"] = "archived"
    original = policy_path(setup).read_bytes()
    different = tmp_path / "other checkout"
    different.mkdir()
    associate(setup.root, different, source_id="different-source")
    result = run(setup, "--new-session")
    assert result.exit_code != 0, result.output
    assert "--codex-sandbox" in result.output
    assert "stale" in result.output.lower() or "changed" in result.output.lower()
    assert len(setup.fake.launches) == 1 and policy_path(setup).read_bytes() == original
    # A new explicit opt-in is the review boundary for the new directory pair.
    result = run(setup, "--new-session", "--codex-sandbox", "workspace-write")
    assert result.exit_code == 0, result.output
    assert setup.fake.launches[-1][1:] == (
        different,
        ("--sandbox", "workspace-write", "--add-dir", str(setup.root)),
    )


def test_replaced_checkout_at_same_path_invalidates_the_saved_grant(setup):
    sid = opt_in(setup)
    setup.fake.rows[sid]["state"] = "archived"
    before = policy_path(setup).read_bytes()
    contents = snapshot(setup.source)
    setup.source.rename(setup.source.with_name("preserved original checkout"))
    setup.source.mkdir()
    for name, data in contents.items():
        (setup.source / name).write_bytes(data)
    # Explicitly updating the source mapping alone does not approve launch permissions.
    associate(setup.root, setup.source)
    result = run(setup, "--new-session")
    assert result.exit_code != 0, result.output
    assert "--codex-sandbox" in result.output
    assert len(setup.fake.launches) == 1 and policy_path(setup).read_bytes() == before


def test_copied_policy_does_not_grant_a_different_records_root(setup, tmp_path):
    sid = opt_in(setup)
    setup.fake.rows[sid]["state"] = "archived"
    original = policy_path(setup).read_bytes()
    other = tmp_path / "different records root"
    initialize_workspace(other, "Separate records")
    add_child(other, "demo")
    associate(other, setup.source)
    (other / "tools/native.local.toml").write_bytes(original)
    # The same source and project name do not authorize another records directory.
    setup.root = other
    result = run(setup)
    assert result.exit_code != 0, result.output
    assert "--codex-sandbox" in result.output
    assert len(setup.fake.launches) == 1
    assert policy_path(setup).read_bytes() == original


def test_symlinked_policy_file_cannot_write_outside_the_local_execution_store(setup, tmp_path):
    outside = tmp_path / "unrelated.toml"
    outside.write_text("# Do not overwrite\n")
    policy_path(setup).symlink_to(outside)
    result = run(setup, "--codex-sandbox", "workspace-write")
    assert result.exit_code != 0, result.output
    assert outside.read_text() == "# Do not overwrite\n"
    assert policy_path(setup).is_symlink() and not setup.fake.launches


def test_uncertain_creation_recovers_original_session_without_duplicate_or_lost_policy(setup):
    setup.fake.lose_add_response = True
    first = run(setup, "--codex-sandbox", "workspace-write")
    assert first.exit_code != 0 and len(setup.fake.launches) == 1
    expected = ("--sandbox", "workspace-write", "--add-dir", str(setup.root))
    assert setup.fake.launches[0][2] == expected
    assert policy_path(setup).exists()
    retry = run(setup)
    assert retry.exit_code == 0, retry.output
    assert len(setup.fake.launches) == 1
    assert json.loads(binding_path(setup).read_text())["session_id"] == setup.fake.launches[0][0]


@pytest.mark.parametrize("blocked", ["trust", "permissions", "dead-pane"])
def test_startup_blocker_remains_visible_without_context_send_or_automatic_bypass(setup, blocked):
    screens = {
        "trust": "Do you trust this folder?\n› 1. Yes\n  2. No\n" + "\n" * 40,
        "permissions": (
            "Error adding directories: Ignoring --add-dir because the effective permissions "
            "do not allow additional writable roots (managed policy).\n"
        ),
    }
    screens["dead-pane"] = screens["permissions"] + "\n" * 60 + "Pane is dead (status 1)\n"
    setup.fake.default_screen = screens[blocked]
    result = run(setup, "--codex-sandbox", "workspace-write", "--attach")
    # Present refusal even if attach itself exits successfully; attaching is not delivery.
    assert "CONTEXT NOT DELIVERED" in result.output
    assert not setup.fake.sends and len(setup.fake.launches) == 1
    saved = json.loads(binding_path(setup).read_text())
    assert saved["delivery"] == "prepared"
    assert not list((setup.root / "projects/demo/runs").rglob("receipt.json"))
    assert "refresh" in result.output
    if blocked != "trust":
        assert "--codex-sandbox" in result.output or "managed" in result.output.lower()
        assert "--new-session" in result.output
    else:
        assert "trust" in result.output.lower()
    assert all(
        call[0] in {"add", "list", "session", "attach-fixture-only"} for call in setup.fake.calls
    )


def test_policy_choice_is_not_accepted_on_workspace_scope(setup):
    result = run(setup, "--codex-sandbox", "workspace-write", project=None)
    assert result.exit_code != 0
    assert "project" in result.output.lower()
    assert not setup.fake.launches and not policy_path(setup).exists()


def test_both_entrypoints_explain_explicit_choice_in_help():
    for args in (["open", "--help"], ["aoe", "open", "--help"]):
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0, result.output
        assert "--codex-sandbox" in result.output
        assert "workspace-write" in result.output and "inherit" in result.output
