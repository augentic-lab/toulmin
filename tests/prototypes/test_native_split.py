"""Exercise actual tmux panes using only the built-in simulated agent."""

import json
import runpy
import shutil
import tempfile
import time
from pathlib import Path

import pytest

MODULE = runpy.run_path(str(Path(__file__).parents[2] / "prototypes/native_split.py"))
initialize = MODULE["initialize"]
tmux = MODULE["tmux"]
start = MODULE["start"]


def until(predicate: object) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("timed out waiting for prototype")


def test_trial_refuses_existing_project(tmp_path: Path) -> None:
    workspace = tmp_path / "existing"
    workspace.mkdir()
    (workspace / "context.md").write_text("original")
    with pytest.raises(FileExistsError):
        initialize(workspace, "new question")
    assert (workspace / "context.md").read_text() == "original"


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux not installed")
@pytest.mark.parametrize("columns", [100, 140])
def test_actual_split_draft_focus_zoom_and_shutdown(tmp_path: Path, columns: int) -> None:
    workspace = tmp_path / "trial with spaces"
    initialize(workspace, "Which observations distinguish two explanations?")
    with tempfile.TemporaryDirectory(prefix="toulmin-test-") as server:
        socket = Path(server) / "socket"
        try:
            start(workspace, socket, "demo", columns, 30)

            def capture(pane: int) -> str:
                return tmux(socket, "capture-pane", "-p", "-t", f"trial:0.{pane}").stdout

            until(lambda: "demo>" in capture(1))
            tmux(socket, "send-keys", "-t", "trial:0.1", "/draft", "Enter")
            until(lambda: (workspace / "draft.md").exists())
            assert not (workspace / "accepted-brief.md").exists()
            assert "simulated" in (workspace / "draft.md").read_text()
            # Real tmux focus and zoom commands, not mocked terminal output.
            tmux(socket, "select-pane", "-t", "trial:0.0")
            assert tmux(socket, "display-message", "-p", "#{pane_index}").stdout.strip() == "0"
            tmux(socket, "resize-pane", "-Z", "-t", "trial:0.0")
            assert (
                tmux(socket, "display-message", "-p", "#{window_zoomed_flag}").stdout.strip() == "1"
            )
            tmux(socket, "resize-pane", "-Z", "-t", "trial:0.0")
            tmux(socket, "send-keys", "-t", "trial:0.1", "/exit", "Enter")
            until(lambda: (workspace / "native-exit.json").exists())
            assert json.loads((workspace / "native-exit.json").read_text())["exit_code"] == 0
            until(lambda: "Explore" in capture(0))
            tmux(socket, "send-keys", "-t", "trial:0.0", "q")
            until(lambda: tmux(socket, "list-sessions", check=False).returncode != 0)
        finally:
            tmux(socket, "kill-server", check=False)
