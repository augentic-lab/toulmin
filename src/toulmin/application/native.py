"""Interactive native CLI lifecycle; project writes remain in the confirmation protocol."""

import argparse
import getpass
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from toulmin.application.workspace import WorkspaceService
from toulmin.core.atomic import handoff_mutex
from toulmin.core.documents import FormatError
from toulmin.core.repository import Repository
from toulmin.protocols.discussion import load_discussion
from toulmin.protocols.native import (
    NativeSession,
    begin_native,
    finalize_native,
    load_native,
)

AGENTS = ("codex", "claude")
INITIAL_PROMPT = (
    "Read context.md in the current directory and begin discussing the research question "
    "with me. When I request a Brief, write the complete proposed replacement to draft.md. "
    "Do not change the saved project files."
)


def tmux(socket: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key in ("TMUX", "COLUMNS", "LINES"):
        env.pop(key, None)
    result = subprocess.run(
        ["tmux", "-S", str(socket), "-f", "/dev/null", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError(f"tmux: {result.stderr.strip() or 'command failed'}")
    return result


def protected_command(root: Path, workspace: Path, socket: Path, command: list[str]) -> list[str]:
    """Protect direct workbench paths, retaining normal networking and native cache access.

    This is not isolation from all same-user IPC/hardlink aliases. The private tmux
    socket is hidden because it can execute commands outside the filesystem namespace.
    """
    return [
        "bwrap",
        "--die-with-parent",
        "--unshare-user",
        "--unshare-pid",
        "--bind",
        "/",
        "/",
        "--proc",
        "/proc",
        "--ro-bind",
        str(root),
        str(root),
        "--bind",
        str(workspace),
        str(workspace),
        "--tmpfs",
        str(socket.parent),
        "--unsetenv",
        "TMUX",
        "--unsetenv",
        "TMUX_PANE",
        "--chdir",
        str(workspace),
        "--",
        *command,
    ]


def _worker_path(root: Path, project: str) -> Path:
    return root / "projects" / project / "runs" / "native-agent-job"


def _finish_stopped(root: Path, project: str, session: str) -> NativeSession:
    # tmux sends HUP on closure; give its worker time to release the execution lease.
    for attempt in range(30):
        try:
            with handoff_mutex(_worker_path(root, project)):
                view = load_native(root, project, session)
                if view.status == "started":
                    return finalize_native(root, project, session, interrupted=True)
                return view
        except FormatError as error:
            if "another handoff writer holds the lock" not in str(error) or attempt == 29:
                raise
            time.sleep(0.1)
    raise RuntimeError("Native worker did not stop; recover this session after it exits")


def run_worker(root: Path, project: str, session: str, socket: Path, role: str) -> int:
    if role == "board":
        view = load_native(root, project, session)
        try:
            return subprocess.call(
                [
                    sys.executable,
                    "-m",
                    "toulmin.tui.native",
                    "--root",
                    str(root),
                    "--project",
                    project,
                    "--session",
                    session,
                    "--actor",
                    view.actor,
                ]
            )
        finally:
            tmux(socket, "kill-server", check=False)
    with handoff_mutex(_worker_path(root, project)):
        view = load_native(root, project, session)
        if view.status != "started" or view.agent not in AGENTS:
            raise FormatError("Native worker requires a new supported native session")
        executable = shutil.which(view.agent)
        if executable is None:
            raise FormatError(f"{view.agent}: executable disappeared before launch")
        print(f"Project: {project} | native {view.agent}", flush=True)
        print(
            "The initial message asks the CLI to read this project's frozen context.md.", flush=True
        )
        print(
            "When ready, ask for draft.md, then exit the CLI to archive and review it.", flush=True
        )
        diagnostic = "Native CLI exited; full conversation was not captured.\n"
        interrupted = False
        command = [executable, "--no-daemon"] if view.agent == "codex" else [executable]
        command.append(INITIAL_PROMPT)
        try:
            process = subprocess.Popen(
                protected_command(root, view.workspace, socket, command),
                cwd=view.workspace,
            )

            def stop(signum: int, frame: object) -> None:
                nonlocal interrupted
                interrupted = True
                process.terminate()

            # Ctrl+C belongs to the foreground CLI, not this bookkeeping wrapper.
            handlers = {
                signum: signal.signal(signum, handler)
                for signum, handler in (
                    (signal.SIGHUP, stop),
                    (signal.SIGTERM, stop),
                    (signal.SIGINT, lambda signum, frame: None),
                )
            }
            try:
                code = process.wait()
            finally:
                for signum, handler in handlers.items():
                    signal.signal(signum, handler)
        except OSError as error:
            code = 127
            diagnostic += str(error)
        finalize_native(root, project, session, code, interrupted, diagnostic=diagnostic.encode())
        print(
            f"Native CLI exited ({code}). Review the archived draft in the left pane.", flush=True
        )
        return code


def start_split(view: NativeSession, socket: Path, columns: int, lines: int) -> None:
    def command(role: str) -> str:
        return shlex.join(
            [
                sys.executable,
                "-m",
                "toulmin.application.native",
                "--root",
                str(view.root),
                "--project",
                view.project,
                "--session",
                view.id,
                "--socket",
                str(socket),
                "--worker",
                role,
            ]
        )

    tmux(
        socket,
        "new-session",
        "-d",
        "-s",
        "research",
        "-x",
        str(columns),
        "-y",
        str(lines),
        "-c",
        str(view.workspace),
        command("board"),
    )
    tmux(socket, "set-option", "-g", "remain-on-exit", "on")
    tmux(socket, "set-option", "-g", "mouse", "on")
    tmux(socket, "set-option", "-g", "status-left", " Toulmin ")
    tmux(socket, "set-option", "-g", "status-right", "Ctrl+b o: focus | Ctrl+b z: zoom")
    tmux(socket, "set-option", "-g", "status-right-length", "65")
    tmux(
        socket,
        "split-window",
        "-h",
        "-l",
        str(columns - 39),
        "-t",
        "research:0.0",
        "-c",
        str(view.workspace),
        command("agent"),
    )
    tmux(socket, "select-pane", "-t", "research:0.1")


def launch_native(
    root: Path,
    project: str,
    agent: str = "codex",
    *,
    session: str | None = None,
    recover: bool = False,
    actor: str | None = None,
) -> NativeSession:
    """Open a new split, or explicitly inspect/recover an archive without calling a model."""
    from toulmin.tui.native import NativeBoard

    root = Repository(root).root
    actor = actor or getpass.getuser()
    project_view = WorkspaceService().open_project(root, project)
    if project_view.setup_pending or project_view.diagnostics:
        raise FormatError(
            "Resolve project diagnostics or incomplete setup before native discussion"
        )
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise FormatError("Native discussion requires an interactive terminal")
    if recover and session is None:
        raise FormatError("--recover requires an explicit --session")
    # Shared with headless Discussion, preventing cross-process concurrent collaboration.
    lease = root / "projects" / project / "runs" / "discussion-job"
    with handoff_mutex(lease):
        if session is not None:
            with handoff_mutex(_worker_path(root, project)):
                view = load_native(root, project, session)
                if view.status == "started":
                    if not recover:
                        raise FormatError("Session was interrupted; explicitly use --recover")
                    view = finalize_native(root, project, session, interrupted=True)
            NativeBoard(root, project, view.id, actor).run()
            return load_native(root, project, view.id)
        if agent not in AGENTS:
            raise FormatError("Choose codex or claude for native discussion")
        for executable in ("tmux", "bwrap", agent):
            if shutil.which(executable) is None:
                raise FormatError(f"{executable}: executable not found; install it before starting")
        columns, lines = shutil.get_terminal_size()
        if columns < 100 or lines < 24:
            raise FormatError("Native split requires at least 100 columns x 24 rows")
        discussion = load_discussion(root, project)
        if any(turn.status == "running" for turn in discussion.turns) or discussion.proposal:
            raise FormatError("Finish/recover Discussion and apply/dismiss its proposal first")
        with handoff_mutex(_worker_path(root, project)):
            pass  # Refuse a live worker even if its original launcher was killed.
        with tempfile.TemporaryDirectory(prefix="toulmin-native-") as server:
            socket = Path(server) / "socket"
            # Fail before creating a durable request if local namespaces are unavailable.
            probe = subprocess.run(
                protected_command(root, Path(server), socket, ["/bin/true"]),
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if probe.returncode:
                raise FormatError(
                    f"Native filesystem protection unavailable: {probe.stderr.strip()}"
                )
            view = begin_native(root, project, agent, actor)
            try:
                start_split(view, socket, columns, lines)
                env = os.environ.copy()
                env.pop("TMUX", None)
                subprocess.run(
                    ["tmux", "-S", str(socket), "attach-session", "-t", "research"],
                    env=env,
                    check=False,
                )
            except KeyboardInterrupt:
                pass
            finally:
                tmux(socket, "kill-server", check=False)
                _finish_stopped(root, project, view.id)
            return load_native(root, project, view.id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Internal native pane worker")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--worker", required=True, choices=("board", "agent"))
    args = parser.parse_args()
    raise SystemExit(run_worker(args.root, args.project, args.session, args.socket, args.worker))


if __name__ == "__main__":
    main()
