"""Native lifecycle with actual tmux/bwrap and disposable fake provider executables."""

import errno
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

pytest.importorskip("textual", reason="install Toulmin's tui extra")

from toulmin.application import native
from toulmin.application.discussion import DiscussionService
from toulmin.application.workspace import WorkspaceService
from toulmin.core.atomic import handoff_mutex
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError
from toulmin.protocols.discussion import begin_turn
from toulmin.protocols.native import begin_native, list_native, load_native


@pytest.fixture
def native_project(tmp_path):
    root = tmp_path / "workbench with spaces"
    project = WorkspaceService().create_project(
        root, "queues", "Find why repeated queries slow down", "Avoid untested cache changes"
    )
    assert not project.setup_pending and not project.diagnostics
    return root


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def until(predicate, *, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.04)
    raise AssertionError("timed out waiting for the disposable native worker")


def fake_codex(tmp_path, monkeypatch, root, socket, *, wait=False):
    executable = tmp_path / "fake-bin" / "codex"
    executable.parent.mkdir()
    cache = tmp_path / "fake-cache"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import errno, json, os, pathlib, subprocess, sys, time\n"
        f"root = pathlib.Path({str(root)!r})\n"
        "workspace = pathlib.Path.cwd()\n"
        "context = pathlib.Path('context.md').read_text()\n"
        "marker = '<<<FILE projects/queues/brief.md>>>\\n'\n"
        "before = context.split(marker, 1)[1].split('\\n<<<END FILE>>>', 1)[0]\n"
        "denials = {}\n"
        "for relative in ('AGENTS.md', 'projects/queues/PROJECT.md', "
        "'projects/queues/brief.md'):\n"
        "    try:\n"
        "        (root / relative).write_text('UNAUTHORIZED')\n"
        "        denials[relative] = None\n"
        "    except OSError as error:\n"
        "        denials[relative] = error.errno\n"
        f"pathlib.Path({str(cache)!r}).write_text('disposable native cache')\n"
        "pathlib.Path('draft.md').write_text(before)\n"
        "report = {'args': sys.argv[1:], 'context': context, 'denials': denials,\n"
        f"    'socket_visible': pathlib.Path({str(socket)!r}).exists(),\n"
        "    'tmux_env': os.environ.get('TMUX'),\n"
        "    'pane_env': os.environ.get('TMUX_PANE'),\n"
        "    'net_ns': os.readlink('/proc/self/ns/net'),\n"
        "    'tty': [os.isatty(fd) for fd in (0, 1, 2)]}\n"
        "pathlib.Path('probe.json').write_text(json.dumps(report))\n"
        + (
            "subprocess.Popen(['sleep', '60'], start_new_session=True)\n"
            "pathlib.Path('ready').write_text('detached child started')\n"
            "time.sleep(60)\n"
            if wait
            else ""
        ),
        encoding="utf-8",
    )
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(executable.parent) + os.pathsep + os.environ["PATH"])
    return cache


real_runtime = pytest.mark.skipif(
    not all(shutil.which(command) for command in ("tmux", "bwrap")),
    reason="actual native lifecycle requires tmux and bubblewrap",
)


@real_runtime
def test_actual_native_worker_protects_project_and_archives_draft(
    native_project, tmp_path, monkeypatch
):
    root = native_project
    original = snapshot(root)
    view = begin_native(root, "queues", "codex", "Researcher")
    with tempfile.TemporaryDirectory(prefix="toulmin-native-test-") as server:
        socket = Path(server) / "socket"
        cache = fake_codex(tmp_path, monkeypatch, root, socket)
        try:
            native.start_split(view, socket, 120, 30)
            until(lambda: load_native(root, "queues", view.id).status == "closed")
            closed = load_native(root, "queues", view.id)
            report = json.loads((view.workspace / "probe.json").read_text())
            assert "--no-daemon" in report["args"]
            assert report["context"] == view.context
            assert set(report["denials"].values()) == {errno.EROFS}
            assert not report["socket_visible"]
            assert report["tmux_env"] is None and report["pane_env"] is None
            assert report["tty"] == [True, True, True]
            assert report["net_ns"] == os.readlink("/proc/self/ns/net")
            assert cache.read_text() == "disposable native cache"
            assert closed.output_status == "completed" and closed.exit_code == 0
            assert closed.proposal_status == "pending"
            assert closed.draft == view.before and closed.application_status == "none"
            assert (closed.archive / "draft.md").read_text() == view.before
            run = decode((root / "projects/queues/runs" / f"{closed.run}.md").read_bytes())
            assert run.header["status"] == "completed" and run.header["role"] == "explorer"
            assert run.header["session_id"] is None
            assert "not reported" in run.header["model"]
            assert "not captured" in run.body
            assert all((root / name).read_bytes() == data for name, data in original.items())
            # Finalization is retryable and creates exactly one Run.
            assert native._finish_stopped(root, "queues", view.id).run == closed.run
            assert len(list((root / "projects/queues/runs").glob("R-*.md"))) == 1
        finally:
            native.tmux(socket, "kill-server", check=False)


def process_identity(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().split()
        return (pid, fields[21]) if fields[2] != "Z" else None
    except FileNotFoundError:
        return None


def descendants(pid):
    result = []
    pending = [pid]
    while pending:
        parent = pending.pop()
        identity = process_identity(parent)
        if identity is not None:
            result.append(identity)
        try:
            children = Path(f"/proc/{parent}/task/{parent}/children").read_text().split()
            pending.extend(int(child) for child in children)
        except FileNotFoundError:
            pass
    return result


@real_runtime
def test_server_shutdown_interrupts_worker_and_detached_children(
    native_project, tmp_path, monkeypatch
):
    root = native_project
    view = begin_native(root, "queues", "codex", "Researcher")
    processes = []
    with tempfile.TemporaryDirectory(prefix="toulmin-native-test-") as server:
        socket = Path(server) / "socket"
        fake_codex(tmp_path, monkeypatch, root, socket, wait=True)
        try:
            native.start_split(view, socket, 120, 30)
            until(lambda: (view.workspace / "ready").exists())
            pane_pid = int(
                native.tmux(
                    socket, "display-message", "-p", "-t", "research:0.1", "#{pane_pid}"
                ).stdout.strip()
            )
            processes = descendants(pane_pid)
            assert len(processes) >= 4  # Worker, namespace launcher/reaper, CLI and child.
            assert any(
                Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[:2] == [b"sleep", b"60"]
                for pid, _ in processes
            )
            with pytest.raises(FormatError, match="another handoff writer"):
                native.run_worker(root, "queues", view.id, socket, "agent")
            native.tmux(socket, "kill-server")
            closed = native._finish_stopped(root, "queues", view.id)
            assert closed.status == "closed" and closed.output_status == "failed"
            assert closed.interrupted and closed.failure
            assert closed.proposal_status == "none"
            assert closed.draft == view.before
            until(
                lambda: all(process_identity(pid) != (pid, started) for pid, started in processes)
            )
            # Recovery and later work can acquire both leases after the worker stops.
            with handoff_mutex(native._worker_path(root, "queues")):
                pass
            service = DiscussionService()
            try:
                service.recover(root, "queues")
            finally:
                service.close()
        finally:
            native.tmux(socket, "kill-server", check=False)
            for pid, started in processes:
                if process_identity(pid) == (pid, started):
                    os.kill(pid, signal.SIGKILL)


def terminal(monkeypatch):
    monkeypatch.setattr(native.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(native.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(native.shutil, "get_terminal_size", lambda: os.terminal_size((120, 30)))


@real_runtime
def test_launcher_holds_shared_project_lease_while_attached(native_project, tmp_path, monkeypatch):
    root = native_project
    terminal(monkeypatch)
    fake_codex(tmp_path, monkeypatch, root, tmp_path / "absent-socket")
    execute = subprocess.run
    attached = []

    def attach_or_execute(command, *args, **kwargs):
        if command[0] == "tmux" and "attach-session" in command:
            attached.append(command)
            service = DiscussionService()
            try:
                with pytest.raises(FormatError, match="another handoff writer"):
                    service.recover(root, "queues")
                with pytest.raises(FormatError, match="another handoff writer"):
                    native.launch_native(root, "queues")
            finally:
                service.close()
            until(lambda: list_native(root, "queues")[-1].status == "closed")
            return subprocess.CompletedProcess(command, 0)
        return execute(command, *args, **kwargs)

    monkeypatch.setattr(native.subprocess, "run", attach_or_execute)
    closed = native.launch_native(root, "queues", actor="Researcher")
    assert len(attached) == 1
    assert closed.output_status == "completed" and closed.proposal_status == "pending"
    assert len(list_native(root, "queues")) == 1
    service = DiscussionService()
    try:
        service.recover(root, "queues")
    finally:
        service.close()


@pytest.mark.parametrize("lease_name", ["discussion-job", "native-agent-job"])
def test_launch_refuses_existing_project_job_without_creating_session(
    native_project, monkeypatch, lease_name
):
    root = native_project
    terminal(monkeypatch)
    monkeypatch.setattr(native.shutil, "which", lambda name: "/unused/" + name)
    before = snapshot(root)
    with handoff_mutex(root / "projects/queues/runs" / lease_name):
        with pytest.raises(FormatError, match="another handoff writer"):
            native.launch_native(root, "queues")
    assert snapshot(root) == before
    assert list_native(root, "queues") == ()


@pytest.mark.parametrize("failure", ["terminal", "missing", "size", "namespace"])
def test_launch_preflight_failure_writes_no_session_or_run(native_project, monkeypatch, failure):
    root = native_project
    terminal(monkeypatch)
    monkeypatch.setattr(native.shutil, "which", lambda name: "/unused/" + name)
    if failure == "terminal":
        monkeypatch.setattr(native.sys.stdin, "isatty", lambda: False)
        expected = "interactive terminal"
    elif failure == "missing":
        monkeypatch.setattr(native.shutil, "which", lambda name: None if name == "bwrap" else name)
        expected = "bwrap: executable not found"
    elif failure == "size":
        monkeypatch.setattr(native.shutil, "get_terminal_size", lambda: os.terminal_size((80, 24)))
        expected = "100 columns"
    else:
        monkeypatch.setattr(
            native.subprocess,
            "run",
            lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "denied namespace"),
        )
        expected = "filesystem protection unavailable: denied namespace"
    before = snapshot(root)
    with pytest.raises(FormatError, match=expected):
        native.launch_native(root, "queues")
    assert snapshot(root) == before
    assert list_native(root, "queues") == ()


def test_launch_refuses_unresolved_headless_discussion(native_project, monkeypatch):
    root = native_project
    terminal(monkeypatch)
    monkeypatch.setattr(native.shutil, "which", lambda name: "/unused/" + name)
    begin_turn(root, "queues", "A pending question", "fake", "Researcher")
    before = snapshot(root)
    with pytest.raises(FormatError, match="Finish/recover Discussion"):
        native.launch_native(root, "queues")
    assert snapshot(root) == before
    assert list_native(root, "queues") == ()
