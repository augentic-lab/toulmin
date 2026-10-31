import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from toulmin.cli.app import app


def test_help_and_version():
    runner = CliRunner()
    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    assert "Toulmin" in help_result.output
    assert "init" in help_result.output
    assert runner.invoke(app, ["--version"]).output.strip() == "0.1.0"


def test_installed_console_script_outside_repository(tmp_path):
    executable = Path(sys.executable).with_name("toulmin")
    result = subprocess.run(
        [str(executable), "--help"], cwd=tmp_path, capture_output=True, text=True, check=True
    )
    assert "Toulmin" in result.stdout


def test_unimplemented_command_does_not_report_success():
    result = CliRunner().invoke(app, ["new"])
    assert result.exit_code != 0
