import re
import tempfile
from pathlib import Path

import pytest

from toulmin.cli.initialize import initialize
from toulmin.core.codec import decode, encode
from toulmin.core.documents import DIRECTORIES


@pytest.fixture(autouse=True)
def isolated_user_config(tmp_path_factory):
    """Never read the researcher's real ~/.config/toulmin/config.toml in tests.

    A private MonkeyPatch, not the shared fixture: tests that call ``monkeypatch.undo()``
    to end a simulated crash must not undo this isolation as well (found with W9).
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("xdg-config")))
        # The known-workspace list (WX6) too: tests never read or write the real one.
        patch.setenv("XDG_STATE_HOME", str(tmp_path_factory.mktemp("xdg-state")))
        # Handoff lock files live in the temporary directory and are never removed (flock
        # files cannot be unlinked safely); per-test roots would pile them up in /tmp (W9).
        scratch = str(tmp_path_factory.mktemp("tmpdir"))
        patch.setattr(tempfile, "tempdir", scratch)
        patch.setenv("TMPDIR", scratch)
        # Native CLI homes too: model reports must never read real session logs (WX3).
        patch.setenv("CODEX_HOME", str(tmp_path_factory.mktemp("codex-home")))
        patch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path_factory.mktemp("claude-home")))
        yield


@pytest.fixture
def example_docs():
    path = Path(__file__).resolve().parents[1] / "docs/format-examples.md"
    return {
        document.object_id.kind: document
        for sample in re.findall(r"````markdown\n(.*?)\n````", path.read_text(), re.S)
        for document in [decode(sample.encode(), str(path))]
    }


@pytest.fixture
def workbench(tmp_path):
    root = tmp_path / "research"
    initialize(root, "demo")
    archive = root / "projects/demo/runs/20261031T100000Z-review"
    archive.mkdir()
    (archive / "output.md").write_text("Test fixture: archived model output.\n")
    return root


@pytest.fixture
def populated(workbench, example_docs):
    for kind, document in example_docs.items():
        path = workbench / "projects/demo" / DIRECTORIES[kind] / f"{document.object_id}.md"
        path.write_bytes(encode(document))
    return workbench
