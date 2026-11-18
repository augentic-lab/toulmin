"""R5: real decide discovery distinguishes context archives from sealed changes."""

import json

import pytest

from tests.acceptance.wo_support import ACTOR, invoke, sha, tree, v2_workspace
from toulmin.adapters.chief import ChiefClient
from toulmin.application.aoe import AoEWorkspace
from toulmin.cli import decide
from toulmin.core.codec import decode, encode
from toulmin.protocols import context_change


@pytest.fixture
def archives(wo, native, monkeypatch):
    v2_workspace(wo.root, wo.source, children=("latency",))
    home = wo.tmp / "fake-chief-state"
    home.mkdir()
    (wo.root / "tools/chief.local.toml").write_text(
        f'command = "MUST_NOT_RUN_CHIEF"\nhome = {json.dumps(str(home))}\n'
    )

    def forbidden_new(*args, **kwargs):
        raise AssertionError("Skipping a preview must never start a Chief worker")

    monkeypatch.setattr(ChiefClient, "new", forbidden_new)
    # Real context generation and source pins; only the native service is fake.
    view = AoEWorkspace(wo.root, None, native).open(codex_sandbox="inherit")
    native_archive = view.context_path.parent
    assert "-aoe-context-" in native_archive.name
    assert (native_archive / "context.md").is_file()
    assert not (native_archive / "seal").exists()
    invoke(
        "draft",
        "task",
        "--workspace",
        "--source",
        "source-main",
        "--root",
        wo.root,
        "--name",
        "discovery-helper",
    )
    requests = list((wo.root / "runs/proposals").glob("task-*.md"))
    assert len(requests) == 1
    request = requests[0]
    document = decode(request.read_bytes(), str(request))
    document.header["checks"] = ["python -m unittest"]
    document.body = (
        "## Goal\nAdd a bounded discovery helper.\n\n"
        "## Scope\nOnly main.py and its executable checks.\n"
    )
    request.write_bytes(encode(document))
    snapshot = wo.root / document.header["source_pin"]["snapshot"]
    task_archive = snapshot.parent.parent
    assert "-task-context-" in task_archive.name and snapshot.is_file()
    assert not (task_archive / "seal").exists()
    wo.archives = (native_archive, task_archive)
    wo.request = request
    wo.native = native
    return wo


def run_decide(wo, monkeypatch, *, interactive=True, workspace=True, answers="s\n"):
    # Exercise actual CLI discovery, item selection and previews. Only terminal
    # availability and external service boundaries are controlled by the fixture.
    monkeypatch.setattr(decide, "_interactive", lambda: interactive)
    return invoke(
        "decide",
        "--root",
        wo.root,
        *(["--workspace"] if workspace else []),
        "--confirmed-by",
        ACTOR,
        "--no-notify",
        input=answers,
    )


@pytest.mark.parametrize("interactive", [False, True])
def test_task_and_native_archives_do_not_create_false_decision_errors(
    archives, monkeypatch, interactive
):
    before = tree(archives.root)
    result = run_decide(archives, monkeypatch, interactive=interactive)
    assert "Not offered:" not in result.output, result.output
    assert "Awaiting your decision: 1 item(s)." in result.output
    assert (
        f"Engineering task: {archives.request.relative_to(archives.root).as_posix()}"
        in result.output
    )
    if interactive:
        assert "Add a bounded discovery helper." in result.output
        assert "Skipped: 1 | Failed: 0" in result.output
    assert tree(archives.root) == before
    assert len(archives.native.created) == 1 and len(archives.native.sent) == 1


def context_packet(root):
    return context_change.propose_overview(
        root,
        "latency",
        "# Components\nReview main.py before measuring latency.\n",
        rationale="Confirm the component inventory before the next measurement.",
    ).loaded.directory


@pytest.mark.parametrize("damage", ["missing-seal", "missing-packet", "tamper", "wrong-kind"])
def test_real_change_packet_damage_is_diagnosed_beside_valid_archives(
    archives, monkeypatch, damage
):
    relative = context_packet(archives.root)
    packet = archives.root / relative
    if damage == "missing-seal":
        (packet / "seal").unlink()
    elif damage == "missing-packet":
        (packet / "packet.md").unlink()
    elif damage == "tamper":
        (packet / "packet.md").write_text("tampered after sealing\n")
    else:
        data = json.loads((packet / "packet.md").read_bytes())
        data["kind"] = "task-context"
        raw = (json.dumps(data) + "\n").encode()
        (packet / "packet.md").write_bytes(raw)
        (packet / "seal").write_text(sha(raw) + "\n")
    before = tree(archives.root)
    result = run_decide(archives, monkeypatch)
    diagnostics = [line for line in result.output.splitlines() if line.startswith("Not offered:")]
    assert len(diagnostics) == 1, result.output
    assert relative in diagnostics[0]
    assert all(archive.name not in diagnostics[0] for archive in archives.archives)
    assert {
        "missing-seal": "/seal",
        "missing-packet": "/packet.md",
        "tamper": "seal mismatch",
        "wrong-kind": "invalid packet fields",
    }[damage] in diagnostics[0]
    assert "Awaiting your decision: 1 item(s)." in result.output
    assert "Add a bounded discovery helper." in result.output
    assert "Skipped: 1 | Failed: 0" in result.output
    assert tree(archives.root) == before


def test_valid_context_change_remains_offered_with_task_and_native_archives(archives, monkeypatch):
    relative = context_packet(archives.root)
    before = tree(archives.root)
    result = run_decide(archives, monkeypatch, workspace=False, answers="s\ns\n")
    assert "Not offered:" not in result.output, result.output
    assert "Awaiting your decision: 2 item(s)." in result.output
    assert f"Project context change: {relative}" in result.output
    assert "Engineering task:" in result.output
    assert "Skipped: 2 | Failed: 0" in result.output
    assert tree(archives.root) == before


def test_exact_named_incomplete_change_is_not_silently_ignored(wo, monkeypatch):
    v2_workspace(wo.root, wo.source, children=("latency",))
    relative = context_packet(wo.root)
    (wo.root / relative / "seal").unlink()
    before = tree(wo.root)
    result = run_decide(wo, monkeypatch, interactive=False)
    assert "Not offered:" in result.output and f"{relative}/seal" in result.output
    assert "expected existing regular file" in result.output
    assert "Nothing awaits your decision." in result.output
    assert tree(wo.root) == before
