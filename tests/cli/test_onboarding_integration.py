from pathlib import Path

from typer.testing import CliRunner

from toulmin.cli import decide
from toulmin.cli.app import app
from toulmin.cli.initialize import initialize_workspace
from toulmin.core.sources import read_catalog

runner = CliRunner()


def test_onboard_decide_overview_reopen_context(tmp_path, monkeypatch):
    source = tmp_path / "existing"
    source.mkdir()
    (source / "README.md").write_text("An existing parser project.\n")
    root = tmp_path / "research"
    initialize_workspace(root)
    before = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
    proposed = runner.invoke(
        app, ["onboard", str(source), "--root", str(root), "--project", "parser"]
    )
    assert proposed.exit_code == 0, proposed.output
    assert not (root / "projects/parser").exists()
    found = decide.inventory(root)
    assert [item.kind for item in found.items] == ["onboarding"]
    monkeypatch.setattr(decide, "_interactive", lambda: True)
    result = runner.invoke(
        app, ["decide", "--root", str(root), "--confirmed-by", "tester", "--no-notify"], input="a\n"
    )
    assert result.exit_code == 0, result.output
    assert (root / "projects/parser/PROJECT.md").exists()
    assert len(read_catalog(root)) == 1
    assert not decide.inventory(root).items
    draft = runner.invoke(app, ["draft", "overview", "parser", "--root", str(root)])
    assert draft.exit_code == 0, draft.output
    relative = draft.output.splitlines()[0]
    (root / relative).write_text("# Understanding\nThe researcher wants to extend the parser.\n")
    proposed = runner.invoke(
        app,
        [
            "overview",
            "parser",
            "Confirm current direction",
            "--root",
            str(root),
            "--input",
            str(root / relative),
        ],
    )
    assert proposed.exit_code == 0, proposed.output
    result = runner.invoke(
        app, ["decide", "--root", str(root), "--confirmed-by", "tester", "--no-notify"], input="a\n"
    )
    assert result.exit_code == 0, result.output
    assert "extend the parser" in (root / "projects/parser/overview.md").read_text()
    assert before == {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
    assert not list((root / "projects/parser/claims").glob("C-*.md"))


def test_onboard_rejection_keeps_source_and_no_child(tmp_path: Path, monkeypatch):
    root = tmp_path / "research"
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("Keep this file.\n")
    initialize_workspace(root)
    proposed = runner.invoke(
        app, ["onboard", str(source), "--root", str(root), "--project", "rejected"]
    )
    assert proposed.exit_code == 0, proposed.output
    monkeypatch.setattr(decide, "_interactive", lambda: True)
    result = runner.invoke(
        app,
        ["decide", "--root", str(root), "--confirmed-by", "tester", "--no-notify"],
        input="r\nWrong scope\n",
    )
    assert result.exit_code == 0, result.output
    assert not (root / "projects/rejected").exists()
    assert not read_catalog(root)
    assert not decide.inventory(root).items
    assert (source / "README.md").read_text() == "Keep this file.\n"


def test_orphan_underlying_creation_is_never_offered(tmp_path):
    from toulmin.application.onboarding import prepare

    root = tmp_path / "research"
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("Original.\n")
    initialize_workspace(root)
    packet = prepare(root, source, "trial")
    (root / packet.loaded.creation / "onboarding").unlink()
    (root / packet.loaded.directory).rename(tmp_path / "unpublished")
    assert not decide.inventory(root).items
    assert not (root / "projects/trial").exists()


def test_receipt_before_retirement_remains_recoverable(tmp_path, monkeypatch):
    from toulmin.application.onboarding import prepare
    from toulmin.core import workspace_journal
    from toulmin.protocols import context_change, onboarding

    root = tmp_path / "research"
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("Original.\n")
    initialize_workspace(root)
    packets = [(onboarding, prepare(root, source, "trial"))]
    for protocol, packet in packets:

        def stop_retire(repository):
            raise OSError("interrupted before retirement")

        with monkeypatch.context() as scoped:
            scoped.setattr(workspace_journal, "retire", stop_retire)
            import pytest

            with pytest.raises(OSError, match="retirement"):
                protocol.apply(root, packet.loaded.directory, "tester", confirmed=True)
        assert (root / packet.loaded.directory / "receipt.md").exists()
        assert any(item.path == packet.loaded.directory for item in decide.inventory(root).items)
        assert (
            protocol.apply(root, packet.loaded.directory, "tester", confirmed=True).status
            == "recovered"
        )
        assert not (root / ".workspace-pending").exists()
        if protocol is onboarding:
            packets.append(
                (
                    context_change,
                    context_change.propose_overview(
                        root,
                        "trial",
                        "# Confirmed structural understanding\n",
                        rationale="Checkpoint",
                    ),
                )
            )
    for staged in (root / "tools").glob("onboard-*.local.toml"):
        staged.unlink()
    found = decide.inventory(root)
    assert not found.items
    assert not found.ignored
