"""Cancellation belongs to one invocation and reaps its whole process group."""

import os
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from toulmin.adapters.base import Finished, Session, failure_of, run_process
from toulmin.adapters.claude_code import ClaudeCode
from toulmin.adapters.codex import Codex


def test_cancel_reaps_group_preserves_output_and_leaves_other_job(tmp_path):
    pid_file = tmp_path / "child.pid"
    source = (
        "import subprocess, sys, time, pathlib\n"
        "sys.stdin.read()\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid))\n"
        "print('partial answer', flush=True)\n"
        "time.sleep(30)\n"
    )
    stop_first, stop_second = threading.Event(), threading.Event()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            run_process, [sys.executable, "-c", source], "question", 5, tmp_path, (), stop_first
        )
        second = pool.submit(
            run_process,
            [sys.executable, "-c", "import time; time.sleep(1); print('other answer')"],
            "",
            5,
            tmp_path,
            (),
            stop_second,
        )
        try:
            deadline = time.monotonic() + 3
            while not pid_file.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert pid_file.exists()
            stop_first.set()
            result = first.result(timeout=3)
            assert result.cancelled
            assert "partial answer" in result.stdout
            assert "cancelled" in failure_of(result, 5)
            other = second.result(timeout=3)
            assert not other.cancelled and other.exit_status == 0
            assert "other answer" in other.stdout
            child = int(pid_file.read_text())
            status = Path(f"/proc/{child}/status")
            deadline = time.monotonic() + 2
            while status.exists() and "State:\tZ" not in status.read_text():
                assert time.monotonic() < deadline, "child process survived cancellation"
                time.sleep(0.02)
        finally:
            stop_first.set()
            stop_second.set()
            if pid_file.exists():
                try:
                    os.kill(int(pid_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass


def test_cancel_before_launch_does_not_execute(tmp_path):
    cancel = threading.Event()
    cancel.set()
    result = run_process(["definitely-not-a-model-executable"], "", 5, tmp_path, cancel=cancel)
    assert result.cancelled
    assert result.stdout == ""


def test_timeout_still_preserves_output_and_reports_timeout(tmp_path):
    result = run_process(
        [sys.executable, "-c", "import time; print('partial', flush=True); time.sleep(5)"],
        "",
        0.2,
        tmp_path,
    )
    assert not result.cancelled
    assert result.exit_status is None
    assert "partial" in result.stdout
    assert "timed out" in failure_of(result, 0.2)


def test_adapters_retain_incomplete_answers_as_failed_output():
    partial = '{"result":"' + "unfinished" * 5000
    finished = Finished(None, partial, "", 1, cancelled=True)
    session = Session("question", "test-model", 5, "unused")
    claude = ClaudeCode().interpret(session, finished)
    assert claude.text == partial and "cancelled" in claude.failure
    codex = Codex().interpret(session, finished, "An unfinished answer")
    assert codex.text == "An unfinished answer" and "cancelled" in codex.failure


def test_process_and_codex_do_not_normalize_raw_output_newlines(tmp_path):
    finished = run_process(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'raw\\r\\nanswer\\r\\n')"],
        "",
        5,
        tmp_path,
    )
    assert finished.stdout == "raw\r\nanswer\r\n"
    script = tmp_path / "fake-codex"
    script.write_text(
        f"#!{sys.executable}\n"
        "import sys, pathlib\n"
        "sys.stdin.buffer.read()\n"
        "pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_bytes(b'brief\\r\\nbody\\r\\n')\n"
    )
    script.chmod(0o755)
    outcome = Codex().run(Session("question", "test", 5, str(script)))
    assert outcome.failure is None
    assert outcome.text == "brief\r\nbody\r\n"
