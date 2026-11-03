"""Exploration enables native tools while independent review keeps its old profile.

Fake executables verify invocation and retention, not the vendors' OS sandboxes.
"""

import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from toulmin.adapters.base import Session
from toulmin.adapters.claude_code import ClaudeCode
from toulmin.adapters.codex import LAST_MESSAGE, Codex


@pytest.fixture
def fake(tmp_path):
    program = tmp_path / "model"
    program.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys, time\n"
        "args = sys.argv[1:]\n"
        "cwd = pathlib.Path.cwd()\n"
        "record = {'args': args, 'cwd': str(cwd), 'files': sorted(p.name for p in cwd.iterdir()), "
        "'prompt': sys.stdin.read()}\n"
        "pathlib.Path(os.environ['CALL_RECORD']).write_text(json.dumps(record))\n"
        "explore = '--restricted' in args or 'workspace-write' in args\n"
        "if explore:\n"
        "    (cwd / 'paper.pdf').write_bytes(b'%PDF downloaded fixture')\n"
        "    print(json.dumps({'type': 'tool_use', 'name': 'Bash', "
        "'command': 'curl paper'}), flush=True)\n"
        "if os.environ.get('FAKE_MODE') == 'wait':\n"
        "    print('partial stderr', file=sys.stderr, flush=True)\n"
        "    time.sleep(30)\n"
        "if 'exec' in args:\n"
        "    pathlib.Path(args[args.index('-o') + 1]).write_bytes(b'Answer\\r\\n')\n"
        "    print(json.dumps({'type': 'thread.started', 'thread_id': 'codex-thread'}))\n"
        "else:\n"
        "    print(json.dumps({'type': 'result', 'result': 'Answer\\r\\n', "
        "'session_id': 'claude-thread', 'modelUsage': {'reported-model': {}}}))\n"
        "if os.environ.get('FAKE_MODE') == 'fail':\n"
        "    print('BEGIN_FAILURE' + 'x' * 25000 + 'END_FAILURE', file=sys.stderr)\n"
        "    sys.exit(3)\n"
    )
    program.chmod(0o755)
    return program


def make_session(tmp_path, fake, *, explore, extra_args=(), mode="", timeout=5, cancel=None):
    archive = tmp_path / "request"
    archive.mkdir()
    workspace = archive / "research"
    if explore:
        workspace.mkdir()
    return Session(
        "Find and download the paper; cite its source.",
        "configured-model",
        timeout,
        str(fake),
        extra_args,
        (("CALL_RECORD", str(tmp_path / "call.json")), ("FAKE_MODE", mode)),
        cancel,
        workspace if explore else None,
    )


@pytest.mark.parametrize("adapter", [ClaudeCode(), Codex()], ids=["claude", "codex"])
def test_exploration_downloads_and_tool_trace_survive(tmp_path, fake, adapter):
    session = make_session(tmp_path, fake, explore=True)
    outcome = adapter.run(session)
    record = json.loads((tmp_path / "call.json").read_text())
    workspace = session.workspace
    assert workspace is not None
    assert record["cwd"] == str(workspace)
    assert record["prompt"] == session.prompt
    assert (workspace / "paper.pdf").read_bytes() == b"%PDF downloaded fixture"
    assert outcome.failure is None
    assert outcome.text == "Answer\r\n"
    assert outcome.session_id == f"{adapter.default_command}-thread"
    trace = workspace.parent / "tool-events.jsonl"
    assert '"name": "Bash"' in trace.read_text()
    assert (workspace.parent / "tool-stderr.log").read_bytes() == b""
    assert not (workspace / "tool-events.jsonl").exists()
    args = record["args"]
    assert not any("dangerously" in arg for arg in args)
    if isinstance(adapter, ClaudeCode):
        assert args[args.index("--tools") + 1] == "Bash,WebSearch,WebFetch"
        assert args[args.index("--output-format") + 1] == "stream-json"
        assert "--safe-mode" in args and "--restricted" in args
        assert args[args.index("--permission-mode") + 1] == "dontAsk"
        settings = json.loads(args[args.index("--settings") + 1])
        assert "WebSearch" in settings["permissions"]["allow"]
        assert "WebFetch(domain:*)" in settings["permissions"]["allow"]
        sandbox = settings["sandbox"]
        assert sandbox["enabled"] and sandbox["failIfUnavailable"]
        assert sandbox["autoAllowBashIfSandboxed"]
        assert not sandbox["allowUnsandboxedCommands"]
        assert not sandbox["filesystem"]["disabled"]
        assert sandbox["excludedCommands"] == []
    else:
        assert args[args.index("--sandbox") + 1] == "workspace-write"
        assert 'web_search="live"' in args
        assert "sandbox_workspace_write.network_access=true" in args
        assert "sandbox_workspace_write.writable_roots=[]" in args
        assert "sandbox_workspace_write.exclude_slash_tmp=true" in args
        assert "sandbox_workspace_write.exclude_tmpdir_env_var=true" in args
        assert "project_doc_max_bytes=0" in args
        assert "project_root_markers=[]" in args
        assert "features.hooks=false" in args
        assert "--ignore-user-config" in args and "--ignore-rules" in args
        assert Path(args[args.index("-o") + 1]) == workspace.parent / LAST_MESSAGE


@pytest.mark.parametrize("adapter", [ClaudeCode(), Codex()], ids=["claude", "codex"])
def test_review_still_starts_empty_and_removes_working_directory(tmp_path, fake, adapter):
    session = make_session(tmp_path, fake, explore=False)
    outcome = adapter.run(session)
    record = json.loads((tmp_path / "call.json").read_text())
    assert outcome.failure is None and outcome.text == "Answer\r\n"
    assert record["files"] == []
    assert not Path(record["cwd"]).exists()
    assert not (tmp_path / "request" / "tool-events.jsonl").exists()
    args = record["args"]
    if isinstance(adapter, ClaudeCode):
        assert args[args.index("--tools") + 1] == ""
        assert args[args.index("--output-format") + 1] == "json"
        assert "--restricted" not in args
    else:
        assert args[args.index("--sandbox") + 1] == "read-only"
        assert 'web_search="live"' not in args


@pytest.mark.parametrize("adapter", [ClaudeCode(), Codex()], ids=["claude", "codex"])
def test_failure_keeps_complete_events_logs_and_downloads(tmp_path, fake, adapter):
    session = make_session(tmp_path, fake, explore=True, mode="fail")
    outcome = adapter.run(session)
    assert outcome.failure is not None and "exit status 3" in outcome.failure
    workspace = session.workspace
    assert workspace is not None
    stderr = (workspace.parent / "tool-stderr.log").read_text()
    assert stderr.startswith("BEGIN_FAILURE") and stderr.endswith("END_FAILURE\n")
    assert len(stderr) > 25000
    assert (workspace / "paper.pdf").exists()
    assert "tool_use" in (workspace.parent / "tool-events.jsonl").read_text()
    assert outcome.text == "Answer\r\n"


@pytest.mark.parametrize("adapter", [ClaudeCode(), Codex()], ids=["claude", "codex"])
def test_cancelled_exploration_keeps_partial_trace_and_download(tmp_path, fake, adapter):
    cancel = threading.Event()
    session = make_session(tmp_path, fake, explore=True, mode="wait", cancel=cancel)
    with ThreadPoolExecutor(max_workers=1) as pool:
        job = pool.submit(adapter.run, session)
        try:
            assert session.workspace is not None
            deadline = time.monotonic() + 3
            while not (session.workspace / "paper.pdf").exists():
                assert time.monotonic() < deadline
                time.sleep(0.02)
            cancel.set()
            outcome = job.result(timeout=3)
        finally:
            cancel.set()
    assert outcome.failure is not None and "cancelled" in outcome.failure
    assert "tool_use" in (session.workspace.parent / "tool-events.jsonl").read_text()
    assert "partial stderr" in (session.workspace.parent / "tool-stderr.log").read_text()
    assert (session.workspace / "paper.pdf").exists()


@pytest.mark.parametrize(
    "extra",
    [
        ("--sandbox", "danger-full-access"),
        ("-sdanger-full-access",),
        ("--add-dir=/other",),
        ("--dangerously-bypass-approvals-and-sandbox",),
        ("-c", "sandbox_workspace_write.writable_roots=['/other']"),
        ("--config=approval_policy='on-request'",),
        ("-cweb_search='disabled'",),
        ("--profile", "other"),
        ("--enable", "hooks"),
        ("-o/other",),
    ],
)
def test_codex_rejects_profile_overrides_before_launch(tmp_path, fake, extra):
    session = make_session(tmp_path, fake, explore=True, extra_args=extra)
    with pytest.raises(ValueError, match="cannot override controlled Codex"):
        Codex().run(session)
    assert not (tmp_path / "call.json").exists()


@pytest.mark.parametrize(
    "extra",
    [
        ("--tools", "default"),
        ("--settings={}",),
        ("--add-dir=/other",),
        ("--dangerously-skip-permissions",),
        ("--permission-mode=bypassPermissions",),
        ("--allowedTools", "Edit"),
        ("--mcp-config", "other.json"),
    ],
)
def test_claude_rejects_profile_overrides_before_launch(tmp_path, fake, extra):
    session = make_session(tmp_path, fake, explore=True, extra_args=extra)
    with pytest.raises(ValueError, match="cannot override controlled Claude"):
        ClaudeCode().run(session)
    assert not (tmp_path / "call.json").exists()


def test_codex_accepts_reasoning_settings_and_existing_ignore_user_config(tmp_path, fake):
    session = make_session(
        tmp_path,
        fake,
        explore=True,
        extra_args=("--ignore-user-config", "-c", 'model_reasoning_effort="high"'),
    )
    outcome = Codex().run(session)
    assert outcome.failure is None
    args = json.loads((tmp_path / "call.json").read_text())["args"]
    assert args.count("--ignore-user-config") == 1
    assert 'model_reasoning_effort="high"' in args


def test_existing_trace_is_not_overwritten(tmp_path, fake):
    session = make_session(tmp_path, fake, explore=True)
    assert session.workspace is not None
    trace = session.workspace.parent / "tool-events.jsonl"
    target = tmp_path / "original.txt"
    target.write_text("original")
    trace.symlink_to(target)
    with pytest.raises(FileExistsError):
        ClaudeCode().run(session)
    assert target.read_text() == "original"
