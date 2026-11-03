"""Real job coordination with disposable fake CLIs, never subscription tools."""

import json
import sys
import time

import pytest

from toulmin.application.discussion import DiscussionService
from toulmin.core.codec import decode
from toulmin.protocols.discussion import begin_turn


@pytest.fixture
def discussion_bench(workbench, tmp_path):
    program = tmp_path / "fake-model"
    log = tmp_path / "prompts"
    log.mkdir()
    program.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys, time, uuid\n"
        "prompt = sys.stdin.read()\n"
        "if pathlib.Path.cwd().name == 'research':\n"
        "    pathlib.Path('paper.txt').write_text('Fake downloaded source; unverified.')\n"
        f"pathlib.Path({str(log)!r}, uuid.uuid4().hex).write_text(prompt)\n"
        "if os.environ.get('FAKE_WAIT') == 'yes':\n"
        "    print('partial diagnostics', flush=True)\n"
        "    time.sleep(10)\n"
        "print(json.dumps({'result': 'The queue depth is still unknown.', "
        "'session_id': 'fake-session', 'modelUsage': {'fake-model': {}}}))\n"
    )
    program.chmod(0o755)
    (workbench / "tools/models.toml").write_text(
        "[review]\nmax_runs=8\nparallel=2\ntimeout_seconds=5\n"
        'personas=[]\nmodels=["fake"]\n'
        '[models.fake]\nadapter="claude-code"\n'
        f"command={json.dumps(str(program))}\n"
    )
    return workbench, log


def wait_done(service, root):
    deadline = time.monotonic() + 7
    while service.active(root, "demo"):
        assert time.monotonic() < deadline, "fake job did not finish"
        time.sleep(0.02)
    assert service.error(root, "demo") is None


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_two_turns_reopen_and_formal_state_unchanged(discussion_bench):
    root, log = discussion_bench
    before = snapshot(root)
    service = DiscussionService(actor="Researcher")
    try:
        assert service.models(root) == ("fake",)
        assert service.load(root, "demo").turns == ()
        assert snapshot(root) == before
        assert list(log.iterdir()) == []
        service.start(root, "demo", "First observation: queue tails grow", "fake")
        wait_done(service, root)
        service.start(root, "demo", "Compare this with batching", "fake")
        wait_done(service, root)
        turns = service.load(root, "demo").turns
        assert len(turns) == 2 and all(turn.status == "completed" for turn in turns)
        assert len(list(log.iterdir())) == 2
        second = max(log.iterdir(), key=lambda p: p.stat().st_mtime_ns).read_text()
        assert "First observation" in second
        assert "The queue depth is still unknown." in second
        assert "Compare this with batching" in second
        for turn in turns:
            request = root / "projects/demo/runs/conversations/main" / turn.id
            assert (request / "research/paper.txt").read_text().startswith("Fake downloaded")
            assert (request / "tool-events.jsonl").is_file()
            assert (request / "tool-stderr.log").is_file()
        assert turns[0].id in second
        for path, content in before.items():
            assert (root / path).read_bytes() == content
        runs = list((root / "projects/demo/runs").glob("R-*.md"))
        assert len(runs) == 2
        assert all(decode(p.read_bytes()).header["role"] == "explorer" for p in runs)
    finally:
        service.close()
    reopened = DiscussionService()
    try:
        saved = snapshot(root)
        assert reopened.load(root, "demo").turns == turns
        assert snapshot(root) == saved
        assert len(list(log.iterdir())) == 2
    finally:
        reopened.close()


def test_cancel_and_close_archive_failure_and_release_lease(discussion_bench, monkeypatch):
    root, log = discussion_bench
    monkeypatch.setenv("FAKE_WAIT", "yes")
    service = DiscussionService()
    other = DiscussionService()
    try:
        service.start(root, "demo", "A slow question", "fake")
        deadline = time.monotonic() + 3
        while not list(log.iterdir()):
            assert time.monotonic() < deadline
            time.sleep(0.02)
        with pytest.raises(ValueError, match="lock|writer|running"):
            other.recover(root, "demo")
        service.close()
        assert not service.active(root, "demo")
        turn = other.load(root, "demo").turns[-1]
        assert turn.status == "failed" and "cancel" in turn.failure.lower()
        assert turn.run
        assert (
            root / "projects/demo/runs/conversations/main" / turn.id / "research/paper.txt"
        ).exists()
        assert "partial diagnostics" in (root / turn.archive / "tool.log").read_text()
        assert len(list(log.iterdir())) == 1
        monkeypatch.delenv("FAKE_WAIT")
        other.start(root, "demo", "Explicit new attempt", "fake")
        wait_done(other, root)
        assert len(list(log.iterdir())) == 2
    finally:
        service.close()
        other.close()


def test_restart_does_not_retry_and_explicit_recovery_does_not_call_model(discussion_bench):
    root, log = discussion_bench
    begin_turn(root, "demo", "Request saved before a crash", "fake", "Researcher")
    service = DiscussionService()
    try:
        before = snapshot(root)
        assert service.load(root, "demo").turns[-1].status == "running"
        assert snapshot(root) == before
        with pytest.raises(ValueError):
            service.start(root, "demo", "Must not send", "fake")
        service.recover(root, "demo")
        turn = service.load(root, "demo").turns[-1]
        assert turn.status == "failed" and turn.run
        assert list(log.iterdir()) == []
        service.start(root, "demo", "Now retry explicitly", "fake")
        wait_done(service, root)
        assert len(list(log.iterdir())) == 1
    finally:
        service.close()


def test_missing_executable_leaves_no_pending_request(discussion_bench):
    root, _ = discussion_bench
    config = root / "tools/models.toml"
    config.write_text(config.read_text().replace(str(root.parent / "fake-model"), "/missing/model"))
    service = DiscussionService()
    try:
        before = snapshot(root)
        with pytest.raises(ValueError, match="executable not found"):
            service.start(root, "demo", "Question", "fake")
        assert snapshot(root) == before
    finally:
        service.close()


def test_brief_generation_keeps_tool_free_profile(discussion_bench):
    root, _ = discussion_bench
    service = DiscussionService()
    try:
        request_id = service.start(root, "demo", "Draft from our discussion", "fake", "brief")
        wait_done(service, root)
        request = root / "projects/demo/runs/conversations/main" / request_id
        assert not (request / "research").exists()
        assert service.load(root, "demo").proposal is not None
        assert "do not" in (request / "prompt.md").read_text().lower()
    finally:
        service.close()
