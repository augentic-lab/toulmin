"""``toulmin workspaces remove``: preview, blockers and confirmed removal.

Temporary directories only; AoE is a fake and the Chief home is a temporary folder.
"""

import json
import tarfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toulmin.adapters.aoe import AoEError, AoESession
from toulmin.cli import registry, workspaces
from toulmin.cli.app import app
from toulmin.cli.initialize import _templates, initialize_workspace

WS = "0011d3d1ca7d4d08"
PROJECT = "8d0e46a5f5514886"
OTHER = "1111111111111111"


class FakeAoE:
    """Sessions per profile; ``removed`` records `aoe remove` calls."""

    sessions: dict[str, list[AoESession]] = {}
    removed: list[tuple[str, str]] = []
    fail_on: str | None = None

    def __init__(self, profile: str) -> None:
        self.profile = profile

    def list_sessions(self) -> tuple[AoESession, ...]:
        return tuple(self.sessions.get(self.profile, ()))

    def show(self, session_id: str) -> AoESession:
        return next(item for item in self.sessions[self.profile] if item.id == session_id)

    def remove(self, session_id: str) -> None:
        if session_id == self.fail_on:
            raise AoEError("AoE remove failed (1): boom")
        self.removed.append((self.profile, session_id))


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "research/test-rdma"
    initialize_workspace(root, "Test RDMA")
    for relative, data in _templates("rdma-vs-tcp").items():  # the template child project
        if relative.parts[0] == "projects":
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            (root / relative).write_bytes(data)
    (root / ".aoe").mkdir(exist_ok=True)
    (root / ".aoe/binding.json").write_text(
        json.dumps({"schema_version": 2, "profile": "main", "session_id": WS})
    )
    registry.remember(root, "Test RDMA")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("AOE_CHIEF_HOME", str(tmp_path / "chief-home"))
    monkeypatch.delenv("AGENT_OF_EMPIRES_PROFILE", raising=False)
    FakeAoE.sessions = {
        "main": [
            AoESession(WS, root, "codex", "live", "idle", None, "Workspace: test-rdma"),
            AoESession(PROJECT, root, "codex", "archived", None, None, "Project: rdma-vs-tcp"),
            AoESession(OTHER, tmp_path / "unrelated", "codex", "live", "running", None, "x"),
            AoESession("2222222222222222", root, "codex", "trashed", None, None, "old"),
        ]
    }
    FakeAoE.removed = []
    FakeAoE.fail_on = None
    monkeypatch.setattr(workspaces, "AoEClient", FakeAoE)
    return root


def run(*args, prompt=None):
    return CliRunner().invoke(app, ["workspaces", "remove", *map(str, args)], input=prompt)


def chief_task(home: Path, task_id: str, **fields):
    folder = home / "tasks" / task_id
    folder.mkdir(parents=True)
    (folder / "task.json").write_text(json.dumps({"id": task_id, **fields}))


def test_preview_lists_sessions_and_losses_and_changes_nothing(workspace):
    result = run("Test RDMA")
    assert result.exit_code == 0, result.output
    assert f"{WS}  [main] Workspace: test-rdma (live, idle)" in result.output
    assert f"{PROJECT}  [main] Project: rdma-vs-tcp (archived)" in result.output
    assert OTHER not in result.output and "2222222222222222" not in result.output
    assert "projects: rdma-vs-tcp" in result.output
    assert "LOST: no commits: no copy of these files exists elsewhere" in result.output
    assert "Preview only. Remove with --confirm" in result.output
    assert workspace.is_dir() and FakeAoE.removed == []


def test_confirm_archives_trashes_sessions_deletes_and_forgets(workspace, tmp_path):
    target = tmp_path / "keep.tar.gz"
    result = run(workspace, "--archive", target, "--confirm", prompt="test-rdma\n")
    assert result.exit_code == 0, result.output
    assert FakeAoE.removed == [("main", WS), ("main", PROJECT)]
    assert not workspace.exists()
    assert "Removed from the workspace list." in result.output
    assert all(entry.path != workspace for entry in registry.load())
    with tarfile.open(target) as archive:
        names = archive.getnames()
    assert (
        "test-rdma/WORKSPACE.md" in names and "test-rdma/projects/rdma-vs-tcp/PROJECT.md" in names
    )


def test_wrong_name_removes_nothing(workspace):
    result = run("Test RDMA", "--confirm", prompt="rdma\n")
    assert result.exit_code == 1
    assert "name did not match; nothing removed" in result.output
    assert workspace.is_dir() and FakeAoE.removed == []


def test_running_session_active_chief_task_and_shell_inside_block(workspace, tmp_path, monkeypatch):
    FakeAoE.sessions["main"][0] = AoESession(WS, workspace, "codex", "live", "running", None, "W")
    chief_task(
        tmp_path / "chief-home", "inside-task", state="needs-you", worktree=str(workspace / "w")
    )
    chief_task(
        tmp_path / "chief-home", "outside-task", state="running", repo=str(tmp_path / "code")
    )
    chief_task(tmp_path / "chief-home", "closed-task", state="done", repo=str(workspace))
    monkeypatch.chdir(workspace / "projects")
    result = run(workspace, "--confirm", prompt="test-rdma\n")
    assert result.exit_code == 1
    assert f"BLOCKED: session {WS} (W) is running" in result.output
    assert "BLOCKED: Chief task inside-task is needs-you" in result.output
    assert "BLOCKED: your shell is inside this workspace" in result.output
    assert "outside-task" not in result.output
    assert "Chief task closed-task (found by its paths): done" in result.output
    assert "closed-task is" not in result.output
    assert workspace.is_dir() and FakeAoE.removed == []


def test_session_failure_keeps_the_folder_and_names_trashed_sessions(workspace):
    FakeAoE.fail_on = PROJECT
    result = run(workspace, "--confirm", prompt="test-rdma\n")
    assert result.exit_code == 1
    assert f"sessions already in AoE's trash: {WS}; folder kept" in result.output
    assert workspace.is_dir()
    assert any(entry.path == workspace for entry in registry.load())


def test_archive_must_be_new_and_outside(workspace, tmp_path):
    (tmp_path / "taken.tar.gz").write_text("x")
    result = run(
        workspace, "--archive", tmp_path / "taken.tar.gz", "--confirm", prompt="test-rdma\n"
    )
    assert result.exit_code == 1 and "already exists" in result.output
    inside = run(workspace, "--archive", workspace / "a.tar.gz", "--confirm", prompt="test-rdma\n")
    assert inside.exit_code == 1 and "inside the workspace" in inside.output
    assert workspace.is_dir() and FakeAoE.removed == []


def test_refuses_folders_that_are_not_workspaces(workspace, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "notes.txt").write_text("x\n")
    result = run(plain, "--confirm", prompt="plain\n")
    assert result.exit_code == 1 and "not a Toulmin workspace" in result.output
    assert (plain / "notes.txt").exists()
    home = run(Path.home(), "--confirm", prompt="x\n")
    assert home.exit_code == 1 and "home or system directory" in home.output
    link = tmp_path / "link"
    link.symlink_to(workspace)
    linked = run(link, "--confirm", prompt="link\n")
    assert linked.exit_code == 1 and "symbolic link" in linked.output
    assert workspace.is_dir()


def test_committed_without_upstream_is_reported_as_local_only(workspace):
    import subprocess

    def git(*args):
        subprocess.run(["git", "-C", str(workspace), *args], check=True, capture_output=True)

    git("config", "user.email", "fixture@example.invalid")
    git("config", "user.name", "Fixture")
    git("add", "-A")
    git("commit", "-m", "fixture")
    result = run(workspace)
    assert "LOST: branch main has no upstream: its commits exist only here" in result.output
    assert "uncommitted" not in result.output.split("LOST", 1)[1]
