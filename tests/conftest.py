import re
from pathlib import Path

import pytest

from toulmin.cli.initialize import initialize
from toulmin.core.codec import decode, encode
from toulmin.core.documents import DIRECTORIES


@pytest.fixture(autouse=True)
def isolated_user_config(tmp_path_factory, monkeypatch):
    """Never read the researcher's real ~/.config/toulmin/config.toml in tests."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("xdg-config")))
    # Native CLI homes too: model reports must never read real session logs (WX3).
    monkeypatch.setenv("CODEX_HOME", str(tmp_path_factory.mktemp("codex-home")))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path_factory.mktemp("claude-home")))


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
