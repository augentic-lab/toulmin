"""UI-R4: disposable tmux workspace with a research board and an unwrapped CLI."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROMPT = "Read context.md, discuss the question, and write a draft to draft.md when asked."


def tmux(socket: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    # A private socket/config prevents changing or destroying the user's tmux sessions.
    env = os.environ.copy()
    env.pop("TMUX", None)
    return subprocess.run(
        ["tmux", "-S", str(socket), "-f", "/dev/null", *args],
        env=env,
        check=check,
        text=True,
        capture_output=True,
        timeout=10,
    )


def initialize(workspace: Path, question: str) -> None:
    workspace.mkdir()  # Never reuse a real project or silently replace a previous trial.
    (workspace / "context.md").write_text(
        "# Disposable research trial\n\n"
        "## Question\n" + question + "\n\n"
        "## Collaboration\n"
        "Discuss freely with the researcher. Ask questions, inspect material and use your "
        "normal tools as requested. When the researcher asks for a brief, write Markdown to "
        "draft.md here. It is a proposal, not a confirmed result. Cite sources if used; "
        "do not invent evidence. Do not write accepted-brief.md: the research board owns "
        "that confirmation. There is no real Toulmin project in this trial.\n",
        encoding="utf-8",
    )


def demo(workspace: Path) -> int:
    print("SIMULATED AGENT — no model, network, or research evidence", flush=True)
    print("Native-style input stays in this pane. /help lists trial actions.", flush=True)
    while True:
        try:
            line = input("demo> ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        if line == "/exit":
            return 0
        if line == "/help":
            print("/context  Read question\n/draft  Write fictional proposal\n/exit  Exit agent")
        elif line == "/context":
            print((workspace / "context.md").read_text(encoding="utf-8"))
        elif line == "/draft":
            # Exclusive creation also refuses symlinks supplied by a different process.
            try:
                with (workspace / "draft.md").open("x", encoding="utf-8") as stream:
                    stream.write(
                        "# Trial brief — simulated\n\n"
                        "Question: why are some repeated queries slow?\n\n"
                        "Next: compare timing traces before choosing caching as a remedy.\n\n"
                        "No measurement or evidence has been collected.\n"
                    )
                print("Wrote draft.md. Switch to the board to inspect and confirm it.")
            except FileExistsError:
                print("draft.md already exists; preserved it.")
        else:
            print("Simulated reply: this checks interaction only. Try /context or /draft.")


def worker(role: str, workspace: Path, socket: Path, agent: str) -> int:
    if role == "board":
        try:
            return subprocess.call(
                [sys.executable, str(HERE / "native_board.py"), "--workspace", str(workspace)]
            )
        finally:
            tmux(socket, "kill-server", check=False)
    if agent == "demo":
        code = demo(workspace)
    else:
        print(f"Native {agent}; uses your normal CLI configuration and permission prompts.")
        print(f"Trial directory: {workspace}\nSuggested first message: {PROMPT}", flush=True)
        code = subprocess.call([agent], cwd=workspace)
    # Exit metadata is informational; this is not a structured model Run archive.
    try:
        with (workspace / "native-exit.json").open("x", encoding="utf-8") as stream:
            json.dump({"agent": agent, "exit_code": code}, stream)
    except FileExistsError:
        pass
    print(f"Agent exited ({code}). Switch to the board; q ends the trial.", flush=True)
    return code


def start(workspace: Path, socket: Path, agent: str, columns: int, lines: int) -> None:
    def command(role: str) -> str:
        return shlex.join(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                role,
                "--workspace",
                str(workspace),
                "--socket",
                str(socket),
                "--agent",
                agent,
            ]
        )

    tmux(
        socket,
        "new-session",
        "-d",
        "-s",
        "trial",
        "-x",
        str(columns),
        "-y",
        str(lines),
        "-c",
        str(workspace),
        command("board"),
    )
    tmux(socket, "set-option", "-g", "remain-on-exit", "on")
    tmux(socket, "set-option", "-g", "mouse", "on")
    tmux(socket, "set-option", "-g", "status-left", " Toulmin trial ")
    tmux(socket, "set-option", "-g", "status-right", "Ctrl+b o: focus | Ctrl+b z: zoom")
    tmux(socket, "set-option", "-g", "status-right-length", "65")
    tmux(
        socket,
        "split-window",
        "-h",
        "-l",
        str(columns - 39),
        "-t",
        "trial:0.0",
        "-c",
        str(workspace),
        command("agent"),
    )
    tmux(socket, "select-pane", "-t", "trial:0.1")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=("demo", "codex", "claude"), default="demo")
    parser.add_argument(
        "--workspace", type=Path, help="New directory only; default: temporary path"
    )
    parser.add_argument("--question", default="Why are some repeated queries slow?")
    parser.add_argument("--worker", choices=("board", "agent"), help=argparse.SUPPRESS)
    parser.add_argument("--socket", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        if args.workspace is None or args.socket is None:
            parser.error("worker requires workspace and socket")
        return worker(args.worker, args.workspace, args.socket, args.agent)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("Run this prototype in an interactive terminal")
    if not shutil.which("tmux"):
        parser.error("tmux is required")
    if args.agent != "demo" and not shutil.which(args.agent):
        parser.error(f"{args.agent} is not on PATH")
    if not args.question.strip():
        parser.error("Question must not be blank")
    columns, lines = shutil.get_terminal_size()
    if columns < 100 or lines < 24:
        parser.error("Use at least 100 columns x 24 rows for this split trial")
    workspace = args.workspace
    if workspace is None:
        workspace = Path(tempfile.mkdtemp(prefix="toulmin-split-")) / "workspace"
    workspace = workspace.expanduser().absolute()
    try:
        initialize(workspace, args.question)
    except OSError as error:
        parser.error(str(error))
    # A short private path fits Unix socket length limits even with long workspace names.
    with tempfile.TemporaryDirectory(prefix="toulmin-tmux-") as server:
        socket = Path(server) / "socket"
        try:
            start(workspace, socket, args.agent, columns, lines)
            env = os.environ.copy()
            env.pop("TMUX", None)
            subprocess.run(
                ["tmux", "-S", str(socket), "attach-session", "-t", "trial"], env=env, check=False
            )
        except (OSError, subprocess.SubprocessError) as error:
            print(f"Trial failed: {error}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            pass
        finally:
            tmux(socket, "kill-server", check=False)
            print(f"Trial stopped. Files retained at: {workspace}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
