"""PE1: file-only project lists and explicit interactive scope selection."""

import pytest
from typer.testing import CliRunner

from toulmin.cli import aoe, entry, projects, registry
from toulmin.cli.app import app
from toulmin.cli.initialize import _templates, initialize_workspace
from toulmin.core.atomic import digest
from toulmin.core.codec import encode
from toulmin.core.documents import replace_section
from toulmin.core.project_proposals import Outcome, render_outcome
from toulmin.core.repository import Repository
from toulmin.protocols import project_proposals


@pytest.fixture(autouse=True)
def no_native_clients(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("Project discovery must not construct native or Chief clients")

    monkeypatch.setattr(aoe, "AoEClient", refuse)
    monkeypatch.setattr("toulmin.application.build.ChiefClient", refuse)


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "research"
    initialize_workspace(root, "Research")
    for name in ("zeta", "alpha"):
        add_child(root, name)
        relative = f"projects/{name}/PROJECT.md"
        charter = Repository(root).read(relative)
        charter.body = replace_section(charter.body, "Goal", f"Understand the {name} question.")
        (root / relative).write_bytes(encode(charter))
    return root


def add_child(root, name):
    """Install a fixture child without going through native sessions or approval dialogs."""
    for relative, content in _templates(name).items():
        if relative.parts[:2] == ("projects", name):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


@pytest.fixture
def opened(monkeypatch):
    calls = []
    monkeypatch.setattr(entry, "open_scope", lambda *args, **kwargs: calls.append((args, kwargs)))
    return calls


def run(*args, answers=None):
    return CliRunner().invoke(app, [str(arg) for arg in args], input=answers)


def snapshot(root):
    return {
        path.relative_to(root): (
            path.lstat().st_mtime_ns,
            path.read_bytes() if path.is_file() and not path.is_symlink() else None,
        )
        for path in [root, *root.rglob("*")]
    }


def test_list_is_sorted_complete_and_read_only(workspace):
    before = snapshot(workspace)
    registry_before = (
        registry.registry_path().read_bytes() if registry.registry_path().exists() else None
    )
    result = run("projects", "--root", workspace)
    assert result.exit_code == 0, result.output
    assert result.output.index("alpha | stage: explore") < result.output.index(
        "zeta | stage: explore"
    )
    assert "Goal: Understand the alpha question." in result.output
    assert "pending proposals: 0" in result.output
    assert snapshot(workspace) == before
    registry_after = (
        registry.registry_path().read_bytes() if registry.registry_path().exists() else None
    )
    assert registry_after == registry_before


def test_discover_from_child_or_select_known_workspace(workspace, monkeypatch, tmp_path):
    monkeypatch.chdir(workspace / "projects/alpha/runs")
    assert run("projects").exit_code == 0
    registry.remember(workspace, "Research")
    monkeypatch.chdir(tmp_path)
    listed = run("projects", "--in", "Research")
    assert listed.exit_code == 0 and f"Workspace: {workspace}" in listed.output
    assert run("projects", "--in", workspace).exit_code == 0
    assert run("projects", "--in", "Research", "--root", workspace).exit_code == 2


@pytest.mark.parametrize("selection", ["missing-name", "Research"])
def test_in_errors_remain_file_only(workspace, tmp_path, monkeypatch, selection):
    other = tmp_path / "other"
    initialize_workspace(other, "Research")
    registry.remember(workspace, "Research")
    registry.remember(other, "Research")

    def refuse(*args, **kwargs):
        raise AssertionError("Error suggestions must not query external pending decisions")

    monkeypatch.setattr(entry, "describe", refuse)
    listed = run("projects", "--in", selection)
    assert listed.exit_code == 2, listed.output
    assert str(workspace) in listed.output and str(other) in listed.output


@pytest.mark.parametrize("kind", ["missing", "empty", "unrelated"])
def test_list_never_initializes_or_prompts(tmp_path, monkeypatch, kind):
    root = tmp_path / kind
    if kind != "missing":
        root.mkdir()
        if kind == "unrelated":
            (root / "notes.md").write_text("Keep this file.\n")
    monkeypatch.setattr(entry, "_interactive", lambda: True)
    before = snapshot(root) if root.exists() else None
    result = run("projects", "--root", root)
    assert result.exit_code == 1 and "nothing was initialized" in result.output
    assert (snapshot(root) if root.exists() else None) == before


def test_project_free_workspace_needs_no_project_menu(tmp_path, monkeypatch, opened):
    root = tmp_path / "empty-workspace"
    initialize_workspace(root, None)
    listed = run("projects", "--root", root)
    assert listed.exit_code == 0 and "No projects yet" in listed.output
    monkeypatch.setattr(entry, "_interactive", lambda: True)
    result = run("open", "--root", root)
    assert result.exit_code == 0 and "Open which conversation?" not in result.output
    assert opened[0][0][:2] == (root, None)


def test_pending_counts_respect_outcomes_and_explain_local_scope(workspace):
    folder = workspace / "projects/alpha/runs/proposals"
    folder.mkdir()
    names = [f"claim-20261119T10000{i}Z.md" for i in range(3)]
    for name in names:
        (folder / name).write_text("An unconfirmed proposal.\n")
    relative = f"projects/alpha/runs/proposals/{names[1]}"
    rejected = Outcome(
        relative, digest((workspace / relative).read_bytes()), "rejected", "Researcher",
        "2026-11-19T10:00:00Z", None, "Superseded idea.", None,
    )  # fmt: skip
    (workspace / project_proposals.outcome_path(relative)).write_bytes(render_outcome(rejected))
    # A draft or live task status is not an undecided proposal.
    drafts = workspace / "projects/alpha/runs/drafts"
    drafts.mkdir()
    (drafts / "notes.md").write_text("Exploration only.\n")
    task = folder / "task-20261119T100003Z.md"
    task.write_text("A pending engineering request.\n")
    listed = run("projects", "--root", workspace)
    assert listed.exit_code == 0, listed.output
    assert "alpha | stage: explore | pending proposals: 3" in listed.output
    assert "excludes handoffs and live Chief results" in listed.output


def test_invalid_pending_outcomes_are_unknown_not_zero(workspace):
    folder = workspace / "projects/alpha/runs/proposals"
    folder.mkdir()
    (folder / "claim-20261119T100000Z.md").write_text("Pending.\n")
    (folder / "claim-20261119T100000Z.outcome.md").write_text("Broken outcome.\n")
    listed = run("projects", "--root", workspace)
    assert listed.exit_code == 1
    assert "alpha | stage: explore | pending proposals: unknown" in listed.output
    assert "Diagnostic:" in listed.output


def test_unrecognized_proposals_are_reported(workspace):
    folder = workspace / "projects/alpha/runs/proposals"
    folder.mkdir()
    (folder / "unknown.md").write_text("Unrecognized.\n")
    listed = run("projects", "--root", workspace)
    assert listed.exit_code == 1 and "unrecognized proposal filename" in listed.output


def test_damaged_and_symlink_children_are_reported_without_following(workspace, tmp_path):
    (workspace / "projects/alpha/PROJECT.md").write_text("Broken charter.\n")
    (workspace / "projects/escape").symlink_to(tmp_path, target_is_directory=True)
    before = snapshot(workspace)
    listed = run("projects", "--root", workspace)
    assert listed.exit_code == 1
    assert "alpha | unavailable:" in listed.output and "projects/escape" in listed.output
    assert "zeta | stage: explore" in listed.output
    assert snapshot(workspace) == before


@pytest.mark.parametrize(("answer", "project"), [("0\n", None), ("1\n", "alpha"), ("2\n", "zeta")])
def test_interactive_open_offers_explicit_workspace_and_project(
    workspace, monkeypatch, opened, answer, project
):
    monkeypatch.setattr(entry, "_interactive", lambda: True)
    monkeypatch.chdir(workspace)
    result = run("open", answers=answer)
    assert result.exit_code == 0, result.output
    assert "0  Workspace conversation" in result.output
    assert "Goal: Understand the alpha question." in result.output
    assert opened[0][0][:2] == (workspace, project)


def test_single_project_still_requires_explicit_scope(tmp_path, monkeypatch, opened):
    root = tmp_path / "single"
    initialize_workspace(root, None)
    add_child(root, "only")
    monkeypatch.setattr(entry, "_interactive", lambda: True)
    result = run("open", "--root", root, answers="0\n")
    assert result.exit_code == 0 and "only | stage: explore" in result.output
    assert opened[0][0][:2] == (root, None)


@pytest.mark.parametrize("mode", ["project", "workspace", "inferred", "noninteractive"])
def test_explicit_inferred_and_noninteractive_scopes_skip_menu(
    workspace, monkeypatch, opened, mode
):
    monkeypatch.setattr(entry, "_interactive", lambda: mode != "noninteractive")
    args = ["open"]
    expected = None
    if mode == "project":
        args += ["alpha", "--root", workspace]
        expected = "alpha"
    elif mode == "workspace":
        args += ["--workspace", "--root", workspace]
    elif mode == "inferred":
        monkeypatch.chdir(workspace / "projects/zeta/runs")
        expected = "zeta"
    else:
        args += ["--root", workspace]
    result = run(*args)
    assert result.exit_code == 0 and "Open which conversation?" not in result.output
    assert opened[0][0][:2] == (workspace, expected)


def test_known_workspace_then_project_is_a_two_step_choice(
    workspace, monkeypatch, opened, tmp_path
):
    registry.remember(workspace, "Research")
    away = tmp_path / "away"
    away.mkdir()
    (away / "notes").write_text("Unrelated.\n")
    monkeypatch.chdir(away)
    monkeypatch.setattr(entry, "_interactive", lambda: True)
    result = run("open", answers="1\n2\n")
    assert result.exit_code == 0, result.output
    assert "Known workspaces" in result.output and "Open which conversation?" in result.output
    assert opened[0][0][:2] == (workspace, "zeta")


def test_in_option_keeps_scope_picker_and_forwards_native_options(workspace, monkeypatch, opened):
    monkeypatch.setattr(entry, "_interactive", lambda: True)
    result = run(
        "open", "--in", workspace, "--agent", "claude", "--profile", "trial", "--new-session",
        "--no-attach", answers="1\n",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert opened == [
        ((workspace, "alpha", "trial", "claude"), {"new_session": True, "attach": False})
    ]


def test_invalid_choice_and_quit_do_not_open_or_update_registry(workspace, monkeypatch, opened):
    monkeypatch.setattr(entry, "_interactive", lambda: True)
    before = snapshot(workspace)
    registry_before = (
        registry.registry_path().read_bytes() if registry.registry_path().exists() else None
    )
    result = run("open", "--root", workspace, answers="99\nunknown\nq\n")
    assert result.exit_code == 1 and "Nothing opened." in result.output
    assert result.output.count("Choose one of:") == 2
    assert opened == [] and snapshot(workspace) == before
    registry_after = (
        registry.registry_path().read_bytes() if registry.registry_path().exists() else None
    )
    assert registry_after == registry_before


def test_project_changed_while_picker_waits_is_not_opened(workspace, monkeypatch, opened):
    monkeypatch.setattr(entry, "_interactive", lambda: True)
    answers = iter(["1", "q"])

    def prompt(*args, **kwargs):
        answer = next(answers)
        if answer == "1":
            (workspace / "projects/alpha/PROJECT.md").unlink()
        return answer

    monkeypatch.setattr(projects.typer, "prompt", prompt)
    result = run("open", "--root", workspace)
    assert result.exit_code == 1 and "alpha is unavailable" in result.output
    assert opened == []


def test_legacy_list_and_interactive_selection_do_not_adopt(workbench, monkeypatch, opened):
    before = snapshot(workbench)
    listed = run("projects", "--root", workbench)
    assert listed.exit_code == 0 and "Legacy workbench" in listed.output
    monkeypatch.setattr(entry, "_interactive", lambda: True)
    selected = run("open", "--root", workbench, answers="0\n1\n")
    assert selected.exit_code == 0, selected.output
    assert "0  Workspace conversation" not in selected.output
    assert opened[0][0][:2] == (workbench, "demo")
    assert snapshot(workbench) == before and not (workbench / "WORKSPACE.md").exists()


def test_sandbox_scope_validation_occurs_after_project_choice(workspace, monkeypatch, opened):
    monkeypatch.setattr(entry, "_interactive", lambda: True)
    selected = run("open", "--root", workspace, "--codex-sandbox", "workspace-write", answers="1\n")
    assert selected.exit_code == 0, selected.output
    assert opened[0][0][:2] == (workspace, "alpha")
    assert opened[0][1]["codex_sandbox"] == "workspace-write"
    refused = run("open", "--root", workspace, "--codex-sandbox", "workspace-write", answers="0\n")
    assert refused.exit_code == 2 and "source-backed workspace" in refused.output
    assert len(opened) == 1
