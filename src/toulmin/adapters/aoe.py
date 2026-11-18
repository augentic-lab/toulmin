"""Thin Agent of Empires CLI adapter; no provider or tmux control.

Screen checks supplement AoE's lifecycle/status reporting. They cannot prove that
an agent received or understood a message, and never override ``starting``.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from toulmin.core.identifiers import validate_project_name

_SESSION_ID = re.compile(r"[0-9a-f]{16}")
_PROFILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_TIMEOUT = 15.0
_CREATE_TIMEOUT = 45.0
_QUIET_INTERVAL = 0.25
_BLOCKED = re.compile(
    r"trust (?:this|the)|do you trust|update (?:available|now)|upgrade|"
    r"permission|approve|approval|allow (?:once|always)|would you like|"
    r"yes,? (?:proceed|continue)|select (?:an? |the )?option|"
    r"esc(?:ape)? to (?:interrupt|cancel|stop)|\b(?:working|thinking|busy|processing)\b|"
    r"connecting|reconnecting|starting|press enter to|sign in|log in",
    re.IGNORECASE,
)
_BORDER = re.compile(r"[\s─━═╭╮╰╯│┃]*")
_BLOCKED_REASON = "Native screen contains a busy state or confirmation/menu; resolve it in AoE"
# Readiness refusals that only the researcher can clear; every other one may clear by
# itself while a freshly launched native CLI draws its first screen (R7).
_NEEDS_RESEARCHER = (
    "Native screen contains a selection menu",
    "Native input contains text",
    "Native launch",
    "Readiness supports",
)


def settling(reason: str) -> bool:
    """Whether a readiness refusal can clear without the researcher (a starting CLI)."""
    return not reason.startswith(_NEEDS_RESEARCHER)


class AoEError(RuntimeError):
    """CLI failure, retaining a created session's identity when it is known."""

    def __init__(
        self, message: str, *, session_id: str | None = None, creation_uncertain: bool = False
    ) -> None:
        super().__init__(message)
        self.session_id = session_id
        self.creation_uncertain = creation_uncertain


@dataclass(frozen=True)
class AoESession:
    id: str
    path: Path
    tool: str
    state: str
    status: str | None = None
    agent_session_id: str | None = None
    title: str = ""


def _validate_id(value: str) -> str:
    if not isinstance(value, str) or not _SESSION_ID.fullmatch(value):
        raise AoEError("AoE session ID must be exactly 16 lowercase hexadecimal characters")
    return value


def _session(value: object) -> AoESession:
    if not isinstance(value, dict):
        raise AoEError("Malformed AoE session: expected an object")
    fields: dict[str, str] = {}
    for key in ("id", "path", "tool", "state"):
        item = value.get(key)
        if not isinstance(item, str) or not item.strip() or "\x00" in item:
            raise AoEError(f"Malformed AoE session: {key} must be a nonempty string")
        fields[key] = item
    _validate_id(fields["id"])
    path = Path(fields["path"])
    if not path.is_absolute():
        raise AoEError("Malformed AoE session: path must be absolute")
    optional: dict[str, str | None] = {}
    for key in ("status", "agent_session_id"):
        item = value.get(key)
        if item is not None and (not isinstance(item, str) or not item.strip() or "\x00" in item):
            raise AoEError(f"Malformed AoE session: {key} must be a nonempty string or null")
        optional[key] = item
    title = value.get("title", "")
    if not isinstance(title, str) or "\x00" in title:
        raise AoEError("Malformed AoE session: title must be a string")
    return AoESession(
        fields["id"],
        path,
        fields["tool"],
        fields["state"],
        optional["status"],
        optional["agent_session_id"],
        title,
    )


class AoEClient:
    """Use public AoE commands with one explicit profile and bounded operations."""

    def __init__(self, profile: str = "main", command: str | None = None) -> None:
        if not isinstance(profile, str) or not _PROFILE.fullmatch(profile):
            raise AoEError("Invalid AoE profile: use 1–64 letters, digits, underscores or hyphens")
        self.profile = profile
        configured = command if command is not None else os.environ.get("TOULMIN_AOE_COMMAND")
        from_path = False
        if configured is not None:
            if not isinstance(configured, str) or not configured.strip() or "\x00" in configured:
                raise AoEError("AoE command must name one executable")
            executable = shutil.which(os.path.expanduser(configured))
        else:
            local = Path.home() / ".local/bin/aoe"
            if local.is_file() and os.access(local, os.X_OK):
                executable = str(local)
            else:
                executable = shutil.which("aoe")
                from_path = True
        if executable is None:
            raise AoEError("Agent of Empires executable not found; set TOULMIN_AOE_COMMAND")
        self.command = executable
        # PATH can contain an unrelated program named aoe. Explicit selections
        # are intentional; the unqualified fallback must identify this product.
        if from_path and "Agent of Empires" not in self._run("--help"):
            raise AoEError("PATH aoe is not Agent of Empires; set TOULMIN_AOE_COMMAND")

    def _argv(self, *args: str) -> list[str]:
        return [self.command, "-p", self.profile, *args]

    def _run(self, *args: str, timeout: float = _TIMEOUT) -> str:
        try:
            result = subprocess.run(
                self._argv(*args),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as error:
            output = error.stdout
            output_text = (
                output.decode("utf-8", errors="replace")
                if isinstance(output, bytes)
                else output or ""
            )
            ids = _output_ids(output_text)
            raise AoEError(
                f"AoE {args[0]} timed out; outcome is unknown; inspect before retrying",
                session_id=next(iter(ids)) if args[0] == "add" and len(ids) == 1 else None,
                creation_uncertain=args[0] == "add",
            ) from error
        except (OSError, UnicodeError) as error:
            raise AoEError(
                f"Cannot execute AoE {args[0]}: {error}", creation_uncertain=args[0] == "add"
            ) from error
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()[-1500:]
            ids = _output_ids(result.stdout)
            raise AoEError(
                f"AoE {args[0]} failed ({result.returncode}): {detail}",
                session_id=next(iter(ids)) if args[0] == "add" and len(ids) == 1 else None,
                creation_uncertain=args[0] == "add",
            )
        return result.stdout

    def _json(self, *args: str) -> object:
        output = self._run(*args)
        try:
            return json.loads(output)
        except (ValueError, RecursionError) as error:
            raise AoEError(f"Malformed AoE {args[0]} JSON") from error

    def _parse_session(self, value: object) -> AoESession:
        session = _session(value)
        assert isinstance(value, dict)
        if "profile" in value and value["profile"] != self.profile:
            raise AoEError("AoE response profile differs from explicitly selected profile")
        return session

    def list_sessions(self) -> tuple[AoESession, ...]:
        value = self._json("list", "--json")
        if not isinstance(value, list):
            raise AoEError("Malformed AoE list: expected an array")
        sessions = tuple(self._parse_session(item) for item in value)
        if len({item.id for item in sessions}) != len(sessions):
            raise AoEError("Malformed AoE list: duplicate session IDs")
        return sessions

    def list_all_sessions(self) -> tuple[tuple[str, AoESession], ...]:
        """Read every profile for checkout conflict checks; unknown shapes fail closed."""
        value = self._json("list", "--all", "--json")
        if not isinstance(value, list):
            raise AoEError("Malformed AoE all-profile list: expected an array")
        sessions: list[tuple[str, AoESession]] = []
        for item in value:
            if not isinstance(item, dict):
                raise AoEError("Malformed AoE all-profile session")
            profile = item.get("profile")
            if not isinstance(profile, str) or not _PROFILE.fullmatch(profile):
                raise AoEError("Malformed AoE all-profile session profile")
            sessions.append((profile, _session(item)))
        if len({(profile, item.id) for profile, item in sessions}) != len(sessions):
            raise AoEError("Malformed AoE all-profile list: duplicate session IDs")
        return tuple(sessions)

    def show(self, session_id: str) -> AoESession:
        session_id = _validate_id(session_id)
        session = self._parse_session(self._json("session", "show", session_id, "--json"))
        if session.id != session_id:
            raise AoEError("AoE show returned a different session ID")
        return session

    def current(self) -> AoESession:
        return self._parse_session(self._json("session", "current", "--json"))

    def create(
        self,
        root: Path,
        project: str | None,
        agent: str,
        *,
        title: str | None = None,
        add_directory: Path | None = None,
        codex_sandbox: str | None = None,
    ) -> AoESession:
        """Create and launch one native session at ``root``; ``project`` None is the workspace."""
        try:
            if project is not None:
                validate_project_name(project)
        except ValueError as error:
            raise AoEError(str(error)) from error
        if project is None and title is None:
            raise AoEError("A workspace session needs an explicit title")
        title = title if title is not None else f"Toulmin: {project}"
        if not title.strip() or len(title) > 200 or any(ord(c) < 32 or c == "\x7f" for c in title):
            raise AoEError("AoE session title must be one printable line of at most 200 characters")
        if agent not in ("codex", "claude"):
            raise AoEError("AoE native agent must be codex or claude")
        if codex_sandbox is not None and (
            codex_sandbox not in {"workspace-write", "inherit"}
            or agent != "codex"
            or add_directory is None
        ):
            raise AoEError(
                "codex_sandbox requires workspace-write or inherit for a Codex session "
                "with an additional records directory"
            )
        root = root.expanduser().resolve()
        if not root.is_dir():
            raise AoEError(f"AoE root is not a directory: {root}")
        extra: tuple[str, ...] = ()
        if add_directory is not None:
            directory = add_directory.expanduser().resolve()
            if not directory.is_dir():
                raise AoEError(f"Additional native directory is not a directory: {directory}")
            if (
                project is None
                and codex_sandbox is not None
                and (root.is_relative_to(directory) or directory.is_relative_to(root))
            ):
                # Workspace source and records grants are distinct. Resolve first so
                # aliases cannot turn the workspace grant into access to its parent.
                raise AoEError(
                    "codex_sandbox requires separate, non-overlapping workspace code "
                    "and records directories"
                )
            # AoE persists this shell-quoted string for resume/restart. Only a local
            # explicit choice adds a sandbox; native trust/approvals remain untouched.
            native = ["--sandbox", "workspace-write"] if codex_sandbox == "workspace-write" else []
            extra = ("--extra-args", shlex.join([*native, "--add-dir", str(directory)]))
        output = self._run(
            "add",
            str(root),
            "-t",
            title,
            "-g",
            "research" if project is None else f"research/{project}",
            "--tool",
            agent,
            "--launch",
            *extra,
            timeout=_CREATE_TIMEOUT,
        )
        ids = _output_ids(output)
        if len(ids) != 1:
            raise AoEError(
                "AoE add completed without one unambiguous session ID; inspect before retrying",
                creation_uncertain=True,
            )
        session_id = ids.pop()
        try:
            return self.show(session_id)
        except AoEError as error:
            raise AoEError(
                f"AoE created session {session_id}, but verification failed: {error}",
                session_id=session_id,
                creation_uncertain=True,
            ) from error

    def remove(self, session_id: str) -> None:
        """Move one session to AoE's trash (restorable there); never ``--purge``."""
        self._run("remove", _validate_id(session_id))

    def send(self, session_id: str, message: str) -> None:
        _validate_id(session_id)
        if not isinstance(message, str) or not message.strip() or "\x00" in message:
            raise AoEError("AoE message must be nonempty text without NUL")
        self._run("send", "--no-revive", session_id, "--", message)

    def ready(self, session_id: str) -> tuple[bool, str]:
        _validate_id(session_id)
        try:
            first = self.show(session_id)
            reason = self._not_idle(first)
            if reason:
                return False, reason
            screen = _render(self._run("session", "capture", session_id))
            reason = self._not_prompt(first.tool, *screen)
            if reason:
                return False, reason
            time.sleep(_QUIET_INTERVAL)
            second = self.show(session_id)
            reason = self._not_idle(second)
            if reason:
                return False, reason
            if second.tool != first.tool:
                return False, "AoE agent changed during readiness check"
            repeated = _render(self._run("session", "capture", session_id))
            reason = self._not_prompt(second.tool, *repeated)
            if reason:
                return False, reason
            if screen != repeated:
                return False, "Native screen is changing; wait and refresh"
        except AoEError as error:
            return False, f"AoE readiness unavailable: {error}"
        return True, "AoE reports idle/waiting and two native input captures are quiet"

    @staticmethod
    def _not_idle(session: AoESession) -> str | None:
        if session.state != "live":
            return f"AoE session state is {session.state}, expected live"
        if session.status not in ("idle", "waiting"):
            return f"AoE status is {session.status or 'unavailable'}; open AoE and refresh"
        if session.tool not in ("codex", "claude"):
            return "Readiness supports native codex/claude only"
        return None

    @staticmethod
    def _not_prompt(tool: str, screen: str, typed: str | None = None) -> str | None:
        """``typed`` is ``screen`` with dim (hint) text blanked; defaults to ``screen``."""
        # Limit heuristics to the current screen's bottom region so an old
        # permission explanation in scrollback does not always block delivery. Trailing
        # blank rows are not part of it: Codex's folder-trust menu sits above about 18
        # blank rows, which once read as an empty capture (WI8 W6, R7).
        rows = screen.splitlines()
        kept = len(rows)
        while kept and not rows[kept - 1].strip():
            kept -= 1
        # tmux can retain a launch error above blank rows and its dead-pane footer.
        # Inspect that failed pane in full before applying live-composer heuristics.
        if kept and re.match(r"^Pane is dead\b", rows[kept - 1]):
            failures = list(
                re.finditer(
                    r"(?im)^\s*(?:error(?: adding directories| loading configuration)?[: ]|"
                    r"failed to launch)[^\n]*",
                    screen,
                )
            )
            failure = failures[-1] if failures else None
            detail = failure.group(0).strip()[:400] if failure else "Native process exited"
            recovery = (
                "; inspect the native launch settings, then archive the failed session "
                "and open --new-session"
            )
            if tool == "codex":
                recovery = (
                    "; inspect native/managed launch settings; for additional-directory "
                    "refusals explicitly choose --codex-sandbox workspace-write or inherit, "
                    "then archive the failed session and open --new-session. "
                    "Managed restrictions must be resolved by the operator; no bypass was attempted"
                )
            return "Native launch failed (dead pane): " + detail + recovery
        lines = rows[:kept][-18:]
        tail = "\n".join(lines)
        if not tail.strip():
            return "Native capture is empty"
        if re.search(r"(?im)^\s*[›❯>]\s*(?:\d+[.)]|(?:yes|no)(?:\s|$))", tail):
            if re.search(r"(?i)trust (?:this|the) (?:folder|directory)", tail):
                return (
                    "Native screen contains a selection menu: the folder-trust prompt; "
                    "accept it in AoE, then refresh"
                )
            if re.search(r"(?i)update available", tail) and re.search(r"(?i)\bskip\b", tail):
                # Seen live in S5: Codex offers an npm upgrade before its first prompt.
                return (
                    "Native screen contains a selection menu: the CLI update prompt; "
                    "choose Skip (or update) in AoE, then refresh"
                )
            return "Native screen contains a selection menu; resolve it in AoE"
        marker = r"^\s*›[^\S\n]*(.*)$" if tool == "codex" else r"^\s*[>❯][^\S\n]*(.*)$"
        prompts = [i for i, line in enumerate(lines) if re.match(marker, line)]
        if not prompts:
            if (
                tool == "codex"
                and re.search(r"(?i)error adding directories|ignoring --add-dir", tail)
                and re.search(r"(?i)effective permissions|writable roots", tail)
            ):
                return (
                    "Native launch blocked: Codex refused --add-dir because its effective "
                    "permissions do not allow additional writable roots. Explicitly choose "
                    "--codex-sandbox workspace-write for this project's code and records "
                    "directories, or --codex-sandbox inherit to keep native restrictions. "
                    "Managed restrictions must be resolved by the operator; no bypass was "
                    "attempted. Then archive the failed session "
                    "and open --new-session. Toulmin has not changed global native "
                    "permission settings"
                )
            failure = re.search(
                r"(?im)^\s*(?:error(?: adding directories| loading configuration)?[: ]|"
                r"failed to launch|.*command not found|process exited with (?:code|status))[^\n]*",
                tail,
            )
            if failure:
                return (
                    "Native launch failed: "
                    + failure.group(0).strip()[:240]
                    + "; inspect the native CLI configuration and output in AoE, then "
                    "archive the failed session and open --new-session"
                )
            if _BLOCKED.search(tail):
                return _BLOCKED_REASON
            return "Native input prompt is not recognizable"
        # Busy indicators sit on the line just above the input box (AoE status is the
        # primary busy check; dialogs are menus, refused above). The agent's own reply
        # can end with words such as "approval" or "would you like" (WI8 live trial);
        # that must not block delivery forever, so only that one line counts.
        index = prompts[-1]
        above = [line for line in lines[:index] if not _BORDER.fullmatch(line)][-1:]
        nearby = above + lines[index:]
        if _BLOCKED.search("\n".join(nearby)):
            return _BLOCKED_REASON
        # A quiet occupied composer remains unsafe: AoE send would append to and
        # submit the researcher's unfinished input. Only the last prompt counts;
        # earlier prompt lines can be already-submitted messages in scrollback.
        typed_lines = (screen if typed is None else typed).splitlines()[:kept][-18:]
        match = re.match(marker, typed_lines[index])
        if match is None:  # The prompt glyph itself was dim: treat as unrecognizable.
            return "Native input prompt is not recognizable"
        current = match.group(1).strip()
        if current and not _placeholder(tool, current):
            return "Native input contains text; submit or clear it in AoE before refreshing"
        return None

    def attach(self, session_id: str) -> int:
        _validate_id(session_id)
        try:
            return subprocess.run(
                self._argv("session", "attach", session_id),
                check=False,
            ).returncode
        except OSError as error:
            raise AoEError(f"Cannot attach AoE session: {error}") from error


_SGR = re.compile(r"\x1b\[([0-9;:]*)m")
_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")


def _render(raw: str) -> tuple[str, str]:
    """Visible text, and the same text with dim (faint) characters blanked.

    Native CLIs draw empty-composer hints and suggested prompts in dim text; once ANSI
    is stripped they look exactly like a researcher's unfinished input (WI8 live trial).
    """
    plain: list[str] = []
    typed: list[str] = []
    dim = False
    position = 0
    for match in re.finditer(f"{_SGR.pattern}|{_ESCAPE.pattern}", raw):
        text = raw[position : match.start()]
        plain.append(text)
        typed.append(re.sub(r"[^\n]", " ", text) if dim else text)
        position = match.end()
        sgr = _SGR.fullmatch(match.group(0))
        if sgr is None:
            continue
        codes = re.split("[;:]", sgr.group(1))
        index = 0
        while index < len(codes):
            code = codes[index]
            if code in ("38", "48", "58"):  # Extended colours carry their own arguments.
                index += 2 if index + 1 < len(codes) and codes[index + 1] == "5" else 4
            elif code in ("", "0", "22"):
                dim = False
            elif code == "2":
                dim = True
            index += 1
    text = raw[position:]
    plain.append(text)
    typed.append(re.sub(r"[^\n]", " ", text) if dim else text)
    return "".join(plain), "".join(typed)


def _placeholder(tool: str, text: str) -> bool:
    """Empty-composer hints; ANSI stripping makes them look like typed text (WI8 live trial)."""
    if tool == "codex":
        return text == "Ask Codex to do anything"
    return re.fullmatch(r'Try "[^"\n]+"', text) is not None


def _output_ids(output: str) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z0-9])[0-9a-f]{16}(?![A-Za-z0-9])", output))
