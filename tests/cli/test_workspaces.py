"""WX6: the known-workspace list, the ``toulmin open`` picker and ``--in``.

Temporary directories only. The list lives under the conftest-isolated XDG_STATE_HOME; AoE
is faked and never constructed for real.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from toulmin.cli import aoe, entry, registry, workspaces
from toulmin.cli.app import app
from toulmin.cli.initialize import initialize, initialize_workspace
from toulmin.protocols import workspace_change


@pytest.fixture(autouse=True)
def no_real_aoe(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("A real AoE adapter must not be constructed in CLI tests")

    monkeypatch.setattr(aoe, "AoEClient", refuse)
    monkeypatch.setattr(workspaces, "AoEClient", refuse)
    for name in ("TOULMIN_ACTOR", "AGENT_OF_EMPIRES_PROFILE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def opened(monkeypatch):
    calls = []

    def execute(root, project, profile, action, *, attach=False, **options):
        class Service:
            def open(self, agent=None, *, new_session=False, fallback_agent="codex"):
                calls.append({"root": root, "project": project})

        action(Service())

    monkeypatch.setattr(aoe, "_execute", execute)
    return calls


@pytest.fixture
def terminal(monkeypatch):
    monkeypatch.setattr(entry, "_interactive", lambda: True)


def run(*args, prompt=None):
    return CliRunner().invoke(app, [str(arg) for arg in args], input=prompt)


def at(hour):
    return datetime(2026, 11, 5, hour, 0, tzinfo=UTC)


@pytest.fixture
def two(tmp_path):
    """The trial situation: two folders named serving; v2 opened more recently."""
    first = tmp_path / "v1/serving"
    second = tmp_path / "v2/serving"
    initialize_workspace(first, "Serving Research")
    initialize_workspace(second, None)
    registry.remember(first, "Serving Research", now=at(1))
    registry.remember(second, "serving", now=at(2))
    return first, second


@pytest.fixture
def away(tmp_path, monkeypatch):
    """An unrelated, non-empty directory, like the home directory."""
    here = tmp_path / "home"
    here.mkdir()
    (here / "notes.txt").write_text("x\n")
    monkeypatch.chdir(here)
    return here


def stored():
    return json.loads(registry.registry_path().read_text())


# The list itself.


def test_location_follows_xdg_state_home_and_ignores_relative(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert registry.registry_path() == tmp_path / "state/toulmin/workspaces.json"
    monkeypatch.setenv("XDG_STATE_HOME", "relative")
    assert registry.registry_path() == Path.home() / ".local/state/toulmin/workspaces.json"


def test_remember_refreshes_one_entry_per_path(tmp_path):
    root = tmp_path / "serving"
    initialize_workspace(root, None)
    assert registry.remember(root / "." / "", "serving", now=at(1))
    assert not registry.remember(root, "serving", now=at(3))
    assert stored() == {
        "schema_version": 1,
        "workspaces": [
            {"path": str(root), "name": "serving", "last_opened": "2026-11-05T03:00:00Z"}
        ],
    }
    assert not registry.remember(root, "serving", opened=False)  # a scan keeps the time
    assert stored()["workspaces"][0]["last_opened"] == "2026-11-05T03:00:00Z"


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        '{"schema_version": 2, "workspaces": []}',
        '{"schema_version": 1, "workspaces": [{"path": "relative", "name": "x", '
        '"last_opened": null}]}',
        '{"schema_version": 1, "workspaces": [], "extra": 1}',
    ],
)
def test_an_unusable_list_is_reported_never_rewritten(tmp_path, text, opened, monkeypatch):
    path = registry.registry_path()
    path.parent.mkdir(parents=True)
    path.write_text(text)
    with pytest.raises(registry.RegistryError):
        registry.load()
    listed = run("workspaces")
    assert listed.exit_code == 1 and "Fix or delete the file" in listed.output
    root = tmp_path / "serving"
    initialize_workspace(root, None)
    monkeypatch.chdir(root)
    result = run("open")
    assert result.exit_code == 0, result.output
    assert opened == [{"root": root, "project": None}]  # open still works
    assert "workspace list not updated" in result.output
    assert path.read_text() == text


def test_init_open_and_adopt_register_and_read_only_commands_do_not(tmp_path, monkeypatch, opened):
    root = tmp_path / "serving"
    assert run("init", root).exit_code == 0
    assert [entry["path"] for entry in stored()["workspaces"]] == [str(root)]
    registry.registry_path().unlink()
    for args in (("status", "--root", root), ("decide", "--root", root), ("config", "show")):
        assert run(*args).exit_code == 0
    assert not registry.registry_path().exists()
    monkeypatch.chdir(root)
    assert run("open").exit_code == 0
    assert stored()["workspaces"][0]["name"] == "serving"
    legacy = tmp_path / "legacy"
    initialize(legacy, "demo")
    preview = run("workspace", "adopt", legacy)
    digest = preview.output.split("Plan digest: ", 1)[1].split()[0]
    adopted = run(
        "workspace", "adopt", legacy, "--plan-digest", digest, "--confirmed-by", "R", "--confirm"
    )
    assert adopted.exit_code == 0, adopted.output
    assert str(legacy) in [entry["path"] for entry in stored()["workspaces"]]


def test_workspaces_lists_live_state_and_forget_keeps_the_folder(two, tmp_path):
    first, second = two
    change = second / "runs/drafts/change.md"
    change.write_text(
        "---\nschema_version: 1\nkind: workspace-change-input\nscope: {kind: workspace}\n"
        "supersedes: null\nsources: []\npins: []\nchanges:\n  - target: charter\n"
        '    sections: {Focus: "FIFO first."}\n---\n## Question\nFocus?\n\n'
        "## Unresolved assumptions\nNone.\n"
    )
    workspace_change.propose(second, "runs/drafts/change.md")
    gone = tmp_path / "gone"
    initialize_workspace(gone, "caching")
    registry.remember(gone, "caching", now=at(0))
    for path in sorted(gone.rglob("*"), reverse=True):
        path.rmdir() if path.is_dir() else path.unlink()
    gone.rmdir()
    result = run("workspaces")
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == f"  1  serving  {second}  2026-11-05 02:00 UTC  [1 item(s) await decision]"
    assert lines[1] == f"  2  Serving Research  {first}  2026-11-05 01:00 UTC"
    assert lines[2] == f"  3  caching  {gone}  2026-11-05 00:00 UTC  [missing]"
    forgotten = run("workspaces", "forget", gone)
    assert forgotten.exit_code == 0 and "the folder was not touched" in forgotten.output
    assert run("workspaces", "forget", gone).exit_code == 1
    assert first.is_dir() and len(stored()["workspaces"]) == 2


# toulmin open with no workbench here.


def test_without_known_workspaces_open_keeps_the_old_behaviour(away, opened):
    result = run("open")
    assert result.exit_code == 1 and "is not a Toulmin workbench" in result.output
    assert opened == []


def test_picker_opens_the_chosen_workspace(two, away, opened, terminal):
    first, second = two
    result = run("open", prompt="2\n")
    assert result.exit_code == 0, result.output
    assert f"  1  serving  {second}" in result.output
    assert f"  2  Serving Research  {first}" in result.output
    assert "[number / q = quit]" in result.output  # not empty here: no init offer
    assert opened == [{"root": first, "project": None}]
    assert stored()["workspaces"][0]["last_opened"] > "2026-11-05T02:00:00Z"


def test_picker_quit_invalid_and_missing_choices(two, away, opened, terminal, tmp_path):
    first, _ = two
    gone = tmp_path / "gone"
    registry.remember(gone, "gone", now=at(0))  # never existed: listed as missing
    result = run("open", prompt="7\n3\nq\n")
    assert result.exit_code == 1
    assert "Choose one of: number / q = quit" in result.output
    assert f"{gone} cannot be opened now (missing)" in result.output
    assert "Nothing opened." in result.output and opened == []


def test_picker_in_an_empty_directory_can_initialize_here(two, tmp_path, monkeypatch, opened):
    monkeypatch.setattr(entry, "_interactive", lambda: True)
    here = tmp_path / "fresh"
    here.mkdir()
    monkeypatch.chdir(here)
    result = run("open", prompt="i\n")
    assert result.exit_code == 0, result.output
    assert "[number / i = initialize here / q = quit]" in result.output
    assert (here / "WORKSPACE.md").is_file()
    assert opened == [{"root": here, "project": None}]


def test_picker_without_a_terminal_lists_and_changes_nothing(two, tmp_path, monkeypatch, opened):
    here = tmp_path / "fresh"
    here.mkdir()
    monkeypatch.chdir(here)
    before = registry.registry_path().read_bytes()
    result = run("open")
    assert result.exit_code == 1
    assert "Open one with: toulmin open --in NAME_OR_PATH" in result.output
    assert f"Or create one here with: toulmin init {here}" in result.output
    assert not (here / "WORKSPACE.md").exists() and opened == []
    assert registry.registry_path().read_bytes() == before


def test_inside_a_workbench_the_picker_is_not_shown(two, monkeypatch, opened, terminal):
    _, second = two
    monkeypatch.chdir(second)
    result = run("open")
    assert result.exit_code == 0 and "Known workspaces" not in result.output
    assert opened == [{"root": second, "project": None}]


# toulmin open --in.


def test_in_opens_by_name_case_insensitively_or_by_path(two, away, opened, monkeypatch):
    first, second = two
    (second / "projects/scheduling").mkdir()
    assert run("open", "--in", "serving research").exit_code == 0
    assert run("open", "--in", str(second), "scheduling").exit_code == 0
    assert opened == [
        {"root": first, "project": None},
        {"root": second, "project": "scheduling"},
    ]


def test_in_reports_ambiguous_unknown_and_conflicting_choices(two, away, opened, tmp_path):
    first, second = two
    third = tmp_path / "v3/serving"
    initialize_workspace(third, None)
    registry.remember(third, "serving", now=at(3))
    ambiguous = run("open", "--in", "serving")
    assert ambiguous.exit_code == 2
    assert "several known workspaces are named 'serving'" in ambiguous.output
    assert str(second) in ambiguous.output and str(third) in ambiguous.output
    unknown = run("open", "--in", "caching")
    assert unknown.exit_code == 2 and "no known workspace is named 'caching'" in unknown.output
    both = run("open", "--in", "serving", "--root", first)
    assert both.exit_code == 2 and "either --in or --root" in both.output
    assert opened == []


# toulmin workspaces scan.


def test_scan_registers_workspace_roots_and_children_from_aoe_sessions(two, tmp_path, monkeypatch):
    first, second = two
    registry.registry_path().unlink()
    (second / "projects/scheduling").mkdir()
    elsewhere = tmp_path / "unrelated"
    elsewhere.mkdir()
    profiles = []

    class Client:
        def __init__(self, profile):
            profiles.append(profile)

        def list_sessions(self):
            paths = (first, second / "projects/scheduling", elsewhere, tmp_path / "nowhere")
            return tuple(SimpleNamespace(path=path) for path in paths)

    monkeypatch.setattr(workspaces, "AoEClient", Client)
    monkeypatch.setenv("AGENT_OF_EMPIRES_PROFILE", "toulmin-trial-wi8")
    result = run("workspaces", "scan")
    assert result.exit_code == 0, result.output
    assert profiles == ["toulmin-trial-wi8"]
    assert "4 session(s), 2 workspace(s) with a WORKSPACE.md, 2 added." in result.output
    entries = {entry["path"]: entry for entry in stored()["workspaces"]}
    assert set(entries) == {str(first), str(second)}
    assert all(entry["last_opened"] is None for entry in entries.values())
    again = run("workspaces", "scan", "--profile", "other")
    assert "0 added" in again.output and profiles[-1] == "other"
    assert "found by scan" in run("workspaces").output
