"""The optional interface must not become a core CLI dependency."""

import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toulmin.cli.app import app


@pytest.mark.parametrize("arguments", [["--project", "demo"], ["--project", "../bad"]])
def test_tui_validates_arguments_before_launch(arguments):
    result = CliRunner().invoke(app, ["tui", *arguments])
    assert result.exit_code == 2


def test_cli_without_textual_has_help_and_actionable_tui_error(tmp_path):
    script = """
import sys
class NoTextual:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "textual" or fullname.startswith("textual."):
            raise ModuleNotFoundError("Textual is not installed", name="textual")
sys.meta_path.insert(0, NoTextual())
from typer.testing import CliRunner
from toulmin.cli.app import app
runner = CliRunner()
assert runner.invoke(app, ["--help"]).exit_code == 0
assert runner.invoke(app, ["tui", "--help"]).exit_code == 0
result = runner.invoke(app, ["tui"])
assert result.exit_code == 1, result.output
assert "uv sync --locked --extra tui" in result.output
assert not any(name.startswith("textual") for name in sys.modules)
"""
    subprocess.run([sys.executable, "-I", "-c", script], cwd=tmp_path, check=True)


def test_tui_launch_passes_explicit_project(monkeypatch, tmp_path):
    pytest.importorskip("textual")
    from toulmin.tui import app as tui

    calls = []
    monkeypatch.setattr(tui, "launch", lambda **kwargs: calls.append(kwargs))
    result = CliRunner().invoke(app, ["tui", "--root", str(tmp_path), "--project", "demo"])
    assert result.exit_code == 0, result.output
    assert calls == [{"root": Path(tmp_path), "project": "demo"}]
