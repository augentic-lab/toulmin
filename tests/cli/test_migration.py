from pathlib import Path

import pytest
from typer.testing import CliRunner

from toulmin.cli.app import app
from toulmin.cli.initialize import initialize
from toulmin.core.codec import decode, encode
from toulmin.core.sources import Source, render_catalog
from toulmin.protocols import migration


def ready(root: Path) -> str:
    initialize(root, "existing")
    (root / "sources.toml").write_bytes(
        render_catalog(
            (
                Source("legacy", "existing", "directory", "reference", "directory:old"),
                Source("rebuilt", "existing", "directory", "working", "directory:new"),
            )
        )
    )
    path = migration.draft(root, "existing")
    doc = decode(path.read_bytes())
    doc.header.update(
        source="legacy",
        target="rebuilt",
        source_version="abc123",
        target_version="def456",
        items=["parser.py"],
        checks=["pytest: exit 0; runs/check/output.txt"],
        outcome="partial",
    )
    doc.body = "## Rationale\nReuse the parser.\n\n## Differences\nNew public interface.\n"
    path.write_bytes(encode(doc))
    return path.relative_to(root).as_posix()


def test_preview_and_idempotent_record(tmp_path: Path) -> None:
    root = tmp_path / "records"
    relative = ready(root)
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    raw, sha = migration.preview(root, "existing", relative)
    assert before == {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    receipt = migration.record(root, "existing", relative, "researcher", sha)
    assert migration.record(root, "existing", relative, "researcher", sha) == receipt
    assert decode(receipt.read_bytes()).header["outcome"] == "partial"
    assert (root / relative).read_bytes() == raw
    assert not list((root / "projects/existing/evidence").glob("E-*.md"))


def test_stale_and_incomplete_refused(tmp_path: Path) -> None:
    relative = ready(tmp_path / "records")
    root = tmp_path / "records"
    with pytest.raises(ValueError, match="changed"):
        migration.record(root, "existing", relative, "researcher", "wrong")
    path = migration.draft(root, "existing")
    with pytest.raises(ValueError):
        migration.preview(root, "existing", path.relative_to(root).as_posix())
    assert not list((root / "projects/existing/runs").glob("migration-*/receipt.md"))


def test_cli_preview_writes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "records"
    relative = ready(root)
    result = CliRunner().invoke(
        app, ["migration", "record", "existing", "--root", str(root), "--input", relative]
    )
    assert result.exit_code == 0, result.output
    assert "Preview only" in result.output
    assert not list((root / "projects/existing/runs").glob("migration-*/receipt.md"))


@pytest.mark.parametrize("change", ["outcome", "body", "kind", "actor"])
def test_tampered_receipt_is_not_replayed(tmp_path: Path, change: str) -> None:
    root = tmp_path / "records"
    relative = ready(root)
    _, sha = migration.preview(root, "existing", relative)
    receipt = migration.record(root, "existing", relative, "researcher", sha)
    doc = decode(receipt.read_bytes())
    if change == "body":
        doc.body += "Unapproved replacement conclusion.\n"
    else:
        key, value = {
            "outcome": ("outcome", "passed"),
            "kind": ("kind", "other"),
            "actor": ("confirmed_by", None),
        }[change]
        doc.header[key] = value
    receipt.write_bytes(encode(doc))
    tampered = receipt.read_bytes()
    with pytest.raises(ValueError):
        migration.record(root, "existing", relative, "researcher", sha)
    assert receipt.read_bytes() == tampered
