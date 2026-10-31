import re
from pathlib import Path

import pytest

from toulmin.cli.initialize import initialize
from toulmin.core.codec import decode, encode
from toulmin.core.documents import DIRECTORIES


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
