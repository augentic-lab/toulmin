"""W9: test isolation survives ``monkeypatch.undo()`` and keeps lock files out of /tmp."""

import os
import tempfile
from pathlib import Path

from toulmin.cli.registry import registry_path
from toulmin.cli.settings import config_path
from toulmin.core.atomic import handoff_mutex


def test_isolation_survives_undo_and_locks_stay_in_the_test_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", "/elsewhere")
    monkeypatch.undo()  # as the crash-recovery tests do
    home = Path.home()
    assert not config_path().is_relative_to(home / ".config")
    assert not registry_path().is_relative_to(home / ".local/state")
    for variable in ("CODEX_HOME", "CLAUDE_CONFIG_DIR", "TMPDIR"):
        assert os.environ[variable].startswith(str(tmp_path.parents[1])), variable
    scratch = Path(tempfile.gettempdir())
    assert scratch != Path("/tmp") and scratch.is_relative_to(tmp_path.parents[1])
    with handoff_mutex(tmp_path):
        assert [path.parent for path in scratch.glob("toulmin-handoff-*.lock")] == [scratch]
